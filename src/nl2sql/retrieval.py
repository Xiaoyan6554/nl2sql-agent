"""小型 BM25 检索：只用 train，过滤全部 dev 库。"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class Retriever:
    def __init__(self, train: list[dict], dev_db_ids: set[str]):
        self.examples = [
            {"id": i, "db_id": row["db_id"], "question": row["question"], "sql": row["query"]}
            for i, row in enumerate(train)
            if row["db_id"] not in dev_db_ids
        ]
        if not self.examples:
            raise ValueError("过滤后没有合法训练示例")
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.lengths = []
        for index, row in enumerate(self.examples):
            tokens = tokenize(row["question"])
            self.lengths.append(len(tokens))
            for token, frequency in Counter(tokens).items():
                self.postings[token].append((index, frequency))
        self.average_length = sum(self.lengths) / len(self.lengths)
        self.source_sha256: str | None = None
        assert not {e["db_id"] for e in self.examples} & dev_db_ids

    def search(self, question: str, k: int = 3) -> list[dict]:
        scores: dict[int, float] = defaultdict(float)
        n = len(self.examples)
        for token in set(tokenize(question)):
            postings = self.postings.get(token, [])
            idf = math.log(1 + (n - len(postings) + 0.5) / (len(postings) + 0.5))
            for index, frequency in postings:
                norm = 1.5 * (1 - 0.75 + 0.75 * self.lengths[index] / self.average_length)
                scores[index] += idf * frequency * 2.5 / (frequency + norm)
        ranked = sorted(scores, key=lambda i: (-scores[i], self.examples[i]["id"]))
        return [self.examples[i] for i in ranked[:k]]


@lru_cache(maxsize=2)
def get_retriever(spider_dir: Path) -> Retriever:
    train_path = spider_dir / "train_spider.json"
    dev = json.loads((spider_dir / "dev.json").read_text())
    raw = train_path.read_bytes()
    retriever = Retriever(json.loads(raw), {row["db_id"] for row in dev})
    retriever.source_sha256 = hashlib.sha256(raw).hexdigest()
    return retriever
