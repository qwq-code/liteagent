from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, MutableMapping

import requests

from multi_apps_adapter.route_utils import decode_text, has_unresolved_encoding


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parent if V2_ROOT.name == "baseline" else V2_ROOT.parents[1]
OSWORLD_ROOT = PROJECT_ROOT / "third_party" / "OSWorld"
V2_SCRIPTS = V2_ROOT / "scripts"
if str(V2_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(V2_SCRIPTS))

from scripts.deploy_all_adapters import ADAPTERS, deploy_adapter  # noqa: E402
from scripts.office_episode_recovery import replay_office_setup  # noqa: E402


DEFAULT_QCOW2 = OSWORLD_ROOT / "docker_vm_data" / "Ubuntu.qcow2"
DEFAULT_CACHE_DIR = OSWORLD_ROOT / "cache"
MAX_EVALUATOR_ARTIFACT_BYTES = 256 * 1024 * 1024

DOMAIN_ADAPTER_MODULE = {
    "libreoffice_calc": "calc_adapter",
    "libreoffice_impress": "impress_adapter",
    "chrome": "chrome_adapter",
    "gimp": "gimp_adapter",
    "os": "os_adapter",
    "libreoffice_writer": "writer_adapter",
    "vs_code": "vscode_adapter",
    "vlc": "vlc_adapter",
    "thunderbird": "thunderbird_adapter",
    "multi_apps": "multi_apps_adapter",
}
ENDPOINT_BY_MODULE = {
    "calc_adapter": "libreoffice_calc",
    "impress_adapter": "libreoffice_impress",
    "chrome_adapter": "chrome",
    "gimp_adapter": "gimp",
    "os_adapter": "os",
    "writer_adapter": "libreoffice_writer",
    "vscode_adapter": "vs_code",
    "vlc_adapter": "vlc",
    "thunderbird_adapter": "thunderbird",
    "multi_apps_adapter": "multi_apps",
}
PREPARE_AFTER_RESET_DOMAINS = {
    "libreoffice_calc",
    "libreoffice_impress",
    "libreoffice_writer",
}
FORBIDDEN_STRICT_MODULES = frozenset({"scripts.run_openapa_pilot"})
TASK_UUID_PATTERN = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])",
    re.IGNORECASE,
)


