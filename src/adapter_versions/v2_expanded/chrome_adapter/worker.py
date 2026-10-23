from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .cdp import CDPClient, ensure_locator_result, locator_expression, url_matches
from .errors import AdapterError, error_payload
from .lifecycle import ChromeLifecycle
from .schema import setting_verification_checks


HOME = Path.home()
PROFILE = HOME / ".config" / "google-chrome" / "Default"
PREFERENCES = PROFILE / "Preferences"
BOOKMARKS = PROFILE / "Bookmarks"
HISTORY = PROFILE / "History"
COOKIES = PROFILE / "Cookies"
STATE_DIR = HOME / ".config" / "osworld-chrome-adapter"
PROFILE_LOCK = STATE_DIR / "profile.lock"

# Profile actions intentionally restart Chrome. pychrome reports that expected
# socket loss as an error even though the worker has already captured its state.
logging.getLogger("pychrome").setLevel(logging.CRITICAL)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(data)
        temp.flush()
        os.fsync(temp.fileno())
        temp_path = Path(temp.name)
    if path.exists():
        os.chmod(temp_path, path.stat().st_mode)
    else:
        os.chmod(temp_path, 0o600)
    temp_path.replace(path)


def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return dict(default or {})
    except (OSError, ValueError) as exc:
        raise AdapterError(
            "PROFILE_INVALID", f"invalid Chrome JSON file: {path}", str(exc), 422
        ) from exc
    if not isinstance(data, dict):
        raise AdapterError(
            "PROFILE_INVALID",
            f"Chrome JSON root must be an object: {path}",
            http_status=422,
        )
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write(
        path, json.dumps(data, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )


def _with_profile_stopped(callback: Callable[[], Any]) -> Any:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    lifecycle = ChromeLifecycle()
    with PROFILE_LOCK.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        was_running = lifecycle.health()["chrome_ready"]
        if was_running:
            lifecycle.shutdown(10)
        try:
            result = callback()
        finally:
            if was_running:
                lifecycle.prepare(25)
        return result


def _deep_get(data: Any, path: str) -> Any:
    value = data
    for part in path.split("."):
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    return value


def _set_preference(settings: dict[str, Any]) -> dict[str, Any]:
    observed: dict[str, Any] = {}

    def mutate() -> None:
        data = _read_json(PREFERENCES)
        if "do_not_track" in settings:
            data["enable_do_not_track"] = settings["do_not_track"]
        if "safe_browsing" in settings:
            safe = data.setdefault("safebrowsing", {})
            safe["enabled"] = settings["safe_browsing"]
            if settings["safe_browsing"]:
                safe["enhanced"] = False
        if "profile_name" in settings:
            data.setdefault("profile", {})["name"] = settings["profile_name"]
        if "startup_mode" in settings:
            session = data.setdefault("session", {})
            session["restore_on_startup"] = (
                1 if settings["startup_mode"] == "continue" else 5
            )
            if settings["startup_mode"] == "new_tab":
                session.pop("startup_urls", None)
        if "appearance" in settings:
            mode = {"system": 0, "light": 1, "dark": 2}[settings["appearance"]]
            theme = data.setdefault("browser", {}).setdefault("theme", {})
            theme["color_scheme"] = mode
            theme["color_scheme2"] = mode
            # Chrome 130 on Linux also exposes this preference through the
            # Appearance WebUI. The public getter checks both paths.
            system_theme = data.setdefault("extensions", {}).setdefault("theme", {})
            if settings["appearance"] == "system":
                system_theme.pop("system_theme", None)
            else:
                system_theme["system_theme"] = (
                    0 if settings["appearance"] == "light" else 1
                )
        if "clear_on_exit" in settings:
            profile = data.setdefault("profile", {})
            values = profile.setdefault("default_content_setting_values", {})
            if settings["clear_on_exit"]:
                values["cookies"] = 4
            else:
                values.pop("cookies", None)
                if not values:
                    profile.pop("default_content_setting_values", None)
        if "font_size" in settings:
            webprefs = data.setdefault("webkit", {}).setdefault("webprefs", {})
            webprefs["default_font_size"] = settings["font_size"]
        if "search_engine" in settings:
            engines = {
                "bing": {
                    "short_name": "Microsoft Bing",
                    "keyword": "bing.com",
                    "url": "https://www.bing.com/search?q={searchTerms}",
                },
                "google": {
                    "short_name": "Google",
                    "keyword": "google.com",
                    "url": "{google:baseURL}search?q={searchTerms}",
                },
            }
            data.setdefault("default_search_provider_data", {})["template_url_data"] = (
                engines[settings["search_engine"]]
            )
        _write_json(PREFERENCES, data)

    _with_profile_stopped(mutate)
    persisted = _read_json(PREFERENCES)
    checks = setting_verification_checks(settings)
    for key, check in zip(settings, checks, strict=True):
        observed[key] = _deep_get(persisted, check["path"])
    return observed


def _walk_bookmarks(node: Any):
    if not isinstance(node, dict):
        return
    yield node
    for child in node.get("children", []):
        yield from _walk_bookmarks(child)


def _next_bookmark_id(data: dict[str, Any]) -> str:
    maximum = 0
    for root in data.get("roots", {}).values():
        for node in _walk_bookmarks(root):
            try:
                maximum = max(maximum, int(node.get("id", 0)))
            except (TypeError, ValueError):
                pass
    return str(maximum + 1)


def _chrome_time() -> str:
    return str(int((time.time() + 11644473600) * 1_000_000))


def _cdp_timeout_seconds(payload: dict[str, Any]) -> float:
    timeout_ms = int(payload.get("timeout_ms", 30_000))
    return max(0.05, min(60.0, (timeout_ms - 2_000) / 1_000))


def _bookmark_bar(data: dict[str, Any]) -> dict[str, Any]:
    roots = data.setdefault("roots", {})
    return roots.setdefault(
        "bookmark_bar",
        {
            "children": [],
            "date_added": "0",
            "date_last_used": "0",
            "date_modified": "0",
            "guid": "00000000-0000-4000-a000-" + "000000000002",
            "id": "1",
            "name": "Bookmarks bar",
            "type": "folder",
        },
    )


def _bookmark_create_folder(name: str) -> dict[str, Any]:
    def mutate() -> dict[str, Any]:
        data = _read_json(BOOKMARKS, {"version": 1, "roots": {}})
        bar = _bookmark_bar(data)
        matches = [
            child
            for child in bar.setdefault("children", [])
            if child.get("type") == "folder" and child.get("name") == name
        ]
        if not matches:
            matches = [
                {
                    "children": [],
                    "date_added": _chrome_time(),
                    "date_last_used": "0",
                    "date_modified": _chrome_time(),
                    "guid": "00000000-0000-4000-a000-"
                    + f"{int(_next_bookmark_id(data)):012d}",
                    "id": _next_bookmark_id(data),
                    "name": name,
                    "type": "folder",
                }
            ]
            bar["children"].append(matches[0])
            bar["date_modified"] = _chrome_time()
        data.pop("checksum", None)
        _write_json(BOOKMARKS, data)
        return matches[0]

    _with_profile_stopped(mutate)
    data = _read_json(BOOKMARKS)
    matches = [
        child
        for child in _bookmark_bar(data).get("children", [])
        if child.get("type") == "folder" and child.get("name") == name
    ]
    if len(matches) != 1:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "bookmark folder was not persisted uniquely",
            {"name": name, "count": len(matches)},
            422,
        )
    return matches[0]


