"""微型数据库仅供单元测试，从不写入 Spider 数据或作品集准确率。"""
import sqlite3

import pytest


@pytest.fixture
def database(tmp_path):
    path = tmp_path / 'unit.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript('CREATE TABLE people(id INTEGER PRIMARY KEY, name TEXT, age INTEGER);'
                          "INSERT INTO people VALUES (1, 'Alice', 20), (2, 'Bob', 30), (3, 'Bob', 30);")
    return path


class FakeModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []
    def complete(self, system, user):
        self.calls.append({'total_tokens': 0, 'prompt': user})
        return next(self.replies)
