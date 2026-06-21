"""News fetcher — pulls headlines from Finnhub, FMP, and an RSS fallback.

Stored into news_items (deduplicated by URL). AI summarisation happens later
in news_analyzer so fetching stays fast and provider-agnostic.
"""
from __future__ import annotations

from typing import Optional

from config.settings import settings
from data_adapters.base import NewsArticle
from data_adapters.finnhub_client import FinnhubAdapter
from data_adapters.fmp_client import FMPAdapter
from db import database as db
from services._logsetup import setup

logger = setup("news_fetcher")

# Generic market RSS feeds used when no API news provider is configured.
_RSS_FEEDS = [
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",
]


def _store(article: NewsArticle) -> bool:
    if not article.url:
        return False
    existing = db.query_one("SELECT id FROM news_items WHERE url=?", (article.url,))
    if existing:
        return False
    db.insert("news_items", {
        "title": article.title, "source": article.source, "url": article.url,
        "published_at": article.published_at, "summary": article.summary,
        "related_symbols": article.related_symbols, "created_at": db.utcnow_iso(),
    })
    return True


def _from_rss(limit: int) -> list[NewsArticle]:
    try:
        import feedparser
    except Exception:
        return []
    out: list[NewsArticle] = []
    for feed_url in _RSS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            logger.debug("RSS parse failed %s: %s", feed_url, exc)
            continue
        for entry in parsed.entries[:limit]:
            out.append(NewsArticle(
                title=getattr(entry, "title", ""),
                source=parsed.feed.get("title", "RSS") if hasattr(parsed, "feed") else "RSS",
                url=getattr(entry, "link", ""),
                published_at=getattr(entry, "published", ""),
                summary=getattr(entry, "summary", "")[:500],
            ))
        if len(out) >= limit:
            break
    return out[:limit]


def fetch_and_store(limit: int = 10, symbols: Optional[list[str]] = None) -> int:
    """Fetch up to `limit` articles and store new ones. Returns count stored."""
    articles: list[NewsArticle] = []

    finnhub = FinnhubAdapter()
    fmp = FMPAdapter()

    if symbols:
        for sym in symbols:
            if finnhub.enabled:
                articles += finnhub.get_news(sym, limit=3)
            elif fmp.enabled:
                articles += fmp.get_news(sym, limit=3)
    else:
        if finnhub.enabled:
            articles += finnhub.get_news(None, limit=limit)
        elif fmp.enabled:
            articles += fmp.get_news(None, limit=limit)

    if not articles:
        logger.info("No API news provider configured/available; using RSS fallback.")
        articles = _from_rss(limit)

    stored = sum(1 for a in articles if _store(a))
    logger.info("Fetched %d articles, stored %d new.", len(articles), stored)
    return stored


if __name__ == "__main__":
    db.init_db()
    fetch_and_store(limit=10)
