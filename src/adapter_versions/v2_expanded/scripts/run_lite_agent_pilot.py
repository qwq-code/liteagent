#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import io
import json
import logging
import os
import re
import sys
import time
import traceback
import zipfile
import zlib
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent if V2_ROOT.name == "baseline" else V2_ROOT.parents[1]
OSWORLD_ROOT = PROJECT_ROOT / "third_party" / "OSWorld"
V2_SCRIPTS = V2_ROOT / "scripts"
for path in (V2_ROOT, V2_SCRIPTS, OSWORLD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from integrations.lite_agent.runtime import (  # noqa: E402
    AdapterExecutor,
    LiteAgent,
    LiteAgentConfig,
    RuntimeState,
    StructuredToolModelClient,
    StructuredToolProtocolError,
    write_event,
)
from integrations.lite_agent.reasoning import (  # noqa: E402
    SUPPORTED_REASONING_EFFORTS,
    SUPPORTED_REASONING_MODES,
    explicit_effective_reasoning_mode,
    extract_reasoning_effort_enum,
)
from integrations.lite_agent.stall_policy import (  # noqa: E402
    detect_no_progress_stall,
)
from integrations.lite_agent.episode_control import (  # noqa: E402
    advance_local_step,
    begin_same_vm_soft_restart,
    consume_terminal_audit,
    finalize_terminal_after_deadline,
    mark_tool_result_for_audit,
    record_model_audit,
)
from integrations.holo_agent import (  # noqa: E402
    HoloGroundingAgent,
    HoloGroundingConfig,
    HoloGuiGateway,
)
from integrations.openapa_osworld.provider import install_provider_patch  # noqa: E402
from scripts.evaluation_boundary import (  # noqa: E402
    attach_evaluator_after_episode,
    evaluator_cache_resources,
    load_agent_task_config_isolated,
    load_evaluator_task_config,
    osworld_task_path,
    prefetch_resources,
    reset_task_config,
    setup_cache_resources,
)
from scripts.frozen_condition import (  # noqa: E402
    _promotion_gate_required,
    enforce_runner_condition,
)
from scripts.openapa_trajectory import build_trajectory_manifest, write_manifest  # noqa: E402
from scripts.office_episode_recovery import (  # noqa: E402
    model_visible_recovery_status,
    recover_office_episode,
    recovery_decision,
)
from scripts.strict_runner_support import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_QCOW2,
    assert_secret_absent,
    assert_strict_process_boundary,
    capture_evaluator_evidence,
    configure_evaluator_runtime,
    deploy_generic_stack,
    install_post_reset_prepare,
    load_tasks,
    should_enable_guest_proxy,
    utc_now,
    write_json,
)


OBSERVATION_SCREENSHOT_ATTEMPTS = 3
OBSERVATION_SCREENSHOT_RETRY_SECONDS = 1.0
ZIP_PACKAGED_DOCUMENT_SUFFIXES = frozenset(
    {
        ".docx",
        ".docm",
        ".odg",
        ".odp",
        ".ods",
        ".odt",
        ".pptm",
        ".pptx",
        ".ppsx",
        ".xlsm",
        ".xlsx",
        ".zip",
    }
)
STRICT_GUEST_SANITIZE_PATTERNS = (
    "task_manifest.json",
    "**/task_manifest.json",
    "tasks.py",
    "reference_profiles.py",
    "__pycache__/tasks*.pyc",
    "__pycache__/reference_profiles*.pyc",
    "**/*gold*",
)
STRICT_GUEST_SANITIZE_CASEFOLDED_FILENAMES = frozenset(
    {
        "task_manifest.json",
        "tasks.py",
        "reference_profiles.py",
    }
)
GENERIC_GUEST_PACKAGE_ROOTS = (
    "/tmp/osworld-calc-adapter-payload/calc_adapter",
    "/home/user/.local/share/osworld-calc-adapter/calc_adapter",
    "/tmp/osworld-impress-adapter-payload/impress_adapter",
    "/home/user/.local/share/osworld-impress-adapter/impress_adapter",
    "/tmp/osworld-chrome-adapter-payload/chrome_adapter",
    "/home/user/.local/share/osworld-chrome-adapter/chrome_adapter",
    "/tmp/osworld-gimp-adapter-payload/gimp_adapter",
    "/home/user/.local/share/osworld-gimp-adapter/gimp_adapter",
    "/tmp/osworld-os-adapter-payload/os_adapter",
    "/home/user/.local/share/osworld-os-adapter/os_adapter",
    "/tmp/osworld-writer-adapter-payload/writer_adapter",
    "/home/user/.local/share/osworld-writer-adapter/writer_adapter",
    "/tmp/osworld-vscode-adapter-payload/vscode_adapter",
    "/home/user/.local/share/osworld-vscode-adapter/vscode_adapter",
    "/tmp/osworld-vlc-adapter-payload/vlc_adapter",
    "/home/user/.local/share/osworld-vlc-adapter/vlc_adapter",
    "/tmp/osworld-thunderbird-adapter-payload/thunderbird_adapter",
    "/home/user/.local/share/osworld-thunderbird-adapter/thunderbird_adapter",
    "/tmp/osworld-multi-apps-adapter-payload/multi_apps_adapter",
    "/home/user/.local/share/osworld-multi-apps-adapter/multi_apps_adapter",
)


def _complete_zip_payload(payload: Any) -> bool:
    if not isinstance(payload, (bytes, bytearray)) or not payload:
        return False
    try:
        return zipfile.is_zipfile(io.BytesIO(payload))
    except (OSError, ValueError):
        return False


def install_stable_evaluator_file_fetch(
    controller: Any,
    *,
    attempts: int = 10,
    delay_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    """Retry VM reads that catch a ZIP-packaged document mid-save."""
    if attempts <= 0:
        raise ValueError("attempts must be positive")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be non-negative")

    original_get_file = controller.get_file
    retry_events: list[dict[str, Any]] = []

    def stable_get_file(path: str) -> Any:
        suffix = Path(path).suffix.lower()
        payload = original_get_file(path)
        if suffix not in ZIP_PACKAGED_DOCUMENT_SUFFIXES or _complete_zip_payload(
            payload
        ):
            return payload

        sizes = [len(payload) if isinstance(payload, (bytes, bytearray)) else None]
        for _attempt in range(2, attempts + 1):
            time.sleep(delay_seconds)
            payload = original_get_file(path)
            sizes.append(
                len(payload) if isinstance(payload, (bytes, bytearray)) else None
            )
            if _complete_zip_payload(payload):
                break

        retry_events.append(
            {
                "path": path,
                "suffix": suffix,
                "attempts": len(sizes),
                "sizes": sizes,
                "final_valid_zip": _complete_zip_payload(payload),
            }
        )
        return payload

    controller.get_file = stable_get_file
    return retry_events


def sanitize_generic_guest_deployment(controller: Any) -> dict[str, Any]:
    encoded_roots = json.dumps(GENERIC_GUEST_PACKAGE_ROOTS)
    encoded_patterns = json.dumps(STRICT_GUEST_SANITIZE_PATTERNS)
    encoded_filenames = json.dumps(sorted(STRICT_GUEST_SANITIZE_CASEFOLDED_FILENAMES))
    code = f"""
import json
from pathlib import Path

roots = json.loads({encoded_roots!r})
patterns = json.loads({encoded_patterns!r})
denied_filenames = set(json.loads({encoded_filenames!r}))
removed = []
for root_value in roots:
    root = Path(root_value)
    if root.is_dir():
        for path in root.rglob('*'):
            folded_name = path.name.casefold()
            if path.is_file() or path.is_symlink():
                if folded_name in denied_filenames or 'gold' in folded_name:
                    path.unlink(missing_ok=True)
                    removed.append(str(path))
    for relative_pattern in patterns:
        for path in root.glob(relative_pattern):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
                removed.append(str(path))
remaining = []
for root_value in roots:
    root = Path(root_value)
    if root.is_dir():
        remaining.extend(
            str(path)
            for path in root.rglob('*')
            if (path.is_file() or path.is_symlink())
            and (
                path.name.casefold() in denied_filenames
                or 'gold' in path.name.casefold()
            )
        )
    for relative_pattern in patterns:
        remaining.extend(str(path) for path in root.glob(relative_pattern))
print(json.dumps({{"removed": sorted(removed), "remaining": sorted(set(remaining))}}))
""".strip()
    response = controller.execute_python_command(code)
    output = str(response.get("output", "")).strip().splitlines()
    try:
        result = json.loads(output[-1]) if output else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"failed to parse generic guest sanitization result: {response}"
        ) from exc
    if result.get("remaining"):
        raise RuntimeError(
            f"legacy dataset artifacts remain in generic guest: {result['remaining']}"
        )
    return result


def capture_generic_guest_inventory(controller: Any) -> dict[str, Any]:
    encoded_roots = json.dumps(GENERIC_GUEST_PACKAGE_ROOTS)
    code = f"""
import base64
import hashlib
import json
import zlib
from pathlib import Path

roots = json.loads({encoded_roots!r})
packages = []
for root_value in roots:
    root = Path(root_value)
    files = []
    if root.is_dir():
        for path in sorted(root.rglob('*')):
            if path.is_symlink():
                files.append(
                    {{
                        'path': str(path),
                        'type': 'symlink',
                        'target': str(path.readlink()),
                    }}
                )
            elif path.is_file():
                digest = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                files.append(
                    {{
                        'path': str(path),
                        'type': 'file',
                        'size': path.stat().st_size,
                        'sha256': digest.hexdigest(),
                    }}
                )
    packages.append({{'root': root_value, 'exists': root.is_dir(), 'files': files}})
inventory = json.dumps(
    {{'schema_version': 1, 'packages': packages}},
    sort_keys=True,
    separators=(',', ':'),
).encode()
print(base64.b64encode(zlib.compress(inventory, level=9)).decode())
""".strip()
    response = controller.execute_python_command(code)
    output = str(response.get("output", "")).strip().splitlines()
    try:
        compressed = base64.b64decode(output[-1], validate=True) if output else b""
        result = json.loads(zlib.decompress(compressed))
    except (
        binascii.Error,
        json.JSONDecodeError,
        UnicodeDecodeError,
        zlib.error,
    ) as exc:
        raise RuntimeError(
            f"failed to parse generic guest inventory: {response}"
        ) from exc
    packages = result.get("packages")
    if (
        result.get("schema_version") != 1
        or not isinstance(packages, list)
        or len(packages) != len(GENERIC_GUEST_PACKAGE_ROOTS)
    ):
        raise RuntimeError(f"incomplete generic guest inventory: {result}")
    return result


