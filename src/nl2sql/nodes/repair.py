import json

from nl2sql.baseline import SYSTEM, extract_sql
from nl2sql.db import schema_text
from nl2sql.llm import Model


def repair_sql(question: str, sql: str, error: str, full_schema: dict, model: Model) -> str:
    # 修复时提供完整 schema，避免选错表后永远看不到遗漏的表。
    content = {
        "question": question,
        "previous_sql": sql,
        "database_error": error,
        "schema": schema_text(full_schema),
        "task": "Fix the SQL error without changing the question meaning.",
    }
    return extract_sql(model.complete(SYSTEM, json.dumps(content, ensure_ascii=False)))
