"""Fail-closed network boundary for strict OSWorld Docker guests."""

from __future__ import annotations

from typing import Any


POLICY_SCHEMA = "openapa.agent_egress.v1"
POLICY_CHAIN = "OPENAPA_AGENT_EGRESS"

_INSTALL_SCRIPT = f"""
set -eu
for binary in iptables ip6tables; do
    command -v "$binary" >/dev/null
    "$binary" -w 10 -N {POLICY_CHAIN} 2>/dev/null || true
    "$binary" -w 10 -F {POLICY_CHAIN}
    while "$binary" -w 10 -C OUTPUT -j {POLICY_CHAIN} 2>/dev/null; do
        "$binary" -w 10 -D OUTPUT -j {POLICY_CHAIN}
    done
    "$binary" -w 10 -I OUTPUT 1 -j {POLICY_CHAIN}
    "$binary" -w 10 -A {POLICY_CHAIN} -o lo -j RETURN
    "$binary" -w 10 -A {POLICY_CHAIN} -m conntrack \
        --ctstate ESTABLISHED,RELATED --ctdir REPLY -j RETURN
    "$binary" -w 10 -A {POLICY_CHAIN} -j DROP
done
""".strip()

_VERIFY_SCRIPT = f"""
set -eu
for binary in iptables ip6tables; do
    command -v "$binary" >/dev/null
    first_rule=$("$binary" -w 10 -S OUTPUT | grep -m1 '^-A OUTPUT ' || true)
    test "$first_rule" = '-A OUTPUT -j {POLICY_CHAIN}'
    test "$("$binary" -w 10 -S {POLICY_CHAIN} | grep -c '^-A ' || true)" = 3
    "$binary" -w 10 -C {POLICY_CHAIN} -o lo -j RETURN
    "$binary" -w 10 -C {POLICY_CHAIN} -m conntrack \
        --ctstate ESTABLISHED,RELATED --ctdir REPLY -j RETURN
    "$binary" -w 10 -C {POLICY_CHAIN} -j DROP
done
printf '%s\n' 'ipv4=blocked' 'ipv6=blocked'
""".strip()


def _exec_root_script(container: Any, script: str, purpose: str) -> str:
    result = container.exec_run(["sh", "-eu", "-c", script], user="root")
    exit_code = getattr(result, "exit_code", None)
    output = getattr(result, "output", None)
    if exit_code is None and isinstance(result, tuple) and len(result) == 2:
        exit_code, output = result
    if isinstance(output, bytes):
        rendered = output.decode("utf-8", errors="replace")
    else:
        rendered = str(output or "")
    if exit_code != 0:
        raise RuntimeError(
            f"strict guest egress {purpose} failed with exit code {exit_code}: "
            f"{rendered[-2000:]}"
        )
    return rendered


def verify_agent_egress_policy(container: Any) -> dict[str, Any]:
    output = _exec_root_script(container, _VERIFY_SCRIPT, "verification")
    statuses = {
        key: value
        for line in output.splitlines()
        if "=" in line
        for key, value in [line.split("=", 1)]
    }
    if statuses != {"ipv4": "blocked", "ipv6": "blocked"}:
        raise RuntimeError(
            f"strict guest egress verification returned unexpected state: {statuses}"
        )
    return {
        "schema_version": POLICY_SCHEMA,
        "mode": "deny_agent_initiated_egress",
        "ipv4": statuses["ipv4"],
        "ipv6": statuses["ipv6"],
        "loopback_allowed": True,
        "host_initiated_reply_traffic_allowed": True,
        "agent_initiated_public_or_private_egress_allowed": False,
    }


def install_agent_egress_policy(container: Any) -> dict[str, Any]:
    _exec_root_script(container, _INSTALL_SCRIPT, "installation")
    return verify_agent_egress_policy(container)
