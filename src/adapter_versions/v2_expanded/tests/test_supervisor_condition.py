from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts import frozen_condition
from scripts import supervise_lite_agent_parallel as supervisor
from scripts.frozen_condition import _validate_common_args


def _args(tmp_path: Path, config: Path) -> SimpleNamespace:
    return SimpleNamespace(
        config=config,
        result_dir=tmp_path / "results",
        model="qwen3.5-4b",
        base_urls=["http://endpoint/v1"],
        workers=1,
        reasoning_effort=None,
        max_steps=4,
        max_no_progress_steps=4,
        max_agent_seconds=30.0,
        evaluator_file_fetch_attempts=1,
        evaluator_file_fetch_delay_seconds=0.0,
        frozen_condition=None,
    )


def test_supervisor_gate_writes_machine_readable_invalid_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text(
        json.dumps(
            {
                "tasks": [
                    {"order": 107, "task_id": "task-107", "domain": "multi_apps"}
                ],
                "protocol": {},
            }
        ),
        encoding="utf-8",
    )
    args = _args(tmp_path, config_path)
    monkeypatch.setattr(supervisor, "parse_args", lambda: args)
    monkeypatch.setattr(
        supervisor,
        "enforce_supervisor_condition",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("reasoning gate failed")),
    )

    assert supervisor.main() == 2

    result = json.loads((args.result_dir / "results.json").read_text())
    assert result["metadata"]["status"] == "invalid_configuration"
    assert result["metadata"]["status_counts"] == {"invalid_configuration": 1}
    assert result["tasks"][0]["status"] == "invalid_configuration"
    assert not (args.result_dir / "workers").exists()


def test_supervisor_rejects_config_drift_before_starting_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text(
        json.dumps(
            {
                "tasks": [{"order": 1, "task_id": "task-1", "domain": "os"}],
                "protocol": {},
            }
        ),
        encoding="utf-8",
    )
    args = _args(tmp_path, config_path)
    monkeypatch.setattr(supervisor, "parse_args", lambda: args)

    def mutate_after_gate(*_args: object) -> dict:
        config_path.write_text('{"changed":true}', encoding="utf-8")
        return {"status": "ok"}

    monkeypatch.setattr(supervisor, "enforce_supervisor_condition", mutate_after_gate)
    monkeypatch.setattr(
        supervisor.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("worker was started")
        ),
    )

    assert supervisor.main() == 2

    result = json.loads((args.result_dir / "results.json").read_text())
    initial_raw = json.dumps(
        {
            "tasks": [{"order": 1, "task_id": "task-1", "domain": "os"}],
            "protocol": {},
        }
    ).encode()
    assert result["metadata"]["status"] == "invalid_configuration"
    assert (
        result["metadata"]["config_sha256"]
        == supervisor.hashlib.sha256(initial_raw).hexdigest()
    )
    assert "changed after the supervisor gate" in result["metadata"]["reason"]
    assert not (args.result_dir / "workers").exists()


def test_aggregate_propagates_worker_gate_status_instead_of_not_run(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "invalid_configuration",
                    "reason": "provider mode is unverifiable",
                },
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )
    task = {"order": 107, "task_id": "task-107", "domain": "multi_apps"}

    payload = supervisor.aggregate(
        args,
        [task],
        [[task]],
        {},
        [],
        "completed",
        "2026-08-30T00:00:00Z",
    )

    assert payload["metadata"]["status"] == "invalid_configuration"
    assert payload["metadata"]["status_counts"] == {"invalid_configuration": 1}
    assert payload["tasks"][0]["status"] == "invalid_configuration"
    assert payload["tasks"][0]["path_class"] == "invalid_configuration"


def test_config_snapshot_preserves_exact_gated_bytes_and_is_read_only(
    tmp_path: Path,
) -> None:
    source = tmp_path / "condition.json"
    raw = b'{"status":"frozen", "tasks":[]}\n'
    source.write_bytes(raw)

    payload, observed_raw, digest = supervisor.read_config_snapshot(source)
    snapshot = tmp_path / "run" / "frozen-config.json"
    supervisor.write_config_snapshot(snapshot, observed_raw)

    assert payload == {"status": "frozen", "tasks": []}
    assert observed_raw == raw
    assert digest == supervisor.hashlib.sha256(raw).hexdigest()
    assert snapshot.read_bytes() == raw
    assert snapshot.stat().st_mode & 0o777 == 0o444


def test_worker_command_uses_immutable_config_snapshot(tmp_path: Path) -> None:
    source = tmp_path / "condition.json"
    snapshot = tmp_path / "run" / "frozen-config.json"
    snapshot.parent.mkdir()
    source.write_text("{}", encoding="utf-8")
    snapshot.write_text('{"status":"frozen"}', encoding="utf-8")
    args = SimpleNamespace(
        python="python",
        runner=tmp_path / "runner.py",
        supervisor=tmp_path / "supervisor.py",
        config=source,
        worker_config=snapshot,
        config_sha256="b" * 64,
        result_dir=tmp_path / "run",
        model="qwen3.5-4b",
        base_urls=["http://endpoint/v1"],
        workers=1,
        api_key="EMPTY",
        max_steps=9,
        max_no_progress_steps=4,
        max_agent_seconds=30.0,
        top_k=7,
        max_output_tokens=512,
        request_timeout=10.0,
        model_retries=1,
        evaluator_file_fetch_attempts=1,
        evaluator_file_fetch_delay_seconds=0.0,
        thinking=False,
        reasoning_effort=None,
        holo_base_url=None,
        holo_model=None,
        holo_api_key=None,
        holo_reasoning_effort=None,
        holo_reasoning_mode=None,
        holo_max_output_tokens=1024,
        holo_temperature=0.8,
        holo_request_timeout=10.0,
        no_gui=True,
    )

    command = supervisor.worker_command(args, 1, [{"order": 1}])

    assert command[command.index("--config") + 1] == str(snapshot)
    assert command[command.index("--expected-config-sha256") + 1] == "b" * 64