def assert_strict_process_boundary() -> dict[str, Any]:
    loaded_forbidden = sorted(FORBIDDEN_STRICT_MODULES.intersection(sys.modules))
    if loaded_forbidden:
        raise RuntimeError(
            f"strict Runner loaded forbidden legacy modules: {loaded_forbidden}"
        )

    scanned: dict[str, dict[str, Any]] = {}
    uuid_sources: list[str] = []
    for module in tuple(sys.modules.values()):
        source_name = getattr(module, "__file__", None)
        if not isinstance(source_name, str) or not source_name.endswith(".py"):
            continue
        source = Path(source_name).resolve()
        try:
            source.relative_to(V2_ROOT)
        except ValueError:
            continue
        if not source.is_file():
            continue
        relative = str(source.relative_to(V2_ROOT))
        content = source.read_bytes()
        scanned[relative] = {
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        if TASK_UUID_PATTERN.search(decode_text(content)) or has_unresolved_encoding(
            content
        ):
            uuid_sources.append(relative)
    if uuid_sources:
        raise RuntimeError(
            f"strict Runner imported source containing task UUID constants: {uuid_sources}"
        )
    source_files = [
        {"path": path, **details} for path, details in sorted(scanned.items())
    ]
    combined = hashlib.sha256(
        json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "status": "ok",
        "loaded_modules_scanned": len(source_files),
        "source_files": source_files,
        "combined_sha256": combined,
        "forbidden_modules": [],
        "task_uuid_sources": [],
    }


def configure_evaluator_runtime(
    environ: MutableMapping[str, str] | None = None,
) -> str:
    target = os.environ if environ is None else environ
    target.setdefault("CUDA_VISIBLE_DEVICES", "")
    return "cpu" if target["CUDA_VISIBLE_DEVICES"] == "" else "configured_cuda"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_tasks(
    config_path: Path,
    limit: int | None,
    orders: set[int] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    tasks = config["tasks"]
    if orders is not None:
        tasks = [task for task in tasks if task["order"] in orders]
        found = {task["order"] for task in tasks}
        missing = sorted(orders - found)
        if missing:
            raise ValueError(f"task orders not found in config: {missing}")
    if limit is not None:
        tasks = tasks[:limit]
    return config, tasks


def should_enable_guest_proxy(config: dict[str, Any], example: dict[str, Any]) -> bool:
    return bool(
        config.get("protocol", {}).get("guest_proxy", False)
        and example.get("proxy", False)
    )


def deploy_generic_stack(env: Any, domain: str) -> dict[str, str]:
    try:
        primary_module = DOMAIN_ADAPTER_MODULE[domain]
    except KeyError as exc:
        raise ValueError(f"unsupported task domain: {domain}") from exc

    required = (
        set(DOMAIN_ADAPTER_MODULE.values())
        if domain == "multi_apps"
        else {primary_module}
    )
    control_url = f"http://127.0.0.1:{env.server_port}"
    adapter_urls = env.provider.adapter_urls()
    for module, _endpoint_key in ADAPTERS:
        if module not in required:
            continue
        deploy_adapter(
            module,
            control_url,
            adapter_urls[ENDPOINT_BY_MODULE[module]],
        )
    return adapter_urls


def prepare_adapter_after_reset(
    domain: str,
    adapter_urls: dict[str, str],
    attempts: int = 4,
) -> dict[str, Any] | None:
    if domain not in PREPARE_AFTER_RESET_DOMAINS:
        return None
    url = adapter_urls[domain].rstrip("/") + "/v1/prepare"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(
                url,
                json={"timeout_ms": 60_000},
                timeout=70,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "ok":
                raise RuntimeError(payload)
            return payload
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 * attempt, 6))
    raise RuntimeError(f"failed to prepare {domain} after task reset: {last_error}")


def install_post_reset_prepare(
    env: Any,
    domain: str,
    adapter_urls: dict[str, str],
) -> None:
    if domain not in PREPARE_AFTER_RESET_DOMAINS:
        return
    original_reset = env.reset

    def reset_with_prepare(*args: Any, **kwargs: Any) -> Any:
        result = original_reset(*args, **kwargs)
        prepare_adapter_after_reset(domain, adapter_urls)
        task_config = kwargs.get("task_config")
        if task_config is None and args:
            task_config = args[0]
        use_proxy = bool(
            (task_config or {}).get("proxy", False)
            and getattr(env, "enable_proxy", False)
        )
        replay_office_setup(
            setup_controller=env.setup_controller,
            setup_steps=(task_config or {}).get("config", []),
            use_proxy=use_proxy,
        )
        return result

    env.reset = reset_with_prepare


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_evaluator_artifact(
    value: Any,
    destination: Path,
    copied: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    role: str,
    index: int,
) -> Any:
    if isinstance(value, list):
        return [
            _copy_evaluator_artifact(
                item,
                destination,
                copied,
                skipped,
                role,
                item_index,
            )
            for item_index, item in enumerate(value)
        ]
    if not isinstance(value, str) or not value.strip():
        return value
    source = Path(value.strip())
    if not source.is_absolute() or not source.exists():
        return value
    if source.is_symlink() or not source.is_file():
        skipped.append(
            {
                "role": role,
                "source": str(source),
                "reason": "symlink" if source.is_symlink() else "not_regular_file",
            }
        )
        return value
    source_size = source.stat().st_size
    if source_size > MAX_EVALUATOR_ARTIFACT_BYTES:
        skipped.append(
            {
                "role": role,
                "source": str(source),
                "reason": "size_limit_exceeded",
                "size": source_size,
                "max_size": MAX_EVALUATOR_ARTIFACT_BYTES,
            }
        )
        return value

    target = destination / f"{role}-{index:02d}-{source.name}"
    shutil.copy2(source, target)
    copied.append(
        {
            "role": role,
            "source": str(source),
            "artifact": target.name,
            "type": "file",
            "size": target.stat().st_size,
            "sha256": _sha256_file(target),
        }
    )
    return str(target)


def capture_evaluator_evidence(
    env: Any,
    example: dict[str, Any],
    task_dir: Path,
) -> dict[str, Any]:
    evaluator = example.get("evaluator", {})
    destination = task_dir / "evaluator_artifacts"
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    states: dict[str, Any] = {}

    for role, getter, config in (
        ("result", env.result_getter, evaluator.get("result")),
        ("expected", env.expected_getter, evaluator.get("expected")),
    ):
        if getter is None or config in (None, [], {}):
            continue
        getters = getter if isinstance(getter, list) else [getter]
        configs = config if isinstance(config, list) else [config]
        role_states = []
        for index, (current_getter, current_config) in enumerate(zip(getters, configs)):
            value = current_getter(env, current_config)
            role_states.append(
                _copy_evaluator_artifact(
                    value,
                    destination,
                    copied,
                    skipped,
                    role,
                    index,
                )
            )
        states[role] = role_states

    manifest = {
        "states": states,
        "artifacts": copied,
        "skipped_artifacts": skipped,
    }
    write_json(destination / "manifest.json", manifest)
    return {
        "manifest": str(destination / "manifest.json"),
        "artifact_count": len(copied),
    }


def assert_secret_absent(root: Path, secret: str) -> None:
    for path in root.rglob("*"):
        if path.is_file() and path.stat().st_size < 20_000_000:
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if secret in content:
                raise RuntimeError(f"API key was written to {path}")
