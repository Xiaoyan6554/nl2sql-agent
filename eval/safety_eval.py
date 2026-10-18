"""固定 SQL 边界回归，与真实模型提示注入探测分开记账。"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from eval.run_eval import write_result
from nl2sql.config import ROOT, Settings
from nl2sql.db import database_path, execute
from nl2sql.graph import run_graph
from nl2sql.llm import ChatModel
from nl2sql.safety import validate_sql


def load_cases() -> list[dict]:
    return [json.loads(line) for line in (ROOT/'eval/malicious_cases.jsonl').read_text().splitlines()]


def check_case(case: dict, path: Path) -> dict:
    try:
        sql = validate_sql(case['sql'], row_limit=1)
        data = execute(path, sql)
        status = 'bounded' if len(data['rows']) <= 1 else 'uncontained'
        return {'id': case['id'], 'status': status, 'passed': status == case['expected']}
    except (ValueError, RuntimeError) as exc:
        return {'id': case['id'], 'status': 'blocked', 'passed': case['expected'] == 'blocked',
                'reason': str(exc)}


def run_safety(output: Path | None = None) -> int:
    output = output or ROOT/'results/safety.json'
    if output.exists():
        raise ValueError('安全报告已存在，请提供新的 --output')
    cases = load_cases()
    with tempfile.TemporaryDirectory(dir=ROOT/'work') as scratch:
        path = Path(scratch)/'unit.sqlite'
        with sqlite3.connect(path) as conn:
            conn.executescript("CREATE TABLE people(id INT,name TEXT,age INT);"
                               "INSERT INTO people VALUES(1,'A',20),(2,'B',30);")
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        records = [check_case(case, path) for case in cases]
        unchanged = before == hashlib.sha256(path.read_bytes()).hexdigest()
    settings = Settings.from_env()
    path = database_path(settings.spider_dir, 'concert_singer')
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    live = []
    for case in cases:
        if 'prompt' not in case:
            continue
        model = ChatModel(settings)
        result = run_graph(case['prompt'], path, model, mode='v2_repair', row_limit=100)
        # 只报告观测到的行为，不把拒绝自然语言的能力等同于底层数据库隔离。
        live.append({'id':case['id'], 'sql':result['sql'], 'error':result['error'],
                     'row_count':len(result['rows']), 'trace':result['trace'], 'calls':model.calls,
                     'database_unchanged':before == hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f'真实提示探测完成：{case["id"]}', flush=True)
    report = {'kind':'safety_boundary', 'status':'complete',
              'metadata':{'date':datetime.now(UTC).isoformat(), 'model':settings.model,
                  'temperature':settings.temperature, 'git_commit':subprocess.check_output(
                   ['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  'cases_sha256':hashlib.sha256((ROOT/'eval/malicious_cases.jsonl').read_bytes()).hexdigest()},
              'metrics':{'n':len(cases), 'passed':sum(r['passed'] for r in records),
                         'blocked':sum(r['status']=='blocked' for r in records),
                         'bounded':sum(r['status']=='bounded' for r in records),
                         'database_unchanged':unchanged,
                         'live_prompt_n':len(live),
                         'live_database_unchanged':all(r['database_unchanged'] for r in live)},
              'records':records, 'live_prompts':live,
              'limitation':'有限 SQL 回归与提示探测；不证明任意提示、任意数据库或部署环境安全。'}
    write_result(output, report)
    print(json.dumps(report['metrics'], ensure_ascii=False))
    return 0 if all(r['passed'] for r in records) and unchanged else 1
