# Taiwan Stock Fundamental Agent

Phase 2 provides FinMind financial-statement fetching and Google News RSS
fetching. Phase 3 calculates quarterly fundamentals, rule-based news analysis,
and weighted scores. Results are stored in the SQLite schema in
`database/schema.sql`.

## Setup

Use Python 3.13 and install the project dependencies:

```powershell
python -m pip install -r requirements.txt
```

Set `FINMIND_TOKEN` in the environment if your FinMind plan requires an API
token. The database defaults to `database/stock_agent.db`; set `DATABASE_PATH`
to use a different SQLite file.

## Fetch financial statements

```powershell
python main.py fetch-financials 2330 --start-date 2024-01-01
```

The fetcher resolves a stock code or exact company name using FinMind's stock
master, then stores income statements, balance sheets, and cash-flow statements
as raw JSON grouped by reported date. Re-running a request updates the same
company/source/period records instead of creating duplicates.

## Fetch recent news

```powershell
python main.py fetch-news 2330 --stock-code 2330 --days 30
```

News is searched through Google News RSS, filtered to the requested lookback
period, and deduplicated by article URL. `--stock-code` associates articles
with a company already created by the financial-statement command.

Both commands require network access. Fetcher tests use mocked responses and
can be run without contacting external services:

```powershell
python -m unittest discover -s tests -v
```

## Phase 3: analyze and score

After fetching financial statements, calculate and save the quarterly metrics:

```powershell
python main.py analyze-fundamentals 2330
```

After fetching news, classify and score unanalyzed articles. Omit
`--stock-code` to analyze all unanalyzed articles; use `--reprocess` to update
existing analyses with the current rules:

```powershell
python main.py analyze-news --stock-code 2330
python main.py analyze-news --stock-code 2330 --reprocess
```

Calculate scores and save the result to `analysis_reports`:

```powershell
python main.py score 2330 --news-days 30
```

The score command uses the latest stored quarter and analyzed company news
within the selected lookback period. It stores the fundamental, growth, news,
and overall scores and grades; Markdown report generation remains Phase 4.

### Calculation rules

- Margins, returns, growth, debt ratio, and liquidity ratios are stored as
  percentage points (for example, `25.0` means 25%). ROE/ROA use average
  period-end equity/assets when the previous quarter is available; otherwise
  they use the current period-end balance.
- Quarterly growth compares with the matching quarter a year earlier or the
  immediately preceding fiscal quarter. Growth is left unavailable if the
  comparison period is missing or its base value is not positive.
- Free cash flow is operating cash flow minus the absolute value of reported
  capital expenditure. It remains unavailable when either input is missing.
- News category, sentiment, and impact (`-100` to `+100`) use a deterministic
  Traditional Chinese/English keyword ruleset; there is no AI summary in
  Phase 3. Impact `0` maps to a news score of `50`.
- Fundamental metric scores use linear threshold bands for ROE, ROA, gross
  margin, and debt ratio; positive EPS below 10 scores 80, EPS of 10 or more
  scores 100, and non-positive EPS scores 0. Growth indicators use
  `clamp(50 + growth_percent * 2.5, 0, 100)`. The respective metrics have equal
  weights within the fundamental component; growth weights are revenue YoY
  35%, revenue QoQ 15%, EPS YoY 30%, EPS QoQ 10%, and profit YoY 10%.
- Fundamental and growth sub-scores average only available indicators and
  renormalize their indicator weights. The overall score is withheld until all
  three PRD components are available; missing sections are printed explicitly.
- Grade thresholds are A (90+), B (80–<90), C (70–<80), D (60–<70), and E
  (<60). Scores are research aids, not investment advice.

On startup, database initialization adds the `profit_yoy` field to an existing
`financial_metrics` table if needed.
