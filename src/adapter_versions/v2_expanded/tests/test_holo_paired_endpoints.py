from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from scripts import run_lite_agent_pilot as runner
from scripts import supervise_lite_agent_parallel as supervisor
from scripts.frozen_condition import _validate_holo_args


ENDPOINTS = ["https://holo1.invalid/v1", "https://holo2.invalid/v1"]


def _supervisor_args(tmp_path: Path, monkeypatch, *, paired: bool = True):
    monkeypatch.setenv("HOLO_BASE_URL", "https://legacy.invalid/v1")
    monkeypatch.delenv("HOLO_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "supervisor",
            "--config",
            str(tmp_path / "condition.json"),
            "--result-dir",
            str(tmp_path / "results"),
            "--workers",
            "14",
            "--base-urls",
            *ENDPOINTS,
            "--model",
            "holo3.1-4b",
            "--thinking",
            "--reasoning-mode",
            "thinking",
            "--max-steps",
            "100",
            "--max-local-steps",
            "50",
            "--max-soft-restarts",
            "1",
            "--max-agent-seconds",
            "1800",
            "--holo-model",
            "holo3.1-4b",
            "--holo-reasoning-mode",
            "thinking",
            *(["--holo-base-urls", *ENDPOINTS] if paired else []),
        ],
    )
    args = supervisor.parse_args()
    args.config_sha256 = "a" * 64
    return args


def _paired_protocol():
    return {
        "gui_enabled": True,
        "gui_model": {
            "provider": "holo",
            "requested": "holo3.1-4b",
            "model": "holo3.1-4b",
            "base_urls": ENDPOINTS,
            "endpoint_assignment": "paired_with_primary",
            "reasoning_mode": "thinking",
            "max_output_tokens": 1024,
            "temperature": 0.8,
            "request_timeout_seconds": 180.0,
        },
    }


def _option(command: list[str], name: str) -> str:
    return command[command.index(name) + 1]


def test_paired_workers_share_primary_and_visual_endpoint_with_seven_per_endpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    args = _supervisor_args(tmp_path, monkeypatch)
    protocol = _paired_protocol()
    _validate_holo_args(protocol, args, primary_base_urls=ENDPOINTS)
    assignments = []
    for index in range(1, 15):
        command = supervisor.worker_command(args, index, [{"order": index}])
        primary = _option(command, "--base-url")
        visual = _option(command, "--holo-base-url")
        assert primary == visual == ENDPOINTS[(index - 1) // 7]
        assignments.append(primary)
        assert _option(command, "--model") == "holo3.1-4b"
        assert _option(command, "--reasoning-mode") == "thinking"
        assert _option(command, "--holo-reasoning-mode") == "thinking"
        assert "--thinking" in command
        assert _option(command, "--max-steps") == "100"
        assert _option(command, "--max-local-steps") == "50"
        assert _option(command, "--max-soft-restarts") == "1"
        assert _option(command, "--max-agent-seconds") == "1800.0"
        assert _option(command, "--temperature") == "0.0"
        assert _option(command, "--holo-temperature") == "0.8"

        worker_values = vars(args).copy()
        worker_values.pop("base_urls")
        worker_values.pop("holo_base_urls")
        worker_values.update(base_url=primary, holo_base_url=visual)
        worker_args = SimpleNamespace(**worker_values)
        _validate_holo_args(protocol, worker_args, primary_base_urls=ENDPOINTS)
        settings = runner._holo_model_settings(worker_args, {"protocol": protocol})
        assert settings["base_url"] == primary
        assert settings["reasoning_mode"] == "thinking"
    assert Counter(assignments) == {endpoint: 7 for endpoint in ENDPOINTS}


def test_legacy_single_visual_endpoint_is_preserved(
    tmp_path: Path, monkeypatch
) -> None:
    args = _supervisor_args(tmp_path, monkeypatch, paired=False)
    for index in (1, 14):
        command = supervisor.worker_command(args, index, [{"order": index}])
        assert _option(command, "--holo-base-url") == "https://legacy.invalid/v1"


def test_paired_worker_rejects_other_declared_visual_endpoint() -> None:
    protocol = _paired_protocol()
    args = SimpleNamespace(base_url=ENDPOINTS[0], holo_base_url=ENDPOINTS[1])
    with pytest.raises(RuntimeError, match="holo_base_url"):
        _validate_holo_args(protocol, args, primary_base_urls=ENDPOINTS)
    with pytest.raises(ValueError, match="must match the worker primary endpoint"):
        runner._holo_model_settings(args, {"protocol": protocol})


def test_paired_settings_resolve_visual_endpoint_from_worker_primary() -> None:
    for primary in ENDPOINTS:
        settings = runner._holo_model_settings(
            SimpleNamespace(base_url=primary), {"protocol": _paired_protocol()}
        )
        assert settings["base_url"] == primary


def test_supervisor_rejects_reordered_visual_endpoints(
    tmp_path: Path, monkeypatch
) -> None:
    _supervisor_args(tmp_path, monkeypatch)
    argv = sys.argv.copy()
    start = argv.index("--holo-base-urls") + 1
    argv[start:] = list(reversed(ENDPOINTS))
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit):
        supervisor.parse_args()
