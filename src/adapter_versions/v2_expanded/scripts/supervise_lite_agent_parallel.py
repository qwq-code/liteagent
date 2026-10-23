#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent if ROOT.name == "baseline" else ROOT.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.frozen_condition import (  # noqa: E402
    enforce_supervisor_condition,
    revalidate_frozen_inputs,
)
from integrations.lite_agent.reasoning import (  # noqa: E402
    SUPPORTED_REASONING_EFFORTS,
    SUPPORTED_REASONING_MODES,
)


DEFAULT_RUNNER = ROOT / "scripts" / "run_lite_agent_pilot.py"
DEFAULT_POLL_SECONDS = 5.0
DEFAULT_HEARTBEAT_SECONDS = 600.0
TERMINAL_STATUSES = {
    "passed",
    "failed",
    "invalid_configuration",
    "invalid_leakage",
    "model_protocol_failure",
    "model_transport_failure",
    "agent_failure",
    "agent_deadline_exhausted",
    "evaluation_failure",
}
WORKER_TASK_STATUSES = TERMINAL_STATUSES | {"environment_failure", "interrupted"}
COMPLETED_WORKER_TASK_STATUSES = WORKER_TASK_STATUSES - {
    "invalid_configuration",
    "invalid_leakage",
    "interrupted",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def progress_report_due(
    *,
    now: float,
    next_heartbeat: float,
    counts: dict[str, int],
    previous_counts: dict[str, int] | None,
) -> bool:
    return previous_counts is None or counts != previous_counts or now >= next_heartbeat


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def read_config_snapshot(path: Path) -> tuple[dict[str, Any], bytes, str]:
    """Read and hash one immutable supervisor-side config snapshot."""
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload, raw, hashlib.sha256(raw).hexdigest()


def write_config_snapshot(path: Path, raw: bytes) -> None:
    """Persist the exact gated bytes that every worker must consume."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(raw)
    temporary.replace(path)
    path.chmod(0o444)


def final_supervisor_integrity(
    config: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    """Revalidate immutable config and source inputs after all workers exit."""
    original_config_sha256 = hashlib.sha256(args.config.read_bytes()).hexdigest()
    snapshot_sha256 = hashlib.sha256(args.worker_config.read_bytes()).hexdigest()
    if original_config_sha256 != args.config_sha256:
        raise RuntimeError("source config changed after the supervisor gate")
    if snapshot_sha256 != args.config_sha256:
        raise RuntimeError("worker config snapshot changed during the run")
    frozen_inputs = revalidate_frozen_inputs(config)
    return {
        "status": "ok",
        "config_sha256": original_config_sha256,
        "worker_config_sha256": snapshot_sha256,
        "source_tree_sha256": frozen_inputs["source_tree"]["sha256"],
        "repository_state": frozen_inputs["repository_state"],
    }


def verify_original_config_snapshot(args: argparse.Namespace) -> str:
    """Confirm the source config still matches the bytes gated by this process."""
    try:
        observed = hashlib.sha256(args.config.read_bytes()).hexdigest()
    except OSError as exc:
        raise RuntimeError(
            f"source config is unavailable after the gate: {exc}"
        ) from exc
    if observed != args.config_sha256:
        raise RuntimeError("source config changed after the supervisor gate")
    return observed


def invalidate_aggregate_payload(
    payload: dict[str, Any], *, status: str, reason: str
) -> None:
    """Make a condition-level integrity failure unambiguously non-scored."""
    existing_status = payload.get("metadata", {}).get("status")
    if existing_status == "invalid_leakage" or any(
        row.get("status") == "invalid_leakage"
        for row in payload.get("tasks", [])
        if isinstance(row, dict)
    ):
        status = "invalid_leakage"

    rows = payload.get("tasks", [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["pre_invalidation"] = {
            "status": row.get("status"),
            "reward": row.get("reward"),
        }
        row["status"] = status
        row["path_class"] = status
        row["reward"] = None
        row["reason"] = reason

    metadata = payload["metadata"]
    metadata.update(
        {
            "status": status,
            "reason": reason,
            "status_counts": {status: len(rows)},
            "passed_count": 0,
            "success_rate": None,
            "evaluator_reward_sum": 0,
            "evaluator_reward_mean": None,
        }
    )


def publish_final_supervisor_result(
    result_path: Path,
    config: dict[str, Any],
    args: argparse.Namespace,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Publish a terminal result only after the ending integrity gate succeeds."""
    try:
        payload["metadata"]["final_integrity"] = final_supervisor_integrity(
            config, args
        )
        if payload["metadata"].get("status") == "finalizing":
            payload["metadata"]["status"] = "completed"
    except Exception as exc:
        reason = f"final supervisor integrity gate failed: {exc}"
        payload["metadata"]["final_integrity"] = {
            "status": "error",
            "error": {"type": type(exc).__name__, "detail": str(exc)[:1_000]},
        }
        invalidate_aggregate_payload(
            payload,
            status="invalid_configuration",
            reason=reason,
        )
    write_json(result_path, payload)
    return payload


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_invalid_configuration_result(
    args: argparse.Namespace,
    config: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    """Persist a condition-level gate failure before any worker starts.

    A supervisor gate can fail before the normal manifest/worker lifecycle is
    created.  Recording one non-scored row per configured task keeps the
    condition machine-readable and prevents the later aggregator from
    inventing ``not_run`` or ``environment_failure`` outcomes.
    """
    result_dir = args.result_dir
    result_path = result_dir / "results.json"
    if result_path.exists():
        raise RuntimeError(
            "cannot record invalid configuration over an existing results.json"
        )
    result_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        {
            "order": task.get("order"),
            "task_id": task.get("task_id"),
            "domain": task.get("domain"),
            "status": "invalid_configuration",
            "path_class": "invalid_configuration",
            "reward": None,
            "reason": reason,
        }
        for task in config.get("tasks", [])
        if isinstance(task, dict)
    ]
    counts = {"invalid_configuration": len(tasks)}
    config_sha256 = getattr(args, "config_sha256", None)
    if not isinstance(config_sha256, str):
        try:
            config_sha256 = hashlib.sha256(args.config.read_bytes()).hexdigest()
        except OSError:
            config_sha256 = None
    metadata = {
        "status": "invalid_configuration",
        "reason": reason,
        "config": str(args.config),
        "config_sha256": config_sha256,
        "model": args.model,
        "reasoning_mode": getattr(args, "reasoning_mode", None),
        "reasoning_effort": getattr(args, "reasoning_effort", None),
        "base_urls": list(args.base_urls),
        "workers": args.workers,
        "task_count": len(tasks),
        "status_counts": counts,
        "passed_count": 0,
        "success_rate": None,
        "evaluator_reward_sum": 0,
        "evaluator_reward_mean": None,
        "started_at": utc_now(),
        "updated_at": utc_now(),
    }
    payload = {"metadata": metadata, "workers": [], "tasks": tasks}
    write_json(result_dir / "metadata.json", metadata)
    write_json(result_path, payload)
    return payload


def shard_tasks(
    tasks: list[dict[str, Any]], workers: int
) -> list[list[dict[str, Any]]]:
    shards = [[] for _ in range(workers)]
    for index, task in enumerate(tasks):
        shards[index % workers].append(task)
    return shards


def load_prior_records(paths: list[Path]) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"resume results do not exist: {path}")
        payload = read_json(path)
        for row in payload.get("tasks", []):
            order = row.get("order")
            if not isinstance(order, int) or row.get("status") not in TERMINAL_STATUSES:
                continue
            record = dict(row)
            record["result_source"] = str(path)
            previous = records.get(order)
            if previous and previous.get("task_id") != record.get("task_id"):
                raise RuntimeError(f"conflicting task IDs for completed order {order}")
            records[order] = record
    return records


