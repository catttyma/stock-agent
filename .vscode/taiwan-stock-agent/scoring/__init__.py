"""依 PRD 權重計算基本面、成長、消息與綜合分數。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping

# 基本面總分由 EPS、ROE、ROA、毛利率、負債比各占 20% 組成。
# 權重表示「指標在基本面分數中的比重」，不是整體總分比重。
FUNDAMENTAL_WEIGHTS = {
    "eps": 0.20,
    "roe": 0.20,
    "roa": 0.20,
    "gross_margin": 0.20,
    "debt_ratio": 0.20,
}
# 成長分數的內部權重；獲利成長以淨利年增率表示。
GROWTH_WEIGHTS = {
    "revenue_yoy": 0.35,
    "revenue_qoq": 0.15,
    "eps_yoy": 0.30,
    "eps_qoq": 0.10,
    "profit_yoy": 0.10,
}
# 最終分數採 PRD 權重：基本面 60%、成長 20%、消息面 20%。
OVERALL_WEIGHTS = {"fundamental": 0.60, "growth": 0.20, "news": 0.20}


@dataclass(frozen=True)
class ScoreResult:
    """一次評分的結果；分數以 0 到 100 表示，資料不足時為 None。"""

    fundamental_score: float | None
    growth_score: float | None
    news_score: float | None
    overall_score: float | None
    fundamental_grade: str | None
    growth_grade: str | None
    news_grade: str | None
    overall_grade: str | None
    article_count: int
    missing_components: tuple[str, ...]
    analysis_report_id: int


def grade_for_score(score: float | None) -> str | None:
    """依 PRD 的分數區間轉換等級；None 代表目前不能評級。"""
    if score is None:
        return None
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "E"


def score_fundamentals(metrics: Mapping[str, Any]) -> float | None:
    """把五項財務指標轉成 0–100 分，再依基本面權重加權平均。

    個別指標會先經過各自的評分曲線；缺少的指標不會當作 0 分，
    而是在加權平均時排除並重新正規化剩餘權重。
    """
    values = {
        # EPS 使用簡單分段規則：虧損或損益兩平為 0 分，
        # 正 EPS 未達 10 為 80 分，EPS 達 10 為 100 分。
        "eps": _score_eps(metrics.get("eps")),
        # ROE 門檻依序為 (比率%, 分數)，門檻之間採線性插值。
        "roe": _score_thresholds(
            metrics.get("roe"),
            ((0, 0), (5, 40), (10, 60), (15, 80), (20, 90), (25, 100)),
        ),
        # ROA、毛利率也使用線性門檻；超過最高門檻維持 100 分。
        "roa": _score_thresholds(
            metrics.get("roa"), ((0, 0), (2, 40), (5, 70), (8, 85), (10, 100))
        ),
        "gross_margin": _score_thresholds(
            metrics.get("gross_margin"),
            ((0, 0), (10, 40), (20, 65), (30, 85), (40, 100)),
        ),
        # 負債比越高分數越低；超過 100% 視為 0 分。
        "debt_ratio": _score_debt_ratio(metrics.get("debt_ratio")),
    }
    return _weighted_average(values, FUNDAMENTAL_WEIGHTS)


def score_growth(metrics: Mapping[str, Any]) -> float | None:
    """計算營收、EPS 與淨利成長分數。

    各成長率先以 clamp(50 + 成長率百分點 * 2.5, 0, 100) 轉分，
    再依 GROWTH_WEIGHTS 加權；例如年增率 20% 對應 100 分。
    負成長會低於 50 分，且所有結果限制在 0 到 100。
    """
    values = {field: _score_growth_rate(metrics.get(field)) for field in GROWTH_WEIGHTS}
    return _weighted_average(values, GROWTH_WEIGHTS)


def score_news(impact_scores: list[float]) -> float | None:
    """把新聞影響分數平均後映射到 0–100；影響分數範圍為 -100 到 +100。

    公式：clamp(50 + 平均影響分數 / 2, 0, 100)。
    因此中性 (0) 為 50 分，平均 +20 為 60 分，平均 -20 為 40 分。
    沒有任何已分析新聞時回傳 None，避免把「無資料」誤當中性。
    """
    if not impact_scores:
        return None
    return _clamp(50 + sum(impact_scores) / len(impact_scores) / 2)


def evaluate_company(
    connection: sqlite3.Connection,
    company_id: int,
    requested_input: str,
    news_days: int = 30,
    today: date | None = None,
) -> ScoreResult:
    """計算並保存最新分項分數與綜合評分。

    基本面與成長分數使用最新一筆 financial_metrics；消息面只採用
    已完成 news_analysis、已關聯此公司的新聞，並依發布日期篩選
    最近 news_days 天。評分結果和缺少資料的說明會新增至
    analysis_reports；這裡只計分，不產生 Phase 4 Markdown 報告。
    """
    if news_days < 1:
        raise ValueError("news_days 必須大於 0")
    current_date = today or date.today()
    # 回溯區間起日；SQL 以此作為發布日期下限，會納入等於起日的新聞。
    start_date = current_date - timedelta(days=news_days)

    # 使用資料庫中期間最新的已計算指標，避免在評分時重複解析原始財報。
    metrics_row = connection.execute(
        """
        SELECT * FROM financial_metrics
        WHERE company_id = ?
        ORDER BY period_end_date DESC, id DESC
        LIMIT 1
        """,
        (company_id,),
    ).fetchone()
    metrics = dict(metrics_row) if metrics_row is not None else {}
    fundamental_score = score_fundamentals(metrics) if metrics else None
    growth_score = score_growth(metrics) if metrics else None

    # 僅計算發布日期不早於起日、且「已分析」的新聞；尚未分析的新聞不納入。
    news_rows = connection.execute(
        """
        SELECT analysis.impact_score
        FROM news_analysis AS analysis
        JOIN news_articles AS article ON article.id = analysis.news_article_id
        WHERE article.company_id = ?
          AND article.published_at IS NOT NULL
          AND julianday(article.published_at) >= julianday(?)
          AND julianday(article.published_at) < julianday(?)
        ORDER BY article.published_at DESC
        """,
        (
            company_id,
            start_date.isoformat(),
            (current_date + timedelta(days=1)).isoformat(),
        ),
    ).fetchall()
    impact_scores = [float(row["impact_score"]) for row in news_rows]
    news_score = score_news(impact_scores)

    component_scores = {
        "fundamental": fundamental_score,
        "growth": growth_score,
        "news": news_score,
    }
    # 明確記錄缺少哪些組成分數。即使有部分分數，也不將其放大重算，
    # 因為 PRD 定義的整體權重必須固定為 60% / 20% / 20%。
    missing = tuple(name for name, value in component_scores.items() if value is None)
    overall_score = (
        sum(
            component_scores[name] * weight
            for name, weight in OVERALL_WEIGHTS.items()
            if component_scores[name] is not None
        )
        if not missing
        else None
    )
    grades = {
        "fundamental": grade_for_score(fundamental_score),
        "growth": grade_for_score(growth_score),
        "news": grade_for_score(news_score),
        "overall": grade_for_score(overall_score),
    }
    # 綜合分數只有三個面向齊全時才計算；沒有資料時直接說明缺項。
    if overall_score is None:
        observation = "資料不足，尚未計算綜合分數；缺少：" + "、".join(missing)
    else:
        observation = (
            f"綜合評分 {overall_score:.1f}（{grades['overall']}）；"
            "此評分為規則式研究參考，不構成投資建議。"
        )

    # 每次評分都保留一筆歷史報告記錄，方便日後追蹤分數變化。
    cursor = connection.execute(
        """
        INSERT INTO analysis_reports (
            company_id, requested_input, analysis_start_date, analysis_end_date,
            fundamental_score, growth_score, news_score, overall_score,
            fundamental_grade, growth_grade, news_grade, overall_grade,
            investment_observation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            requested_input,
            start_date.isoformat(),
            current_date.isoformat(),
            fundamental_score,
            growth_score,
            news_score,
            overall_score,
            grades["fundamental"],
            grades["growth"],
            grades["news"],
            grades["overall"],
            observation,
        ),
    )
    return ScoreResult(
        fundamental_score=fundamental_score,
        growth_score=growth_score,
        news_score=news_score,
        overall_score=overall_score,
        fundamental_grade=grades["fundamental"],
        growth_grade=grades["growth"],
        news_grade=grades["news"],
        overall_grade=grades["overall"],
        article_count=len(impact_scores),
        missing_components=missing,
        analysis_report_id=int(cursor.lastrowid),
    )


