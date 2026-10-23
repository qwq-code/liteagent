from __future__ import annotations

import os
import re
import sys
from argparse import Namespace
from pathlib import Path
import subprocess
from typing import Any
from urllib.parse import urlsplit

from scripts.condition_seal import (
    SOURCE_SCOPE_ROOTS,
    build_source_tree_seal,
    source_tree_seal_matches,
)
from integrations.lite_agent.reasoning import (
    SUPPORTED_REASONING_EFFORTS,
    SUPPORTED_REASONING_MODES,
)


CONDITION_SCHEMA = "trusted_generic_only_condition.v1"
V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parents[1]
TRUSTED_GIT = Path("/usr/bin/git")
PROMOTION_ROLE_MARKERS = (
    "baseline",
    "promotion",
    "fixed189",
    "fixed_189",
    "full189",
    "full_189",
    "smoke",
    "validation",
)
OSWORLD_ALLOWED_UNTRACKED_PREFIXES = (".conda/",)


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"frozen condition requires {name} object")
    return value


def _require_equal(name: str, observed: Any, expected: Any) -> None:
    if observed != expected:
        raise RuntimeError(
            f"frozen condition mismatch for {name}: observed={observed!r}, "
            f"expected={expected!r}"
        )


def _promotion_gate_required(config: dict[str, Any], condition: dict[str, Any]) -> bool:
    role = re.sub(
        r"[^a-z0-9]+", "_", str(condition.get("role") or "").casefold()
    ).strip("_")
    role_requires_gate = any(
        re.search(rf"(?:^|_){re.escape(marker)}(?:_|$)", role)
        for marker in PROMOTION_ROLE_MARKERS
    )
    return any(
        (
            config.get("promotion_gate") is not None,
            condition.get("promotion_gate") is True,
            condition.get("baseline_candidate") is True,
            condition.get("promotion_pre_authorized") is True,
            # Historical smoke/validation manifests predate this repository
            # gate. They must be resealed before reuse, rather than silently
            # entering a promotion-only workflow with incomplete provenance.
            role_requires_gate,
        )
    )


def _require_project_path(
    project_root: Path, value: Any, name: str, *, allow_root: bool = False
) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"invalid_configuration: {name} must be a relative path")
    relative = Path(value)
    if relative.is_absolute():
        raise RuntimeError(f"invalid_configuration: {name} must be project-relative")
    root = project_root.resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(
            f"invalid_configuration: {name} escapes the project root"
        ) from exc
    if resolved == root and not allow_root:
        raise RuntimeError(f"invalid_configuration: {name} cannot be the project root")
    return resolved


