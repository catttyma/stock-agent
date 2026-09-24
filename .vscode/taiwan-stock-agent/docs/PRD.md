
Taiwan Stock Fundamental Agent PRD
1. 專案名稱
Taiwan Stock Fundamental Agent（台股基本面分析 Agent）


2. 專案願景
建立一套能自動蒐集、整理、分析台股公司基本面與消息面的 AI Agent。
使用者只需輸入股票代號或公司名稱，系統即可：

- 自動取得財報資料
- 自動取得相關新聞
- 分析公司基本面
- 分析消息面與總體經濟
- 給出綜合評分
- 產生投資研究報告


3. 目標使用者
初期使用者

- 自己
- 台股投資人
- 基本面投資愛好者
未來使用者

- 研究員
- 投資顧問
- 財經部落客
- 中小型投資團隊


4. MVP 目標（第一版）
要完成
✅ 財報資料抓取
✅ 新聞資料抓取
✅ 基本面分析
✅ 新聞摘要
✅ 評分系統
✅ Markdown 報告輸出
暫不實作
❌ 即時報價
❌ 自動下單
❌ 技術分析
❌ 網頁 Dashboard
❌ 多 Agent 架構


5. 資料來源規劃
財報資料
優先順序：

1. FinMind API
2. 公開資訊觀測站（MOPS）
3. 台灣證券交易所（TWSE）
4. 櫃買中心（TPEX）
消息面資料

1. Google News
2. Yahoo 股市
3. 鉅亨網
4. 中央社財經
5. Fed 官方網站
6. 台灣央行官方網站


6. 基本面分析模組
獲利能力

- EPS
- ROE
- ROA
- 毛利率
- 營業利益率
- 淨利率
成長能力

- 營收年增率
- 營收季增率
- EPS 年增率
- EPS 季增率
財務體質

- 負債比
- 流動比率
- 速動比率
現金流分析

- 營業現金流
- 自由現金流
- 投資現金流
- 融資現金流


7. 消息面分析模組
總體經濟

- 美國聯準會（Fed）

- 美國 CPI
- 美國 GDP
- 美國非農就業
- 台灣央行升降息
- PMI
公司消息

- 法說會
- 財測調整
- 重大訊息
- 併購
- 增資減資
產業消息

- AI
- 半導體
- 金融
- 航運
- 面板


8. 新聞分析邏輯
新聞分類

- 利率政策
- 總體經濟
- 公司新聞
- 法說會
- 產業消息
情緒判斷

- 利多
- 中性
- 利空
影響分數
範圍：
-100 ~ +100
範例：

- Fed 降息 +20
- Fed 升息 -20
- 上修財測 +15
- 重大資安事件 -15


9. 評分系統
基本面 60%
評估指標：

- EPS
- ROE
- ROA
- 毛利率
- 負債比
成長性 20%
評估指標：

- 營收成長
- EPS 成長
- 獲利成長
消息面 20%
評估指標：

- 新聞情緒

- 利率環境
- 產業趨勢
評級制度

- A：90~100
- B：80~89
- C：70~79
- D：60~69
- E：60 以下


10. 使用流程
輸入：

2330


系統流程：

1. 抓取財報資料
2. 分析基本面
3. 抓取最近 30 天新聞
4. AI 摘要新聞
5. 計算評分
6. 輸出分析報告


11. 預期輸出

股票：2330 台積電

ROE：28%
EPS：45.2
負債比：21%

近期重要新聞：
- Fed 利率決議
- AI 需求成長
- 法說會內容

基本面評級：A
消息面評級：B
綜合評分：89

投資觀察：
值得持續追蹤




12. 技術架構
程式語言

- Python 3.13
套件

- Pandas
- Numpy
- Requests
- BeautifulSoup4
- SQLAlchemy
- OpenAI SDK
- FinMind
資料庫

- SQLite
版本控制

- Git
- GitHub


13. 專案結構

taiwan-stock-agent/
│
├── docs/
│   ├── PRD.md
│   ├── Architecture.md
│   └── Roadmap.md
│
├── agent/
├── fetchers/
│   ├── financial/
│   └── news/
│
├── analyzers/
├── scoring/
├── database/
├── reports/
├── tests/
│
├── main.py
├── requirements.txt
└── README.md




14. 已完成前置準備

- 已安裝 Python
- 已建立 .venv
- 已安裝 Git
- 已完成 git init
- 已理解 Git、Branch、PR 基本概念


15. 開發 Roadmap
Phase 1

- 建立 GitHub Repository
- 建立專案架構
- 建立 SQLite Schema
Phase 2

- 完成財報抓取模組
- 完成新聞抓取模組
Phase 3

- 完成基本面分析
- 完成新聞分析
- 完成評分系統
Phase 4

- 串接 OpenAI
- 產生 AI 摘要
- 產出 Markdown 報告


16. 長期規劃
V2：技術面分析
V3：Web Dashboard
V4：Line Bot
V5：Telegram Bot
V6：多 Agent 協作V7：RAG 與向量資料庫
V8：台股 + 美股整合分析平台