def _score_eps(value: Any) -> float | None:
    """EPS 的 MVP 分段曲線：<= 0 為 0、(0, 10) 為 80、>= 10 為 100。"""
    numeric = _number(value)
    if numeric is None:
        return None
    if numeric <= 0:
        return 0
    return 100 if numeric >= 10 else 80


def _score_thresholds(
    value: Any, thresholds: tuple[tuple[float, float], ...]
) -> float | None:
    """依照 (指標門檻, 分數) 序列做分段線性換算。

    例如 ROE 7.5% 位於 (5%, 40 分) 與 (10%, 60 分) 中間，
    所得分數為 50 分。低於第一門檻採第一分數，高於最後門檻採最後分數。
    """
    numeric = _number(value)
    if numeric is None:
        return None
    if numeric <= thresholds[0][0]:
        return thresholds[0][1]
    for (lower_value, lower_score), (upper_value, upper_score) in zip(
        thresholds, thresholds[1:]
    ):
        if numeric <= upper_value:
            # 計算數值在兩個門檻間的比例，再對分數做相同比例插值。
            ratio = (numeric - lower_value) / (upper_value - lower_value)
            return lower_score + ratio * (upper_score - lower_score)
    return thresholds[-1][1]


def _score_debt_ratio(value: Any) -> float | None:
    """負債比專用曲線：低負債得高分；負值或缺值代表資料不適用。"""
    numeric = _number(value)
    if numeric is None or numeric < 0:
        return None
    thresholds = ((0, 100), (20, 95), (40, 80), (60, 60), (80, 35), (100, 10))
    return _score_thresholds(numeric, thresholds) if numeric <= 100 else 0