def _bookmark_add(url: str, title: str) -> dict[str, Any]:
    def mutate() -> None:
        data = _read_json(BOOKMARKS, {"version": 1, "roots": {}})
        bar = _bookmark_bar(data)
        matches = [
            child
            for child in bar.setdefault("children", [])
            if child.get("type") == "url" and child.get("url") == url
        ]
        if not matches:
            node_id = _next_bookmark_id(data)
            bar["children"].append(
                {
                    "date_added": _chrome_time(),
                    "date_last_used": "0",
                    "guid": "00000000-0000-4000-a000-" + f"{int(node_id):012d}",
                    "id": node_id,
                    "name": title or url,
                    "type": "url",
                    "url": url,
                }
            )
            bar["date_modified"] = _chrome_time()
        data.pop("checksum", None)
        _write_json(BOOKMARKS, data)

    _with_profile_stopped(mutate)
    data = _read_json(BOOKMARKS)
    matches = [
        child
        for child in _bookmark_bar(data).get("children", [])
        if child.get("type") == "url" and child.get("url") == url
    ]
    if len(matches) != 1:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "bookmark URL was not persisted uniquely",
            {"url": url, "count": len(matches)},
            422,
        )
    return matches[0]


def _delete_sqlite(
    path: Path, statements: list[tuple[str, tuple[Any, ...]]]
) -> dict[str, Any]:
    if not path.exists():
        raise AdapterError(
            "PROFILE_FILE_NOT_FOUND",
            f"Chrome database not found: {path}",
            http_status=404,
        )

    def mutate() -> dict[str, Any]:
        connection = sqlite3.connect(path, timeout=10)
        try:
            before = connection.total_changes
            with connection:
                for sql, parameters in statements:
                    connection.execute(sql, parameters)
            return {"deleted_rows": connection.total_changes - before}
        except sqlite3.Error as exc:
            raise AdapterError(
                "SQLITE_ERROR", f"failed to update {path.name}", str(exc), 422
            ) from exc
        finally:
            connection.close()

    return _with_profile_stopped(mutate)


