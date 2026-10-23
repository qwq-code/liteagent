from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from urllib.parse import unquote, urlparse

from .errors import AdapterError
from .notes_transfer import read_docx_paragraphs


MAX_SUBMISSIONS = 200
MAX_QUESTIONS = 200
_ANSWER_RE = re.compile(
    r"(?:[\u3010\[]\s*answer\s*[\u3011\]]|\banswer\s*[:\uff1a])\s*"
    r"([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_STUDENT_ID_RE = re.compile(
    r"(?:student|candidate)\s*(?:id|number)\s*[:\uff1a]\s*([^\s]+)",
    re.IGNORECASE,
)
_STUDENT_NAME_RE = re.compile(
    r"(?:student|candidate)\s*name\s*[:\uff1a]\s*(.+?)\s*$",
    re.IGNORECASE,
)
_POINTS_RE = re.compile(
    r"(?P<points>\d+(?:\.\d+)?)\s*(?:points?|marks?)\s*"
    r"(?:per\s+question|for\s+each\s+question)",
    re.IGNORECASE,
)
_QUESTION_HEADER_RE = re.compile(r"(?:q|question)(\d+)$")


@dataclass(frozen=True)
class Submission:
    path: Path
    student_id: str
    student_name: str
    answers: tuple[str, ...]


def validate_grade_multiple_choice_params(params: Mapping[str, Any]) -> None:
    allowed = {
        "reference_path",
        "workbook_path",
        "submissions_directory",
        "submission_glob",
        "sheet",
        "points_per_correct",
        "correct_value",
        "incorrect_value",
        "preserve_existing",
    }
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST",
            "assessment.grade_multiple_choice_documents received unsupported parameters",
            {"unexpected": unexpected, "allowed": sorted(allowed)},
        )
    for field, suffixes in (
        ("reference_path", (".docx",)),
        ("workbook_path", (".csv", ".ods", ".xlsx")),
    ):
        if field not in params:
            continue
        value = params[field]
        if (
            not isinstance(value, str)
            or not value.strip()
            or not value.startswith(("/", "~/", "file:///"))
            or not value.casefold().endswith(suffixes)
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.{field} must be a local supported file path",
            )
    if "submissions_directory" in params:
        value = params["submissions_directory"]
        if not isinstance(value, str) or not value.startswith(("/", "~/")):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.submissions_directory must be absolute or begin with ~/",
            )
    if "submission_glob" in params:
        value = params["submission_glob"]
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 120
            or "/" in value
            or "\\" in value
            or ".." in value
        ):
            raise AdapterError(
                "INVALID_REQUEST",
                "params.submission_glob must be a basename-only glob up to 120 characters",
            )
    if "sheet" in params and (
        not isinstance(params["sheet"], str) or not params["sheet"].strip()
    ):
        raise AdapterError("INVALID_REQUEST", "params.sheet must be a non-empty string")
    for field in ("points_per_correct", "correct_value", "incorrect_value"):
        if field not in params:
            continue
        value = params[field]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise AdapterError(
                "INVALID_REQUEST", f"params.{field} must be finite numeric"
            )
    if (
        "points_per_correct" in params
        and not 0 < params["points_per_correct"] <= 1_000_000
    ):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.points_per_correct must be greater than zero and at most 1000000",
        )
    if float(params.get("correct_value", 1)) == float(params.get("incorrect_value", 0)):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.correct_value and params.incorrect_value must differ",
        )
    if "preserve_existing" in params and not isinstance(
        params["preserve_existing"], bool
    ):
        raise AdapterError(
            "INVALID_REQUEST", "params.preserve_existing must be a boolean"
        )


def local_path(value: str, *, field: str, suffixes: set[str]) -> Path:
    if value.startswith("file://"):
        parsed = urlparse(value)
        if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"}:
            raise AdapterError(
                "INVALID_PATH",
                f"{field} must be a local file URL",
                {field: value},
                422,
            )
        path = Path(unquote(parsed.path))
    else:
        path = Path(value).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise AdapterError(
            "PATH_NOT_FOUND",
            f"{field} does not exist",
            {field: value},
            404,
        ) from exc
    if not resolved.is_file() or resolved.suffix.casefold() not in suffixes:
        raise AdapterError(
            "INVALID_PATH",
            f"{field} must identify a supported local file",
            {field: str(resolved), "supported_suffixes": sorted(suffixes)},
            422,
        )
    return resolved


def _answers(paragraphs: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        match.group(1).strip().casefold()
        for paragraph in paragraphs
        for match in _ANSWER_RE.finditer(paragraph)
    )


