"""Require observation before mutating a spreadsheet opened by the model."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

from .adapter_results import has_passed_verification
from .completion_policy import (
    action_is_read_only,
    canonical_action_request,
    effective_canonical_action,
    inspection_identity_url,
    local_document_paths_match,
)


OPEN_ACTION = "desktop.open_path"
INSPECT_ACTION = "spreadsheet.inspect_current"
_CANONICAL_INSPECT = ("libreoffice_calc", "workbook.inspect")
_INSPECTION_ACTIONS = frozenset({"workbook.inspect", "workbook.read_file"})
_SPREADSHEET_SUFFIXES = frozenset(
    {".csv", ".fods", ".ods", ".ots", ".tsv", ".xls", ".xlsb", ".xlsm", ".xlsx"}
)
_GUI_OPEN_VERB_RE = re.compile(
    r"(?i)\b(?:open(?:ed|ing|s)?|double(?:-|\s)?click(?:ed|ing|s)?)\b"
)
_GUI_SPREADSHEET_SUFFIX_RE = re.compile(
    r"(?i)\.(?:csv|fods|ods|ots|tsv|xls|xlsb|xlsm|xlsx)"
    r"(?=$|[\s\"'\)\],;:!?]|\.(?![A-Za-z0-9]))"
)
_NEGATED_GUI_OPEN_RE = re.compile(
    r"(?i)\b(?:avoid|do\s+not|don't|never)\b.{0,48}"
    r"\b(?:open(?:ed|ing|s)?|double(?:-|\s)?click(?:ed|ing|s)?)\b"
)
_SAVE_AS_RE = re.compile(
    r"(?is)\bsav(?:e|ed|es|ing)\b.{0,64}\b(?:as|a\s+(?:new\s+)?copy)\b"
)
_SAVE_TO_RE = re.compile(
    r"(?is)\bsav(?:e|ed|es|ing)\b.{0,48}\b(?:to|into|under)\b"
    r"(?P<target>.{0,96})"
)
_FILE_TARGET_RE = re.compile(
    r"(?is)[/~][^\s,;)]*|"
    r"\.(?:csv|fods|ods|ots|tsv|xls|xlsb|xlsm|xlsx|pdf)\b|"
    r"\b(?:desktop|documents?|downloads?|folder|directory)\b"
)
_EXPORT_FILE_RE = re.compile(
    r"(?is)\b(?:export|convert)\b.{0,96}\b(?:as|to|into)\b.{0,64}"
    r"(?:\.(?:csv|fods|ods|ots|tsv|xls|xlsb|xlsm|xlsx|pdf)\b|"
    r"\b(?:csv|excel|ods|pdf|spreadsheet|workbook|file)\b)"
)
_COPY_FILE_RE = re.compile(
    r"(?is)\b(?:copy|duplicate)\b\s+"
    r"(?:(?:a|the|this|current|existing)\s+)?"
    r"(?:file|spreadsheet|workbook)(?:\s+file)?\s+"
    r"(?:as|to|into|under|named)\b|"
    r"\b(?:make|create)\b.{0,32}\ba\s+(?:new\s+)?copy\b"
)
_GUI_DESTINATION_MARKER_RE = re.compile(
    r"(?i)\b(?:save|saved|saving|export|exported|convert|converted|"
    r"copy|copied|duplicate|duplicated|move|moved|moving|rename|renamed|renaming)\b"
)
_GUI_NON_OPEN_VERB_RE = re.compile(
    r"(?i)\b(?:locate|find|search|browse|select|selecting|choose|choosing|"
    r"click|clicking|view|viewing|edit|editing|update|updating|inspect|"
    r"inspecting|read|reading|save|saving|export|exporting|convert|converting|"
    r"duplicate(?!\s*[,;:]?\s+of\b)|duplicating|move|moving|rename|renaming)\b"
)
_GUI_NON_OPEN_COPY_RE = re.compile(r"(?i)\b(?:copy|copying)\b(?!\s+of\b)")
_GUI_NON_OPEN_PARTICIPLE_RE = re.compile(
    r"(?i)(?:\b(?:and|then|to|by|while)\b|[,;])\s*"
    r"(?:located|found|searched|browsed|selected|chosen|clicked|viewed|"
    r"edited|updated|inspected|read|saved|exported|converted|copied|"
    r"duplicated|moved|renamed)\b"
)
_GUI_LEADING_FILLER_RE = re.compile(
    r"(?i)^(?:(?:copy|duplicate)\s*[,;:]?\s+of\s+|"
    r"(?:the|a|an|existing|current|new|on|in|from|at|by|for|"
    r"with|name|named|called|titled|labeled|labelled|highlighted|"
    r"selected|chosen|clicked|viewed|edited|updated|inspected|"
    r"saved|exported|converted|copied|duplicated|moved|renamed|"
    r"icon|item)\s+|"
    r"(?:file|workbook|spreadsheet|document)"
    r"(?:\s+(?:named|called|titled|labeled|labelled))?"
    r"(?:\s+|\s*[,;:()=-]\s*))"
)

_OPEN_ACTIONS = frozenset({OPEN_ACTION, "spreadsheet.open_in_terminal"})
_EXPLICIT_GUI_PATH_RE = re.compile(
    r"(?P<quoted>[\"'](?:file://|~/|/)[^\"']+[\"'])|"
    r"(?P<plain>(?:file://|~/|/(?:home|root|tmp|mnt|var|opt|Users)/)[^\s,;!?)]*)",
    re.IGNORECASE,
)


def _contains_explicit_failure(value: Any, *, depth: int = 0) -> bool:
    if depth > 8 or not isinstance(value, dict):
        return False
    if value.get("status") in {"error", "failed"}:
        return True
    verification = value.get("verification")
    if isinstance(verification, dict) and verification.get("passed") is False:
        return True
    return any(
        _contains_explicit_failure(value.get(key), depth=depth + 1)
        for key in (
            "context_hint",
            "downstream_context",
            "adapter_response",
            "response",
            "result",
        )
    )


def _spreadsheet_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    return PurePosixPath(value.strip()).suffix.casefold() in _SPREADSHEET_SUFFIXES


def _gui_request_intent(event: Any) -> str | None:
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict) or proposed.get("kind") != "gui":
        return None
    request_arguments = proposed.get("gui_request_arguments")
    request_arguments = request_arguments if isinstance(request_arguments, dict) else {}
    is_gui_request = bool(
        proposed.get("tool") == "gui_request"
        or proposed.get("action") == "gui_request"
        or request_arguments.get("action") == "gui_request"
    )
    if not is_gui_request:
        return None
    intent = request_arguments.get("intent")
    if not isinstance(intent, str):
        arguments = proposed.get("arguments")
        intent = arguments.get("intent") if isinstance(arguments, dict) else None
    return intent if isinstance(intent, str) else None


def _gui_open_target_parts(
    intent: str,
) -> tuple[re.Match[str], re.Match[str], str] | None:
    if _NEGATED_GUI_OPEN_RE.search(intent):
        return None
    suffix_matches = list(_GUI_SPREADSHEET_SUFFIX_RE.finditer(intent))
    if not suffix_matches:
        return None
    open_matches = list(_GUI_OPEN_VERB_RE.finditer(intent))
    if not open_matches:
        return None
    # Once an output operation is followed by another spreadsheet open, the
    # instruction contains two possible source leases.  Do not bind the first
    # suffix silently; require the model to issue separate, observable GUI
    # requests instead.
    if len(suffix_matches) > 1:
        destination = _GUI_DESTINATION_MARKER_RE.search(intent, suffix_matches[0].end())
        if destination is not None:
            later_open = next(
                (
                    match
                    for match in open_matches
                    if match.start() > destination.end()
                    and any(suffix.start() > match.start() for suffix in suffix_matches)
                ),
                None,
            )
            if later_open is not None:
                return None
    # Keep only suffixes that belong to an explicit open clause.  A later
    # suffix in a save/export/copy clause is an output destination, not a new
    # workbook to inspect.  Any other second source remains ambiguous and is
    # rejected rather than binding to an arbitrary file.
    candidates: list[tuple[re.Match[str], re.Match[str]]] = []
    for index, suffix in enumerate(suffix_matches):
        preceding_opens = [
            match for match in open_matches if match.start() < suffix.start()
        ]
        if not preceding_opens:
            continue
        open_match = preceding_opens[-1]
        previous_end = suffix_matches[index - 1].end() if index else open_match.end()
        between = intent[previous_end : suffix.start()]
        if index and _GUI_DESTINATION_MARKER_RE.search(between):
            continue
        candidates.append((suffix, open_match))
    if len(candidates) != 1:
        return None
    suffix_match, open_match = candidates[0]
    prefix = intent[open_match.end() : suffix_match.start()]
    # A file-manager/search clause is not proof that the spreadsheet itself was
    # opened. Requiring the filename to be in the same simple open clause also
    # avoids hijacking compound GUI workflows.
    if (
        _GUI_NON_OPEN_VERB_RE.search(prefix)
        or _GUI_NON_OPEN_PARTICIPLE_RE.search(prefix)
        or _GUI_NON_OPEN_COPY_RE.search(prefix)
    ):
        return None
    return suffix_match, open_match, prefix


def _gui_open_filename(intent: str) -> str | None:
    target_parts = _gui_open_target_parts(intent)
    if target_parts is None:
        return None
    suffix_match, _open_match, prefix = target_parts
    if "\\" in prefix:
        # The active guest uses POSIX paths.  Do not reinterpret a
        # Windows-style path as a basename that could acquire a lease without
        # an identity-bearing local path.
        return None
    filename = prefix.strip(" \t\"'.,:;()[]")
    # Keep only the final path/name component.  This handles quoted names,
    # URL-encoded spaces, and phrases such as "the workbook named X" without
    # treating the surrounding application prose as part of the filename.
    # Keep POSIX path semantics.  A Windows-style backslash path is not a
    # verified local identity in this Linux guest and must fail closed.
    filename = filename.rsplit("/", 1)[-1].strip(" \t\"'")
    filename = filename.rsplit(":", 1)[-1].strip(" \t\"'")
    # Filler can be stacked ("on the existing workbook named X").  Strip one
    # leading phrase per pass so ordering does not leak words into the basename.
    for _ in range(8):
        previous = filename
        filename = filename.strip(" \t\"'.,:;()[]")
        filename = _GUI_LEADING_FILLER_RE.sub("", filename, count=1)
        if filename == previous:
            break
    filename = unquote(filename).strip(" \t\"'")
    if not filename or re.search(
        r"(?i)\b(?:files?|file\s+manager|folder|directory|app)\b", filename
    ):
        return None
    suffix = suffix_match.group(0)
    return PurePosixPath(filename + suffix).name or None


def _gui_open_clause(intent: str) -> str | None:
    """Return only the source-open clause, excluding later output operations."""
    target_parts = _gui_open_target_parts(intent)
    if target_parts is None:
        return None
    suffix_match, open_match, _prefix = target_parts
    clause_end = len(intent)
    destination = _GUI_DESTINATION_MARKER_RE.search(intent, suffix_match.end())
    if destination is not None:
        clause_end = destination.start()
    return intent[open_match.start() : clause_end]


def _gui_open_location_hint(intent: str) -> str | None:
    """Return an explicit standard-directory hint from a GUI open request."""
    clause = _gui_open_clause(intent)
    if clause is None:
        return None
    if re.search(
        r"(?i)(?:file://|~/|/(?:home|root|tmp|mnt|var|opt|Users)/)[^\s\"']+",
        clause,
    ):
        return "explicit"
    # ``document`` is a generic file noun; only plural Documents denotes the
    # standard directory without an additional task-specific assumption.
    location = re.search(r"(?i)\b(desktop|documents|downloads?)\b", clause)
    if location is not None:
        name = location.group(1).casefold()
        if name.startswith("document"):
            return "documents"
        if name.startswith("download"):
            return "downloads"
        return "desktop"
    return None


def _gui_explicit_path(intent: str, filename: str | None) -> str | None:
    """Return the instruction's explicit local path for the named workbook."""
    clause = _gui_open_clause(intent)
    if not filename or clause is None:
        return None
    for match in _EXPLICIT_GUI_PATH_RE.finditer(clause):
        raw = match.group("quoted") or match.group("plain")
        if not isinstance(raw, str):
            continue
        raw = raw.strip(" \t\"'.,:;()[]")
        if _document_basename(raw) == filename:
            return raw
    return None


