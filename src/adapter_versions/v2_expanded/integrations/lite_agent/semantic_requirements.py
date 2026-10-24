"""Application-semantic completion requirements for strict episodes.

The checks in this module compare explicit instruction structure with
model-selected, successfully executed Adapter calls. They never inspect task
identity, evaluator state, or golden artifacts, and they never manufacture or
rewrite tool arguments.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from calc_adapter.schema import explicit_format_ranges
from impress_adapter.geometry_contract import ATOMIC_GEOMETRY_FIELDS

from .calc_column_reorder import missing_column_reorder_call
from . import (
    calc_semantics,
    impress_table_row,
)
from .calc_fill_down import missing_fill_down_columns
from .clipboard_path_semantics import (
    completion_errors as clipboard_path_completion_errors,
)
from .calc_scaled_display import (
    describe_scaled_display_output,
    missing_scaled_display_outputs,
)
from . import impress_semantics
from .filesystem_copy_semantics import (
    completion_errors as filesystem_copy_completion_errors,
)
from .impress_background import background_requirement_errors
from .impress_page_number import page_number_requirement_errors
from .impress_colors import normalize_impress_color
from .impress_role_formatting import (
    ACTION as MULTISLIDE_ROLE_ACTION,
    ROLE_ACTIONS,
    SINGLE_ACTION as SINGLE_SLIDE_ROLE_ACTION,
    action_slide_indices,
    adapter_confirmed_role_slides,
    multislide_role_requirement_errors,
    parse_multislide_role_format_intent,
)
from .impress_role_text_update import role_text_update_requirement_errors
from .impress_title_formatting import title_format_requirement_errors
from .impress_image_insertion import image_insertion_requirement_errors
from .impress_textboxes import all_textbox_color_requirement_errors
from .instruction_semantics import (
    requested_chart_count,
    requested_merged_text_regions,
    requested_pivot_count,
    requested_row_labels,
    requested_sheet_copy_lifecycle,
    requested_slide_content_formatting,
    requested_slide_role_text_formatting,
)
from .terminal_output_semantics import (
    completion_errors as terminal_output_completion_errors,
)
from . import source_execution_semantics
from .output_artifact_semantics import (
    completion_errors as output_artifact_completion_errors,
)
from .workspace_open_semantics import (
    completion_errors as workspace_open_completion_errors,
)


def _arguments(state: Any, action: str) -> list[dict[str, Any]]:
    return [
        arguments
        for event in state.successful_action_events(action)
        if isinstance((arguments := event.proposed.get("arguments")), dict)
    ]


def _identifier(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _values(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        if "value" in value:
            yield value["value"]
        for key, item in value.items():
            if key != "value":
                yield from _values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _values(item)
    else:
        yield value


def _range(value: Any) -> str:
    return re.sub(r"[\s$]", "", str(value)).upper()


def _has_region_write(writes: Iterable[dict[str, Any]], region: dict[str, Any]) -> bool:
    expected_sheet = _identifier(region["sheet"])
    expected_ranges = {_range(region["anchor"]), _range(region["range"])}
    expected_text = str(region["text"])
    return any(
        _identifier(arguments.get("sheet")) == expected_sheet
        and _range(arguments.get("range")) in expected_ranges
        and expected_text in {str(item) for item in _values(arguments.get("values"))}
        for arguments in writes
    )


def _has_region_text_action(
    actions: Iterable[dict[str, Any]], region: dict[str, Any]
) -> bool:
    expected_sheet = _identifier(region["sheet"])
    expected_range = _range(region["range"])
    expected_text = str(region["text"])
    return any(
        _identifier(arguments.get("sheet")) == expected_sheet
        and _range(arguments.get("range")) == expected_range
        and str(arguments.get("text")) == expected_text
        for arguments in actions
    )


def _has_region_format(
    formats: Iterable[dict[str, Any]], region: dict[str, Any]
) -> bool:
    expected = region.get("format")
    if not isinstance(expected, dict) or not expected:
        return True
    expected_sheet = _identifier(region["sheet"])
    expected_range = _range(region["range"])
    return any(
        _identifier(arguments.get("sheet")) == expected_sheet
        and expected_range
        in {
            _range(member)
            for member in (
                explicit_format_ranges(arguments.get("range"))
                or (arguments.get("range"),)
            )
        }
        and isinstance(arguments.get("format"), dict)
        and all(
            str(arguments["format"].get(key)).casefold() == str(value).casefold()
            for key, value in expected.items()
        )
        for arguments in formats
    )


def _calc_errors(state: Any) -> list[str]:
    instruction = str(state.instruction)
    errors: list[str] = list(calc_semantics.sort_completion_missing(state))

    chart_count = requested_chart_count(instruction)
    observed_charts = len(_arguments(state, "chart.create"))
    if chart_count > observed_charts:
        errors.append(
            f"the instruction requires {chart_count} chart.create operations; "
            f"only {observed_charts} succeeded"
        )

    pivot_count = requested_pivot_count(instruction)
    observed_pivots = len(_arguments(state, "pivot.create"))
    if pivot_count is not None and pivot_count > observed_pivots:
        errors.append(
            f"the instruction requires {pivot_count} pivot.create operations; "
            f"only {observed_pivots} succeeded"
        )

    missing_scaled_outputs = missing_scaled_display_outputs(
        instruction,
        _arguments(state, "range.set_scaled_display"),
    )
    if missing_scaled_outputs:
        missing = [
            describe_scaled_display_output(output) for output in missing_scaled_outputs
        ]
        errors.append(
            "range.set_scaled_display has not covered every explicitly requested "
            f"scaled output ({'; '.join(missing)}); submit one model-selected call for "
            "each missing output with the requested precision, separator, and rounding"
        )

    missing_reorder = missing_column_reorder_call(
        instruction,
        _arguments(state, "table.reorder_columns"),
    )
    if missing_reorder is not None:
        errors.append(
            "table.reorder_columns has not succeeded with every explicitly requested header "
            "in the requested order; submit one model-selected call for the complete nonblank table"
        )

    missing_fill_columns = missing_fill_down_columns(
        instruction,
        _arguments(state, "range.fill_down"),
    )
    if missing_fill_columns:
        errors.append(
            "range.fill_down has not covered every explicitly requested target column; "
            f"missing columns {list(missing_fill_columns)}. Submit a model-selected call "
            "for each missing column using the observed table row bounds"
        )

    labels = requested_row_labels(instruction)
    if labels:
        written_values = {
            str(item)
            for arguments in _arguments(state, "range.write")
            for item in _values(arguments.get("values"))
        }
        missing_labels = [label for label in labels if label not in written_values]
        if missing_labels:
            errors.append(
                "write every explicitly named summary row; missing row labels "
                f"{missing_labels}"
            )

    regions = requested_merged_text_regions(instruction)
    if regions:
        creates = _arguments(state, "sheet.create")
        merges = _arguments(state, "range.merge")
        writes = _arguments(state, "range.write")
        formats = _arguments(state, "range.format")
        sheet = str(regions[0]["sheet"])
        if not any(
            _identifier(item.get("name")) == _identifier(sheet) for item in creates
        ):
            errors.append(f"create the instruction-named sheet {sheet!r}")
        missing_merges = [
            region["range"]
            for region in regions
            if not any(
                _identifier(item.get("sheet")) == _identifier(region["sheet"])
                and _range(item.get("range")) == _range(region["range"])
                and item.get("merge") is True
                for item in merges
            )
        ]
        if missing_merges:
            errors.append(
                f"merge every instruction-named region; missing {missing_merges}"
            )
        missing_writes = [
            region["range"]
            for region in regions
            if not (_has_region_write(writes, region))
        ]
        if missing_writes:
            errors.append(
                "write the requested text into every merged region; missing "
                f"{missing_writes}"
            )
        missing_formats = [
            region["range"]
            for region in regions
            if not _has_region_format(formats, region)
        ]
        if missing_formats:
            errors.append(
                "apply every explicitly requested merged-region format; missing "
                f"{missing_formats}"
            )

    lifecycle = requested_sheet_copy_lifecycle(instruction)
    if lifecycle is not None:
        renames = _arguments(state, "sheet.rename")
        missing_renames = [
            rename
            for rename in lifecycle["renames"]
            if not any(
                _identifier(arguments.get("sheet")) == _identifier(rename["source"])
                and _identifier(arguments.get("new_name"))
                == _identifier(rename["target"])
                for arguments in renames
            )
        ]
        if missing_renames:
            errors.append(
                "perform every explicitly requested sheet rename; missing "
                f"{missing_renames}"
            )
        copies = _arguments(state, "sheet.copy")
        if not any(
            _identifier(arguments.get("sheet"))
            == _identifier(lifecycle["renamed_source"])
            and _identifier(arguments.get("new_name"))
            == _identifier(lifecycle["copy_name"])
            for arguments in copies
        ):
            errors.append(
                "copy the renamed source sheet with the exact instruction-derived copy name"
            )
    return errors


_IMPRESS_TEXT_ROLES = ("title", "content", "table", "text")
_IMPRESS_ROLE_ALIASES = {"body": "content"}
_IMPRESS_FORMAT_FIELDS = {
    "color",
    "font_size",
    "font_name",
    "bold",
    "italic",
    "underline",
    "strike",
    "alignment",
}


def _normalized_impress_color(value: Any) -> str | None:
    return normalize_impress_color(value)


def _impress_role_format_state(
    state: Any,
) -> dict[int, dict[str, dict[str, Any]]]:
    formatted: dict[int, dict[str, dict[str, Any]]] = {}
    events = sorted(
        (
            (action, event)
            for action in ROLE_ACTIONS
            for event in state.successful_action_events(action)
        ),
        key=lambda item: item[1].step,
    )
    for action, event in events:
        arguments = event.proposed.get("arguments")
        if not isinstance(arguments, dict):
            continue
        slides = action_slide_indices(arguments)
        if slides is None:
            continue
        rules = [
            {
                key: value
                for key, value in arguments.items()
                if key not in {"slide", "slides", "overrides"}
            },
            *[
                rule
                for rule in arguments.get("overrides", [])
                if isinstance(rule, dict)
            ],
        ]
        for slide in slides:
            slide_state = formatted.setdefault(slide, {})
            for rule in rules:
                roles = rule.get("roles")
                if not isinstance(roles, list):
                    continue
                selected = {
                    _IMPRESS_ROLE_ALIASES.get(str(role), str(role)) for role in roles
                }
                targets = set(_IMPRESS_TEXT_ROLES) if "all" in selected else selected
                if (
                    action == MULTISLIDE_ROLE_ACTION
                    and slide
                    not in adapter_confirmed_role_slides(event, tuple(targets))
                ):
                    continue
                properties = {
                    key: value
                    for key, value in rule.items()
                    if key in _IMPRESS_FORMAT_FIELDS
                }
                for role in targets.intersection(_IMPRESS_TEXT_ROLES):
                    slide_state.setdefault(role, {}).update(properties)
    return formatted


def _candidate_slides(
    requested_slide: Any, formatted: dict[int, dict[str, dict[str, Any]]]
) -> list[int]:
    return (
        [requested_slide]
        if isinstance(requested_slide, int) and not isinstance(requested_slide, bool)
        else sorted(formatted)
    )


def _role_text_request_satisfied(
    request: dict[str, Any], formatted: dict[int, dict[str, dict[str, Any]]]
) -> bool:
    expected_color = _normalized_impress_color(request["color"])
    for slide in _candidate_slides(request.get("slide"), formatted):
        roles = formatted.get(slide, {})
        if not all(
            _normalized_impress_color(roles.get(role, {}).get("color"))
            == expected_color
            for role in ("title", "content", "table")
        ):
            continue
        if roles.get("content", {}).get("underline") is not True:
            continue
        if any(
            roles.get(role, {}).get("underline") is True for role in ("title", "table")
        ):
            continue
        return True
    return False


def _content_text_request_satisfied(
    request: dict[str, Any], formatted: dict[int, dict[str, dict[str, Any]]]
) -> bool:
    expected_color = _normalized_impress_color(request["font_color"])
    expected_size = float(request["font_size"])
    for slide in _candidate_slides(request.get("slide"), formatted):
        roles = formatted.get(slide, {})
        content = roles.get("content", {})
        size = content.get("font_size")
        if (
            isinstance(size, bool)
            or not isinstance(size, (int, float))
            or float(size) != expected_size
            or _normalized_impress_color(content.get("color")) != expected_color
        ):
            continue
        if any(
            {"font_size", "color"}.intersection(roles.get(role, {}))
            for role in ("title", "table", "text")
        ):
            continue
        return True
    return False


def _impress_errors(state: Any) -> list[str]:
    instruction = str(state.instruction)
    errors: list[str] = []
    formatted = _impress_role_format_state(state)

    role_request = requested_slide_role_text_formatting(instruction)
    if role_request is not None and not _role_text_request_satisfied(
        role_request, formatted
    ):
        errors.append(
            "slide.format_text_roles has not covered the requested shared color for "
            "title, body, and table together with body-only underline; submit the "
            "missing model-selected role-format rule before completion"
        )

    content_request = requested_slide_content_formatting(instruction)
    if content_request is not None:
        if not _content_text_request_satisfied(content_request, formatted):
            errors.append(
                "slide.format_text_roles has not covered the exact requested content-only "
                "font size and color without changing other text roles"
            )
    errors.extend(background_requirement_errors(state))
    errors.extend(page_number_requirement_errors(state))
    errors.extend(impress_table_row.requirement_errors(state))
    errors.extend(all_textbox_color_requirement_errors(state))
    errors.extend(multislide_role_requirement_errors(state))
    errors.extend(role_text_update_requirement_errors(state))
    errors.extend(title_format_requirement_errors(state))
    errors.extend(image_insertion_requirement_errors(state))
    return errors


def strict_semantic_requirement_errors(state: Any) -> list[str]:
    """Return unmet reusable instruction requirements for completion gating."""
    if state.domain == "libreoffice_calc":
        return _calc_errors(state)
    if state.domain == "libreoffice_impress":
        return [
            *_impress_errors(state),
            *impress_semantics.completion_missing(state),
        ]
    if state.domain == "multi_apps":
        return [
            *source_execution_semantics.completion_errors(state),
            *output_artifact_completion_errors(state),
        ]
    if state.domain == "os":
        return [
            *terminal_output_completion_errors(state),
            *filesystem_copy_completion_errors(state),
            *clipboard_path_completion_errors(state),
            *output_artifact_completion_errors(state),
        ]
    if state.domain == "vs_code":
        return workspace_open_completion_errors(state)
    return []


def strict_semantic_action_equivalents(state: Any) -> dict[str, set[str]]:
    """Map canonical public actions to reusable semantic alternatives."""
    equivalents: dict[str, set[str]] = {}
    if state.domain == "libreoffice_impress":
        # The generic geometry requirement predates the separate public operations.
        # Accept their successful execution as evidence; keep save/read-back and
        # target coverage checks, and never rewrite the recorded model action.
        equivalents["shape.set_geometry"] = set(ATOMIC_GEOMETRY_FIELDS)
        # The verified image-deck operation already creates the slides and
        # inserts their images. Requiring both older actions afterward makes
        # the model add unwanted slides/objects to an otherwise complete deck.
        equivalents["slide.create"] = {"slides.create_from_images"}
        equivalents["shape.insert_image"] = {"slides.create_from_images"}
    if (
        state.domain == "libreoffice_impress"
        and impress_semantics.parse_textbox_underline_intent(str(state.instruction))
        is not None
    ):
        equivalents["shape.format_text"] = set(ROLE_ACTIONS)
    if (
        state.domain == "libreoffice_impress"
        and parse_multislide_role_format_intent(str(state.instruction)) is not None
    ):
        equivalents[MULTISLIDE_ROLE_ACTION] = {SINGLE_SLIDE_ROLE_ACTION}
    if state.domain == "libreoffice_impress" and (
        requested_slide_content_formatting(str(state.instruction)) is not None
        or requested_slide_role_text_formatting(str(state.instruction)) is not None
    ):
        equivalents[SINGLE_SLIDE_ROLE_ACTION] = {MULTISLIDE_ROLE_ACTION}
    return equivalents
