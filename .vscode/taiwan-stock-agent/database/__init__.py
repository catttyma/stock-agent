"""SQLite 初始化與連線工具。"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DATABASE_PATH = Path(__file__).with_name("stock_agent.db")


@contextmanager
def connect(database_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """建立 SQLite 連線，結束時提交或回滾並關閉連線。"""
    path = Path(database_path or os.environ.get("DATABASE_PATH", DEFAULT_DATABASE_PATH))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(database_path: str | Path | None = None) -> None:
    """建立尚未存在的 Schema 資料表。"""
    with connect(database_path) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def upsert_company(
    connection: sqlite3.Connection,
    stock_code: str,
    name: str,
    market: str,
    industry: str | None = None,
) -> int:
    """新增或更新公司主檔，並回傳資料庫內的公司 ID。"""
    connection.execute(
        """
        INSERT INTO companies (stock_code, name, market, industry)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(stock_code) DO UPDATE SET
            name = excluded.name,
            market = excluded.market,
            industry = excluded.industry,
            updated_at = CURRENT_TIMESTAMP
        """,
        (stock_code, name, market, industry),
    )
    row = connection.execute(
        "SELECT id FROM companies WHERE stock_code = ?", (stock_code,)
    ).fetchone()
    if row is None:
        raise RuntimeError(f"無法取得公司資料庫 ID：{stock_code}")
    return int(row["id"])


__all__ = ["connect", "initialize_database", "upsert_company"]
