#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "openapa.osworld.trajectory.v1"
ACTION_SEPARATOR = "-" * 50


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            records.append({"_malformed_line": line_number, "_error": str(exc)})
            continue
        records.append(value if isinstance(value, dict) else {"value": value})
    return records


def parse_action_steps(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records = []
    header = re.compile(r"^Step (\d+) - (.+)$")
    for block in path.read_text(encoding="utf-8").split(ACTION_SEPARATOR):
        lines = [line.rstrip() for line in block.strip().splitlines()]
        if not lines:
            continue
        match = header.match(lines[0])
        if not match:
            continue
        values: dict[str, Any] = {
            "step_num": int(match.group(1)),
            "timestamp_source": match.group(2),
        }
        for key, prefix in (
            ("action_type", "Type: "),
            ("model_action", "Original Action: "),
            ("executed_action", "Action Code: "),
        ):
            values[key] = next(
                (
                    line.removeprefix(prefix)
                    for line in lines[1:]
                    if line.startswith(prefix)
                ),
                "",
            )
        records.append(values)
    return records


def _artifact(task_dir: Path, path: Path) -> dict[str, Any]:
    return {
        "path": str(path.relative_to(task_dir)),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def _termination_reason(
    status: str,
    actions: list[dict[str, Any]],
    trajectory: list[dict[str, Any]],
    max_steps: int,
    lite_events: list[dict[str, Any]] | None = None,
) -> str:
    if status == "environment_failure":
        return "environment_or_runner_exception"
    last_model_action = actions[-1].get("model_action", "") if actions else ""
    if last_model_action.startswith("agent.fail("):
        return "agent_fail"
    if last_model_action.startswith("agent.done("):
        return "agent_done"
    if lite_events:
        last_kind = lite_events[-1].get("proposed", {}).get("kind")
        if last_kind == "failure":
            return "agent_fail"
        if last_kind == "completion" and lite_events[-1].get("executed") is True:
            return "agent_done"
    if len(lite_events or []) >= max_steps or len(trajectory) >= max_steps:
        return "max_steps"
    if status == "passed":
        return "evaluator_pass"
    return "loop_ended_before_success"


def build_trajectory_manifest(
    task_dir: Path,
    *,
    episode_context: dict[str, Any],
    record: dict[str, Any],
    instruction: str,
    agent_prompt: str,
    model_requested: str,
    reasoning_effort: str,
    reasoning_mode: str | None = None,
    max_steps: int,
    config_sha256: str,
    coverage_sha256: str | None,
    osworld_commit: str,
    openapa_commit: str,
    screen_size: list[int],
    grounding_coordinate_size: list[int],
    started_at: str,
    completed_at: str,
    schema_version: str = SCHEMA_VERSION,
    agent_framework: str = "OpenAPA",
    model_identifier_source: str = "OpenAPA LLM session log",
    adapter_version: str = "v2_expanded",
) -> dict[str, Any]:
    task_dir = task_dir.resolve()
    llm_calls = read_jsonl(task_dir / "llm_call_log.jsonl")
    actions = parse_action_steps(task_dir / "action_steps.log")
    trajectory = read_jsonl(task_dir / "traj.jsonl")
    adapter_calls = read_jsonl(task_dir / "adapter_calls.jsonl")
    lite_events = read_jsonl(task_dir / "lite_agent_events.jsonl")
    office_environment_recoveries = read_jsonl(
        task_dir / "office_environment_recovery.jsonl"
    )
    screenshots = sorted(task_dir.glob("step_*.png"))
    models_observed = sorted(
        {str(call["model"]) for call in llm_calls if call.get("model")}
    )
    by_step: dict[int, dict[str, Any]] = {}
    for action in actions:
        step = int(action["step_num"])
        by_step.setdefault(step, {"step_num": step})["action"] = action
    for index, row in enumerate(trajectory):
        step = max(0, int(row.get("step_num", index + 1)) - 1)
        by_step.setdefault(step, {"step_num": step})["environment_transition"] = row
    for index, call in enumerate(llm_calls):
        if not isinstance(call.get("step_num"), int):
            continue
        step = int(call["step_num"])
        by_step.setdefault(step, {"step_num": step}).setdefault(
            "llm_call_indices", []
        ).append(index)
    for index, call in enumerate(adapter_calls):
        step_value = call.get("step_num", call.get("step"))
        if not isinstance(step_value, int):
            continue
        step = int(step_value)
        by_step.setdefault(step, {"step_num": step}).setdefault(
            "adapter_call_indices", []
        ).append(index)
    for event in lite_events:
        if not isinstance(event.get("step"), int):
            continue
        step = int(event["step"])
        by_step.setdefault(step, {"step_num": step})["action"] = event

    artifact_names = (
        "original_instruction.txt",
        "agent_prompt.txt",
        "instruction.txt",
        "llm_call_log.jsonl",
        "llm_request_index.jsonl",
        "action_steps.log",
        "traj.jsonl",
        "adapter_calls.jsonl",
        "gui_calls.jsonl",
        "holo_grounding_calls.jsonl",
        "result.txt",
        "usage.json",
        "action_summary.txt",
        "exception.txt",
        "lite_agent_events.jsonl",
        "office_environment_recovery.jsonl",
        "guest_file_inventory.json",
        "final.png",
        "evaluator_artifacts/manifest.json",
    )
    artifacts = {
        name: _artifact(task_dir, task_dir / name)
        for name in artifact_names
        if (task_dir / name).is_file()
    }
    reward = record.get("reward")
    status = str(record.get("status", "environment_failure"))
    verifier_passed = 0
    for call in adapter_calls:
        result = call.get("result")
        verification = result.get("verification") if isinstance(result, dict) else None
        if (
            call.get("status") == "ok"
            and isinstance(verification, dict)
            and verification.get("passed") is True
        ):
            verifier_passed += 1
    episode_id = (
        episode_context.get("episode_id")
        or hashlib.sha256(
            f"{episode_context.get('task_id')}:{started_at}:{task_dir}".encode("utf-8")
        ).hexdigest()[:24]
    )
    return {
        "schema_version": schema_version,
        "episode": {
            **episode_context,
            "episode_id": episode_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": record.get("duration_seconds"),
            "retry_lineage": {
                "attempt_index": int(episode_context.get("attempt_index", 1)),
                "parent_episode_id": episode_context.get("parent_episode_id"),
                "run_owner": episode_context.get("run_owner"),
            },
        },
        "task": {
            "task_id": episode_context.get("task_id"),
            "order": episode_context.get("order"),
            "domain": episode_context.get("domain"),
            "instruction": instruction,
            "proxy_enabled": record.get("proxy_enabled", False),
        },
        "agent": {
            "framework": agent_framework,
            "model_requested": model_requested,
            "models_observed_in_openapa_log": models_observed,
            "model_identifier_source": model_identifier_source,
            "reasoning_effort": reasoning_effort,
            "reasoning_mode": reasoning_mode,
            "agent_prompt_sha256": hashlib.sha256(
                agent_prompt.encode("utf-8")
            ).hexdigest(),
            "tool_catalog_sha256": episode_context.get("tool_catalog_sha256"),
            "max_steps": max_steps,
        },
        "environment": {
            "adapter_version": adapter_version,
            "osworld_commit": osworld_commit,
            "openapa_commit": openapa_commit,
            "config_sha256": config_sha256,
            "coverage_sha256": coverage_sha256,
            "screen_size": screen_size,
            "grounding_coordinate_size": grounding_coordinate_size,
            "vm_reset": "fresh_docker_kvm_container_per_task",
        },
        "outcome": {
            "status": status,
            "original_evaluator_reward": reward,
            "partial_reward": reward,
            "binary_reward": (1 if reward == 1.0 else 0)
            if isinstance(reward, (int, float))
            else None,
            "adapter_verifier_passed_calls": verifier_passed,
            "path_class": record.get("path_class"),
            "termination_reason": record.get("termination_reason")
            or _termination_reason(status, actions, trajectory, max_steps, lite_events),
            "error": record.get("error"),
        },
        "counts": {
            "steps": len(lite_events) if lite_events else len(actions),
            "llm_calls": len(llm_calls),
            "adapter_calls": len(adapter_calls),
            "office_environment_recoveries": len(office_environment_recoveries),
            "screenshots": len(screenshots),
        },
        "events": [by_step[step] for step in sorted(by_step)],
        "artifacts": artifacts,
        "screenshots": [_artifact(task_dir, path) for path in screenshots],
        "raw_logs": {
            "llm_calls": llm_calls,
            "adapter_calls": adapter_calls,
            "office_environment_recoveries": office_environment_recoveries,
        },
        "generated_at": utc_now(),
    }


def write_manifest(task_dir: Path, manifest: dict[str, Any]) -> Path:
    path = task_dir / "trajectory_manifest.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True, default=str) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def iter_manifests(inputs: Iterable[Path]) -> Iterable[tuple[Path, dict[str, Any]]]:
    for root in inputs:
        candidates = (
            [root]
            if root.name == "trajectory_manifest.json"
            else root.rglob("trajectory_manifest.json")
        )
        for path in sorted(candidates):
            yield path, json.loads(path.read_text(encoding="utf-8"))


def export_training_jsonl(inputs: list[Path], output: Path) -> int:
    rows = []
    seen = set()
    for path, manifest in iter_manifests(inputs):
        episode_id = manifest["episode"]["episode_id"]
        if episode_id in seen:
            continue
        seen.add(episode_id)
        rows.append(
            {
                "schema_version": SCHEMA_VERSION,
                "episode_id": episode_id,
                "task": manifest["task"],
                "agent": manifest["agent"],
                "environment": manifest["environment"],
                "events": manifest["events"],
                "llm_calls": manifest["raw_logs"]["llm_calls"],
                "adapter_calls": manifest["raw_logs"]["adapter_calls"],
                "outcome": manifest["outcome"],
                "source_manifest": str(path.resolve()),
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
    temporary.replace(output)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export OpenAPA trajectory manifests as training JSONL."
    )
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    count = export_training_jsonl(
        [path.resolve() for path in args.inputs], args.output.resolve()
    )
    print(
        json.dumps({"output": str(args.output.resolve()), "episodes": count}, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