def _document_basename(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        raw = unquote(parsed.path)
    return PurePosixPath(unquote(raw)).name or None


def _local_identity_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            return None
        raw = unquote(parsed.path)
    else:
        raw = unquote(raw)
    if raw.startswith(("/", "~/")):
        return str(PurePosixPath(raw))
    return None


def _instruction_requests_destination_change(instruction: str) -> bool:
    if _SAVE_AS_RE.search(instruction):
        return True
    if _EXPORT_FILE_RE.search(instruction):
        return True
    for match in _SAVE_TO_RE.finditer(instruction):
        if _FILE_TARGET_RE.search(match.group("target")):
            return True
    for match in _COPY_FILE_RE.finditer(instruction):
        if _FILE_TARGET_RE.search(match.group(0)):
            return True
        target = instruction[match.end() : match.end() + 96]
        if _FILE_TARGET_RE.search(target):
            return True
        if re.search(r"(?i)\b(?:new|another)\s+(?:file|workbook|copy)\b", target):
            return True
    return False


def _is_spreadsheet_open_event(event: Any, default_domain: str) -> bool:
    if (
        not getattr(event, "executed", False)
        or getattr(event, "error", None) is not None
    ):
        return False
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict):
        return False
    if proposed.get("kind") == "adapter":
        domain, action, arguments = effective_canonical_action(event, default_domain)
        return bool(
            domain in {"multi_apps", "os"}
            and action in _OPEN_ACTIONS
            and _spreadsheet_path(arguments.get("path"))
            and has_passed_verification(getattr(event, "result", None))
            and not _contains_explicit_failure(getattr(event, "result", None))
        )
    intent = _gui_request_intent(event)
    result = getattr(event, "result", None)
    if not isinstance(result, dict) or _contains_explicit_failure(result):
        return False
    return bool(intent and _gui_open_filename(intent))