def test_worker_payload_integrity_binds_config_and_assigned_task() -> None:
    task = {"order": 7, "task_id": "task-7", "domain": "multi_apps"}
    payload = {
        "metadata": {
            "status": "completed",
            "config_sha256": "c" * 64,
            "task_order": ["task-7"],
        },
        "tasks": [
            {
                "order": 7,
                "task_id": "task-7",
                "domain": "multi_apps",
                "status": "passed",
            }
        ],
    }

    assert (
        supervisor.worker_payload_integrity_errors(
            payload, [task], expected_config_sha256="c" * 64
        )
        == []
    )

    payload["metadata"]["config_sha256"] = "d" * 64
    payload["tasks"][0]["task_id"] = "other-task"
    payload["tasks"][0]["domain"] = "os"
    errors = supervisor.worker_payload_integrity_errors(
        payload, [task], expected_config_sha256="c" * 64
    )

    assert errors == [
        "worker config SHA-256 does not match supervisor snapshot",
        "worker task_id mismatch for order 7",
        "worker domain mismatch for order 7",
    ]


def test_aggregate_rejects_passed_row_with_wrong_config_identity(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "e" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 7, "task_id": "task-7", "domain": "multi_apps"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "completed",
                    "config_sha256": "f" * 64,
                    "task_order": ["task-7"],
                },
                "tasks": [{**task, "status": "passed", "reward": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    payload = supervisor.aggregate(
        args, [task], [[task]], {}, [], "completed", "2026-09-02T00:00:00Z"
    )

    assert payload["metadata"]["status"] == "invalid_configuration"
    assert payload["metadata"]["passed_count"] == 0
    assert payload["tasks"][0]["status"] == "invalid_configuration"
    assert "config SHA-256" in payload["tasks"][0]["reason"]


def test_aggregate_preserves_invalid_leakage_over_integrity_failure(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "1" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 8, "task_id": "task-8", "domain": "os"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "invalid_leakage",
                    "reason": "task identity reached a model-facing request",
                    "config_sha256": "2" * 64,
                },
                "tasks": [],
            }
        ),
        encoding="utf-8",
    )

    payload = supervisor.aggregate(
        args, [task], [[task]], {}, [], "completed", "2026-09-02T00:00:00Z"
    )

    assert payload["metadata"]["status"] == "invalid_leakage"
    assert payload["tasks"][0]["status"] == "invalid_leakage"
    assert "task identity" in payload["tasks"][0]["reason"]
    assert "config SHA-256" in payload["tasks"][0]["reason"]


def test_aggregate_never_ingests_rows_from_invalid_worker(tmp_path: Path) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "3" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 9, "task_id": "task-9", "domain": "os"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "invalid_configuration",
                    "reason": "final worker seal changed",
                    "config_sha256": "3" * 64,
                },
                "tasks": [{**task, "status": "passed", "reward": 1.0}],
            }
        ),
        encoding="utf-8",
    )

    payload = supervisor.aggregate(
        args, [task], [[task]], {}, [], "completed", "2026-09-02T00:00:00Z"
    )

    assert payload["metadata"]["status"] == "invalid_configuration"
    assert payload["metadata"]["passed_count"] == 0
    assert payload["metadata"]["evaluator_reward_sum"] == 0
    assert payload["tasks"][0]["status"] == "invalid_configuration"
    assert payload["tasks"][0]["reward"] is None


