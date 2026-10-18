# NL2SQL 数据问答 Agent

**个人项目，基于 Spider 公开数据集评测。**

当前处于 Phase 0，项目尚未完成。已建立环境、依赖锁文件、密钥模板和官方数据下载脚本。
Spider 自动下载返回非 ZIP 内容，按 `AGENTS.md` 要求暂停。
尚未调用模型，也没有任何基线或消融评测数字。

## 下一步：准备官方数据

1. 打开 [Spider 官方网站](https://yale-lily.github.io/spider)，点击 **Spider Dataset**。
2. 下载官方 `spider_data.zip`，保存在本项目的 `work/` 文件夹中。
3. 在终端运行：

```bash
cd /Users/mima1234/Downloads/nl2sql-agent
uv run python scripts/download_spider.py --archive work/spider_data.zip
```

也可以手动解压，调整目录为：

```text
data/spider/
├── dev.json
├── tables.json
├── train_spider.json
└── database/
    └── concert_singer/
        └── concert_singer.sqlite
```

检查已有数据（发现目标目录存在时仅校验，不再下载）：

```bash
uv run python scripts/download_spider.py
```

## 本地环境

```bash
uv sync --locked
```

Python 版本记在 `.python-version`，依赖记在 `pyproject.toml` 和 `uv.lock`。
`.env.example` 是空密钥模板；本机 `.env` 已配置 DeepSeek，权限为仅当前用户可读写。
数据、密钥、虚拟环境和临时下载均已加入 `.gitignore`。
不要将 `.env` 粘贴到问题报告或公开仓库。

## 计划与验收状态

| 阶段 | 状态 |
| --- | --- |
| Phase 0：环境与数据 | 环境已建立；等待手动下载官方数据 |
| Phase 0：基线与最小真实评测入口 | 尚未实现；数据下载失败后按要求停止 |
| Phase 1：完整基线评测 | 未开始 |
| Phase 2：Schema Linking、校验与重试 | 未开始 |
| Phase 3：训练集示例检索（可选） | 未开始 |
| Phase 4：安全测试 | 未开始 |
| Phase 5：错误导出与用户人工分类 | 未开始 |
| Phase 6：API、演示和面试文档 | 未开始 |

## 结果

无真实结果，`results/` 目前为空。不得把开发进度写成评测成果。

## 参考与致谢

- [Spider 数据与论文](https://yale-lily.github.io/spider)：数据集为 CC BY-SA 4.0；
  [官方代码](https://github.com/taoyds/spider) 为 Apache-2.0。本项目仅下载数据用于本地评测。
- [SQLGlot](https://github.com/tobymao/sqlglot)：MIT，计划用于 SQL AST 校验。
- [HTTPX](https://github.com/encode/httpx)：BSD-3-Clause，计划用于兼容模型接口。
- [python-dotenv](https://github.com/theskumar/python-dotenv)：BSD-3-Clause，计划读取本地配置。
- [pytest](https://github.com/pytest-dev/pytest)：MIT；[Ruff](https://github.com/astral-sh/ruff)：MIT。
- [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)：已查阅官方文档；
  LangGraph 为 MIT，待 Phase 2 按阶段引入。
- [DeepSeek 官方接口文档](https://api-docs.deepseek.com/)：默认模型配置来源。

当前脚手架和下载脚本为本项目编写，未复制第三方仓库实现。
