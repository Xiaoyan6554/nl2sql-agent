"""读取 run_eval.py 结果生成对比表，不手工录入或美化数字。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODES = ["baseline", "v1_schema_link", "v2_repair", "v3_retrieval"]


def comparison() -> str:
    lines = [
        "| 模式 | 正确题数 | 执行准确率 | 可执行率 | 平均调用 | 平均秒数 | token |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for mode in MODES:
        path = ROOT / "results" / f"{mode}.json"
        if not path.exists():
            lines.append(f"| {mode} | 未评测 | — | — | — | — | — |")
            continue
        report = json.loads(path.read_text())
        if report["status"] != "complete":
            lines.append(f"| {mode} | 运行中 | — | — | — | — | — |")
            continue
        m = report["metrics"]
        lines.append(
            f"| {mode} | {m['correct']}/{m['n']} | {m['execution_accuracy']} | "
            f"{m['executable_rate']} | {m['average_calls']} | "
            f"{m['average_latency_seconds']} | {m['total_tokens']} |"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    table = comparison()
    (ROOT / "docs/RESULTS.md").write_text(
        "# 实测结果\n\n由 scripts/report_results.py 生成；"
        "数值直接取自 results/*.json，未四舍五入。\n\n" + table + "\n"
    )
    print(table)