@pytest.mark.parametrize("worker_status", ["completed", "invalid_configuration"])
def test_aggregate_preserves_task_row_leakage_over_worker_status(
    tmp_path: Path, worker_status: str
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "7" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 13, "task_id": "task-13", "domain": "os"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": worker_status,
                    "reason": "worker metadata reason",
                    "config_sha256": "7" * 64,
                    "task_order": ["task-13"],
                    "integrity_revalidation": {"status": "ok"},
                },
                "tasks": [
                    {
                        **task,
                        "status": "invalid_leakage",
                        "reward": None,
                        "reason": "task UUID reached model request",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    process = SimpleNamespace(pid=123, poll=lambda: 0)

    payload = supervisor.aggregate(
        args,
        [task],
        [[task]],
        {},
        [process],
        "finalizing",
        "2026-09-02T00:00:00Z",
    )

    assert payload["metadata"]["status"] == "invalid_leakage"
    assert payload["metadata"]["passed_count"] == 0
    assert payload["tasks"][0]["status"] == "invalid_leakage"
    assert "task UUID" in payload["tasks"][0]["reason"]


def test_aggregate_requires_completed_revalidated_zero_exit_worker(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "4" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 10, "task_id": "task-10", "domain": "multi_apps"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "running",
                    "config_sha256": "4" * 64,
                    "task_order": ["task-10"],
                },
                "tasks": [{**task, "status": "passed", "reward": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    process = SimpleNamespace(pid=123, poll=lambda: 1)

    payload = supervisor.aggregate(
        args,
        [task],
        [[task]],
        {},
        [process],
        "completed",
        "2026-09-02T00:00:00Z",
    )

    assert payload["metadata"]["status"] == "invalid_configuration"
    assert payload["tasks"][0]["status"] == "invalid_configuration"
    assert "not completed" in payload["tasks"][0]["reason"]
    assert "revalidation is not ok" in payload["tasks"][0]["reason"]
    assert "return code is not zero" in payload["tasks"][0]["reason"]


def test_aggregate_accepts_complete_revalidated_zero_exit_worker(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "6" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 12, "task_id": "task-12", "domain": "os"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "completed",
                    "config_sha256": "6" * 64,
                    "task_order": ["task-12"],
                    "integrity_revalidation": {"status": "ok"},
                },
                "tasks": [{**task, "status": "passed", "reward": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    process = SimpleNamespace(pid=123, poll=lambda: 0)

    payload = supervisor.aggregate(
        args,
        [task],
        [[task]],
        {},
        [process],
        "finalizing",
        "2026-09-02T00:00:00Z",
    )

    assert payload["metadata"]["status"] == "finalizing"
    assert payload["metadata"]["passed_count"] == 1
    assert payload["tasks"][0]["status"] == "passed"
    assert payload["tasks"][0]["reward"] == 1.0


@pytest.mark.parametrize(
    ("task_status", "reward", "reason_fragment"),
    [
        ("passed", 999, "passed task has invalid reward"),
        ("passed", None, "passed task has invalid reward"),
        ("passed", True, "passed task has invalid reward"),
        ("passed", 10**400, "passed task has invalid reward"),
        ("passed", float("nan"), "passed task has invalid reward"),
        ("passed", float("inf"), "passed task has invalid reward"),
        ("failed", 1.0, "failed task has invalid reward"),
        ("failed", None, "failed task has invalid reward"),
        ("model_protocol_failure", 0.0, "terminal task has a reward"),
    ],
)
def test_aggregate_rejects_inconsistent_terminal_rewards(
    tmp_path: Path,
    task_status: str,
    reward: object,
    reason_fragment: str,
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "8" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    task = {"order": 14, "task_id": "task-14", "domain": "os"}
    (worker_dir / "results.json").write_text(
        json.dumps(
            {
                "metadata": {
                    "status": "completed",
                    "config_sha256": "8" * 64,
                    "task_order": ["task-14"],
                    "integrity_revalidation": {"status": "ok"},
                },
                "tasks": [{**task, "status": task_status, "reward": reward}],
            }
        ),
        encoding="utf-8",
    )
    process = SimpleNamespace(pid=123, poll=lambda: 0)

    payload = supervisor.aggregate(
        args,
        [task],
        [[task]],
        {},
        [process],
        "finalizing",
        "2026-09-02T00:00:00Z",
    )

    assert payload["metadata"]["status"] == "invalid_configuration"
    assert payload["metadata"]["passed_count"] == 0
    assert payload["metadata"]["evaluator_reward_sum"] == 0
    assert payload["tasks"][0]["status"] == "invalid_configuration"
    assert reason_fragment in payload["tasks"][0]["reason"]


@pytest.mark.parametrize(
    ("worker_bytes", "reason_fragment"),
    [
        (b"{not-json", "unreadable"),
        (
            json.dumps(
                {
                    "metadata": {
                        "status": "completed",
                        "config_sha256": "5" * 64,
                        "task_order": ["task-11"],
                        "integrity_revalidation": {"status": "ok"},
                    },
                    "tasks": None,
                }
            ).encode(),
            "tasks field is not an array",
        ),
        (
            json.dumps(
                {
                    "metadata": {
                        "status": "completed",
                        "config_sha256": "5" * 64,
                        "task_order": ["task-11"],
                        "integrity_revalidation": {"status": "ok"},
                    },
                    "tasks": [
                        {
                            "order": 11,
                            "task_id": "task-11",
                            "domain": "os",
                            "status": "bogus",
                        }
                    ],
                }
            ).encode(),
            "task status is invalid",
        ),
        (
            json.dumps(
                {
                    "metadata": {
                        "status": "completed",
                        "config_sha256": "5" * 64,
                        "task_order": ["task-11"],
                        "integrity_revalidation": {"status": "ok"},
                    },
                    "tasks": [
                        {
                            "order": [],
                            "task_id": "task-11",
                            "domain": "os",
                            "status": "passed",
                        }
                    ],
                }
            ).encode(),
            "task order is invalid",
        ),
        (
            json.dumps(
                {
                    "metadata": {
                        "status": "completed",
                        "config_sha256": "5" * 64,
                        "task_order": ["task-11"],
                        "integrity_revalidation": {"status": "ok"},
                    },
                    "tasks": [
                        {
                            "order": True,
                            "task_id": "task-11",
                            "domain": "os",
                            "status": "passed",
                            "reward": 1.0,
                        }
                    ],
                }
            ).encode(),
            "task order is invalid",
        ),
        (
            json.dumps(
                {
                    "metadata": {
                        "status": "completed",
                        "config_sha256": "5" * 64,
                        "task_order": ["task-11"],
                        "integrity_revalidation": {"status": "ok"},
                    },
                    "tasks": ["not-an-object"],
                }
            ).encode(),
            "row is not an object",
        ),
    ],
)
def test_aggregate_fails_closed_on_malformed_worker_payload(
    tmp_path: Path, worker_bytes: bytes, reason_fragment: str
) -> None:
    config_path = tmp_path / "condition.json"
    config_path.write_text("{}", encoding="utf-8")
    args = _args(tmp_path, config_path)
    args.config_sha256 = "5" * 64
    worker_dir = args.result_dir / "workers" / "worker-01"
    worker_dir.mkdir(parents=True)
    (worker_dir / "results.json").write_bytes(worker_bytes)
    task = {"order": 11, "task_id": "task-11", "domain": "os"}
    process = SimpleNamespace(pid=123, poll=lambda: 0)

    payload = supervisor.aggregate(
        args,
        [task],
        [[task]],
        {},
        [process],
        "completed",
        "2026-09-02T00:00:00Z",
    )

    assert payload["metadata"]["status"] == "invalid_configuration"
    assert reason_fragment in payload["tasks"][0]["reason"]


def test_worker_command_forwards_soft_restart_controls_with_legacy_defaults(
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        python="python",
        runner=tmp_path / "runner.py",
        supervisor=tmp_path / "supervisor.py",
        config=tmp_path / "condition.json",
        config_sha256="a" * 64,
        result_dir=tmp_path / "results",
        model="qwen3.5-4b",
        base_urls=["http://endpoint/v1"],
        workers=1,
        api_key="EMPTY",
        max_steps=9,
        max_no_progress_steps=4,
        max_agent_seconds=30.0,
        top_k=7,
        max_output_tokens=512,
        request_timeout=10.0,
        model_retries=1,
        evaluator_file_fetch_attempts=1,
        evaluator_file_fetch_delay_seconds=0.0,
        max_local_steps=3,
        max_soft_restarts=2,
        thinking=False,
        reasoning_effort=None,
        holo_base_url=None,
        holo_model=None,
        holo_api_key=None,
        holo_reasoning_effort=None,
        holo_max_output_tokens=1024,
        holo_temperature=0.8,
        holo_request_timeout=10.0,
        no_gui=True,
    )
    task = [{"order": 1}]

    command = supervisor.worker_command(args, 1, task)

    assert command[command.index("--expected-config-sha256") + 1] == "a" * 64
    assert command[command.index("--supervisor") + 1] == str(args.supervisor)
    assert command[command.index("--max-local-steps") + 1] == "3"
    assert command[command.index("--max-soft-restarts") + 1] == "2"

    # Older callers may construct a Namespace before these options existed.
    legacy_values = vars(args).copy()
    legacy_values.pop("max_local_steps")
    legacy_values.pop("max_soft_restarts")
    legacy_command = supervisor.worker_command(
        SimpleNamespace(**legacy_values), 1, task
    )
    assert "--max-local-steps" not in legacy_command
    assert legacy_command[legacy_command.index("--max-soft-restarts") + 1] == "1"

    # Binary Holo mode must suppress the legacy default effort flag.
    args.holo_reasoning_mode = "thinking"
    mode_command = supervisor.worker_command(args, 1, task)
    assert "--holo-reasoning-mode" in mode_command
    assert "--holo-reasoning-effort" not in mode_command


@pytest.mark.parametrize(
    ("extra_args", "minimum_free_gib"),
    [([], 30.0), (["--min-free-gib", "45"], 45.0)],
)
def test_supervisor_disk_stop_line_default_and_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra_args: list[str],
    minimum_free_gib: float,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "supervise_lite_agent_parallel.py",
            "--config",
            str(tmp_path / "config.json"),
            "--result-dir",
            str(tmp_path / "results"),
            *extra_args,
        ],
    )

    assert supervisor.parse_args().min_free_gib == minimum_free_gib


@pytest.mark.parametrize(
    ("extra_args", "temperature"),
    [([], 0.0), (["--temperature", "1.0"], 1.0)],
)
def test_supervisor_forwards_qwen_temperature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra_args: list[str],
    temperature: float,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "supervise_lite_agent_parallel.py",
            "--config",
            str(tmp_path / "config.json"),
            "--result-dir",
            str(tmp_path / "results"),
            *extra_args,
        ],
    )
    args = supervisor.parse_args()
    args.config_sha256 = "a" * 64

    command = supervisor.worker_command(args, 1, [{"order": 1}])

    assert args.temperature == temperature
    assert float(command[command.index("--temperature") + 1]) == temperature


def test_supervisor_holo_cli_defaults_are_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOLO_BASE_URL", raising=False)
    monkeypatch.delenv("HOLO_MODEL", raising=False)
    monkeypatch.delenv("HOLO_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("HOLO_REASONING_MODE", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "supervise_lite_agent_parallel.py",
            "--config",
            str(tmp_path / "config.json"),
            "--result-dir",
            str(tmp_path / "results"),
        ],
    )

    args = supervisor.parse_args()

    assert args.holo_base_url is None
    assert args.holo_model is None
    assert args.holo_reasoning_effort is None
    assert args.holo_reasoning_mode is None


def test_supervisor_binary_holo_cli_does_not_add_legacy_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HOLO_MODEL", raising=False)
    monkeypatch.delenv("HOLO_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("HOLO_REASONING_MODE", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "supervise_lite_agent_parallel.py",
            "--config",
            str(tmp_path / "config.json"),
            "--result-dir",
            str(tmp_path / "results"),
            "--holo-base-url",
            "http://holo/v1",
            "--holo-model",
            "holo3.1-4b",
            "--holo-reasoning-mode",
            "thinking",
        ],
    )

    args = supervisor.parse_args()

    assert args.holo_reasoning_mode == "thinking"
    assert args.holo_reasoning_effort is None


def test_reasoning_gate_requires_explicit_provider_maximum() -> None:
    config = {
        "protocol": {
            "reasoning_effort": "max",
            "thinking": True,
        },
        "model": {
            "requested": "qwen3.5-4b",
            "reasoning_effort": "max",
            # Deliberately omit provider_max_reasoning_effort.
        },
    }
    args = SimpleNamespace(
        model="qwen3.5-4b",
        thinking=True,
        reasoning_effort="max",
    )

    with pytest.raises(RuntimeError, match="provider_max_reasoning_effort"):
        _validate_common_args(config, args)


def test_qwen_binary_thinking_gate_does_not_require_numeric_provider_maximum() -> None:
    """Qwen3.5's native contract is a boolean switch, not an effort ladder."""
    config = {
        "protocol": {
            "reasoning_mode": "thinking",
            "thinking": True,
            "max_local_steps": 3,
            "max_soft_restarts": 1,
            "max_steps": 4,
            "max_no_progress_steps": 4,
            "max_agent_seconds": 30.0,
            "top_k": 7,
            "max_output_tokens": 512,
            "request_timeout": 10.0,
            "model_retries": 1,
            "gui_enabled": True,
            "evaluator_file_fetch_attempts": 1,
            "evaluator_file_fetch_delay_seconds": 0.0,
        },
        "model": {
            "requested": "qwen3.5-4b",
            "reasoning_mode": "thinking",
            # There is intentionally no provider_max_reasoning_mode field.
        },
    }
    args = SimpleNamespace(
        model="qwen3.5-4b",
        thinking=True,
        reasoning_mode="thinking",
        reasoning_effort=None,
        max_local_steps=3,
        max_soft_restarts=1,
        max_steps=4,
        max_no_progress_steps=4,
        max_agent_seconds=30.0,
        top_k=7,
        max_output_tokens=512,
        request_timeout=10.0,
        model_retries=1,
        no_gui=False,
        evaluator_file_fetch_attempts=1,
        evaluator_file_fetch_delay_seconds=0.0,
    )

    _validate_common_args(config, args)


def test_qwen_binary_mode_rejects_conflicting_optional_provider_annotation() -> None:
    config = {
        "protocol": {"reasoning_mode": "thinking", "thinking": True},
        "model": {
            "requested": "qwen3.5-4b",
            "reasoning_mode": "thinking",
            "provider_max_reasoning_mode": "non_thinking",
        },
    }
    args = SimpleNamespace(
        model="qwen3.5-4b",
        thinking=True,
        reasoning_mode="thinking",
        reasoning_effort=None,
    )

    with pytest.raises(RuntimeError, match="provider_max_reasoning_mode"):
        _validate_common_args(config, args)


def _hybrid_condition() -> tuple[dict, SimpleNamespace]:
    config = {
        "protocol": {
            "reasoning_mode": "thinking",
            "thinking": True,
            "max_steps": 30,
            "max_local_steps": 15,
            "max_soft_restarts": 1,
            "max_no_progress_steps": 8,
            "max_agent_seconds": 900.0,
            "top_k": 7,
            "max_output_tokens": 4096,
            "request_timeout": 240.0,
            "model_retries": 3,
            "gui_enabled": True,
            "evaluator_file_fetch_attempts": 3,
            "evaluator_file_fetch_delay_seconds": 1.0,
            "gui_model": {
                "provider": "holo",
                "requested": "holo3.1-4b",
                "model": "holo3.1-4b",
                "base_url": "http://holo/v1",
                "reasoning_mode": "thinking",
                "max_output_tokens": 1024,
                "temperature": 0.8,
                "request_timeout_seconds": 180.0,
            },
        },
        "model": {
            "requested": "qwen3.5-4b",
            "reasoning_mode": "thinking",
        },
    }
    args = SimpleNamespace(
        model="qwen3.5-4b",
        thinking=True,
        reasoning_mode="thinking",
        reasoning_effort=None,
        max_steps=30,
        max_local_steps=15,
        max_soft_restarts=1,
        max_no_progress_steps=8,
        max_agent_seconds=900.0,
        top_k=7,
        max_output_tokens=4096,
        request_timeout=240.0,
        model_retries=3,
        no_gui=False,
        evaluator_file_fetch_attempts=3,
        evaluator_file_fetch_delay_seconds=1.0,
        holo_base_url="http://holo/v1",
        holo_model="holo3.1-4b",
        holo_reasoning_mode="thinking",
        holo_reasoning_effort=None,
        holo_max_output_tokens=1024,
        holo_temperature=0.8,
        holo_request_timeout=180.0,
    )
    return config, args


def test_hybrid_condition_freezes_holo_and_soft_restart_controls() -> None:
    config, args = _hybrid_condition()

    _validate_common_args(config, args)


@pytest.mark.parametrize(
    ("argument", "replacement", "error_name"),
    [
        ("max_local_steps", 14, "max_local_steps"),
        ("max_soft_restarts", 0, "max_soft_restarts"),
        ("holo_base_url", "http://other/v1", "holo_base_url"),
        ("holo_model", "other-model", "holo_model"),
        ("holo_reasoning_mode", "non_thinking", "holo_reasoning_mode"),
        ("holo_max_output_tokens", 2048, "holo_max_output_tokens"),
        ("holo_temperature", 0.0, "holo_temperature"),
        ("holo_request_timeout", 60.0, "holo_request_timeout"),
    ],
)
def test_hybrid_condition_rejects_cli_drift(
    argument: str, replacement: object, error_name: str
) -> None:
    config, args = _hybrid_condition()
    setattr(args, argument, replacement)

    with pytest.raises(RuntimeError, match=error_name):
        _validate_common_args(config, args)


def test_hybrid_condition_rejects_mixed_holo_reasoning_controls() -> None:
    config, args = _hybrid_condition()
    args.holo_reasoning_effort = "max"

    with pytest.raises(RuntimeError, match="binary Holo mode"):
        _validate_common_args(config, args)


def test_condition_without_holo_rejects_holo_cli_enablement() -> None:
    config, args = _hybrid_condition()
    config["protocol"].pop("gui_model")

    with pytest.raises(RuntimeError, match="require a frozen protocol.gui_model"):
        _validate_common_args(config, args)


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        " http://holo/v1",
        "holo/v1",
        "ftp://holo/v1",
        "http://HOLO/v1",
        "http://user@holo/v1",
        "http://holo/v1/",
        "http://holo/v1?condition=other",
        "http://holo/v1#fragment",
        "http://holo/v1/../other",
    ],
)
def test_hybrid_condition_rejects_empty_or_noncanonical_holo_url(
    base_url: str,
) -> None:
    config, args = _hybrid_condition()
    config["protocol"]["gui_model"]["base_url"] = base_url
    args.holo_base_url = base_url

    with pytest.raises(RuntimeError, match="Holo base_url"):
        _validate_common_args(config, args)


