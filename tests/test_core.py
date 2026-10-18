import pytest

from eval.run_eval import equal_results, summarize
from nl2sql.baseline import run_baseline
from nl2sql.db import QueryError, connect, database_path, execute
from nl2sql.safety import UnsafeSQL, validate_sql
from tests.conftest import FakeModel


def test_compare_bag_order_and_duplicates():
    assert equal_results([(1,), (2,)], [(2,), (1,)], False)
    assert not equal_results([(1,), (2,)], [(2,), (1,)], True)
    assert not equal_results([(1,), (1,)], [(1,)], False)
    assert not equal_results([(None,)], [(0,)], False)


def test_baseline_is_single_call(database):
    model = FakeModel(['```sql\nSELECT count(*) FROM people\n```'])
    result = run_baseline('how many?', database, model)
    assert result['rows'] == [(3,)]
    assert result['error'] is None
    assert len(model.calls) == 1


@pytest.mark.parametrize('sql', ['DROP TABLE people', 'SELECT 1; DELETE FROM people',
    'PRAGMA table_info(people)', "SELECT load_extension('x')", 'SELECT * FROM sqlite_master',
    "SELECT * FROM pragma_table_info('people')", "ATTACH DATABASE '/tmp/x' AS x"])
def test_guard_blocks(database, sql):
    with pytest.raises((UnsafeSQL, QueryError)):
        execute(database, sql)


def test_read_only_and_limits(database):
    with connect(database) as conn, pytest.raises(Exception, match='readonly'):
        conn.execute('DELETE FROM people')
    with pytest.raises(QueryError, match='上限'):
        execute(database, 'SELECT * FROM people', max_rows=1)
    assert 'LIMIT 2' in validate_sql('SELECT * FROM people', row_limit=2)
    assert 'LIMIT 2' in validate_sql('SELECT * FROM people LIMIT 999', row_limit=2)


def test_timeout_and_columns(database):
    with pytest.raises(QueryError):
        execute(database, 'SELECT missing FROM people', explain=True)
    with pytest.raises(QueryError, match='interrupt'):
        execute(database, 'SELECT count(*) FROM people a, people b, people c, people d, '
                'people e, people f, people g, people h, people i, people j', timeout=0.000001)


def test_path_and_missing_tokens(tmp_path):
    with pytest.raises(ValueError):
        database_path(tmp_path, '../../etc/passwd')
    m = summarize([{'calls': [{'total_tokens': None}], 'correct': False, 'executable': False,
                    'latency_seconds': 1, 'gold_error': None}])
    assert m['total_tokens'] is None
    assert not m['usage_complete']


def test_invalid_utf8_preserves_distinction(database):
    import sqlite3
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO people VALUES (4, CAST(x'ff' AS TEXT), 40)")
        conn.execute("INSERT INTO people VALUES (5, CAST(x'fe' AS TEXT), 50)")
    result = execute(database, 'SELECT name FROM people WHERE id >= 4 ORDER BY id')
    assert result['rows'][0] != result['rows'][1]


def test_cte_union_aliases_and_strings(database):
    assert execute(database, 'WITH a AS (SELECT name FROM people) SELECT name FROM a')['rows']
    assert execute(database, "SELECT 'DROP TABLE people' AS harmless")['rows']
    assert execute(database, 'SELECT id FROM people UNION SELECT age FROM people')['rows']
    assert execute(database, 'SELECT p.name AS n FROM people p ORDER BY n')['rows']


def test_sqlite_authorizer_independent_of_ast(database):
    import sqlite3

    from nl2sql.db import guard, schema
    with connect(database) as conn:
        guard(conn, schema(database), 5)
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute('SELECT * FROM sqlite_master')
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("SELECT load_extension('x')")
