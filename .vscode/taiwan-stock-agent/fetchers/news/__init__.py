"""Google News RSS 新聞抓取與儲存。"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"


class NewsFetcherError(RuntimeError):
    """新聞來源回應失敗或格式不符。"""


@dataclass(frozen=True)
class NewsArticle:
    source: str
    source_url: str
    title: str
    summary: str | None
    published_at: str | None


class GoogleNewsFetcher:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()

    def fetch(
        self, query: str, days: int = 30, now: datetime | None = None
    ) -> list[NewsArticle]:
        if not query.strip():
            raise ValueError("query 不可為空")
        if days < 1:
            raise ValueError("days 必須大於 0")
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        cutoff = current_time.astimezone(timezone.utc) - timedelta(days=days)
        try:
            response = self.session.get(
                GOOGLE_NEWS_RSS_URL,
                params={
                    "q": f"{query.strip()} after:{cutoff.date().isoformat()}",
                    "hl": "zh-TW",
                    "gl": "TW",
                    "ceid": "TW:zh-Hant",
                },
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            raise NewsFetcherError(f"抓取 Google News 失敗：{error}") from error
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as error:
            raise NewsFetcherError(f"Google News RSS XML 格式錯誤：{error}") from error

        articles: list[NewsArticle] = []
        for item in root.findall("./channel/item"):
            title = _text(item, "title")
            url = _text(item, "link")
            if not title or not url:
                continue
            published_at = _published_at(_text(item, "pubDate"))
            if published_at:
                published_time = datetime.fromisoformat(published_at)
                if published_time < cutoff:
                    continue
            source_node = item.find("source")
            source = (source_node.text or "").strip() if source_node is not None else ""
            articles.append(
                NewsArticle(
                    source=source or "Google News",
                    source_url=url,
                    title=title,
                    summary=_text(item, "description") or None,
                    published_at=published_at,
                )
            )
        return articles


def fetch_and_store_news(
    connection: sqlite3.Connection,
    query: str,
    company_id: int | None = None,
    days: int = 30,
    fetcher: GoogleNewsFetcher | None = None,
) -> list[NewsArticle]:
    """抓取近期新聞並以來源網址去重寫入資料庫。"""
    articles = (fetcher or GoogleNewsFetcher()).fetch(query, days=days)
    for article in articles:
        connection.execute(
            """
            INSERT INTO news_articles (
                company_id, source, source_url, title, summary, published_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_url) DO UPDATE SET
                company_id = COALESCE(excluded.company_id, news_articles.company_id),
                source = excluded.source,
                title = excluded.title,
                summary = excluded.summary,
                published_at = excluded.published_at
            """,
            (
                company_id,
                article.source,
                article.source_url,
                article.title,
                article.summary,
                article.published_at,
            ),
        )
    return articles


def _text(parent: ET.Element, tag: str) -> str:
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _published_at(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise NewsFetcherError(f"新聞發布時間格式錯誤：{value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


__all__ = [
    "GoogleNewsFetcher",
    "NewsArticle",
    "NewsFetcherError",
    "fetch_and_store_news",
]
