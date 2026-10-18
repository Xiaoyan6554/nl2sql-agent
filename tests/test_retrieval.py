import json
from pathlib import Path

import pytest

from nl2sql.config import ROOT
from nl2sql.graph import run_graph
from nl2sql.retrieval import Retriever, get_retriever
from tests.conftest import FakeModel


def test_leaking_db_excluded_and_ranking():
    train = [
        {"db_id": "train", "question": "count singers", "query": "SELECT 1"},
        {"db_id": "dev", "question": "count singers", "query": "SELECT SECRET"},
        {"db_id": "other", "question": "names of cities", "query": "SELECT 2"},
    ]
    index = Retriever(train, {"dev"})
    matches = index.search("count singers")
    assert matches[0]["db_id"] == "train"
    assert all(row["db_id"] != "dev" for row in index.examples)


def test_actual_train_dev_database_disjoint():
    root = ROOT / "data/spider"
    if not root.exists():
        pytest.skip("未下载 Spider；真实数据防泄漏检查需下载后运行")
    index = get_retriever(root)
    dev = json.loads((root / "dev.json").read_text())
    assert not {r["db_id"] for r in dev} & {r["db_id"] for r in index.examples}
    assert len(index.search("How many singers are there?")) == 3


def test_retrieval_node_trace_and_prompt(database, monkeypatch):
    index = Retriever(
        [{"db_id": "train", "question": "list names", "query": "SELECT name FROM t"}], set()
    )
    monkeypatch.setattr("nl2sql.retrieval.get_retriever", lambda _: index)
    model = FakeModel(['{"tables":{"people":["name"]}}', "SELECT name FROM people"])
    result = run_graph("list names", database, model, mode="v3_retrieval", spider_dir=Path("."))
    assert result["error"] is None
    assert any(t["node"] == "retrieve" for t in result["trace"])
    assert json.loads(model.calls[1]["prompt"])["training_examples"][0]["db_id"] == "train"
