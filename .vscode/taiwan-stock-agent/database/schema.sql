-- 啟用外鍵約束，確保公司、財報、新聞與報告之間的關聯資料一致。
PRAGMA foreign_keys = ON;

-- 公司主檔：保存股票代號、公司名稱、上市櫃市場與產業分類。
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    stock_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    market TEXT NOT NULL CHECK (market IN ('TWSE', 'TPEx', 'OTHER')),
    industry TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 原始財報：保存從外部資料來源取得的損益表、資產負債表與現金流量表。
-- raw_data 以 JSON 文字保存原始回應，避免抓取時遺失來源欄位。
CREATE TABLE IF NOT EXISTS financial_statements (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    statement_type TEXT NOT NULL CHECK (
        statement_type IN (
            'income_statement',
            'balance_sheet',
            'cash_flow_statement'
        )
    ),
    period_type TEXT NOT NULL CHECK (period_type IN ('quarterly', 'annual')),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER CHECK (fiscal_quarter BETWEEN 1 AND 4),
    period_end_date TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data TEXT NOT NULL,
    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
    UNIQUE (
        company_id,
        statement_type,
        period_type,
        fiscal_year,
        fiscal_quarter,
        period_end_date,
        source
    ),
    CHECK (
        (period_type = 'quarterly' AND fiscal_quarter IS NOT NULL)
        OR (period_type = 'annual' AND fiscal_quarter IS NULL)
    )
);

-- 財務指標：保存由原始財報計算出的 EPS、獲利率、成長率、財務比率與現金流指標。
CREATE TABLE IF NOT EXISTS financial_metrics (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    financial_statement_id INTEGER,
    period_type TEXT NOT NULL CHECK (period_type IN ('quarterly', 'annual')),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter INTEGER CHECK (fiscal_quarter BETWEEN 1 AND 4),
    period_end_date TEXT NOT NULL,
    eps REAL,
    roe REAL,
    roa REAL,
    gross_margin REAL,
    operating_margin REAL,
    net_margin REAL,
    revenue_yoy REAL,
    revenue_qoq REAL,
    eps_yoy REAL,
    eps_qoq REAL,
    debt_ratio REAL,
    current_ratio REAL,
    quick_ratio REAL,
    operating_cash_flow REAL,
    free_cash_flow REAL,
    investing_cash_flow REAL,
    financing_cash_flow REAL,
    calculated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE,
    FOREIGN KEY (financial_statement_id)
        REFERENCES financial_statements (id) ON DELETE SET NULL,
    UNIQUE (company_id, period_type, fiscal_year, fiscal_quarter, period_end_date),
    CHECK (
        (period_type = 'quarterly' AND fiscal_quarter IS NOT NULL)
        OR (period_type = 'annual' AND fiscal_quarter IS NULL)
    )
);

-- 新聞文章：保存新聞來源、標題、網址、摘要、內容與發布時間。
CREATE TABLE IF NOT EXISTS news_articles (
    id INTEGER PRIMARY KEY,
    company_id INTEGER,
    source TEXT NOT NULL,
    source_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE SET NULL
);

-- 新聞分析：保存 AI 或規則分析後的新聞分類、情緒、影響分數與摘要。
CREATE TABLE IF NOT EXISTS news_analysis (
    id INTEGER PRIMARY KEY,
    news_article_id INTEGER NOT NULL UNIQUE,
    category TEXT NOT NULL CHECK (
        category IN (
            'interest_rate_policy',
            'macroeconomics',
            'company',
            'earnings_conference',
            'industry'
        )
    ),
    sentiment TEXT NOT NULL CHECK (sentiment IN ('positive', 'neutral', 'negative')),
    impact_score REAL NOT NULL CHECK (impact_score BETWEEN -100 AND 100),
    ai_summary TEXT,
    analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (news_article_id) REFERENCES news_articles (id) ON DELETE CASCADE
);

-- 總體經濟指標：保存 Fed、CPI、GDP、PMI 等跨公司共用的經濟資料。
CREATE TABLE IF NOT EXISTS macro_indicators (
    id INTEGER PRIMARY KEY,
    indicator_type TEXT NOT NULL,
    region TEXT NOT NULL,
    value REAL,
    unit TEXT,
    period_date TEXT NOT NULL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_data TEXT,
    UNIQUE (indicator_type, region, period_date, source)
);

-- 分析報告：保存一次完整分析的各面向分數、等級、投資觀察與 Markdown 內容。
CREATE TABLE IF NOT EXISTS analysis_reports (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL,
    requested_input TEXT NOT NULL,
    analysis_start_date TEXT,
    analysis_end_date TEXT,
    fundamental_score REAL CHECK (fundamental_score BETWEEN 0 AND 100),
    growth_score REAL CHECK (growth_score BETWEEN 0 AND 100),
    news_score REAL CHECK (news_score BETWEEN 0 AND 100),
    overall_score REAL CHECK (overall_score BETWEEN 0 AND 100),
    fundamental_grade TEXT CHECK (fundamental_grade IN ('A', 'B', 'C', 'D', 'E')),
    growth_grade TEXT CHECK (growth_grade IN ('A', 'B', 'C', 'D', 'E')),
    news_grade TEXT CHECK (news_grade IN ('A', 'B', 'C', 'D', 'E')),
    overall_grade TEXT CHECK (overall_grade IN ('A', 'B', 'C', 'D', 'E')),
    investment_observation TEXT,
    markdown_content TEXT,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE
);

-- 以下索引可加速依公司、期間、新聞發布時間與評分結果查詢資料。
CREATE INDEX IF NOT EXISTS idx_financial_statements_company_period
    ON financial_statements (company_id, period_end_date);

CREATE INDEX IF NOT EXISTS idx_financial_metrics_company_period
    ON financial_metrics (company_id, period_end_date);

CREATE INDEX IF NOT EXISTS idx_news_articles_company_published
    ON news_articles (company_id, published_at);

CREATE INDEX IF NOT EXISTS idx_news_analysis_sentiment
    ON news_analysis (sentiment);

CREATE INDEX IF NOT EXISTS idx_macro_indicators_type_period
    ON macro_indicators (indicator_type, period_date);

CREATE INDEX IF NOT EXISTS idx_analysis_reports_company_generated
    ON analysis_reports (company_id, generated_at);
