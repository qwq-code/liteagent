#!/usr/bin/env python3
"""Run the source-built Codex/Qwen desktop experiment in an isolated session."""

import argparse
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4


V2_ROOT = Path(__file__).resolve().parents[1]
ASSETS = V2_ROOT / "integrations" / "codex_agent"


def model_catalog(model):
    return {
        "models": [
            {
                "slug": model,
                "display_name": model,
                "description": "Single-model computer-use experiment",
                "base_instructions": "Use the available desktop tools to complete the user request.",
                "supported_reasoning_levels": [],
                "shell_type": "disabled",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 1,
                "support_verbosity": False,
                "apply_patch_tool_type": None,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "experimental_supported_tools": [],
                "include_skills_usage_instructions": False,
                "include_plugin_usage_instructions": False,
                "include_apps_usage_instructions": False,
                "supports_reasoning_summary_parameter": False,
                "default_reasoning_summary": "none",
                "input_modalities": ["text", "image"],
                "context_window": 262144,
                "supports_search_tool": False,
                "node_repl_disabled": True,
                "tool_mode": "direct",
                "multi_agent_version": "disabled",
            }
        ]
    }


def stop_child(process):
    if process is None:
        return
    # Only this invocation's own process group. Codex starts MCP in a separate group.
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run(args):
    os.umask(0o077)
    source = args.source_root.resolve()
    if not args.skip_build:
        subprocess.run(["bash", str(source / "run-dev.sh"), "--version"], check=True)
    binary = source / "codex-rs" / "target" / "debug" / "codex"
    if not binary.is_file():
        raise FileNotFoundError(f"Build the development CLI first: {binary}")
    prompt = args.prompt_file.read_text() if args.prompt_file else args.prompt
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or (
            V2_ROOT
            / "experiments"
            / "work"
            / "codex-qwen"
            / f"{stamp}-{uuid4().hex[:8]}"
        )
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    session_home = run_dir / "home"
    workspace = run_dir / "workspace"
    session_home.mkdir()
    workspace.mkdir()
    (run_dir / "prompt.txt").write_text(prompt)
    (session_home / "models.json").write_text(json.dumps(model_catalog(args.model)))
    (session_home / "instructions.md").write_text(
        (ASSETS / "instructions.md").read_text()
    )
    upstream = args.upstream_url.rstrip("/")
    if not upstream.endswith("/chat/completions"):
        upstream += "/chat/completions"
    metadata = {
        "label": "non_promotable_development",
        "started_at": stamp,
        "model": args.model,
        "upstream_url": upstream,
        "reasoning_mode": args.reasoning_mode,
        "protocol": {"thinking": args.reasoning_mode == "thinking", "stream": True},
        "max_tokens": args.max_tokens,
        "request_timeout_seconds": args.request_timeout,
        "max_steps": args.max_steps,
        "timeout_seconds": args.timeout_seconds,
        "guest_url": args.guest_url,
        "desktop_observation": {
            "after_gui_action": True,
            "click_target": "ocr_text",
            "default_action_settle_seconds": 0.5,
            "coordinate_tools": False,
            "ocr_enabled": not args.no_ocr,
            "ocr_engine": "tesseract",
            "ocr_language": args.ocr_language,
            "ocr_timeout_seconds": 5,
        }
        if args.guest_url
        else None,
        "codex_source": str(source),
        "codex_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, text=True
        ).strip(),
        "codex_dirty": bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=source, text=True
            ).strip()
        ),
        "status": "starting",
    }
    metadata_path = run_dir / "run.json"
    metadata_path.write_text(json.dumps(metadata, indent=2))
    child_env = os.environ.copy()
    child_env["CODEX_HOME"] = str(session_home)
    child_env["PYTHONPATH"] = str(V2_ROOT)
    # Qwen auth belongs to the proxy only; never copy the current Codex login.
    proxy_key = child_env.pop(args.api_key_env, "local-qwen")
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"):
        child_env.pop(key, None)
    proxy = agent = None
    started = time.monotonic()
    outcome = "failed"
    try:
        with (run_dir / "proxy.log").open("w") as proxy_log:
            proxy = subprocess.Popen(
                [
                    str(binary),
                    "responses-api-proxy",
                    "--chat-completions",
                    "--upstream-url",
                    upstream,
                    "--reasoning-mode",
                    args.reasoning_mode,
                    "--max-tokens",
                    str(args.max_tokens),
                    "--timeout-secs",
                    str(args.request_timeout),
                    "--server-info",
                    str(run_dir / "proxy.json"),
                    "--dump-dir",
                    str(run_dir / "wire"),
                ],
                stdin=subprocess.PIPE,
                stdout=proxy_log,
                stderr=proxy_log,
                env=child_env,
                text=True,
                start_new_session=True,
            )
            proxy.stdin.write(proxy_key + "\n")
            proxy.stdin.close()
            ready_deadline = time.monotonic() + 15
            proxy_info = None
            while time.monotonic() < ready_deadline:
                if proxy.poll() is not None:
                    raise RuntimeError(
                        f"Protocol proxy exited; see {run_dir / 'proxy.log'}"
                    )
                try:
                    proxy_info = json.loads((run_dir / "proxy.json").read_text())
                    break
                except (FileNotFoundError, json.JSONDecodeError):
                    time.sleep(0.05)
            if proxy_info is None:
                raise TimeoutError("Protocol proxy did not start within 15 seconds")
            config = (
                f"model = {json.dumps(args.model)}\n"
                'model_provider = "qwen-test"\n'
                'model_catalog_json = "models.json"\n'
                'model_instructions_file = "instructions.md"\n'
                + (ASSETS / "config.toml").read_text()
                + '\n[model_providers.qwen-test]\nname = "Qwen test bridge"\n'
                + f'base_url = "http://127.0.0.1:{proxy_info["port"]}/v1"\n'
                + 'wire_api = "responses"\nrequires_openai_auth = false\n'
                + "supports_websockets = false\nrequest_max_retries = 0\n"
                + "stream_max_retries = 0\nstream_idle_timeout_ms = 300000\n"
            )
            if args.guest_url:
                mcp_args = [
                    str(ASSETS / "desktop_mcp.py"),
                    "--guest-url",
                    args.guest_url,
                    "--trace-dir",
                    str(run_dir / "desktop"),
                    "--max-steps",
                    str(args.max_steps),
                    "--timeout-seconds",
                    str(args.timeout_seconds),
                    "--ocr-language",
                    args.ocr_language,
                ]
                if args.no_ocr:
                    mcp_args.append("--no-ocr")
                if args.adapter_urls_json:
                    mcp_args += [
                        "--adapter-urls-json",
                        str(args.adapter_urls_json.resolve()),
                    ]
                config += (
                    "\n[mcp_servers.desktop]\n"
                    f"command = {json.dumps(sys.executable)}\n"
                    f"args = {json.dumps(mcp_args)}\n"
                    f"env = {{ PYTHONPATH = {json.dumps(str(V2_ROOT))} }}\n"
                    "required = true\nstartup_timeout_sec = 30\n"
                    'default_tools_approval_mode = "approve"\n'
                    "tool_timeout_sec = 180\nsupports_parallel_tool_calls = false\n"
                )
            (session_home / "config.toml").write_text(config)
            command = [
                str(binary),
                "exec",
                "--json",
                "--ephemeral",
                "--skip-git-repo-check",
                "--cd",
                str(workspace),
            ]
            for path in args.image:
                command += ["--image", str(path.resolve())]
            command.append("-")
            events = queue.Queue()
            with (
                (run_dir / "agent.log").open("w") as stderr,
                (run_dir / "events.jsonl").open("w") as trace,
            ):
                agent = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=stderr,
                    env=child_env,
                    text=True,
                    start_new_session=True,
                )
                agent.stdin.write(prompt)
                agent.stdin.close()

                def collect():
                    for line in agent.stdout:
                        events.put(line)
                    events.put(None)

                threading.Thread(target=collect, daemon=True).start()
                calls = 0
                metadata["status"] = "running"
                metadata_path.write_text(json.dumps(metadata, indent=2))
                deadline = started + args.timeout_seconds
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        outcome = "deadline_exhausted"
                        break
                    try:
                        line = events.get(timeout=min(remaining, 1))
                    except queue.Empty:
                        continue
                    if line is None:
                        break
                    trace.write(line)
                    trace.flush()
                    event = json.loads(line)
                    item = event.get("item", {})
                    if event["type"] == "turn.completed":
                        outcome = "completed"
                    if event["type"] == "turn.failed":
                        outcome = "failed"
                    if event["type"] == "item.completed":
                        if item.get("type") == "agent_message":
                            print(item["text"], flush=True)
                        if item.get("type") == "mcp_tool_call":
                            calls += 1
                            if calls >= args.max_steps:
                                outcome = "step_budget_exhausted"
                                break
                metadata["tool_calls"] = calls
    except KeyboardInterrupt:
        outcome = "interrupted"
    finally:
        try:
            mcp_info = json.loads((run_dir / "desktop" / "server.json").read_text())
            os.kill(mcp_info["pid"], signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError):
            pass
        stop_child(agent)
        stop_child(proxy)
        metadata.update(
            status=outcome, duration_seconds=round(time.monotonic() - started, 3)
        )
        metadata_path.write_text(json.dumps(metadata, indent=2))
        print(f"{outcome}: {run_dir}", file=sys.stderr)
    return 0 if outcome == "completed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root", type=Path, default=Path("/home/liuhao/codex-qwen")
    )
    parser.add_argument("--upstream-url", default="https://qwen.jinmaoapi.cc.cd/v1")
    parser.add_argument("--model", default="qwen3.5-4b")
    parser.add_argument("--api-key-env", default="QWEN_API_KEY")
    parser.add_argument(
        "--reasoning-mode", choices=["thinking", "non_thinking"], default="thinking"
    )
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--request-timeout", type=int, default=240)
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--timeout-seconds", type=float, default=1800)
    parser.add_argument(
        "--guest-url", help="Explicit OSWorld guest HTTP URL; omit for text-only probes"
    )
    parser.add_argument("--adapter-urls-json", type=Path)
    parser.add_argument(
        "--ocr-language", default="eng", help="Installed Tesseract language(s)"
    )
    parser.add_argument(
        "--no-ocr", action="store_true", help="Return screenshots without OCR"
    )
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Reuse the already-built development binary",
    )
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("--prompt")
    prompt.add_argument("--prompt-file", type=Path)
    args = parser.parse_args()
    if (
        min(args.max_steps, args.timeout_seconds, args.request_timeout, args.max_tokens)
        <= 0
    ):
        parser.error("Step, time and token budgets must be positive")
    if args.adapter_urls_json and not args.guest_url:
        parser.error("--adapter-urls-json requires --guest-url")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