def _submission(path: Path) -> Submission | None:
    paragraphs = read_docx_paragraphs(path)
    student_id = None
    student_name = None
    for paragraph in paragraphs:
        if student_id is None:
            match = _STUDENT_ID_RE.search(paragraph)
            if match is not None:
                student_id = match.group(1).strip()
        if student_name is None:
            match = _STUDENT_NAME_RE.search(paragraph)
            if match is not None:
                student_name = match.group(1).strip()
    if student_id is None and student_name is None:
        return None
    if not student_id or not student_name:
        raise AdapterError(
            "SUBMISSION_IDENTITY_INCOMPLETE",
            "a response document must contain both a student/candidate ID and name",
            {
                "path": str(path),
                "student_id_found": bool(student_id),
                "student_name_found": bool(student_name),
            },
            422,
        )
    answers = _answers(paragraphs)
    if not answers:
        raise AdapterError(
            "SUBMISSION_ANSWERS_NOT_FOUND",
            "a response document contained identity fields but no answer markers",
            {"path": str(path)},
            422,
        )
    return Submission(path, student_id, student_name, answers)


def load_assessment_documents(
    reference_path: Path,
    *,
    submissions_directory: str | None,
    submission_glob: str,
) -> tuple[list[str], tuple[str, ...], list[Submission]]:
    reference_paragraphs = read_docx_paragraphs(reference_path)
    reference_answers = _answers(reference_paragraphs)
    if not 1 <= len(reference_answers) <= MAX_QUESTIONS:
        raise AdapterError(
            "REFERENCE_ANSWERS_NOT_FOUND",
            "the reference document must contain from 1 to 200 answer markers",
            {
                "reference_path": str(reference_path),
                "answer_count": len(reference_answers),
            },
            422,
        )
    directory = (
        Path(submissions_directory).expanduser()
        if submissions_directory is not None
        else reference_path.parent
    )
    try:
        directory = directory.resolve(strict=True)
    except OSError as exc:
        raise AdapterError(
            "SUBMISSIONS_DIRECTORY_NOT_FOUND",
            "submissions_directory does not exist",
            {"submissions_directory": str(directory)},
            404,
        ) from exc
    if not directory.is_dir():
        raise AdapterError(
            "INVALID_SUBMISSIONS_DIRECTORY",
            "submissions_directory must identify a local directory",
            {"submissions_directory": str(directory)},
            422,
        )
    if (
        not submission_glob
        or "/" in submission_glob
        or "\\" in submission_glob
        or ".." in submission_glob
    ):
        raise AdapterError(
            "INVALID_SUBMISSION_GLOB",
            "submission_glob must be a basename-only glob",
            {"submission_glob": submission_glob},
            422,
        )
    candidates = sorted(
        path.resolve()
        for path in directory.glob(submission_glob)
        if path.is_file()
        and path.suffix.casefold() == ".docx"
        and path.resolve() != reference_path
    )
    if len(candidates) > MAX_SUBMISSIONS:
        raise AdapterError(
            "TOO_MANY_SUBMISSIONS",
            "the selected directory contains more than 200 candidate response documents",
            {"candidate_count": len(candidates)},
            422,
        )
    submissions = [item for path in candidates if (item := _submission(path))]
    if not submissions:
        raise AdapterError(
            "SUBMISSIONS_NOT_FOUND",
            "no DOCX files with student/candidate identity and answer markers were found",
            {
                "submissions_directory": str(directory),
                "submission_glob": submission_glob,
                "candidate_count": len(candidates),
            },
            404,
        )
    mismatches = [
        {"path": str(item.path), "answer_count": len(item.answers)}
        for item in submissions
        if len(item.answers) != len(reference_answers)
    ]
    if mismatches:
        raise AdapterError(
            "SUBMISSION_ANSWER_COUNT_MISMATCH",
            "every response document must contain the same number of answers as the reference",
            {
                "reference_answer_count": len(reference_answers),
                "mismatches": mismatches[:20],
            },
            422,
        )
    identities = [
        (item.student_id.casefold(), item.student_name.casefold())
        for item in submissions
    ]
    if len(set(identities)) != len(identities):
        raise AdapterError(
            "DUPLICATE_SUBMISSION_IDENTITY",
            "student/candidate identities must be unique across response documents",
            {"submission_count": len(submissions)},
            422,
        )
    return reference_paragraphs, reference_answers, submissions


