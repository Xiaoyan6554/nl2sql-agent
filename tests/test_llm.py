import httpx
import pytest

from nl2sql.config import Settings
from nl2sql.llm import ChatModel, ModelError


def fake_client(monkeypatch, payload, status=200):
    def respond(request):
        return httpx.Response(status, json=payload)

    client_class = httpx.Client
    monkeypatch.setattr(
        "nl2sql.llm.httpx.Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(respond), **kwargs),
    )


def test_failed_http_records_attempt_without_secret(monkeypatch):
    fake_client(monkeypatch, {"error": "secret-containing arbitrary upstream body"}, 402)
    model = ChatModel(Settings(api_key="test-secret"))
    with pytest.raises(ModelError, match="HTTP 402") as error:
        model.complete("system", "question")
    assert "secret" not in str(error.value)
    assert len(model.calls) == 1
    assert model.calls[0]["prompt_tokens"] is None
    assert "test-secret" not in repr(model.settings)


def test_truncated_response_keeps_reported_usage(monkeypatch):
    fake_client(
        monkeypatch,
        {
            "model": "stub",
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            "choices": [{"finish_reason": "length", "message": {"content": "SELECT"}}],
        },
    )
    model = ChatModel(Settings(api_key="test-secret"))
    with pytest.raises(ModelError, match="完整"):
        model.complete("system", "question")
    assert model.calls[0]["total_tokens"] == 7
    assert model.calls[0]["status"] == "error"
