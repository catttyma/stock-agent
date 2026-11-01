"""台股基本面分析 Agent 的命令列入口。"""

from __future__ import annotations

import argparse
import sqlite3

from analyzers.fundamental import analyze_fundamentals
from analyzers.news import analyze_news_articles
from analyzers.summarization import summarize_recent_news
from database import connect, initialize_database
from fetchers.financial import FinMindFetcher, fetch_and_store_statements
from fetchers.news import fetch_and_store_news
from reports.generator import generate_company_report
from scoring import evaluate_company


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="台股基本面分析工具")
    commands = parser.add_subparsers(dest="command", required=True)

    financial = commands.add_parser("fetch-financials", help="抓取 FinMind 財報")
    financial.add_argument("stock", help="股票代號或公司名稱，例如 2330 或 台積電")
    financial.add_argument("--start-date", required=True, help="開始日期 YYYY-MM-DD")
    financial.add_argument("--end-date", help="結束日期 YYYY-MM-DD，預設今天")
    financial.add_argument("--industry", help="產業分類")

    news = commands.add_parser("fetch-news", help="抓取最近 30 天 Google News")
    news.add_argument("query", help="公司名稱、股票代號或產業關鍵字")
    news.add_argument("--stock-code", help="將新聞關聯至已存在的股票代號")
    news.add_argument("--days", type=int, default=30, help="回溯天數，預設 30")

    fundamentals = commands.add_parser(
        "analyze-fundamentals", help="計算已抓取的基本面指標"
    )
    fundamentals.add_argument("stock", help="已建立的股票代號或公司名稱")

    news_analysis = commands.add_parser(
        "analyze-news", help="分類新聞並計算情緒與影響分數"
    )
    news_analysis.add_argument(
        "--stock-code", help="只分析指定股票；省略時分析所有未分析新聞"
    )
    news_analysis.add_argument(
        "--reprocess", action="store_true", help="重新計算既有新聞分析"
    )

    scoring = commands.add_parser("score", help="計算並保存各項與綜合評分")
    scoring.add_argument("stock", help="已建立的股票代號或公司名稱")
    scoring.add_argument("--news-days", type=int, default=30, help="消息面回溯天數")

    summarization = commands.add_parser(
        "summarize-news", help="使用 OpenAI 摘要指定股票的近期新聞"
    )
    summarization.add_argument("--stock-code", required=True, help="股票代號")
    summarization.add_argument("--days", type=int, default=30, help="回溯天數")
    summarization.add_argument("--model", help="OpenAI 模型，預設使用 OPENAI_MODEL")
    summarization.add_argument(
        "--resummarize", action="store_true", help="重新摘要已有摘要的新聞"
    )

    report = commands.add_parser(
        "generate-report", help="執行完整分析並輸出 Markdown 報告"
    )
    report.add_argument("stock", help="已建立的股票代號或公司名稱")
    report.add_argument("--news-days", type=int, default=30, help="新聞回溯天數")
    report.add_argument("--model", help="OpenAI 模型，預設使用 OPENAI_MODEL")
    report.add_argument("--output-dir", help="報告輸出目錄，預設為 reports/")
    report.add_argument(
        "--resummarize", action="store_true", help="重新摘要已有摘要的新聞"
    )
    return parser


def _find_company(connection: sqlite3.Connection, stock_input: str) -> sqlite3.Row:
    companies = connection.execute(
        """
        SELECT id, stock_code, name FROM companies
        WHERE stock_code = ? OR name = ?
        ORDER BY stock_code
        """,
        (stock_input, stock_input),
    ).fetchall()
    if not companies:
        raise ValueError(f"資料庫中找不到公司：{stock_input}，請先抓取該公司的財報")
    if len(companies) > 1:
        raise ValueError(f"公司名稱對應多筆股票，請改用股票代號：{stock_input}")
    return companies[0]


def _format_score(score: float | None, grade: str | None) -> str:
    return "資料不足" if score is None else f"{score:.1f}（{grade}）"


