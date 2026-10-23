#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import sys
import time
import traceback
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image


V2_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = V2_ROOT.parents[1]
OSWORLD_ROOT = PROJECT_ROOT / "third_party" / "OSWorld"
V2_SCRIPTS = V2_ROOT / "scripts"
for path in (V2_ROOT, V2_SCRIPTS, OSWORLD_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from integrations.holo_agent import (  # noqa: E402
    HOLO_GUI_TOOLS,
    HoloAgentConfig,
    HoloNativeAgent,
    execute_desktop_action,
    prepare_action,
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
from scripts.frozen_condition import enforce_runner_condition  # noqa: E402
from scripts.openapa_trajectory import build_trajectory_manifest, write_manifest  # noqa: E402
from scripts.strict_runner_support import (  # noqa: E402
    DEFAULT_CACHE_DIR,
    DEFAULT_QCOW2,
    assert_secret_absent,
    assert_strict_process_boundary,
    capture_evaluator_evidence,
    configure_evaluator_runtime,
    load_tasks,
    should_enable_guest_proxy,
    utc_now,
    write_json,
)


FORBIDDEN_MODEL_SURFACE = (
    "task.execute",
    "task.inspect",
    "artifact.materialize",
    "assessment.grade_multiple_choice_documents",
    "assessment_grade_multiple_choice_documents",
    "task_action_hints",
)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(value, ensure_ascii=False, default=str) + "\n")


def model_preflight(base_url: str, api_key: str, model: str) -> dict[str, Any]:
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
    return match.model_dump(mode="json", exclude_none=True)


def require_screenshot(env: Any, observation: Any, description: str) -> dict[str, Any]:
    current = observation
    seen: list[dict[str, Any]] = []
    for attempt in range(1, 4):
        screenshot = current.get("screenshot") if isinstance(current, dict) else None
        if isinstance(screenshot, (bytes, bytearray, memoryview)) and screenshot:
            normalized = dict(current)
            normalized["screenshot"] = bytes(screenshot)
            return normalized
        seen.append(
            {
                "attempt": attempt,
                "observation_type": type(current).__name__,
                "screenshot_type": type(screenshot).__name__,
            }
        )
        if attempt < 3:
            time.sleep(1)
            current = env._get_obs()
    raise RuntimeError(f"{description} has no screenshot after 3 attempts: {seen}")


def screenshot_size(payload: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(payload)) as image:
        return image.size


def write_model_request(
    task_dir: Path,
    *,
    request_index: int,
    step: int,
    attempt: int,
    screenshot_name: str,
    request: dict[str, Any],
) -> dict[str, Any]:
    encoded = json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    relative = Path("llm_requests") / (
        f"request_{request_index:04d}_step_{step:03d}_attempt_{attempt}.json"
    )
    target = task_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded + b"\n")
    return {
        "request_index": request_index,
        "step": step,
        "attempt": attempt,
        "screenshot": screenshot_name,
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded) + 1,
        "timestamp_utc": utc_now(),
    }


def assert_request_safe(request: dict[str, Any], task_id: str) -> None:
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True)
    forbidden = [
        marker
        for marker in (task_id, task_id[:8], *FORBIDDEN_MODEL_SURFACE)
        if marker.casefold() in encoded.casefold()
    ]
    if forbidden:
        raise RuntimeError(f"invalid_leakage before model request: {forbidden}")


def _complete_zip(payload: Any) -> bool:
    return bool(
        isinstance(payload, (bytes, bytearray))
        and payload
        and zipfile.is_zipfile(io.BytesIO(payload))
    )