def _delete_cookies(domain: str) -> dict[str, Any]:
    normalized = domain.lower().lstrip(".")
    result = _delete_sqlite(
        COOKIES,
        [
            (
                "DELETE FROM cookies WHERE lower(ltrim(host_key, '.')) = ? OR lower(ltrim(host_key, '.')) LIKE ?",
                (normalized, "%." + normalized),
            )
        ],
    )
    connection = sqlite3.connect(COOKIES)
    try:
        remaining = connection.execute(
            "SELECT count(*) FROM cookies WHERE lower(ltrim(host_key, '.')) = ? OR lower(ltrim(host_key, '.')) LIKE ?",
            (normalized, "%." + normalized),
        ).fetchone()[0]
    finally:
        connection.close()
    if remaining:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "target cookies remain",
            {"domain": domain, "remaining": remaining},
            422,
        )
    return {**result, "domain": domain, "remaining": 0}


def _delete_history(contains: str) -> dict[str, Any]:
    pattern = f"%{contains.lower()}%"
    result = _delete_sqlite(
        HISTORY,
        [
            (
                "DELETE FROM visits WHERE url IN (SELECT id FROM urls WHERE lower(url) LIKE ?)",
                (pattern,),
            ),
            ("DELETE FROM urls WHERE lower(url) LIKE ?", (pattern,)),
        ],
    )
    connection = sqlite3.connect(HISTORY)
    try:
        remaining = connection.execute(
            "SELECT count(*) FROM urls WHERE lower(url) LIKE ?", (pattern,)
        ).fetchone()[0]
    finally:
        connection.close()
    if remaining:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "target history entries remain",
            {"contains": contains, "remaining": remaining},
            422,
        )
    return {**result, "contains": contains, "remaining": 0}


def _page_summary(cdp: CDPClient, tab: Any) -> dict[str, Any]:
    expression = """
(() => ({
  url: location.href,
  title: document.title,
  ready_state: document.readyState,
  body_text: (document.body?.innerText || '').slice(0, 20000)
}))()
"""
    return cdp.evaluate(tab, expression) or {}


def _snapshot(cdp: CDPClient, tab: Any) -> dict[str, Any]:
    expression = r"""
(() => {
  const roots = [document];
  for (let i = 0; i < roots.length; i++) {
    for (const node of roots[i].querySelectorAll ? roots[i].querySelectorAll('*') : []) {
      if (node.shadowRoot) roots.push(node.shadowRoot);
    }
  }
  const items = [];
  const seen = new Set();
  for (const root of roots) {
    for (const node of root.querySelectorAll ? root.querySelectorAll('a,button,input,textarea,select,[role],[contenteditable=true]') : []) {
      if (seen.has(node)) continue;
      seen.add(node);
      const rect = node.getBoundingClientRect();
      if (!rect.width || !rect.height) continue;
      items.push({
        tag: node.tagName,
        role: node.getAttribute('role'),
        text: String(node.innerText || node.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 500),
        label: node.getAttribute('aria-label') || node.title || '',
        name: node.name || '',
        type: node.type || '',
        value: node.value ?? null,
        checked: node.checked ?? null,
        disabled: !!node.disabled,
        href: node.href || '',
        id: node.id || ''
      });
      if (items.length >= 500) break;
    }
    if (items.length >= 500) break;
  }
  return {url:location.href,title:document.title,ready_state:document.readyState,interactive:items,body_text:(document.body?.innerText || '').slice(0,20000)};
})()
"""
    return cdp.evaluate(tab, expression) or {}


