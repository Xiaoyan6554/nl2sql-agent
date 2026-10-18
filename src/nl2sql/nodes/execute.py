from pathlib import Path

from nl2sql.db import execute


def execute_sql(sql: str, path: Path, timeout: float, max_rows: int) -> dict:
    return execute(path, sql, timeout=timeout, max_rows=max_rows)
