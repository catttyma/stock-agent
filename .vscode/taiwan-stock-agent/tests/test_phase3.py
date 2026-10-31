from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from analyzers.fundamental import analyze_fundamentals
from analyzers.news import analyze_news_articles, classify_news
from database import initialize_database, upsert_company
from scoring import (
    evaluate_company,
    grade_for_score,
    score_fundamentals,
    score_growth,
    score_news,
)


class Phase3Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "phase3.db"
        initialize_database(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.company_id = upsert_company(
            self.connection, "2330", "台積電", "TWSE", "半導體業"
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.temp_dir.cleanup()

    def test_database_initialization_migrates_profit_growth_column(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        schema_path = Path(__file__).parents[1] / "database" / "schema.sql"
        legacy_schema = schema_path.read_text(encoding="utf-8").replace(
            "    profit_yoy REAL,\n", ""
        )
        legacy_connection = sqlite3.connect(legacy_path)
        legacy_connection.executescript(legacy_schema)
        legacy_connection.close()

        initialize_database(legacy_path)

        migrated = sqlite3.connect(legacy_path)
        columns = {
            row[1] for row in migrated.execute("PRAGMA table_info(financial_metrics)")
        }
        migrated.close()
        self.assertIn("profit_yoy", columns)

    def test_fundamental_analysis_computes_and_upserts_all_quarters(self) -> None:
        self._insert_quarter(
            "2024-03-31",
            revenue=100,
            gross_profit=30,
            operating_income=10,
            net_income=8,
            eps=1,
            assets=200,
            liabilities=100,
            equity=100,
            current_assets=80,
            current_liabilities=40,
            inventory=10,
            operating_cash_flow=20,
            investing_cash_flow=-4,
            financing_cash_flow=2,
            capex=5,
        )
        self._insert_quarter(
            "2024-12-31",
            revenue=150,
            gross_profit=45,
            operating_income=20,
            net_income=12,
            eps=1.5,
            assets=250,
            liabilities=110,
            equity=140,
            current_assets=100,
            current_liabilities=50,
            inventory=15,
            operating_cash_flow=30,
            investing_cash_flow=-6,
            financing_cash_flow=3,
            capex=7,
        )
        self._insert_quarter(
            "2025-03-31",
            revenue=200,
            gross_profit=80,
            operating_income=40,
            net_income=30,
            eps=3,
            assets=300,
            liabilities=120,
            equity=180,
            current_assets=120,
            current_liabilities=60,
            inventory=20,
            operating_cash_flow=50,
            investing_cash_flow=-10,
            financing_cash_flow=5,
            capex=12,
        )

        first_run = analyze_fundamentals(self.connection, self.company_id)
        second_run = analyze_fundamentals(self.connection, self.company_id)

        latest = first_run[-1]
        self.assertEqual(len(first_run), 3)
        self.assertAlmostEqual(latest["gross_margin"], 40)
        self.assertAlmostEqual(latest["operating_margin"], 20)
        self.assertAlmostEqual(latest["net_margin"], 15)
        self.assertAlmostEqual(latest["roe"], 18.75)
        self.assertAlmostEqual(latest["roa"], 100 * 30 / 275)
        self.assertAlmostEqual(latest["debt_ratio"], 40)
        self.assertAlmostEqual(latest["current_ratio"], 200)
        self.assertAlmostEqual(latest["quick_ratio"], 100 * (120 - 20) / 60)
        self.assertAlmostEqual(latest["revenue_yoy"], 100)
        self.assertAlmostEqual(latest["revenue_qoq"], 100 * (200 - 150) / 150)
        self.assertAlmostEqual(latest["eps_yoy"], 200)
        self.assertAlmostEqual(latest["profit_yoy"], 275)
        self.assertAlmostEqual(latest["operating_cash_flow"], 50)
        self.assertAlmostEqual(latest["free_cash_flow"], 38)
        self.assertAlmostEqual(latest["investing_cash_flow"], -10)
        self.assertAlmostEqual(latest["financing_cash_flow"], 5)
        self.assertEqual(len(second_run), 3)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM financial_metrics").fetchone()[0],
            3,
        )

    def test_news_classifier_uses_expected_categories_and_impact_examples(self) -> None:
        rate_news = classify_news("Fed 宣布降息")
        forecast_news = classify_news("公司上修財測")
        security_news = classify_news("重大資安事件造成客戶疑慮")
        neutral_news = classify_news("公司舉辦法說會")

        self.assertEqual((rate_news.category, rate_news.sentiment, rate_news.impact_score),
                         ("interest_rate_policy", "positive", 20))
        self.assertEqual((forecast_news.category, forecast_news.sentiment, forecast_news.impact_score),
                         ("earnings_conference", "positive", 15))
        self.assertEqual((security_news.category, security_news.sentiment, security_news.impact_score),
                         ("company", "negative", -15))
        self.assertEqual((neutral_news.category, neutral_news.sentiment, neutral_news.impact_score),
                         ("earnings_conference", "neutral", 0))

    def test_news_analysis_is_persisted_idempotently(self) -> None:
        self.connection.execute(
            """
            INSERT INTO news_articles (
                company_id, source, source_url, title, summary, published_at
            ) VALUES (?, 'test', 'https://news.example/1', 'Fed 宣布降息', NULL,
                      '2026-10-30T12:00:00+00:00')
            """,
            (self.company_id,),
        )

        self.assertEqual(analyze_news_articles(self.connection, self.company_id), 1)
        self.assertEqual(analyze_news_articles(self.connection, self.company_id), 0)
        self.assertEqual(analyze_news_articles(self.connection, self.company_id, True), 1)
        row = self.connection.execute("SELECT * FROM news_analysis").fetchone()
        self.assertEqual(row["category"], "interest_rate_policy")
        self.assertEqual(row["sentiment"], "positive")
        self.assertEqual(row["impact_score"], 20)
        self.assertIsNone(row["ai_summary"])

    def test_scoring_weights_grades_and_missing_data(self) -> None:
        fundamental = score_fundamentals(
            {
                "eps": 45.2,
                "roe": 28,
                "roa": 12,
                "gross_margin": 40,
                "debt_ratio": 20,
            }
        )
        growth = score_growth(
            {
                "revenue_yoy": 20,
                "revenue_qoq": -10,
                "eps_yoy": 10,
                "eps_qoq": 0,
                "profit_yoy": 20,
            }
        )

        self.assertEqual(fundamental, 99)
        self.assertAlmostEqual(growth, 76.25)
        self.assertEqual(score_news([20]), 60)
        self.assertIsNone(score_news([]))
        self.assertEqual(
            [grade_for_score(score) for score in (90, 80, 70, 60, 59.9, None)],
            ["A", "B", "C", "D", "E", None],
        )

    def test_evaluate_company_requires_all_components_for_overall_score(self) -> None:
        self._insert_quarter(
            "2024-03-31",
            revenue=100,
            gross_profit=30,
            operating_income=20,
            net_income=15,
            eps=1,
            assets=250,
            liabilities=100,
            equity=150,
            current_assets=100,
            current_liabilities=50,
            inventory=10,
            operating_cash_flow=30,
            investing_cash_flow=-5,
            financing_cash_flow=2,
            capex=5,
        )
        self._insert_quarter(
            "2025-03-31",
            revenue=200,
            gross_profit=80,
            operating_income=40,
            net_income=30,
            eps=3,
            assets=300,
            liabilities=120,
            equity=180,
            current_assets=120,
            current_liabilities=60,
            inventory=20,
            operating_cash_flow=50,
            investing_cash_flow=-10,
            financing_cash_flow=5,
            capex=12,
        )
        analyze_fundamentals(self.connection, self.company_id)

        partial = evaluate_company(
            self.connection, self.company_id, "2330", today=date(2026, 10, 31)
        )
        self.assertIsNone(partial.overall_score)
        self.assertEqual(partial.missing_components, ("news",))

        self.connection.execute(
            """
            INSERT INTO news_articles (
                company_id, source, source_url, title, published_at
            ) VALUES (?, 'test', 'https://news.example/score', 'Fed 降息',
                      '2026-10-30T12:00:00+00:00')
            """,
            (self.company_id,),
        )
        article_id = self.connection.execute(
            "SELECT id FROM news_articles WHERE source_url = 'https://news.example/score'"
        ).fetchone()["id"]
        self.connection.execute(
            """
            INSERT INTO news_analysis (
                news_article_id, category, sentiment, impact_score
            ) VALUES (?, 'interest_rate_policy', 'positive', 20)
            """,
            (article_id,),
        )
        result = evaluate_company(
            self.connection, self.company_id, "2330", today=date(2026, 10, 31)
        )

        self.assertIsNotNone(result.overall_score)
        self.assertEqual(result.news_score, 60)
        self.assertEqual(result.article_count, 1)
        self.assertAlmostEqual(
            result.overall_score,
            result.fundamental_score * 0.60
            + result.growth_score * 0.20
            + result.news_score * 0.20,
        )
        saved = self.connection.execute(
            "SELECT * FROM analysis_reports WHERE id = ?",
            (result.analysis_report_id,),
        ).fetchone()
        self.assertEqual(saved["overall_grade"], result.overall_grade)
        self.assertIsNone(saved["markdown_content"])

    def _insert_quarter(
        self,
        period_end: str,
        *,
        revenue: float,
        gross_profit: float,
        operating_income: float,
        net_income: float,
        eps: float,
        assets: float,
        liabilities: float,
        equity: float,
        current_assets: float,
        current_liabilities: float,
        inventory: float,
        operating_cash_flow: float,
        investing_cash_flow: float,
        financing_cash_flow: float,
        capex: float,
    ) -> None:
        values_by_type = {
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
                "CurrentAssets": current_assets,
                "CurrentLiabilities": current_liabilities,
                "Inventories": inventory,
            },
            "cash_flow_statement": {
                "CashFlowsFromOperatingActivities": operating_cash_flow,
                "CashFlowsFromInvestingActivities": investing_cash_flow,
                "CashFlowsFromFinancingActivities": financing_cash_flow,
                "AcquisitionOfPropertyPlantAndEquipment": capex,
            },
        }
        period = date.fromisoformat(period_end)
        quarter = (period.month - 1) // 3 + 1
        for statement_type, values in values_by_type.items():
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
