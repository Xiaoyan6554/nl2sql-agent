"""本机演示 API，输入只接受已配置数据库 ID，不接受文件路径。"""

from __future__ import annotations

import math
from threading import BoundedSemaphore
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field, field_validator

from nl2sql.baseline import run_baseline
from nl2sql.config import Settings
from nl2sql.db import database_path, schema
from nl2sql.graph import run_graph
from nl2sql.llm import ChatModel

app = FastAPI(title="NL2SQL 数据问答", version="0.1.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
capacity = BoundedSemaphore(2)


class AskRequest(BaseModel):
    db_id: str = Field(pattern=r"^[A-Za-z0-9_]+$", max_length=100)
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["baseline", "v1_schema_link", "v2_repair", "v3_retrieval"] = "v3_retrieval"
    row_limit: int = Field(default=100, ge=1, le=1000)

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("问题不能为空")
        return value.strip()


def settings_dependency() -> Settings:
    try:
        return Settings.from_env()
    except ValueError:
        raise HTTPException(503, "请检查项目 .env 配置") from None


Config = Annotated[Settings, Depends(settings_dependency)]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "project": "personal-spider-evaluation"}


@app.get("/databases")
def databases(settings: Config) -> list[str]:
    root = settings.spider_dir / "database"
    if not root.is_dir():
        raise HTTPException(503, "请先下载 Spider 数据")
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / f"{p.name}.sqlite").is_file()
    )


@app.get("/schema/{db_id}")
def get_schema(db_id: str, settings: Config) -> dict:
    try:
        return schema(database_path(settings.spider_dir, db_id))
    except ValueError:
        raise HTTPException(404, "数据库不存在") from None


def display_value(value):
    # API 展示使用替换字符；评测仍保留原始字节差异，不用展示值评分。
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8")
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


@app.post("/ask")
def ask(request: AskRequest, settings: Config) -> dict:
    try:
        path = database_path(settings.spider_dir, request.db_id)
    except ValueError:
        raise HTTPException(404, "数据库不存在") from None
    if not capacity.acquire(blocking=False):
        raise HTTPException(429, "已有查询执行中，请稍后重试")
    try:
        model = ChatModel(settings)
        kwargs = {
            "timeout": settings.sql_timeout,
            "max_rows": settings.max_rows,
            "row_limit": request.row_limit,
        }
        if request.mode == "baseline":
            result = run_baseline(request.question, path, model, **kwargs)
        else:
            result = run_graph(
                request.question,
                path,
                model,
                mode=request.mode,
                spider_dir=settings.spider_dir,
                **kwargs,
            )
        result["rows"] = [[display_value(v) for v in row] for row in result["rows"]]
        result["mode"] = request.mode
        result["row_limit"] = request.row_limit
        result["display_limited"] = True
        result["usage"] = {
            "calls": len(model.calls),
            "reported_tokens": sum(c.get("total_tokens") or 0 for c in model.calls),
            "complete": all(c.get("total_tokens") is not None for c in model.calls),
        }
        # 只返回需要的调用元数据，不回传密钥或原始提示。
        result.pop("calls")
        return result
    finally:
        capacity.release()