def _promotion_config() -> dict:
    source_commit = "a" * 40
    return {
        "status": "frozen",
        "tasks": [{"order": 1, "task_id": "task-1", "domain": "os"}],
        "sources": {"source_git_commit": source_commit},
        # Existing fixed-189 manifests use this top-level object. The gate must
        # not depend on a newly invented nested flag being present.
        "promotion_gate": {"pre_registered_before_fixed189_result": True},
        "condition": {
            "schema_version": "trusted_generic_only_condition.v1",
            "enforced": True,
            "role": "fixed189",
            "result_directory": "results/run1",
            "source_tree": {},
            "source_git_commit": source_commit,
            "source_dirty": False,
            "baseline_candidate": True,
            "promotion_pre_authorized": True,
        },
        "protocol": {
            "runs": 1,
            "best_of": False,
            "preserve_every_attempt": True,
            "task_specific_or_golden_exposed": False,
            "guest_proxy": False,
            "supervisor": "scripts/supervise_lite_agent_parallel.py",
            "runner": "scripts/run_lite_agent_pilot.py",
            "python": sys.executable,
        },
        "model": {"base_urls": ["http://model/v1"]},
        "vm": {
            "screen_size": [1920, 1080],
            "image": "third_party/OSWorld/docker_vm_data/Ubuntu.qcow2",
        },
        "osworld_commit": "b" * 40,
    }


