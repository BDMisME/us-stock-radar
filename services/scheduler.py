"""AI analysis scheduler (spec section 9).

Drives the *scheduled* analyses (the event-driven ones come from the signal
engine -> ai_worker). Uses APScheduler with cron triggers anchored to US
Eastern market hours:

  Core holdings (category='core' or any holding):
    - pre-open summary (09:00 ET)
    - intraday condensed analysis every 30 min (10:00-15:30 ET)
    - close summary (16:05 ET)
  High-focus watchlist:
    - pre-open summary (09:00 ET)
    - intraday every 60 min
  General watchlist:
    - close summary only (event-driven otherwise)
  News:
    - fetched/analyzed once per Taiwan evening (18:00 Asia/Taipei)

If ARK is unconfigured, scheduled jobs no-op gracefully (logged).
"""
from __future__ import annotations

from typing import Iterable

from agents.stock_analyst_agent import StockAnalystAgent
from db import database as db
from services._logsetup import setup

logger = setup("scheduler")

_agent = StockAnalystAgent()


def _analyze_universe(symbols: Iterable[str], analysis_type: str, trigger: str) -> None:
    symbols = list(symbols)
    if not symbols:
        return
    if not _agent.enabled:
        logger.info("[%s] ARK not configured; skipping %d symbols.", analysis_type, len(symbols))
        return
    logger.info("[%s] analyzing %d symbols (%s)", analysis_type, len(symbols), trigger)
    for sym in symbols:
        try:
            analysis = _agent.analyze(sym, trigger_description=trigger)
            if not analysis:
                continue
            meta = analysis.get("_meta", {})
            db.log_ai_analysis({
                "symbol": sym, "analysis_type": analysis_type, "trigger_type": "schedule",
                "recommendation": analysis.get("recommendation"),
                "risk_level": analysis.get("risk_level"), "action": analysis.get("action"),
                "summary": analysis.get("summary"), "reasoning": analysis.get("reasoning"),
                "invalidation_condition": analysis.get("invalidation_condition"),
                "next_watch_price": analysis.get("next_watch_price"),
                "model": meta.get("model"), "input_tokens": meta.get("input_tokens"),
                "output_tokens": meta.get("output_tokens"),
            })
        except Exception as exc:
            logger.exception("scheduled analysis failed for %s: %s", sym, exc)


# ---- job targets ----------------------------------------------------------
def _core_symbols() -> list[str]:
    return [h["symbol"] for h in db.active_holdings()]


def _focus_symbols() -> list[str]:
    return [w["symbol"] for w in db.active_watchlist("high_focus")]


def _general_symbols() -> list[str]:
    return db.general_watch_symbols()


def job_preopen() -> None:
    _analyze_universe(_core_symbols(), "preopen", "開盤前摘要 - 核心持股")
    _analyze_universe(_focus_symbols(), "preopen", "開盤前摘要 - 高關注")


def job_intraday_core() -> None:
    _analyze_universe(_core_symbols(), "intraday", "盤中濃縮分析(30 分) - 核心持股")


def job_intraday_focus() -> None:
    _analyze_universe(_focus_symbols(), "intraday", "盤中濃縮分析(60 分) - 高關注")


def job_close() -> None:
    _analyze_universe(_core_symbols(), "close", "收盤總結 - 核心持股")
    _analyze_universe(_general_symbols(), "close", "收盤摘要 - 一般觀察")


def job_news() -> None:
    try:
        from news.news_fetcher import fetch_and_store
        from news.news_analyzer import analyze_pending_news
        fetch_and_store(limit=10)
        analyze_pending_news()
    except Exception as exc:
        logger.exception("news job failed: %s", exc)


def build_scheduler():
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    tz = "America/New_York"
    sched = BlockingScheduler(timezone=tz)

    sched.add_job(job_preopen, CronTrigger(hour=9, minute=0, day_of_week="mon-fri", timezone=tz))
    sched.add_job(job_news, CronTrigger(hour=18, minute=0, day_of_week="mon-fri", timezone="Asia/Taipei"))
    # Intraday core every 30 min, 10:00-15:30
    sched.add_job(job_intraday_core,
                  CronTrigger(hour="10-15", minute="0,30", day_of_week="mon-fri", timezone=tz))
    # Intraday focus hourly, 10:00-15:00
    sched.add_job(job_intraday_focus,
                  CronTrigger(hour="10-15", minute=0, day_of_week="mon-fri", timezone=tz))
    sched.add_job(job_close, CronTrigger(hour=16, minute=5, day_of_week="mon-fri", timezone=tz))
    return sched


if __name__ == "__main__":
    db.init_db()
    logger.info("Scheduler starting (US Eastern market hours).")
    if not _agent.enabled:
        logger.warning("ARK not configured; scheduled analyses will be skipped until keys are set.")
    build_scheduler().start()