def _require_v2_entrypoint(value: Any, name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(
            f"invalid_configuration: promotion gate requires protocol.{name}"
        )
    relative = Path(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(
            f"invalid_configuration: protocol.{name} must be a canonical v2-relative path"
        )
    resolved = (V2_ROOT / relative).resolve()
    try:
        resolved.relative_to(V2_ROOT)
    except ValueError as exc:
        raise RuntimeError(
            f"invalid_configuration: protocol.{name} escapes the active v2 tree"
        ) from exc
    if not resolved.is_file():
        raise RuntimeError(
            f"invalid_configuration: protocol.{name} does not name a file"
        )
    return resolved


def _require_frozen_python(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(
            "invalid_configuration: promotion gate requires protocol.python"
        )
    path = Path(value)
    if not path.is_absolute() or value != value.strip() or not path.is_file():
        raise RuntimeError(
            "invalid_configuration: protocol.python must be an absolute executable path"
        )
    if not os.access(path, os.X_OK):
        raise RuntimeError("invalid_configuration: protocol.python is not executable")
    return path.resolve()


def _validate_promotion_runtime(
    config: dict[str, Any], args: Namespace, project_root: Path
) -> dict[str, str] | None:
    condition = config["condition"]
    if not _promotion_gate_required(config, condition):
        return None
    protocol = config["protocol"]
    expected_supervisor = _require_v2_entrypoint(
        protocol.get("supervisor"), "supervisor"
    )
    expected_runner = _require_v2_entrypoint(protocol.get("runner"), "runner")
    configured_python = protocol.get("python")
    expected_python = _require_frozen_python(configured_python)

    observed_supervisor_value = getattr(args, "supervisor", None)
    if not isinstance(observed_supervisor_value, (str, Path)):
        raise RuntimeError(
            "invalid_configuration: promotion supervisor identity is unavailable"
        )
    observed_supervisor = Path(observed_supervisor_value).resolve()
    observed_runner_value = getattr(args, "runner", None)
    if not isinstance(observed_runner_value, (str, Path)) or not str(
        observed_runner_value
    ):
        raise RuntimeError(
            "invalid_configuration: promotion runner identity is unavailable"
        )
    observed_runner = Path(observed_runner_value).resolve()
    observed_python_value = getattr(args, "python", None)
    if (
        not isinstance(observed_python_value, str)
        or not Path(observed_python_value).is_absolute()
    ):
        raise RuntimeError(
            "invalid_configuration: promotion worker Python must be an absolute path"
        )
    observed_python = Path(observed_python_value).resolve()

    _require_equal("supervisor", observed_supervisor, expected_supervisor)
    _require_equal("runner", observed_runner, expected_runner)
    _require_equal("python", observed_python, expected_python)
    _require_equal("supervisor_python", Path(sys.executable).resolve(), expected_python)
    _require_project_path(
        project_root,
        condition.get("result_directory"),
        "condition.result_directory",
    )
    _require_project_path(project_root, config["vm"].get("image"), "vm.image")
    return {
        "supervisor": str(expected_supervisor),
        "runner": str(expected_runner),
        "python": str(expected_python),
    }


def _validate_runner_runtime(config: dict[str, Any]) -> dict[str, str] | None:
    condition = config["condition"]
    if not _promotion_gate_required(config, condition):
        return None
    protocol = config["protocol"]
    expected_runner = _require_v2_entrypoint(protocol.get("runner"), "runner")
    expected_python = _require_frozen_python(protocol.get("python"))

    observed_runner_value = sys.argv[0] if sys.argv else None
    if not isinstance(observed_runner_value, str) or not observed_runner_value:
        raise RuntimeError(
            "invalid_configuration: promotion runner identity is unavailable"
        )
    observed_runner = Path(observed_runner_value).resolve()
    observed_python = Path(sys.executable).resolve()
    _require_equal("runner", observed_runner, expected_runner)
    _require_equal("runner_python", observed_python, expected_python)
    return {
        "runner": str(expected_runner),
        "python": str(expected_python),
    }


def _require_canonical_http_url(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RuntimeError(f"invalid_configuration: frozen {name} is not a URL")
    parsed = urlsplit(value)
    try:
        parsed.port
    except ValueError as exc:
        raise RuntimeError(
            f"invalid_configuration: frozen {name} has an invalid port"
        ) from exc
    path_parts = parsed.path.split("/")
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.scheme != parsed.scheme.lower()
        or not parsed.hostname
        or parsed.netloc != parsed.netloc.lower()
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path.endswith("/")
        or "//" in parsed.path
        or any(part in {".", ".."} for part in path_parts)
    ):
        raise RuntimeError(
            f"invalid_configuration: frozen {name} must be a canonical HTTP(S) base URL"
        )
    return value


def _validate_holo_args(
    protocol: dict[str, Any],
    args: Namespace,
    *,
    primary_base_urls: list[str] | None = None,
) -> None:
    gui_model_value = protocol.get("gui_model")
    if gui_model_value is None:
        unexpected = {
            name: getattr(args, name, None)
            for name in (
                "holo_base_url",
                "holo_base_urls",
                "holo_model",
                "holo_reasoning_effort",
                "holo_reasoning_mode",
            )
            if getattr(args, name, None) not in (None, "")
        }
        if unexpected:
            raise RuntimeError(
                "invalid_configuration: Holo CLI options require a frozen "
                "protocol.gui_model declaration"
            )
        return

    gui_model = _require_object(gui_model_value, "protocol.gui_model")
    if protocol.get("gui_enabled") is not True:
        raise RuntimeError(
            "invalid_configuration: frozen Holo model requires gui_enabled=true"
        )
    if gui_model.get("provider") != "holo":
        raise RuntimeError(
            "invalid_configuration: protocol.gui_model.provider must be holo"
        )

    requested = gui_model.get("requested")
    if not isinstance(requested, str) or not requested:
        raise RuntimeError(
            "invalid_configuration: frozen Holo model has no requested model id"
        )
    declared_model = gui_model.get("model", requested)
    _require_equal("holo_model_declaration", declared_model, requested)
    paired_urls = gui_model.get("base_urls")
    if paired_urls is not None:
        _require_equal(
            "Holo endpoint_assignment",
            gui_model.get("endpoint_assignment"),
            "paired_with_primary",
        )
        if not isinstance(paired_urls, list) or not paired_urls:
            raise RuntimeError("invalid_configuration: Holo base_urls must be non-empty")
        for endpoint in paired_urls:
            _require_canonical_http_url(endpoint, "Holo base_urls endpoint")
        _require_equal("Holo paired endpoints", paired_urls, primary_base_urls)
        _require_equal(
            "Holo single endpoint in paired mode", gui_model.get("base_url"), None
        )
        if hasattr(args, "base_urls"):
            _require_equal(
                "holo_base_urls", getattr(args, "holo_base_urls", None), paired_urls
            )
            _require_equal("holo_base_url", getattr(args, "holo_base_url", None), None)
        else:
            primary_url = getattr(args, "base_url", None)
            if primary_url not in paired_urls:
                raise RuntimeError("Runner model endpoint is outside the paired condition")
            _require_equal(
                "holo_base_url", getattr(args, "holo_base_url", None), primary_url
            )
    else:
        _require_canonical_http_url(gui_model.get("base_url"), "Holo base_url")
        _require_equal("holo_base_urls", getattr(args, "holo_base_urls", None), None)
        _require_equal(
            "holo_base_url", getattr(args, "holo_base_url", None), gui_model["base_url"]
        )

    checks = {
        "holo_model": (getattr(args, "holo_model", None), requested),
        "holo_max_output_tokens": (
            getattr(args, "holo_max_output_tokens", None),
            gui_model.get("max_output_tokens"),
        ),
        "holo_temperature": (
            getattr(args, "holo_temperature", None),
            gui_model.get("temperature"),
        ),
        "holo_request_timeout": (
            getattr(args, "holo_request_timeout", None),
            gui_model.get("request_timeout_seconds"),
        ),
    }
    for name, (observed, expected) in checks.items():
        if expected is None:
            raise RuntimeError(
                f"invalid_configuration: frozen Holo model has no {name} value"
            )
        _require_equal(name, observed, expected)

    configured_mode = gui_model.get("reasoning_mode")
    configured_effort = gui_model.get("reasoning_effort")
    if configured_mode is not None and configured_effort is not None:
        raise RuntimeError(
            "invalid_configuration: Holo reasoning_mode and reasoning_effort are "
            "mutually exclusive controls"
        )
    if configured_mode is not None:
        if configured_mode not in SUPPORTED_REASONING_MODES:
            raise RuntimeError(
                "invalid_configuration: unsupported frozen Holo reasoning_mode"
            )
        if getattr(args, "holo_reasoning_effort", None) is not None:
            raise RuntimeError(
                "invalid_configuration: binary Holo mode cannot use "
                "holo_reasoning_effort"
            )
        _require_equal(
            "holo_reasoning_mode",
            getattr(args, "holo_reasoning_mode", None),
            configured_mode,
        )
        return
    if configured_effort is not None:
        if configured_effort not in SUPPORTED_REASONING_EFFORTS:
            raise RuntimeError(
                "invalid_configuration: unsupported frozen Holo reasoning_effort"
            )
        if getattr(args, "holo_reasoning_mode", None) is not None:
            raise RuntimeError(
                "invalid_configuration: tiered Holo effort cannot use "
                "holo_reasoning_mode"
            )
        _require_equal(
            "holo_reasoning_effort",
            getattr(args, "holo_reasoning_effort", None),
            configured_effort,
        )
        return
    raise RuntimeError(
        "invalid_configuration: frozen Holo model must declare reasoning_mode "
        "or reasoning_effort"
    )


def validate_frozen_config(config: dict[str, Any]) -> dict[str, Any]:
    condition = _require_object(config.get("condition"), "condition")
    protocol = _require_object(config.get("protocol"), "protocol")
    model = _require_object(config.get("model"), "model")
    vm = _require_object(config.get("vm"), "vm")
    if condition.get("schema_version") != CONDITION_SCHEMA:
        raise RuntimeError("config is not a trusted frozen condition")
    if condition.get("enforced") is not True or config.get("status") != "frozen":
        raise RuntimeError("trusted condition must be frozen and enforced")
    if protocol.get("runs") != 1 or protocol.get("best_of") is not False:
        raise RuntimeError("trusted condition requires runs=1 and best_of=false")
    if protocol.get("preserve_every_attempt") is not True:
        raise RuntimeError("trusted condition must preserve every attempt")
    if protocol.get("task_specific_or_golden_exposed") is not False:
        raise RuntimeError("trusted condition cannot expose dataset-specific routes")
    if protocol.get("guest_proxy") is not False:
        raise RuntimeError("trusted condition requires guest_proxy=false")
    if not isinstance(condition.get("source_tree"), dict):
        raise RuntimeError("trusted condition has no source-tree seal")
    if not isinstance(condition.get("result_directory"), str):
        raise RuntimeError("trusted condition has no fixed result directory")
    if not isinstance(model.get("base_urls"), list) or not model["base_urls"]:
        raise RuntimeError("trusted condition has no fixed model endpoints")
    if not isinstance(vm.get("screen_size"), list) or len(vm["screen_size"]) != 2:
        raise RuntimeError("trusted condition has no fixed screen size")
    if not isinstance(vm.get("image"), str) or not vm["image"]:
        raise RuntimeError("trusted condition has no fixed VM image")
    nested_promotion_gate = condition.get("promotion_gate")
    if nested_promotion_gate is not None and not isinstance(
        nested_promotion_gate, bool
    ):
        raise RuntimeError("condition.promotion_gate must be boolean when present")
    top_level_promotion_gate = config.get("promotion_gate")
    if top_level_promotion_gate is not None and not isinstance(
        top_level_promotion_gate, dict
    ):
        raise RuntimeError("top-level promotion_gate must be an object when present")
    if _promotion_gate_required(config, condition):
        tasks = config.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise RuntimeError("promotion gate requires a non-empty frozen task set")
        task_orders: set[int] = set()
        task_ids: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict):
                raise RuntimeError("promotion gate task entries must be objects")
            order = task.get("order")
            task_id = task.get("task_id")
            domain = task.get("domain")
            if type(order) is not int or order <= 0:
                raise RuntimeError(
                    "promotion gate task order must be a positive integer"
                )
            if not isinstance(task_id, str) or not task_id:
                raise RuntimeError("promotion gate task_id must be a non-empty string")
            if not isinstance(domain, str) or not domain:
                raise RuntimeError(
                    "promotion gate task domain must be a non-empty string"
                )
            if order in task_orders or task_id in task_ids:
                raise RuntimeError(
                    "promotion gate task set contains duplicate identity"
                )
            task_orders.add(order)
            task_ids.add(task_id)
        source_commit = condition.get("source_git_commit")
        if not isinstance(source_commit, str) or not re.fullmatch(
            r"[0-9a-f]{40}", source_commit
        ):
            raise RuntimeError("promotion gate requires a full source_git_commit hash")
        if condition.get("source_dirty") is not False:
            raise RuntimeError("promotion gate requires source_dirty=false")
        sources = _require_object(config.get("sources"), "sources")
        _require_equal(
            "sources.source_git_commit",
            sources.get("source_git_commit"),
            source_commit,
        )
        osworld_commit = config.get("osworld_commit")
        if not isinstance(osworld_commit, str) or not re.fullmatch(
            r"[0-9a-f]{40}", osworld_commit
        ):
            raise RuntimeError("promotion gate requires a full osworld_commit hash")
        _require_v2_entrypoint(protocol.get("supervisor"), "supervisor")
        _require_v2_entrypoint(protocol.get("runner"), "runner")
        _require_frozen_python(protocol.get("python"))
    return condition


def _verify_source_tree(condition: dict[str, Any]) -> dict[str, Any]:
    current = build_source_tree_seal(V2_ROOT)
    if not source_tree_seal_matches(condition["source_tree"], current):
        raise RuntimeError(
            "frozen condition source-tree seal does not match the executing source"
        )
    return current


def _git_stdout(cwd: Path, *arguments: str) -> str:
    if not TRUSTED_GIT.is_file() or not os.access(TRUSTED_GIT, os.X_OK):
        raise RuntimeError(
            f"invalid_configuration: trusted Git executable is unavailable: {TRUSTED_GIT}"
        )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith("GIT_")
    }
    environment.update({"LC_ALL": "C", "LANG": "C"})
    try:
        result = subprocess.run(
            [str(TRUSTED_GIT), "--no-optional-locks", *arguments],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", None)
        detail = str(detail).strip()[:500] if detail else str(exc)[:500]
        raise RuntimeError(
            f"invalid_configuration: Git repository check failed: {detail}"
        ) from exc
    return result.stdout.strip()


def _verify_repository_identity(root: Path, name: str) -> dict[str, str]:
    expected_root = root.resolve()
    if root.is_symlink():
        raise RuntimeError(
            f"invalid_configuration: {name} repository root must not be a symlink"
        )
    expected_git_dir = expected_root / ".git"
    if not expected_git_dir.is_dir() or expected_git_dir.is_symlink():
        raise RuntimeError(
            f"invalid_configuration: {name} repository has no trusted .git directory"
        )
    observed_root = Path(
        _git_stdout(expected_root, "rev-parse", "--show-toplevel")
    ).resolve()
    observed_git_dir = Path(
        _git_stdout(expected_root, "rev-parse", "--absolute-git-dir")
    ).resolve()
    _require_equal(f"{name}_git_toplevel", observed_root, expected_root)
    _require_equal(
        f"{name}_git_directory", observed_git_dir, expected_git_dir.resolve()
    )
    return {
        "toplevel": str(observed_root),
        "git_directory": str(observed_git_dir),
    }


def _validate_osworld_status(status: str) -> None:
    rejected = []
    for row in status.splitlines():
        if not row:
            continue
        if row.startswith("?? ") and row[3:].startswith(
            OSWORLD_ALLOWED_UNTRACKED_PREFIXES
        ):
            continue
        rejected.append(row)
    if rejected:
        preview = "; ".join(rejected[:5])
        raise RuntimeError(
            "invalid_configuration: pinned OSWorld worktree has changes outside "
            f"the allowed .conda runtime environment: {preview}"
        )


def _verify_repository_state(
    config: dict[str, Any], condition: dict[str, Any]
) -> dict[str, Any] | None:
    if not _promotion_gate_required(config, condition):
        return None

    project_root = PROJECT_ROOT
    project_identity = _verify_repository_identity(project_root, "source")
    source_commit = condition["source_git_commit"]
    _require_equal(
        "source_git_commit",
        _git_stdout(project_root, "rev-parse", "HEAD"),
        source_commit,
    )
    source_paths = [
        (V2_ROOT / relative).relative_to(project_root).as_posix()
        for relative in SOURCE_SCOPE_ROOTS
    ]
    source_status = _git_stdout(
        project_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        *source_paths,
    )
    if source_status:
        raise RuntimeError(
            "invalid_configuration: promotion gate source scope is dirty"
        )

    osworld_root = project_root / "third_party" / "OSWorld"
    osworld_identity = _verify_repository_identity(osworld_root, "osworld")
    osworld_commit = config["osworld_commit"]
    _require_equal(
        "osworld_commit",
        _git_stdout(osworld_root, "rev-parse", "HEAD"),
        osworld_commit,
    )
    osworld_status = _git_stdout(
        osworld_root,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    )
    _validate_osworld_status(osworld_status)
    return {
        "source_git_commit": source_commit,
        "source_dirty": False,
        "osworld_commit": osworld_commit,
        "source_repository": project_identity,
        "osworld_repository": osworld_identity,
        "osworld_allowed_untracked_prefixes": list(OSWORLD_ALLOWED_UNTRACKED_PREFIXES),
    }


def revalidate_frozen_inputs(config: dict[str, Any]) -> dict[str, Any]:
    """Recheck immutable condition inputs without inspecting CLI/output state."""
    condition = validate_frozen_config(config)
    source_tree = _verify_source_tree(condition)
    repository_state = _verify_repository_state(config, condition)
    return {
        "condition": condition,
        "source_tree": source_tree,
        "repository_state": repository_state,
    }


def expected_result_directory(config: dict[str, Any], project_root: Path) -> Path:
    condition = validate_frozen_config(config)
    return _require_project_path(
        project_root,
        condition["result_directory"],
        "condition.result_directory",
    )


def _validate_common_args(config: dict[str, Any], args: Namespace) -> None:
    protocol = config["protocol"]
    model = config["model"]

    # Conditions created before the binary Qwen3.5 contract use the effort
    # vocabulary.  Keep that gate intact, but only apply it when the legacy
    # fields are present so a new binary-only condition does not need to carry
    # a provider option that the endpoint ignores.
    configured_effort = protocol.get("reasoning_effort")
    model_effort = model.get("reasoning_effort")
    has_effort_gate = any(
        key in protocol or key in model
        for key in ("reasoning_effort", "provider_max_reasoning_effort")
    )
    if has_effort_gate:
        # A model-side label is not evidence of the provider's maximum.
        # Require a separate frozen declaration so a missing field cannot
        # silently pass via a fallback to ``model.reasoning_effort``.
        if "provider_max_reasoning_effort" not in model:
            raise RuntimeError(
                "invalid_configuration: frozen condition must explicitly declare "
                "provider_max_reasoning_effort"
            )
        provider_max = model.get("provider_max_reasoning_effort")
        if (
            not isinstance(configured_effort, str)
            or configured_effort not in SUPPORTED_REASONING_EFFORTS
        ):
            raise RuntimeError(
                "invalid_configuration: frozen condition must declare a provider "
                "reasoning_effort"
            )
        if (
            not isinstance(model_effort, str)
            or model_effort not in SUPPORTED_REASONING_EFFORTS
            or not isinstance(provider_max, str)
            or provider_max not in SUPPORTED_REASONING_EFFORTS
            or configured_effort != model_effort
            or configured_effort != provider_max
        ):
            raise RuntimeError(
                "invalid_configuration: requested reasoning effort does not match "
                "the model/provider maximum declaration"
            )

    # New Qwen3.5 conditions use the explicit binary mode.  The protocol and
    # model must agree on the switch.  A provider-max field is accepted as an
    # optional capability annotation, but it is not required: Qwen3.5 has no
    # numeric effort ladder whose maximum could be declared or compared.
    configured_mode = protocol.get("reasoning_mode")
    model_mode = model.get("reasoning_mode")
    has_mode_gate = any(
        key in protocol or key in model
        for key in ("reasoning_mode", "provider_max_reasoning_mode")
    )
    if has_effort_gate and has_mode_gate:
        raise RuntimeError(
            "invalid_configuration: reasoning_effort and reasoning_mode are "
            "mutually exclusive controls"
        )
    if has_mode_gate:
        provider_max_mode = model.get("provider_max_reasoning_mode")
        if (
            not isinstance(configured_mode, str)
            or configured_mode not in SUPPORTED_REASONING_MODES
            or not isinstance(model_mode, str)
            or model_mode not in SUPPORTED_REASONING_MODES
            or configured_mode != model_mode
        ):
            raise RuntimeError(
                "invalid_configuration: requested reasoning mode does not match "
                "the protocol/model declaration"
            )
        if provider_max_mode is not None and (
            not isinstance(provider_max_mode, str)
            or provider_max_mode not in SUPPORTED_REASONING_MODES
            or provider_max_mode != configured_mode
        ):
            raise RuntimeError(
                "invalid_configuration: provider_max_reasoning_mode, when present, "
                "must equal the binary reasoning_mode"
            )
        if "max_local_steps" not in protocol or "max_soft_restarts" not in protocol:
            raise RuntimeError(
                "invalid_configuration: binary reasoning conditions must freeze "
                "max_local_steps and max_soft_restarts"
            )

    if not has_effort_gate and not has_mode_gate:
        raise RuntimeError(
            "invalid_configuration: frozen condition must declare reasoning_mode "
            "or reasoning_effort"
        )

    # The binary mode is the source of truth for new conditions.  For old
    # effort-only manifests retain the historical requirement that reasoning
    # is enabled; this keeps their validation behavior unchanged.
    if has_mode_gate:
        expected_thinking = configured_mode == "thinking"
        observed_thinking = getattr(args, "thinking", False)
        if (
            protocol.get("thinking") is not expected_thinking
            or observed_thinking is not expected_thinking
        ):
            raise RuntimeError(
                "invalid_configuration: reasoning_mode and thinking flag disagree"
            )
    elif (
        protocol.get("thinking") is not True
        or getattr(args, "thinking", False) is not True
    ):
        raise RuntimeError(
            "invalid_configuration: model tests require thinking enabled"
        )

    cli_mode = getattr(args, "reasoning_mode", None)
    if cli_mode is None and has_mode_gate:
        # Older callers only have the boolean flag.  Derive the equivalent
        # value rather than making those Namespaces incompatible.
        cli_mode = "thinking" if getattr(args, "thinking", False) else "non_thinking"
    if cli_mode is not None and cli_mode not in SUPPORTED_REASONING_MODES:
        raise RuntimeError(
            "invalid_configuration: CLI reasoning_mode must be thinking or non_thinking"
        )
    if has_mode_gate and getattr(args, "reasoning_effort", None) is not None:
        raise RuntimeError(
            "invalid_configuration: binary reasoning mode cannot use CLI reasoning_effort"
        )
    if has_effort_gate and getattr(args, "reasoning_mode", None) is not None:
        raise RuntimeError(
            "invalid_configuration: tiered reasoning effort cannot use CLI reasoning_mode"
        )
    checks = {
        "model": (args.model, model["requested"]),
        "max_steps": (args.max_steps, protocol["max_steps"]),
        "max_no_progress_steps": (
            args.max_no_progress_steps,
            protocol["max_no_progress_steps"],
        ),
        "max_agent_seconds": (args.max_agent_seconds, protocol["max_agent_seconds"]),
        "top_k": (args.top_k, protocol["top_k"]),
        "max_output_tokens": (args.max_output_tokens, protocol["max_output_tokens"]),
        "request_timeout": (args.request_timeout, protocol["request_timeout"]),
        "model_retries": (args.model_retries, protocol["model_retries"]),
        "thinking": (args.thinking, protocol["thinking"]),
        "gui_enabled": (not args.no_gui, protocol["gui_enabled"]),
        "evaluator_file_fetch_attempts": (
            args.evaluator_file_fetch_attempts,
            protocol["evaluator_file_fetch_attempts"],
        ),
        "evaluator_file_fetch_delay_seconds": (
            args.evaluator_file_fetch_delay_seconds,
            protocol["evaluator_file_fetch_delay_seconds"],
        ),
    }
    if "max_local_steps" in protocol:
        checks["max_local_steps"] = (
            getattr(args, "max_local_steps", None),
            protocol["max_local_steps"],
        )
    if "max_soft_restarts" in protocol:
        checks["max_soft_restarts"] = (
            getattr(args, "max_soft_restarts", None),
            protocol["max_soft_restarts"],
        )
    if has_effort_gate:
        checks["reasoning_effort"] = (
            getattr(args, "reasoning_effort", None),
            configured_effort,
        )
    if has_mode_gate:
        checks["reasoning_mode"] = (cli_mode, configured_mode)
    for name, (observed, expected) in checks.items():
        _require_equal(name, observed, expected)
    _validate_holo_args(protocol, args, primary_base_urls=model.get("base_urls"))


def enforce_supervisor_condition(
    config: dict[str, Any], args: Namespace, project_root: Path
) -> dict[str, Any]:
    frozen_inputs = revalidate_frozen_inputs(config)
    condition = frozen_inputs["condition"]
    source_tree = frozen_inputs["source_tree"]
    repository_state = frozen_inputs["repository_state"]
    _validate_common_args(config, args)
    promotion_runtime = _validate_promotion_runtime(config, args, project_root)
    protocol = config["protocol"]
    expected_result = expected_result_directory(config, project_root)
    _require_equal("result_directory", args.result_dir.resolve(), expected_result)
    _require_equal("workers", args.workers, protocol["concurrency"])
    _require_equal("base_urls", list(args.base_urls), config["model"]["base_urls"])
    _require_equal(
        "worker_start_delay_seconds",
        args.worker_start_delay_seconds,
        protocol["worker_start_delay_seconds"],
    )
    if args.resume_results:
        raise RuntimeError("trusted condition forbids resume results")
    if expected_result.exists():
        raise RuntimeError(
            f"trusted condition requires a new result directory: {expected_result}"
        )
    return {
        "status": "ok",
        "schema_version": CONDITION_SCHEMA,
        "experiment_id": config["experiment_id"],
        "role": condition["role"],
        "result_directory": condition["result_directory"],
        "source_tree_sha256": source_tree["sha256"],
        "repository_state": repository_state,
        "promotion_runtime": promotion_runtime,
        "baseline_candidate": bool(condition.get("baseline_candidate")),
        "promotion_pre_authorized": bool(condition.get("promotion_pre_authorized")),
        "resume": False,
    }


def enforce_runner_condition(
    config: dict[str, Any], args: Namespace, project_root: Path
) -> dict[str, Any]:
    frozen_inputs = revalidate_frozen_inputs(config)
    condition = frozen_inputs["condition"]
    source_tree = frozen_inputs["source_tree"]
    repository_state = frozen_inputs["repository_state"]
    _validate_common_args(config, args)
    promotion_runtime = _validate_runner_runtime(config)
    protocol = config["protocol"]
    vm = config["vm"]
    _require_equal("temperature", args.temperature, protocol["temperature"])
    _require_equal(
        "initial_settle_seconds",
        args.initial_settle_seconds,
        protocol["initial_settle_seconds"],
    )
    _require_equal(
        "action_settle_seconds",
        args.action_settle_seconds,
        protocol["action_settle_seconds"],
    )
    _require_equal(
        "evaluator_settle_seconds",
        args.evaluator_settle_seconds,
        protocol["evaluator_settle_seconds"],
    )
    _require_equal(
        "screen_size",
        [args.screen_width, args.screen_height],
        vm["screen_size"],
    )
    expected_qcow2 = _require_project_path(project_root, vm["image"], "vm.image")
    _require_equal("qcow2", args.qcow2.resolve(), expected_qcow2)
    if args.base_url not in config["model"]["base_urls"]:
        raise RuntimeError("Runner model endpoint is outside the frozen condition")
    if args.limit is not None or not args.orders:
        raise RuntimeError("trusted Runner requires an explicit non-empty order shard")
    configured_orders = {task["order"] for task in config["tasks"]}
    if (
        len(args.orders) != len(set(args.orders))
        or not set(args.orders) <= configured_orders
    ):
        raise RuntimeError("Runner order shard does not match the frozen task set")

    expected_root = expected_result_directory(config, project_root)
    workers_root = expected_root / "workers"
    try:
        relative = args.result_dir.resolve().relative_to(workers_root)
    except ValueError as exc:
        raise RuntimeError(
            "Runner result directory is outside the frozen condition"
        ) from exc
    if len(relative.parts) != 1 or not re.fullmatch(r"worker-\d{2}", relative.name):
        raise RuntimeError("Runner result directory is not a fixed worker shard")
    return {
        "status": "ok",
        "schema_version": CONDITION_SCHEMA,
        "experiment_id": config["experiment_id"],
        "role": condition["role"],
        "result_directory": condition["result_directory"],
        "worker": relative.name,
        "orders": list(args.orders),
        "base_url": args.base_url,
        "source_tree_sha256": source_tree["sha256"],
        "repository_state": repository_state,
        "promotion_runtime": promotion_runtime,
        "baseline_candidate": bool(condition.get("baseline_candidate")),
        "promotion_pre_authorized": bool(condition.get("promotion_pre_authorized")),
    }
