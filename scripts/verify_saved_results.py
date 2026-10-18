"""离线重放已保存 SQL，核对历史结果；不调用模型，也不改写评测结果。"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.run_eval import equal_results, summarize
from nl2sql.db import database_path, execute
from nl2sql.safety import parse_select


def main() -> None:
    raw = (ROOT / "data/spider/dev.json").read_bytes()
    dev = json.loads(raw)
    for path in sorted((ROOT / "results").glob("*.json")):
        report = json.loads(path.read_text())
        if report.get("kind") != "spider_execution" or report["status"] != "complete":
            continue
        assert hashlib.sha256(raw).hexdigest() == report["metadata"]["dev_sha256"]
        assert summarize(report["records"]) == report["metrics"], f"汇总不一致：{path.name}"
        assert [r["id"] for r in report["records"]] == report["metadata"]["question_ids"]
        for row in report["records"]:
            question = dev[row["id"]]
            database = database_path(ROOT / "data/spider", row["db_id"])
            gold = execute(database, question["query"])
            try:
                pred = execute(database, row["sql"])
                executable = True
            except (ValueError, RuntimeError):
                pred, executable = {"rows": []}, False
            ordered = parse_select(question["query"]).args.get("order") is not None
            correct = executable and equal_results(pred["rows"], gold["rows"], ordered)
            assert executable == row["executable"], f"可执行状态不一致：{path.name} ID {row['id']}"
            assert correct == row["correct"], f"评分不一致：{path.name} ID {row['id']}"
        print(f"已核验 {path.name}：逐题结果和汇总一致")


if __name__ == "__main__":
    main()
