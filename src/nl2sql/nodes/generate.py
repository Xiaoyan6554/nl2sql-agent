from nl2sql.baseline import SYSTEM, extract_sql, prompt
from nl2sql.db import schema_text
from nl2sql.llm import Model


def generate_sql(question: str, selected: dict, model: Model, examples: list | None = None) -> str:
    return extract_sql(model.complete(SYSTEM, prompt(question, schema_text(selected), examples)))