def main() -> None:
    args = build_parser().parse_args()
    initialize_database()

    with connect() as connection:
        if args.command == "fetch-financials":
            fetcher = FinMindFetcher()
            company = fetcher.resolve_stock(args.stock)
            company_id = fetch_and_store_statements(
                connection,
                str(company["stock_code"]),
                str(company["name"]),
                str(company["market"]),
                args.start_date,
                args.end_date,
                company["industry"],
                fetcher=fetcher,
            )
            print(f"已更新 {company['stock_code']} {company['name']} 財報，公司 ID：{company_id}")
        elif args.command == "fetch-news":
            company_id = None
            if args.stock_code:
                company = connection.execute(
                    "SELECT id FROM companies WHERE stock_code = ?",
                    (args.stock_code,),
                ).fetchone()
                if company is None:
                    raise ValueError(
                        f"找不到股票代號 {args.stock_code}，請先抓取財報建立公司資料"
                    )
                company_id = int(company["id"])
            articles = fetch_and_store_news(
                connection, args.query, company_id=company_id, days=args.days
            )
            print(f"已取得並儲存 {len(articles)} 則新聞")
        elif args.command == "analyze-fundamentals":
            company = _find_company(connection, args.stock)
            metrics = analyze_fundamentals(connection, int(company["id"]))
            if not metrics:
                print(f"{company['stock_code']} {company['name']} 尚無可分析的季度財報")
                return
            latest = metrics[-1]
            print(
                f"已分析 {company['stock_code']} {company['name']} "
                f"共 {len(metrics)} 季；最新期間 {latest['period_end_date']}"
            )
            for label, field in (
                ("EPS", "eps"),
                ("ROE", "roe"),
                ("ROA", "roa"),
                ("毛利率", "gross_margin"),
                ("負債比", "debt_ratio"),
                ("營收年增率", "revenue_yoy"),
                ("獲利年增率", "profit_yoy"),
            ):
                value = latest[field]
                print(f"{label}：{'資料不足' if value is None else f'{value:.2f}'}")
        elif args.command == "analyze-news":
            company_id = None
            if args.stock_code:
                company = _find_company(connection, args.stock_code)
                company_id = int(company["id"])
            count = analyze_news_articles(
                connection, company_id=company_id, reprocess=args.reprocess
            )
            print(f"已分析 {count} 則新聞")
        elif args.command == "summarize-news":
            company = _find_company(connection, args.stock_code)
            count = summarize_recent_news(
                connection,
                int(company["id"]),
                days=args.days,
                model=args.model,
                resummarize=args.resummarize,
            )
            print(f"已完成 {count} 則新聞摘要")
        elif args.command == "generate-report":
            company = _find_company(connection, args.stock)
            report = generate_company_report(
                connection,
                company,
                requested_input=args.stock,
                news_days=args.news_days,
                model=args.model,
                output_dir=args.output_dir,
                resummarize=args.resummarize,
            )
            print(f"股票：{company['stock_code']} {company['name']}")
            print(
                "綜合評分："
                + _format_score(
                    report.score.overall_score, report.score.overall_grade
                )
            )
            if report.score.missing_components:
                print("缺少資料：" + "、".join(report.score.missing_components))
            print(f"新聞摘要：{report.summarized_articles} 則")
            print(f"Markdown 報告：{report.output_path}")
        else:
            company = _find_company(connection, args.stock)
            result = evaluate_company(
                connection,
                int(company["id"]),
                requested_input=args.stock,
                news_days=args.news_days,
            )
            print(f"股票：{company['stock_code']} {company['name']}")
            print(
                "基本面評分："
                + _format_score(result.fundamental_score, result.fundamental_grade)
            )
            print(
                "成長性評分："
                + _format_score(result.growth_score, result.growth_grade)
            )
            print(
                f"消息面評分：{_format_score(result.news_score, result.news_grade)}"
                f"（{result.article_count} 則新聞）"
            )
            print(
                "綜合評分："
                + _format_score(result.overall_score, result.overall_grade)
            )
            if result.missing_components:
                print("缺少資料：" + "、".join(result.missing_components))
            print(f"分析記錄 ID：{result.analysis_report_id}")


if __name__ == "__main__":
    main()
