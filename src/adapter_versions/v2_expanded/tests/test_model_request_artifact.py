from copy import deepcopy
import hashlib
import json

from scripts.run_lite_agent_pilot import write_model_request_artifact


def test_request_artifact_preserves_tool_order_and_canonical_hash(tmp_path):
    request = {
        "model": "synthetic-model",
        "messages": [{"role": "user", "content": "Inspect the visible record."}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "inspect_record",
                "description": "Read one selected record.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "record_path": {"type": "string"},
                        "mode": {"type": "string", "enum": ["brief", "full"]},
                    },
                    "required": ["record_path"],
                    "additionalProperties": False,
                },
            },
        }],
    }
    original = deepcopy(request)
    record = write_model_request_artifact(
        tmp_path,
        request_index=1,
        step_num=3,
        attempt=1,
        screenshot="step_003_before.png",
        request=request,
    )
    artifact = (tmp_path / record["path"]).read_bytes()
    unsorted = json.dumps(request, ensure_ascii=False, default=str).encode("utf-8")
    canonical = json.dumps(
        request, ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")

    assert artifact == unsorted + b"\n"
    assert artifact != canonical + b"\n"
    assert record["canonical_request_sha256"] == hashlib.sha256(canonical).hexdigest()
    assert record["artifact_sha256"] == hashlib.sha256(artifact).hexdigest()
    assert record["bytes"] == len(artifact)
    assert request == original
