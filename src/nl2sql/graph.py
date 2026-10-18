"""StateGraph 的条件边实现有界修复，不重试合法空结果。"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from nl2sql.db import schema
from nl2sql.llm import Model, ModelError
from nl2sql.nodes.execute import execute_sql
from nl2sql.nodes.generate import generate_sql
from nl2sql.nodes.repair import repair_sql
from nl2sql.nodes.schema_link import choose_schema
from nl2sql.nodes.validate import check_sql
from nl2sql.safety import validate_sql


class State(TypedDict, total=False):
    question: str
    selected: dict
    sql: str
    rows: list
    columns: list
    error: str | None
    fatal: bool
    repairs: int
    trace: list[dict]
    examples: list[dict]


def run_graph(question: str, path: Path, model: Model, *, mode: str = 'v2_repair',
              spider_dir: Path | None = None, timeout: float = 5, max_rows: int = 100000,
              row_limit: int | None = None) -> dict:
    if mode not in {'v1_schema_link', 'v2_repair', 'v3_retrieval'}:
        raise ValueError('未知图模式')
    start = perf_counter()
    full_schema = schema(path)
    repair_enabled = mode != 'v1_schema_link'

    def wrap(name, function):
        def node(state: State) -> dict:
            began = perf_counter()
            detail = {}
            try:
                update, detail = function(state)
            except (ValueError, RuntimeError) as exc:
                update = {'error': f'{type(exc).__name__}: {exc}',
                          'fatal': isinstance(exc, ModelError)}
            event = {'node': name, 'latency_seconds': perf_counter() - began, **detail}
            if 'sql' in update:
                event['sql'] = update['sql']
            if update.get('error'):
                event['error'] = update['error']
            update['trace'] = state.get('trace', []) + [event]
            return update
        return node

    def link_node(state):
        selected, fallback = choose_schema(state['question'], full_schema, model)
        return {'selected': selected, 'error': None}, {'tables': list(selected), 'fallback': fallback}

    def retrieve_node(state):
        from nl2sql.retrieval import get_retriever
        if spider_dir is None:
            raise ValueError('检索模式必须提供 Spider 目录')
        examples = get_retriever(spider_dir).search(state['question'], 3)
        return {'examples': examples}, {'example_ids': [e['id'] for e in examples],
                                        'example_db_ids': [e['db_id'] for e in examples]}

    def generate_node(state):
        sql = generate_sql(state['question'], state['selected'], model, state.get('examples'))
        return {'sql': sql, 'error': None}, {}

    def validate_node(state):
        sql = check_sql(state['sql'], path, timeout, row_limit)
        return {'sql': sql, 'error': None}, {}

    def execute_node(state):
        sql = validate_sql(state['sql'], row_limit)
        result = execute_sql(sql, path, timeout, max_rows)
        return {**result, 'sql': sql, 'error': None}, {'row_count': len(result['rows'])}

    def repair_node(state):
        sql = repair_sql(state['question'], state['sql'], state['error'], full_schema, model)
        return {'sql': sql, 'repairs': state['repairs'] + 1, 'error': None}, {}

    def after_error(state):
        if state.get('fatal'):
            return 'answer'
        if state.get('error'):
            return 'repair' if repair_enabled and state['repairs'] < 2 else 'answer'
        return 'execute'

    builder = StateGraph(State)
    for name, function in [('schema_link', link_node), ('generate', generate_node),
                           ('validate', validate_node), ('execute', execute_node),
                           ('repair', repair_node), ('retrieve', retrieve_node),
                           ('answer', lambda state: ({}, {'ok': state.get('error') is None}))]:
        builder.add_node(name, wrap(name, function))
    builder.add_edge(START, 'schema_link')
    builder.add_conditional_edges('schema_link', lambda s: 'answer' if s.get('error') else
                                  ('retrieve' if mode == 'v3_retrieval' else 'generate'))
    builder.add_conditional_edges('retrieve', lambda s: 'answer' if s.get('error') else 'generate')
    builder.add_conditional_edges('generate', lambda s: 'answer' if s.get('error') else
                                  ('validate' if repair_enabled else 'execute'))
    builder.add_conditional_edges('validate', after_error)
    builder.add_conditional_edges('execute', lambda s: after_error(s) if s.get('error') else 'answer')
    builder.add_conditional_edges('repair', lambda s: 'answer' if s.get('error') else 'validate')
    builder.add_edge('answer', END)
    result = builder.compile().invoke({'question': question, 'sql': '', 'rows': [], 'columns': [],
             'error': None, 'fatal': False, 'repairs': 0, 'trace': []}, {'recursion_limit': 20})
    return {key: result[key] for key in ('sql','rows','columns','error','trace')} | {
        'calls': model.calls, 'latency_seconds': perf_counter() - start}