def _wait_for(cdp: CDPClient, tab: Any, params: dict[str, Any]) -> dict[str, Any]:
    timeout = min(float(params.get("timeout_ms", 20_000)) / 1000, 60)
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        summary = _page_summary(cdp, tab)
        passed = True
        if "url_contains" in params:
            passed = passed and params["url_contains"] in summary.get("url", "")
        if "url_matches" in params:
            passed = passed and bool(
                re.search(params["url_matches"], summary.get("url", ""))
            )
        if "text" in params:
            passed = passed and params["text"] in summary.get("body_text", "")
        if "ready_state" in params:
            passed = passed and summary.get("ready_state") == params["ready_state"]
        if "locator" in params:
            last = cdp.evaluate(tab, locator_expression(params["locator"], "inspect"))
            passed = passed and isinstance(last, dict) and last.get("ok")
        if passed:
            return {"matched": True, "page": summary, "locator": last}
        time.sleep(0.2)
    raise AdapterError(
        "TIMEOUT",
        "page condition was not met before timeout",
        {"condition": params, "last": last},
        504,
    )


def _resolve_unpacked_extension_path(path_value: str) -> tuple[Path, bool]:
    requested = Path(path_value).expanduser().resolve()
    if not requested.is_dir():
        raise AdapterError(
            "INVALID_REQUEST",
            "unpacked extension path must be an existing directory",
            {"path": str(requested)},
        )
    if (requested / "manifest.json").is_file():
        return requested, False

    candidates = sorted(
        child.resolve()
        for child in requested.iterdir()
        if child.is_dir() and (child / "manifest.json").is_file()
    )
    if len(candidates) == 1:
        return candidates[0], True
    raise AdapterError(
        "INVALID_REQUEST",
        (
            "unpacked extension path must contain manifest.json or be a parent "
            "directory with exactly one extension child"
        ),
        {
            "path": str(requested),
            "extension_candidates": [str(candidate) for candidate in candidates],
        },
    )


def _load_extension(path_value: str) -> dict[str, Any]:
    path, resolved_from_parent = _resolve_unpacked_extension_path(path_value)
    manifest = path / "manifest.json"
    manifest_data = _read_json(manifest)
    if not manifest_data.get("name") or not manifest_data.get("version"):
        raise AdapterError(
            "INVALID_REQUEST",
            "extension manifest lacks name or version",
            {"path": str(manifest)},
        )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(
        STATE_DIR / "launch-args.json",
        {"args": [f"--disable-extensions-except={path}", f"--load-extension={path}"]},
    )
    lifecycle = ChromeLifecycle()
    lifecycle.restart(30)
    deadline = time.monotonic() + 10
    observed: list[str] = []
    while time.monotonic() < deadline:
        data = _read_json(PREFERENCES)
        observed = [
            str(item.get("path", ""))
            for item in data.get("extensions", {}).get("settings", {}).values()
        ]
        if str(path) in observed:
            return {
                "path": str(path),
                "requested_path": str(Path(path_value).expanduser().resolve()),
                "resolved_from_parent": resolved_from_parent,
                "name": manifest_data["name"],
                "profile_paths": observed,
            }
        time.sleep(0.25)
    raise AdapterError(
        "VERIFICATION_FAILED",
        "unpacked extension did not persist in the Chrome Profile",
        {"path": str(path), "observed": observed},
        422,
    )


