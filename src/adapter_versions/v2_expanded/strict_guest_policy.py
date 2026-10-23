"""Guest-side enforcement for strict generic-only Adapter actions.

The host creates a per-domain policy manifest only for strict deployments. A
normal legacy deployment has no manifest and therefore keeps its historical
surface. Strict policy is enforced before an Adapter request reaches its schema
or worker, including requests sent directly to the guest HTTP endpoint.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request


POLICY_FILENAME = "strict_action_policy.json"
POLICY_SCHEMA_VERSION = 1
_POLICY_KEYS = {
    "schema_version",
    "strict_generic",
    "domain",
    "allowed_actions",
}
_GUARDED_PATHS = frozenset({"/v1/actions", "/v1/verify"})


@dataclass(frozen=True)
class GuestActionPolicy:
    domain: str
    strict_generic: bool
    allowed_actions: frozenset[str]
    sha256: str | None
    manifest_path: str | None

    @classmethod
    def load(cls, domain: str, package_file: str | Path) -> GuestActionPolicy:
        package_dir = Path(package_file).resolve().parent
        manifest = package_dir / POLICY_FILENAME
        if not manifest.is_file():
            return cls(
                domain=domain,
                strict_generic=False,
                allowed_actions=frozenset(),
                sha256=None,
                manifest_path=None,
            )

        raw = manifest.read_bytes()
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"invalid strict action policy JSON: {manifest}"
            ) from exc
        if not isinstance(payload, dict) or set(payload) != _POLICY_KEYS:
            raise RuntimeError("strict action policy has an invalid top-level schema")
        if payload.get("schema_version") != POLICY_SCHEMA_VERSION:
            raise RuntimeError("strict action policy has an unsupported schema version")
        if payload.get("strict_generic") is not True:
            raise RuntimeError("an installed strict action policy must fail closed")
        if payload.get("domain") != domain:
            raise RuntimeError(
                f"strict action policy domain mismatch: expected {domain!r}"
            )
        actions = payload.get("allowed_actions")
        if (
            not isinstance(actions, list)
            or not actions
            or any(not isinstance(action, str) or not action for action in actions)
            or actions != sorted(set(actions))
        ):
            raise RuntimeError(
                "strict action policy allowed_actions must be a non-empty sorted unique list"
            )
        return cls(
            domain=domain,
            strict_generic=True,
            allowed_actions=frozenset(actions),
            sha256=hashlib.sha256(raw).hexdigest(),
            manifest_path=str(manifest),
        )

    def allows(self, action: str) -> bool:
        return not self.strict_generic or action in self.allowed_actions

    def health(self) -> dict[str, Any]:
        return {
            "strict_generic": self.strict_generic,
            "domain": self.domain,
            "allowed_action_count": len(self.allowed_actions),
            "policy_sha256": self.sha256,
        }


def install_strict_action_guard(
    app: Flask,
    domain: str,
    package_file: str | Path,
) -> GuestActionPolicy:
    """Install a fail-closed HTTP guard and return its immutable policy state."""

    policy = GuestActionPolicy.load(domain, package_file)

    @app.before_request
    def reject_disabled_strict_action():
        if not policy.strict_generic or request.path not in _GUARDED_PATHS:
            return None
        payload = request.get_json(silent=True)
        action = payload.get("action") if isinstance(payload, dict) else None
        if not isinstance(action, str) or policy.allows(action):
            return None
        request_id = payload.get("request_id")
        return (
            jsonify(
                {
                    "request_id": request_id,
                    "status": "error",
                    "result": None,
                    "verification": None,
                    "error_code": "STRICT_ACTION_DISABLED",
                    "error": {
                        "code": "STRICT_ACTION_DISABLED",
                        "message": (
                            f"action {action!r} is disabled by the strict generic-only "
                            "guest policy"
                        ),
                        "details": {"domain": domain, "action": action},
                    },
                    "duration_ms": 0,
                    "logs": [],
                }
            ),
            403,
        )

    return policy