def _is_successful_inspection(event: Any, default_domain: str) -> bool:
    domain, action, _arguments = effective_canonical_action(event, default_domain)
    return bool(
        getattr(event, "executed", False)
        and getattr(event, "error", None) is None
        and has_passed_verification(getattr(event, "result", None))
        and not _contains_explicit_failure(getattr(event, "result", None))
        and inspection_identity_url(event) is not None
        and domain == _CANONICAL_INSPECT[0]
        and action in _INSPECTION_ACTIONS
    )


def _inspection_matches_open(inspected: Any, opened: Any, default_domain: str) -> bool:
    inspected_identity = inspection_identity_url(inspected)
    if inspected_identity is None:
        return False
    proposed = getattr(opened, "proposed", None)
    if not isinstance(proposed, dict):
        return False
    if proposed.get("kind") == "adapter":
        _domain, _action, arguments = effective_canonical_action(opened, default_domain)
        return local_document_paths_match(arguments.get("path"), inspected_identity)
    intent = _gui_request_intent(opened)
    opened_name = _gui_open_filename(intent) if intent is not None else None
    inspected_name = _document_basename(inspected_identity)
    if not opened_name or not inspected_name or opened_name != inspected_name:
        return False
    location_hint = _gui_open_location_hint(intent or "")
    if location_hint == "explicit":
        requested_path = _gui_explicit_path(intent or "", opened_name)
        return requested_path is not None and local_document_paths_match(
            requested_path, inspected_identity
        )
    if location_hint in {"desktop", "documents", "downloads"}:
        expected_path = f"~/{location_hint.title()}/{opened_name}"
        return local_document_paths_match(expected_path, inspected_identity)
    # A filename-only GUI request does not constrain the directory.  The
    # verified current-workbook probe establishes the active file with that
    # exact name; an arbitrary same-named file read does not establish focus.
    return effective_canonical_action(inspected, default_domain)[:2] == _CANONICAL_INSPECT


