"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations
import re
from typing import Any
from . import (
    calc_semantics,
    impress_semantics,
    impress_cover_semantics,
    impress_image_insertion,
    impress_title_formatting,
    impress_role_text_update,
    source_execution_semantics,
    terminal_output_semantics,
    vscode_configuration_semantics,
)
from .adapter_results import (
    a1_geometry,
    adapter_context_hint as adapter_context_hint,
    column_label,
    column_number,
    compact_adapter_body as compact_adapter_body,
)
from .completion_policy import (
    completion_claim_contradictions as completion_claim_contradictions,
)
from .generic_routing import (
    discovered_adapter_routes,
    filter_generic_actions,
    focus_generic_actions,
    stage_generic_actions,
)
from .tool_catalog import FORBIDDEN_DATASET_ACTIONS, select_actions
from .instruction_semantics import (
    requested_audio_path,
    requests_presentation_audio_insertion,
    requested_sized_slide_image,
    requested_table_row_replacement,
    requested_ordered_image_slides,
    requested_sheet_names,
    requested_sheet_copy_lifecycle,
    requested_row_labels,
    requested_text_line_indices,
    requests_appended_named_rows,
    valid_month_growth_formula,
    requested_os_account,
    requested_slide_background_color,
    requested_title_edge_position,
    requested_slide_title_update,
    requested_slide_title_formatting,
    requested_named_slide_table,
    requested_image_edge_position,
    requested_table_edge_position,
    requested_title_range_personal_info_cleanup,
    requested_slide_role_text_formatting,
    requested_slide_content_formatting,
    requested_matching_indent_without_bullet,
    strict_instruction_required_actions,
)
from .state_model import RuntimeState
from .local_file_discovery import stage_local_file_discovery
from .vscode_workspace_context import (
    has_successful_workspace_inspect,
    has_verified_workspace_addition,
    requests_workspace_folder_addition,
)


def _debug_dependency_recovery_needed(state: RuntimeState) -> bool:
    """Expose the generic extension primitive after a failed debug launch."""
    events = getattr(state, "events", ())
    if not events:
        return False
    event = events[-1]
    if getattr(event, "executed", False):
        return False
    proposed = getattr(event, "proposed", None)
    if not isinstance(proposed, dict) or proposed.get("action") != "debug.start":
        return False
    error = getattr(event, "error", None)
    if not isinstance(error, dict):
        return False
    # Adapter and worker wrappers use different public error fields. Walk only
    # the bounded nested error shape; never inspect task data or arguments.
    current: Any = error
    for _ in range(3):
        if not isinstance(current, dict):
            return False
        code = current.get("code") or current.get("error_code") or current.get("type")
        if isinstance(code, str) and code in {
            "VSCODE_NOT_READY",
            "OPERATION_TIMEOUT",
            "VERIFICATION_FAILED",
        }:
            return True
        nested = current.get("error") or current.get("previous_error")
        if isinstance(nested, dict):
            current = nested
            continue
        details = current.get("details")
        if isinstance(details, dict) and isinstance(details.get("error"), dict):
            current = details["error"]
            continue
        return False
    return False


