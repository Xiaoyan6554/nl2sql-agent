# AGENTS.md — NL2SQL 数据问答 Agent（个人求职项目）

> 本文件放在仓库根目录，Codex 每次开工前先读它。
> 用户是 2026 届本科毕业生，目标是尽快拿到 "AI 应用 / Agent 开发" 岗位。这个仓库是他的**真实作品集**，所以下面的"诚信规则"优先级最高。

## 0. 诚信规则（最高优先级）

1. **所有指标只能来自 `eval/run_eval.py` 实际跑出来的结果文件**（`results/*.json`）。README、文档、简历文案里的数字必须能在结果文件里找到。禁止编造、四舍五入美化、或写"预计提升"。
2. 项目定位写成：**"个人项目，基于 Spider 公开数据集评测"**。禁止写"上线""日均请求量""公司项目""团队协作"等不存在的内容。
3. 代码里复用的开源代码或思路，在 README 的 "参考与致谢" 里写明来源和许可证。
4. 不提交 API Key、数据集原文件（Spider 的 License 为 CC BY-SA 4.0，只提交下载脚本和题目 ID 列表）。
5. 做不到、跑不通、结果变差，都如实记录，不要掩盖。"某优化没有提升" 本身就是合格的面试素材。

## 1. 项目目标

做一个能用自然语言查询 SQLite 数据库的 Agent，并且**用评测数据证明**每一步改进是否有效：

`基线（一次提示直接生成 SQL）` → `+ Schema Linking` → `+ SQL 校验与报错重试` → `+ 相似示例检索` → 逐项对比执行准确率。

重点不是功能多，而是**"有基线、有消融、有错误分析、有安全测试"**——这是面试官真正想听的。

### 明确不做（防止范围膨胀）
Neo4j、Milvus、vLLM、Kubernetes、模型微调、多租户权限、GraphRAG。需要加任何重依赖前，先在 `docs/NOTES.md` 写明理由并问用户。

## 2. 技术栈

- Python 3.11+，用 `uv` 或 `venv` + `requirements.txt` 管理
- 编排：LangGraph（**先查当前官方文档再写，不要凭记忆写 API**）
- LLM：OpenAI 兼容接口，`base_url` / `model` / `api_key` 全部走环境变量（默认可用 DeepSeek，必须可切换）
- SQL 解析与校验：SQLGlot
- 数据库：SQLite（只读连接：`file:...?mode=ro`，加执行超时）
- 服务：FastAPI；演示页面：Streamlit 或 Gradio（二选一，最简）
- 测试：pytest
- 代码风格：类型标注、函数短小、关键位置写中文注释（用户要读懂它）

## 3. 数据与评测

- 数据集：Spider（官方仓库 https://github.com/taoyds/spider ，README 里有下载方式）。
  - 若自动下载失败，**停下来告诉用户手动下载到 `data/spider/`**，不要自己造数据。
- 评测集：从 Spider **dev** 集中按固定随机种子抽 **150 题**，覆盖至少 10 个不同数据库，题目 ID 保存到 `eval/questions.jsonl`（含 question、db_id、gold_sql）。
- 指标：**执行准确率（Execution Accuracy）**——预测 SQL 与标准 SQL 在同一数据库上的执行结果集一致（忽略行顺序，除非标准 SQL 含 ORDER BY）。同时记录：SQL 可执行率、平均调用次数、平均延迟、token 用量。
- 可选加分：接入 Spider 官方 test-suite 评测（taoyds/test-suite-sql-eval）做更严格的对比。
- **防泄漏**：Phase 3 的"相似示例检索"只能从 Spider **train** 集取示例，且不能包含 dev 评测库对应的题目。
- 固定随机种子与模型版本，每个结果文件记录：日期、模型名、温度、git commit。

## 4. 目录结构（建议）

```
.
├── AGENTS.md
├── README.md                # 项目介绍、架构图（mermaid）、结果表、复现步骤、局限
├── pyproject.toml / requirements.txt
├── .env.example
├── scripts/download_spider.py
├── src/nl2sql/
│   ├── llm.py               # 模型调用封装
│   ├── db.py                # 只读连接、执行、超时
│   ├── baseline.py          # 基线：整库 schema + 问题 -> SQL
│   ├── graph.py             # LangGraph 流程
│   ├── nodes/               # schema_link / generate / validate / execute / repair
│   ├── safety.py            # SQL 安全校验（SQLGlot AST）
│   └── api.py               # FastAPI
├── eval/
│   ├── questions.jsonl
│   ├── run_eval.py          # 一条命令跑完并写 results/
│   └── malicious_cases.jsonl
├── results/                 # 每次评测的 json 结果
├── tests/
└── docs/
    ├── NOTES.md             # 每阶段做了什么、为什么（中文，给用户学习）
    ├── ERROR_ANALYSIS.md
    └── INTERVIEW.md
```