def _promotion_runtime_args() -> SimpleNamespace:
    return SimpleNamespace(
        supervisor=frozen_condition.V2_ROOT
        / "scripts"
        / "supervise_lite_agent_parallel.py",
        runner=frozen_condition.V2_ROOT / "scripts" / "run_lite_agent_pilot.py",
        python=sys.executable,
    )


@pytest.mark.parametrize(
    "activation", ["top_level", "role", "candidate", "smoke", "validation"]
)
def test_promotion_gate_is_derived_from_existing_condition_semantics(
    activation: str,
) -> None:
    config = _promotion_config()
    config.pop("promotion_gate")
    condition = config["condition"]
    condition["role"] = "diagnostic"
    condition["baseline_candidate"] = False
    condition["promotion_pre_authorized"] = False
    if activation == "top_level":
        config["promotion_gate"] = {"pre_registered": True}
    elif activation == "role":
        condition["role"] = "fixed189"
    elif activation == "candidate":
        condition["baseline_candidate"] = True
    else:
        condition["role"] = f"development_{activation}"

    assert frozen_condition._promotion_gate_required(config, condition) is True


@pytest.mark.parametrize("role", ["smokescreen_diagnostic", "validationless_probe"])
def test_promotion_role_markers_require_token_boundaries(role: str) -> None:
    config = _promotion_config()
    config.pop("promotion_gate")
    condition = config["condition"]
    condition["role"] = role
    condition["baseline_candidate"] = False
    condition["promotion_pre_authorized"] = False

    assert frozen_condition._promotion_gate_required(config, condition) is False