def _latest_spreadsheet_open(
    state: Any, *, before_step: int | None = None
) -> Any | None:
    if str(getattr(state, "domain", "")) != "multi_apps":
        return None
    domain = str(getattr(state, "domain", ""))
    opens = [
        event
        for event in getattr(state, "events", ())
        if (before_step is None or getattr(event, "step", 0) < before_step)
        if _is_spreadsheet_open_event(event, domain)
    ]
    if not opens:
        return None
    return max(opens, key=lambda event: getattr(event, "step", 0))


def _inspection_actions_for_open(opened: Any) -> frozenset[str]:
    intent = _gui_request_intent(opened)
    if intent is not None and _gui_open_location_hint(intent) is None:
        # Background file reads do not change the active workbook identity.
        return frozenset({_CANONICAL_INSPECT[1]})
    return _INSPECTION_ACTIONS


def _latest_successful_inspection_after(
    state: Any, opened: Any, *, before_step: int | None = None
) -> Any | None:
    domain = str(getattr(state, "domain", ""))
    step = getattr(opened, "step", 0)
    inspection_actions = _inspection_actions_for_open(opened)
    inspections = [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "step", 0) > step
        and (before_step is None or getattr(event, "step", 0) < before_step)
        and effective_canonical_action(event, domain)[0] == _CANONICAL_INSPECT[0]
        and effective_canonical_action(event, domain)[1] in inspection_actions
    ]
    latest = max(inspections, key=lambda event: getattr(event, "step", 0), default=None)
    if latest is None:
        return None
    if not _is_successful_inspection(latest, domain):
        return None
    return latest if _inspection_matches_open(latest, opened, domain) else None


