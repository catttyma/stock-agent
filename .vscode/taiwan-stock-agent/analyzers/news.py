"""規則式新聞分類、情緒判斷與影響分數。"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from html import unescape

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "interest_rate_policy": (
        "聯準會",
        "Fed",
        "央行利率",
        "升息",
        "降息",
        "利率決議",
        "利率政策",
        "interest rate",
        "rate decision",
    ),
    "macroeconomics": (
        "CPI",
        "GDP",
        "非農",
        "PMI",
        "通膨",
        "通貨膨脹",
        "失業率",
        "就業數據",
        "經濟成長",
        "景氣",
        "inflation",
        "macroeconomic",
        "economic growth",
    ),
    "earnings_conference": (
        "法說會",
        "法人說明會",
        "財測",
        "業績展望",
        "earnings call",
        "earnings conference",
        "guidance",
    ),
    "company": (
        "重大訊息",
        "併購",
        "收購",
        "增資",
        "減資",
        "資安",
        "裁員",
        "公司公告",
        "company announcement",
        "merger",
        "acquisition",
    ),
}

IMPACT_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("下修財測", -15),
    ("下調財測", -15),
    ("上修財測", 15),
    ("上調財測", 15),
    ("資安事件", -15),
    ("重大資安", -15),
    ("升息", -20),
    ("降息", 20),
    ("違約", -20),
    ("停工", -15),
    ("營收下滑", -12),
    ("獲利衰退", -12),
    ("虧損", -12),
    ("裁員", -10),
    ("罰款", -10),
    ("營收創高", 15),
    ("獲利創高", 15),
    ("訂單成長", 12),
    ("需求成長", 10),
    ("營收成長", 8),
    ("獲利成長", 10),
    ("擴大合作", 10),
    ("利空", -10),
    ("利多", 10),
    ("受惠", 8),
)


@dataclass(frozen=True)
class NewsAnalysis:
    category: str
    sentiment: str
    impact_score: int


def classify_news(text: str) -> NewsAnalysis:
    """依標題與摘要文字判斷分類、情緒及 -100 到 +100 的影響分數。"""
    normalized_text = unescape(re.sub(r"<[^>]*>", " ", text)).casefold()
    category = "industry"
    for candidate in (
        "interest_rate_policy",
        "macroeconomics",
        "earnings_conference",
        "company",
    ):
        if _contains_any(normalized_text, CATEGORY_KEYWORDS[candidate]):
            category = candidate
            break

    impact_score = _impact_from_keywords(normalized_text)
    impact_score = max(-100, min(100, impact_score))
    sentiment = (
        "positive" if impact_score > 0 else "negative" if impact_score < 0 else "neutral"
    )
    return NewsAnalysis(category, sentiment, impact_score)


def analyze_news_articles(
    connection: sqlite3.Connection,
    company_id: int | None = None,
    reprocess: bool = False,
) -> int:
    """分類尚未分析的新聞，或以 reprocess 重算既有分析。"""
    query = """
        SELECT article.id, article.title, article.summary, article.content
        FROM news_articles AS article
    """
    conditions: list[str] = []
    parameters: list[int] = []
    if company_id is not None:
        conditions.append("article.company_id = ?")
        parameters.append(company_id)
    if not reprocess:
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM news_analysis "
            "WHERE news_article_id = article.id)"
        )
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY article.published_at DESC, article.id"

    articles = connection.execute(query, parameters).fetchall()
    for article in articles:
        text = " ".join(
            part for part in (article["title"], article["summary"], article["content"]) if part
        )
        analysis = classify_news(text)
        connection.execute(
            """
            INSERT INTO news_analysis (
                news_article_id, category, sentiment, impact_score, ai_summary
            ) VALUES (?, ?, ?, ?, NULL)
            ON CONFLICT(news_article_id) DO UPDATE SET
                category = excluded.category,
                sentiment = excluded.sentiment,
                impact_score = excluded.impact_score,
                analyzed_at = CURRENT_TIMESTAMP
            """,
            (
                article["id"],
                analysis.category,
                analysis.sentiment,
                analysis.impact_score,
            ),
        )
    return len(articles)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.casefold() in text for keyword in keywords)


def _impact_from_keywords(text: str) -> int:
    matches: list[tuple[int, int, int]] = []
    for keyword, weight in IMPACT_KEYWORDS:
        normalized_keyword = keyword.casefold()
        start = text.find(normalized_keyword)
        if start >= 0:
            matches.append((start, start + len(normalized_keyword), weight))
    selected: list[tuple[int, int, int]] = []
    for match in sorted(matches, key=lambda item: (-(item[1] - item[0]), item[0])):
        start, end, _ = match
        if any(
            start < selected_end and end > selected_start
            for selected_start, selected_end, _ in selected
        ):
            continue
        selected.append(match)
    return sum(weight for _, _, weight in selected)


__all__ = ["NewsAnalysis", "analyze_news_articles", "classify_news"]
