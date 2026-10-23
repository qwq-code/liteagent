#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
import uuid

import requests


AGENT_TASK_KEYS = ("id", "instruction", "config", "proxy")
RESET_EVALUATOR_PLACEHOLDER = {"func": "infeasible", "result": {}}


def osworld_task_path(osworld_root: Path, task: dict[str, Any]) -> Path:
    return (
        osworld_root
        / "evaluation_examples"
        / "examples"
        / str(task["domain"])
        / f"{task['task_id']}.json"
    )


def _project_agent_task(path: Path) -> dict[str, Any]:
    full = json.loads(path.read_text(encoding="utf-8"))
    return {
        "id": full["id"],
        "instruction": full["instruction"],
        "config": full.get("config", []),
        "proxy": bool(full.get("proxy", False)),
    }


def load_agent_task_config_isolated(
    path: Path,
    *,
    expected_task_id: str,
) -> dict[str, Any]:
    """Load only Agent/setup fields in a short-lived process with no model access."""
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "project-agent-task",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"agent task projection failed for {path}: {completed.stderr.strip()}"
        )
    projected = json.loads(completed.stdout)
    if set(projected) != set(AGENT_TASK_KEYS):
        raise RuntimeError(f"unsafe agent task projection keys: {sorted(projected)}")
    if projected["id"] != expected_task_id:
        raise RuntimeError(
            f"task ID mismatch: expected {expected_task_id}, got {projected['id']}"
        )
    if not isinstance(projected["instruction"], str) or not isinstance(
        projected["config"], list
    ):
        raise RuntimeError("invalid agent task projection")
    return projected


def reset_task_config(agent_task: dict[str, Any]) -> dict[str, Any]:
    if set(agent_task) != set(AGENT_TASK_KEYS):
        raise ValueError("reset requires the isolated Agent task projection")
    return {**agent_task, "evaluator": dict(RESET_EVALUATOR_PLACEHOLDER)}


def load_evaluator_task_config(
    path: Path,
    *,
    expected_task_id: str,
    episode_finished: bool,
) -> dict[str, Any]:
    if not episode_finished:
        raise RuntimeError(
            "evaluator configuration cannot load before the Agent episode ends"
        )
    full = json.loads(path.read_text(encoding="utf-8"))
    if full.get("id") != expected_task_id or not isinstance(
        full.get("evaluator"), dict
    ):
        raise RuntimeError(f"invalid evaluator task configuration: {path}")
    return full


def attach_evaluator_after_episode(
    env: Any,
    evaluator_task: dict[str, Any],
    *,
    episode_finished: bool,
) -> None:
    if not episode_finished:
        raise RuntimeError("evaluator cannot attach before the Agent episode ends")
    env._set_evaluator_info(evaluator_task)


def _download_resources(steps: list[dict[str, Any]]) -> list[tuple[str, str]]:
    resources: list[tuple[str, str]] = []
    for step in steps:
        if step.get("type") != "download":
            continue
        for item in step.get("parameters", {}).get("files", []):
            url = item.get("url")
            guest_path = item.get("path")
            if isinstance(url, str) and isinstance(guest_path, str):
                resources.append(
                    (
                        url,
                        f"{uuid.uuid5(uuid.NAMESPACE_URL, url)}_{Path(guest_path).name}",
                    )
                )
    return resources


def _cloud_file_pairs(value: Any) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if isinstance(value, list):
        for item in value:
            pairs.extend(_cloud_file_pairs(item))
    elif isinstance(value, dict):
        if value.get("type") == "cloud_file":
            paths = value.get("path")
            destinations = value.get("dest")
            if isinstance(paths, str) and isinstance(destinations, str):
                pairs.append((paths, destinations))
            elif isinstance(paths, list) and isinstance(destinations, list):
                pairs.extend(
                    (url, destination)
                    for url, destination in zip(paths, destinations)
                    if isinstance(url, str) and isinstance(destination, str)
                )
        for child in value.values():
            pairs.extend(_cloud_file_pairs(child))
    return pairs


def setup_cache_resources(agent_task: dict[str, Any]) -> list[tuple[str, str]]:
    return list(dict.fromkeys(_download_resources(agent_task.get("config", []))))


def evaluator_cache_resources(evaluator_task: dict[str, Any]) -> list[tuple[str, str]]:
    evaluator = evaluator_task["evaluator"]
    resources = _download_resources(evaluator.get("postconfig", []))
    resources.extend(_cloud_file_pairs(evaluator.get("expected")))
    return list(dict.fromkeys(resources))


def _download_cached_resource(url: str, destination: Path, attempts: int = 6) -> None:
    if destination.is_file() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        temporary = destination.with_name(
            f".{destination.name}.part-{os.getpid()}-{attempt}"
        )
        try:
            with requests.get(
                url,
                stream=True,
                timeout=(30, 600),
                headers={"User-Agent": "OSWorld-local-prefetch/1.0"},
            ) as response:
                response.raise_for_status()
                with temporary.open("wb") as output:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            output.write(chunk)
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError(f"empty download: {url}")
            temporary.replace(destination)
            return
        except Exception as exc:
            last_error = exc
            temporary.unlink(missing_ok=True)
            if attempt < attempts:
                time.sleep(min(2**attempt, 20))
    raise RuntimeError(f"failed to prefetch {url}: {last_error}")


def prefetch_resources(
    task_id: str,
    resources: list[tuple[str, str]],
    cache_dir: Path,
) -> list[Path]:
    task_cache = cache_dir / task_id
    cached: list[Path] = []
    for url, name in resources:
        destination = task_cache / name
        _download_cached_resource(url, destination)
        cached.append(destination)
    return cached


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["project-agent-task"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if args.command == "project-agent-task":
        print(json.dumps(_project_agent_task(args.path), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
