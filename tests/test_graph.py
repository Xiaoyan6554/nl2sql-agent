import json

import pytest

from nl2sql.db import schema
from nl2sql.graph import run_graph
from nl2sql.llm import ModelError
from nl2sql.nodes.execute import execute_sql
from nl2sql.nodes.generate import generate_sql
from nl2sql.nodes.repair import repair_sql
from nl2sql.nodes.schema_link import choose_schema
from nl2sql.nodes.validate import check_sql
from tests.conftest import FakeModel

SELECTION = '{"tables":{"people":["name"]}}'


def test_schema_link_keeps_primary_key_and_falls_back(database):
    full = schema(database)
    selected, fallback = choose_schema('names', full, FakeModel([SELECTION]))
    assert not fallback
    assert set(selected['people']['columns']) == {'name', 'id'}
    for answer in ('nonsense', '{"tables":{"ghost":["name"]}}', '{"tables":[]}'):
        assert choose_schema('names', full, FakeModel([answer])) == (full, True)


def test_generate_validate_execute_repair_nodes(database):
    sql = generate_sql('names', schema(database), FakeModel(['SELECT name FROM people']))
    normalized = check_sql(sql, database, 5, 2)
    assert len(execute_sql(normalized, database, 5, 10)['rows']) == 2
    model = FakeModel(['SELECT name FROM people'])
    assert repair_sql('names', 'SELECT x', 'no such column', schema(database), model) == sql
    request = json.loads(model.calls[0]['prompt'])
    assert request['database_error'] == 'no such column'
    assert 'age' in request['schema']


def test_graph_repairs_once(database):
    model = FakeModel([SELECTION, 'SELECT missing FROM people', 'SELECT name FROM people'])
    result = run_graph('names', database, model)
    assert result['error'] is None
    assert len(model.calls) == 3
    assert [r['node'] for r in result['trace']].count('repair') == 1


def test_graph_max_two_repairs(database):
    model = FakeModel([SELECTION] + ['SELECT missing FROM people'] * 3)
    result = run_graph('names', database, model)
    assert result['error']
    assert len(model.calls) == 4
    assert [r['node'] for r in result['trace']].count('repair') == 2


def test_v1_and_empty_result_do_not_repair(database):
    result = run_graph('names', database, FakeModel([SELECTION, 'SELECT missing FROM people']),
                       mode='v1_schema_link')
    assert result['error']
    assert all(t['node'] != 'repair' for t in result['trace'])
    model = FakeModel([SELECTION, 'SELECT name FROM people WHERE id = -1'])
    result = run_graph('no match', database, model)
    assert not result['rows'] and result['error'] is None and len(model.calls) == 2


def test_model_failure_stops_graph(database):
    class Broken(FakeModel):
        def complete(self, system, user):
            raise ModelError('HTTP 402')
    result = run_graph('names', database, Broken([]))
    assert result['error']
    assert [t['node'] for t in result['trace']] == ['schema_link', 'answer']


def test_unknown_graph_mode(database):
    with pytest.raises(ValueError):
        run_graph('names', database, FakeModel([]), mode='unknown')
