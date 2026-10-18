"""只读 SQLite、对象白名单、执行时限和完整结果上限。"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from time import monotonic

from nl2sql.safety import SAFE_FUNCTIONS, validate_sql


class QueryError(RuntimeError):
    pass


def database_path(root: Path, db_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_]+", db_id):
        raise ValueError("非法 db_id")
    path = (root / "database" / db_id / f"{db_id}.sqlite").resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError(f"数据库不存在：{db_id}")
    return path


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def connect(path: Path, timeout: float = 5) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=timeout)
    # surrogateescape 保留非法 UTF-8 字节差异，避免替换字符造成假相等。
    conn.text_factory = lambda value: value.decode("utf-8", errors="surrogateescape")
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("PRAGMA trusted_schema=OFF")
        conn.enable_load_extension(False)
        conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 20000)
        conn.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
        conn.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20)
        yield conn
    finally:
        conn.close()


def schema(path: Path) -> dict:
    with connect(path) as conn:
        names = [
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")
            if not r[0].lower().startswith("sqlite_")
        ]
        result = {}
        for name in names:
            columns = conn.execute(f"PRAGMA table_info({quote(name)})").fetchall()
            keys = conn.execute(f"PRAGMA foreign_key_list({quote(name)})").fetchall()
            result[name] = {
                "columns": {r[1]: r[2] or "TEXT" for r in columns},
                "primary_keys": [r[1] for r in columns if r[5]],
                "foreign_keys": [{"column": r[3], "table": r[2], "target": r[4]} for r in keys],
            }
        return result


def schema_text(tables: dict) -> str:
    lines = []
    for name, info in tables.items():
        cols = ", ".join(f"{quote(col)} {kind}" for col, kind in info["columns"].items())
        lines.append(f"TABLE {quote(name)} ({cols}); PK={info['primary_keys']}")
        for fk in info["foreign_keys"]:
            lines.append(
                f"FK {quote(name)}.{quote(fk['column'])} -> "
                f"{quote(fk['table'])}.{quote(fk['target'] or '<primary key>')}"
            )
    return "\n".join(lines)


def guard(conn: sqlite3.Connection, tables: dict, timeout: float) -> None:
    allowed = {t.lower() for t in tables}

    def authorize(
        action: int, arg1: str | None, arg2: str | None, db_name: str | None, source: str | None
    ) -> int:
        if action == sqlite3.SQLITE_SELECT:
            return sqlite3.SQLITE_OK
        if (
            action == sqlite3.SQLITE_READ
            and (arg1 or "").lower() in allowed
            and db_name in ("main", None)
        ):
            return sqlite3.SQLITE_OK
        if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in SAFE_FUNCTIONS:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    deadline = monotonic() + timeout
    conn.set_authorizer(authorize)
    conn.set_progress_handler(lambda: int(monotonic() > deadline), 1000)


def execute(
    path: Path, sql: str, *, timeout: float = 5, max_rows: int = 100000, explain: bool = False
) -> dict:
    sql = validate_sql(sql)
    tables = schema(path)
    try:
        with connect(path, timeout) as conn:
            guard(conn, tables, timeout)
            cursor = conn.execute(("EXPLAIN QUERY PLAN " if explain else "") + sql)
            rows = []
            size = 0
            while batch := cursor.fetchmany(256):
                rows.extend(batch)
                size += sum(sum(len(str(value)) for value in row) for row in batch)
                if len(rows) > max_rows or size > 8_000_000:
                    raise QueryError("结果超过资源上限；未使用截断结果进行评测")
            return {"columns": [item[0] for item in cursor.description or []], "rows": rows}
    except sqlite3.Error as exc:
        raise QueryError(str(exc)) from None
