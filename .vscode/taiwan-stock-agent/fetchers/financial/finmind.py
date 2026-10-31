"""FinMind 財務報表資料抓取器。"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests

API_URL = "https://api.finmindtrade.com/api/v4/data"

DATASETS = {
    "income_statement": "TaiwanStockFinancialStatements",
    "balance_sheet": "TaiwanStockBalanceSheet",
    "cash_flow_statement": "TaiwanStockCashFlowsStatement",
}


class FinMindError(RuntimeError):
    """FinMind 回應失敗或格式不符。"""


class FinMindFetcher:
    def __init__(
        self,
        token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.token = token or os.environ.get("FINMIND_TOKEN")
        self.session = session or requests.Session()

    def resolve_stock(self, stock_input: str) -> dict[str, str | None]:
        """依股票代號或公司名稱，從 FinMind 公司主檔解析公司資料。"""
        query = stock_input.strip()
        if not query:
            raise ValueError("股票代號或公司名稱不可為空")
        records = self._request({"dataset": "TaiwanStockInfo"})
        matches = [
            record
            for record in records
            if record.get("stock_id") == query or record.get("stock_name") == query
        ]
        if not matches:
            raise FinMindError(f"FinMind 公司主檔找不到：{query}")
        if len(matches) > 1:
            raise FinMindError(f"公司名稱對應多筆股票，請改用股票代號：{query}")

        record = matches[0]
        stock_code = record.get("stock_id")
        name = record.get("stock_name")
        if not isinstance(stock_code, str) or not isinstance(name, str):
            raise FinMindError(f"FinMind 公司主檔缺少有效代號或公司名稱：{query}")
        market_type = str(record.get("type", "")).lower()
        if "twse" in market_type:
            market = "TWSE"
        elif "tpex" in market_type or "otc" in market_type:
            market = "TPEx"
        else:
            market = "OTHER"
        industry = record.get("industry_category")
        return {
            "stock_code": stock_code,
            "name": name,
            "market": market,
            "industry": industry if isinstance(industry, str) else None,
        }

    def fetch_statements(
        self,
        stock_code: str,
        start_date: date | str,
        end_date: date | str | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        """抓取指定日期範圍的損益表、資產負債表與現金流量表。"""
        start = _iso_date(start_date)
        end = _iso_date(end_date or date.today())
        if start > end:
            raise ValueError("start_date 不可晚於 end_date")
        if not stock_code.strip():
            raise ValueError("stock_code 不可為空")

        results: dict[str, list[dict[str, Any]]] = {}
        for statement_type, dataset in DATASETS.items():
            results[statement_type] = self._request(
                {
                    "dataset": dataset,
                    "data_id": stock_code.strip(),
                    "start_date": start,
                    "end_date": end,
                },
                context=f"{stock_code} {statement_type}",
            )
        return results

    def _request(
        self, params: dict[str, str], context: str | None = None
    ) -> list[dict[str, Any]]:
        request_params = dict(params)
        if self.token:
            request_params["token"] = self.token
        try:
            response = self.session.get(API_URL, params=request_params, timeout=30)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            description = context or params.get("dataset", "FinMind")
            raise FinMindError(f"抓取 {description} 失敗：{error}") from error
        if not isinstance(payload, dict) or payload.get("status") != 200:
            message = (
                payload.get("msg", "回應格式錯誤")
                if isinstance(payload, dict)
                else "回應格式錯誤"
            )
            raise FinMindError(f"FinMind {params.get('dataset')} 錯誤：{message}")
        data = payload.get("data")
        if not isinstance(data, list) or any(
            not isinstance(record, dict) for record in data
        ):
            raise FinMindError(
                f"FinMind {params.get('dataset')} 未回傳有效資料清單"
            )
        return data


def _iso_date(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else date.fromisoformat(value).isoformat()
