"""財報資料抓取與儲存。"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any

from .finmind import FinMindError, FinMindFetcher


def fetch_and_store_statements(
    connection: sqlite3.Connection,
    stock_code: str,
    company_name: str,
    market: str,
    start_date: date | str,
    end_date: date | str | None = None,
    industry: str | None = None,
    fetcher: FinMindFetcher | None = None,
) -> int:
    """抓取並依公司、報表種類與季度儲存財報原始資料。"""
    from database import upsert_company

    statements = (fetcher or FinMindFetcher()).fetch_statements(
        stock_code, start_date, end_date
    )
    company_id = upsert_company(
        connection, stock_code, company_name, market, industry
    )

    for statement_type, records in statements.items():
        periods: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            period_end = record.get("date")
            if not isinstance(period_end, str):
                raise FinMindError(
                    f"{stock_code} {statement_type} 資料缺少有效 date 欄位"
                )
            try:
                period_date = date.fromisoformat(period_end)
            except ValueError as error:
                raise FinMindError(
                    f"{stock_code} {statement_type} 日期格式錯誤：{period_end}"
                ) from error
            periods[(period_date.year, (period_date.month - 1) // 3 + 1, period_end)].append(
                record
            )

        for (fiscal_year, fiscal_quarter, period_end), rows in periods.items():
            connection.execute(
                """
                INSERT INTO financial_statements (
                    company_id, statement_type, period_type, fiscal_year,
                    fiscal_quarter, period_end_date, source, raw_data
                ) VALUES (?, ?, 'quarterly', ?, ?, ?, 'FinMind', ?)
                ON CONFLICT (
                    company_id, statement_type, period_type, fiscal_year,
                    fiscal_quarter, period_end_date, source
                ) DO UPDATE SET
                    raw_data = excluded.raw_data,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (
                    company_id,
                    statement_type,
                    fiscal_year,
                    fiscal_quarter,
                    period_end,
                    json.dumps(rows, ensure_ascii=False),
                ),
            )
    return company_id


__all__ = ["FinMindError", "FinMindFetcher", "fetch_and_store_statements"]