## 5. 分阶段计划（每阶段独立提交，完成并验收后再进入下一阶段）

### Phase 0 — 脚手架与数据（约半天）
- 初始化仓库、依赖、`.env.example`、数据下载脚本、抽题脚本、模型调用封装。
- **验收**：`python eval/run_eval.py --limit 5 --mode baseline` 能跑通并生成结果文件（哪怕准确率低）。

### Phase 1 — 基线 + 评测框架（约 1 天）
- 实现 `baseline`：把整个库的 schema 放进提示，一次生成 SQL，执行，与标准答案比对。
- **验收**：150 题完整跑完，`results/baseline.json` 记录执行准确率、可执行率、延迟、token。
- 先跑 10 题检查成本，再跑全量。

### Phase 2 — LangGraph 流程（约 2–3 天）
节点：`schema_link → generate → validate → execute → (失败) repair → ... → answer`
- `schema_link`：只保留与问题相关的表和字段（先用 LLM 选表选列；有余力再加 BM25 或向量召回对比）。
- `validate`：SQLGlot 解析；只允许单条 SELECT；禁止写操作；校验表名字段名存在；缺 LIMIT 时补上。
- `repair`：把数据库报错（或空结果提示）回传模型，**最多 2 轮**。
- 每加一个能力，各跑一次全量评测，保存为 `results/v1_schema_link.json`、`results/v2_repair.json` 等，**做消融对比**。
- **验收**：`docs/NOTES.md` 有一张对比表；每个节点有单元测试。

### Phase 3 — 相似示例检索（约 1–2 天，可选，时间紧就跳过）
- 从 Spider train 里检索 3 条相似问题和 SQL 作为 few-shot（先用 BM25，简单可靠）。
- **验收**：对比有无 few-shot 的结果，并确认没有数据泄漏（写一个测试检查示例库与评测集的 db_id 不重叠）。

### Phase 4 — 安全测试（约 1 天）
- 构造 30 条恶意或越界输入（DROP/DELETE/UPDATE、多语句注入、"忽略以上指令"、读取系统表、超大结果集等），写入 `eval/malicious_cases.jsonl`。
- 用 pytest 跑，报告 "N/30 被拦截"，列出没拦住的并修复或记录局限。**不要承诺 100%。**
- **验收**：`pytest` 全绿，README 如实写拦截结果。

### Phase 5 — 错误分析（约 1 天，最重要）
- 把最终版失败的题全部导出，人工（用户本人）读至少 20 条，在 `docs/ERROR_ANALYSIS.md` 里分类：schema 选错 / JOIN 错 / 聚合错 / 歧义 / 标准答案本身有问题 / 其他。每类给 1–2 个例子和可能的改法。
- Codex 负责导出和统计，**分类结论由用户亲自判断**，Codex 可提示但不能直接代写。

### Phase 6 — 服务、演示与文档（约 1 天）
- FastAPI `POST /ask` 返回：生成的 SQL、结果、每个节点的 trace、耗时。
- 一个最简演示页面。Dockerfile 可选。
- README：一句话介绍、架构 mermaid 图、结果对比表（数字来自 results/）、复现步骤、局限与未来改进、参考与致谢。
- `docs/INTERVIEW.md`：1 分钟版 / 5 分钟版项目讲解稿，以及 20 个面试官可能的追问和**基于本项目真实代码和结果**的回答要点（例如：为什么要做 Schema Linking？repair 为什么最多 2 轮？怎么防止评测泄漏？SQL 注入怎么防？执行准确率怎么算？哪些改进没有效果？）。

## 6. 工作方式

- 每个阶段开工前，先在 `docs/NOTES.md` 写 5 行以内的计划；完成后写：做了什么、为什么这样做、**用户必须弄懂的 5 个概念/问题**（中文，通俗，带指向代码位置）。
- 小步提交，commit message 清晰（例如 `feat: add sqlglot validator`）。
- 遇到需求不清、数据下载失败、需要花钱的操作或加重依赖，先停下来问用户。
- 不要一次生成大量用户看不懂的代码；宁可功能少，保证用户能逐行解释。
- 项目完成后，由用户自己重新跑一遍 `eval/run_eval.py` 确认数字可复现。

## 7. 完成定义（Definition of Done）

- [ ] 仓库公开，README 完整，`.env.example` 有，无任何密钥
- [ ] 基线与至少 2 个改进版的评测结果文件齐全，且可一条命令复现
- [ ] 安全测试和单元测试通过
- [ ] `ERROR_ANALYSIS.md` 由用户本人完成分类
- [ ] `INTERVIEW.md` 完成，用户能不看稿讲清楚整个流程