def _score_growth_rate(value: Any) -> float | None:
    """將成長率百分點映射到分數；每成長 1 個百分點加 2.5 分。"""
    numeric = _number(value)
    return _clamp(50 + numeric * 2.5) if numeric is not None else None


def _weighted_average(
    values: Mapping[str, float | None], weights: Mapping[str, float]
) -> float | None:
    """只對有數值的指標做加權平均，並以可用權重總和重新正規化。

    例如兩項權重 0.2、0.3 有值時，分數為
    (分數1 * 0.2 + 分數2 * 0.3) / (0.2 + 0.3)。
    全部都缺值時回傳 None，而非 0 分。
    """
    available = [
        (values[name], weight)
        for name, weight in weights.items()
        if values.get(name) is not None
    ]
    if not available:
        return None
    total_weight = sum(weight for _, weight in available)
    return sum(value * weight for value, weight in available) / total_weight


def _number(value: Any) -> float | None:
    """安全轉換數值，排除 None、非數值、NaN 與正負無限大。"""
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric and abs(numeric) != float("inf") else None


def _clamp(value: float) -> float:
    """將分數限制在 0 到 100 的有效範圍。"""
    return max(0.0, min(100.0, value))


__all__ = [
    "ScoreResult",
    "evaluate_company",
    "grade_for_score",
    "score_fundamentals",
    "score_growth",
    "score_news",
]
