"""News analyzer — uses the LLM to summarise and classify stored news.

For each unanalysed news item it produces: summary, related_symbols,
sentiment (bullish/bearish/neutral/uncertain), impact_level, why_it_matters.
News that materially affects a holding is queued as an alert.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from agents.ark_client import LLMClient as ArkClient
from db import database as db
from services._logsetup import setup

logger = setup("news_analyzer")

_SYSTEM = """你是一位美股新聞分析師。針對提供的新聞，輸出單一 JSON 物件，欄位如下：
{
  "summary": "兩三句中文摘要",
  "related_symbols": "逗號分隔的相關美股代號，如 NVDA,AMD；若不確定填空字串",
  "sentiment": "bullish / bearish / neutral / uncertain 其中之一",
  "impact_level": "low / medium / high 其中之一",
  "why_it_matters": "為什麼這則新聞重要"
}
規則：只根據新聞內容判斷，不捏造；不提供投資建議；不保證任何結果。只輸出 JSON。"""

SENTIMENTS = {"bullish", "bearish", "neutral", "uncertain"}
IMPACTS = {"low", "medium", "high"}


def _extract_json(text: str) -> Optional[dict]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


def _holdings_set() -> set[str]:
    return {h["symbol"] for h in db.active_holdings()}


def analyze_pending_news(limit: int = 10) -> int:
    client = ArkClient()
    rows = db.query(
        "SELECT * FROM news_items WHERE ai_summary IS NULL OR ai_summary='' "
        "ORDER BY created_at DESC LIMIT ?", (limit,),
    )
    if not rows:
        return 0
    if not client.enabled:
        logger.info("ARK not configured; skipping AI summarisation of %d items.", len(rows))
        return 0

    holdings = _holdings_set()
    processed = 0
    for row in rows:
        item = dict(row)
        user = (f"標題: {item.get('title')}\n來源: {item.get('source')}\n"
                f"內容: {item.get('summary') or item.get('title')}")
        result = client.chat(_SYSTEM, user, json_mode=True, endpoint="news_analysis")
        if not result:
            continue
        parsed = _extract_json(result.content) or {}

        sentiment = parsed.get("sentiment") if parsed.get("sentiment") in SENTIMENTS else "uncertain"
        impact = parsed.get("impact_level") if parsed.get("impact_level") in IMPACTS else "low"
        related = parsed.get("related_symbols") or item.get("related_symbols") or ""

        db.execute(
            "UPDATE news_items SET ai_summary=?, summary=?, related_symbols=?, "
            "sentiment=?, impact_level=? WHERE id=?",
            (parsed.get("summary", ""), parsed.get("summary", item.get("summary", "")),
             related, sentiment, impact, item["id"]),
        )
        processed += 1

        # Alert if it touches a holding and is impactful.
        related_syms = {s.strip().upper() for s in related.split(",") if s.strip()}
        hit = related_syms & holdings
        if hit and impact in ("medium", "high"):
            db.create_alert(
                symbol=",".join(sorted(hit)), alert_type="news",
                title=f"持股相關新聞 [{','.join(sorted(hit))}] ({sentiment}, {impact})",
                message=(f"{item.get('title')}\n\n{parsed.get('summary', '')}\n\n"
                         f"為何重要: {parsed.get('why_it_matters', '')}\n{item.get('url', '')}\n\n"
                         f"（僅供研究與風險提醒，非投資建議。）"),
                channel="all",
            )
    logger.info("Analyzed %d news items.", processed)
    return processed


if __name__ == "__main__":
    db.init_db()
    analyze_pending_news()
