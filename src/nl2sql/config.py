"""从环境变量读取配置；不把密钥写入日志或结果。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    base_url: str = 'https://api.deepseek.com'
    model: str = 'deepseek-flash'
    temperature: float = 0
    max_tokens: int = 2048
    llm_timeout: float = 90
    spider_dir: Path = ROOT / 'data/spider'
    sql_timeout: float = 5
    max_rows: int = 100000
    extra_body: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(ROOT / '.env')
        key = os.getenv('LLM_API_KEY', '')
        if not key:
            raise ValueError('请在项目 .env 中配置 LLM_API_KEY')
        path = Path(os.getenv('SPIDER_DIR', 'data/spider'))
        return cls(
            api_key=key, base_url=os.getenv('LLM_BASE_URL', cls.base_url).rstrip('/'),
            model=os.getenv('LLM_MODEL', cls.model),
            temperature=float(os.getenv('LLM_TEMPERATURE', '0')),
            max_tokens=int(os.getenv('LLM_MAX_TOKENS', '2048')),
            llm_timeout=float(os.getenv('LLM_TIMEOUT_SECONDS', '90')),
            spider_dir=path if path.is_absolute() else ROOT / path,
            sql_timeout=float(os.getenv('SQL_TIMEOUT_SECONDS', '5')),
            max_rows=int(os.getenv('SQL_MAX_ROWS', '100000')),
            extra_body=json.loads(os.getenv('LLM_EXTRA_BODY', '{}')),
        )
