from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from scripts import run_lite_agent_pilot as lite_runner
from scripts.openapa_trajectory import build_trajectory_manifest
from scripts.run_holo_agent_pilot import assert_request_safe


def _worker_config() -> dict[str, Any]:
    return {
        "condition": {"role": "repair_worker"},
        "protocol": {
            "reasoning_mode": "thinking",
            "gui_model": {
                "provider": "holo",
                "requested": "holo3.1-4b",
                "model": "holo3.1-4b",
                "base_url": "http://holo.invalid/v1",
                "served_root": "Hcompany/Holo-3.1-4B",
                "accepted_actual_models": ["holo3.1-4b"],
                "reasoning_mode": "thinking",
                "reasoning_profile": "binary_thinking_switch",
                "max_output_tokens": 1024,
                "temperature": 0.8,
                "request_timeout_seconds": 180.0,
            },
        },
        "model": {
            "requested": "qwen3.5-4b",
            "served_root": "Qwen/Qwen3.5-4B",
            "reasoning_profile": "qwen35_thinking_switch",
        },
        "osworld_commit": "b" * 40,
        "tasks": [{"order": 1, "task_id": "synthetic-task", "domain": "os"}],
    }


def _patch_worker_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    events: list[str],
    *,
    holo_root: str = "Hcompany/Holo-3.1-4B",
    run_task: Any | None = None,
) -> None:
    monkeypatch.setattr(
        lite_runner,
        "assert_strict_process_boundary",
        lambda: {"status": "ok"},
    )
    monkeypatch.setattr(lite_runner.os, "chdir", lambda _path: None)
    monkeypatch.setattr(lite_runner, "configure_evaluator_runtime", lambda: None)

    def enforce(_config: dict[str, Any], args: Any, _root: Path) -> dict[str, Any]:
        events.append("frozen_gate")
        assert args.runner == Path(lite_runner.__file__).resolve()
        assert args.python == str(Path(sys.executable).resolve())
        return {"status": "ok"}

    monkeypatch.setattr(lite_runner, "enforce_runner_condition", enforce)

    def preflight(base_url: str, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        if base_url == "http://holo.invalid/v1":
            events.append("holo_preflight")
            return {
                "id": "holo3.1-4b",
                "root": holo_root,
                "reasoning_gate": {
                    "verified": True,
                    "requested_mode": "thinking",
                    "profile": "binary_thinking_switch",
                },
            }
        events.append("qwen_preflight")
        return {
            "id": "qwen3.5-4b",
            "root": "Qwen/Qwen3.5-4B",
            "reasoning_gate": {
                "verified": True,
                "requested_mode": "thinking",
                "profile": "qwen35_thinking_switch",
            },
        }

    monkeypatch.setattr(lite_runner, "model_preflight", preflight)
    monkeypatch.setattr(
        lite_runner,
        "install_provider_patch",
        lambda: events.append("provider_patch"),
    )
    monkeypatch.setattr(
        lite_runner,
        "osworld_task_path",
        lambda _root, _task: Path("synthetic-task.json"),
    )
    monkeypatch.setattr(
        lite_runner,
        "load_agent_task_config_isolated",
        lambda *_args, **_kwargs: {"instruction": "Use no GUI for this task."},
    )
    if run_task is None:

        def run_task(**_kwargs: Any) -> dict[str, Any]:
            events.append("run_task")
            return {"status": "passed"}

    monkeypatch.setattr(lite_runner, "run_task", run_task)


def _run_worker_main(
    monkeypatch: pytest.MonkeyPatch,
    config_path: Path,
    result_dir: Path,
    *extra: str,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(Path(lite_runner.__file__).resolve()),
            "--config",
            str(config_path),
            "--result-dir",
            str(result_dir),
            "--thinking",
            *extra,
        ],
    )
    lite_runner.main()


def test_request_boundary_accepts_generic_holo_surface() -> None:
    assert_request_safe(
        {
            "messages": [{"role": "user", "content": "Inspect the screenshot."}],
            "tools": [{"function": {"name": "click"}}],
        },
        "private-task-token",
    )


@pytest.mark.parametrize(
    "leak",
    [
        "private-task-token",
        "private-",
        "task.execute",
        "task.inspect",
        "artifact.materialize",
        "task_action_hints",
    ],
)
def test_request_boundary_fails_closed_on_identity_or_forbidden_route(
    leak: str,
) -> None:
    with pytest.raises(RuntimeError, match="invalid_leakage"):
        assert_request_safe(
            {"messages": [{"role": "user", "content": leak}]},
            "private-task-token",
        )


def test_bad_config_hash_is_persisted_before_config_load_or_vm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text(json.dumps(_worker_config()), encoding="utf-8")
    result_dir = tmp_path / "result"
    monkeypatch.setattr(
        lite_runner,
        "assert_strict_process_boundary",
        lambda: (_ for _ in ()).throw(AssertionError("process gate was reached")),
    )
    monkeypatch.setattr(
        lite_runner,
        "load_tasks",
        lambda *_args: (_ for _ in ()).throw(AssertionError("config was parsed")),
    )
    monkeypatch.setattr(
        lite_runner,
        "run_task",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("VM was started")),
    )

    _run_worker_main(
        monkeypatch,
        config_path,
        result_dir,
        "--expected-config-sha256",
        "0" * 64,
    )

    metadata = json.loads((result_dir / "metadata.json").read_text())
    assert metadata["status"] == "invalid_configuration"
    assert metadata["tasks_started"] == 0
    assert metadata["config_integrity"]["pre_load"]["verified"] is False
    assert "do not match" in metadata["reason"]


