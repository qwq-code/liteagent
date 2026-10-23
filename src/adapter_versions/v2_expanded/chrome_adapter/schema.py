from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from uuid import uuid4

from .errors import AdapterError


ADAPTER_NAME = "chrome"
MIN_TIMEOUT_MS = 100
MAX_TIMEOUT_MS = 120_000
DEFAULT_TIMEOUT_MS = 30_000

ACTIONS = frozenset(
    {
        "browser.inspect",
        "browser.ensure_running",
        "browser.restart",
        "tab.list",
        "tab.open",
        "tab.activate",
        "tab.close",
        "tab.restore_last_closed",
        "page.snapshot",
        "page.goto",
        "page.click",
        "page.fill",
        "page.select",
        "page.press",
        "page.wait_for",
        "page.read",
        "bookmark.create_folder",
        "bookmark.add_current",
        "settings.set",
        "privacy.delete_cookies",
        "privacy.delete_history",
        "extension.load_unpacked",
        "shortcut.create_current",
        "page.print_pdf",
    }
)

VERIFY_TYPES = frozenset(
    {
        "browser_ready",
        "active_url",
        "tabs",
        "page_state",
        "preference",
        "bookmark",
        "cookies_absent",
        "history_absent",
        "extension_path",
        "desktop_shortcut",
        "pdf_file",
        "settings",
    }
)

LOCATOR_KEYS = frozenset({"css", "xpath", "text", "label", "role"})
TARGET_KEYS = frozenset({"target_id", "url", "title", "index"})
TARGET_REQUIRED_ACTIONS = frozenset(
    {
        "page.snapshot",
        "page.goto",
        "page.click",
        "page.fill",
        "page.select",
        "page.press",
        "page.wait_for",
        "page.read",
        "bookmark.add_current",
        "shortcut.create_current",
        "page.print_pdf",
    }
)
SETTING_KEYS = frozenset(
    {
        "do_not_track",
        "safe_browsing",
        "profile_name",
        "startup_mode",
        "appearance",
        "clear_on_exit",
        "font_size",
        "search_engine",
    }
)
FONT_SIZE_ALIASES = {
    "very_small": 9,
    "small": 12,
    "medium": 16,
    "large": 20,
    "very_large": 24,
    "largest": 24,
}
SETTING_PREFERENCE_PATHS = {
    "do_not_track": "enable_do_not_track",
    "safe_browsing": "safebrowsing.enabled",
    "profile_name": "profile.name",
    "startup_mode": "session.restore_on_startup",
    "appearance": "browser.theme.color_scheme",
    "clear_on_exit": "profile.default_content_setting_values.cookies",
    "font_size": "webkit.webprefs.default_font_size",
    "search_engine": "default_search_provider_data.template_url_data.short_name",
}


@dataclass(frozen=True)
class ActionRequest:
    request_id: str
    adapter: str
    action: str
    timeout_ms: int
    target: dict[str, Any]
    params: dict[str, Any]
    verify: list[dict[str, Any]]

    def to_worker_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "timeout_ms": self.timeout_ms,
            "target": self.target,
            "params": self.params,
            "verify": self.verify,
        }


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise AdapterError("INVALID_REQUEST", f"{field} must be an object")
    return dict(value)


def _required_string(
    data: Mapping[str, Any], field: str, prefix: str = "params"
) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a non-empty string"
        )
    return value


def _optional_bool(data: Mapping[str, Any], field: str, prefix: str = "params") -> None:
    if field in data and not isinstance(data[field], bool):
        raise AdapterError("INVALID_REQUEST", f"{prefix}.{field} must be a boolean")


def _positive_int(data: Mapping[str, Any], field: str, prefix: str = "params") -> None:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AdapterError(
            "INVALID_REQUEST", f"{prefix}.{field} must be a positive integer"
        )


def _normalize_settings(params: dict[str, Any]) -> dict[str, Any]:
    settings = params.get("settings")
    if not isinstance(settings, Mapping):
        return params
    normalized = dict(settings)
    alias = normalized.pop("default_font_size", None)
    if alias is not None:
        if "font_size" in normalized and normalized["font_size"] != alias:
            raise AdapterError(
                "INVALID_REQUEST",
                "font_size and default_font_size must not conflict",
            )
        normalized.setdefault("font_size", alias)
    font_size = normalized.get("font_size")
    if isinstance(font_size, str):
        mapped = FONT_SIZE_ALIASES.get(font_size.strip().lower())
        if mapped is None:
            raise AdapterError(
                "INVALID_REQUEST",
                "font_size name is unsupported",
                {"supported": sorted(FONT_SIZE_ALIASES)},
            )
        normalized["font_size"] = mapped
    return params | {"settings": normalized}