def probe_terminal_working_directory(controller: Any) -> str | None:
    code = """
import json
import os
from pathlib import Path

candidates = []
for process_dir in Path('/proc').glob('[0-9]*'):
    try:
        command = (process_dir / 'cmdline').read_bytes().split(b'\\0')[0].decode('utf-8')
        working_directory = os.readlink(process_dir / 'cwd')
    except (FileNotFoundError, PermissionError, ProcessLookupError, UnicodeDecodeError):
        continue
    if os.path.basename(command) in {'bash', 'zsh', 'fish'} and working_directory.startswith('/home/user'):
        candidates.append(working_directory)
print(json.dumps(sorted(set(candidates))))
""".strip()
    try:
        response = controller.execute_python_command(code)
        output = str(response.get("output", "")).strip().splitlines()
        candidates = json.loads(output[-1]) if output else []
    except (AttributeError, IndexError, json.JSONDecodeError, TypeError, ValueError):
        return None
    valid = [
        path
        for path in candidates
        if isinstance(path, str) and path.startswith("/home/user")
    ]
    non_home = [path for path in valid if path != "/home/user"]
    return max(non_home or valid, key=len, default=None)


def prepare_guest_setup_dependencies(
    controller: Any, example: dict[str, Any]
) -> dict[str, Any]:
    setup_text = json.dumps(example.get("config", []), ensure_ascii=True).lower()
    required = ["jq"] if re.search(r"\bjq\b", setup_text) else []
    if re.search(r"\bsar\b", str(example.get("instruction", "")), re.IGNORECASE):
        required.append("sar")
    if not required:
        return {"required": [], "prepared": []}
    code = "required = " + repr(required) + "\n" + r"""
import json
import shutil
import subprocess


def sudo(command):
    return subprocess.run(
        ["sudo", "-S", *command],
        input="password\n",
        text=True,
        capture_output=True,
        timeout=180,
    )


sudo(["systemctl", "stop", "packagekit.service", "packagekit.socket"])
sudo(["systemctl", "mask", "--runtime", "packagekit.service", "packagekit.socket"])
attempts = []
missing = [name for name in required if shutil.which(name) is None]
if missing:
    update = sudo(["apt-get", "-o", "DPkg::Lock::Timeout=90", "update"])
    install = sudo(
        ["apt-get", "-o", "DPkg::Lock::Timeout=90", "install", "-y", *["sysstat" if name == "sar" else name for name in missing]]
    )
    attempts.extend(
        [
            {"operation": "apt-get update", "returncode": update.returncode},
            {"operation": "apt-get install " + " ".join(missing), "returncode": install.returncode},
        ]
    )
print(
    json.dumps(
        {
            "required": required,
            "prepared": [name for name in required if shutil.which(name)],
            "attempts": attempts,
        }
    )
)
""".strip()
    response = controller.execute_python_command(code)
    output = str(response.get("output", "")).strip().splitlines()
    try:
        result = json.loads(output[-1]) if output else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"failed to parse guest dependency result: {response}"
        ) from exc
    if result.get("prepared") != required:
        raise RuntimeError(f"failed to prepare guest dependencies {required}: {result}")
    return result


def _openapi_urls(base_url: str) -> tuple[str, ...]:
    parsed = urlsplit(base_url)
    origin = (
        f"{parsed.scheme}://{parsed.netloc}"
        if parsed.scheme and parsed.netloc
        else base_url.rstrip("/")
    )
    candidates = [f"{origin}/openapi.json"]
    endpoint_candidate = f"{base_url.rstrip('/')}/openapi.json"
    if endpoint_candidate not in candidates:
        candidates.append(endpoint_candidate)
    return tuple(candidates)


def _fetch_openapi_document(
    base_url: str,
    api_key: str,
    *,
    http_client: Any | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    import httpx

    client = http_client
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=15, trust_env=False)
    try:
        for url in _openapi_urls(base_url):
            try:
                response = client.get(
                    url,
                    headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
                )
            except (httpx.HTTPError, OSError):
                continue
            if response.status_code != 200:
                continue
            try:
                payload = response.json()
            except (ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                return payload, url
    finally:
        if owns_client:
            client.close()
    return None, None


def model_preflight(
    base_url: str,
    api_key: str,
    model: str,
    *,
    reasoning_effort: str | None = None,
    reasoning_mode: str | None = None,
    reasoning_profile: str | None = None,
    expected_root: str | None = None,
    http_client: Any | None = None,
) -> dict[str, Any]:
    import httpx
    from openai import OpenAI

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
        http_client=httpx.Client(timeout=30, trust_env=False),
    )
    available = client.models.list()
    match = next((item for item in available.data if item.id == model), None)
    if match is None:
        raise RuntimeError(
            f"model {model!r} is not served; available={[item.id for item in available.data]}"
        )
    result = match.model_dump(mode="json", exclude_none=True)
    if expected_root is not None and result.get("root") != expected_root:
        result["reasoning_gate"] = {
            "verified": False,
            "reason": "served model root does not match frozen condition",
            "requested": reasoning_effort,
            "requested_mode": reasoning_mode,
            "effective": None,
        }
        return result
    if reasoning_effort is not None and reasoning_mode is not None:
        raise RuntimeError(
            "reasoning_effort and reasoning_mode cannot both be configured"
        )
    if reasoning_mode is not None:
        if reasoning_mode not in SUPPORTED_REASONING_MODES:
            result["reasoning_gate"] = {
                "verified": False,
                "reason": "requested reasoning mode is outside the binary vocabulary",
                "requested_mode": reasoning_mode,
                "effective": None,
            }
            return result
        # Qwen3.5's public contract is the chat-template boolean.  The
        # OpenAI-compatible reasoning_effort enum is not a capability signal
        # for this profile, so only model identity and the frozen profile are
        # checked before the first task request.  Each response is validated
        # by StructuredToolModelClient and fills in effective_mode below.
        openapi, openapi_url = _fetch_openapi_document(
            base_url,
            api_key,
            http_client=http_client,
        )
        effective = explicit_effective_reasoning_mode(result)
        effective = effective if effective in SUPPORTED_REASONING_MODES else None
        profile_supported = reasoning_profile in {
            "qwen35_thinking_switch",
            "binary_thinking_switch",
        }
        if reasoning_profile is None:
            # Keep direct callers compatible while still requiring a matching
            # Qwen3.5 identity before accepting the binary profile.
            profile_supported = model.casefold().replace("-", "") in {
                "qwen3.54b",
                "qwen35-4b",
            } or str(result.get("root", "")).casefold().startswith("qwen/qwen3.5")
        profile_name = reasoning_profile or (
            "qwen35_thinking_switch" if profile_supported else None
        )
        # Some Qwen3.5 llama.cpp gateways intentionally omit OpenAPI
        # metadata while still exposing the model identity and accepting the
        # native binary thinking switch. The response-side model client
        # remains the source of truth for the effective mode; requiring an
        # OpenAPI document here would reject an otherwise usable multimodal
        # endpoint before the first task request.
        model_identity = str(result.get("id") or model).casefold()
        qwen35_identity = (
            model_identity.replace("-", "").replace("_", "").replace(".", "")
            .startswith("qwen35")
        )
        reasoning_preflight_verified = bool(
            profile_supported and (openapi is not None or qwen35_identity)
        )
        result["reasoning_gate"] = {
            # ``verified`` means the model identity and its binary thinking
            # profile passed preflight.  Qwen3.5 has no numeric maximum to
            # compare here; the request-side boolean is sent explicitly and
            # the response observation is recorded by the model client.
            "verified": reasoning_preflight_verified,
            "preflight_verified": reasoning_preflight_verified,
            "effective_verified": (
                effective == reasoning_mode if effective is not None else None
            ),
            "verification_pending": effective is None,
            "profile": profile_name,
            "control": "extra_body.chat_template_kwargs.enable_thinking",
            "requested_mode": reasoning_mode,
            "supported_modes": list(SUPPORTED_REASONING_MODES),
            "supported_by_provider_profile": profile_supported,
            "effective": effective,
            "effective_source": "model_metadata" if effective else None,
            "effective_observation": (
                "response.message.reasoning_or_reasoning_content"
                " (binary observation; not a numeric effort tier)"
            ),
            "numeric_effort_supported": False,
            "openapi_url": openapi_url,
        }
        return result
    if reasoning_effort is None:
        return result
    if reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
        result["reasoning_gate"] = {
            "verified": False,
            "reason": "requested effort is outside the supported vocabulary",
            "requested": reasoning_effort,
            "effective": None,
        }
        return result

    openapi, openapi_url = _fetch_openapi_document(
        base_url,
        api_key,
        http_client=http_client,
    )
    supported_values = extract_reasoning_effort_enum(openapi)
    effective = explicit_effective_reasoning_mode(result)
    result["reasoning_gate"] = {
        "verified": bool(
            openapi is not None
            and reasoning_effort in supported_values
            and effective == reasoning_effort
        ),
        "requested": reasoning_effort,
        "supported_values": list(supported_values),
        "supported_by_openapi": reasoning_effort in supported_values,
        "effective": effective,
        "effective_source": "model_metadata" if effective else None,
        "openapi_url": openapi_url,
    }
    return result


def path_class(state: RuntimeState) -> str:
    successful = state.successful_adapter_events()
    used_gui = any(
        event.executed and event.proposed.get("kind") == "gui" for event in state.events
    )
    attempted_adapter = any(
        event.proposed.get("kind") == "adapter" for event in state.events
    )
    if used_gui and (successful or attempted_adapter):
        return "api_plus_gui"
    if used_gui:
        return "gui_only"
    return "generic_api_only"


def osworld_terminal_action(stop_reason: str) -> str | None:
    """Map only explicit Agent decisions to OSWorld terminal actions."""
    if stop_reason == "agent_done":
        return "DONE"
    if stop_reason == "agent_failed":
        return "FAIL"
    return None


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