@pytest.mark.parametrize("role", ["smoke", "validation"])
def test_historical_promotion_role_requires_resealed_repository_metadata(
    role: str,
) -> None:
    config = _promotion_config()
    config.pop("promotion_gate")
    config.pop("sources")
    condition = config["condition"]
    condition["role"] = role
    condition["baseline_candidate"] = False
    condition["promotion_pre_authorized"] = False
    condition.pop("source_git_commit")

    with pytest.raises(RuntimeError, match="source_git_commit"):
        frozen_condition.validate_frozen_config(config)


def test_legacy_nonpromotion_condition_does_not_require_new_runtime_fields() -> None:
    config = _promotion_config()
    config.pop("promotion_gate")
    config.pop("sources")
    config.pop("osworld_commit")
    condition = config["condition"]
    condition["role"] = "diagnostic"
    condition["baseline_candidate"] = False
    condition["promotion_pre_authorized"] = False
    condition.pop("source_git_commit")
    condition.pop("source_dirty")
    config["protocol"].pop("supervisor")
    config["protocol"].pop("runner")
    config["protocol"].pop("python")

    assert frozen_condition.validate_frozen_config(config) is condition


def test_promotion_gate_requires_clean_full_commit_metadata() -> None:
    config = _promotion_config()

    frozen_condition.validate_frozen_config(config)

    config["condition"]["source_dirty"] = True
    with pytest.raises(RuntimeError, match="source_dirty=false"):
        frozen_condition.validate_frozen_config(config)


def test_promotion_gate_rejects_source_commit_metadata_mismatch() -> None:
    config = _promotion_config()
    config["sources"]["source_git_commit"] = "c" * 40

    with pytest.raises(RuntimeError, match="sources.source_git_commit"):
        frozen_condition.validate_frozen_config(config)


@pytest.mark.parametrize(
    ("attribute", "replacement", "error_name"),
    [
        ("supervisor", Path("/tmp/not-the-supervisor.py"), "supervisor"),
        ("runner", Path("/tmp/not-the-runner.py"), "runner"),
        ("python", "/tmp/not-the-python", "python"),
    ],
)
def test_promotion_gate_rejects_runtime_entrypoint_drift(
    tmp_path: Path,
    attribute: str,
    replacement: object,
    error_name: str,
) -> None:
    config = _promotion_config()
    args = _promotion_runtime_args()
    setattr(args, attribute, replacement)

    with pytest.raises(RuntimeError, match=error_name):
        frozen_condition._validate_promotion_runtime(config, args, tmp_path)


def test_promotion_gate_records_frozen_runtime_entrypoints(tmp_path: Path) -> None:
    config = _promotion_config()

    runtime = frozen_condition._validate_promotion_runtime(
        config, _promotion_runtime_args(), tmp_path
    )

    assert runtime == {
        "supervisor": str(
            frozen_condition.V2_ROOT / "scripts" / "supervise_lite_agent_parallel.py"
        ),
        "runner": str(frozen_condition.V2_ROOT / "scripts" / "run_lite_agent_pilot.py"),
        "python": str(Path(sys.executable).resolve()),
    }


def test_runner_gate_records_frozen_runtime_entrypoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _promotion_config()
    runner = frozen_condition.V2_ROOT / "scripts" / "run_lite_agent_pilot.py"
    monkeypatch.setattr(sys, "argv", [str(runner)])

    runtime = frozen_condition._validate_runner_runtime(config)

    assert runtime == {
        "runner": str(runner),
        "python": str(Path(sys.executable).resolve()),
    }


@pytest.mark.parametrize("drift", ["runner", "python"])
def test_runner_gate_rejects_its_own_runtime_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    config = _promotion_config()
    runner = frozen_condition.V2_ROOT / "scripts" / "run_lite_agent_pilot.py"
    monkeypatch.setattr(sys, "argv", [str(runner)])
    if drift == "runner":
        sys.argv[0] = str(tmp_path / "alternate-runner.py")
    else:
        monkeypatch.setattr(sys, "executable", str(tmp_path / "alternate-python"))

    with pytest.raises(RuntimeError, match=drift):
        frozen_condition._validate_runner_runtime(config)