def setting_verification_checks(settings: Mapping[str, Any]) -> list[dict[str, Any]]:
    normalized = _normalize_settings({"settings": settings})["settings"]
    validate_action_params("settings.set", {"settings": normalized})
    expected_values = {
        "startup_mode": {"continue": 1, "new_tab": 5},
        "appearance": {"system": 0, "light": 1, "dark": 2},
        "clear_on_exit": {True: 4, False: None},
        "search_engine": {"bing": "Microsoft Bing", "google": "Google"},
    }
    return [
        {
            "type": "preference",
            "path": SETTING_PREFERENCE_PATHS[key],
            "expected": expected_values.get(key, {}).get(value, value),
        }
        for key, value in normalized.items()
    ]


def _locator(value: Any, prefix: str = "params.locator") -> dict[str, Any]:
    locator = _mapping(value, prefix)
    used = LOCATOR_KEYS.intersection(locator)
    if len(used) != 1:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix} must contain exactly one of {sorted(LOCATOR_KEYS)}",
        )
    key = next(iter(used))
    _required_string(locator, key, prefix)
    if key == "role" and "name" in locator:
        _required_string(locator, "name", prefix)
    if "index" in locator:
        index = locator["index"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise AdapterError(
                "INVALID_REQUEST", f"{prefix}.index must be a non-negative integer"
            )
    _optional_bool(locator, "exact", prefix)
    return locator


def _target(value: Any, prefix: str = "target") -> dict[str, Any]:
    target = _mapping(value, prefix)
    unexpected = sorted(set(target) - TARGET_KEYS)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix} contains unsupported selectors",
            {"unexpected": unexpected, "allowed": sorted(TARGET_KEYS)},
        )
    if not target:
        raise AdapterError(
            "INVALID_REQUEST",
            f"{prefix} requires at least one exact selector copied from tab.list",
        )
    if "index" in target:
        index = target["index"]
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise AdapterError(
                "INVALID_REQUEST", f"{prefix}.index must be a non-negative integer"
            )
    for field in ("target_id", "url", "title"):
        if field in target:
            _required_string(target, field, prefix)
    return target


def _verification(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError("INVALID_REQUEST", "verify must be an array")
    checks: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        check = _mapping(raw, f"verify[{index}]")
        check_type = check.get("type")
        if check_type is None and isinstance(check.get("path"), str):
            path = check["path"]
            if path.startswith("settings.") and "equals" in check:
                setting = path.removeprefix("settings.")
                checks.extend(setting_verification_checks({setting: check["equals"]}))
                continue
        if check_type not in VERIFY_TYPES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"verify[{index}].type is unsupported",
                {"type": check_type},
            )
        if check_type == "settings":
            settings = _mapping(check.get("settings"), f"verify[{index}].settings")
            if not settings:
                raise AdapterError(
                    "INVALID_REQUEST",
                    f"verify[{index}].settings must not be empty",
                )
            checks.extend(setting_verification_checks(settings))
            continue
        if check_type in {
            "active_url",
            "preference",
            "cookies_absent",
            "history_absent",
            "extension_path",
            "desktop_shortcut",
            "pdf_file",
        }:
            field = {
                "active_url": "expected",
                "preference": "path",
                "cookies_absent": "domain",
                "history_absent": "contains",
                "extension_path": "path",
                "desktop_shortcut": "path",
                "pdf_file": "path",
            }[check_type]
            _required_string(check, field, f"verify[{index}]")
        if check_type == "page_state" and "locator" in check:
            _locator(check["locator"], f"verify[{index}].locator")
        if check_type in {"active_url", "page_state"}:
            _target(check.get("target"), f"verify[{index}].target")
        checks.append(check)
    return checks