class ConfigSnapshotError(RuntimeError):
    """The worker config bytes do not match their expected immutable digest."""

    def __init__(self, message: str, evidence: dict[str, Any]) -> None:
        super().__init__(message)
        self.evidence = evidence


class GuiModelPreflightError(RuntimeError):
    """The frozen GUI model endpoint failed its model-free identity gate."""

    def __init__(self, message: str, snapshot: dict[str, Any]) -> None:
        super().__init__(message)
        self.snapshot = snapshot


def config_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_config_snapshot(
    path: Path,
    *,
    expected_sha256: str | None,
    phase: str,
    previous_sha256: str | None = None,
    require_expected: bool = False,
) -> dict[str, Any]:
    """Verify immutable config bytes without parsing or trusting their content."""
    observed = config_file_sha256(path)
    evidence = {
        "phase": phase,
        "path": str(path),
        "expected_sha256": expected_sha256,
        "previous_sha256": previous_sha256,
        "observed_sha256": observed,
        "verified": False,
    }
    if require_expected and expected_sha256 is None:
        raise ConfigSnapshotError(
            "promotion worker requires --expected-config-sha256",
            evidence,
        )
    if expected_sha256 is not None and not re.fullmatch(
        r"[0-9a-f]{64}", expected_sha256
    ):
        raise ConfigSnapshotError(
            "expected config SHA-256 must be 64 lowercase hexadecimal characters",
            evidence,
        )
    if expected_sha256 is not None and observed != expected_sha256:
        raise ConfigSnapshotError(
            "worker config bytes do not match --expected-config-sha256",
            evidence,
        )
    if previous_sha256 is not None and observed != previous_sha256:
        raise ConfigSnapshotError(
            "worker config bytes changed after the initial snapshot gate",
            evidence,
        )
    evidence["verified"] = True
    return evidence


def write_invalid_configuration_result(
    result_dir: Path,
    *,
    config_path: Path,
    model: str,
    base_url: str,
    reasoning_effort: str | None,
    reason: str,
    reasoning_mode: str | None = None,
    model_preflight_result: dict[str, Any] | None = None,
    gui_model_preflight_result: dict[str, Any] | None = None,
    config_integrity: dict[str, Any] | None = None,
) -> None:
    """Persist a non-scored gate failure without starting a VM or task.

    Configuration failures are evidence about the condition, not an
    environment failure and not a task result.  Keeping a small result file
    makes supervisor aggregation and later audits classify it correctly.
    """
    result_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "status": "invalid_configuration",
        "reason": reason,
        "agent_framework": "LiteAgent",
        "model_requested": model,
        "base_url": base_url,
        "reasoning_effort": reasoning_effort,
        "reasoning_mode": reasoning_mode,
        "model_preflight": model_preflight_result,
        "gui_model_preflight": gui_model_preflight_result,
        "config_integrity": config_integrity,
        "config": str(config_path),
        "config_sha256": config_file_sha256(config_path),
        "tasks_started": 0,
        "started_at": utc_now(),
        "completed_at": utc_now(),
    }
    write_json(result_dir / "metadata.json", metadata)
    write_json(result_dir / "results.json", {"metadata": metadata, "tasks": []})


def persist_invalid_configuration(
    args: argparse.Namespace,
    reason: str,
    *,
    model_preflight_result: dict[str, Any] | None = None,
    gui_model_preflight_result: dict[str, Any] | None = None,
    config_integrity: dict[str, Any] | None = None,
) -> None:
    write_invalid_configuration_result(
        args.result_dir,
        config_path=args.config,
        model=args.model,
        base_url=args.base_url,
        reasoning_effort=getattr(args, "reasoning_effort", None),
        reasoning_mode=getattr(args, "reasoning_mode", None),
        reason=reason,
        model_preflight_result=model_preflight_result,
        gui_model_preflight_result=gui_model_preflight_result,
        config_integrity=config_integrity,
    )
    print(
        json.dumps(
            {
                "status": "invalid_configuration",
                "reason": reason,
                "result_dir": str(args.result_dir),
            },
            ensure_ascii=False,
        )
    )


