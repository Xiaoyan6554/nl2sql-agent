"""真实 Spider 执行评测；所有对外指标均从本脚本的结果文件生成。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from nl2sql.baseline import run_baseline
from nl2sql.config import Settings
from nl2sql.db import database_path, execute
from nl2sql.llm import ChatModel
from nl2sql.safety import parse_select


def equal_results(predicted: list, gold: list, ordered: bool) -> bool:
    a, b = [tuple(row) for row in predicted], [tuple(row) for row in gold]
    # 保留重复行数量，不用 set 隐藏重复行错误；只在顶层 ORDER BY 时比较顺序。
    return a == b if ordered else Counter(a) == Counter(b)


def load_questions(settings: Settings, limit: int | None) -> tuple[list[dict], dict]:
    manifest = json.loads((ROOT / "eval/question_ids.json").read_text())
    source = (settings.spider_dir / "dev.json").read_bytes()
    if hashlib.sha256(source).hexdigest() != manifest["source_sha256"]:
        raise ValueError("dev.json 哈希与固定题目清单不一致")
    rows = json.loads(source)
    questions = [
        {
            "id": i,
            "db_id": rows[i]["db_id"],
            "question": rows[i]["question"],
            "gold_sql": rows[i]["query"],
        }
        for i in manifest["ids"]
    ]
    if limit is not None and not 1 <= limit <= len(questions):
        raise ValueError("--limit 超出题目范围")
    return questions[:limit], manifest


def evaluate_one(question: dict, settings: Settings, mode: str) -> dict:
    path = database_path(settings.spider_dir, question["db_id"])
    model = ChatModel(settings)
    if mode == "baseline":
        result = run_baseline(
            question["question"],
            path,
            model,
            timeout=settings.sql_timeout,
            max_rows=settings.max_rows,
        )
    else:
        from nl2sql.graph import run_graph

        result = run_graph(
            question["question"],
            path,
            model,
            mode=mode,
            spider_dir=settings.spider_dir,
            timeout=settings.sql_timeout,
            max_rows=settings.max_rows,
        )
    correct, gold_error = False, None
    try:
        gold = execute(
            path, question["gold_sql"], timeout=settings.sql_timeout, max_rows=settings.max_rows
        )
        ordered = parse_select(question["gold_sql"]).args.get("order") is not None
        correct = result["error"] is None and equal_results(result["rows"], gold["rows"], ordered)
    except (ValueError, RuntimeError) as exc:
        gold_error = str(exc)
    # 不将题目原文、gold SQL 或数据库原始结果提交到公开仓库。
    return {
        "id": question["id"],
        "db_id": question["db_id"],
        "sql": result["sql"],
        "correct": correct,
        "executable": result["error"] is None,
        "error": result["error"],
        "gold_error": gold_error,
        "row_count": len(result["rows"]),
        "trace": result["trace"],
        "calls": result["calls"],
        "latency_seconds": result["latency_seconds"],
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    calls = [call for row in rows for call in row["calls"]]
    tokens_known = all(call.get("total_tokens") is not None for call in calls)
    correct = sum(row["correct"] for row in rows)
    executable = sum(row["executable"] for row in rows)
    return {
        "n": n,
        "correct": correct,
        "executable": executable,
        "execution_accuracy": correct / n if n else None,
        "executable_rate": executable / n if n else None,
        "average_calls": len(calls) / n if n else None,
        "average_latency_seconds": sum(r["latency_seconds"] for r in rows) / n if n else None,
        "total_calls": len(calls),
        "total_tokens": sum(c["total_tokens"] for c in calls) if tokens_known else None,
        "reported_tokens": sum(c.get("total_tokens") or 0 for c in calls),
        "usage_complete": tokens_known,
        "gold_errors": sum(r["gold_error"] is not None for r in rows),
    }


def code_fingerprint() -> str:
    files = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "eval").glob("*.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def write_result(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--mode",
        choices=["baseline", "v1_schema_link", "v2_repair", "v3_retrieval", "safety"],
        default="baseline",
    )
    p.add_argument("--limit", type=int)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--output", type=Path)
    p.add_argument("--preflight", action="store_true", help="验证数据与 gold，不调用模型")
    args = p.parse_args()
    if args.mode == "safety":
        from eval.safety_eval import run_safety

        return run_safety(args.output)
    settings = Settings.from_env()
    questions, manifest = load_questions(settings, args.limit)
    if not 1 <= args.workers <= 8:
        p.error("--workers 范围为 1..8")
    # 预检所有 gold，基础设施故障不能被错误记成模型答错。
    for question in questions:
        execute(
            database_path(settings.spider_dir, question["db_id"]),
            question["gold_sql"],
            timeout=settings.sql_timeout,
            max_rows=settings.max_rows,
        )
    if args.preflight:
        print(f"数据与 gold 预检通过：{len(questions)} 题；未调用模型")
        return 0
    output = (
        args.output
        or ROOT / "results" / f"{args.mode}{'_' + str(args.limit) if args.limit else ''}.json"
    )
    if output.exists():
        p.error(f"结果文件已存在，请指定新的 --output：{output}")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
    report = {
        "kind": "spider_execution",
        "status": "running",
        "metadata": {
            "date": datetime.now(UTC).isoformat(),
            "mode": args.mode,
            "model": settings.model,
            "temperature": settings.temperature,
            "base_url": settings.base_url,
            "max_tokens": settings.max_tokens,
            "extra_body": settings.extra_body,
            "git_commit": commit,
            "git_dirty": dirty,
            "code_sha256": code_fingerprint(),
            "seed": manifest["seed"],
            "dev_sha256": manifest["source_sha256"],
            "train_sha256": hashlib.sha256(
                (settings.spider_dir / "train_spider.json").read_bytes()
            ).hexdigest(),
            "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
            "question_ids": [q["id"] for q in questions],
            "workers": args.workers,
            "sql_timeout": settings.sql_timeout,
            "max_rows": settings.max_rows,
            "metric": "single_database_execution_multiset",
        },
        "records": [],
    }
    start = perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(evaluate_one, q, settings, args.mode): q for q in questions}
        for future in as_completed(futures):
            result = future.result()
            report["records"].append(result)
            report["records"].sort(key=lambda r: manifest["ids"].index(r["id"]))
            report["metrics"] = summarize(report["records"])
            report["wall_seconds"] = perf_counter() - start
            write_result(output, report)
            print(
                f"{args.mode}: {len(report['records'])}/{len(questions)} "
                f"correct={report['metrics']['correct']}",
                flush=True,
            )
    report["status"] = "complete"
    write_result(output, report)
    print(json.dumps(report["metrics"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
