"""AI Worker — resident analyst loop with smart cooldown.

Cooldown rules (configurable via .env):
  • core holdings     → max 1 analysis per AI_COOLDOWN_CORE_HOURS (default 2h)
  • high_focus watch  → max 1 analysis per AI_COOLDOWN_FOCUS_HOURS (default 4h)
  • general watch     → not processed here; handled by scheduler.job_close()

Multiple CRITICAL signals for the same symbol within one run are batched into
a single AI call to avoid redundant token usage.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from typing import Any

from agents.stock_analyst_agent import StockAnalystAgent
from config.settings import settings
from db import database as db
from services._logsetup import setup

logger = setup("ai_worker")

ALERT_ACTIONS = {"trim", "sell", "add", "buy_watch"}


# ── cooldown helpers ────────────────────────────────────────────────────────

def _cooldown_hours(symbol: str) -> int:
    """Return the cooldown period in hours for this symbol based on its category.

    Holdings:
      swing     → ai_cooldown_core_hours  (default 2h — short-term trades need faster updates)
      long_term → ai_cooldown_focus_hours (default 4h — buy-and-hold needs fewer interruptions)
      legacy core/high_focus → long_term treatment

    Watchlist:
      high_focus → ai_cooldown_focus_hours (4h)
      general    → 999 (batch post-market only, never via this worker)
    """
    holding = db.query_one("SELECT category FROM holdings WHERE symbol=? AND active=1", (symbol,))
    if holding:
        cat = holding.get("category") or "long_term"
        if cat == "swing":
            return settings.ai_cooldown_core_hours   # 2h
        return settings.ai_cooldown_focus_hours      # 4h (long_term + legacy)

    watch = db.query_one("SELECT category FROM watchlist WHERE symbol=? AND active=1", (symbol,))
    if watch and watch["category"] == "high_focus":
        return settings.ai_cooldown_focus_hours

    return 999  # general watchlist: effectively never via this worker


def _within_cooldown(symbol: str) -> bool:
    """True if this symbol was analyzed within its cooldown window.

    NOTE: created_at is stored as ISO-8601 with a 'T' separator and trailing 'Z'
    (e.g. 2026-06-13T09:00:00.000Z). SQLite's datetime('now', ...) emits a
    space-separated form with no 'Z'. A raw string comparison is therefore
    WRONG (the 'T' sorts after the space, so any same-day log looks "recent").
    We must wrap the column in datetime() so both sides are normalized.
    """
    hours = _cooldown_hours(symbol)
    check = db.query_one(
        "SELECT 1 ok FROM ai_analysis_logs "
        "WHERE symbol=? AND datetime(created_at) >= datetime('now', ?) LIMIT 1",
        (symbol, f"-{hours} hours"),
    )
    return bool(check)


# ── persist / alert helpers ─────────────────────────────────────────────────

def _maybe_alert(symbol: str, analysis: dict[str, Any], trigger_title: str) -> None:
    risk   = analysis.get("risk_level")
    action = analysis.get("action")
    if risk == "high" or action in ALERT_ACTIONS:
        rr = analysis.get("risk_reward_ratio")
        rr_str = f" | R:R={rr:.1f}" if isinstance(rr, (int, float)) else ""
        title = f"AI 建議 [{symbol}] {analysis.get('recommendation','')} ({action}){rr_str}"
        message = (
            f"標的: {symbol}\n"
            f"觸發: {trigger_title}\n"
            f"趨勢階段: {analysis.get('stage','—')}\n"
            f"建議: {analysis.get('recommendation')} | action={action} | risk={risk}{rr_str}\n"
            f"摘要: {analysis.get('summary','')}\n"
            f"失效條件: {analysis.get('invalidation_condition','')}\n"
            f"下一觀察價: {analysis.get('next_watch_price')}\n"
            f"\n（本訊息僅供研究與風險提醒，非投資建議，不保證獲利。）"
        )
        db.create_alert(symbol=symbol, alert_type="ai_analysis",
                        title=title, message=message, channel="all")
        logger.info("Queued alert for %s (risk=%s, action=%s)", symbol, risk, action)


def _persist(symbol: str, analysis: dict[str, Any], trigger_type: str = "signal") -> None:
    meta = analysis.get("_meta", {})
    db.log_ai_analysis({
        "symbol": symbol,
        "analysis_type": "event",
        "trigger_type": trigger_type,
        "recommendation": analysis.get("recommendation"),
        "risk_level": analysis.get("risk_level"),
        "action": analysis.get("action"),
        "summary": analysis.get("summary"),
        "reasoning": analysis.get("reasoning"),
        "invalidation_condition": analysis.get("invalidation_condition"),
        "next_watch_price": analysis.get("next_watch_price"),
        "input_snapshot_json": json.dumps(meta.get("context", {}), ensure_ascii=False, default=str),
        "model": meta.get("model"),
        "input_tokens": meta.get("input_tokens"),
        "output_tokens": meta.get("output_tokens"),
    })


# ── core processing ──────────────────────────────────────────────────────────

def _process_symbol_batch(agent: StockAnalystAgent,
                          symbol: str,
                          signals: list[dict[str, Any]]) -> None:
    """Analyze one symbol using all its pending signals batched into one context."""
    if not agent.enabled:
        logger.warning("LLM not configured; logging placeholder for %s.", symbol)
        db.log_ai_analysis({
            "symbol": symbol, "analysis_type": "event", "trigger_type": "signal",
            "recommendation": "觀察", "risk_level": "medium", "action": "wait",
            "summary": "AI 未設定（需在 .env 填入 LLM_API_KEY / LLM_MODEL）。",
            "reasoning": "", "invalidation_condition": "", "next_watch_price": None,
            "model": "unconfigured",
        })
        for sig in signals:
            db.set_signal_status(sig["id"], "analyzed")
        return

    # Build combined trigger description from all signals
    triggers = "; ".join(
        sig.get("title") or sig.get("signal_type", "") for sig in signals
    )

    # Use indicator snapshot from the most recent signal
    snap = None
    for sig in reversed(signals):
        if sig.get("indicator_snapshot_json"):
            try:
                snap = json.loads(sig["indicator_snapshot_json"])
                break
            except Exception:
                pass

    analysis = agent.analyze(symbol, trigger_description=triggers, indicator_snapshot=snap)
    if analysis is None:
        logger.warning("Analysis returned None for %s; leaving pending for retry.", symbol)
        return

    _persist(symbol, analysis, trigger_type="signal")
    _maybe_alert(symbol, analysis, triggers)

    for sig in signals:
        db.set_signal_status(sig["id"], "analyzed")

    logger.info("Analyzed %s [%d signals batched]: %s / %s / %s",
                symbol, len(signals),
                analysis.get("recommendation"),
                analysis.get("action"),
                analysis.get("risk_level"))


def run_once(agent: StockAnalystAgent) -> int:
    pending = db.pending_ai_signals(limit=50)
    if not pending:
        return 0

    # Group by symbol for batching
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for sig in pending:
        by_symbol[sig["symbol"]].append(sig)

    processed = 0
    for symbol, signals in by_symbol.items():
        try:
            if _within_cooldown(symbol):
                logger.info("Cooldown active for %s; marking signals ignored.", symbol)
                for sig in signals:
                    db.set_signal_status(sig["id"], "ignored")
                continue
            _process_symbol_batch(agent, symbol, signals)
            processed += len(signals)
        except Exception as exc:
            logger.exception("batch processing failed for %s: %s", symbol, exc)

    return processed


def run_forever(interval_seconds: int = 30) -> None:
    agent = StockAnalystAgent()
    if not agent.enabled:
        logger.warning("LLM not configured — worker will drain queue with placeholders.")
    logger.info("AI worker starting (interval=%ss, core_cooldown=%sh, focus_cooldown=%sh).",
                interval_seconds,
                settings.ai_cooldown_core_hours,
                settings.ai_cooldown_focus_hours)
    while True:
        try:
            n = run_once(agent)
            if n:
                logger.info("Processed %d pending signals.", n)
        except Exception as exc:
            logger.exception("AI worker loop error: %s", exc)
        time.sleep(interval_seconds)


if __name__ == "__main__":
    db.init_db()
    run_forever(interval_seconds=settings.ai_worker_interval_seconds)
