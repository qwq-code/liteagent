"""Compare saved failure requests on the NPU; returned operations are never executed."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src/adapter_versions/v2_expanded"))
import integrations.lite_agent.model_client as model_client

BASE = Path("/home/pengzhe/liteagent-repair-full189-r16-20261023T0820")
ORDERS = (95, 99, 107, 122)
output = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "atomic-request-replay.json")
if output.exists():
    raise SystemExit("Refusing to overwrite an existing replay")
projection = model_client.atomic_provider_surface
records = []
client = model_client.StructuredToolModelClient(
    base_url="http://127.0.0.1:18035/v1", api_key="EMPTY", request_timeout_seconds=120,
)
try:
    for index, order in enumerate(ORDERS):
        candidates = sorted(BASE.glob(f"src/adapter_versions/v2_expanded/experiments/work/*/workers/*/raw/run-1/{order}-*/llm_requests/*attempt_1.json"))
        selected = None
        for path in candidates:
            request = json.loads(path.read_text())
            for tool in request.get("tools", []):
                function = tool["function"]
                props = function.get("parameters", {}).get("properties", {})
                if (function.get("name") == "adapter_call"
                        and props.get("adapter", {}).get("enum") == ["os"]
                        and props.get("action", {}).get("enum") == ["image.extract_text_batch"]):
                    selected = path, request
                    break
            if selected:
                break
        if selected is None:
            raise RuntimeError(f"No preserved fixed OCR route for order {order}")
        path, request = selected
        tools = copy.deepcopy(request["tools"])
        for tool in tools:
            function = tool["function"]
            if function["name"] == "adapter_call":
                function["name"] = "adapter__adapter_call"
                schema = function["parameters"]
                schema["x-route"] = {"adapter": "os", "action": "image.extract_text_batch"}
        assert projection(tools)[1], "Atomic projection must be exercised"
        # Alternate comparison order; this is a small diagnostic, not a benchmark.
        modes = ("wrapper", "atomic") if index % 2 == 0 else ("atomic", "wrapper")
        for mode in modes:
            model_client.atomic_provider_surface = projection if mode == "atomic" else lambda ts: (ts, {})
            started = time.monotonic()
            row = dict(order=order, mode=mode, request_file=str(path),
                       request_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       endpoint="http://127.0.0.1:18035/v1", model=request["model"],
                       output_token_budget=request["max_tokens"], tools_executed=False)
            try:
                result = client.propose(
                    model=request["model"], messages=request["messages"], tools=tools,
                    temperature=request["temperature"], output_token_budget=request["max_tokens"],
                    enable_thinking=request["extra_body"]["chat_template_kwargs"]["enable_thinking"],
                    expected_model=request["model"], request_timeout_seconds=120,
                )
                row.update(schema_valid=True, finish_reason=result["finish_reason"],
                           provider_tool=result["provider_tool"],
                           arguments=json.loads(result["arguments_raw"]), usage=result["usage"])
            except Exception as exc:
                row.update(schema_valid=False, error_type=type(exc).__name__, error=str(exc)[:400])
                if isinstance(exc, model_client.StructuredToolProtocolError):
                    row["schema_hints"] = exc.schema_hints
            row["seconds"] = round(time.monotonic() - started, 3)
            records.append(row)
            output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({key: row[key] for key in ("order", "mode", "schema_valid", "seconds")}), flush=True)
finally:
    model_client.atomic_provider_surface = projection
    client.client.close()