@pytest.mark.parametrize(
    ("field", "value", "error_name"),
    [
        ("result_directory", "/tmp/results", "project-relative"),
        ("result_directory", "../../results", "escapes the project root"),
        ("image", "/tmp/Ubuntu.qcow2", "project-relative"),
        ("image", "../../Ubuntu.qcow2", "escapes the project root"),
    ],
)
def test_promotion_gate_rejects_paths_outside_project_root(
    tmp_path: Path, field: str, value: str, error_name: str
) -> None:
    config = _promotion_config()
    if field == "image":
        config["vm"][field] = value
    else:
        config["condition"][field] = value

    with pytest.raises(RuntimeError, match=error_name):
        frozen_condition._validate_promotion_runtime(
            config, _promotion_runtime_args(), tmp_path
        )


def _fake_repository_git(
    config: dict, condition: dict, *, osworld_status: str = "?? .conda/bin/python\n"
):
    def fake_git_stdout(cwd: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "--show-toplevel"):
            return str(cwd.resolve())
        if arguments == ("rev-parse", "--absolute-git-dir"):
            return str((cwd / ".git").resolve())
        if arguments == ("rev-parse", "HEAD"):
            return (
                config["osworld_commit"]
                if cwd.name == "OSWorld"
                else condition["source_git_commit"]
            )
        if cwd.name == "OSWorld" and arguments[0] == "status":
            return osworld_status
        return ""

    return fake_git_stdout


def test_promotion_gate_verifies_repository_and_pinned_osworld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _promotion_config()
    condition = frozen_condition.validate_frozen_config(config)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    base_git_stdout = _fake_repository_git(config, condition)

    def fake_git_stdout(cwd: Path, *arguments: str) -> str:
        calls.append((cwd, arguments))
        return base_git_stdout(cwd, *arguments)

    monkeypatch.setattr(frozen_condition, "_git_stdout", fake_git_stdout)

    repository_state = frozen_condition._verify_repository_state(config, condition)

    assert repository_state is not None
    assert repository_state["source_git_commit"] == "a" * 40
    assert repository_state["source_dirty"] is False
    assert repository_state["osworld_commit"] == "b" * 40
    assert repository_state["source_repository"]["toplevel"] == str(
        frozen_condition.PROJECT_ROOT
    )
    assert repository_state["osworld_allowed_untracked_prefixes"] == [".conda/"]
    assert any(arguments[0] == "status" for _, arguments in calls)


def test_promotion_gate_rejects_dirty_active_source_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _promotion_config()
    condition = frozen_condition.validate_frozen_config(config)

    base_git_stdout = _fake_repository_git(config, condition)

    def fake_git_stdout(cwd: Path, *arguments: str) -> str:
        if cwd.name != "OSWorld" and arguments[0] == "status":
            return " M adapter_versions/v2_expanded/scripts/runtime.py"
        return base_git_stdout(cwd, *arguments)

    monkeypatch.setattr(frozen_condition, "_git_stdout", fake_git_stdout)

    with pytest.raises(RuntimeError, match="source scope is dirty"):
        frozen_condition._verify_repository_state(config, condition)


def test_promotion_gate_rejects_untracked_osworld_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _promotion_config()
    condition = frozen_condition.validate_frozen_config(config)
    monkeypatch.setattr(
        frozen_condition,
        "_git_stdout",
        _fake_repository_git(
            config,
            condition,
            osworld_status="?? .conda/bin/python\n?? desktop_env/evaluators/override.py\n",
        ),
    )

    with pytest.raises(RuntimeError, match="desktop_env/evaluators/override.py"):
        frozen_condition._verify_repository_state(config, condition)