def validate_action_params(action: str, params: Mapping[str, Any]) -> None:
    if action in {"tab.open", "page.goto"}:
        _required_string(params, "url")
    elif action in {"tab.activate", "tab.close"}:
        if not any(
            params.get(field) is not None
            for field in ("target_id", "url", "title", "index")
        ):
            raise AdapterError("INVALID_REQUEST", "a tab selector is required")
    elif action in {"page.click", "page.fill", "page.select"}:
        _locator(params.get("locator"))
        if action == "page.fill":
            if not isinstance(params.get("value"), str):
                raise AdapterError("INVALID_REQUEST", "params.value must be a string")
        if action == "page.select":
            _required_string(params, "value")
    elif action == "page.press":
        _required_string(params, "key")
        if "locator" in params:
            _locator(params["locator"])
    elif action == "page.wait_for":
        if not any(
            key in params
            for key in ("url_contains", "url_matches", "text", "locator", "ready_state")
        ):
            raise AdapterError("INVALID_REQUEST", "page.wait_for requires a condition")
        if "locator" in params:
            _locator(params["locator"])
    elif action == "page.read":
        if "locator" in params:
            _locator(params["locator"])
    elif action == "bookmark.create_folder":
        _required_string(params, "name")
    elif action == "settings.set":
        settings = _mapping(params.get("settings"), "params.settings")
        if not settings:
            raise AdapterError("INVALID_REQUEST", "params.settings must not be empty")
        unsupported = sorted(set(settings) - SETTING_KEYS)
        if unsupported:
            raise AdapterError(
                "INVALID_REQUEST", "unsupported Chrome settings", {"keys": unsupported}
            )
        if "profile_name" in settings:
            _required_string(settings, "profile_name", "params.settings")
        if "startup_mode" in settings and settings["startup_mode"] not in {
            "new_tab",
            "continue",
        }:
            raise AdapterError(
                "INVALID_REQUEST", "startup_mode must be new_tab or continue"
            )
        if "appearance" in settings and settings["appearance"] not in {
            "light",
            "dark",
            "system",
        }:
            raise AdapterError(
                "INVALID_REQUEST", "appearance must be light, dark, or system"
            )
        if "font_size" in settings:
            _positive_int(settings, "font_size", "params.settings")
        if "search_engine" in settings and settings["search_engine"] not in {
            "bing",
            "google",
        }:
            raise AdapterError(
                "INVALID_REQUEST", "search_engine must be bing or google"
            )
        for key in ("do_not_track", "safe_browsing", "clear_on_exit"):
            _optional_bool(settings, key, "params.settings")
    elif action == "privacy.delete_cookies":
        _required_string(params, "domain")
    elif action == "privacy.delete_history":
        _required_string(params, "contains")
    elif action == "extension.load_unpacked":
        _required_string(params, "path")
    elif action == "shortcut.create_current":
        if "name" in params:
            _required_string(params, "name")
    elif action == "page.print_pdf":
        path = _required_string(params, "path")
        if not path.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST", "params.path must be absolute or begin with ~/"
            )
        _optional_bool(params, "landscape")
        _optional_bool(params, "print_background")


def parse_action_request(payload: Any) -> ActionRequest:
    data = _mapping(payload, "request")
    request_id = data.get("request_id") or str(uuid4())
    if not isinstance(request_id, str) or not request_id.strip():
        raise AdapterError("INVALID_REQUEST", "request_id must be a non-empty string")
    adapter = data.get("adapter", ADAPTER_NAME)
    if adapter != ADAPTER_NAME:
        raise AdapterError(
            "INVALID_REQUEST",
            "adapter does not match this service",
            {"expected": ADAPTER_NAME, "actual": adapter},
        )
    action = data.get("action")
    if action not in ACTIONS:
        raise AdapterError(
            "UNSUPPORTED_OPERATION", "action is not supported", {"action": action}
        )
    timeout_ms = data.get("timeout_ms", DEFAULT_TIMEOUT_MS)
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int):
        raise AdapterError("INVALID_REQUEST", "timeout_ms must be an integer")
    if not MIN_TIMEOUT_MS <= timeout_ms <= MAX_TIMEOUT_MS:
        raise AdapterError(
            "INVALID_REQUEST",
            f"timeout_ms must be between {MIN_TIMEOUT_MS} and {MAX_TIMEOUT_MS}",
        )
    target = _mapping(data.get("target"), "target")
    if target:
        target = _target(target)
    elif action in TARGET_REQUIRED_ACTIONS:
        _target(target)
    params = _mapping(data.get("params"), "params")
    if action == "settings.set":
        params = _normalize_settings(params)
    validate_action_params(action, params)
    return ActionRequest(
        request_id=request_id,
        adapter=adapter,
        action=action,
        timeout_ms=timeout_ms,
        target=target,
        params=params,
        verify=_verification(data.get("verify")),
    )
