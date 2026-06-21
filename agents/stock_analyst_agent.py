"""The AI analyst agent: assembles context, calls the LLM, validates the output.

It pulls everything the model needs (latest price, cost basis if held, the
indicator snapshot, a short bar summary, related news, and recent prior
analyses) and returns a validated, structured analysis dict.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from agents.ark_client import LLMClient as ArkClient
from agents.prompts import (ACTIONS, ANALYST_SYSTEM_PROMPT, RECOMMENDATIONS,
                            RISK_LEVELS, build_user_prompt)
from db import database as db
from indicators import technical
from data_adapters.yfinance_history import YFinanceAdapter

logger = logging.getLogger(__name__)


def _bar_summary(symbol: str, limit: int = 20) -> dict[str, Any]:
    rows = db.query(
        "SELECT open, high, low, close, volume, timestamp FROM bars "
        "WHERE symbol=? AND timeframe='1Day' ORDER BY timestamp DESC LIMIT ?",
        (symbol, limit),
    )
    if not rows:
        return {}
    closes = [r["close"] for r in rows if r["close"] is not None]
    if not closes:
        return {}
    recent, oldest = closes[0], closes[-1]
    return {
        "bars_count": len(closes),
        "latest_close": recent,
        "window_change_pct": round((recent - oldest) / oldest * 100, 2) if oldest else None,
        "window_high": max(r["high"] for r in rows if r["high"] is not None),
        "window_low": min(r["low"] for r in rows if r["low"] is not None),
    }


def _recent_news(symbol: str, limit: int = 3) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT title, sentiment, impact_level, ai_summary, published_at FROM news_items "
        "WHERE related_symbols LIKE ? ORDER BY published_at DESC LIMIT ?",
        (f"%{symbol}%", limit),
    )
    return db.to_dicts(rows)


def _recent_ai(symbol: str, limit: int = 2) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT recommendation, risk_level, action, summary, created_at FROM ai_analysis_logs "
        "WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
        (symbol, limit),
    )
    return db.to_dicts(rows)


def _latest_indicators(symbol: str) -> dict[str, Any]:
    row = db.query_one(
        "SELECT * FROM technical_indicators WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
        (symbol,),
    )
    return dict(row) if row else {}


def build_context(symbol: str, *, trigger_description: str = "",
                  indicator_snapshot: Optional[dict] = None) -> dict[str, Any]:
    """Gather all inputs for one symbol's analysis."""
    holding = db.query_one("SELECT * FROM holdings WHERE symbol=? AND active=1", (symbol,))
    watch = db.query_one("SELECT * FROM watchlist WHERE symbol=? AND active=1", (symbol,))

    indicators = indicator_snapshot or _latest_indicators(symbol)
    if not indicators:
        # Compute on the fly from yfinance history as a last resort.
        df = YFinanceAdapter().get_bars(symbol, "1Day", limit=160)
        if not df.empty:
            indicators = technical.compute_indicators(df)

    price = db.latest_price(symbol) or indicators.get("last_close")

    context: dict[str, Any] = {
        "symbol": symbol,
        "latest_price": price,
        "trigger_description": trigger_description,
        "indicators": indicators,
        "bar_summary": _bar_summary(symbol),
        "related_news": _recent_news(symbol),
        "recent_ai_analysis": _recent_ai(symbol),
        "is_holding": bool(holding),
    }
    if holding:
        h = dict(holding)
        context["position"] = {
            "shares": h.get("shares"), "avg_cost": h.get("avg_cost"),
            "stop_loss": h.get("stop_loss"), "take_profit": h.get("take_profit"),
            "target_price": h.get("target_price"), "strategy_type": h.get("strategy_type"),
        }
        if price and h.get("avg_cost"):
            context["position"]["unrealized_pnl_pct"] = round(
                (price - h["avg_cost"]) / h["avg_cost"] * 100, 2)
    if watch:
        w = dict(watch)
        context["watch"] = {
            "category": w.get("category"), "watch_level": w.get("watch_level"),
            "target_buy_low": w.get("target_buy_low"), "target_buy_high": w.get("target_buy_high"),
            "reason": w.get("reason"),
        }
    return context


def _extract_json(text: str) -> Optional[dict]:
    text = text.strip()
    # Strip accidental markdown fences.
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _validate(parsed: dict, symbol: str) -> dict:
    """Coerce / clamp model output into the expected shape."""
    out = dict(parsed)
    out["symbol"] = out.get("symbol") or symbol
    if out.get("recommendation") not in RECOMMENDATIONS:
        out["recommendation"] = "觀察"
    if out.get("risk_level") not in RISK_LEVELS:
        out["risk_level"] = "medium"
    if out.get("action") not in ACTIONS:
        out["action"] = "wait"
    npw = out.get("next_watch_price")
    try:
        out["next_watch_price"] = float(npw) if npw is not None and npw != "" else None
    except (TypeError, ValueError):
        out["next_watch_price"] = None
    return out


class StockAnalystAgent:
    def __init__(self, client: Optional[ArkClient] = None) -> None:
        self.client = client or ArkClient()

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    def analyze(self, symbol: str, *, trigger_description: str = "",
                indicator_snapshot: Optional[dict] = None) -> Optional[dict[str, Any]]:
        """Run a full analysis. Returns the validated dict + token/model meta,
        or None if ARK is unavailable."""
        context = build_context(symbol, trigger_description=trigger_description,
                                indicator_snapshot=indicator_snapshot)
        user_prompt = build_user_prompt(context)
        result = self.client.chat(ANALYST_SYSTEM_PROMPT, user_prompt, json_mode=False,
                                  endpoint="stock_analysis")
        if result is None:
            return None

        parsed = _extract_json(result.content)
        if parsed is None:
            logger.warning("Could not parse ARK output for %s; raw=%.200s", symbol, result.content)
            parsed = {"summary": "AI 回應解析失敗", "reasoning": result.content[:500]}
        analysis = _validate(parsed, symbol)
        analysis["_meta"] = {
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "context": context,
        }
        return analysis
