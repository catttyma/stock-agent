# Taiwan Stock Fundamental Agent

Phase 2 provides FinMind financial-statement fetching and Google News RSS
fetching, with results stored in the SQLite schema in `database/schema.sql`.

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
