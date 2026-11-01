from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database import initialize_database, upsert_company
from openai import OpenAIError
from analyzers.news import analyze_news_articles
from reports.generator import generate_company_report
from scoring import evaluate_company
from analyzers.summarization import (
    NewsSummarizationError,
    summarize_recent_news,
)


class FakeOpenAIClient:
    def __init__(self, summaries: list[str] | None = None) -> None:
        self.summaries = list(summaries or ["AI 新聞摘要"])
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self.create_completion)
        )

    def create_completion(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        summary = self.summaries.pop(0)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=summary))
            ]
        )


class Phase4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "phase4.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.company_id = upsert_company(
            self.connection, "2330", "台積電", "TWSE", "半導體業"
        )
        self._insert_quarter("2024-03-31", 100, 25, 12, 10, 5, 200, 80, 120)
        self._insert_quarter("2025-03-31", 130, 39, 20, 16, 8, 240, 90, 150)
        self.connection.execute(
            """
            INSERT INTO news_articles (
                company_id, source, source_url, title, summary, content, published_at
            ) VALUES (?, '測試來源', 'https://news.example/2330',
                      '台積電營收成長', '公司營收成長且需求成長',
                      '公司公布近期營運資訊。',
                      '2026-10-30T12:00:00+00:00')
            """,
            (self.company_id,),
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_summary_is_saved_without_overwriting_rule_analysis(self) -> None:
        client = FakeOpenAIClient(["台積電營收與需求均呈成長。"])

        count = summarize_recent_news(
            self.connection,
            self.company_id,
            client=client,
            today=date(2026, 10, 31),
        )

        row = self.connection.execute(
            """
            SELECT analysis.category, analysis.sentiment, analysis.impact_score,
                   analysis.ai_summary
            FROM news_analysis AS analysis
            JOIN news_articles AS article ON article.id = analysis.news_article_id
            WHERE article.company_id = ?
            """,
            (self.company_id,),
        ).fetchone()
        self.assertEqual(count, 1)
        self.assertEqual(row["category"], "industry")
        self.assertEqual(row["sentiment"], "positive")
        self.assertEqual(row["ai_summary"], "台積電營收與需求均呈成長。")
        self.assertEqual(len(client.calls), 1)
        messages = client.calls[0]["messages"]
        self.assertIn("不可信資料", messages[0]["content"])
        self.assertIn("台積電營收成長", messages[1]["content"])
        self.assertEqual(
            summarize_recent_news(
                self.connection,
                self.company_id,
                client=FakeOpenAIClient(),
                today=date(2026, 10, 31),
            ),
            0,
        )

    def test_summary_does_not_call_openai_without_recent_articles(self) -> None:
        count = summarize_recent_news(
            self.connection,
            self.company_id,
            client=None,
            today=date(2026, 12, 31),
        )

        self.assertEqual(count, 0)

    def test_summary_loads_api_key_from_env_file_before_openai_initialization(self) -> None:
        env_file = Path(self.temp_dir.name) / ".env"
        env_file.write_text("OPENAI_API_KEY=test-key-for-unit-test\n", encoding="utf-8")

        class EnvironmentCheckingClient(FakeOpenAIClient):
            def __init__(self) -> None:
                if os.environ.get("OPENAI_API_KEY") != "test-key-for-unit-test":
                    raise AssertionError("Expected API key to be loaded from dotenv")
                super().__init__(["新聞摘要"])

        with patch.dict(os.environ):
            os.environ.pop("OPENAI_API_KEY", None)
            with (
                patch("analyzers.summarization.ENV_FILES", (env_file,)),
                patch(
                    "analyzers.summarization.OpenAI",
                    EnvironmentCheckingClient,
                ),
            ):
                count = summarize_recent_news(
                    self.connection,
                    self.company_id,
                    today=date(2026, 10, 31),
                )

        self.assertEqual(count, 1)

    def test_openai_errors_are_reported_with_article_context(self) -> None:
        class FailingClient:
            class Chat:
                class Completions:
                    @staticmethod
                    def create(**kwargs: object) -> None:
                        raise OpenAIError("service unavailable")

                completions = Completions()

            chat = Chat()

        with self.assertRaisesRegex(NewsSummarizationError, "新聞 id="):
            summarize_recent_news(
                self.connection,
                self.company_id,
                client=FailingClient(),
                today=date(2026, 10, 31),
            )

    def test_generate_report_runs_pipeline_saves_markdown_and_database_record(self) -> None:
        output_dir = Path(self.temp_dir.name) / "reports"
        client = FakeOpenAIClient(["台積電近期營收與需求成長。"])
        company = self.connection.execute(
            "SELECT id, stock_code, name FROM companies WHERE id = ?",
            (self.company_id,),
        ).fetchone()

        result = generate_company_report(
            self.connection,
            company,
            requested_input="2330",
            client=client,
            today=date(2026, 10, 31),
            output_dir=output_dir,
        )

        self.assertEqual(result.fundamental_periods, 2)
        self.assertEqual(result.analyzed_articles, 1)
        self.assertEqual(result.summarized_articles, 1)
        self.assertTrue(result.output_path.is_file())
        self.assertEqual(
            result.output_path.read_text(encoding="utf-8"), result.markdown
        )
        self.assertIn("# 台股基本面分析報告：台積電（2330）", result.markdown)
        self.assertIn("台積電近期營收與需求成長。", result.markdown)
        self.assertIn("綜合評分", result.markdown)
        report_row = self.connection.execute(
            "SELECT * FROM analysis_reports WHERE id = ?",
            (result.score.analysis_report_id,),
        ).fetchone()
        self.assertEqual(report_row["markdown_content"], result.markdown)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM news_analysis WHERE ai_summary IS NOT NULL"
            ).fetchone()[0],
            1,
        )

    def test_score_excludes_articles_outside_both_ends_of_period(self) -> None:
        analyze_news_articles(self.connection, company_id=self.company_id)
        self.connection.execute(
            """
            INSERT INTO news_articles (
                company_id, source, source_url, title, published_at
            ) VALUES (?, 'test', 'https://news.example/future', '未來新聞',
                      '2026-11-02T00:00:00+00:00')
            """,
            (self.company_id,),
        )
        future_article_id = self.connection.execute(
            "SELECT id FROM news_articles WHERE source_url = 'https://news.example/future'"
        ).fetchone()["id"]
        self.connection.execute(
            """
            INSERT INTO news_analysis (
                news_article_id, category, sentiment, impact_score
            ) VALUES (?, 'industry', 'positive', 100)
            """,
            (future_article_id,),
        )

        result = evaluate_company(
            self.connection,
            self.company_id,
            requested_input="2330",
            today=date(2026, 10, 31),
        )

        self.assertEqual(result.article_count, 1)

    def _insert_quarter(
        self,
        period_end: str,
        revenue: float,
        gross_profit: float,
        operating_income: float,
        net_income: float,
        eps: float,
        assets: float,
        liabilities: float,
        equity: float,
    ) -> None:
        period = date.fromisoformat(period_end)
        quarter = (period.month - 1) // 3 + 1
        statements = {
            "income_statement": {
                "Revenue": revenue,
                "GrossProfit": gross_profit,
                "OperatingIncome": operating_income,
                "IncomeAfterTaxes": net_income,
                "EPS": eps,
            },
            "balance_sheet": {
                "TotalAssets": assets,
                "TotalLiabilities": liabilities,
                "TotalEquity": equity,
                "CurrentAssets": assets / 2,
                "CurrentLiabilities": liabilities / 2,
                "Inventories": 10,
            },
            "cash_flow_statement": {
                "CashFlowsFromOperatingActivities": 20,
                "CashFlowsFromInvestingActivities": -5,
                "CashFlowsFromFinancingActivities": 2,
                "AcquisitionOfPropertyPlantAndEquipment": 6,
            },
        }
        for statement_type, values in statements.items():
            records = [
                {"type": metric_type, "value": value, "date": period_end}
                for metric_type, value in values.items()
            ]
            self.connection.execute(
                """
                INSERT INTO financial_statements (
                    company_id, statement_type, period_type, fiscal_year,
                    fiscal_quarter, period_end_date, source, raw_data
                ) VALUES (?, ?, 'quarterly', ?, ?, ?, 'test', ?)
                """,
                (
                    self.company_id,
                    statement_type,
                    period.year,
                    quarter,
                    period_end,
                    json.dumps(records),
                ),
            )


if __name__ == "__main__":
    unittest.main()
