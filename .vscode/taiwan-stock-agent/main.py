"""台股基本面分析 Agent 的命令列入口。"""

from __future__ import annotations

import argparse

from database import connect, initialize_database
from fetchers.financial import FinMindFetcher, fetch_and_store_statements
from fetchers.news import fetch_and_store_news


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="台股基本面資料抓取工具")
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
    return parser


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
        else:
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


if __name__ == "__main__":
    main()
