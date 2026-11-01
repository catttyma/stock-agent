"""產生並保存分析報告的 Markdown 內容。"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scoring import ScoreResult

METRIC_LABELS = (
    ("EPS", "eps", ""),
    ("ROE", "roe", "%"),
    ("ROA", "roa", "%"),
    ("毛利率", "gross_margin", "%"),
    ("營業利益率", "operating_margin", "%"),
    ("淨利率", "net_margin", "%"),
    ("營收年增率", "revenue_yoy", "%"),
    ("營收季增率", "revenue_qoq", "%"),
    ("EPS 年增率", "eps_yoy", "%"),
    ("EPS 季增率", "eps_qoq", "%"),
    ("淨利年增率", "profit_yoy", "%"),
    ("負債比", "debt_ratio", "%"),
    ("流動比率", "current_ratio", "%"),
    ("速動比率", "quick_ratio", "%"),
    ("營業現金流", "operating_cash_flow", ""),
    ("自由現金流", "free_cash_flow", ""),
    ("投資現金流", "investing_cash_flow", ""),
    ("融資現金流", "financing_cash_flow", ""),
)
CATEGORY_LABELS = {
    "interest_rate_policy": "利率政策",
    "macroeconomics": "總體經濟",
    "company": "公司新聞",
    "earnings_conference": "法說會／財測",
    "industry": "產業消息",
}
SENTIMENT_LABELS = {
    "positive": "利多",
    "neutral": "中性",
    "negative": "利空",
}


def build_markdown_report(
    connection: sqlite3.Connection,
    company: sqlite3.Row | dict[str, Any],
    score: ScoreResult,
    start_date: date,
    end_date: date,
) -> str:
    """依資料庫最新財務指標、近期新聞及評分建立 Markdown 報告。"""
    company_id = int(company["id"])
    metrics_row = connection.execute(
        """
        SELECT * FROM financial_metrics
        WHERE company_id = ?
        ORDER BY period_end_date DESC, id DESC
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    metrics = dict(metrics_row) if metrics_row is not None else {}
    articles = connection.execute(
        """
        SELECT article.title, article.source, article.source_url,
               article.published_at, analysis.category, analysis.sentiment,
               analysis.impact_score, analysis.ai_summary
        FROM news_articles AS article
        JOIN news_analysis AS analysis
          ON analysis.news_article_id = article.id
        WHERE article.company_id = ?
          AND article.published_at IS NOT NULL
          AND julianday(article.published_at) >= julianday(?)
          AND julianday(article.published_at) < julianday(?)
        ORDER BY ABS(analysis.impact_score) DESC, article.published_at DESC
        LIMIT 10
        """,
        (
            company_id,
            start_date.isoformat(),
            (end_date + timedelta(days=1)).isoformat(),
        ),
    ).fetchall()

    lines = [
        f"# 台股基本面分析報告：{_cell(company['name'])}（{_cell(company['stock_code'])}）",
        "",
        f"- 報告日期：{end_date.isoformat()}",
        f"- 新聞分析區間：{start_date.isoformat()} 至 {end_date.isoformat()}",
        "- 資料來源：已儲存的財報與新聞資料",
        "",
        "## 評分摘要",
        "",
        "| 面向 | 分數 | 等級 |",
        "| --- | ---: | :---: |",
        f"| 基本面（60%） | {_score_text(score.fundamental_score)} | {_cell(score.fundamental_grade or '資料不足')} |",
        f"| 成長性（20%） | {_score_text(score.growth_score)} | {_cell(score.growth_grade or '資料不足')} |",
        f"| 消息面（20%） | {_score_text(score.news_score)} | {_cell(score.news_grade or '資料不足')} |",
        f"| **綜合評分** | **{_score_text(score.overall_score)}** | **{_cell(score.overall_grade or '資料不足')}** |",
        "",
        "## 最新基本面指標",
        "",
    ]
    if metrics:
        lines.extend(
            [
                f"最新財報期間：{_cell(metrics.get('period_end_date') or '資料不足')}",
                "",
                "| 指標 | 數值 |",
                "| --- | ---: |",
            ]
        )
        for label, field, unit in METRIC_LABELS:
            lines.append(f"| {label} | {_metric_text(metrics.get(field), unit)} |")
    else:
        lines.append("尚無已計算的基本面指標。")

    lines.extend(["", "## 近期重要新聞", ""])
    if articles:
        for article in articles:
            title = _cell(article["title"])
            category = CATEGORY_LABELS.get(article["category"], article["category"])
            sentiment = SENTIMENT_LABELS.get(article["sentiment"], article["sentiment"])
            published = (article["published_at"] or "")[:10] or "日期未知"
            summary = _cell(article["ai_summary"] or "尚無 AI 摘要")
            source = _cell(article["source"] or "未知來源")
            lines.extend(
                [
                    f"### {title}",
                    "",
                    f"- 日期：{published}",
                    f"- 來源：{source}",
                    f"- 分類：{category}",
                    f"- 情緒：{sentiment}（影響分數 {article['impact_score']:+.0f}）",
                    f"- 摘要：{summary}",
                    f"- 原文：{_cell(article['source_url'])}",
                    "",
                ]
            )
    else:
        lines.append("此期間沒有已分析且具發布日期的公司新聞。")

    lines.extend(
        [
            "## 投資觀察",
            "",
            _cell(score_observation(score)),
            "",
            "## 評分與資料限制",
            "",
            "- 評分依專案內的規則式指標門檻與 60%／20%／20% 權重計算；分數僅供研究參考，不構成投資建議。",
            "- 新聞分類、情緒與影響分數由關鍵字規則產生；AI 摘要只根據已取得的新聞文字，不代表對消息真偽的查證。",
            "- 財務指標可能因來源欄位缺漏而無法計算；請搭配原始財報與其他資訊自行核對。",
            "",
        ]
    )
    if score.missing_components:
        lines.extend(
            [
                "目前無法計算綜合分數，缺少：" + "、".join(score.missing_components),
                "",
            ]
        )
    return "\n".join(lines)


