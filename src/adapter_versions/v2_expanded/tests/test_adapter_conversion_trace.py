from __future__ import annotations

from copy import deepcopy
import io
import json
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from calc_adapter.errors import AdapterError
from calc_adapter.service import create_app as calc_app
from integrations.lite_agent.adapter_executor import AdapterExecutor
from multi_apps_adapter.service import create_app as multi_apps_app


CONVERSION = {
    "contract": "calc.range.write.literal_cells.v1",
    "literal_cells": 4,
    "target_rows": 1,
    "target_columns": 4,
    "canonical_matrix_sha256": "a" * 64,
    "canonical_encoding": "json:ensure_ascii=false,sort_keys=true,separators=(comma,colon)",
}


@pytest.fixture
def bridge(monkeypatch):
    captured = {"error": False, "error_http_200": False, "padding": 0, "conversion": True}

    def run(parsed):
        captured["native_params"] = deepcopy(parsed.params)
        data = {"sheet": "Data", "range": "A1:D1", "observations": "x" * captured["padding"]}
        if captured["conversion"]:
            data["argument_conversion"] = deepcopy(CONVERSION)
        if captured["error"]:
            raise AdapterError("WRITE_FAILED", "synthetic native write failure", data, 422)
        return {"result": data, "verification": {"passed": True}}

    calc_client = calc_app(
        lifecycle=SimpleNamespace(listener_ready=lambda: True),
        runner=SimpleNamespace(run=run),
    ).test_client()

    def urlopen(request, *, timeout):
        payload = json.loads(request.data)
        captured["downstream"] = deepcopy(payload)
        response = calc_client.post("/v1/actions", json=payload)
        if response.status_code != 200 and not captured["error_http_200"]:
            raise HTTPError(
                request.full_url, response.status_code, "native error", {},
                io.BytesIO(response.data),
            )
        return io.BytesIO(response.data)

    monkeypatch.setattr("multi_apps_adapter.actions.urlopen", urlopen)
    multi_client = multi_apps_app().test_client()

    def post(url, *, json, timeout):
        captured["outer"] = deepcopy(json)
        client = multi_client if "/multi/" in url else calc_client
        response = client.post("/v1/actions", json=json)
        body = response.get_json()
        captured["http_body"] = body
        captured["http_body_before"] = deepcopy(body)
        return SimpleNamespace(
            ok=response.status_code == 200,
            status_code=response.status_code,
            json=lambda: body,
        )

    monkeypatch.setattr("integrations.lite_agent.adapter_executor.requests.post", post)
    return captured


@pytest.mark.parametrize("padding", [0, 7_000], ids=["short", "compacted"])
@pytest.mark.parametrize(
    ("forwarded", "failed", "error_http_200"),
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, False),
        (True, True, True),
    ],
    ids=["direct-ok", "direct-error", "forward-ok", "forward-http-error", "forward-body-error"],
)
def test_conversion_stays_in_host_trace_and_raw_calls_survive(
    bridge, tmp_path, padding, forwarded, failed, error_http_200,
):
    bridge.update(padding=padding, error=failed, error_http_200=error_http_200)
    params = {"sheet": "Data", "range": "A1:D1", "values": [["=literal", 12.5, True, None]]}
    arguments = (
        {"adapter": "libreoffice_calc", "action": "range.write", "payload": {"params": params}}
        if forwarded else params
    )
    original = deepcopy(arguments)
    domain, action = ("multi_apps", "adapter.call") if forwarded else ("libreoffice_calc", "range.write")
    trace_path = tmp_path / "adapter_calls.jsonl"
    executor = AdapterExecutor(
        {"libreoffice_calc": "http://synthetic/calc", "multi_apps": "http://synthetic/multi"},
        trace_path,
    )

    result = executor.execute(domain, action, arguments, {"step": 1})

    trace = json.loads(trace_path.read_text())
    assert trace["argument_conversion"] == CONVERSION
    assert result["executed"] is (not failed)
    assert result["status"] == ("error" if failed else "ok")
    assert trace["executed"] is (not failed)
    assert "argument_conversion" not in json.dumps(result)
    assert CONVERSION["contract"] not in json.dumps(result)
    assert bridge["http_body"] == bridge["http_body_before"]
    assert "argument_conversion" in json.dumps(bridge["http_body"])
    assert arguments == original == bridge["outer"]["params"] == trace["payload"]["params"]
    assert bridge["native_params"] == params
    if forwarded:
        assert bridge["downstream"]["params"] == params
    if padding:
        assert len(json.dumps(bridge["http_body"])) > 6_000
        feedback = result["result"]
        compacted = feedback.get("adapter_response", feedback)
        assert compacted["truncated"] is True
        if failed:
            assert result["error"]["truncated"] is True


def test_response_without_conversion_keeps_existing_feedback(bridge, tmp_path):
    bridge["conversion"] = False
    trace_path = tmp_path / "adapter_calls.jsonl"
    executor = AdapterExecutor({"libreoffice_calc": "http://synthetic/calc"}, trace_path)
    arguments = {
        "sheet": "Data", "range": "A1", "values": [[{"kind": "string", "value": "example"}]],
    }

    result = executor.execute("libreoffice_calc", "range.write", arguments, {})

    assert result["executed"] is True
    assert result["result"] == bridge["http_body_before"] == bridge["http_body"]
    assert "argument_conversion" not in json.loads(trace_path.read_text())
