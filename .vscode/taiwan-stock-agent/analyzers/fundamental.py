"""從已儲存的原始財報計算季度基本面指標。"""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import defaultdict
from typing import Any


FIELD_ALIASES: dict[str, set[str]] = {
    "revenue": {
        "revenue",
        "營業收入",
        "營業收入合計",
        "營業收入淨額",
    },
    "gross_profit": {"grossprofit", "grossprofitloss", "營業毛利", "營業毛利淨額"},
    "operating_income": {
        "operatingincome",
        "operatingincomeloss",
        "營業利益",
        "營業利益（損失）",
    },
    "net_income": {
        "incomeaftertaxes",
        "incomeaftertax",
        "netincome",
        "profitloss",
        "本期淨利",
        "本期淨利（淨損）",
        "稅後淨利",
    },
    "eps": {"eps", "earningspershare", "basicearningspershare", "每股盈餘"},
    "total_assets": {"totalassets", "資產總計"},
    "total_liabilities": {"totalliabilities", "負債總計"},
    "total_equity": {
        "totalequity",
        "equityattributabletoownersofparent",
        "權益總計",
        "歸屬於母公司業主之權益合計",
    },
    "current_assets": {"currentassets", "流動資產合計"},
    "current_liabilities": {"currentliabilities", "流動負債合計"},
    "inventory": {"inventories", "inventory", "存貨"},
    "operating_cash_flow": {
        "cashflowsfromoperatingactivities",
        "cashprovidedbyoperatingactivities",
        "netcashflowsfromusedinoperatingactivities",
        "營業活動之淨現金流入（流出）",
        "營業活動之淨現金流量",
    },
    "investing_cash_flow": {
        "cashflowsfrominvestingactivities",
        "cashprovidedbyinvestingactivities",
        "netcashflowsfromusedininvestingactivities",
        "投資活動之淨現金流入（流出）",
        "投資活動之淨現金流量",
    },
    "financing_cash_flow": {
        "cashflowsfromfinancingactivities",
        "cashprovidedbyfinancingactivities",
        "netcashflowsfromusedinfinancingactivities",
        "籌資活動之淨現金流入（流出）",
        "籌資活動之淨現金流量",
    },
    "capital_expenditure": {
        "acquisitionofpropertyplantandequipment",
        "paymentstoacquirepropertyplantandequipment",
        "purchaseofpropertyplantandequipment",
        "capitalexpenditures",
        "取得不動產、廠房及設備",
        "購置不動產、廠房及設備",
    },
}

STATEMENT_TYPES = {
    "income_statement",
    "balance_sheet",
    "cash_flow_statement",
}


def analyze_fundamentals(
    connection: sqlite3.Connection, company_id: int
) -> list[dict[str, Any]]:
    """計算並 upsert 公司所有有財報資料季度的指標。"""
    statements = connection.execute(
        """
        SELECT id, statement_type, period_type, fiscal_year, fiscal_quarter,
               period_end_date, raw_data
        FROM financial_statements
        WHERE company_id = ?
          AND period_type = 'quarterly'
        ORDER BY period_end_date, id
        """,
        (company_id,),
    ).fetchall()
    if not statements:
        return []

    periods: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"statement_ids": {}, "values": {}}
    )
    for statement in statements:
        statement_type = statement["statement_type"]
        if statement_type not in STATEMENT_TYPES:
            continue
        try:
            records = json.loads(statement["raw_data"])
        except (TypeError, json.JSONDecodeError) as error:
            raise ValueError(
                f"財報資料格式錯誤，statement id={statement['id']}"
            ) from error
        if not isinstance(records, list) or any(
            not isinstance(record, dict) for record in records
        ):
            raise ValueError(
                f"財報資料必須是物件清單，statement id={statement['id']}"
            )
        period = periods[statement["period_end_date"]]
        period["statement_ids"][statement_type] = statement["id"]
        period["fiscal_year"] = statement["fiscal_year"]
        period["fiscal_quarter"] = statement["fiscal_quarter"]
        for field in _fields_for_statement(statement_type):
            value = _extract_value(records, FIELD_ALIASES[field])
            if value is not None:
                period["values"][field] = value

    ordered_dates = sorted(periods)
    date_by_quarter = {
        (
            periods[period_date]["fiscal_year"],
            periods[period_date]["fiscal_quarter"],
        ): period_date
        for period_date in ordered_dates
    }

    results: list[dict[str, Any]] = []
    for period_date in ordered_dates:
        period = periods[period_date]
        fiscal_year = period["fiscal_year"]
        fiscal_quarter = period["fiscal_quarter"]
        values = period["values"]
        previous_quarter = _previous_quarter_date(
            date_by_quarter, fiscal_year, fiscal_quarter
        )
        previous_year = date_by_quarter.get((fiscal_year - 1, fiscal_quarter))
        prior_values = periods[previous_quarter]["values"] if previous_quarter else {}
        prior_year_values = periods[previous_year]["values"] if previous_year else {}
        prior_balance = prior_values

        revenue = values.get("revenue")
        gross_profit = values.get("gross_profit")
        operating_income = values.get("operating_income")
        net_income = values.get("net_income")
        total_assets = values.get("total_assets")
        total_liabilities = values.get("total_liabilities")
        total_equity = values.get("total_equity")
        current_assets = values.get("current_assets")
        current_liabilities = values.get("current_liabilities")
        inventory = values.get("inventory")
        operating_cash_flow = values.get("operating_cash_flow")
        investing_cash_flow = values.get("investing_cash_flow")
        financing_cash_flow = values.get("financing_cash_flow")
        capital_expenditure = values.get("capital_expenditure")

        metrics: dict[str, Any] = {
            "company_id": company_id,
            "financial_statement_id": period["statement_ids"].get("income_statement"),
            "period_type": "quarterly",
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "period_end_date": period_date,
            "eps": values.get("eps"),
            "roe": _return_ratio(
                net_income, total_equity, prior_balance.get("total_equity")
            ),
            "roa": _return_ratio(
                net_income, total_assets, prior_balance.get("total_assets")
            ),
            "gross_margin": _percentage(gross_profit, revenue),
            "operating_margin": _percentage(operating_income, revenue),
            "net_margin": _percentage(net_income, revenue),
            "revenue_yoy": _growth(revenue, prior_year_values.get("revenue")),
            "revenue_qoq": _growth(revenue, prior_values.get("revenue")),
            "eps_yoy": _growth(values.get("eps"), prior_year_values.get("eps")),
            "eps_qoq": _growth(values.get("eps"), prior_values.get("eps")),
            "profit_yoy": _growth(net_income, prior_year_values.get("net_income")),
            "debt_ratio": _percentage(total_liabilities, total_assets),
            "current_ratio": _percentage(current_assets, current_liabilities),
            "quick_ratio": _percentage(
                (
                    current_assets - inventory
                    if current_assets is not None and inventory is not None
                    else None
                ),
                current_liabilities,
            ),
            "operating_cash_flow": operating_cash_flow,
            "free_cash_flow": (
                operating_cash_flow - abs(capital_expenditure)
                if operating_cash_flow is not None and capital_expenditure is not None
                else None
            ),
            "investing_cash_flow": investing_cash_flow,
            "financing_cash_flow": financing_cash_flow,
        }
        _upsert_metrics(connection, metrics)
        results.append(metrics)
    return results