def _shortcut(cdp: CDPClient, tab: Any, name: str | None) -> dict[str, Any]:
    page = _page_summary(cdp, tab)
    shortcut_name = name or page.get("title") or "Chrome Shortcut"
    safe_filename = (
        re.sub(r"[^A-Za-z0-9._ -]+", "_", shortcut_name).strip() or "Chrome Shortcut"
    )
    path = HOME / "Desktop" / f"{safe_filename}.desktop"
    content = "\n".join(
        [
            "[Desktop Entry]",
            "Version=1.0",
            "Type=Application",
            f"Name={shortcut_name}",
            f"Exec=google-chrome --app={page['url']}",
            "Icon=google-chrome",
            "Terminal=false",
            "",
        ]
    )
    _atomic_write(path, content.encode("utf-8"))
    os.chmod(path, 0o755)
    persisted = path.read_text(encoding="utf-8")
    if f"Name={shortcut_name}\n" not in persisted or page["url"] not in persisted:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "desktop shortcut verification failed",
            {"path": str(path)},
            422,
        )
    return {"path": str(path), "name": shortcut_name, "url": page["url"]}


def _print_pdf(cdp: CDPClient, tab: Any, params: dict[str, Any]) -> dict[str, Any]:
    page = _page_summary(cdp, tab)
    title = page.get("title") or "page"
    path = Path(params["path"]).expanduser()
    if not path.is_absolute():
        raise AdapterError("INVALID_REQUEST", "PDF path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    content = cdp.print_pdf(
        tab,
        landscape=bool(params.get("landscape", False)),
        print_background=bool(params.get("print_background", True)),
    )
    _atomic_write(path, content)
    if not content.startswith(b"%PDF-") or len(content) < 1000:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "Chrome produced an invalid PDF",
            {"path": str(path), "size": len(content)},
            422,
        )
    return {
        "path": str(path),
        "size": len(content),
        "source_url": page.get("url"),
        "title": title,
    }


def _restore_last_closed(cdp: CDPClient) -> dict[str, Any]:
    before = cdp.list_tabs()
    completed_error = "xdotool is not installed"
    if shutil.which("xdotool"):
        command = [
            "xdotool",
            "search",
            "--class",
            "google-chrome",
            "windowactivate",
            "--sync",
            "key",
            "--clearmodifiers",
            "ctrl+shift+t",
        ]
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        completed_error = completed.stderr
    else:
        completed = None
    if completed is None or completed.returncode != 0:
        try:
            import pyautogui

            pyautogui.hotkey("ctrl", "shift", "t")
        except Exception as exc:
            raise AdapterError(
                "GUI_FALLBACK_FAILED",
                "failed to invoke Chrome restore-tab shortcut",
                {"xdotool": completed_error, "pyautogui": str(exc)},
                502,
            ) from exc
    deadline = time.monotonic() + 5
    before_ids = {item["target_id"] for item in before}
    while time.monotonic() < deadline:
        after = cdp.list_tabs()
        if len(after) > len(before):
            restored = next(
                (item for item in after if item["target_id"] not in before_ids),
                after[0],
            )
            return {"before": before, "after": after, "restored": restored}
        time.sleep(0.2)
    raise AdapterError(
        "VERIFICATION_FAILED",
        "Chrome did not restore a closed tab",
        {"before": before, "after": cdp.list_tabs()},
        422,
    )


def _observed(check: dict[str, Any], cdp: CDPClient | None) -> Any:
    check_type = check["type"]
    if check_type == "browser_ready":
        return ChromeLifecycle().health()
    if check_type == "preference":
        return _deep_get(_read_json(PREFERENCES), check["path"])
    if check_type == "bookmark":
        data = _read_json(BOOKMARKS)
        return list(_walk_bookmarks(_bookmark_bar(data)))
    if check_type == "cookies_absent":
        normalized = check["domain"].lower().lstrip(".")
        connection = sqlite3.connect(COOKIES)
        try:
            return connection.execute(
                "SELECT count(*) FROM cookies WHERE lower(ltrim(host_key, '.')) = ? OR lower(ltrim(host_key, '.')) LIKE ?",
                (normalized, "%." + normalized),
            ).fetchone()[0]
        finally:
            connection.close()
    if check_type == "history_absent":
        connection = sqlite3.connect(HISTORY)
        try:
            return connection.execute(
                "SELECT count(*) FROM urls WHERE lower(url) LIKE ?",
                (f"%{check['contains'].lower()}%",),
            ).fetchone()[0]
        finally:
            connection.close()
    if check_type == "extension_path":
        data = _read_json(PREFERENCES)
        return [
            str(item.get("path", ""))
            for item in data.get("extensions", {}).get("settings", {}).values()
        ]
    if check_type == "desktop_shortcut":
        path = Path(check["path"])
        return {
            "exists": path.is_file(),
            "content": path.read_text(encoding="utf-8") if path.is_file() else None,
        }
    if check_type == "pdf_file":
        path = Path(check["path"])
        return {
            "exists": path.is_file(),
            "size": path.stat().st_size if path.is_file() else 0,
            "header": path.read_bytes()[:5].decode("ascii", "replace")
            if path.is_file()
            else None,
        }
    if cdp is None:
        raise AdapterError(
            "CHROME_NOT_READY", "CDP verifier requires Chrome", http_status=503
        )
    if check_type == "tabs":
        return cdp.list_tabs()
    tab = cdp.select_tab(check.get("target") or {})
    if check_type == "active_url":
        return _page_summary(cdp, tab).get("url")
    if check_type == "page_state":
        if "locator" in check:
            return cdp.evaluate(tab, locator_expression(check["locator"], "inspect"))
        return _page_summary(cdp, tab)
    raise AdapterError("INVALID_REQUEST", "unsupported verifier", {"type": check_type})