def test_promotion_worker_requires_expected_config_hash_before_vm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _worker_config()
    config["condition"] = {"promotion_gate": True, "role": "promotion_smoke"}
    config_path = tmp_path / "condition.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result_dir = tmp_path / "result"
    monkeypatch.setattr(
        lite_runner,
        "assert_strict_process_boundary",
        lambda: {"status": "ok"},
    )
    monkeypatch.setattr(lite_runner.os, "chdir", lambda _path: None)
    monkeypatch.setattr(lite_runner, "configure_evaluator_runtime", lambda: None)
    monkeypatch.setattr(
        lite_runner,
        "enforce_runner_condition",
        lambda *_args: (_ for _ in ()).throw(AssertionError("frozen gate was reached")),
    )
    monkeypatch.setattr(
        lite_runner,
        "run_task",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("VM was started")),
    )

    _run_worker_main(monkeypatch, config_path, result_dir)

    metadata = json.loads((result_dir / "metadata.json").read_text())
    assert metadata["status"] == "invalid_configuration"
    assert metadata["tasks_started"] == 0
    assert "requires --expected-config-sha256" in metadata["reason"]


def test_holo_preflight_runs_for_task_that_never_requests_gui(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text(json.dumps(_worker_config()), encoding="utf-8")
    result_dir = tmp_path / "result"
    events: list[str] = []
    _patch_worker_boundaries(monkeypatch, events)

    _run_worker_main(monkeypatch, config_path, result_dir)

    assert events.index("holo_preflight") < events.index("run_task")
    metadata = json.loads((result_dir / "metadata.json").read_text())
    assert metadata["status"] == "completed"
    assert metadata["gui_model_preflight"]["status"] == "ok"
    assert metadata["gui_model_preflight"]["preflight_scope"] == [
        "models",
        "openapi",
    ]
    assert metadata["gui_model_preflight"]["inference_request_sent"] is False
    assert metadata["integrity_revalidation"]["status"] == "ok"


def test_bad_holo_preflight_is_persisted_without_starting_vm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text(json.dumps(_worker_config()), encoding="utf-8")
    result_dir = tmp_path / "result"
    events: list[str] = []

    def no_vm(**_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("VM was started")

    _patch_worker_boundaries(
        monkeypatch,
        events,
        holo_root="unexpected/root",
        run_task=no_vm,
    )

    _run_worker_main(monkeypatch, config_path, result_dir)

    assert "provider_patch" not in events
    metadata = json.loads((result_dir / "metadata.json").read_text())
    assert metadata["status"] == "invalid_configuration"
    assert metadata["tasks_started"] == 0
    assert metadata["gui_model_preflight"]["status"] == "error"
    assert metadata["gui_model_preflight"]["identity_gate"]["verified"] is False


def test_final_config_revalidation_invalidates_changed_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text(json.dumps(_worker_config()), encoding="utf-8")
    result_dir = tmp_path / "result"
    events: list[str] = []

    def mutate_config(**_kwargs: Any) -> dict[str, Any]:
        events.append("run_task")
        config_path.write_text('{"changed":true}', encoding="utf-8")
        return {"status": "passed"}

    _patch_worker_boundaries(
        monkeypatch,
        events,
        run_task=mutate_config,
    )

    _run_worker_main(monkeypatch, config_path, result_dir)

    metadata = json.loads((result_dir / "metadata.json").read_text())
    assert metadata["status"] == "invalid_configuration"
    assert metadata["invalid_configuration"] == 1
    assert metadata["integrity_revalidation"]["status"] == "error"
    assert metadata["config_integrity"]["final"]["verified"] is False
    assert "changed after the initial snapshot gate" in metadata["reason"]


def test_trajectory_manifest_seals_holo_grounding_trace(tmp_path) -> None:
    trace = tmp_path / "holo_grounding_calls.jsonl"
    trace_bytes = (
        b'{"record_type":"request_attempt","request_id":"synthetic"}\n'
        b'{"record_type":"request_failure","request_id":"synthetic"}\n'
    )
    trace.write_bytes(trace_bytes)

    manifest = build_trajectory_manifest(
        tmp_path,
        episode_context={
            "task_id": "synthetic-task",
            "order": 1,
            "domain": "os",
        },
        record={"status": "failed", "reward": 0.0},
        instruction="Click the visible button.",
        agent_prompt="Synthetic generic prompt",
        model_requested="synthetic-model",
        reasoning_effort="medium",
        max_steps=1,
        config_sha256="a" * 64,
        coverage_sha256=None,
        osworld_commit="b" * 40,
        openapa_commit="c" * 40,
        screen_size=[1920, 1080],
        grounding_coordinate_size=[1000, 1000],
        started_at="2026-09-02T00:00:00+00:00",
        completed_at="2026-09-02T00:00:01+00:00",
    )

    artifact = manifest["artifacts"]["holo_grounding_calls.jsonl"]
    assert artifact == {
        "path": "holo_grounding_calls.jsonl",
        "bytes": len(trace_bytes),
        "sha256": hashlib.sha256(trace_bytes).hexdigest(),
    }
