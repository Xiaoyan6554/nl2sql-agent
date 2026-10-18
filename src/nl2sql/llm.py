"""一次 HTTP 请求对应一次计费尝试，不隐藏 SDK 自动重试。"""
from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Protocol

import httpx

from nl2sql.config import Settings


class ModelError(RuntimeError):
    pass


class Model(Protocol):
    calls: list[dict]
    def complete(self, system: str, user: str) -> str: ...


@dataclass
class ChatModel:
    settings: Settings
    calls: list[dict] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        start = perf_counter()
        record: dict = {'model_requested': self.settings.model, 'status': 'error',
                        'prompt_tokens': None, 'completion_tokens': None}
        self.calls.append(record)
        # extra_body 可适配供应商，但不能覆盖模型、消息和采样参数。
        body = {**self.settings.extra_body, 'model': self.settings.model,
                'temperature': self.settings.temperature, 'max_tokens': self.settings.max_tokens,
                'stream': False, 'messages': [{'role': 'system', 'content': system},
                                             {'role': 'user', 'content': user}]}
        try:
            with httpx.Client(timeout=self.settings.llm_timeout) as client:
                response = client.post(self.settings.base_url + '/chat/completions', json=body,
                                       headers={'Authorization': f'Bearer {self.settings.api_key}'})
            record['http_status'] = response.status_code
            if response.status_code != 200:
                # 不回显请求头、密钥或供应商的任意报错正文。
                raise ModelError(f'模型接口 HTTP {response.status_code}')
            data = response.json()
            usage = data.get('usage') or {}
            record.update(model_returned=data.get('model'),
                          prompt_tokens=usage.get('prompt_tokens'),
                          completion_tokens=usage.get('completion_tokens'),
                          total_tokens=usage.get('total_tokens'),
                          finish_reason=data['choices'][0].get('finish_reason'))
            if record['finish_reason'] != 'stop':
                raise ModelError(f'模型未完整输出：{record["finish_reason"]}')
            content = data['choices'][0]['message'].get('content')
            if not isinstance(content, str) or not content.strip():
                raise ModelError('模型返回空内容')
            record['status'] = 'ok'
            return content.strip()
        except httpx.HTTPError as exc:
            raise ModelError(f'模型网络错误：{type(exc).__name__}') from None
        except (KeyError, ValueError, TypeError, IndexError):
            raise ModelError('模型返回格式无效') from None
        finally:
            record['latency_seconds'] = perf_counter() - start
