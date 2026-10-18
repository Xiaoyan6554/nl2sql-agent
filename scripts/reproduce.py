"""一条命令重跑完整对比，保存新文件，不覆盖历史结果。会产生模型调用费用。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="可选：只做小样本复现")
    args = parser.parse_args()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    for mode in ["baseline", "v1_schema_link", "v2_repair", "v3_retrieval"]:
        output = ROOT / "results" / f"{stamp}_{mode}.json"
        command = [
            sys.executable,
            str(ROOT / "eval/run_eval.py"),
            "--mode",
            mode,
            "--output",
            str(output),
        ]
        if args.limit is not None:
            command.extend(["--limit", str(args.limit)])
        subprocess.run(command, cwd=ROOT, check=True)
    print(f"本次全部结果已写入 results/{stamp}_*.json；旧结果保留。")


if __name__ == "__main__":
    main()
