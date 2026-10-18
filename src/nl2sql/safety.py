"""AST 白名单是第一层边界，SQLite authorizer 是第二层。"""
from __future__ import annotations

import sqlglot
from sqlglot import exp


class UnsafeSQL(ValueError):
    pass


# 保留 Spider 常用的确定性函数，拒绝扩展加载、文件访问和大块内存函数。
SAFE_FUNCTIONS = frozenset(['abs', 'avg', 'count', 'sum', 'total', 'min', 'max', 'round', 'lower', 'upper', 'length', 'substr', 'substring', 'trim', 'ltrim', 'rtrim', 'replace', 'coalesce', 'ifnull', 'nullif', 'iif', 'like', 'glob', 'instr', 'date', 'time', 'datetime', 'julianday', 'strftime', 'unixepoch', 'cast', 'typeof', 'ceil', 'ceiling', 'floor', 'power', 'pow', 'sqrt', 'mod', 'printf', 'format', 'row_number', 'rank', 'dense_rank', 'percent_rank', 'cume_dist', 'ntile', 'lag', 'lead', 'first_value', 'last_value', 'nth_value', 'group_concat', 'concat', 'concat_ws'])


def parse_select(sql: str) -> exp.Expression:
    if not isinstance(sql, str) or len(sql) > 20000:
        raise UnsafeSQL('SQL 为空或过长')
    try:
        statements = sqlglot.parse(sql, read='sqlite')
    except sqlglot.errors.ParseError as exc:
        raise UnsafeSQL(f'SQL 解析失败：{exc.errors[0].get("description", "syntax")}') from None
    if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.SetOperation)):
        raise UnsafeSQL('只允许单条 SELECT 查询（可含 UNION/INTERSECT/EXCEPT）')
    tree = statements[0]
    for node in tree.walk():
        if isinstance(node, (exp.DDL, exp.DML, exp.Command, exp.Into, exp.Lock)):
            raise UnsafeSQL('查询中包含禁止操作')
        if isinstance(node, exp.With) and node.args.get('recursive'):
            raise UnsafeSQL('不允许递归 CTE')
        if isinstance(node, exp.Table):
            if not isinstance(node.this, exp.Identifier) or node.db or node.catalog:
                raise UnsafeSQL('不允许外部数据库或表值函数')
            if node.name.lower().startswith('sqlite_'):
                raise UnsafeSQL('不允许读取系统表')
        if isinstance(node, exp.Anonymous) and node.name.lower() not in SAFE_FUNCTIONS:
            raise UnsafeSQL(f'不允许函数：{node.name}')
    return tree


def validate_sql(sql: str, row_limit: int | None = None) -> str:
    tree = parse_select(sql)
    if row_limit is not None:
        limit = tree.args.get('limit')
        if limit is None:
            tree = tree.limit(row_limit)
        else:
            value = limit.expression
            if not isinstance(value, exp.Literal) or not value.is_int or int(value.this) < 0:
                raise UnsafeSQL('LIMIT 必须是非负整数')
            tree = tree.limit(min(row_limit, int(value.this)))
    return tree.sql(dialect='sqlite')