def _fields_for_statement(statement_type: str) -> tuple[str, ...]:
    if statement_type == "income_statement":
        return (
            "revenue",
            "gross_profit",
            "operating_income",
            "net_income",
            "eps",
        )
    if statement_type == "balance_sheet":
        return (
            "total_assets",
            "total_liabilities",
            "total_equity",
            "current_assets",
            "current_liabilities",
            "inventory",
        )
    return (
        "operating_cash_flow",
        "investing_cash_flow",
        "financing_cash_flow",
        "capital_expenditure",
    )


def _normalize_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", str(value).lower())


def _extract_value(records: list[dict[str, Any]], aliases: set[str]) -> float | None:
    normalized_aliases = {_normalize_label(alias) for alias in aliases}
    for record in records:
        labels = (record.get("type"), record.get("origin_name"))
        if not any(
            label is not None and _normalize_label(label) in normalized_aliases
            for label in labels
        ):
            continue
        value = record.get("value")
        try:
            numeric = float(str(value).replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            return numeric
    return None


def _percentage(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator * 100


def _return_ratio(
    profit: float | None,
    current_balance: float | None,
    previous_balance: float | None,
) -> float | None:
    if profit is None or current_balance is None:
        return None
    average_balance = (
        (current_balance + previous_balance) / 2
        if previous_balance is not None
        else current_balance
    )
    return _percentage(profit, average_balance)


def _growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    return (current - previous) / previous * 100


def _previous_quarter_date(
    date_by_quarter: dict[tuple[int, int], str], year: int, quarter: int
) -> str | None:
    previous_year, previous_quarter = (
        (year - 1, 4) if quarter == 1 else (year, quarter - 1)
    )
    return date_by_quarter.get((previous_year, previous_quarter))


def _upsert_metrics(connection: sqlite3.Connection, metrics: dict[str, Any]) -> None:
    fields = tuple(metrics)
    updates = ", ".join(
        f"{field} = excluded.{field}"
        for field in fields
        if field
        not in {
            "company_id",
            "period_type",
            "fiscal_year",
            "fiscal_quarter",
            "period_end_date",
        }
    )
    placeholders = ", ".join("?" for _ in fields)
    connection.execute(
        f"""
        INSERT INTO financial_metrics ({", ".join(fields)})
        VALUES ({placeholders})
        ON CONFLICT (company_id, period_type, fiscal_year, fiscal_quarter, period_end_date)
        DO UPDATE SET {updates}, calculated_at = CURRENT_TIMESTAMP
        """,
        tuple(metrics[field] for field in fields),
    )


__all__ = ["analyze_fundamentals"]
