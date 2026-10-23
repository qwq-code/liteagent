from __future__ import annotations

from typing import Any

import httpx
import integrations.lite_agent.model_client as model_client_module
import pytest
from openai import APITimeoutError, OpenAI
from integrations.lite_agent.model_client import StructuredToolModelClient


def test_default_transport_delegates_retries_to_runner(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    class FakeHttpClient:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(model_client_module, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(model_client_module.httpx, "Client", FakeHttpClient)

    StructuredToolModelClient(
        base_url="http://unused/v1",
        api_key="EMPTY",
        request_timeout_seconds=12.0,
    )

    assert captured["max_retries"] == 0
    assert isinstance(captured["http_client"], FakeHttpClient)


def test_sdk_timeout_is_not_retried_inside_one_runner_attempt() -> None:
    requests: list[httpx.Request] = []

    def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    transport = httpx.MockTransport(fail)
    http_client = httpx.Client(transport=transport)
    sdk = OpenAI(
        base_url="http://unused/v1",
        api_key="EMPTY",
        max_retries=model_client_module.MODEL_SDK_MAX_RETRIES,
        http_client=http_client,
    )

    with pytest.raises(APITimeoutError):
        sdk.chat.completions.create(model="qwen3.5-4b", messages=[], tools=[])

    assert len(requests) == 1
    http_client.close()