class ActionSelectionMixin:
    def selected_actions(self, state: RuntimeState) -> list[str]:
        semantic_hints = [
            action
            for action in strict_instruction_required_actions(
                state.domain, state.instruction
            )
            if action not in FORBIDDEN_DATASET_ACTIONS
        ]
        if (
            state.domain == "libreoffice_impress"
            and requested_ordered_image_slides(state.instruction) is not None
        ):
            # Keep template cleanup discoverable without making both operations
            # required successful actions in completion review.
            semantic_hints.extend(["slide.delete", "shape.delete"])
        selected = [
            action
            for action in select_actions(
                state.domain,
                state.instruction,
                recommended=semantic_hints,
                expanded=state.expanded_actions,
                limit=self.config.top_k_actions if state.domain == "multi_apps" else None,
            )
            if action not in FORBIDDEN_DATASET_ACTIONS
        ]
        if state.domain == "multi_apps":
            # ``expanded_actions`` is populated from a successful tools_search
            # response by the runtime.  Keep the state-derived route check as
            # the authoritative execution guard, while accepting the compact
            # expanded-action projection used by recovery/state handoffs.
            if "adapter.call" not in state.expanded_actions and not discovered_adapter_routes(state):
                return [action for action in selected if action != "adapter.call"]
            return [action for action in selected if action == "adapter.call"]

        # Filter before Top-K so a satisfied read or blocked action frees its
        # slot for the next ranked tool instead of silently shrinking the set.
        selected = filter_generic_actions(state, selected)[: self.config.top_k_actions]
        selected = stage_local_file_discovery(state, selected)
        selected = focus_generic_actions(state, selected, semantic_hints)
        selected = stage_generic_actions(state, selected)
        selected = impress_semantics.stage_actions(
            state, selected, prefer_role_api=True
        )
        selected = impress_image_insertion.stage_actions(state, selected)
        selected = impress_role_text_update.stage_actions(state, selected)
        selected = impress_title_formatting.stage_actions(state, selected)
        # Table mutations need exact cell identifiers returned by table.read.
        # Keep the public read action visible alongside a Writer table
        # mutator so the model does not guess identifiers from the table name.
        if state.domain == "libreoffice_writer" and any(
            action.startswith("table.") and action != "table.read"
            for action in selected
        ) and "table.read" not in selected:
            selected.append("table.read")
        selected = vscode_configuration_semantics.stage_actions(
            state.domain, state.instruction, selected, state.events
        )
        selected = source_execution_semantics.stage_actions(state, selected)
        selected = terminal_output_semantics.stage_actions(state, selected)
        if (
            state.domain == "vs_code"
            and requests_workspace_folder_addition(state.instruction)
            and has_successful_workspace_inspect(state)
        ):
            # The inspect result contains the exact saved workspace path. Keep the
            # next model turn on the requested additive mutation so a small model
            # cannot repeat the read-only probe. After verified mutation, only
            # completion controls remain; repeating the write cannot add evidence.
            selected = (
                [] if has_verified_workspace_addition(state)
                else ["workspace.add_folders"]
            )
        # A failed debug.start commonly means that VS Code is waiting for a
        # debugger extension. Keep the existing model-selected alternatives,
        # but make the public install primitive visible on the next turn so
        # the model can choose it with its own source and source_type. This is
        # recovery routing only; no extension identity or argument is inferred.
        if state.domain == "vs_code" and _debug_dependency_recovery_needed(state):
            selected = [
                action for action in selected if action != "extension.install"
            ]
            limit = max(1, int(self.config.top_k_actions))
            if len(selected) >= limit:
                selected = selected[: limit - 1]
            selected.append("extension.install")
        return selected

    @staticmethod
    def _validate_stateful_arguments(
        state: RuntimeState, action: str, arguments: dict[str, Any]
    ) -> None:
        if impress_semantics.validate_arguments(state, action, arguments):
            return
        period_rate_step = state.next_period_rate_action()
        if (
            state.period_rate_request() is not None
            and period_rate_step is not None
            and (
                action
                in {
                    "workbook.inspect",
                    "range.read",
                    "range.write",
                    "range.format",
                    "workbook.save",
                }
            )
        ):
            if (
                period_rate_step["action"] != action
                or period_rate_step["arguments"] != arguments
            ):
                raise ValueError(
                    f"period-rate action must match the next instruction- and source-table-derived step: {period_rate_step!r}"
                )
            return
        annual_step = state.next_annual_percentage_change_action()
        if (
            state.annual_percentage_change_request() is not None
            and annual_step is not None
            and (
                action
                in {
                    "workbook.inspect",
                    "range.read",
                    "sheet.create",
                    "range.write",
                    "range.format",
                    "workbook.save",
                }
            )
        ):
            if annual_step["action"] != action or annual_step["arguments"] != arguments:
                raise ValueError(
                    f"annual percentage-change action must match the next instruction- and source-table-derived step: {annual_step!r}"
                )
            return
        monthly_totals_step = state.next_monthly_column_totals_action()
        if (
            state.monthly_column_totals_request() is not None
            and monthly_totals_step is not None
            and (
                action
                in {
                    "workbook.inspect",
                    "range.read",
                    "sheet.create",
                    "range.write",
                    "workbook.save",
                }
            )
        ):
            if (
                monthly_totals_step["action"] != action
                or monthly_totals_step["arguments"] != arguments
            ):
                raise ValueError(
                    f"monthly column-totals action must match the next instruction- and source-table-derived step: {monthly_totals_step!r}"
                )
            return
        sheet_lifecycle = requested_sheet_copy_lifecycle(state.instruction)
        if sheet_lifecycle is not None and action in {"sheet.rename", "sheet.copy"}:
            expected = state.next_sheet_copy_lifecycle_action()
            if (
                expected is None
                or expected["action"] != action
                or expected["arguments"] != arguments
            ):
                raise ValueError(
                    f"sheet lifecycle action must match the next instruction-derived, workbook-observed step: {expected!r}"
                )
            return
        requested_sheets = requested_sheet_names(state.instruction)
        if action == "sheet.create" and len(requested_sheets) == 1:
            if arguments.get("name") != requested_sheets[0]:
                raise ValueError(
                    f"sheet.create name must match the single instruction-derived sheet name: {requested_sheets[0]!r}"
                )
            return
        merged_text_specs = state.merged_text_region_specs()
        if merged_text_specs and action in {
            "range.merge",
            "range.write",
            "range.format",
        }:
            expected = state.next_merged_text_action()
            if (
                expected is None
                or expected["action"] != action
                or expected["arguments"] != arguments
            ):
                raise ValueError(
                    f"merged-text action must match the next instruction-derived range/text step: {expected!r}"
                )
            return
        stacked_pivot_step = state.next_stacked_percentage_pivot_action()
        if action == "pivot.create" and stacked_pivot_step is not None:
            expected = stacked_pivot_step["arguments"]
            if arguments != expected:
                raise ValueError(
                    f"stacked percentage pivot must match the next instruction- and source-table-derived step: {expected!r}"
                )
            return
        ordered_request = requested_ordered_image_slides(state.instruction)
        if (
            ordered_request is not None
            and action == "slides.create_from_images"
        ):
            expected = {
                "image_paths": ordered_request["files"],
                "replace_existing_slides": True,
            }
            if any(
                arguments.get(key) != value for key, value in expected.items()
            ):
                raise ValueError(
                    "slides.create_from_images must use the ordered Desktop image paths "
                    "and replace_existing_slides=true"
                )
            return
        if ordered_request is not None and action in {
            "slide.delete",
            "shape.delete",
            "slide.create",
            "shape.insert_image",
        }:
            expected = state.next_ordered_image_slide_action()
            if (
                expected is None
                or expected["action"] != action
                or expected["arguments"] != arguments
            ):
                raise ValueError(
                    f"ordered image-slide action must match the next instruction-derived plan step: {expected!r}"
                )
            return
        if action == "audio.insert":
            audio_path = requested_audio_path(state.instruction)
            if audio_path is not None:
                if not requests_presentation_audio_insertion(state.instruction):
                    raise ValueError(
                        "audio.insert requires explicit presentation audio insertion intent"
                    )
                if arguments.get("path") != audio_path:
                    raise ValueError(
                        f"audio.insert path must be {audio_path!r}, derived from the requested Desktop file"
                    )
            return
        if action == "user.ensure_account":
            spec = requested_os_account(state.instruction)
            if spec is not None:
                for key, expected in spec.items():
                    if arguments.get(key) != expected:
                        raise ValueError(
                            f"user.ensure_account {key} must be {expected!r}, derived from the instruction"
                        )
            return
        title_update_request = requested_slide_title_update(state.instruction)
        if title_update_request is not None and action in {
            "presentation.inspect",
            "shape.write_text",
            "shape.format_text",
        }:
            expected = state.next_slide_title_update_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and (state.slide_title_update_plan() is not None)
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"slide title update must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        title_format_request = requested_slide_title_formatting(state.instruction)
        if title_format_request is not None and action in {
            "presentation.inspect",
            "shape.format_text",
        }:
            expected = state.next_slide_title_format_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and (state.slide_title_format_plan() is not None)
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"slide title formatting must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        sized_image_request = requested_sized_slide_image(state.instruction)
        if sized_image_request is not None and action in {
            "presentation.inspect",
            "shape.insert_image",
        }:
            expected = state.next_sized_slide_image_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and (state.sized_slide_image_plan() is not None)
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"sized slide image insertion must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        table_row_request = requested_table_row_replacement(state.instruction)
        if table_row_request is not None and action in {
            "presentation.inspect",
            "table.write",
        }:
            expected = state.next_table_row_replacement_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and (state.table_row_replacement_plan() is not None)
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"table row replacement must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        named_table_request = requested_named_slide_table(state.instruction)
        if named_table_request is not None and action in {
            "presentation.inspect",
            "shape.delete",
            "table.create",
        }:
            expected = state.next_named_slide_table_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and (state.named_slide_table_plan() is not None)
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"named slide table workflow must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        content_format_request = requested_slide_content_formatting(state.instruction)
        if content_format_request is not None and action in {
            "presentation.inspect",
            "shape.format_text",
            "slide.set_background",
        }:
            expected = state.next_slide_content_format_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and state.slide_content_format_mutations_satisfied()
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"slide content formatting must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        if action == "slide.set_background":
            color = requested_slide_background_color(state.instruction)
            if color is not None and str(arguments.get("color", "")).upper() != color:
                raise ValueError(
                    f"slide.set_background color must be {color!r}, derived from the instruction"
                )
            expected = state.all_slide_background_arguments()
            if expected is not None and arguments != expected:
                raise ValueError(
                    f"slide.set_background must target every slide with the exact instruction-derived arguments {expected!r}"
                )
            return
        role_format_request = requested_slide_role_text_formatting(state.instruction)
        if role_format_request is not None and action in {
            "presentation.inspect",
            "shape.format_text",
            "table.format_text",
        }:
            expected = state.next_slide_role_text_format_action()
            if (
                action == "presentation.inspect"
                and expected is None
                and state.slide_role_text_format_mutations_satisfied()
            ):
                return
            if (
                expected is None
                or action != expected["action"]
                or arguments != expected["arguments"]
            ):
                raise ValueError(
                    f"slide role text formatting must match the next instruction- and presentation-observation-derived step: {expected!r}"
                )
            return
        if action in {"presentation.inspect", "shape.set_geometry"}:
            step = state.next_title_edge_position_action()
            if (
                requested_title_edge_position(state.instruction) is not None
                and step is not None
                and (action != step["action"] or arguments != step["arguments"])
            ):
                raise ValueError(
                    f"title-edge positioning must match the next instruction- and presentation-observation-derived step: {step!r}"
                )
            if requested_title_edge_position(state.instruction) is not None:
                return
        if action in {"presentation.inspect", "shape.set_geometry"}:
            step = state.next_image_edge_position_action()
            if (
                requested_image_edge_position(state.instruction) is not None
                and step is not None
                and (action != step["action"] or arguments != step["arguments"])
            ):
                raise ValueError(
                    f"image-edge positioning must match the next instruction- and presentation-observation-derived step: {step!r}"
                )
            if requested_image_edge_position(state.instruction) is not None:
                return
        if action in {"presentation.inspect", "shape.set_geometry"}:
            step = state.next_table_edge_position_action()
            if (
                requested_table_edge_position(state.instruction) is not None
                and step is not None
                and (action != step["action"] or arguments != step["arguments"])
            ):
                raise ValueError(
                    f"table-edge positioning must match the next instruction- and presentation-observation-derived step: {step!r}"
                )
            if requested_table_edge_position(state.instruction) is not None:
                return
        cleanup_request = requested_title_range_personal_info_cleanup(state.instruction)
        if cleanup_request is not None and action in {
            "presentation.inspect",
            "shape.format_text",
            "shape.delete",
        }:
            step = state.next_title_range_personal_info_cleanup_action()
            if (
                action == "presentation.inspect"
                and step is None
                and (state.title_range_personal_info_cleanup_plan() is not None)
            ):
                return
            if (
                step is None
                or action != step["action"]
                or arguments != step["arguments"]
            ):
                raise ValueError(
                    f"title formatting and personal-info cleanup must match the next instruction- and observation-derived step: {step!r}"
                )
            return
        if (
            action == "shape.format_text"
            and requested_matching_indent_without_bullet(state.instruction) is not None
        ):
            spec = state.matching_indent_spec()
            if spec is None:
                raise ValueError(
                    "inspect the target slide and identify the target and reference paragraphs before formatting"
                )
            expected = {
                key: spec[key]
                for key in (
                    "slide",
                    "selector",
                    "match_text",
                    "bullet",
                    "left_margin",
                    "first_line_indent",
                )
            }
            if arguments != expected:
                raise ValueError(
                    f"shape.format_text must apply only the inspected reference indentation and no-bullet state to the exact target paragraph: {expected!r}"
                )
            return
        if action == "shape.format_text":
            strike_requested = bool(
                re.search("(?i)\\bstrike(?:-?through)?\\b", state.instruction)
            )
            line_indices = requested_text_line_indices(state.instruction)
            if strike_requested and arguments.get("strike") is not True:
                raise ValueError(
                    "shape.format_text must set strike=true for a strike-through request"
                )
            if line_indices and arguments.get("lines") != line_indices:
                raise ValueError(
                    f"shape.format_text lines must be {line_indices}, derived from the requested lines"
                )
            if strike_requested:
                unrelated = {
                    "color",
                    "font_size",
                    "font_name",
                    "bold",
                    "italic",
                    "underline",
                    "bullet",
                    "alignment",
                    "match_text",
                }.intersection(arguments)
                if unrelated:
                    raise ValueError(
                        f"shape.format_text must not change unrelated formatting for a strike-only request: {sorted(unrelated)}"
                    )
            if line_indices:
                shape = state.inspected_presentation_shape(
                    int(arguments.get("slide", -1)), arguments.get("selector", {})
                )
                if shape is not None and len(shape.get("lines", [])) <= max(
                    line_indices
                ):
                    raise ValueError(
                        "the selected shape does not contain all requested line indices; select the multiline content shape instead of a title"
                    )
            return
        if action == "shape.fit_to_slide":
            contradiction = impress_cover_semantics.validate_fit_arguments(
                state, action, arguments
            )
            if contradiction is not None:
                raise ValueError(contradiction)
            return
        if action == "slide.duplicate":
            spec = state.next_slide_duplicate_spec()
            if spec is not None:
                for key in ("slide", "index"):
                    if arguments.get(key) != spec[key]:
                        raise ValueError(
                            f"slide.duplicate {key} must be {spec[key]} for ordered copy {spec['sequence']} of {spec['required']} derived from the initial slide count"
                        )
            return
        if action == "table.reorder_columns":
            spec = state.reorder_table_spec()
            if spec is not None:
                for key in ("sheet", "range", "headers"):
                    if arguments.get(key) != spec[key]:
                        raise ValueError(
                            f"table.reorder_columns {key} must be {spec[key]!r}, derived from the requested order and nonblank observed table header"
                        )
            return
        if calc_semantics.validate_sort_arguments(state, action, arguments):
            return
        if action == "workbook.export":
            spec = state.requested_calc_export_spec()
            if spec is not None and any(
                (arguments.get(key) != value for key, value in spec.items())
            ):
                raise ValueError(
                    f"workbook.export must use the required format, output basename, directory, and sheet derived from workbook.inspect and the instruction: {spec!r}"
                )
            return
        if action == "chart.create":
            used_range = state.latest_workbook_used_range()
            used_geometry = (
                a1_geometry(used_range[1]) if used_range is not None else None
            )
            geometry = (
                (
                    used_geometry[0],
                    used_geometry[2],
                    used_geometry[1],
                    used_geometry[3],
                    column_number(used_geometry[2])
                    - column_number(used_geometry[0])
                    + 1,
                )
                if used_geometry is not None
                else state.source_read_geometry()
            )
            if geometry is not None:
                start_column, end_column, _start_row, end_row, _width = geometry
                min_column = column_number(start_column)
                max_column = column_number(end_column)
                max_row = end_row + len(requested_row_labels(state.instruction))
                for cell_range in arguments.get("source_ranges", []):
                    parsed = a1_geometry(str(cell_range))
                    if parsed is None:
                        raise ValueError(f"invalid chart source range: {cell_range}")
                    (
                        range_start_column,
                        range_start_row,
                        range_end_column,
                        range_end_row,
                    ) = parsed
                    if (
                        column_number(range_start_column) < min_column
                        or column_number(range_end_column) > max_column
                        or range_start_row < 1
                        or (range_end_row > max_row)
                    ):
                        raise ValueError(
                            f"chart source range {cell_range} is outside the observed/created sheet bounds {start_column}1:{end_column}{max_row}"
                        )
            spec = state.next_chart_spec()
            if spec is not None:
                if (
                    str(arguments.get("title", "")).casefold()
                    != spec["label"].casefold()
                ):
                    raise ValueError(
                        f"chart {spec['index'] + 1} title must exactly match its requested row header {spec['label']!r}"
                    )
                actual_type = str(arguments.get("type", ""))
                if actual_type not in (
                    {"column", "bar"} if spec["type"] == "column" else {spec["type"]}
                ):
                    raise ValueError(
                        f"chart {spec['index'] + 1} type must be {spec['type']!r} for the requested chart"
                    )
                if arguments.get("source_ranges") != spec["source_ranges"]:
                    raise ValueError(
                        f"chart {spec['index'] + 1} must use the header and requested output row ranges {spec['source_ranges']}; this preserves labels and requested category omissions"
                    )
            axis_spec = state.axis_chart_spec()
            if axis_spec is not None:
                for key in (
                    "sheet",
                    "source_ranges",
                    "type",
                    "data_row_source",
                    "column_headers",
                    "row_headers",
                ):
                    if arguments.get(key) != axis_spec[key]:
                        raise ValueError(
                            f"chart.create {key} must be {axis_spec[key]!r}, derived from the observed headers {axis_spec['x_header']!r}/{axis_spec['y_header']!r} and the requested X/Y axes"
                        )
            new_sheet_spec = state.new_sheet_chart_spec()
            if new_sheet_spec is not None:
                for key in (
                    "sheet",
                    "source_sheet",
                    "name",
                    "title",
                    "source_ranges",
                    "type",
                    "data_row_source",
                    "column_headers",
                    "row_headers",
                ):
                    if arguments.get(key) != new_sheet_spec[key]:
                        raise ValueError(
                            f"chart.create {key} must be {new_sheet_spec[key]!r}, derived from the requested new chart sheet and the observed source table"
                        )
            return
        if action == "range.format":
            spec = state.decimal_separator_spec()
            if spec is not None:
                expected = {
                    "sheet": spec["sheet"],
                    "range": spec["range"],
                    "format": {
                        "number_format": spec["number_format"],
                        "locale": spec["locale"],
                    },
                }
                if arguments != expected:
                    raise ValueError(
                        f"range.format must preserve the observed decimal precision and use the requested comma separator: {expected!r}"
                    )
            return
        if action != "range.write" or not requests_appended_named_rows(
            state.instruction
        ):
            return
        end_row = state.source_read_end_row()
        target = str(arguments.get("range", ""))
        start_match = re.match("[A-Za-z]+(\\d+)", target)
        if (
            end_row is not None
            and start_match
            and (int(start_match.group(1)) <= end_row)
        ):
            raise ValueError(
                f"append target {target} overlaps source data through row {end_row}; start at row {end_row + 1} or later"
            )
        labels = requested_row_labels(state.instruction)
        written = state.written_row_labels()
        next_label = next(
            (label for label in labels if label.casefold() not in written), None
        )
        values = arguments.get("values")
        row = values[0] if isinstance(values, list) and len(values) == 1 else None
        if next_label is None or not isinstance(row, list):
            return
        first_value = row[0].get("value") if row and isinstance(row[0], dict) else None
        if (
            not isinstance(first_value, str)
            or first_value.casefold() != next_label.casefold()
        ):
            raise ValueError(
                f"the first cell must be the current row label {next_label!r}"
            )
        if next_label.casefold() == "total" and any(
            (
                not isinstance(cell, dict) or cell.get("kind") != "formula"
                for cell in row[1:]
            )
        ):
            raise ValueError(
                "the Total row data cells must use formulas, not precomputed constants"
            )
        geometry = state.source_read_geometry()
        if next_label.casefold() == "total" and geometry is not None:
            start_column, end_column, start_row, source_end_row, _width = geometry
            expected_formulas = [
                f"=SUM({column}{start_row + 1}:{column}{source_end_row})"
                for column in (
                    column_label(number)
                    for number in range(
                        column_number(start_column) + 1, column_number(end_column) + 1
                    )
                )
            ]
            actual_formulas = [
                re.sub("[\\s$]", "", str(cell.get("value", ""))).upper()
                for cell in row[1:]
            ]
            if actual_formulas != [formula.upper() for formula in expected_formulas]:
                raise ValueError(
                    f"the Total row formulas must sum every observed source row in each respective column; expected {expected_formulas}"
                )
        if (
            next_label.casefold() == "growth"
            and re.search("(?i)month-on-month|month on month", state.instruction)
            and (
                len(row) < 2
                or not isinstance(row[1], dict)
                or row[1].get("kind") != "blank"
                or any(
                    (
                        not isinstance(cell, dict) or cell.get("kind") != "formula"
                        for cell in row[2:]
                    )
                )
            )
        ):
            raise ValueError(
                "the Growth row must use a blank typed cell for omitted Jan and formula cells for later months"
            )
        if (
            next_label.casefold() == "growth"
            and geometry is not None
            and re.search("(?i)month-on-month|month on month", state.instruction)
        ):
            start_column, end_column, _start_row, source_end_row, _width = geometry
            total_row = source_end_row + 1
            expected_pairs = [
                (column_label(number - 1), column_label(number))
                for number in range(
                    column_number(start_column) + 2, column_number(end_column) + 1
                )
            ]
            for cell, (previous_column, current_column) in zip(
                row[2:], expected_pairs, strict=True
            ):
                formula = str(cell.get("value", ""))
                current_cell = f"{current_column}{total_row}"
                previous_cell = f"{previous_column}{total_row}"
                if not valid_month_growth_formula(formula, current_cell, previous_cell):
                    raise ValueError(
                        f"each Growth formula must compare the current Total cell with the immediately previous Total cell; for example use =({current_cell}-{previous_cell})/{previous_cell} or ={current_cell}/{previous_cell}-1; keep the percentage as a decimal ratio and do not multiply by 100"
                    )
