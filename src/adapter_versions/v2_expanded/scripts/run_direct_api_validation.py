#!/usr/bin/env python3
"""Run one OSWorld task through operator-authored public Adapter calls."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parents[1]
OSWORLD_ROOT = PROJECT_ROOT / "third_party" / "OSWorld"
for path in (V2_ROOT, V2_ROOT / "scripts", OSWORLD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from integrations.lite_agent.adapter_executor import AdapterExecutor  # noqa: E402
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
from scripts.run_lite_agent_pilot import (  # noqa: E402
    capture_generic_guest_inventory,
    install_stable_evaluator_file_fetch,
    prepare_guest_setup_dependencies,
    require_observation_screenshot,
    sanitize_generic_guest_deployment,
)
from scripts.strict_runner_support import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_QCOW2,
    assert_strict_process_boundary,
    capture_evaluator_evidence,
    configure_evaluator_runtime,
    deploy_generic_stack,
    install_post_reset_prepare,
    load_tasks,
    utc_now,
    write_json,
)


UUID_PATTERN = re.compile(
    r"(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{4}-[0-9a-f]{12}(?![0-9a-f])",
    re.IGNORECASE,
)
FORBIDDEN_OPERATOR_KEYS = frozenset(
    {"task_id", "task_uuid", "dataset_order", "evaluator", "golden"}
)
COMMAND_KEYS = {
    "action": frozenset({"command", "domain", "action", "arguments"}),
    "screenshot": frozenset({"command", "name"}),
    "finish": frozenset({"command"}),
}
SCREENSHOT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key) for key in value} | {
            nested for child in value.values() for nested in _nested_keys(child)
        }
    if isinstance(value, list):
        return {nested for child in value for nested in _nested_keys(child)}
    return set()


def validate_operator_command(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("operator command must be a JSON object")
    command = value.get("command")
    if command not in COMMAND_KEYS:
        raise ValueError("command must be action, screenshot, or finish")
    unexpected = set(value).difference(COMMAND_KEYS[command])
    missing = COMMAND_KEYS[command].difference(value)
    if unexpected or missing:
        raise ValueError(
            f"{command} command keys mismatch: missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )

    if command == "action":
        domain = value["domain"]
        action = value["action"]
        arguments = value["arguments"]
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError("action domain must be a non-empty string")
        if not isinstance(action, str) or not action.strip():
            raise ValueError("action name must be a non-empty string")
        if not isinstance(arguments, dict):
            raise ValueError("action arguments must be an object")
        forbidden = FORBIDDEN_OPERATOR_KEYS.intersection(_nested_keys(arguments))
        if forbidden:
            raise ValueError(
                f"operator arguments contain forbidden metadata keys: {sorted(forbidden)}"
            )
        serialized = json.dumps(arguments, sort_keys=True, ensure_ascii=True)
        if UUID_PATTERN.search(serialized):
            raise ValueError("operator arguments must not contain a task UUID")
    elif command == "screenshot":
        name = value["name"]
        if not isinstance(name, str) or not SCREENSHOT_NAME.fullmatch(name):
            raise ValueError("screenshot name must be a safe 1-64 character basename")

    return dict(value)


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(payload, ensure_ascii=True, default=str) + "\n")


def emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True, default=str), flush=True)


def git_revision() -> dict[str, Any]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return {"commit": commit, "dirty": dirty}


def capture_screenshot(env: Any, destination: Path, description: str) -> None:
    observation = require_observation_screenshot(
        env,
        env._get_obs(),
        description=description,
    )
    destination.write_bytes(observation["screenshot"])


def run_session(args: argparse.Namespace) -> dict[str, Any]:
    from desktop_env.desktop_env import DesktopEnv

    config, tasks = load_tasks(args.config, None, {args.order})
    if len(tasks) != 1:
        raise RuntimeError(f"expected one selected task, got {len(tasks)}")
    task = tasks[0]
    task_path = osworld_task_path(OSWORLD_ROOT, task)
    example = load_agent_task_config_isolated(
        task_path,
        expected_task_id=task["task_id"],
    )
    task_dir = (
        args.result_dir
        / "raw"
        / "run-1"
        / (f"{task['order']:03d}-{task['domain']}-{task['task_id']}")
    )
    task_dir.mkdir(parents=True)
    (task_dir / "original_instruction.txt").write_text(
        example["instruction"] + "\n", encoding="utf-8"
    )
    adapter_trace = task_dir / "adapter_calls.jsonl"
    operator_trace = task_dir / "operator_commands.jsonl"
    record: dict[str, Any] = {
        "order": task["order"],
        "task_id": task["task_id"],
        "domain": task["domain"],
        "status": "environment_failure",
        "classification": "environment_failure",
        "reward": None,
        "execution_class": "direct_api_only_non_agent",
        "model_requests": 0,
        "gui_actions": 0,
        "evaluation_boundary": {
            "agent_task_keys": sorted(example),
            "evaluator_loaded_before_finish": False,
            "evaluator_loaded_after_finish": False,
            "evaluator_calls": 0,
        },
    }
    env = None
    sequence = 0
    successful_actions = 0
    started = time.monotonic()
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
            enable_proxy=False,
            client_password="password",
            cache_dir=str(DEFAULT_CACHE_DIR),
        )
        # Multi-Apps deployment installs every sanitized Adapter, allowing explicit
        # cross-domain composition without adding a task-shaped support route.
        adapter_urls = deploy_generic_stack(env, "multi_apps")
        record["generic_guest_sanitization"] = sanitize_generic_guest_deployment(
            env.controller
        )
        record["guest_setup_dependencies"] = prepare_guest_setup_dependencies(
            env.controller, example
        )
        install_post_reset_prepare(env, task["domain"], adapter_urls)
        env.reset(task_config=reset_task_config(example))
        record["agent_egress_policy"] = env.provider.assert_agent_egress_policy()
        time.sleep(args.initial_settle_seconds)
        record["generic_guest_pre_action_sanitization"] = (
            sanitize_generic_guest_deployment(env.controller)
        )
        write_json(
            task_dir / "guest_file_inventory.json",
            capture_generic_guest_inventory(env.controller),
        )
        capture_screenshot(env, task_dir / "initial.png", "initial observation")

        executor = AdapterExecutor(adapter_urls, adapter_trace)
        record["status"] = "operator_session"
        record["classification"] = None
        write_json(task_dir / "result.json", record)
        emit(
            {
                "event": "ready",
                "instruction": example["instruction"],
                "task_dir": str(task_dir),
                "available_domains": sorted(adapter_urls),
            }
        )

        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            sequence += 1
            try:
                command = validate_operator_command(json.loads(raw))
            except (json.JSONDecodeError, ValueError) as exc:
                response = {
                    "event": "command_rejected",
                    "sequence": sequence,
                    "error": str(exc),
                }
                append_jsonl(operator_trace, {"raw": raw, **response})
                emit(response)
                continue

            append_jsonl(
                operator_trace,
                {
                    "sequence": sequence,
                    "timestamp_utc": utc_now(),
                    "command": command,
                },
            )
            if command["command"] == "screenshot":
                destination = (
                    task_dir / f"operator-{sequence:03d}-{command['name']}.png"
                )
                capture_screenshot(env, destination, command["name"])
                emit(
                    {
                        "event": "screenshot",
                        "sequence": sequence,
                        "path": str(destination),
                    }
                )
                continue
            if command["command"] == "finish":
                break

            result = executor.execute(
                command["domain"],
                command["action"],
                command["arguments"],
                {
                    "operator_sequence": sequence,
                    "source": "codex_direct_api_validation",
                },
            )
            if result.get("executed"):
                successful_actions += 1
            time.sleep(args.action_settle_seconds)
            capture_screenshot(
                env,
                task_dir / f"after-{sequence:03d}.png",
                f"after operator action {sequence}",
            )
            emit(
                {
                    "event": "action_result",
                    "sequence": sequence,
                    "domain": command["domain"],
                    "action": command["action"],
                    "result": result,
                }
            )
        else:
            raise RuntimeError("operator input ended before finish")

        capture_screenshot(env, task_dir / "final.png", "final observation")
        time.sleep(args.evaluator_settle_seconds)
        evaluator_example = load_evaluator_task_config(
            task_path,
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
        record["evaluation_boundary"]["evaluator_loaded_after_finish"] = True
        record["evaluator_file_fetch"] = {
            "retry_events": install_stable_evaluator_file_fetch(
                env.controller,
                attempts=args.evaluator_file_fetch_attempts,
                delay_seconds=args.evaluator_file_fetch_delay_seconds,
            )
        }
        record["evaluation_boundary"]["evaluator_calls"] = 1
        reward = float(env.evaluate())
        record.update(
            {
                "status": "passed" if reward == 1.0 else "failed",
                "classification": (
                    "api_composition_pass" if reward == 1.0 else "unclassified_failure"
                ),
                "reward": reward,
                "operator_commands": sequence,
                "successful_api_actions": successful_actions,
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
        record.update(
            {
                "status": "interrupted",
                "classification": "interrupted",
                "error": {"type": "KeyboardInterrupt", "detail": "user interrupted"},
            }
        )
    except Exception as exc:
        record["error"] = {"type": type(exc).__name__, "detail": str(exc)}
        (task_dir / "exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    finally:
        record["duration_seconds"] = round(time.monotonic() - started, 3)
        write_json(task_dir / "result.json", record)
        write_json(args.result_dir / "results.json", {"tasks": [record]})
        if env is not None:
            try:
                env.close()
            except Exception as exc:
                record["cleanup_error"] = str(exc)
                write_json(task_dir / "result.json", record)
                write_json(args.result_dir / "results.json", {"tasks": [record]})
    emit({"event": "completed", "result": record})
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--order", type=int, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--initial-settle-seconds", type=float, default=10.0)
    parser.add_argument("--action-settle-seconds", type=float, default=1.0)
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
    if args.result_dir.exists():
        parser.error(f"result directory already exists: {args.result_dir}")
    if args.order <= 0:
        parser.error("order must be positive")
    if args.evaluator_file_fetch_attempts <= 0:
        parser.error("evaluator file fetch attempts must be positive")
    if (
        min(
            args.initial_settle_seconds,
            args.action_settle_seconds,
            args.evaluator_settle_seconds,
            args.evaluator_file_fetch_delay_seconds,
        )
        < 0
    ):
        parser.error("settle and retry delay values must be non-negative")

    args.result_dir.mkdir(parents=True)
    configure_evaluator_runtime()
    os.chdir(OSWORLD_ROOT)
    install_provider_patch()
    metadata = {
        "schema_version": 1,
        "experiment_id": args.result_dir.name,
        "status": "running",
        "evaluation_type": "direct_api_composition_non_agent",
        "model_used": False,
        "router_used": False,
        "gui_actions_allowed": False,
        "original_evaluator": True,
        "evaluator_calls_per_task": 1,
        "order": args.order,
        "config": str(args.config),
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "source": git_revision(),
        "strict_process_boundary": assert_strict_process_boundary(),
        "started_at": utc_now(),
    }
    write_json(args.result_dir / "metadata.json", metadata)
    result = run_session(args)
    metadata.update(
        {
            "status": (
                "completed"
                if result["status"] in {"passed", "failed"}
                else result["status"]
            ),
            "completed_at": utc_now(),
            "reward": result.get("reward"),
            "classification": result.get("classification"),
        }
    )
    write_json(args.result_dir / "metadata.json", metadata)


if __name__ == "__main__":
    main()