def test_git_check_uses_fixed_binary_and_clears_git_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}
    monkeypatch.setenv("GIT_DIR", "/tmp/alternate.git")
    monkeypatch.setenv("GIT_WORK_TREE", "/tmp/alternate-worktree")

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        observed["command"] = command
        observed["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="trusted\n", stderr="")

    monkeypatch.setattr(frozen_condition.subprocess, "run", fake_run)

    assert frozen_condition._git_stdout(Path.cwd(), "rev-parse", "HEAD") == "trusted"
    assert observed["command"][:2] == [
        str(frozen_condition.TRUSTED_GIT),
        "--no-optional-locks",
    ]
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert not any(str(key).upper().startswith("GIT_") for key in environment)


def test_git_failure_is_reported_as_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_git(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess:
        raise subprocess.CalledProcessError(
            128, [str(frozen_condition.TRUSTED_GIT)], stderr="fatal: bad repository"
        )

    monkeypatch.setattr(frozen_condition.subprocess, "run", fail_git)

    with pytest.raises(RuntimeError, match="Git repository check failed"):
        frozen_condition._git_stdout(Path.cwd(), "rev-parse", "HEAD")


def test_revalidate_frozen_inputs_rechecks_seal_and_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = _promotion_config()
    condition = config["condition"]
    source_tree = {"sha256": "current-seal"}
    repository_state = {"source_git_commit": "a" * 40}
    calls: list[str] = []

    def validate(observed_config: dict) -> dict:
        assert observed_config is config
        calls.append("config")
        return condition

    def verify_source(observed_condition: dict) -> dict:
        assert observed_condition is condition
        calls.append("source")
        return source_tree

    def verify_repository(observed_config: dict, observed_condition: dict) -> dict:
        assert observed_config is config
        assert observed_condition is condition
        calls.append("repository")
        return repository_state

    monkeypatch.setattr(frozen_condition, "validate_frozen_config", validate)
    monkeypatch.setattr(frozen_condition, "_verify_source_tree", verify_source)
    monkeypatch.setattr(frozen_condition, "_verify_repository_state", verify_repository)

    assert frozen_condition.revalidate_frozen_inputs(config) == {
        "condition": condition,
        "source_tree": source_tree,
        "repository_state": repository_state,
    }
    assert calls == ["config", "source", "repository"]


def test_final_supervisor_integrity_rechecks_both_configs_and_frozen_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = b'{"status":"frozen"}\n'
    config_path = tmp_path / "condition.json"
    snapshot_path = tmp_path / "run" / "frozen-config.json"
    snapshot_path.parent.mkdir()
    config_path.write_bytes(raw)
    snapshot_path.write_bytes(raw)
    digest = supervisor.hashlib.sha256(raw).hexdigest()
    args = SimpleNamespace(
        config=config_path,
        worker_config=snapshot_path,
        config_sha256=digest,
    )
    frozen_inputs = {
        "source_tree": {"sha256": "sealed-source"},
        "repository_state": {"source_git_commit": "a" * 40},
    }
    monkeypatch.setattr(
        supervisor, "revalidate_frozen_inputs", lambda config: frozen_inputs
    )

    assert supervisor.final_supervisor_integrity({"status": "frozen"}, args) == {
        "status": "ok",
        "config_sha256": digest,
        "worker_config_sha256": digest,
        "source_tree_sha256": "sealed-source",
        "repository_state": {"source_git_commit": "a" * 40},
    }

    snapshot_path.chmod(0o644)
    snapshot_path.write_text('{"status":"changed"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="worker config snapshot changed"):
        supervisor.final_supervisor_integrity({"status": "frozen"}, args)


def test_condition_level_invalidation_zeroes_scores_and_preserves_leakage() -> None:
    payload = {
        "metadata": {
            "status": "invalid_leakage",
            "passed_count": 1,
            "success_rate": 1.0,
            "evaluator_reward_sum": 1.0,
            "evaluator_reward_mean": 1.0,
        },
        "tasks": [
            {"status": "passed", "reward": 1.0, "path_class": "generic_api_only"},
            {"status": "invalid_leakage", "reward": None},
        ],
    }

    supervisor.invalidate_aggregate_payload(
        payload,
        status="invalid_configuration",
        reason="source changed",
    )

    assert payload["metadata"]["status"] == "invalid_leakage"
    assert payload["metadata"]["status_counts"] == {"invalid_leakage": 2}
    assert payload["metadata"]["passed_count"] == 0
    assert payload["metadata"]["success_rate"] is None
    assert payload["metadata"]["evaluator_reward_sum"] == 0
    assert payload["metadata"]["evaluator_reward_mean"] is None
    assert {row["status"] for row in payload["tasks"]} == {"invalid_leakage"}
    assert all(row["reward"] is None for row in payload["tasks"])


def test_final_integrity_interrupt_cannot_publish_completed_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result_path = tmp_path / "results.json"
    payload = {
        "metadata": {
            "status": "finalizing",
            "passed_count": 1,
            "status_counts": {"passed": 1},
        },
        "tasks": [{"status": "passed", "reward": 1.0}],
    }
    supervisor.write_json(result_path, payload)
    monkeypatch.setattr(
        supervisor,
        "final_supervisor_integrity",
        lambda *_args: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(KeyboardInterrupt):
        supervisor.publish_final_supervisor_result(
            result_path,
            {},
            SimpleNamespace(),
            payload,
        )

    persisted = json.loads(result_path.read_text())
    assert persisted["metadata"]["status"] == "finalizing"
    assert "final_integrity" not in persisted["metadata"]


def test_final_integrity_failure_publishes_non_scored_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result_path = tmp_path / "results.json"
    payload = {
        "metadata": {
            "status": "finalizing",
            "passed_count": 1,
            "success_rate": 1.0,
            "evaluator_reward_sum": 1.0,
            "evaluator_reward_mean": 1.0,
            "status_counts": {"passed": 1},
        },
        "tasks": [{"status": "passed", "reward": 1.0}],
    }
    supervisor.write_json(result_path, payload)
    monkeypatch.setattr(
        supervisor,
        "final_supervisor_integrity",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("source seal changed")),
    )

    supervisor.publish_final_supervisor_result(
        result_path,
        {},
        SimpleNamespace(),
        payload,
    )

    persisted = json.loads(result_path.read_text())
    assert persisted["metadata"]["status"] == "invalid_configuration"
    assert persisted["metadata"]["passed_count"] == 0
    assert persisted["metadata"]["success_rate"] is None
    assert persisted["metadata"]["evaluator_reward_sum"] == 0
    assert persisted["tasks"][0]["status"] == "invalid_configuration"
    assert persisted["tasks"][0]["reward"] is None
    assert persisted["metadata"]["final_integrity"]["status"] == "error"


def test_promotion_gate_rejects_empty_task_set() -> None:
    config = _promotion_config()
    config["tasks"] = []

    with pytest.raises(RuntimeError, match="non-empty frozen task set"):
        frozen_condition.validate_frozen_config(config)


@pytest.mark.parametrize(
    ("task", "reason"),
    [
        ({"order": True, "task_id": "task-1", "domain": "os"}, "positive integer"),
        ({"order": 1, "task_id": "", "domain": "os"}, "task_id"),
        ({"order": 1, "task_id": "task-1", "domain": ""}, "domain"),
    ],
)
def test_promotion_gate_rejects_malformed_task_identity(
    task: dict, reason: str
) -> None:
    config = _promotion_config()
    config["tasks"] = [task]

    with pytest.raises(RuntimeError, match=reason):
        frozen_condition.validate_frozen_config(config)


def test_promotion_gate_rejects_duplicate_task_identity() -> None:
    config = _promotion_config()
    config["tasks"] = [
        {"order": 1, "task_id": "task-1", "domain": "os"},
        {"order": 2, "task_id": "task-1", "domain": "multi_apps"},
    ]

    with pytest.raises(RuntimeError, match="duplicate identity"):
        frozen_condition.validate_frozen_config(config)
