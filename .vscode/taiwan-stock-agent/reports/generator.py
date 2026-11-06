"""串接 Phase 3 分析、Phase 4 AI 摘要及 Markdown 報告輸出。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from analyzers.fundamental import analyze_fundamentals
from analyzers.news import analyze_news_articles
from analyzers.summarization import summarize_recent_news
from scoring import ScoreResult, evaluate_company

from .markdown import build_markdown_report, save_markdown_report


@dataclass(frozen=True)
class GeneratedReport:
    score: ScoreResult
    markdown: str
    output_path: Path
    fundamental_periods: int
    analyzed_articles: int
    summarized_articles: int


def generate_company_report(
    connection: sqlite3.Connection,
    company: sqlite3.Row | dict[str, Any],
    requested_input: str,
    news_days: int = 30,
    *,
    client: Any | None = None,
    model: str | None = None,
    today: date | None = None,
    output_dir: str | Path | None = None,
    resummarize: bool = False,
) -> GeneratedReport:
    """執行完整分析並把分數及 Markdown 報告保存至 SQLite 和檔案。"""
    if news_days < 1:
        raise ValueError("news_days 必須大於 0")
    current_date = today or date.today()
    company_id = int(company["id"])

    metrics = analyze_fundamentals(connection, company_id)
    analyzed_articles = analyze_news_articles(connection, company_id=company_id)
    summarized_articles = summarize_recent_news(
        connection,
        company_id,
        days=news_days,
        client=client,
        model=model,
        today=current_date,
        resummarize=resummarize,
    )
    score = evaluate_company(
        connection,
        company_id,
        requested_input=requested_input,
        news_days=news_days,
        today=current_date,
    )
    start_date = current_date - timedelta(days=news_days)
    markdown = build_markdown_report(
        connection,
        company,
        score,
        start_date=start_date,
        end_date=current_date,
    )
    output_path = save_markdown_report(
        markdown,
        stock_code=str(company["stock_code"]),
        generated_on=current_date,
        report_id=score.analysis_report_id,
        output_dir=output_dir,
    )
    cursor = connection.execute(
        "UPDATE analysis_reports SET markdown_content = ? WHERE id = ?",
        (markdown, score.analysis_report_id),
    )
    if cursor.rowcount != 1:
        raise RuntimeError(
            f"無法保存分析報告內容，report id={score.analysis_report_id}"
        )
    return GeneratedReport(
        score=score,
        markdown=markdown,
        output_path=output_path,
        fundamental_periods=len(metrics),
        analyzed_articles=analyzed_articles,
        summarized_articles=summarized_articles,
    )


__all__ = ["GeneratedReport", "generate_company_report"]