def _check_passed(check: dict[str, Any], observed: Any) -> bool:
    check_type = check["type"]
    if check_type == "browser_ready":
        return bool(observed.get("chrome_ready") and observed.get("forward_ready"))
    if check_type == "active_url":
        return url_matches(observed or "", check["expected"], bool(check.get("regex")))
    if check_type == "tabs":
        urls = [item.get("url") for item in observed]
        expected = check.get("urls", [])
        return (
            urls == expected
            if check.get("ordered", True)
            else set(urls) == set(expected)
        )
    if check_type == "page_state":
        if not isinstance(observed, dict):
            return False
        if check.get("exists") is not None and bool(observed.get("ok")) != bool(
            check["exists"]
        ):
            return False
        for field in ("url", "title", "text", "value"):
            if field in check:
                actual = observed.get(field)
                if field == "text" and actual is None:
                    actual = observed.get("body_text")
                if check[field] not in str(actual or ""):
                    return False
        return True
    if check_type == "preference":
        return observed == check.get("expected")
    if check_type == "bookmark":
        return any(
            ("name" not in check or item.get("name") == check["name"])
            and ("url" not in check or item.get("url") == check["url"])
            for item in observed
        )
    if check_type in {"cookies_absent", "history_absent"}:
        return observed == 0
    if check_type == "extension_path":
        return str(Path(check["path"]).expanduser().resolve()) in observed
    if check_type == "desktop_shortcut":
        return bool(
            observed["exists"]
            and (
                "name" not in check or f"Name={check['name']}\n" in observed["content"]
            )
        )
    if check_type == "pdf_file":
        return bool(
            observed["exists"]
            and observed["size"] >= check.get("min_size", 1000)
            and observed["header"] == "%PDF-"
        )
    return False


def _verify(
    checks: list[dict[str, Any]], cdp: CDPClient | None
) -> dict[str, Any] | None:
    if not checks:
        return None
    results = []
    for check in checks:
        observed = _observed(check, cdp)
        passed = _check_passed(check, observed)
        results.append(
            {
                "type": check["type"],
                "passed": passed,
                "observed_state": observed,
                "expected_state": check,
                "details": None if passed else "state did not match",
            }
        )
    passed = all(item["passed"] for item in results)
    return {
        "passed": passed,
        "checks": results,
        "observed_state": [item["observed_state"] for item in results],
        "expected_state": checks,
        "error_code": None if passed else "VERIFICATION_FAILED",
        "details": None if passed else "one or more verifier checks failed",
    }