def model_preflight_failure(
    exc: BaseException,
    *,
    model: str,
    base_url: str,
    reasoning_effort: str | None,
    reasoning_mode: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Turn a pre-model endpoint failure into auditable gate evidence.

    A failed ``/v1/models`` or OpenAPI request is not a task/environment
    outcome.  Returning a bounded snapshot lets the caller persist an
    ``invalid_configuration`` condition while retaining enough detail to
    distinguish an unavailable endpoint from an unsupported reasoning mode.
    """
    detail = str(exc).strip() or type(exc).__name__
    # Exception text should not be allowed to grow an artifact indefinitely.
    detail = detail[:1_000]
    reason = f"model preflight failed ({type(exc).__name__}): {detail}"
    snapshot = {
        "status": "error",
        "model_requested": model,
        "base_url": base_url,
        "reasoning_mode": reasoning_mode,
        "error": {"type": type(exc).__name__, "detail": detail},
        "reasoning_gate": {
            "verified": False,
            "reason": "model endpoint preflight did not complete",
            "requested": reasoning_effort,
            "requested_mode": reasoning_mode,
            "effective": None,
        },
    }
    return snapshot, reason


def write_model_request_artifact(
    task_dir: Path,
    *,
    request_index: int,
    step_num: int,
    attempt: int,
    screenshot: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    relative_path = Path("llm_requests") / (
        f"request_{request_index:04d}_step_{step_num:03d}_attempt_{attempt}.json"
    )
    path = task_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical_request = json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    # Templates can expose schema property order. Keep it in the artifact;
    # retain the separate canonical digest for existing semantic audit joins.
    artifact = json.dumps(request, ensure_ascii=False, default=str).encode("utf-8") + b"\n"
    path.write_bytes(artifact)
    return {
        "request_index": request_index,
        "step_num": step_num,
        "attempt": attempt,
        "screenshot": screenshot,
        "path": relative_path.as_posix(),
        "canonical_request_sha256": hashlib.sha256(canonical_request).hexdigest(),
        "artifact_sha256": hashlib.sha256(artifact).hexdigest(),
        "bytes": len(artifact),
        "timestamp_utc": utc_now(),
    }


def screenshot_path(task_dir: Path, step: int, phase: str) -> Path:
    return task_dir / f"step_{step:03d}_{phase}.png"


class ScreenshotObservationError(RuntimeError):
    pass


class ModelRequestFailure(RuntimeError):
    """All model attempts for one step failed before a proposal was returned."""

    def __init__(
        self,
        errors: list[dict[str, Any]],
        *,
        protocol_failure: bool,
        deadline_exhausted: bool = False,
        configuration_failure: bool = False,
    ) -> None:
        self.errors = errors
        self.protocol_failure = protocol_failure
        self.deadline_exhausted = deadline_exhausted
        self.configuration_failure = configuration_failure
        super().__init__(
            f"model request failed after {len(errors)} attempts"
            + (" (structured protocol)" if protocol_failure else "")
            + (" (configuration)" if configuration_failure else "")
            + (" (episode deadline)" if deadline_exhausted else "")
        )


def protocol_recovery_after_error(
    previous: bool,
    exc: BaseException,
) -> bool:
    """Keep compact protocol recovery active for the rest of the retry cycle."""
    return (
        previous
        or isinstance(exc, StructuredToolProtocolError)
        or "structured tool call" in str(exc)
    )


def classify_runner_exception(
    phase: str,
    exc: BaseException,
    state: RuntimeState,
) -> tuple[str, str]:
    """Classify failures without folding agent/model failures into the VM bucket."""
    if isinstance(exc, ModelRequestFailure):
        if exc.configuration_failure:
            return "invalid_configuration", "invalid_configuration"
        if exc.deadline_exhausted:
            return "agent_deadline_exhausted", path_class(state)
        status = (
            "model_protocol_failure"
            if exc.protocol_failure
            else "model_transport_failure"
        )
        return status, path_class(state)
    if phase == "agent":
        return "agent_failure", path_class(state)
    if phase == "evaluation":
        return "evaluation_failure", path_class(state)
    return "environment_failure", "environment_failure"


def require_observation_screenshot(
    env: Any,
    observation: Any,
    *,
    description: str,
    attempts: int = OBSERVATION_SCREENSHOT_ATTEMPTS,
    retry_seconds: float = OBSERVATION_SCREENSHOT_RETRY_SECONDS,
) -> dict[str, Any]:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    observed: list[dict[str, Any]] = []
    current = observation
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            try:
                current = env._get_obs()
            except Exception as exc:
                observed.append(
                    {
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                current = None
        screenshot = current.get("screenshot") if isinstance(current, dict) else None
        if isinstance(screenshot, (bytes, bytearray, memoryview)) and screenshot:
            normalized = dict(current)
            normalized["screenshot"] = bytes(screenshot)
            return normalized
        observed.append(
            {
                "attempt": attempt,
                "observation_type": type(current).__name__,
                "screenshot_type": type(screenshot).__name__,
            }
        )
        if attempt < attempts:
            time.sleep(retry_seconds)
    raise ScreenshotObservationError(
        f"{description} did not provide screenshot bytes after {attempts} attempts: "
        f"{observed}"
    )


def _holo_model_settings(
    args: argparse.Namespace, config: dict[str, Any]
) -> dict[str, Any] | None:
    """Resolve the optional primary-to-Holo GUI model configuration.

    Holo is opt-in: an ordinary LiteAgent run keeps the direct GUI fallback.
    The settings may live in the protocol's ``gui_model`` block so a frozen
    condition can describe the full two-model path, while explicit CLI values
    remain useful for a local smoke test.  No endpoint is contacted when the
    base URL is absent.
    """
    protocol = config.get("protocol", {})
    model = config.get("model", {})
    protocol = protocol if isinstance(protocol, dict) else {}
    model = model if isinstance(model, dict) else {}
    configured = protocol.get("gui_model") or model.get("gui_model")
    if not isinstance(configured, dict):
        configured = {}
    base_url = getattr(args, "holo_base_url", None) or configured.get("base_url")
    if configured.get("endpoint_assignment") == "paired_with_primary":
        primary_url = getattr(args, "base_url", None)
        if primary_url not in configured.get("base_urls", []):
            raise ValueError("primary endpoint is outside the paired Holo endpoints")
        if base_url is not None and base_url != primary_url:
            raise ValueError("paired Holo endpoint must match the worker primary endpoint")
        base_url = primary_url
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    model_name = (
        getattr(args, "holo_model", None) or configured.get("model") or "holo3.1-4b"
    )
    api_key = (
        getattr(args, "holo_api_key", None)
        or configured.get("api_key")
        or os.getenv("HOLO_API_KEY", "EMPTY")
    )
    reasoning_mode = getattr(args, "holo_reasoning_mode", None) or configured.get(
        "reasoning_mode"
    )
    reasoning_effort = (
        None
        if reasoning_mode is not None
        else (
            getattr(args, "holo_reasoning_effort", None)
            or configured.get("reasoning_effort")
            or "medium"
        )
    )
    timeout = getattr(args, "holo_request_timeout", None)
    if timeout is None:
        timeout = configured.get("request_timeout_seconds", 180.0)
    max_output_tokens = getattr(args, "holo_max_output_tokens", None)
    if max_output_tokens is None:
        max_output_tokens = configured.get("max_output_tokens", 1024)
    temperature = getattr(args, "holo_temperature", None)
    if temperature is None:
        temperature = configured.get("temperature", 0.8)
    accepted_actual_models = configured.get("accepted_actual_models")
    if accepted_actual_models is None:
        accepted_actual_models = [model_name]
    if (
        not isinstance(accepted_actual_models, list)
        or not accepted_actual_models
        or any(
            not isinstance(value, str) or not value.strip()
            for value in accepted_actual_models
        )
    ):
        raise ValueError(
            "Holo GUI model accepted_actual_models must be a non-empty string list"
        )
    expected_model_root = configured.get("served_root")
    if expected_model_root is not None and (
        not isinstance(expected_model_root, str) or not expected_model_root.strip()
    ):
        raise ValueError("Holo GUI model served_root must be a non-empty string")
    reasoning_profile = configured.get("reasoning_profile")
    if reasoning_profile is not None and (
        not isinstance(reasoning_profile, str) or not reasoning_profile.strip()
    ):
        raise ValueError("Holo GUI model reasoning_profile must be a non-empty string")
    try:
        timeout = float(timeout)
        max_output_tokens = int(max_output_tokens)
        temperature = float(temperature)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid Holo GUI model numeric setting") from exc
    if timeout <= 0 or max_output_tokens <= 0 or temperature < 0:
        raise ValueError("Holo GUI model settings must be positive")
    return {
        "base_url": base_url.strip(),
        "model": str(model_name),
        "api_key": str(api_key),
        "reasoning_effort": (
            str(reasoning_effort) if reasoning_effort is not None else None
        ),
        "reasoning_mode": (str(reasoning_mode) if reasoning_mode is not None else None),
        "reasoning_profile": reasoning_profile,
        "expected_model_root": expected_model_root,
        "accepted_actual_models": tuple(accepted_actual_models),
        "request_timeout_seconds": timeout,
        "max_output_tokens": max_output_tokens,
        "temperature": temperature,
    }


def gui_model_preflight(
    settings: dict[str, Any],
    *,
    preflight_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify a frozen GUI endpoint using only model listing and OpenAPI."""
    probe = preflight_fn or model_preflight
    raw = probe(
        settings["base_url"],
        settings["api_key"],
        settings["model"],
        reasoning_effort=settings.get("reasoning_effort"),
        reasoning_mode=settings.get("reasoning_mode"),
        reasoning_profile=settings.get("reasoning_profile"),
        expected_root=settings.get("expected_model_root"),
    )
    if not isinstance(raw, dict):
        raise GuiModelPreflightError(
            "GUI model preflight returned a non-object snapshot",
            {"status": "error", "result_type": type(raw).__name__},
        )
    snapshot = dict(raw)
    requested = settings["model"]
    expected_root = settings.get("expected_model_root")
    accepted_actual_models = list(settings.get("accepted_actual_models") or ())
    snapshot.update(
        {
            "status": "ok",
            "base_url": settings["base_url"],
            "model_requested": requested,
            "expected_model_root": expected_root,
            "accepted_actual_models": accepted_actual_models,
            "preflight_scope": ["models", "openapi"],
            "inference_request_sent": False,
        }
    )

    observed_id = snapshot.get("id")
    observed_root = snapshot.get("root")
    identity_verified = observed_id == requested and (
        expected_root is None or observed_root == expected_root
    )
    snapshot["identity_gate"] = {
        "verified": identity_verified,
        "model_requested": requested,
        "model_observed": observed_id,
        "root_expected": expected_root,
        "root_observed": observed_root,
    }
    if not identity_verified:
        snapshot["status"] = "error"
        raise GuiModelPreflightError(
            "GUI model identity does not match the frozen condition",
            snapshot,
        )

    reasoning_gate = snapshot.get("reasoning_gate")
    requested_mode = settings.get("reasoning_mode")
    requested_effort = settings.get("reasoning_effort")
    reasoning_profile = settings.get("reasoning_profile")
    if requested_mode is not None or requested_effort is not None:
        verified = (
            isinstance(reasoning_gate, dict) and reasoning_gate.get("verified") is True
        )
        if requested_mode is not None:
            verified = bool(
                verified and reasoning_gate.get("requested_mode") == requested_mode
            )
        if reasoning_profile is not None:
            verified = bool(
                verified and reasoning_gate.get("profile") == reasoning_profile
            )
        if not verified:
            snapshot["status"] = "error"
            raise GuiModelPreflightError(
                "GUI model reasoning profile does not match the frozen condition",
                snapshot,
            )
    return snapshot


def run_task(
    *,
    task: dict[str, Any],
    example: dict[str, Any],
    task_config_path: Path,
    task_dir: Path,
    args: argparse.Namespace,
    config: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    from desktop_env.desktop_env import DesktopEnv

    started_at = utc_now()
    started = time.monotonic()
    env = None
    recording_started = False
    interrupted = False
    phase = "setup"
    if "evaluator" in example:
        raise RuntimeError("Agent phase received evaluator configuration")
    state = RuntimeState(
        task_id=task["task_id"],
        domain=task["domain"],
        instruction=example["instruction"],
        recommended_actions=[],
    )
    # Terminal control results are sent through one bounded Qwen audit turn
    # before the Runner allows the episode to finish.  The default behavior of
    # direct LiteAgent callers remains unchanged.
    state.defer_terminal_audit = True
    record: dict[str, Any] = {
        "order": task["order"],
        "task_id": task["task_id"],
        "domain": task["domain"],
        "status": "environment_failure",
        "reward": None,
        "path_class": "environment_failure",
        "proxy_enabled": should_enable_guest_proxy(config, example),
        "dataset_proxy_requested": bool(example.get("proxy", False)),
        "evaluation_boundary": {
            "agent_task_keys": sorted(example),
            "evaluator_loaded_before_agent": False,
            "evaluator_loaded_after_agent": False,
        },
    }
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "original_instruction.txt").write_text(
        example["instruction"], encoding="utf-8"
    )
    adapter_trace = task_dir / "adapter_calls.jsonl"
    gui_trace = task_dir / "gui_calls.jsonl"
    holo_trace = task_dir / "holo_grounding_calls.jsonl"
    event_trace = task_dir / "lite_agent_events.jsonl"
    model_audit_trace = task_dir / "model_audits.jsonl"
    llm_trace = task_dir / "llm_call_log.jsonl"
    llm_request_index = task_dir / "llm_request_index.jsonl"
    office_recovery_trace = task_dir / "office_environment_recovery.jsonl"

    try:
        prefetch_resources(
            task["task_id"],
            setup_cache_resources(example),
            DEFAULT_CACHE_DIR,
        )
        env = DesktopEnv(
            path_to_vm=str(args.qcow2),
            action_space="pyautogui",
            provider_name="docker",
            screen_size=(args.screen_width, args.screen_height),
            headless=True,
            os_type="Ubuntu",
            require_a11y_tree=False,
            enable_proxy=should_enable_guest_proxy(config, example),
            client_password="password",
            cache_dir=str(DEFAULT_CACHE_DIR),
        )
        adapter_urls = deploy_generic_stack(env, task["domain"])
        record["generic_guest_sanitization"] = sanitize_generic_guest_deployment(
            env.controller
        )
        record["guest_setup_dependencies"] = prepare_guest_setup_dependencies(
            env.controller,
            example,
        )
        install_post_reset_prepare(env, task["domain"], adapter_urls)
        observation = env.reset(task_config=reset_task_config(example))
        if not hasattr(env.provider, "assert_agent_egress_policy"):
            raise RuntimeError("strict OSWorld provider has no guest egress boundary")
        record["agent_egress_policy"] = env.provider.assert_agent_egress_policy()
        time.sleep(args.initial_settle_seconds)
        observation = require_observation_screenshot(
            env,
            env._get_obs(),
            description="initial observation",
        )
        record["generic_guest_pre_model_sanitization"] = (
            sanitize_generic_guest_deployment(env.controller)
        )
        guest_inventory = capture_generic_guest_inventory(env.controller)
        guest_inventory_path = task_dir / "guest_file_inventory.json"
        write_json(guest_inventory_path, guest_inventory)
        inventory_bytes = guest_inventory_path.read_bytes()
        record["generic_guest_inventory"] = {
            "path": guest_inventory_path.name,
            "sha256": hashlib.sha256(inventory_bytes).hexdigest(),
            "package_roots": len(guest_inventory["packages"]),
            "existing_package_roots": sum(
                bool(package["exists"]) for package in guest_inventory["packages"]
            ),
            "files": sum(
                len(package["files"]) for package in guest_inventory["packages"]
            ),
        }
        env.controller.start_recording()
        recording_started = True
        state.working_directory = probe_terminal_working_directory(env.controller)
        record["terminal_working_directory"] = state.working_directory

        observation_box = {"value": observation}

        def gui_executor(arguments: dict[str, Any]) -> dict[str, Any]:
            append_jsonl(
                gui_trace,
                {
                    "step": len(state.events) + 1,
                    "timestamp_utc": utc_now(),
                    "arguments": {
                        key: value
                        for key, value in arguments.items()
                        if key != "command"
                    },
                    "command": arguments["command"],
                    "phase": "attempt",
                },
            )
            try:
                pause = float(arguments.get("seconds", args.action_settle_seconds))
                obs, _reward, _done, _info = env.step(arguments["command"], pause)
                observation_box["value"] = obs
                return {
                    "status": "ok",
                    "executed": True,
                    "result": {"environment_acknowledged": True},
                }
            except Exception as exc:
                return {
                    "status": "error",
                    "executed": False,
                    "error": {"type": type(exc).__name__, "detail": str(exc)},
                }

        # The text model remains the episode controller.  When the optional
        # Holo endpoint is configured, Qwen sees only ``gui_request`` and the
        # Holo gateway performs one screenshot-grounded GUI action.  The
        # callbacks preserve the host-only request/response/dispatch evidence;
        # the model-facing turn still receives only the sanitized action result.
        holo_gateway = None
        holo_settings = _holo_model_settings(args, config)
        if holo_settings is not None and not args.no_gui:

            def observe_holo_evidence(evidence: dict[str, Any]) -> None:
                append_jsonl(
                    holo_trace,
                    {
                        "step": len(state.events) + 1,
                        "timestamp_utc": utc_now(),
                        **evidence,
                    },
                )

            holo_agent = HoloGroundingAgent(
                HoloGroundingConfig(**holo_settings),
                evidence_observer=observe_holo_evidence,
            )
            holo_gateway = HoloGuiGateway(
                holo_agent,
                gui_executor,
                default_settle_seconds=args.action_settle_seconds,
                execution_observer=observe_holo_evidence,
            )
            record["gui_model"] = {
                "provider": "holo",
                "model_requested": holo_settings["model"],
                "base_url": holo_settings["base_url"],
                "reasoning_effort_requested": holo_settings["reasoning_effort"],
                "reasoning_mode_requested": holo_settings["reasoning_mode"],
                "delegation_tool": "gui_request",
                "trace": holo_trace.name,
            }
        else:
            record["gui_model"] = {
                "provider": "direct_gui" if not args.no_gui else "disabled",
                "delegation_tool": None,
            }

        lite_config = LiteAgentConfig(
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            top_k_actions=args.top_k,
            include_gui=not args.no_gui,
            enable_thinking=args.thinking,
            reasoning_effort=args.reasoning_effort,
            reasoning_mode=getattr(args, "reasoning_mode", None),
            max_output_tokens=args.max_output_tokens,
            temperature=args.temperature,
            presence_penalty=config.get("protocol", {}).get("presence_penalty"),
            thinking_token_budget=config.get("protocol", {}).get("thinking_token_budget"),
            tool_call_stop_sequence=config.get("protocol", {}).get("tool_call_stop_sequence"),
            request_timeout_seconds=args.request_timeout,
        )
        request_context = {"step_num": 0, "attempt": 0, "screenshot": ""}
        request_count = 0

        def record_model_request(request: dict[str, Any]) -> None:
            nonlocal request_count
            request_count += 1
            evidence = write_model_request_artifact(
                task_dir,
                request_index=request_count,
                step_num=int(request_context["step_num"]),
                attempt=int(request_context["attempt"]),
                screenshot=str(request_context["screenshot"]),
                request=request,
            )
            append_jsonl(llm_request_index, evidence)

        agent = LiteAgent(
            lite_config,
            AdapterExecutor(
                adapter_urls,
                adapter_trace,
            ),
            gui_executor=None if args.no_gui else gui_executor,
            model_client=StructuredToolModelClient(
                base_url=lite_config.base_url,
                api_key=lite_config.api_key,
                request_timeout_seconds=lite_config.request_timeout_seconds,
                request_observer=record_model_request,
            ),
            holo_gui_gateway=holo_gateway,
        )
        selected = agent.selected_actions(state)
        agent_prompt = json.dumps(
            {
                "system": agent._system_message(state),
                "initial_tools": agent.tools(state),
            },
            indent=2,
            ensure_ascii=False,
        )
        agent.assert_agent_surface_safe(
            state,
            [{"role": "system", "content": agent._system_message(state)}],
            agent.tools(state),
        )
        record["pre_model_strict_process_boundary"] = assert_strict_process_boundary()
        (task_dir / "agent_prompt.txt").write_text(
            agent_prompt + "\n", encoding="utf-8"
        )
        record["initial_top_k_actions"] = selected
        record["tool_catalog_sha256"] = agent.tool_catalog_hash(state)

        initial_path = screenshot_path(task_dir, 0, "initial")
        initial_path.write_bytes(observation_box["value"]["screenshot"])

        phase = "agent"
        agent_loop_started = time.monotonic()
        agent.adapter_executor.deadline_monotonic = (
            agent_loop_started + args.max_agent_seconds
        )
        office_recoveries_attempted = 0
        # ``max_steps`` remains the immutable global episode budget.  A target
        # condition may additionally provide a smaller local budget so a
        # bounded same-VM soft restart can rebuild context and continue within
        # the same episode.  No VM reset occurs in this loop.
        local_step_limit = getattr(args, "max_local_steps", None) or args.max_steps
        soft_restart_limit = getattr(args, "max_soft_restarts", 1)
        total_steps = 0
        # A terminal Tool consumes one additional model turn for its audit.
        # Permit that bounded turn even when the normal Tool budget was just
        # exhausted; it does not create a VM reset or a second terminal event.
        terminal_audit_turns_remaining = 1
        while total_steps < args.max_steps or (
            isinstance(getattr(state, "pending_terminal", None), dict)
            and terminal_audit_turns_remaining > 0
        ):
            terminal_audit_turn = (
                isinstance(getattr(state, "pending_terminal", None), dict)
                and total_steps >= args.max_steps
                and terminal_audit_turns_remaining > 0
            )
            if terminal_audit_turn:
                terminal_audit_turns_remaining -= 1
            total_steps += 1
            step = total_steps
            state.local_step = max(1, int(getattr(state, "local_step", 1)))
            was_runner_replan = state.pending_runner_replan is not None
            before = observation_box["value"]
            before_path = screenshot_path(task_dir, step, "before")
            before_path.write_bytes(before["screenshot"])
            proposal = None
            errors = []
            protocol_recovery = False
            protocol_recovery_context = None
            protocol_failure_seen = False
            configuration_failure_seen = False
            deadline_exhausted = False
            for attempt in range(1, args.model_retries + 1):
                remaining_seconds = args.max_agent_seconds - (
                    time.monotonic() - agent_loop_started
                )
                if remaining_seconds <= 0:
                    deadline_exhausted = True
                    errors.append(
                        {
                            "attempt": attempt,
                            "type": "AgentDeadlineExceeded",
                            "detail": "episode budget expired before the next model request",
                            "timestamp_utc": utc_now(),
                        }
                    )
                    break
                request_context.update(
                    {
                        "step_num": step,
                        "attempt": attempt,
                        "screenshot": before_path.name,
                    }
                )
                try:
                    proposal = agent.propose(
                        state,
                        before["screenshot"],
                        protocol_recovery=protocol_recovery,
                        protocol_error=protocol_recovery_context,
                        request_timeout_seconds=min(
                            args.request_timeout,
                            max(0.1, remaining_seconds),
                        ),
                    )
                    break
                except Exception as exc:
                    detail = str(exc)
                    errors.append(
                        {
                            "attempt": attempt,
                            "type": type(exc).__name__,
                            "detail": detail,
                            "timestamp_utc": utc_now(),
                        }
                    )
                    if isinstance(exc, StructuredToolProtocolError):
                        protocol_failure_seen = True
                        configuration_failure_seen = exc.configuration_failure
                        errors[-1]["protocol"] = exc.trace_record()
                        protocol_recovery_context = {
                            "reason": exc.reason,
                            "tool": exc.tool_name,
                            "missing_fields": list(exc.missing_fields),
                            "schema_hints": list(exc.schema_hints),
                            "finish_reason": exc.response_snapshot.get(
                                "finish_reason"
                            ),
                            # The provider may deterministically replay the
                            # same malformed call when the recovery prompt is
                            # byte-for-byte identical.  Carry the retry ordinal
                            # into the next prompt so a repeated protocol
                            # failure gets an explicit, bounded replan cue.
                            "recovery_attempt": attempt,
                        }
                        if exc.configuration_failure:
                            # A provider-mode attestation failure invalidates
                            # the frozen condition.  Retrying cannot repair a
                            # condition-level mismatch and would issue more
                            # unqualified model requests.
                            break
                    # A prose-only response is not fixed by replaying the
                    # same large prompt.  Keep the bounded, tool-first
                    # projection active through later transport retries.
                    protocol_recovery = protocol_recovery_after_error(
                        protocol_recovery,
                        exc,
                    )
                    if attempt < args.model_retries:
                        sleep_seconds = min(
                            2**attempt,
                            8,
                            max(
                                0.0,
                                args.max_agent_seconds
                                - (time.monotonic() - agent_loop_started),
                            ),
                        )
                        if sleep_seconds <= 0:
                            deadline_exhausted = True
                            break
                        time.sleep(sleep_seconds)
            append_jsonl(
                llm_trace,
                {
                    "step_num": step,
                    "timestamp_utc": utc_now(),
                    "model": proposal.get("model_actual") if proposal else None,
                    "proposal": proposal,
                    "errors": errors,
                    "protocol_recovery": protocol_recovery if errors else False,
                    "screenshot": before_path.name,
                    "tool_catalog_sha256": agent.tool_catalog_hash(state),
                },
            )
            if proposal is None:
                if deadline_exhausted and isinstance(
                    getattr(state, "pending_terminal", None), dict
                ):
                    terminal = finalize_terminal_after_deadline(state)
                    if terminal is not None:
                        stop_reason = "agent_done" if state.done else "agent_failed"
                        record["terminal_audit"] = {
                            **terminal,
                            "review_step": step,
                        }
                        record["termination_reason"] = stop_reason
                        terminal_action = osworld_terminal_action(stop_reason)
                        if terminal_action is not None:
                            env.step(terminal_action, 0.1)
                        break
                raise ModelRequestFailure(
                    errors,
                    protocol_failure=protocol_failure_seen,
                    deadline_exhausted=deadline_exhausted,
                    configuration_failure=configuration_failure_seen,
                )

            # The previous Tool result (including a control Tool result) is
            # considered audited only after this complete Qwen call returns.
            # A failed model retry leaves the pending marker intact.  A
            # terminal result gets one special audit-only turn: confirming the
            # same terminal control commits it, while choosing another Tool
            # clears the pending terminal and proceeds normally.
            pending_terminal_before_audit = isinstance(
                getattr(state, "pending_terminal", None), dict
            )
            terminal_audit = (
                consume_terminal_audit(state, proposal)
                if pending_terminal_before_audit
                else None
            )
            if pending_terminal_before_audit and terminal_audit is None:
                raise ModelRequestFailure(
                    [
                        {
                            "type": "TerminalAuditInvariantError",
                            "detail": (
                                "terminal result was present without a pending "
                                "Tool-result audit marker"
                            ),
                            "timestamp_utc": utc_now(),
                        }
                    ],
                    protocol_failure=True,
                )
            audit_record = (
                terminal_audit.get("audit")
                if isinstance(terminal_audit, dict)
                else record_model_audit(state, proposal)
            )
            if audit_record is not None:
                audit_entry = {
                    **audit_record,
                    "requested_before_step": step,
                    "audit_only": bool(
                        isinstance(terminal_audit, dict)
                        and terminal_audit.get("terminal") is not None
                    ),
                }
                if isinstance(terminal_audit, dict):
                    audit_entry["terminal_confirmed"] = bool(
                        terminal_audit.get("confirmed")
                    )
                    if terminal_audit.get("terminal") is not None:
                        audit_entry["terminal"] = terminal_audit["terminal"]
                record.setdefault("model_audits", []).append(audit_entry)
                append_jsonl(
                    model_audit_trace,
                    {
                        "step": step,
                        "timestamp_utc": utc_now(),
                        **audit_entry,
                    },
                )

            if (
                isinstance(terminal_audit, dict)
                and terminal_audit.get("terminal") is not None
            ):
                # No second Tool is executed for an audit acknowledgement.
                # The existing terminal event is the sole VM-facing result;
                # final evaluation happens below after the normal final
                # screenshot capture.
                stop_reason = "agent_done" if state.done else "agent_failed"
                record["terminal_audit"] = {
                    **terminal_audit["terminal"],
                    "review_step": step,
                    "audit_only": True,
                }
                record["termination_reason"] = stop_reason
                terminal_action = osworld_terminal_action(stop_reason)
                if terminal_action is not None:
                    env.step(terminal_action, 0.1)
                break

            if terminal_audit_turn and isinstance(terminal_audit, dict):
                # The audit turn is allowed after the global Tool budget, but
                # a continuation selected from that turn is not.  Do not run
                # an extra VM mutation and then silently fall through to the
                # evaluator with no terminal state; record the bounded stop
                # explicitly instead.
                selected_tool = (
                    proposal.get("tool") if isinstance(proposal, dict) else None
                )
                record["terminal_audit"] = {
                    "review_step": step,
                    "audit_only": True,
                    "terminal_confirmed": False,
                    "selected_tool": selected_tool,
                    "budget_exhausted": True,
                }
                record["runner_termination"] = {
                    "type": "terminal_audit_continuation_budget_exhausted",
                    "limit_steps": args.max_steps,
                    "review_step": step,
                    "selected_tool": selected_tool,
                }
                record["termination_reason"] = (
                    "terminal_audit_continuation_budget_exhausted"
                )
                # ``FAIL`` is an explicit OSWorld episode boundary; the
                # original terminal Tool remains the only model-selected
                # terminal event in the ledger.
                terminal_action = osworld_terminal_action("agent_failed")
                if terminal_action is not None:
                    env.step(terminal_action, 0.1)
                break

            event = agent.execute_proposal(
                state,
                proposal,
                screenshot_before=before_path.name,
                screenshot=before["screenshot"],
            )
            event.local_step = state.local_step
            event.retry = state.retry
            mark_tool_result_for_audit(state, event)
            if was_runner_replan:
                state.pending_runner_replan = None
            recovery_failure = None
            decision = recovery_decision(
                domain=state.domain,
                events=state.events,
                recoveries_attempted=office_recoveries_attempted,
            )
            if decision.eligible:
                office_recoveries_attempted += 1
                recovery = recover_office_episode(
                    domain=state.domain,
                    adapter_url=adapter_urls[state.domain],
                    setup_steps=example.get("config", []),
                    setup_controller=env.setup_controller,
                    use_proxy=bool(
                        example.get("proxy", False)
                        and getattr(env, "enable_proxy", False)
                    ),
                    trigger_event=event,
                    recovery_ordinal=office_recoveries_attempted,
                )
                recovery["decision"] = {
                    "reason": decision.reason,
                    "evidence": decision.evidence,
                    "potentially_mutating_call_before_trigger": False,
                }
                append_jsonl(office_recovery_trace, recovery)
                record.setdefault("office_environment_recoveries", []).append(
                    {
                        "trace": office_recovery_trace.name,
                        "trigger_step": event.step,
                        "status": recovery["status"],
                        "model_action_replayed": False,
                    }
                )
                recovery_status = model_visible_recovery_status(recovery)
                if isinstance(event.error, dict):
                    event.error = {
                        **event.error,
                        "environment_recovery": recovery_status,
                    }
                else:
                    event.error = {
                        "original_error": event.error,
                        "environment_recovery": recovery_status,
                    }
                if recovery["status"] != "recovered":
                    recovery_failure = recovery
            if event.proposed.get("kind") == "adapter":
                time.sleep(args.action_settle_seconds)
                observation_box["value"] = env._get_obs()
            elif event.proposed.get("kind") in {"catalog", "completion", "failure"}:
                observation_box["value"] = env._get_obs()

            try:
                observation_box["value"] = require_observation_screenshot(
                    env,
                    observation_box["value"],
                    description=f"step {step} post-action observation",
                )
            except ScreenshotObservationError:
                write_event(event_trace, event)
                raise
            after_path = screenshot_path(task_dir, step, "after")
            after_path.write_bytes(observation_box["value"]["screenshot"])
            event.screenshot_after = after_path.name
            write_event(event_trace, event)
            if recovery_failure is not None:
                raise RuntimeError(
                    "Office environment recovery failed at "
                    f"{recovery_failure.get('failure_stage', 'unknown')}"
                )

            stop_reason = None
            stall = detect_no_progress_stall(
                state.events, window=args.max_no_progress_steps
            )
            elapsed_agent_seconds = time.monotonic() - agent_loop_started
            local_limit_reached = state.local_step >= int(local_step_limit)
            recovery_reason = (
                stall.get("reason")
                if isinstance(stall, dict)
                else ("local_step_limit" if local_limit_reached else None)
            )
            if (
                recovery_reason is not None
                and total_steps < args.max_steps
                and not state.done
                and not state.failed
                and not isinstance(getattr(state, "pending_terminal", None), dict)
            ):
                soft_restart = begin_same_vm_soft_restart(
                    state,
                    str(recovery_reason),
                    max_retries=int(soft_restart_limit),
                    trigger_step=event.step,
                )
                if soft_restart.accepted:
                    record.setdefault("runner_replans", []).append(
                        {
                            **(
                                stall
                                if isinstance(stall, dict)
                                else {
                                    "type": "local_step_limit",
                                    "reason": "local_step_limit",
                                    "window": int(local_step_limit),
                                }
                            ),
                            "requested_after_step": event.step,
                            "elapsed_agent_seconds": round(elapsed_agent_seconds, 3),
                            "retry": soft_restart.retry,
                            "preserve_vm": soft_restart.preserve_vm,
                            "summary": soft_restart.summary,
                        }
                    )
                    # Continue the same environment with a rebuilt model
                    # projection.  ``total_steps`` and the event ledger remain
                    # monotonic, so global budgets and evidence do not reset.
                    continue
                record["runner_termination"] = {
                    **(
                        stall
                        if isinstance(stall, dict)
                        else {
                            "type": "local_step_limit",
                            "reason": "local_step_limit",
                            "window": int(local_step_limit),
                        }
                    ),
                    "elapsed_agent_seconds": round(elapsed_agent_seconds, 3),
                    "retry": soft_restart.retry,
                    "soft_restart_limit": int(soft_restart_limit),
                    "summary": soft_restart.summary,
                }
                record["termination_reason"] = (
                    "stalled_no_progress" if stall is not None else "local_step_limit"
                )
                stop_reason = "stalled_no_progress"
            elif elapsed_agent_seconds >= args.max_agent_seconds and not isinstance(
                getattr(state, "pending_terminal", None), dict
            ):
                record["runner_termination"] = {
                    "type": "agent_loop_time_budget_exhausted",
                    "limit_seconds": args.max_agent_seconds,
                    "elapsed_agent_seconds": round(elapsed_agent_seconds, 3),
                }
                record["termination_reason"] = "agent_loop_time_budget_exhausted"
                stop_reason = "agent_loop_time_budget_exhausted"
            elif state.done:
                stop_reason = "agent_done"
            elif state.failed:
                stop_reason = "agent_failed"

            if (
                stop_reason is None
                and recovery_reason is None
                and not state.done
                and not state.failed
                and not isinstance(getattr(state, "pending_terminal", None), dict)
            ):
                advance_local_step(state)

            if stop_reason is not None:
                terminal_action = osworld_terminal_action(stop_reason)
                if terminal_action is not None:
                    env.step(terminal_action, 0.1)
                break

        record["episode_control"] = {
            "global_steps": total_steps,
            "local_step": state.local_step,
            "retry": state.retry,
            "soft_restart_count": state.soft_restart_count,
            "soft_restart_vm_policy": "preserve_current_vm",
            "model_audit_count": len(record.get("model_audits", [])),
            "model_audit_trace": model_audit_trace.name,
            "pending_model_audit": state.pending_model_audit,
        }
        phase = "post_agent"
        final_path = task_dir / "final.png"
        final_observation = require_observation_screenshot(
            env,
            env._get_obs(),
            description="final observation",
        )
        final_path.write_bytes(final_observation["screenshot"])
        time.sleep(args.evaluator_settle_seconds)
        phase = "evaluation"
        evaluator_example = load_evaluator_task_config(
            task_config_path,
            expected_task_id=task["task_id"],
            episode_finished=True,
        )
        prefetch_resources(
            task["task_id"],
            evaluator_cache_resources(evaluator_example),
            DEFAULT_CACHE_DIR,
        )
        attach_evaluator_after_episode(
            env,
            evaluator_example,
            episode_finished=True,
        )
        record["evaluation_boundary"]["evaluator_loaded_after_agent"] = True
        evaluator_file_fetch_retries = install_stable_evaluator_file_fetch(
            env.controller,
            attempts=args.evaluator_file_fetch_attempts,
            delay_seconds=args.evaluator_file_fetch_delay_seconds,
        )
        record["evaluator_file_fetch"] = {
            "policy": "retry_incomplete_zip_packaged_documents",
            "max_attempts": args.evaluator_file_fetch_attempts,
            "delay_seconds": args.evaluator_file_fetch_delay_seconds,
            "retry_events": evaluator_file_fetch_retries,
        }
        reward = float(env.evaluate())
        (task_dir / "result.txt").write_text(f"{reward}\n", encoding="utf-8")
        record.update(
            {
                "status": "passed" if reward == 1.0 else "failed",
                "reward": reward,
                "path_class": path_class(state),
                "steps": len(state.events),
                "completion_rejections": state.completion_rejections,
                "terminated_by_agent": state.done or state.failed,
            }
        )
        try:
            record["evaluator_evidence"] = capture_evaluator_evidence(
                env, evaluator_example, task_dir
            )
        except Exception as exc:
            record["evaluator_evidence_error"] = {
                "type": type(exc).__name__,
                "detail": str(exc),
            }
    except KeyboardInterrupt:
        interrupted = True
        record.update(
            {
                "status": "interrupted",
                "path_class": path_class(state),
                "steps": len(state.events),
                "completion_rejections": state.completion_rejections,
                "terminated_by_agent": state.done or state.failed,
                "error": {
                    "type": "KeyboardInterrupt",
                    "detail": "run interrupted by user; partial evidence was preserved",
                },
            }
        )
        (task_dir / "exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    except Exception as exc:
        failure_status, failure_path = classify_runner_exception(phase, exc, state)
        record.update(
            {
                "status": failure_status,
                "path_class": failure_path,
                "termination_reason": failure_status,
            }
        )
        record["error"] = {"type": type(exc).__name__, "detail": str(exc)}
        if isinstance(exc, ModelRequestFailure):
            record["model_request_errors"] = exc.errors
            if exc.configuration_failure:
                record["configuration_failure"] = True
        (task_dir / "exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    finally:
        if env is not None:
            if recording_started:
                try:
                    env.controller.end_recording(str(task_dir / "recording.mp4"))
                except KeyboardInterrupt:
                    interrupted = True
                    record["status"] = "interrupted"
                    record.setdefault(
                        "recording_error", "recording finalization interrupted by user"
                    )
                except Exception as exc:
                    record.setdefault("recording_error", str(exc))
            try:
                env.close()
            except KeyboardInterrupt:
                interrupted = True
                record["status"] = "interrupted"
                record.setdefault(
                    "cleanup_error", "environment cleanup interrupted by user"
                )
            except Exception as exc:
                record.setdefault("cleanup_error", str(exc))

    completed_at = utc_now()
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    episode_context = {
        "episode_id": os.environ.get("LITE_AGENT_EPISODE_ID"),
        "task_id": task["task_id"],
        "order": task["order"],
        "domain": task["domain"],
        "run_index": 1,
        "attempt_index": int(os.environ.get("LITE_AGENT_ATTEMPT_INDEX", "1")),
        "parent_episode_id": os.environ.get("LITE_AGENT_PARENT_EPISODE_ID"),
        "run_owner": os.environ.get("LITE_AGENT_RUN_OWNER"),
        "tool_catalog_sha256": record.get("tool_catalog_sha256"),
    }
    manifest = build_trajectory_manifest(
        task_dir,
        episode_context=episode_context,
        record=record,
        instruction=example["instruction"],
        agent_prompt=(task_dir / "agent_prompt.txt").read_text(encoding="utf-8")
        if (task_dir / "agent_prompt.txt").is_file()
        else "",
        model_requested=args.model,
        reasoning_effort=args.reasoning_effort or "unconfigured",
        reasoning_mode=getattr(args, "reasoning_mode", None),
        max_steps=args.max_steps,
        config_sha256=metadata["config_sha256"],
        coverage_sha256=None,
        osworld_commit=metadata["osworld_commit"],
        openapa_commit=config.get("openapa_commit", "not_used"),
        screen_size=metadata["screen_size"],
        grounding_coordinate_size=metadata["screen_size"],
        started_at=started_at,
        completed_at=completed_at,
        schema_version="lite_agent.osworld.trajectory.v1",
        agent_framework="LiteAgent",
        model_identifier_source="native OpenAI-compatible response.model",
    )
    manifest["agent"]["generation_config"] = {
        "max_output_tokens": args.max_output_tokens,
        "temperature": args.temperature,
        "top_k_actions": args.top_k,
        "thinking": args.thinking,
        "reasoning_effort": args.reasoning_effort,
        "reasoning_mode": getattr(args, "reasoning_mode", None),
        "gui_enabled": not args.no_gui,
    }
    write_manifest(task_dir, manifest)
    record["trajectory_manifest"] = str(task_dir / "trajectory_manifest.json")
    if interrupted:
        record["status"] = "interrupted"
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-config-sha256",
        default=None,
        help="Supervisor-observed immutable config digest.",
    )
    parser.add_argument(
        "--supervisor",
        type=Path,
        default=None,
        help="Supervisor entrypoint identity forwarded to the frozen worker gate.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--orders", type=int, nargs="+", default=None)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--max-local-steps",
        type=int,
        default=None,
        help="Optional per-plan step limit before a same-VM soft restart.",
    )
    parser.add_argument(
        "--max-soft-restarts",
        type=int,
        default=1,
        help="Bounded in-episode soft restarts; VM reset is never used for recovery.",
    )
    parser.add_argument(
        "--max-no-progress-steps",
        type=int,
        default=8,
        help="Stop a repeated rejection/search loop after this many no-progress events.",
    )
    parser.add_argument(
        "--max-agent-seconds",
        type=float,
        default=300.0,
        help="Hard wall-clock budget for the screenshot/tool loop of one task.",
    )
    parser.add_argument("--model", default=os.getenv("QWEN_MODEL", "qwen3.5-4b"))
    parser.add_argument(
        "--base-url", default=os.getenv("QWEN_BASE_URL", "http://192.168.0.138:8001/v1")
    )
    parser.add_argument("--api-key", default=os.getenv("QWEN_API_KEY", "EMPTY"))
    parser.add_argument("--top-k", type=int, default=7)
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument(
        "--reasoning-effort",
        choices=SUPPORTED_REASONING_EFFORTS,
        default=None,
        help="Legacy tiered-provider reasoning effort (not used by Qwen3.5).",
    )
    parser.add_argument(
        "--reasoning-mode",
        choices=SUPPORTED_REASONING_MODES,
        default=None,
        help="Binary provider mode, e.g. thinking for Qwen3.5.",
    )
    parser.add_argument(
        "--holo-base-url",
        default=os.getenv("HOLO_BASE_URL"),
        help="Optional Holo visual-grounding endpoint; enables delegated gui_request.",
    )
    parser.add_argument(
        "--holo-model",
        default=os.getenv("HOLO_MODEL"),
    )
    parser.add_argument(
        "--holo-api-key",
        default=os.getenv("HOLO_API_KEY", "EMPTY"),
    )
    parser.add_argument(
        "--holo-reasoning-effort",
        default=os.getenv("HOLO_REASONING_EFFORT"),
        help="Legacy Holo effort setting; ignored when --holo-reasoning-mode is set.",
    )
    parser.add_argument(
        "--holo-reasoning-mode",
        choices=SUPPORTED_REASONING_MODES,
        default=os.getenv("HOLO_REASONING_MODE"),
        help="Binary Holo thinking mode for providers without effort tiers.",
    )
    parser.add_argument(
        "--holo-max-output-tokens",
        type=int,
        default=1024,
    )
    parser.add_argument(
        "--holo-temperature",
        type=float,
        default=0.8,
    )
    parser.add_argument(
        "--holo-request-timeout",
        type=float,
        default=180.0,
    )
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--model-retries", type=int, default=3)
    parser.add_argument("--initial-settle-seconds", type=float, default=10.0)
    parser.add_argument("--action-settle-seconds", type=float, default=2.0)
    parser.add_argument("--evaluator-settle-seconds", type=float, default=5.0)
    parser.add_argument("--evaluator-file-fetch-attempts", type=int, default=3)
    parser.add_argument("--evaluator-file-fetch-delay-seconds", type=float, default=1.0)
    parser.add_argument("--screen-width", type=int, default=1920)
    parser.add_argument("--screen-height", type=int, default=1080)
    parser.add_argument("--qcow2", type=Path, default=DEFAULT_QCOW2)
    args = parser.parse_args()

    args.config = args.config.resolve()
    args.result_dir = args.result_dir.resolve()
    args.qcow2 = args.qcow2.resolve()
    if args.supervisor is not None:
        args.supervisor = args.supervisor.resolve()
    # These are observations made by the worker process itself, not values
    # accepted from the launcher.
    args.runner = Path(__file__).resolve()
    args.python = str(Path(sys.executable).resolve())
    if args.evaluator_file_fetch_attempts <= 0:
        parser.error("evaluator file fetch attempts must be positive")
    if args.evaluator_file_fetch_delay_seconds < 0:
        parser.error("evaluator file fetch delay must be non-negative")
    if args.max_no_progress_steps < 4:
        parser.error("max no-progress steps must be at least 4")
    if args.max_agent_seconds <= 0:
        parser.error("max agent seconds must be positive")
    if args.max_local_steps is not None and args.max_local_steps < 1:
        parser.error("max local steps must be positive")
    if args.max_soft_restarts < 0:
        parser.error("max soft restarts must be nonnegative")
    if args.holo_max_output_tokens <= 0:
        parser.error("Holo max output tokens must be positive")
    if args.holo_temperature < 0:
        parser.error("Holo temperature must be non-negative")
    if args.holo_request_timeout <= 0:
        parser.error("Holo request timeout must be positive")
    if not 1 <= args.top_k <= 12:
        raise ValueError("--top-k must be between 1 and 12")

    config_integrity: dict[str, Any] = {}
    try:
        pre_load_integrity = verify_config_snapshot(
            args.config,
            expected_sha256=args.expected_config_sha256,
            phase="pre_load",
        )
        config_integrity["pre_load"] = pre_load_integrity
    except ConfigSnapshotError as exc:
        config_integrity["pre_load"] = exc.evidence
        persist_invalid_configuration(
            args,
            f"config snapshot gate failed: {exc}",
            config_integrity=config_integrity,
        )
        return

    strict_process_boundary = assert_strict_process_boundary()
    os.chdir(OSWORLD_ROOT)
    configure_evaluator_runtime()
    config, tasks = load_tasks(
        args.config,
        args.limit,
        set(args.orders) if args.orders is not None else None,
    )
    condition = config.get("condition")
    promotion_gate_required = bool(
        isinstance(condition, dict) and _promotion_gate_required(config, condition)
    )
    try:
        config_integrity["post_load"] = verify_config_snapshot(
            args.config,
            expected_sha256=args.expected_config_sha256,
            previous_sha256=pre_load_integrity["observed_sha256"],
            require_expected=promotion_gate_required,
            phase="post_load",
        )
    except ConfigSnapshotError as exc:
        config_integrity["post_load"] = exc.evidence
        persist_invalid_configuration(
            args,
            f"config snapshot gate failed: {exc}",
            config_integrity=config_integrity,
        )
        return
    if args.reasoning_effort is None:
        args.reasoning_effort = config.get("protocol", {}).get("reasoning_effort")
    if getattr(args, "reasoning_mode", None) is None:
        args.reasoning_mode = config.get("protocol", {}).get("reasoning_mode")
    if config.get("protocol", {}).get("task_specific_or_golden_exposed", False):
        raise ValueError(
            "LiteAgent strict Runner rejects task-specific or golden-enabled configs"
        )
    try:
        frozen_condition = enforce_runner_condition(config, args, PROJECT_ROOT)
    except (RuntimeError, ValueError) as exc:
        # Condition errors are non-scored configuration evidence.  Persist the
        # classification before returning so a supervisor cannot mistake a
        # rejected gate for a VM or model environment failure.
        reason = f"condition gate failed: {exc}"
        persist_invalid_configuration(
            args,
            reason,
            config_integrity=config_integrity,
        )
        return
    try:
        model_info = model_preflight(
            args.base_url,
            args.api_key,
            args.model,
            reasoning_effort=args.reasoning_effort,
            reasoning_mode=args.reasoning_mode,
            reasoning_profile=config.get("model", {}).get("reasoning_profile"),
            expected_root=config.get("model", {}).get("served_root"),
        )
    except Exception as exc:
        model_info, reason = model_preflight_failure(
            exc,
            model=args.model,
            base_url=args.base_url,
            reasoning_effort=args.reasoning_effort,
            reasoning_mode=args.reasoning_mode,
        )
        persist_invalid_configuration(
            args,
            reason,
            model_preflight_result=model_info,
            config_integrity=config_integrity,
        )
        return
    reasoning_gate = model_info.get("reasoning_gate")
    if (args.reasoning_effort is not None or args.reasoning_mode is not None) and (
        not isinstance(reasoning_gate, dict)
        or reasoning_gate.get("verified") is not True
    ):
        reason = (
            reasoning_gate.get("reason")
            if isinstance(reasoning_gate, dict)
            else "provider did not expose verifiable effective reasoning mode"
        )
        persist_invalid_configuration(
            args,
            f"reasoning gate failed: {reason}",
            model_preflight_result=model_info,
            config_integrity=config_integrity,
        )
        return

    holo_settings: dict[str, Any] | None = None
    gui_model_info: dict[str, Any] | None = None
    try:
        holo_settings = _holo_model_settings(args, config)
        if holo_settings is not None:
            gui_model_info = gui_model_preflight(holo_settings)
    except Exception as exc:
        if isinstance(exc, GuiModelPreflightError):
            gui_model_info = exc.snapshot
            reason = f"GUI model preflight failed: {exc}"
        elif holo_settings is not None:
            gui_model_info, detail = model_preflight_failure(
                exc,
                model=holo_settings["model"],
                base_url=holo_settings["base_url"],
                reasoning_effort=holo_settings.get("reasoning_effort"),
                reasoning_mode=holo_settings.get("reasoning_mode"),
            )
            gui_model_info.update(
                {
                    "preflight_scope": ["models", "openapi"],
                    "inference_request_sent": False,
                }
            )
            reason = f"GUI {detail}"
        else:
            gui_model_info = {
                "status": "error",
                "preflight_scope": ["models", "openapi"],
                "inference_request_sent": False,
                "error": {"type": type(exc).__name__, "detail": str(exc)[:1_000]},
            }
            reason = f"GUI model configuration failed: {exc}"
        persist_invalid_configuration(
            args,
            reason,
            model_preflight_result=model_info,
            gui_model_preflight_result=gui_model_info,
            config_integrity=config_integrity,
        )
        return

    install_provider_patch()
    args.result_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "experiment_id": args.result_dir.name,
        "status": "running",
        "agent_framework": "LiteAgent",
        "model_requested": args.model,
        "model_preflight": model_info,
        "gui_model_preflight": gui_model_info,
        "base_url": args.base_url,
        "thinking": args.thinking,
        "reasoning_mode": args.reasoning_mode,
        "reasoning_effort": args.reasoning_effort,
        "top_k": args.top_k,
        "max_output_tokens": args.max_output_tokens,
        "temperature": args.temperature,
        "gui_enabled": not args.no_gui,
        "task_specific_or_golden_exposed": False,
        "strict_process_boundary": strict_process_boundary,
        "frozen_condition": frozen_condition,
        "agent_task_id_visible": False,
        "task_id_usage": "runner_internal_setup_evaluator_and_trace_only",
        "evaluator_isolation": (
            "agent_fields_projected_in_short_lived_process; evaluator loaded only after episode"
        ),
        "max_steps": args.max_steps,
        "max_local_steps": args.max_local_steps,
        "max_soft_restarts": args.max_soft_restarts,
        "max_no_progress_steps": args.max_no_progress_steps,
        "max_agent_seconds": args.max_agent_seconds,
        "screen_size": [args.screen_width, args.screen_height],
        "task_count": len(tasks),
        "task_order": [task["task_id"] for task in tasks],
        "osworld_commit": config["osworld_commit"],
        "config_sha256": pre_load_integrity["observed_sha256"],
        "config_integrity": config_integrity,
        "runner_entrypoint": str(args.runner),
        "python_entrypoint": args.python,
        "supervisor_entrypoint": (
            str(args.supervisor) if args.supervisor is not None else None
        ),
        "started_at": utc_now(),
    }
    write_json(args.result_dir / "metadata.json", metadata)
    results = []
    logging.basicConfig(
        level=logging.INFO, format="[%(asctime)s %(levelname)s] %(message)s"
    )
    for task in tasks:
        task_path = osworld_task_path(OSWORLD_ROOT, task)
        example = load_agent_task_config_isolated(
            task_path,
            expected_task_id=task["task_id"],
        )
        task_dir = (
            args.result_dir
            / "raw"
            / "run-1"
            / (f"{task['order']:02d}-{task['domain']}-{task['task_id']}")
        )
        result = run_task(
            task=task,
            example=example,
            task_config_path=task_path,
            task_dir=task_dir,
            args=args,
            config=config,
            metadata=metadata,
        )
        results.append(result)
        write_json(
            args.result_dir / "results.json", {"metadata": metadata, "tasks": results}
        )
        if args.api_key != "EMPTY":
            assert_secret_absent(task_dir, args.api_key)
        if result["status"] in {"interrupted", "invalid_configuration"}:
            break

    integrity_failure_reason: str | None = None
    try:
        config_integrity["final"] = verify_config_snapshot(
            args.config,
            expected_sha256=args.expected_config_sha256,
            previous_sha256=pre_load_integrity["observed_sha256"],
            require_expected=promotion_gate_required,
            phase="final",
        )
        frozen_condition_revalidation = enforce_runner_condition(
            config,
            args,
            PROJECT_ROOT,
        )
        metadata["integrity_revalidation"] = {
            "status": "ok",
            "config": config_integrity["final"],
            "frozen_condition": frozen_condition_revalidation,
        }
    except Exception as exc:
        if isinstance(exc, ConfigSnapshotError):
            config_integrity["final"] = exc.evidence
        integrity_failure_reason = f"final worker integrity gate failed: {exc}"
        metadata["integrity_revalidation"] = {
            "status": "error",
            "config": config_integrity.get("final"),
            "error": {"type": type(exc).__name__, "detail": str(exc)[:1_000]},
        }
        metadata["reason"] = integrity_failure_reason

    completed_normally = len(results) == len(tasks) and not any(
        item["status"] == "interrupted" for item in results
    )
    invalid_configuration_count = sum(
        item["status"] == "invalid_configuration" for item in results
    )
    invalid_leakage_count = sum(item["status"] == "invalid_leakage" for item in results)
    if invalid_leakage_count:
        overall_status = "invalid_leakage"
    elif invalid_configuration_count or integrity_failure_reason is not None:
        overall_status = "invalid_configuration"
    elif completed_normally:
        overall_status = "completed"
    else:
        overall_status = "interrupted"
    metadata.update(
        {
            "status": overall_status,
            "completed_at": utc_now(),
            "passed": sum(item["status"] == "passed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "environment_failure": sum(
                item["status"] == "environment_failure" for item in results
            ),
            "model_protocol_failure": sum(
                item["status"] == "model_protocol_failure" for item in results
            ),
            "model_transport_failure": sum(
                item["status"] == "model_transport_failure" for item in results
            ),
            "agent_failure": sum(item["status"] == "agent_failure" for item in results),
            "agent_deadline_exhausted": sum(
                item["status"] == "agent_deadline_exhausted" for item in results
            ),
            "evaluation_failure": sum(
                item["status"] == "evaluation_failure" for item in results
            ),
            "invalid_configuration": max(
                invalid_configuration_count,
                1 if integrity_failure_reason is not None else 0,
            ),
            "invalid_leakage": invalid_leakage_count,
            "interrupted": sum(item["status"] == "interrupted" for item in results),
        }
    )
    write_json(args.result_dir / "metadata.json", metadata)
    write_json(
        args.result_dir / "results.json", {"metadata": metadata, "tasks": results}
    )


if __name__ == "__main__":
    main()