def _normalized_header(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _header_layout(
    workbook: Mapping[str, Any],
    *,
    sheet_name: str | None,
    question_count: int,
) -> dict[str, Any]:
    layouts: list[dict[str, Any]] = []
    for sheet in workbook.get("sheets", []):
        if not isinstance(sheet, Mapping) or (
            sheet_name is not None and sheet.get("name") != sheet_name
        ):
            continue
        matrix = sheet.get("display_text")
        if not isinstance(matrix, list):
            continue
        for row_index, row in enumerate(matrix):
            if not isinstance(row, list):
                continue
            normalized = [_normalized_header(value) for value in row]
            id_columns = [
                index
                for index, value in enumerate(normalized)
                if value
                in {
                    "studentid",
                    "studentnumber",
                    "candidateid",
                    "candidatenumber",
                    "id",
                }
            ]
            name_columns = [
                index
                for index, value in enumerate(normalized)
                if value in {"studentname", "candidatename", "name"}
            ]
            total_columns = [
                index
                for index, value in enumerate(normalized)
                if value
                in {
                    "total",
                    "totalscore",
                    "totalgrade",
                    "totalpoints",
                    "score",
                    "grade",
                }
            ]
            question_columns: dict[int, int] = {}
            for index, value in enumerate(normalized):
                match = _QUESTION_HEADER_RE.fullmatch(value)
                if match is not None:
                    question_columns[int(match.group(1))] = index
            if (
                len(id_columns) == 1
                and len(name_columns) == 1
                and len(total_columns) == 1
                and set(question_columns) == set(range(1, question_count + 1))
            ):
                layouts.append(
                    {
                        "sheet": str(sheet.get("name")),
                        "matrix": matrix,
                        "header_row_index": row_index,
                        "id_column": id_columns[0],
                        "name_column": name_columns[0],
                        "question_columns": [
                            question_columns[number]
                            for number in range(1, question_count + 1)
                        ],
                        "total_column": total_columns[0],
                    }
                )
    if not layouts:
        raise AdapterError(
            "GRADING_TABLE_NOT_FOUND",
            "no worksheet contained unique student ID/name, sequential question, and total headers",
            {
                "requested_sheet": sheet_name,
                "question_count": question_count,
                "sheet_names": [
                    sheet.get("name")
                    for sheet in workbook.get("sheets", [])
                    if isinstance(sheet, Mapping)
                ],
            },
            404,
        )
    if len(layouts) != 1:
        raise AdapterError(
            "GRADING_TABLE_NOT_UNIQUE",
            "more than one worksheet/header row matched the grading table shape; provide sheet",
            {
                "matches": [
                    {"sheet": item["sheet"], "header_row": item["header_row_index"] + 1}
                    for item in layouts
                ]
            },
            422,
        )
    layout = layouts[0]
    expected_columns = list(
        range(
            layout["question_columns"][0],
            layout["question_columns"][0] + question_count,
        )
    )
    if (
        layout["question_columns"] != expected_columns
        or layout["total_column"] != expected_columns[-1] + 1
    ):
        raise AdapterError(
            "GRADING_COLUMNS_NOT_CONTIGUOUS",
            "question columns followed by the total column must be contiguous",
            {
                "question_columns": [value + 1 for value in layout["question_columns"]],
                "total_column": layout["total_column"] + 1,
            },
            422,
        )
    return layout


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _points_per_correct(
    reference_paragraphs: Sequence[str],
    layout: Mapping[str, Any],
    *,
    explicit: float | None,
    correct_value: float,
) -> float:
    if explicit is not None:
        return explicit
    for paragraph in reference_paragraphs:
        match = _POINTS_RE.search(paragraph)
        if match is not None:
            return float(match.group("points"))
    inferred: list[float] = []
    matrix = layout["matrix"]
    for row in matrix[layout["header_row_index"] + 1 :]:
        if not isinstance(row, list) or layout["total_column"] >= len(row):
            continue
        question_values = [
            _number(row[index]) if index < len(row) else None
            for index in layout["question_columns"]
        ]
        total = _number(row[layout["total_column"]])
        correct_count = sum(
            value is not None and abs(value - correct_value) <= 1e-9
            for value in question_values
        )
        if (
            all(value is not None for value in question_values)
            and total is not None
            and correct_count
        ):
            inferred.append(total / correct_count)
    if inferred and max(inferred) - min(inferred) <= 1e-9 and inferred[0] > 0:
        return inferred[0]
    raise AdapterError(
        "POINTS_PER_CORRECT_UNAVAILABLE",
        "points_per_correct could not be inferred from the reference or completed workbook rows",
        {"inferred_candidates": inferred[:20]},
        422,
    )


def _column_label(index: int) -> str:
    value = index + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(ord("A") + remainder) + label
    return label


def build_grading_plan(
    workbook: Mapping[str, Any],
    reference_paragraphs: Sequence[str],
    reference_answers: Sequence[str],
    submissions: Sequence[Submission],
    params: Mapping[str, Any],
) -> dict[str, Any]:
    layout = _header_layout(
        workbook,
        sheet_name=params.get("sheet"),
        question_count=len(reference_answers),
    )
    correct_value = float(params.get("correct_value", 1))
    incorrect_value = float(params.get("incorrect_value", 0))
    points = _points_per_correct(
        reference_paragraphs,
        layout,
        explicit=float(params["points_per_correct"])
        if "points_per_correct" in params
        else None,
        correct_value=correct_value,
    )
    matrix = layout["matrix"]
    rows_by_id: dict[str, list[tuple[int, list[Any]]]] = {}
    rows_by_name: dict[str, list[tuple[int, list[Any]]]] = {}
    for row_index, row in enumerate(
        matrix[layout["header_row_index"] + 1 :],
        start=layout["header_row_index"] + 1,
    ):
        if not isinstance(row, list):
            continue
        if layout["id_column"] < len(row) and str(row[layout["id_column"]]).strip():
            rows_by_id.setdefault(
                str(row[layout["id_column"]]).strip().casefold(), []
            ).append((row_index, row))
        if layout["name_column"] < len(row) and str(row[layout["name_column"]]).strip():
            rows_by_name.setdefault(
                str(row[layout["name_column"]]).strip().casefold(), []
            ).append((row_index, row))

    updates = []
    skipped = []
    for submission in submissions:
        matches = rows_by_id.get(submission.student_id.strip().casefold(), [])
        if not matches:
            matches = rows_by_name.get(submission.student_name.strip().casefold(), [])
        if len(matches) != 1:
            raise AdapterError(
                "STUDENT_ROW_NOT_UNIQUE",
                "each response document must match exactly one workbook row by ID or name",
                {
                    "student_id": submission.student_id,
                    "student_name": submission.student_name,
                    "match_count": len(matches),
                },
                422,
            )
        row_index, row = matches[0]
        relevant_columns = [*layout["question_columns"], layout["total_column"]]
        existing = [
            row[index] if index < len(row) else "" for index in relevant_columns
        ]
        if params.get("preserve_existing", True) and all(
            str(value).strip() for value in existing
        ):
            skipped.append(
                {
                    "student_id": submission.student_id,
                    "student_name": submission.student_name,
                    "row": row_index + 1,
                }
            )
            continue
        detail = [
            correct_value if actual == expected else incorrect_value
            for actual, expected in zip(
                submission.answers, reference_answers, strict=True
            )
        ]
        correct_count = sum(
            actual == expected
            for actual, expected in zip(
                submission.answers, reference_answers, strict=True
            )
        )
        values = [*detail, correct_count * points]
        start_column = layout["question_columns"][0]
        updates.append(
            {
                "student_id": submission.student_id,
                "student_name": submission.student_name,
                "row": row_index + 1,
                "range": (
                    f"{_column_label(start_column)}{row_index + 1}:"
                    f"{_column_label(layout['total_column'])}{row_index + 1}"
                ),
                "values": values,
                "correct_count": correct_count,
                "total": correct_count * points,
            }
        )
    return {
        "sheet": layout["sheet"],
        "question_count": len(reference_answers),
        "points_per_correct": points,
        "correct_value": correct_value,
        "incorrect_value": incorrect_value,
        "submission_count": len(submissions),
        "updates": updates,
        "skipped_existing": skipped,
    }


def verify_grading_plan(
    workbook: Mapping[str, Any], plan: Mapping[str, Any]
) -> dict[str, Any]:
    sheet = next(
        (
            item
            for item in workbook.get("sheets", [])
            if isinstance(item, Mapping) and item.get("name") == plan["sheet"]
        ),
        None,
    )
    matrix = sheet.get("display_text") if isinstance(sheet, Mapping) else None
    checks = []
    for update in plan["updates"]:
        observed = None
        passed = False
        row_index = update["row"] - 1
        if isinstance(matrix, list) and row_index < len(matrix):
            row = matrix[row_index]
            if isinstance(row, list):
                start = _column_index_from_range(update["range"])
                observed = row[start : start + len(update["values"])]
                passed = len(observed) == len(update["values"]) and all(
                    (
                        _number(actual) is not None
                        and abs(_number(actual) - float(expected)) <= 1e-9
                    )
                    for actual, expected in zip(observed, update["values"], strict=True)
                )
        checks.append(
            {
                "type": "graded_submission_row",
                "student_id": update["student_id"],
                "row": update["row"],
                "range": update["range"],
                "passed": passed,
                "observed": observed,
            }
        )
    return {"passed": all(item["passed"] for item in checks), "checks": checks}


def _column_index_from_range(range_ref: str) -> int:
    match = re.match(r"([A-Za-z]+)", range_ref)
    if match is None:
        raise ValueError(f"invalid A1 range: {range_ref}")
    value = 0
    for character in match.group(1).upper():
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _current_document_path(actions: Any, timeout_seconds: float) -> Path:
    inspected = actions.call_adapter(
        {
            "adapter": "libreoffice_writer",
            "action": "document.inspect",
            "payload": {"params": {}},
        },
        timeout_seconds,
    )
    result = actions._downstream_result(inspected)
    identity = result.get("identity")
    url = identity.get("url") if isinstance(identity, Mapping) else None
    if not isinstance(url, str) or not url:
        raise AdapterError(
            "REFERENCE_PATH_UNAVAILABLE",
            "the current Writer document has no local saved path; provide reference_path",
            {"identity": identity},
            422,
        )
    return local_path(url, field="reference_path", suffixes={".docx"})


def _current_workbook_path(actions: Any, timeout_seconds: float) -> Path:
    inspected = actions.call_adapter(
        {
            "adapter": "libreoffice_calc",
            "action": "workbook.inspect",
            "payload": {"params": {}},
        },
        timeout_seconds,
    )
    result = actions._downstream_result(inspected)
    url = result.get("url")
    if not isinstance(url, str) or not url:
        raise AdapterError(
            "WORKBOOK_PATH_UNAVAILABLE",
            "the current Calc workbook has no local saved path; provide workbook_path",
            {"identity": {"url": url, "title": result.get("title")}},
            422,
        )
    return local_path(url, field="workbook_path", suffixes={".csv", ".ods", ".xlsx"})


def grade_multiple_choice_documents(
    actions: Any,
    params: Mapping[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    reference_path = (
        local_path(
            params["reference_path"],
            field="reference_path",
            suffixes={".docx"},
        )
        if "reference_path" in params
        else _current_document_path(actions, timeout_seconds)
    )
    workbook_path = (
        local_path(
            params["workbook_path"],
            field="workbook_path",
            suffixes={".csv", ".ods", ".xlsx"},
        )
        if "workbook_path" in params
        else _current_workbook_path(actions, timeout_seconds)
    )
    reference_paragraphs, reference_answers, submissions = load_assessment_documents(
        reference_path,
        submissions_directory=params.get("submissions_directory"),
        submission_glob=params.get("submission_glob", "*.docx"),
    )
    read_params: dict[str, Any] = {
        "path": str(workbook_path),
        "max_rows": 1000,
        "max_columns": 256,
        "max_sheets": 32,
    }
    if "sheet" in params:
        read_params["sheet"] = params["sheet"]
    initial = actions._downstream_result(
        actions.read_spreadsheet_file(read_params, timeout_seconds)
    )
    plan = build_grading_plan(
        initial,
        reference_paragraphs,
        reference_answers,
        submissions,
        params,
    )
    for update in plan["updates"]:
        actions.write_spreadsheet_range(
            {
                "sheet": plan["sheet"],
                "range": update["range"],
                "values": update["values"],
            },
            timeout_seconds,
        )
    saved = actions._downstream_result(
        actions.save_spreadsheet_workbook({}, timeout_seconds)
    )
    observed = actions._downstream_result(
        actions.read_spreadsheet_file(read_params, timeout_seconds)
    )
    verification = verify_grading_plan(observed, plan)
    if not verification["passed"]:
        raise AdapterError(
            "VERIFICATION_FAILED",
            "one or more graded workbook rows did not match the computed assessment plan after save",
            verification,
            422,
        )
    return {
        "reference_path": str(reference_path),
        "workbook_path": str(workbook_path),
        "sheet": plan["sheet"],
        "question_count": plan["question_count"],
        "submission_count": plan["submission_count"],
        "graded_count": len(plan["updates"]),
        "skipped_existing_count": len(plan["skipped_existing"]),
        "points_per_correct": plan["points_per_correct"],
        "graded_rows": [
            {
                key: update[key]
                for key in (
                    "student_id",
                    "student_name",
                    "row",
                    "range",
                    "correct_count",
                    "total",
                )
            }
            for update in plan["updates"]
        ],
        "skipped_existing_rows": plan["skipped_existing"],
        "changed": bool(plan["updates"]),
        "saved_url": saved.get("url"),
        "saved_path": saved.get("path"),
        "saved_size": saved.get("size"),
        "verification": verification,
    }
