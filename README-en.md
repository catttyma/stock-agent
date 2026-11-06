# Taiwan Stock Fundamental Agent

A command-line tool for collecting Taiwan stock financial statements and news,
calculating fundamental and sentiment scores, and generating Markdown research
reports.

[繁體中文使用手冊](README-zh.md)

## Features

- Fetch quarterly income statements, balance sheets, and cash-flow statements
  from FinMind.
- Fetch recent company or industry news from Google News RSS.
- Calculate profitability, growth, liquidity, debt, and cash-flow metrics.
- Classify news and estimate sentiment and impact with deterministic keyword
  rules.
- Score fundamentals, growth, and news, then generate an optional AI-assisted
  Markdown report.
- Store data in SQLite. No dashboard, technical analysis, or order placement
  is included.

## Requirements and setup

The repository contains the application in `.vscode/taiwan-stock-agent` and
the virtual environment in `.venv`. Run the following commands in PowerShell
from the repository root:

```powershell
$project = Join-Path (Get-Location) ".vscode\taiwan-stock-agent"
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
```

Check that the interpreter exists:

```powershell
Test-Path $python
```

If this prints `False`, create the environment and install dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\.vscode\taiwan-stock-agent\requirements.txt
```

If the virtual environment already exists, install or update dependencies with:

```powershell
& $python -m pip install -r (Join-Path $project "requirements.txt")
```

The SQLite database defaults to
`.vscode/taiwan-stock-agent/database/stock_agent.db`. To use another database,
set `DATABASE_PATH` in the environment before running a command.

## API credentials

Financial data may require a FinMind token. Set `FINMIND_TOKEN` in the current
PowerShell session:

```powershell
$env:FINMIND_TOKEN = "your FinMind token"
```

AI news summaries require an OpenAI API key. You can either set it in the
current session:

```powershell
$env:OPENAI_API_KEY = "your OpenAI API key"
```

Or add `OPENAI_API_KEY=...` to `.env` in the repository root or `.venv/.env`.
The application loads either file when it initializes the OpenAI client; an
environment variable already set in the process takes precedence. Do not
commit `.env` files or share API keys. The default model is `gpt-4o-mini`;
override it with `OPENAI_MODEL` or a command's `--model` option.

## Typical workflow

Run commands from the repository root. Replace the sample stock code or dates
with the company and periods you want to analyze.

### 1. Fetch financial statements

```powershell
& $python (Join-Path $project "main.py") fetch-financials 2330 --start-date 2024-01-01
```

You can use an exact company name instead of a stock code. FinMind resolves the
company and the application stores the three statement datasets as raw JSON.
Repeated fetches update existing company/source/period records.

### 2. Calculate fundamental metrics

```powershell
& $python (Join-Path $project "main.py") analyze-fundamentals 2330
```

Metrics are calculated from the stored quarterly statements and saved to
`financial_metrics`. Growth rates require the relevant comparison quarter.

### 3. Fetch and analyze news

Fetch the latest 30 days of news and associate it with the company:

```powershell
& $python (Join-Path $project "main.py") fetch-news 2330 --stock-code 2330 --days 30
```

Classify the saved articles and calculate sentiment and impact scores:

```powershell
& $python (Join-Path $project "main.py") analyze-news --stock-code 2330
```

Use `--reprocess` to recalculate existing classifications with the current
keyword rules. To search news without associating it with a company, omit
`--stock-code`.

### 4. Calculate scores

```powershell
& $python (Join-Path $project "main.py") score 2330 --news-days 30
```

The scores are saved in `analysis_reports`. The overall score is left
unavailable until fundamental, growth, and news scores are all available; the
command reports missing components rather than treating missing data as zero.

### 5. Generate a Markdown report

Set `OPENAI_API_KEY` as described above, then run:

```powershell
& $python (Join-Path $project "main.py") generate-report 2330 --news-days 30
```

This command recalculates metrics, analyzes new articles, summarizes recent
company news that has no summary, calculates scores, stores the Markdown in
SQLite, and writes a UTF-8 file under
`.vscode/taiwan-stock-agent/reports/`.

Optional arguments:

- `--model MODEL`: use a different OpenAI model.
- `--output-dir PATH`: write the report to another directory.
- `--resummarize`: replace existing AI summaries in the selected news period.

To summarize news without generating a full report:

```powershell
& $python (Join-Path $project "main.py") summarize-news --stock-code 2330 --days 30
```

OpenAI is only called when there are recent company articles that need
summaries. If there are no eligible articles, no OpenAI request is made.

## Scoring and data notes

- The overall score weights fundamentals at 60%, growth at 20%, and news at
  20%. Grades are A (90–100), B (80–<90), C (70–<80), D (60–<70), and E (<60).
- Financial ratios and growth rates are stored as percentage points; for
  example, `25.0` means 25%.
- News category, sentiment, and impact are estimated with keyword rules, not
  AI. AI is used for article summaries only.
- An unavailable metric is not assumed to be zero. Incomplete data can prevent
  an overall score from being produced.
- Summaries depend on the fetched article text and do not verify its accuracy.
  Scores and reports are research aids, not investment advice.
- API calls require network access. The test suite uses mocked data and does
  not need API credentials.

## Tests

From the repository root, switch to the application directory before running
the tests so the application modules can be imported:

```powershell
Set-Location $project
& $python -m unittest discover -s tests -v
```

## Other commands

```powershell
& $python (Join-Path $project "main.py") --help
& $python (Join-Path $project "main.py") generate-report --help
```