def _latest_unobserved_open(state: Any) -> Any | None:
    latest = _latest_spreadsheet_open(state)
    if latest is None:
        return None
    domain = str(getattr(state, "domain", ""))
    inspection_actions = _inspection_actions_for_open(latest)
    inspections = [
        event
        for event in getattr(state, "events", ())
        if getattr(event, "step", 0) > getattr(latest, "step", 0)
        and effective_canonical_action(event, domain)[0] == _CANONICAL_INSPECT[0]
        and effective_canonical_action(event, domain)[1] in inspection_actions
    ]
    latest_inspection = max(
        inspections, key=lambda event: getattr(event, "step", 0), default=None
    )
    if (
        latest_inspection is not None
        and _is_successful_inspection(latest_inspection, domain)
        and _inspection_matches_open(latest_inspection, latest, domain)
    ):
        return None
    return latest


def _has_inspection_attempt_after(state: Any, step: int) -> bool:
    domain = str(getattr(state, "domain", ""))
    return any(
        getattr(event, "step", 0) > step
        and effective_canonical_action(event, domain)[0] == _CANONICAL_INSPECT[0]
        and effective_canonical_action(event, domain)[1] in _INSPECTION_ACTIONS
        for event in getattr(state, "events", ())
    )


def gui_request_contract_errors(state: Any, intent: str | None = None) -> list[str]:
    """Prevent GUI fallback from bypassing an unresolved workbook observation."""
    if _latest_unobserved_open(state) is None:
        return []
    # A new, explicitly named spreadsheet open is a legitimate recovery route;
    # it becomes the latest open lease and must itself be inspected.
    if isinstance(intent, str) and _gui_open_filename(intent):
        return []
    return [
        "a spreadsheet was opened but its verified current-workbook inspection "
        "is missing or failed; use tools_search to find libreoffice_calc workbook.inspect "
        "and inspect the current workbook. GUI actions cannot bypass that observation gate"
    ]


def pending_actions(state: Any) -> list[str] | None:
    """Expose one unambiguous current-workbook probe before the first attempt."""
    opened = _latest_unobserved_open(state)
    if opened is None:
        return None
    # Once the parameterless probe itself has reached the Runner's bounded
    # repeated-request block, keeping an exclusive one-tool surface would make
    # recovery impossible.  Fall through to the normal bounded recovery
    # surface (tools_search/fail_task and any safe alternatives) in that case.
    for block in getattr(state, "active_request_blocks", lambda: {})().values():
        if (
            block.get("canonical_domain") == _CANONICAL_INSPECT[0]
            and block.get("canonical_action") == _CANONICAL_INSPECT[1]
        ):
            return None
    return [INSPECT_ACTION]


def inspection_retry_required(
    state: Any, action: str, arguments: dict[str, Any] | None = None
) -> bool:
    """Allow a fresh inspect after a failed or wrong-identity workbook probe."""
    domain, canonical, _selected = canonical_action_request(
        str(getattr(state, "domain", "")), action, arguments or {}
    )
    if (domain, canonical) != _CANONICAL_INSPECT:
        return False
    return _latest_unobserved_open(state) is not None


def _is_calc_mutation_or_save(
    default_domain: str, action: str, arguments: dict[str, Any]
) -> bool:
    domain, canonical, _selected = canonical_action_request(
        default_domain, action, arguments
    )
    return domain == "libreoffice_calc" and not action_is_read_only(canonical)


def _save_target(
    default_domain: str, action: str, arguments: dict[str, Any]
) -> tuple[bool, str | None]:
    domain, canonical, selected = canonical_action_request(
        default_domain, action, arguments
    )
    if domain != "libreoffice_calc" or canonical != "workbook.save":
        return False, None
    target = selected.get("url", selected.get("output_path"))
    return True, target if isinstance(target, str) and target.strip() else None


def _resolved_save_target(
    domain: str, action: str, arguments: dict[str, Any]
) -> tuple[bool, str | None]:
    if domain != "libreoffice_calc" or action != "workbook.save":
        return False, None
    target = arguments.get("url", arguments.get("output_path"))
    return True, target if isinstance(target, str) and target.strip() else None