def save_markdown_report(
    markdown: str,
    stock_code: str,
    generated_on: date,
    report_id: int,
    output_dir: str | Path | None = None,
) -> Path:
    """將報告以 UTF-8 寫入 reports 目錄，回傳檔案路徑。"""
    directory = Path(output_dir) if output_dir is not None else Path(__file__).parent
    directory.mkdir(parents=True, exist_ok=True)
    safe_stock_code = re.sub(r"[^A-Za-z0-9._-]", "_", stock_code)
    if not safe_stock_code:
        raise ValueError("stock_code 無法用於報告檔名")
    output_path = directory / (
        f"{safe_stock_code}_{generated_on:%Y%m%d}_report_{report_id}.md"
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def _cell(value: Any) -> str:
    return str(value).replace("|", r"\|").replace("\r", " ").replace("\n", " ").strip()


def _metric_text(value: Any, unit: str) -> str:
    if value is None:
        return "資料不足"
    return f"{float(value):,.2f}{unit}"


def _score_text(value: float | None) -> str:
    return "資料不足" if value is None else f"{value:.1f}"


def score_observation(score: ScoreResult) -> str:
    if score.overall_score is None:
        missing = "、".join(score.missing_components) or "必要資料"
        return f"資料不足，尚未計算綜合分數；缺少：{missing}。"
    if score.overall_score >= 80:
        outlook = "目前規則式評分偏正向，建議持續追蹤財報與新聞變化。"
    elif score.overall_score >= 60:
        outlook = "目前規則式評分屬中間區間，建議留意各項指標的後續變化。"
    else:
        outlook = "目前規則式評分偏低，建議檢視財務指標與近期消息的風險因素。"
    return outlook + "此結果不構成投資建議。"


__all__ = ["build_markdown_report", "save_markdown_report", "score_observation"]
