from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from .errors import AdapterError


_EMAIL_RE = re.compile(
    r"(?i)(?<![A-Z0-9.!#$%&'*+/=?^_`{|}~-])"
    r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+"
)

_ATTACHMENT_CHOOSER_SUBMIT_ATTEMPTS = 3
_ATTACHMENT_CONFIRM_ATTEMPT_SECONDS = 5.0


def _modules():
    try:
        import pyatspi
        import pyautogui
    except ImportError as exc:
        raise AdapterError(
            "UI_AUTOMATION_UNAVAILABLE",
            "AT-SPI or PyAutoGUI is unavailable",
            str(exc),
            503,
        ) from exc
    return pyatspi, pyautogui


def walk(node):
    yield node
    for index in range(getattr(node, "childCount", 0)):
        try:
            yield from walk(node.getChildAtIndex(index))
        except Exception:
            continue


def thunderbird_app():
    pyatspi, _ = _modules()
    for app in pyatspi.Registry.getDesktop(0):
        if app.name == "Thunderbird":
            return app
    return None


def wait_node(predicate: Callable[[Any], bool], timeout: float, description: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app = thunderbird_app()
        if app is not None:
            for node in walk(app):
                try:
                    if predicate(node):
                        return node
                except Exception:
                    continue
        time.sleep(0.25)
    raise AdapterError(
        "UI_STATE_NOT_FOUND", f"timed out waiting for {description}", http_status=422
    )


def node_text(node) -> str:
    try:
        return node.queryText().getText(0, -1)
    except Exception:
        return ""


def node_attributes(node) -> dict[str, str]:
    try:
        values = node.getAttributes()
    except Exception:
        return {}
    attributes: dict[str, str] = {}
    for value in values:
        key, separator, item = str(value).partition(":")
        if separator:
            attributes[key.casefold()] = item
    return attributes


def _class_names(node) -> set[str]:
    return {
        item.casefold()
        for item in node_attributes(node).get("class", "").split()
        if item
    }


def _email_addresses(value: str) -> list[str]:
    return [match.group(0).casefold() for match in _EMAIL_RE.finditer(value)]


def normalize_recipient_addresses(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        matches = _email_addresses(value)
        if len(matches) != 1 or matches[0] != value.casefold():
            raise AdapterError(
                "INVALID_RECIPIENT",
                "each recipient must be one plain email address",
                {"recipient": raw},
                422,
            )
        address = matches[0]
        if address not in seen:
            normalized.append(address)
            seen.add(address)
    return normalized


def recipient_pill_nodes(frame) -> list[Any]:
    return [node for node in walk(frame) if "address-pill" in _class_names(node)]


def compose_recipient_addresses(frame) -> list[str]:
    addresses: list[str] = []
    seen: set[str] = set()
    pill_nodes = recipient_pill_nodes(frame)
    candidates: list[Any] = []
    for pill in pill_nodes:
        candidates.extend(walk(pill))
    if not candidates:
        candidates = [
            node for node in walk(frame) if "pill-label" in _class_names(node)
        ]
    for node in candidates:
        values = [str(getattr(node, "name", "") or ""), node_text(node)]
        for address in _email_addresses(" ".join(values)):
            if address not in seen:
                addresses.append(address)
                seen.add(address)
    return addresses


def compose_recipient_entry(frame):
    candidates = []
    for node in walk(frame):
        attributes = node_attributes(node)
        role = str(node.getRoleName()).casefold()
        classes = _class_names(node)
        score = 0
        if attributes.get("id", "").casefold() == "toaddrinput":
            score += 100
        if "address-input" in classes:
            score += 50
        if str(getattr(node, "name", "")).strip().casefold() == "to":
            score += 20
        if role in {"entry", "text", "password text"}:
            score += 5
        if score >= 50:
            candidates.append((score, node))
    if not candidates:
        raise AdapterError(
            "UI_STATE_NOT_FOUND",
            "Thunderbird To recipient input was not found in the compose window",
            http_status=422,
        )
    return max(candidates, key=lambda item: item[0])[1]


def compose_frame(subject: str | None, timeout: float):
    def matches(node) -> bool:
        if node.getRoleName() != "frame":
            return False
        title = str(node.name or "")
        if not title.startswith("Write:") or "Thunderbird" not in title:
            return False
        return subject is None or title == f"Write: {subject} - Thunderbird"

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app = thunderbird_app()
        candidates = []
        if app is not None:
            for node in walk(app):
                try:
                    if matches(node):
                        candidates.append(node)
                except Exception:
                    continue
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise AdapterError(
                "AMBIGUOUS_COMPOSE_WINDOW",
                "multiple Thunderbird compose windows match the requested subject",
                {
                    "subject": subject,
                    "titles": [str(node.name or "") for node in candidates],
                },
                409,
            )
        time.sleep(0.25)
    raise AdapterError(
        "UI_STATE_NOT_FOUND",
        "timed out waiting for Thunderbird compose window",
        {"subject": subject},
        422,
    )


def _wait_for_recipients(
    frame,
    predicate: Callable[[list[str]], bool],
    timeout: float,
) -> list[str]:
    deadline = time.monotonic() + timeout
    observed: list[str] = []
    while time.monotonic() < deadline:
        observed = compose_recipient_addresses(frame)
        if predicate(observed):
            return observed
        time.sleep(0.15)
    return observed


def click_node(node) -> None:
    pyatspi, pyautogui = _modules()
    component = node.queryComponent()
    x, y = component.getPosition(pyatspi.XY_SCREEN)
    width, height = component.getSize()
    pyautogui.click(x + max(1, width // 2), y + max(1, height // 2))


def activate_thunderbird() -> None:
    subprocess.run(
        ["wmctrl", "-xa", "Mail.thunderbird"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.35)


def _remaining_timeout(deadline: float, description: str) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AdapterError(
            "UI_STATE_NOT_FOUND",
            f"timed out waiting for {description}",
            http_status=422,
        )
    return remaining


def _window_title_containing(value: str) -> tuple[str | None, str]:
    try:
        completed = subprocess.run(
            ["wmctrl", "-l"],
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)
    output = completed.stdout
    for line in output.splitlines():
        fields = line.split(None, 3)
        title = fields[3] if len(fields) == 4 else ""
        if value.casefold() in title.casefold():
            return title, output
    return None, output


def wait_window_title(value: str, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    last_observation = ""
    while time.monotonic() < deadline:
        title, last_observation = _window_title_containing(value)
        if title is not None:
            return title
        time.sleep(0.2)
    raise AdapterError(
        "UI_STATE_NOT_FOUND",
        f"timed out waiting for window title containing {value}",
        {"wmctrl": last_observation},
        422,
    )


def activate_window(title: str) -> None:
    subprocess.run(
        ["wmctrl", "-a", title],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    time.sleep(0.2)


def _submit_attachment_path(pyautogui, path: Path) -> None:
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(str(path), interval=0.005)
    time.sleep(0.1)
    pyautogui.press("enter")


def prefill_account_setup(
    full_name: str, email: str, password: str, timeout: float
) -> dict[str, Any]:
    _, pyautogui = _modules()
    fields = [
        ("Your full name", "entry", full_name),
        ("Email address", "entry", email),
        ("Password", "password text", password),
    ]
    observed = {}
    for name, role, value in fields:
        observed[name] = ""
        for _attempt in range(3):
            activate_thunderbird()
            node = wait_node(
                lambda item, n=name, r=role: item.name == n and item.getRoleName() == r,
                timeout,
                name,
            )
            try:
                node.queryComponent().grabFocus()
            except Exception:
                pass
            click_node(node)
            pyautogui.hotkey("ctrl", "a")
            pyautogui.write(value, interval=0.01)
            time.sleep(0.4)
            refreshed = wait_node(
                lambda item, n=name, r=role: item.name == n and item.getRoleName() == r,
                timeout,
                name,
            )
            observed[name] = node_text(refreshed)
            if observed[name] == value or (role == "password text" and observed[name]):
                break
    if observed.get("Email address") != email:
        raise AdapterError(
            "VERIFICATION_FAILED", "account setup email was not entered", observed, 422
        )
    return {
        "full_name": full_name,
        "email": email,
        "password_field_present": True,
        "observed": observed,
    }


def compose_attachment(
    subject: str, attachment_path: str, timeout: float
) -> dict[str, Any]:
    _, pyautogui = _modules()
    path = Path(attachment_path).expanduser().resolve()
    if not path.is_file():
        raise AdapterError(
            "PATH_NOT_FOUND", f"attachment does not exist: {path}", http_status=404
        )
    deadline = time.monotonic() + timeout
    title = f"Write: {subject} - Thunderbird"
    wait_node(
        lambda item: item.getRoleName() == "frame" and item.name == title,
        _remaining_timeout(deadline, title),
        title,
    )
    activate_window(title)
    chooser_title, _observation = _window_title_containing("Attach File")
    if chooser_title is None:
        pyautogui.hotkey("ctrl", "shift", "a")
        chooser_title = wait_window_title(
            "Attach File",
            _remaining_timeout(deadline, "Thunderbird attachment file chooser"),
        )
    expected = " ".join(path.stem.split("."))

    def attachment_predicate(item) -> bool:
        return item.getRoleName() == "list item" and item.name.lower().startswith(
            expected.lower()
        )

    chooser_observation = ""
    node = None
    for attempt in range(1, _ATTACHMENT_CHOOSER_SUBMIT_ATTEMPTS + 1):
        activate_window(chooser_title)
        _submit_attachment_path(pyautogui, path)
        confirm_timeout = min(
            _ATTACHMENT_CONFIRM_ATTEMPT_SECONDS,
            _remaining_timeout(deadline, f"attachment {path.name}"),
        )
        try:
            node = wait_node(
                attachment_predicate,
                confirm_timeout,
                f"attachment {path.name}",
            )
            break
        except AdapterError as exc:
            if exc.code != "UI_STATE_NOT_FOUND":
                raise
        chooser_title, chooser_observation = _window_title_containing("Attach File")
        if chooser_title is None:
            node = wait_node(
                attachment_predicate,
                _remaining_timeout(deadline, f"attachment {path.name}"),
                f"attachment {path.name}",
            )
            break
        if attempt == _ATTACHMENT_CHOOSER_SUBMIT_ATTEMPTS:
            raise AdapterError(
                "UI_STATE_NOT_FOUND",
                f"attachment {path.name} did not appear after repeated file chooser submissions",
                {
                    "attempts": attempt,
                    "chooser_title": chooser_title,
                    "wmctrl": chooser_observation,
                },
                422,
            )
    if node is None:
        raise AdapterError(
            "UI_STATE_NOT_FOUND",
            f"timed out waiting for attachment {path.name}",
            http_status=422,
        )
    return {
        "subject": subject,
        "attachment": str(path),
        "attachment_node": node.name,
        "compose_open": True,
    }


def compose_set_recipients(
    recipients: list[str],
    mode: str,
    subject: str | None,
    timeout: float,
) -> dict[str, Any]:
    _, pyautogui = _modules()
    requested = normalize_recipient_addresses(recipients)
    frame = compose_frame(subject, timeout)
    title = str(frame.name or "")
    subprocess.run(
        ["wmctrl", "-a", title],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=5,
    )
    time.sleep(0.25)
    before = compose_recipient_addresses(frame)

    if mode == "replace":
        entry = compose_recipient_entry(frame)
        try:
            entry.queryComponent().grabFocus()
        except Exception:
            pass
        click_node(entry)
        for _attempt in range(max(2, len(before) * 3)):
            previous = compose_recipient_addresses(frame)
            if not previous:
                break
            pyautogui.press("backspace")
            _wait_for_recipients(
                frame,
                lambda observed, count=len(previous): len(observed) < count,
                min(1.0, timeout),
            )
        remaining = compose_recipient_addresses(frame)
        if remaining:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "Thunderbird did not clear all existing recipient pills",
                {"observed_recipients": remaining},
                422,
            )

    current = compose_recipient_addresses(frame)
    current_set = set(current)
    added: list[str] = []
    for address in requested:
        if address in current_set:
            continue
        entry = compose_recipient_entry(frame)
        try:
            entry.queryComponent().grabFocus()
        except Exception:
            pass
        click_node(entry)
        pyautogui.write(address, interval=0.01)
        pyautogui.press("enter")
        observed = _wait_for_recipients(
            frame,
            lambda values, target=address: target in values,
            min(3.0, timeout),
        )
        if address not in observed:
            raise AdapterError(
                "VERIFICATION_FAILED",
                "Thunderbird did not create the requested recipient pill",
                {"recipient": address, "observed_recipients": observed},
                422,
            )
        current_set = set(observed)
        added.append(address)

    observed = compose_recipient_addresses(frame)
    expected = (
        requested if mode == "replace" else list(dict.fromkeys([*before, *requested]))
    )
    passed = set(observed) == set(expected) and len(observed) == len(expected)
    if not passed:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "Thunderbird compose recipients do not match the requested state",
            {
                "mode": mode,
                "expected_recipients": expected,
                "observed_recipients": observed,
            },
            422,
        )
    return {
        "compose_title": title,
        "mode": mode,
        "recipients_before": before,
        "requested_recipients": requested,
        "added_recipients": added,
        "observed_recipients": observed,
        "verified": True,
        "compose_open": True,
    }


def accessibility_state(kind: str, value: str) -> dict[str, Any]:
    app = thunderbird_app()
    if app is None:
        return {"matched": False, "kind": kind, "value": value}
    matches = []
    for node in walk(app):
        role = node.getRoleName()
        text = node_text(node)
        if kind == "text" and value in text:
            matches.append({"role": role, "name": node.name, "text": text})
        elif kind == "name" and value.lower() in str(node.name).lower():
            matches.append({"role": role, "name": node.name, "text": text})
        elif kind == "page_tab" and role == "page tab" and node.name == value:
            matches.append({"role": role, "name": node.name})
        elif (
            kind == "attachment"
            and role == "list item"
            and node.name.lower().startswith(value.lower())
        ):
            matches.append({"role": role, "name": node.name})
        elif (
            kind == "recipient"
            and value.casefold()
            in _email_addresses(f"{getattr(node, 'name', '')} {text}")
            and (
                "pill-label" in _class_names(node)
                or "address-pill" in _class_names(node)
            )
        ):
            matches.append({"role": role, "name": node.name, "text": text})
    return {
        "matched": bool(matches),
        "kind": kind,
        "value": value,
        "matches": matches[:10],
    }
