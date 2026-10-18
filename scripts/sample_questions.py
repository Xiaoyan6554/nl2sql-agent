"""固定种子抽 dev 题目；只提交 ID 清单，题目全文留在本地。"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sample(source: Path, count: int = 150, seed: int = 20261018) -> tuple[dict, list[dict]]:
    raw = source.read_bytes()
    rows = json.loads(raw)
    ids = random.Random(seed).sample(range(len(rows)), count)
    questions = [{'id': i, 'db_id': rows[i]['db_id'], 'question': rows[i]['question'],
                  'gold_sql': rows[i]['query']} for i in ids]
    if len({q['db_id'] for q in questions}) < 10:
        raise ValueError('抽样未覆盖至少 10 个数据库；不自动挑选有利样本')
    return {'seed': seed, 'count': count, 'source_sha256': hashlib.sha256(raw).hexdigest(),
            'ids': ids, 'db_ids': sorted({q['db_id'] for q in questions})}, questions


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spider-dir', type=Path, default=ROOT / 'data/spider')
    args = p.parse_args()
    manifest, questions = sample(args.spider_dir / 'dev.json')
    (ROOT / 'eval/question_ids.json').write_text(json.dumps(manifest, indent=2))
    (ROOT / 'eval/questions.jsonl').write_text(''.join(json.dumps(q, ensure_ascii=False)+'\n'
                                                     for q in questions))
    print(f'已抽取 {len(questions)} 题，覆盖 {len(manifest["db_ids"])} 个数据库')


if __name__ == '__main__':
    main()
