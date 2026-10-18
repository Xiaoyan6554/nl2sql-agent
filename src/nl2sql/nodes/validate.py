from pathlib import Path

from nl2sql.db import execute
from nl2sql.safety import validate_sql


def check_sql(sql: str, path: Path, timeout: float, row_limit: int | None = None) -> str:
    normalized = validate_sql(sql, row_limit)
    # SQLite 编译器正确处理 CTE、别名和相关子查询，同时验证表名和字段名。
    execute(path, normalized, timeout=timeout, explain=True)
    return normalized
