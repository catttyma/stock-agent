# 台股基本面分析 Agent

這是一套命令列工具，可蒐集台股財報與新聞、計算基本面和消息面評分，並產生 Markdown 研究報告。

[English user guide](README-en.md)

## 功能

- 透過 FinMind 抓取季度損益表、資產負債表與現金流量表。
- 透過 Google News RSS 抓取公司或產業近期新聞。
- 計算獲利、成長、流動性、負債與現金流指標。
- 使用固定關鍵字規則分類新聞、判斷情緒並估算影響分數。
- 評估基本面、成長性與消息面，並可產生 AI 新聞摘要及 Markdown 報告。
- 使用 SQLite 儲存資料；目前不包含 Dashboard、技術分析或自動下單。

## 環境需求與設定

程式位於 `.vscode/taiwan-stock-agent`，虛擬環境位於 `.venv`。請在
PowerShell 的 Git 專案根目錄執行：

```powershell
$project = Join-Path (Get-Location) ".vscode\taiwan-stock-agent"
$python = Join-Path (Get-Location) ".venv\Scripts\python.exe"
```

確認 Python 執行檔存在：

```powershell
Test-Path $python
```

如果結果是 `False`，請建立虛擬環境並安裝套件：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\.vscode\taiwan-stock-agent\requirements.txt
```

如果虛擬環境已存在，可用以下命令安裝或更新套件：

```powershell
& $python -m pip install -r (Join-Path $project "requirements.txt")
```

SQLite 預設資料庫位置是
`.vscode/taiwan-stock-agent/database/stock_agent.db`。若要改用其他資料庫，
請在執行命令前設定環境變數 `DATABASE_PATH`。

## API 金鑰設定

抓取財報時，FinMind 可能要求 Token。可在目前的 PowerShell 視窗設定：

```powershell
$env:FINMIND_TOKEN = "你的 FinMind Token"
```

AI 新聞摘要需要 OpenAI API Key。可以在目前的 PowerShell 視窗設定：

```powershell
$env:OPENAI_API_KEY = "你的 OpenAI API Key"
```

也可以在 Git 專案根目錄的 `.env`，或 `.venv/.env` 中加入
`OPENAI_API_KEY=...`。程式初始化 OpenAI 用戶端時會載入這些檔案；若目前程序
已設定同名環境變數，則優先使用環境變數。請勿將 `.env` 提交至 Git，也不要
分享 API Key。預設模型為 `gpt-4o-mini`，可用 `OPENAI_MODEL` 或命令的
`--model` 參數更改。

## 一般使用流程

以下命令都在 Git 專案根目錄執行。請依需求替換股票代號及日期。

### 1. 抓取財報

```powershell
& $python (Join-Path $project "main.py") fetch-financials 2330 --start-date 2024-01-01
```

除了股票代號，也可輸入完全相符的公司名稱。程式會透過 FinMind 查找公司，
並將三種財報以原始 JSON 儲存。重複抓取會更新相同公司、來源和期間的資料。

### 2. 計算基本面指標

```powershell
& $python (Join-Path $project "main.py") analyze-fundamentals 2330
```

程式會分析已儲存的季度財報，將指標寫入 `financial_metrics`。成長率需要對應
的比較季度資料才能計算。

### 3. 抓取與分析新聞

抓取最近 30 天新聞並關聯到公司：

```powershell
& $python (Join-Path $project "main.py") fetch-news 2330 --stock-code 2330 --days 30
```

分類已儲存的新聞，並計算情緒與影響分數：

```powershell
& $python (Join-Path $project "main.py") analyze-news --stock-code 2330
```

使用 `--reprocess` 可依目前的關鍵字規則重新分析舊新聞。若只要搜尋新聞而不
關聯公司，可省略 `--stock-code`。

### 4. 計算評分

```powershell
& $python (Join-Path $project "main.py") score 2330 --news-days 30
```

評分會儲存至 `analysis_reports`。基本面、成長性與消息面三項分數都可用時，
才會計算綜合分數；缺少資料會明確列出，不會直接當成 0 分。

### 5. 產生 Markdown 報告

依前述方式設定 `OPENAI_API_KEY` 後，執行：

```powershell
& $python (Join-Path $project "main.py") generate-report 2330 --news-days 30
```

此命令會重新計算基本面指標、分析新新聞、摘要尚未摘要的近期公司新聞、計算
評分，將 Markdown 儲存至 SQLite，並輸出 UTF-8 報告至
`.vscode/taiwan-stock-agent/reports/`。

可選參數：

- `--model MODEL`：指定 OpenAI 模型。
- `--output-dir PATH`：指定報告輸出目錄。
- `--resummarize`：重新產生選定新聞期間內既有的 AI 摘要。

若只需要摘要新聞、不需要完整報告：

```powershell
& $python (Join-Path $project "main.py") summarize-news --stock-code 2330 --days 30
```

只有存在符合期間且尚無摘要的公司新聞時，程式才會呼叫 OpenAI；沒有符合條件
的新聞時不會送出 API 請求。

## 評分及資料注意事項

- 綜合評分權重為基本面 60%、成長性 20%、消息面 20%。評級為 A（90–100）、
  B（80–未滿 90）、C（70–未滿 80）、D（60–未滿 70）、E（未滿 60）。
- 財務比率及成長率以百分點儲存，例如 `25.0` 代表 25%。
- 新聞分類、情緒與影響分數由關鍵字規則估算，不是 AI 分析；AI 僅用於新聞摘要。
- 無法取得的指標不會假設為 0；資料不完整時可能無法計算綜合分數。
- AI 摘要依據抓取到的文章文字，並不代表已查證新聞真偽。評分與報告僅供研究
  參考，不構成投資建議。
- 實際抓取資料需要網路連線；測試套件使用模擬資料，不需要 API 金鑰。

## 執行測試

在 Git 專案根目錄先切換到程式目錄，再執行測試，確保測試能匯入應用程式模組：

```powershell
Set-Location $project
& $python -m unittest discover -s tests -v
```

## 查看命令說明

```powershell
& $python (Join-Path $project "main.py") --help
& $python (Join-Path $project "main.py") generate-report --help
```
