"""导出失败题，分类字段留给用户本人填写。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--result", type=Path, default=ROOT / "results/v3_retrieval.json")
    p.add_argument("--output", type=Path, default=ROOT / "docs/ERROR_CASES.local.md")
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit("导出文件已存在；为保护人工笔记，请指定新的 --output")
    report = json.loads(args.result.read_text())
    dev = json.loads((ROOT / "data/spider/dev.json").read_text())
    failed = [row for row in report["records"] if not row["correct"]]
    lines = [
        "# 失败题人工复核（仅本地）",
        "",
        "题目与 gold 来自 Spider（CC BY-SA 4.0），此文件不提交。",
        "",
        "请本人至少读二十题。先独立理解问题，再检查 SQL；不要默认 gold 一定正确。",
        "",
    ]
    for row in failed:
        question = dev[row["id"]]
        lines.extend(
            [
                f"## dev ID {row['id']} · {row['db_id']}",
                "",
                question["question"],
                "",
                "标准 SQL：",
                "```sql",
                question["query"],
                "```",
                "",
                "预测 SQL：",
                "```sql",
                row["sql"],
                "```",
                "",
                f"执行错误：{row['error'] or '无；结果不一致'}",
                "",
                "本人分类：待填写",
                "",
                "判断依据和可能改法：待填写",
                "",
            ]
        )
    args.output.write_text("\n".join(lines))
    public = ROOT / "docs/ERROR_ANALYSIS.md"
    if not public.exists():
        public.write_text(
            "# 错误分析（等待本人分类）\n\n"
            "来源：results/v3_retrieval.json。全部失败题已导出到被 Git 忽略的 "
            "`docs/ERROR_CASES.local.md`。这里不冒充用户已经完成人工分析。\n\n"
            "请至少复核二十题，分类：schema 选错 / JOIN 错 / 聚合错 / 歧义 / "
            "标准答案问题 / 其他。每类补一至两个实例 ID、判断依据与可能改法。\n\n"
            "| dev ID | 数据库 | 本人分类 | 判断依据 / 改法 |\n| --- | --- | --- | --- |\n"
            + "\n".join(f"| {r['id']} | {r['db_id']} | 待填写 | 待填写 |" for r in failed)
            + "\n\n## 分类统计\n\n待本人完成分类后统计；不预填结论。\n"
        )
    print(f"已导出 {len(failed)} 道失败题，全部分类留空。")


if __name__ == "__main__":
    main()