def install_stable_evaluator_fetch(
    controller: Any,
    *,
    attempts: int,
    delay_seconds: float,
) -> list[dict[str, Any]]:
    packaged = {
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
    original = controller.get_file
    retry_events: list[dict[str, Any]] = []

    def stable_get_file(path: str) -> Any:
        payload = original(path)
        if Path(path).suffix.lower() not in packaged or _complete_zip(payload):
            return payload
        sizes = [len(payload) if isinstance(payload, (bytes, bytearray)) else None]
        for _ in range(1, attempts):
            time.sleep(delay_seconds)
            payload = original(path)
            sizes.append(
                len(payload) if isinstance(payload, (bytes, bytearray)) else None
            )
            if _complete_zip(payload):
                break
        retry_events.append(
            {
                "path": path,
                "attempts": len(sizes),
                "sizes": sizes,
                "final_valid_zip": _complete_zip(payload),
            }
        )
        return payload

    controller.get_file = stable_get_file
    return retry_events


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
    agent_started = False
    interrupted = False
    events: list[dict[str, Any]] = []
    model_actual: str | None = None
    if "evaluator" in example:
        raise RuntimeError("Agent phase received evaluator configuration")
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
    request_index = 0
    request_context = {"step": 0, "attempt": 0, "screenshot": ""}

    def observe_request(request: dict[str, Any]) -> None:
        nonlocal request_index
        assert_request_safe(request, task["task_id"])
        request_index += 1
        evidence = write_model_request(
            task_dir,
            request_index=request_index,
            step=int(request_context["step"]),
            attempt=int(request_context["attempt"]),
            screenshot_name=str(request_context["screenshot"]),
            request=request,
        )
        append_jsonl(task_dir / "llm_request_index.jsonl", evidence)

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
        observation = env.reset(task_config=reset_task_config(example))
        if not hasattr(env.provider, "assert_agent_egress_policy"):
            raise RuntimeError("strict OSWorld provider has no guest egress boundary")
        record["agent_egress_policy"] = env.provider.assert_agent_egress_policy()
        time.sleep(args.initial_settle_seconds)
        observation = require_screenshot(env, env._get_obs(), "initial observation")
        env.controller.start_recording()
        recording_started = True

        agent_config = HoloAgentConfig(
            base_url=args.base_url,
            model=args.model,
            api_key=args.api_key,
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
            request_timeout_seconds=args.request_timeout,
            image_history_limit=args.image_history,
        )
        agent = HoloNativeAgent(
            agent_config,
            example["instruction"],
            request_observer=observe_request,
        )
        agent_started = True
        prompt_record = {
            "system": agent.messages[0],
            "tools": HOLO_GUI_TOOLS,
            "tool_choice": "required",
            "reasoning_effort": "medium",
            "image_history_limit": args.image_history,
            "coordinate_space": [0, 1000],
        }
        assert_request_safe(prompt_record, task["task_id"])
        (task_dir / "agent_prompt.json").write_text(
            json.dumps(prompt_record, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        record["pre_model_strict_process_boundary"] = assert_strict_process_boundary()
        record["tool_catalog_sha256"] = hashlib.sha256(
            json.dumps(HOLO_GUI_TOOLS, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        (task_dir / "step_000_initial.png").write_bytes(observation["screenshot"])

        loop_started = time.monotonic()
        terminal_action: str | None = None
        for step in range(1, args.max_steps + 1):
            before = observation
            before_name = f"step_{step:03d}_before.png"
            (task_dir / before_name).write_bytes(before["screenshot"])
            agent.observe(before["screenshot"])
            proposal = None
            request_errors: list[dict[str, Any]] = []
            for attempt in range(1, args.model_retries + 1):
                request_context.update(
                    {"step": step, "attempt": attempt, "screenshot": before_name}
                )
                try:
                    proposal = agent.propose()
                    break
                except Exception as exc:
                    request_errors.append(
                        {
                            "attempt": attempt,
                            "type": type(exc).__name__,
                            "detail": str(exc),
                            "timestamp_utc": utc_now(),
                        }
                    )
                    if attempt < args.model_retries:
                        time.sleep(min(2**attempt, 8))
            append_jsonl(
                task_dir / "llm_call_log.jsonl",
                {
                    "step": step,
                    "timestamp_utc": utc_now(),
                    "proposal": proposal,
                    "errors": request_errors,
                    "screenshot": before_name,
                },
            )
            if proposal is None:
                raise RuntimeError(
                    f"model request failed after {args.model_retries} attempts: "
                    f"{request_errors}"
                )
            model_actual = proposal["model_actual"]
            width, height = screenshot_size(before["screenshot"])
            event: dict[str, Any] = {
                "step": step,
                "timestamp_utc": utc_now(),
                "model_call": {
                    "call_id": proposal["call_id"],
                    "name": proposal["name"],
                    "arguments_raw": proposal["arguments_raw"],
                    "arguments": proposal["arguments"],
                    "returned_tool_call_count": proposal["returned_tool_call_count"],
                    "ignored_tool_call_count": proposal["ignored_tool_call_count"],
                },
                "screenshot_before": before_name,
                "executed": False,
            }
            try:
                prepared = prepare_action(
                    proposal["name"],
                    proposal["arguments"],
                    screenshot_width=width,
                    screenshot_height=height,
                    default_settle_seconds=args.action_settle_seconds,
                )
            except Exception as exc:
                result = {
                    "status": "error",
                    "executed": False,
                    "error": {"type": type(exc).__name__, "detail": str(exc)},
                }
                event["result"] = result
                agent.record_tool_result(proposal["call_id"], result)
                observation = require_screenshot(
                    env, env._get_obs(), f"step {step} rejected-action observation"
                )
            else:
                event["prepared_action"] = {
                    "name": prepared.name,
                    "model_arguments": prepared.model_arguments,
                    "pixel_arguments": prepared.pixel_arguments,
                    "command": prepared.command,
                    "settle_seconds": prepared.settle_seconds,
                    "terminal": prepared.terminal,
                }
                if prepared.terminal is not None:
                    terminal_action = prepared.terminal
                    event["result"] = {
                        "status": "terminal",
                        "executed": True,
                        "terminal": terminal_action,
                    }
                    event["executed"] = True
                    env.step(terminal_action, 0.1)
                    observation = require_screenshot(
                        env, env._get_obs(), f"step {step} terminal observation"
                    )
                else:
                    append_jsonl(
                        task_dir / "gui_calls.jsonl",
                        {
                            "step": step,
                            "timestamp_utc": utc_now(),
                            "model_call": event["model_call"],
                            "prepared_action": event["prepared_action"],
                        },
                    )
                    try:
                        execution = execute_desktop_action(
                            env,
                            prepared.command,
                            prepared.settle_seconds,
                        )
                        observation_raw = execution.observation
                        result = execution.result
                        event["execution_transport"] = execution.transport
                        event["executed"] = result["executed"]
                    except Exception as exc:
                        observation_raw = env._get_obs()
                        result = {
                            "status": "error",
                            "executed": False,
                            "error": {
                                "type": type(exc).__name__,
                                "detail": str(exc),
                            },
                        }
                    event["result"] = result
                    agent.record_tool_result(proposal["call_id"], result)
                    observation = require_screenshot(
                        env,
                        observation_raw,
                        f"step {step} post-action observation",
                    )

            after_name = f"step_{step:03d}_after.png"
            (task_dir / after_name).write_bytes(observation["screenshot"])
            event["screenshot_after"] = after_name
            events.append(event)
            append_jsonl(task_dir / "holo_agent_events.jsonl", event)
            if terminal_action is not None:
                record["termination_reason"] = (
                    "agent_done" if terminal_action == "DONE" else "agent_failed"
                )
                break
            elapsed = time.monotonic() - loop_started
            if elapsed >= args.max_agent_seconds:
                record["termination_reason"] = "agent_loop_time_budget_exhausted"
                record["runner_termination"] = {
                    "limit_seconds": args.max_agent_seconds,
                    "elapsed_seconds": round(elapsed, 3),
                }
                break
        else:
            record["termination_reason"] = "max_steps_exhausted"

        final_observation = require_screenshot(env, env._get_obs(), "final observation")
        (task_dir / "final.png").write_bytes(final_observation["screenshot"])
        time.sleep(args.evaluator_settle_seconds)
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
        attach_evaluator_after_episode(env, evaluator_example, episode_finished=True)
        record["evaluation_boundary"]["evaluator_loaded_after_agent"] = True
        retries = install_stable_evaluator_fetch(
            env.controller,
            attempts=args.evaluator_file_fetch_attempts,
            delay_seconds=args.evaluator_file_fetch_delay_seconds,
        )
        record["evaluator_file_fetch"] = {"retry_events": retries}
        reward = float(env.evaluate())
        (task_dir / "result.txt").write_text(f"{reward}\n", encoding="utf-8")
        record.update(
            {
                "status": "passed" if reward == 1.0 else "failed",
                "reward": reward,
                "path_class": "gui_only",
                "steps": len(events),
                "terminated_by_agent": terminal_action is not None,
                "terminal_action": terminal_action,
                "model_actual": model_actual,
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
                "path_class": "gui_only" if agent_started else "environment_failure",
                "steps": len(events),
                "error": {"type": "KeyboardInterrupt", "detail": "run interrupted"},
            }
        )
        (task_dir / "exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    except Exception as exc:
        if agent_started:
            record["status"] = "failed"
            record["path_class"] = "gui_only"
        record["steps"] = len(events)
        record["error"] = {"type": type(exc).__name__, "detail": str(exc)}
        (task_dir / "exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8"
        )
    finally:
        if env is not None:
            if recording_started:
                try:
                    env.controller.end_recording(str(task_dir / "recording.mp4"))
                except Exception as exc:
                    record.setdefault("recording_error", str(exc))
            try:
                env.close()
            except Exception as exc:
                record.setdefault("cleanup_error", str(exc))

    completed_at = utc_now()
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    manifest = build_trajectory_manifest(
        task_dir,
        episode_context={
            "episode_id": os.environ.get("HOLO_AGENT_EPISODE_ID"),
            "task_id": task["task_id"],
            "order": task["order"],
            "domain": task["domain"],
            "run_index": 1,
            "attempt_index": 1,
            "tool_catalog_sha256": record.get("tool_catalog_sha256"),
        },
        record=record,
        instruction=example["instruction"],
        agent_prompt=(task_dir / "agent_prompt.json").read_text(encoding="utf-8")
        if (task_dir / "agent_prompt.json").is_file()
        else "",
        model_requested=args.model,
        reasoning_effort="medium",
        max_steps=args.max_steps,
        config_sha256=metadata["config_sha256"],
        coverage_sha256=None,
        osworld_commit=metadata["osworld_commit"],
        openapa_commit="not_used",
        screen_size=metadata["screen_size"],
        grounding_coordinate_size=[1000, 1000],
        started_at=started_at,
        completed_at=completed_at,
        schema_version="holo_native.osworld.trajectory.v1",
        agent_framework="HoloNativeFunctionCalling",
        model_identifier_source="native OpenAI-compatible response.model",
    )
    manifest["agent"]["generation_config"] = {
        "max_output_tokens": args.max_output_tokens,
        "temperature": args.temperature,
        "reasoning_effort": "medium",
        "thinking": True,
        "image_history_limit": args.image_history,
        "tool_choice": "required",
        "route": "gui_only",
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
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--orders", type=int, nargs="+", default=None)
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument(
        "--max-no-progress-steps",
        type=int,
        default=8,
        help="Supervisor compatibility field; Holo currently relies on its hard time/step budgets.",
    )
    parser.add_argument("--max-agent-seconds", type=float, default=300.0)
    parser.add_argument("--model", default="holo3.1-4b")
    parser.add_argument("--base-url", default="http://192.168.0.224:8002/v1")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument(
        "--top-k",
        type=int,
        default=7,
        help="Supervisor compatibility field; native Holo receives the complete fixed GUI toolbox.",
    )
    parser.add_argument("--thinking", action="store_true")
    parser.add_argument("--no-gui", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--image-history", type=int, default=3)
    parser.add_argument("--request-timeout", type=float, default=180.0)
    parser.add_argument("--model-retries", type=int, default=2)
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
    if args.max_steps <= 0 or args.max_agent_seconds <= 0:
        parser.error("step and time budgets must be positive")
    if args.max_no_progress_steps < 4:
        parser.error("max no-progress steps must be at least 4")
    if args.no_gui:
        parser.error("Holo native condition is GUI-only and cannot disable GUI tools")
    if args.image_history != 3:
        parser.error("Holo official harness requires exactly 3 retained screenshots")
    if args.temperature != 0.8:
        parser.error("Holo official agent-loop example uses temperature 0.8")
    if args.evaluator_file_fetch_attempts <= 0:
        parser.error("evaluator file fetch attempts must be positive")
    if args.evaluator_file_fetch_delay_seconds < 0:
        parser.error("evaluator file fetch delay must be non-negative")

    strict_process_boundary = assert_strict_process_boundary()
    os.chdir(OSWORLD_ROOT)
    configure_evaluator_runtime()
    config, tasks = load_tasks(
        args.config,
        args.limit,
        set(args.orders) if args.orders is not None else None,
    )
    if config.get("condition", {}).get("baseline_candidate", False):
        raise ValueError("exploratory Holo Runner cannot produce a baseline candidate")
    if config.get("protocol", {}).get("task_specific_or_golden_exposed", False):
        raise ValueError("Holo Runner rejects task-specific or golden-enabled configs")
    if config.get("protocol", {}).get("tools") != "holo_native_gui_only":
        raise ValueError("Holo Runner requires the explicit GUI-only tool condition")
    frozen_condition = (
        enforce_runner_condition(config, args, PROJECT_ROOT)
        if config.get("status") == "frozen"
        else {
            "status": "not_enforced_exploration",
            "baseline_candidate": False,
            "promotion_pre_authorized": False,
        }
    )
    model_info = model_preflight(args.base_url, args.api_key, args.model)
    install_provider_patch()
    args.result_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "experiment_id": args.result_dir.name,
        "status": "running",
        "stage": "exploration",
        "promotable": False,
        "agent_framework": "HoloNativeFunctionCalling",
        "model_requested": args.model,
        "model_preflight": model_info,
        "base_url": args.base_url,
        "reasoning_effort": "medium",
        "thinking": True,
        "temperature": args.temperature,
        "max_output_tokens": args.max_output_tokens,
        "image_history_limit": args.image_history,
        "tools": "holo_native_gui_only",
        "task_specific_or_golden_exposed": False,
        "strict_process_boundary": strict_process_boundary,
        "frozen_condition": frozen_condition,
        "agent_task_id_visible": False,
        "task_id_usage": "runner_internal_setup_evaluator_and_trace_only",
        "evaluator_loaded_after_episode": True,
        "max_steps": args.max_steps,
        "max_no_progress_steps": args.max_no_progress_steps,
        "max_agent_seconds": args.max_agent_seconds,
        "screen_size": [args.screen_width, args.screen_height],
        "coordinate_space": [0, 1000],
        "task_count": len(tasks),
        "task_order": [task["task_id"] for task in tasks],
        "osworld_commit": config["osworld_commit"],
        "config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
        "started_at": utc_now(),
    }
    write_json(args.result_dir / "metadata.json", metadata)
    results: list[dict[str, Any]] = []
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
            / f"{task['order']:03d}-{task['domain']}-{task['task_id']}"
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
        if result["status"] == "interrupted":
            break

    completed = len(results) == len(tasks) and not any(
        item["status"] == "interrupted" for item in results
    )
    metadata.update(
        {
            "status": "completed" if completed else "interrupted",
            "completed_at": utc_now(),
            "passed": sum(item["status"] == "passed" for item in results),
            "failed": sum(item["status"] == "failed" for item in results),
            "environment_failure": sum(
                item["status"] == "environment_failure" for item in results
            ),
            "interrupted": sum(item["status"] == "interrupted" for item in results),
        }
    )
    write_json(args.result_dir / "metadata.json", metadata)
    write_json(
        args.result_dir / "results.json", {"metadata": metadata, "tasks": results}
    )


if __name__ == "__main__":
    main()