def execute(payload: dict[str, Any]) -> dict[str, Any]:
    action = payload["action"]
    params = payload.get("params") or {}
    target = payload.get("target") or {}
    cdp_timeout = _cdp_timeout_seconds(payload)
    lifecycle = ChromeLifecycle()
    cdp: CDPClient | None = None

    if action == "browser.ensure_running":
        result = lifecycle.prepare(25)
    elif action == "browser.restart":
        result = lifecycle.restart(30)
    elif action == "browser.inspect":
        result = lifecycle.health()
        if result["chrome_ready"]:
            cdp = CDPClient()
            result["tabs"] = cdp.list_tabs()
    else:
        cdp = CDPClient()
        if action == "tab.list":
            result = {"tabs": cdp.list_tabs()}
        elif action == "tab.open":
            tab = cdp.new_tab("about:blank")
            result = cdp.goto(
                tab,
                params["url"],
                cdp_timeout,
            )
            result["target_id"] = tab.id
        elif action == "tab.activate":
            tab = cdp.select_tab(params)
            cdp.activate(tab)
            result = _page_summary(cdp, tab)
            result["target_id"] = tab.id
        elif action == "tab.close":
            tab = cdp.select_tab(params)
            tab_info = next(
                item for item in cdp.list_tabs() if item["target_id"] == tab.id
            )
            info = {
                "target_id": tab.id,
                "url": tab_info["url"],
                "title": tab_info["title"],
            }
            cdp.close_tab(tab)
            result = {"closed": info, "tabs": cdp.list_tabs()}
        elif action == "tab.restore_last_closed":
            result = _restore_last_closed(cdp)
        elif action == "page.snapshot":
            result = _snapshot(cdp, cdp.select_tab(target))
        elif action == "page.goto":
            tab = cdp.select_tab(target)
            result = cdp.goto(tab, params["url"], cdp_timeout)
            result["target_id"] = tab.id
        elif action in {"page.click", "page.fill", "page.select"}:
            tab = cdp.select_tab(target)
            operation = action.split(".", 1)[1]
            value = params.get("value")
            result = ensure_locator_result(
                cdp.evaluate(
                    tab, locator_expression(params["locator"], operation, value)
                )
            )
            result["page"] = _page_summary(cdp, tab)
        elif action == "page.press":
            tab = cdp.select_tab(target)
            if "locator" in params:
                ensure_locator_result(
                    cdp.evaluate(tab, locator_expression(params["locator"], "inspect"))
                )
                cdp.evaluate(tab, locator_expression(params["locator"], "click"))
            cdp.press(tab, params["key"])
            result = _page_summary(cdp, tab)
        elif action == "page.wait_for":
            result = _wait_for(cdp, cdp.select_tab(target), params)
        elif action == "page.read":
            tab = cdp.select_tab(target)
            if "locator" in params:
                result = ensure_locator_result(
                    cdp.evaluate(tab, locator_expression(params["locator"], "inspect"))
                )
            else:
                result = _page_summary(cdp, tab)
        elif action == "bookmark.create_folder":
            result = _bookmark_create_folder(params["name"])
        elif action == "bookmark.add_current":
            tab = cdp.select_tab(target)
            page = _page_summary(cdp, tab)
            result = _bookmark_add(page["url"], page["title"])
        elif action == "settings.set":
            result = {"observed": _set_preference(params["settings"])}
        elif action == "privacy.delete_cookies":
            result = _delete_cookies(params["domain"])
        elif action == "privacy.delete_history":
            result = _delete_history(params["contains"])
        elif action == "extension.load_unpacked":
            result = _load_extension(params["path"])
        elif action == "shortcut.create_current":
            result = _shortcut(cdp, cdp.select_tab(target), params.get("name"))
        elif action == "page.print_pdf":
            result = _print_pdf(cdp, cdp.select_tab(target), params)
        else:
            raise AdapterError(
                "UNSUPPORTED_OPERATION", "unsupported Chrome action", {"action": action}
            )

    checks = payload.get("verify") or []
    if action == "settings.set" and not checks:
        checks = setting_verification_checks(params["settings"])
    verification = _verify(checks, cdp)
    return {"result": result, "verification": verification, "logs": []}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(execute(payload), ensure_ascii=True))
    except AdapterError as error:
        print(
            json.dumps(
                {
                    "error": {
                        **error_payload(error),
                        "http_status": error.http_status,
                    }
                },
                ensure_ascii=True,
            )
        )
        raise SystemExit(1)
    except Exception as exc:
        error = AdapterError(
            "INTERNAL_ERROR", "unexpected Chrome worker failure", repr(exc), 500
        )
        print(
            json.dumps(
                {
                    "error": {
                        **error_payload(error),
                        "http_status": error.http_status,
                    }
                }
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