def _unrequested_destination_change_error(
    state: Any,
    action: str,
    arguments: dict[str, Any],
    *,
    before_step: int | None = None,
) -> str | None:
    domain, canonical, selected_arguments = canonical_action_request(
        str(getattr(state, "domain", "")), action, arguments
    )
    return _resolved_destination_change_error(
        state,
        domain,
        canonical,
        selected_arguments,
        before_step=before_step,
    )


def _resolved_destination_change_error(
    state: Any,
    domain: str,
    action: str,
    arguments: dict[str, Any],
    *,
    before_step: int | None = None,
) -> str | None:
    is_save, selected = _resolved_save_target(domain, action, arguments)
    if (
        not is_save
        or selected is None
        or _instruction_requests_destination_change(
            str(getattr(state, "instruction", ""))
        )
    ):
        return None
    opened = _latest_spreadsheet_open(state, before_step=before_step)
    if opened is None:
        return None
    inspected = _latest_successful_inspection_after(
        state, opened, before_step=before_step
    )
    if inspected is None:
        return (
            "the model selected an explicit spreadsheet save destination before "
            "the successfully opened workbook identity was verified; inspect the "
            "current workbook first, then omit the destination for an in-place save"
        )
    current = inspection_identity_url(inspected)
    if current is None or local_document_paths_match(current, selected):
        return None
    return (
        "the model selected a different spreadsheet save destination even though "
        "the instruction does not request Save As, export, conversion, or a copy; "
        "omit the destination to save the inspected workbook in place, or select "
        "the exact inspected workbook path"
    )


def argument_contract_errors(
    state: Any, action: str, arguments: dict[str, Any]
) -> list[str]:
    """Reject model-selected Calc writes until the opened workbook is observed."""
    if _latest_unobserved_open(state) is not None and _is_calc_mutation_or_save(
        str(getattr(state, "domain", "")), action, arguments
    ):
        return [
            "inspect the successfully opened spreadsheet with "
            "libreoffice_calc workbook.inspect before any Calc mutation or save; the Runner "
            "does not infer a worksheet, range, value, or save target"
        ]
    destination_error = _unrequested_destination_change_error(state, action, arguments)
    return [destination_error] if destination_error is not None else []


def completion_errors(state: Any) -> list[str]:
    """Preserve any successful mutation that preceded current-workbook inspection."""
    if str(getattr(state, "domain", "")) != "multi_apps":
        return []
    domain = str(getattr(state, "domain", ""))
    awaiting_inspection = False
    opened = None
    for event in sorted(
        getattr(state, "events", ()), key=lambda item: getattr(item, "step", 0)
    ):
        event_domain, event_action, _event_arguments = effective_canonical_action(
            event, domain
        )
        is_inspection = (event_domain, event_action) == _CANONICAL_INSPECT
        if _is_spreadsheet_open_event(event, domain):
            opened = event
            awaiting_inspection = True
            continue
        if is_inspection and opened is not None:
            if _is_successful_inspection(event, domain) and _inspection_matches_open(
                event, opened, domain
            ):
                awaiting_inspection = False
            else:
                # A later failed or wrong-workbook probe invalidates older
                # evidence until a fresh matching inspection succeeds.
                awaiting_inspection = True
            continue
        if not awaiting_inspection or not getattr(event, "executed", False):
            continue
        if event_domain == "libreoffice_calc" and not action_is_read_only(event_action):
            return [
                "a successfully opened spreadsheet was mutated or saved before a "
                "later successful workbook.inspect established the active workbook "
                "structure; that unsafe ordering remains in the episode ledger"
            ]
    for event in sorted(
        getattr(state, "events", ()), key=lambda item: getattr(item, "step", 0)
    ):
        if (
            not getattr(event, "executed", False)
            or _latest_spreadsheet_open(state, before_step=getattr(event, "step", 0))
            is None
        ):
            continue
        event_domain, action, arguments = effective_canonical_action(event, domain)
        error = _resolved_destination_change_error(
            state,
            event_domain,
            action,
            arguments,
            before_step=getattr(event, "step", 0),
        )
        if error is not None:
            return [error]
    return []


__all__ = [
    "INSPECT_ACTION",
    "OPEN_ACTION",
    "argument_contract_errors",
    "completion_errors",
    "gui_request_contract_errors",
    "inspection_retry_required",
    "pending_actions",
]