def endpoint_for_worker(base_urls: list[str], workers: int, index: int) -> str:
    if not base_urls:
        raise ValueError("at least one base URL is required")
    if workers % len(base_urls) != 0:
        raise ValueError("worker count must be divisible by the number of base URLs")
    workers_per_endpoint = workers // len(base_urls)
    return base_urls[(index - 1) // workers_per_endpoint]


def holo_endpoint_for_worker(args: argparse.Namespace, index: int) -> str | None:
    base_urls = getattr(args, "holo_base_urls", None)
    if base_urls:
        return endpoint_for_worker(base_urls, args.workers, index)
    return getattr(args, "holo_base_url", None)


def worker_command(
    args: argparse.Namespace,
    index: int,
    tasks: list[dict[str, Any]],
) -> list[str]:
    worker_config = getattr(args, "worker_config", args.config)
    config_sha256 = getattr(args, "config_sha256", None)
    if not isinstance(config_sha256, str):
        config_sha256 = hashlib.sha256(worker_config.read_bytes()).hexdigest()
    supervisor = getattr(args, "supervisor", Path(__file__).resolve())
    command = [
        args.python,
        str(args.runner),
        "--config",
        str(worker_config),
        "--expected-config-sha256",
        config_sha256,
        "--supervisor",
        str(supervisor),
        "--result-dir",
        str(args.result_dir / "workers" / f"worker-{index:02d}"),
        "--orders",
        *[str(task["order"]) for task in tasks],
        "--model",
        args.model,
        "--base-url",
        endpoint_for_worker(args.base_urls, args.workers, index),
        "--api-key",
        args.api_key,
        "--max-steps",
        str(args.max_steps),
        "--max-no-progress-steps",
        str(args.max_no_progress_steps),
        "--max-agent-seconds",
        str(args.max_agent_seconds),
        "--top-k",
        str(args.top_k),
        "--max-output-tokens",
        str(args.max_output_tokens),
        "--temperature",
        str(getattr(args, "temperature", 0.0)),
        "--request-timeout",
        str(args.request_timeout),
        "--model-retries",
        str(args.model_retries),
        "--initial-settle-seconds",
        str(args.initial_settle_seconds),
        "--action-settle-seconds",
        str(args.action_settle_seconds),
        "--evaluator-settle-seconds",
        str(args.evaluator_settle_seconds),
        "--evaluator-file-fetch-attempts",
        str(args.evaluator_file_fetch_attempts),
        "--evaluator-file-fetch-delay-seconds",
        str(args.evaluator_file_fetch_delay_seconds),
    ]
    # Keep these optional/compatible for callers that construct a legacy
    # Namespace directly.  The worker runner owns the defaults; forwarding an
    # explicitly configured value makes same-VM recovery consistent across
    # parallel workers.
    max_local_steps = getattr(args, "max_local_steps", None)
    max_soft_restarts = getattr(args, "max_soft_restarts", 1)
    if max_local_steps is not None:
        command.extend(["--max-local-steps", str(max_local_steps)])
    command.extend(["--max-soft-restarts", str(max_soft_restarts)])
    if args.thinking:
        command.append("--thinking")
    if args.reasoning_effort is not None:
        command.extend(["--reasoning-effort", args.reasoning_effort])
    if getattr(args, "reasoning_mode", None) is not None:
        command.extend(["--reasoning-mode", args.reasoning_mode])
    holo_base_url = holo_endpoint_for_worker(args, index)
    if holo_base_url:
        command.extend(["--holo-base-url", holo_base_url])
    if args.holo_model:
        command.extend(["--holo-model", args.holo_model])
    if args.holo_api_key:
        command.extend(["--holo-api-key", args.holo_api_key])
    # A binary Holo mode and the legacy tiered effort are mutually exclusive.
    # Prefer the explicit mode so a parser default such as ``medium`` cannot
    # make the worker command look like it requested two controls.
    holo_reasoning_mode = getattr(args, "holo_reasoning_mode", None)
    if holo_reasoning_mode:
        command.extend(["--holo-reasoning-mode", holo_reasoning_mode])
    elif args.holo_reasoning_effort:
        command.extend(["--holo-reasoning-effort", args.holo_reasoning_effort])
    command.extend(
        [
            "--holo-max-output-tokens",
            str(args.holo_max_output_tokens),
            "--holo-temperature",
            str(args.holo_temperature),
            "--holo-request-timeout",
            str(args.holo_request_timeout),
        ]
    )
    if args.no_gui:
        command.append("--no-gui")
    return command


def cleanup_run_owner(run_owner: str) -> None:
    completed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", f"label=openapa.run_owner={run_owner}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    container_ids = [
        line.strip() for line in completed.stdout.splitlines() if line.strip()
    ]
    if container_ids:
        subprocess.run(
            ["docker", "rm", "-f", *container_ids],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def stop_workers(
    processes: list[subprocess.Popen[Any] | None], owners: list[str]
) -> None:
    for process in processes:
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and any(
        process and process.poll() is None for process in processes
    ):
        time.sleep(0.2)
    for process in processes:
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for owner in owners:
        cleanup_run_owner(owner)


def worker_payload_integrity_errors(
    payload: dict[str, Any],
    shard: list[dict[str, Any]],
    *,
    expected_config_sha256: str,
) -> list[str]:
    """Bind a worker result to the supervisor snapshot and assigned task shard."""
    errors: list[str] = []
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return ["worker results have no metadata object"]
    if metadata.get("config_sha256") != expected_config_sha256:
        errors.append("worker config SHA-256 does not match supervisor snapshot")

    expected_by_order = {task["order"]: task for task in shard}
    expected_task_ids = [task["task_id"] for task in shard]
    worker_status = metadata.get("status")
    observed_task_order = metadata.get("task_order")
    if (
        worker_status != "invalid_configuration"
        and observed_task_order != expected_task_ids
    ):
        errors.append("worker task_order does not match assigned shard")

    seen_orders: set[int] = set()
    rows = payload.get("tasks")
    if not isinstance(rows, list):
        return [*errors, "worker results tasks field is not an array"]
    for row in rows:
        if not isinstance(row, dict):
            errors.append("worker result row is not an object")
            continue
        order = row.get("order")
        if type(order) is not int:
            errors.append(f"worker task order is invalid: {order!r}")
            continue
        expected = expected_by_order.get(order)
        if expected is None:
            errors.append(f"worker returned unassigned task order {order!r}")
            continue
        if order in seen_orders:
            errors.append(f"worker returned duplicate task order {order}")
        seen_orders.add(order)
        if row.get("task_id") != expected["task_id"]:
            errors.append(f"worker task_id mismatch for order {order}")
        if row.get("domain") != expected["domain"]:
            errors.append(f"worker domain mismatch for order {order}")
        if row.get("status") not in WORKER_TASK_STATUSES:
            errors.append(f"worker task status is invalid for order {order}")
    return errors


def worker_terminal_integrity_errors(
    payload: dict[str, Any],
    shard: list[dict[str, Any]],
    *,
    process_returncode: int | None,
) -> list[str]:
    """Require a complete, successfully revalidated worker at supervisor exit."""
    errors: list[str] = []
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return ["worker results have no metadata object"]
    if metadata.get("status") != "completed":
        errors.append("worker metadata status is not completed")
    revalidation = metadata.get("integrity_revalidation")
    if not isinstance(revalidation, dict) or revalidation.get("status") != "ok":
        errors.append("worker final integrity revalidation is not ok")
    if process_returncode != 0:
        errors.append(f"worker process return code is not zero: {process_returncode!r}")

    rows = payload.get("tasks")
    if not isinstance(rows, list):
        return [*errors, "worker results tasks field is not an array"]
    expected_orders = {task["order"] for task in shard}
    observed_orders = {row.get("order") for row in rows if isinstance(row, dict)}
    if len(rows) != len(shard) or observed_orders != expected_orders:
        errors.append("worker terminal task rows do not exactly match assigned shard")
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_status = row.get("status")
        if row_status not in COMPLETED_WORKER_TASK_STATUSES:
            errors.append(
                "worker terminal task status is not reportable for order "
                f"{row.get('order')!r}"
            )
            continue
        reward = row.get("reward")
        if isinstance(reward, bool):
            reward_is_number = False
        elif isinstance(reward, int):
            reward_is_number = 0 <= reward <= 1
        elif isinstance(reward, float):
            reward_is_number = math.isfinite(reward) and 0.0 <= reward <= 1.0
        else:
            reward_is_number = False
        if row_status == "passed" and (not reward_is_number or reward != 1.0):
            errors.append(
                f"worker passed task has invalid reward for order {row.get('order')!r}"
            )
        elif row_status == "failed" and (not reward_is_number or reward == 1.0):
            errors.append(
                f"worker failed task has invalid reward for order {row.get('order')!r}"
            )
        elif row_status not in {"passed", "failed"} and reward is not None:
            errors.append(
                "worker non-evaluated terminal task has a reward for order "
                f"{row.get('order')!r}"
            )
    return errors


def aggregate(
    args: argparse.Namespace,
    all_tasks: list[dict[str, Any]],
    shards: list[list[dict[str, Any]]],
    prior: dict[int, dict[str, Any]],
    processes: list[subprocess.Popen[Any] | None],
    status: str,
    started_at: str,
) -> dict[str, Any]:
    records = {order: dict(row) for order, row in prior.items()}
    workers = []
    worker_gate_failures: dict[int, tuple[str, str]] = {}
    expected_config_sha256 = getattr(args, "config_sha256", None)
    if not isinstance(expected_config_sha256, str):
        expected_config_sha256 = hashlib.sha256(args.config.read_bytes()).hexdigest()
    for index, shard in enumerate(shards, start=1):
        process = processes[index - 1] if index <= len(processes) else None
        result_path = (
            args.result_dir / "workers" / f"worker-{index:02d}" / "results.json"
        )
        payload: dict[str, Any] | None = None
        if result_path.is_file():
            try:
                payload = read_json(result_path)
            except (OSError, RuntimeError, ValueError) as exc:
                worker_gate_failures[index] = (
                    "invalid_configuration",
                    f"worker results are unreadable: {type(exc).__name__}: {exc}",
                )
        elif status in {"completed", "finalizing"} and shard:
            worker_gate_failures[index] = (
                "invalid_configuration",
                "worker completed without a results.json payload",
            )
        if payload is not None:
            worker_metadata = payload.get("metadata")
            if isinstance(worker_metadata, dict):
                worker_status = worker_metadata.get("status")
                if worker_status in {"invalid_configuration", "invalid_leakage"}:
                    worker_gate_failures[index] = (
                        str(worker_status),
                        str(worker_metadata.get("reason") or worker_status),
                    )
            payload_rows = payload.get("tasks")
            leakage_rows = (
                [
                    row
                    for row in payload_rows
                    if isinstance(row, dict) and row.get("status") == "invalid_leakage"
                ]
                if isinstance(payload_rows, list)
                else []
            )
            if leakage_rows:
                leakage_reason = next(
                    (str(row["reason"]) for row in leakage_rows if row.get("reason")),
                    "worker task detected model-facing leakage",
                )
                worker_gate_failures[index] = (
                    "invalid_leakage",
                    leakage_reason,
                )
            integrity_errors = worker_payload_integrity_errors(
                payload,
                shard,
                expected_config_sha256=expected_config_sha256,
            )
            if integrity_errors:
                integrity_reason = "worker result integrity failed: " + "; ".join(
                    integrity_errors
                )
                existing_failure = worker_gate_failures.get(index)
                if existing_failure and existing_failure[0] == "invalid_leakage":
                    worker_gate_failures[index] = (
                        "invalid_leakage",
                        f"{existing_failure[1]}; {integrity_reason}",
                    )
                else:
                    worker_gate_failures[index] = (
                        "invalid_configuration",
                        integrity_reason,
                    )
            if index not in worker_gate_failures and status in {
                "completed",
                "finalizing",
            }:
                terminal_errors = worker_terminal_integrity_errors(
                    payload,
                    shard,
                    process_returncode=process.poll() if process is not None else None,
                )
                if terminal_errors:
                    worker_gate_failures[index] = (
                        "invalid_configuration",
                        "worker terminal integrity failed: "
                        + "; ".join(terminal_errors),
                    )
            if index not in worker_gate_failures:
                for row in payload.get("tasks", []):
                    record = dict(row)
                    record["result_source"] = str(result_path)
                    records[record["order"]] = record
        workers.append(
            {
                "worker": index,
                "base_url": endpoint_for_worker(args.base_urls, args.workers, index),
                "holo_base_url": holo_endpoint_for_worker(args, index),
                "pid": process.pid if process else None,
                "returncode": process.poll() if process else None,
                "orders": [task["order"] for task in shard],
                "result": str(result_path),
                "status": (
                    worker_gate_failures[index][0]
                    if index in worker_gate_failures
                    else None
                ),
                "reason": (
                    worker_gate_failures[index][1]
                    if index in worker_gate_failures
                    else None
                ),
            }
        )

    rows = []
    for task in all_tasks:
        row = records.get(task["order"])
        if row is None:
            shard_index = next(
                (
                    index
                    for index, shard in enumerate(shards, start=1)
                    if any(item["order"] == task["order"] for item in shard)
                ),
                None,
            )
            gate_failure = worker_gate_failures.get(shard_index)
            if gate_failure is not None:
                gate_status, gate_reason = gate_failure
                row = {
                    "order": task["order"],
                    "task_id": task["task_id"],
                    "domain": task["domain"],
                    "status": gate_status,
                    "reward": None,
                    "path_class": gate_status,
                    "reason": gate_reason,
                }
        if row is None:
            row = {
                "order": task["order"],
                "task_id": task["task_id"],
                "domain": task["domain"],
                "status": "not_run",
                "reward": None,
                "path_class": "not_run",
            }
        rows.append(row)

    counts = Counter(row["status"] for row in rows)
    rewards = [
        row["reward"] for row in rows if isinstance(row.get("reward"), (int, float))
    ]
    evaluated = counts.get("passed", 0) + counts.get("failed", 0)
    aggregate_status = status
    if counts.get("invalid_leakage", 0):
        aggregate_status = "invalid_leakage"
    elif counts.get("invalid_configuration", 0):
        aggregate_status = "invalid_configuration"
    reportable = aggregate_status not in {
        "invalid_configuration",
        "invalid_leakage",
    }
    return {
        "metadata": {
            "status": aggregate_status,
            "started_at": started_at,
            "updated_at": utc_now(),
            "config": str(args.config),
            "config_sha256": expected_config_sha256,
            "workers": args.workers,
            "base_urls": args.base_urls,
            "holo_base_urls": getattr(args, "holo_base_urls", None),
            "model": args.model,
            "temperature": getattr(args, "temperature", 0.0),
            "reasoning_mode": getattr(args, "reasoning_mode", None),
            "reasoning_effort": getattr(args, "reasoning_effort", None),
            "max_steps": args.max_steps,
            "max_local_steps": getattr(args, "max_local_steps", None),
            "max_soft_restarts": getattr(args, "max_soft_restarts", 1),
            "max_no_progress_steps": args.max_no_progress_steps,
            "max_agent_seconds": args.max_agent_seconds,
            "evaluator_file_fetch_attempts": args.evaluator_file_fetch_attempts,
            "evaluator_file_fetch_delay_seconds": args.evaluator_file_fetch_delay_seconds,
            "frozen_condition": args.frozen_condition,
            "task_count": len(all_tasks),
            "resumed_terminal_count": len(prior),
            "status_counts": dict(sorted(counts.items())),
            "passed_count": counts.get("passed", 0) if reportable else 0,
            "success_rate": (
                counts.get("passed", 0) / evaluated
                if reportable and evaluated
                else None
            ),
            "evaluator_reward_sum": sum(rewards) if reportable else 0,
            "evaluator_reward_mean": (
                sum(rewards) / len(rewards) if reportable and rewards else None
            ),
        },
        "workers": workers,
        "tasks": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fixed LiteAgent OSWorld tasks across multiple model endpoints."
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--resume-results", type=Path, action="append", default=[])
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument(
        "--base-urls",
        nargs="+",
        default=["http://192.168.0.138:8001/v1"],
    )
    parser.add_argument("--worker-start-delay-seconds", type=float, default=5.0)
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=DEFAULT_POLL_SECONDS,
        help="Seconds between internal worker lifecycle checks (default: 5).",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=DEFAULT_HEARTBEAT_SECONDS,
        help="Seconds between unchanged progress reports (default: 600).",
    )
    parser.add_argument("--min-free-gib", type=float, default=30.0)
    parser.add_argument("--model", default="qwen3.5-4b")
    parser.add_argument("--api-key", default="EMPTY")
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
    parser.add_argument("--max-no-progress-steps", type=int, default=8)
    parser.add_argument("--max-agent-seconds", type=float, default=300.0)
    parser.add_argument("--top-k", type=int, default=7)
    parser.add_argument("--max-output-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--model-retries", type=int, default=3)
    parser.add_argument("--initial-settle-seconds", type=float, default=10.0)
    parser.add_argument("--action-settle-seconds", type=float, default=2.0)
    parser.add_argument("--evaluator-settle-seconds", type=float, default=5.0)
    parser.add_argument("--evaluator-file-fetch-attempts", type=int, default=3)
    parser.add_argument("--evaluator-file-fetch-delay-seconds", type=float, default=1.0)
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument(
        "--reasoning-effort",
        choices=SUPPORTED_REASONING_EFFORTS,
        default=None,
    )
    parser.add_argument(
        "--reasoning-mode",
        choices=SUPPORTED_REASONING_MODES,
        default=None,
        help="Binary provider mode, e.g. thinking for Qwen3.5.",
    )
    holo_endpoints = parser.add_mutually_exclusive_group()
    holo_endpoints.add_argument(
        "--holo-base-url",
        default=os.getenv("HOLO_BASE_URL"),
        help="Optional Holo visual-grounding endpoint for delegated GUI turns.",
    )
    holo_endpoints.add_argument(
        "--holo-base-urls",
        nargs="+",
        help="Holo endpoints paired in the same order as --base-urls for each worker.",
    )
    parser.add_argument("--holo-model", default=os.getenv("HOLO_MODEL"))
    parser.add_argument("--holo-api-key", default=os.getenv("HOLO_API_KEY", "EMPTY"))
    parser.add_argument(
        "--holo-reasoning-effort",
        default=os.getenv("HOLO_REASONING_EFFORT"),
    )
    parser.add_argument(
        "--holo-reasoning-mode",
        choices=SUPPORTED_REASONING_MODES,
        default=os.getenv("HOLO_REASONING_MODE"),
    )
    parser.add_argument("--holo-max-output-tokens", type=int, default=1024)
    parser.add_argument("--holo-temperature", type=float, default=0.8)
    parser.add_argument("--holo-request-timeout", type=float, default=180.0)
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--runner", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    if args.holo_base_urls is not None:
        # An explicit endpoint list supersedes the legacy environment default.
        args.holo_base_url = None
        if args.holo_base_urls != args.base_urls:
            parser.error("paired Holo base URLs must match --base-urls in order")
    args.config = args.config.resolve()
    args.result_dir = args.result_dir.resolve()
    args.resume_results = [path.resolve() for path in args.resume_results]
    args.runner = args.runner.resolve()
    args.supervisor = Path(__file__).resolve()
    if args.workers <= 0:
        parser.error("workers must be positive")
    if args.worker_start_delay_seconds < 0:
        parser.error("worker start delay must be non-negative")
    if args.evaluator_file_fetch_attempts <= 0:
        parser.error("evaluator file fetch attempts must be positive")
    if args.evaluator_file_fetch_delay_seconds < 0:
        parser.error("evaluator file fetch delay must be non-negative")
    if args.holo_max_output_tokens <= 0:
        parser.error("Holo max output tokens must be positive")
    if args.holo_temperature < 0:
        parser.error("Holo temperature must be non-negative")
    if args.holo_request_timeout <= 0:
        parser.error("Holo request timeout must be positive")
    if args.max_no_progress_steps < 4:
        parser.error("max no-progress steps must be at least 4")
    if args.max_local_steps is not None and args.max_local_steps < 1:
        parser.error("max local steps must be positive")
    if args.max_soft_restarts < 0:
        parser.error("max soft restarts must be nonnegative")
    if args.max_agent_seconds <= 0:
        parser.error("max agent seconds must be positive")
    try:
        endpoint_for_worker(args.base_urls, args.workers, args.workers)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main() -> int:
    args = parse_args()
    config, config_bytes, config_sha256 = read_config_snapshot(args.config)
    args.config_sha256 = config_sha256
    if args.reasoning_effort is None:
        args.reasoning_effort = config.get("protocol", {}).get("reasoning_effort")
    if getattr(args, "reasoning_mode", None) is None:
        args.reasoning_mode = config.get("protocol", {}).get("reasoning_mode")
    try:
        args.frozen_condition = enforce_supervisor_condition(config, args, PROJECT_ROOT)
        verify_original_config_snapshot(args)
    except (RuntimeError, ValueError) as exc:
        reason = f"condition gate failed: {exc}"
        payload = write_invalid_configuration_result(args, config, reason)
        print(
            json.dumps(
                {
                    "status": payload["metadata"]["status"],
                    "reason": reason,
                    "result_dir": str(args.result_dir),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        return 2
    all_tasks = list(config["tasks"])
    prior = load_prior_records(args.resume_results)
    task_by_order = {task["order"]: task for task in all_tasks}
    for order, record in prior.items():
        task = task_by_order.get(order)
        if task is None or task["task_id"] != record.get("task_id"):
            raise RuntimeError(
                f"resume result does not match fixed config at order {order}"
            )
    remaining = [task for task in all_tasks if task["order"] not in prior]
    shards = shard_tasks(remaining, args.workers)

    plan = {
        "config": str(args.config),
        "config_sha256": args.config_sha256,
        "worker_config_snapshot": "frozen-config.json",
        "result_dir": str(args.result_dir),
        "workers": args.workers,
        "poll_seconds": args.poll_seconds,
        "heartbeat_seconds": args.heartbeat_seconds,
        "base_urls": args.base_urls,
        "holo_base_urls": getattr(args, "holo_base_urls", None),
        "resumed_terminal_count": len(prior),
        "remaining_count": len(remaining),
        "shards": [
            {
                "worker": index,
                "base_url": endpoint_for_worker(args.base_urls, args.workers, index),
                "holo_base_url": holo_endpoint_for_worker(args, index),
                "task_count": len(shard),
                "orders": [task["order"] for task in shard],
            }
            for index, shard in enumerate(shards, start=1)
        ],
    }
    if args.plan_only:
        print(json.dumps(plan, indent=2))
        return 0
    if not remaining:
        write_json(
            args.result_dir / "results.json",
            aggregate(args, all_tasks, shards, prior, [], "completed", utc_now()),
        )
        return 0

    args.result_dir.mkdir(parents=True, exist_ok=True)
    args.worker_config = args.result_dir / "frozen-config.json"
    write_config_snapshot(args.worker_config, config_bytes)
    if (
        hashlib.sha256(args.worker_config.read_bytes()).hexdigest()
        != args.config_sha256
    ):
        raise RuntimeError("persisted worker config snapshot hash mismatch")
    write_json(args.result_dir / "plan.json", plan)
    manifest = {
        "schema_version": 1,
        **plan,
        "runner": str(args.runner),
        "runner_sha256": hashlib.sha256(args.runner.read_bytes()).hexdigest(),
        "worker_config": str(args.worker_config),
        "worker_config_sha256": args.config_sha256,
        "resume_results": [str(path) for path in args.resume_results],
        "frozen_condition": args.frozen_condition,
    }
    manifest_path = args.result_dir / "manifest.json"
    if manifest_path.is_file() and read_json(manifest_path) != manifest:
        raise RuntimeError("existing result directory uses a different manifest")
    write_json(manifest_path, manifest)

    processes: list[subprocess.Popen[Any] | None] = []
    log_files = []
    owners = []
    started_at = utc_now()
    interrupted = False
    payload: dict[str, Any] = {}
    try:
        for index, shard in enumerate(shards, start=1):
            if not shard:
                processes.append(None)
                continue
            if index > 1 and args.worker_start_delay_seconds:
                time.sleep(args.worker_start_delay_seconds)
            worker_dir = args.result_dir / "workers" / f"worker-{index:02d}"
            worker_dir.mkdir(parents=True, exist_ok=True)
            log_file = (worker_dir / "runner.log").open("a", encoding="utf-8")
            log_files.append(log_file)
            owner = f"lite-{args.result_dir.name}-w{index:02d}"
            owners.append(owner)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["OPENAPA_RUN_OWNER"] = owner
            env["LITE_AGENT_RUN_OWNER"] = owner
            # Workers receive every frozen Holo setting explicitly. Prevent a
            # stale shell default from adding a second reasoning control.
            for name in (
                "HOLO_BASE_URL",
                "HOLO_MODEL",
                "HOLO_REASONING_EFFORT",
                "HOLO_REASONING_MODE",
            ):
                env.pop(name, None)
            process = subprocess.Popen(
                worker_command(args, index, shard),
                cwd=ROOT,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(process)
            print(
                f"[parallel] worker={index} pid={process.pid} endpoint="
                f"{endpoint_for_worker(args.base_urls, args.workers, index)} tasks={len(shard)}",
                flush=True,
            )

        previous_counts: dict[str, int] | None = None
        next_heartbeat = 0.0
        while any(process and process.poll() is None for process in processes):
            free_gib = (
                os.statvfs(args.result_dir).f_bavail
                * os.statvfs(args.result_dir).f_frsize
                / (1024**3)
            )
            if free_gib < args.min_free_gib:
                raise RuntimeError(
                    f"free disk {free_gib:.1f} GiB is below {args.min_free_gib:.1f} GiB guard"
                )
            payload = aggregate(
                args, all_tasks, shards, prior, processes, "running", started_at
            )
            counts = payload["metadata"]["status_counts"]
            now = time.monotonic()
            if progress_report_due(
                now=now,
                next_heartbeat=next_heartbeat,
                counts=counts,
                previous_counts=previous_counts,
            ):
                write_json(args.result_dir / "results.json", payload)
                print(
                    f"[parallel] counts={json.dumps(counts, sort_keys=True)} "
                    f"free_gib={free_gib:.1f}",
                    flush=True,
                )
                previous_counts = dict(counts)
                next_heartbeat = now + args.heartbeat_seconds
            time.sleep(args.poll_seconds)
    except BaseException:
        interrupted = True
        stop_workers(processes, owners)
        raise
    finally:
        for log_file in log_files:
            log_file.close()
        status = "interrupted" if interrupted else "finalizing"
        payload = aggregate(
            args, all_tasks, shards, prior, processes, status, started_at
        )
        write_json(args.result_dir / "results.json", payload)

    payload = publish_final_supervisor_result(
        args.result_dir / "results.json",
        config,
        args,
        payload,
    )

    terminal_status = payload["metadata"].get("status")
    if terminal_status in {"invalid_configuration", "invalid_leakage"}:
        return 2
    return 0 if payload["metadata"]["status_counts"].get("not_run", 0) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
