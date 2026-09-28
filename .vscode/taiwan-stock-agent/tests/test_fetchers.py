from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import datetime, timezone
from pathlib import Path

from database import initialize_database, upsert_company
from fetchers.financial import fetch_and_store_statements
from fetchers.financial.finmind import DATASETS, FinMindFetcher
from fetchers.news import GoogleNewsFetcher, fetch_and_store_news


class FakeResponse:
    def __init__(self, payload: dict | None = None, content: bytes = b"") -> None:
        self._payload = payload or {}
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class QueueSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict, int]] = []

    def get(self, url: str, params: dict, timeout: int) -> FakeResponse:
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


class FetcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path(self.id().replace(".", "_") + ".db")
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row

    def tearDown(self) -> None:
        self.connection.close()
        self.database_path.unlink(missing_ok=True)

    def test_finmind_requests_all_statement_datasets(self) -> None:
        session = QueueSession(
            [FakeResponse({"status": 200, "data": []}) for _ in DATASETS]
        )

        result = FinMindFetcher(session=session).fetch_statements(
            "2330", "2025-01-01", "2025-12-31"
        )

        self.assertEqual(set(result), set(DATASETS))
        self.assertEqual(
            [call[1]["dataset"] for call in session.calls], list(DATASETS.values())
        )
        self.assertTrue(all(call[1]["start_date"] == "2025-01-01" for call in session.calls))

    def test_finmind_resolves_stock_code_and_company_metadata(self) -> None:
        fetcher = FinMindFetcher(
            session=QueueSession(
                [
                    FakeResponse(
                        {
                            "status": 200,
                            "data": [
                                {
                                    "stock_id": "2330",
                                    "stock_name": "台積電",
                                    "type": "twse",
                                    "industry_category": "半導體業",
                                }
                            ],
                        }
                    )
                ]
            )
        )

        company = fetcher.resolve_stock("台積電")

        self.assertEqual(company["stock_code"], "2330")
        self.assertEqual(company["market"], "TWSE")
        self.assertEqual(company["industry"], "半導體業")

    def test_financial_statements_are_grouped_and_upserted(self) -> None:
        statements = {
            "income_statement": [
                {"date": "2025-03-31", "type": "Revenue", "value": 100},
                {"date": "2025-03-31", "type": "EPS", "value": 2},
            ],
            "balance_sheet": [],
            "cash_flow_statement": [],
        }

        class StubFetcher:
            def fetch_statements(self, *args: object) -> dict:
                return statements

        for _ in range(2):
            fetch_and_store_statements(
                self.connection, "2330", "台積電", "TWSE", "2025-01-01",
                fetcher=StubFetcher(),  # type: ignore[arg-type]
            )

        rows = self.connection.execute(
            "SELECT * FROM financial_statements"
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["fiscal_quarter"], 1)
        self.assertEqual(len(json.loads(rows[0]["raw_data"])), 2)

    def test_google_news_filters_old_articles_and_stores_idempotently(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
          <item><title>近期新聞</title><link>https://news.example/recent</link>
            <description>摘要</description><pubDate>Mon, 21 Sep 2026 00:00:00 GMT</pubDate>
            <source>新聞來源</source></item>
          <item><title>過期新聞</title><link>https://news.example/old</link>
            <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item>
        </channel></rss>""".encode("utf-8")
        fetcher = GoogleNewsFetcher(
            QueueSession([FakeResponse(content=xml)])  # type: ignore[arg-type]
        )
        articles = fetcher.fetch(
            "2330", now=datetime(2026, 9, 28, tzinfo=timezone.utc)
        )
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0].source, "新聞來源")

        company_id = upsert_company(self.connection, "2330", "台積電", "TWSE")

        class StubNewsFetcher:
            def fetch(self, *args: object, **kwargs: object) -> list:
                return articles

        for _ in range(2):
            fetch_and_store_news(
                self.connection,
                "2330",
                company_id=company_id,
                fetcher=StubNewsFetcher(),  # type: ignore[arg-type]
            )
        saved = self.connection.execute("SELECT * FROM news_articles").fetchall()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["company_id"], company_id)


if __name__ == "__main__":
    unittest.main()
