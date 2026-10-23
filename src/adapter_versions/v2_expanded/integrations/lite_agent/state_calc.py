"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state_model import ExecutionEvent
from urllib.parse import unquote, urlparse


from . import impress_cover_semantics
from .adapter_results import (
    a1_geometry,
    adapter_context_hint as adapter_context_hint,
    column_label,
    column_number,
    compact_adapter_body as compact_adapter_body,
)
from .completion_policy import (
    action_is_read_only as is_read_only,
    action_is_save as is_save,
    canonical_action_request,
    completion_claim_contradictions as completion_claim_contradictions,
    effective_canonical_action,
    required_mutation_actions as collect_required_mutation_actions,
)


from .instruction_semantics import (
    MONTH_TOKENS,
    requested_files,
    requested_audio_path,
    requested_ordered_image_slides,
    requested_sheet_names,
    requested_annual_percentage_change_summary,
    requested_monthly_column_totals_summary,
    requested_scaled_number_displays,
    requested_labeled_concatenation,
    requested_merged_text_regions,
    requested_pivot_blank_rows,
    requested_sheet_copy_lifecycle,
    requested_pivot_count,
    requested_row_labels,
    requested_period_rate_column,
    calc_formula_sheet_reference,
    normalized_calc_formula,
    requested_chart_types,
    requested_chart_title,
    requested_content_textbox_insert,
    requested_matching_indent_without_bullet,
    requested_calc_export_format,
    requests_same_basename_export,
    instruction_required_actions,
    requested_column_order,
)
from .observation_fields import (
    display_rows,
    first_display_row,
    mapping_field,
    matrix_field,
)


class CalcStateMixin:
    def required_mutation_actions(self) -> set[str]:
        return collect_required_mutation_actions(
            self,
            instruction_actions=instruction_required_actions,
            is_read_only_action=is_read_only,
            is_save_action=is_save,
        )

    def save_target_satisfied(self, action: str | None = None) -> bool:
        """Return true only when a current successful save proves the requested target."""
        files = [filename.lower() for filename in self.requested_save_files()]
        desktop_required = "desktop" in self.instruction.lower()
        for event in reversed(self.events):
            if not event.executed:
                continue
            if event.proposed.get("kind") == "gui":
                return False
            if event.proposed.get("kind") != "adapter":
                continue
            event_action = effective_canonical_action(event, self.domain)[1]
            if is_read_only(event_action):
                continue
            if not is_save(event_action):
                return False
            if action is not None:
                requested_action = canonical_action_request(self.domain, action, {})[1]
                if event_action != requested_action:
                    continue
            result = json.dumps(event.result, ensure_ascii=False, default=str).lower()
            if files and not all(filename in result for filename in files):
                continue
            if desktop_required and "/desktop/" not in result:
                continue
            return True
        return False

    def requested_calc_export_url(self) -> str | None:
        spec = self.requested_calc_export_spec()
        return str(spec["url"]) if spec is not None else None

    def requested_calc_export_spec(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc":
            return None
        format_name = requested_calc_export_format(self.instruction)
        if format_name is None or not requests_same_basename_export(self.instruction):
            return None
        for event in reversed(self.successful_action_events("workbook.inspect")):
            body = event.result if isinstance(event.result, dict) else {}
            result = body.get("result") if isinstance(body.get("result"), dict) else {}
            title = result.get("title")
            source_url = result.get("url")
            active_sheet = result.get("active_sheet")
            if not isinstance(title, str) or not title.strip():
                continue
            if re.search(r"(?i)\bhome\s+directory\b", self.instruction):
                output_path = (
                    Path("/home/user") / f"{Path(title.strip()).stem}.{format_name}"
                )
            elif isinstance(source_url, str) and source_url.startswith("file:"):
                output_path = Path(unquote(urlparse(source_url).path)).with_suffix(
                    f".{format_name}"
                )
            else:
                output_path = (
                    Path("/home/user") / f"{Path(title.strip()).stem}.{format_name}"
                )
            spec: dict[str, Any] = {
                "format": format_name,
                "url": output_path.as_uri(),
            }
            if format_name == "csv" and isinstance(active_sheet, str) and active_sheet:
                spec["sheet"] = active_sheet
            return spec
        return None

    def sheet_create_target_satisfied(self) -> bool:
        names = [name.lower() for name in requested_sheet_names(self.instruction)]
        if not names:
            return False
        for event in reversed(self.successful_adapter_events()):
            action = str(event.proposed.get("action", ""))
            if action != "sheet.create":
                continue
            result = json.dumps(event.result, ensure_ascii=False, default=str).lower()
            return all(name in result for name in names)
        return False

    def merged_text_region_specs(self) -> list[dict[str, str]]:
        if self.domain != "libreoffice_calc":
            return []
        return requested_merged_text_regions(self.instruction)

    def next_merged_text_action(self) -> dict[str, Any] | None:
        for index, spec in enumerate(self.merged_text_region_specs()):
            merge_arguments = {
                "sheet": spec["sheet"],
                "range": spec["range"],
                "merge": True,
            }
            merge_events = [
                event
                for event in self.successful_action_events("range.merge")
                if event.proposed.get("arguments") == merge_arguments
            ]
            if not merge_events:
                return {
                    "index": index,
                    "count": len(self.merged_text_region_specs()),
                    "action": "range.merge",
                    "arguments": merge_arguments,
                }
            write_arguments = {
                "sheet": spec["sheet"],
                "range": spec["anchor"],
                "values": [[{"kind": "string", "value": spec["text"]}]],
            }
            if not any(
                event.step > merge_events[-1].step
                and event.proposed.get("arguments") == write_arguments
                for event in self.successful_action_events("range.write")
            ):
                return {
                    "index": index,
                    "count": len(self.merged_text_region_specs()),
                    "action": "range.write",
                    "arguments": write_arguments,
                }
            requested_format = spec.get("format")
            if isinstance(requested_format, dict) and requested_format:
                format_arguments = {
                    "sheet": spec["sheet"],
                    "range": spec["range"],
                    "format": requested_format,
                }
                if not any(
                    event.step > merge_events[-1].step
                    and event.proposed.get("arguments") == format_arguments
                    for event in self.successful_action_events("range.format")
                ):
                    return {
                        "index": index,
                        "count": len(self.merged_text_region_specs()),
                        "action": "range.format",
                        "arguments": format_arguments,
                    }
        return None

    def merged_text_mutations_satisfied(self) -> bool:
        return (
            bool(self.merged_text_region_specs())
            and self.next_merged_text_action() is None
        )

    def merged_text_readback_range(self) -> str | None:
        specs = self.merged_text_region_specs()
        geometries = [a1_geometry(spec["range"]) for spec in specs]
        if not specs or any(geometry is None for geometry in geometries):
            return None
        valid = [geometry for geometry in geometries if geometry is not None]
        start_column = min(column_number(geometry[0]) for geometry in valid)
        start_row = min(geometry[1] for geometry in valid)
        end_column = max(column_number(geometry[2]) for geometry in valid)
        end_row = max(geometry[3] for geometry in valid)
        return (
            f"{column_label(start_column)}{start_row}:"
            f"{column_label(end_column)}{end_row}"
        )

    def merged_text_readback_satisfied(self) -> bool:
        specs = self.merged_text_region_specs()
        readback_range = self.merged_text_readback_range()
        mutations = [
            *self.successful_action_events("range.merge"),
            *self.successful_action_events("range.write"),
            *self.successful_action_events("range.format"),
        ]
        if (
            not specs
            or readback_range is None
            or not self.merged_text_mutations_satisfied()
        ):
            return False
        last_mutation_step = max(event.step for event in mutations)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation_step
        ]
        if not saves:
            return False
        for event in reversed(self.successful_action_events("range.read")):
            arguments = event.proposed.get("arguments", {})
            actual_range = str(arguments.get("range", ""))
            actual_geometry = a1_geometry(actual_range)
            expected_geometry = a1_geometry(readback_range)
            if (
                event.step <= saves[-1].step
                or arguments.get("sheet") != specs[0]["sheet"]
                or actual_geometry is None
                or expected_geometry is None
                or column_number(actual_geometry[0])
                > column_number(expected_geometry[0])
                or actual_geometry[1] > expected_geometry[1]
                or column_number(actual_geometry[2])
                < column_number(expected_geometry[2])
                or actual_geometry[3] < expected_geometry[3]
            ):
                continue
            rows = display_rows(event.result)
            styles = matrix_field(event.result, "styles")
            style_cells = mapping_field(event.result, "style_cells")
            if not rows:
                return False
            start_column, start_row, _end_column, _end_row = actual_geometry
            first_column = column_number(start_column)
            for spec in specs:
                anchor = a1_geometry(spec["anchor"])
                if anchor is None:
                    return False
                column_offset = column_number(anchor[0]) - first_column
                row_offset = anchor[1] - start_row
                if (
                    row_offset < 0
                    or row_offset >= len(rows)
                    or column_offset < 0
                    or column_offset >= len(rows[row_offset])
                    or rows[row_offset][column_offset] != spec["text"]
                ):
                    return False
                requested_format = spec.get("format")
                if isinstance(requested_format, dict) and requested_format:
                    observed_style = None
                    if (
                        row_offset < len(styles)
                        and column_offset < len(styles[row_offset])
                        and isinstance(styles[row_offset][column_offset], dict)
                    ):
                        observed_style = styles[row_offset][column_offset]
                    if observed_style is None:
                        observed_style = style_cells.get(spec["anchor"])
                    if not isinstance(observed_style, dict):
                        return False
                    for key, expected in requested_format.items():
                        observed = observed_style.get(key)
                        if key in {"background_color", "font_color"}:
                            if str(observed).casefold() != str(expected).casefold():
                                return False
                        elif observed != expected:
                            return False
            return True
        return False

    def annual_percentage_change_request(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc":
            return None
        return requested_annual_percentage_change_summary(self.instruction)

    def annual_percentage_change_source_read(self) -> ExecutionEvent | None:
        request = self.annual_percentage_change_request()
        used_range = self.latest_workbook_used_range()
        if request is None or used_range is None:
            return None
        source_sheet, source_range = used_range
        if source_sheet == request["target_sheet"]:
            return None
        return next(
            (
                event
                for event in self.successful_action_events("range.read")
                if event.proposed.get("arguments")
                == {"sheet": source_sheet, "range": source_range}
            ),
            None,
        )

    def annual_percentage_change_plan(self) -> dict[str, Any] | None:
        request = self.annual_percentage_change_request()
        source_event = self.annual_percentage_change_source_read()
        if request is None or source_event is None:
            return None
        source_arguments = source_event.proposed.get("arguments", {})
        source_sheet = str(source_arguments.get("sheet", ""))
        source_range = str(source_arguments.get("range", ""))
        geometry = a1_geometry(source_range)
        rows = display_rows(source_event.result)
        if geometry is None or not rows:
            return None

        def normalized_header(value: Any) -> str:
            return re.sub(r"\s+", " ", str(value).strip()).casefold()

        requested_headers = [
            normalized_header(value) for value in request["source_headers"]
        ]
        year_header = normalized_header(request["output_headers"][0])
        header_index = None
        year_column_index = None
        source_column_indices: list[int] = []
        for row_index, row in enumerate(rows):
            normalized = [normalized_header(value) for value in row]
            if year_header not in normalized or any(
                header not in normalized for header in requested_headers
            ):
                continue
            header_index = row_index
            year_column_index = normalized.index(year_header)
            source_column_indices = [
                normalized.index(header) for header in requested_headers
            ]
            break
        if header_index is None or year_column_index is None:
            return None

        row_by_year: dict[int, int] = {}
        for row_offset, row in enumerate(
            rows[header_index + 1 :], start=header_index + 1
        ):
            if year_column_index >= len(row):
                continue
            match = re.fullmatch(r"\s*(\d{4})(?:\.0+)?\s*", str(row[year_column_index]))
            if match:
                row_by_year[int(match.group(1))] = geometry[1] + row_offset
        years = list(range(request["start_year"], request["end_year"] + 1))
        if any(
            year not in row_by_year or year - 1 not in row_by_year for year in years
        ):
            return None

        source_start_column = column_number(geometry[0])
        source_columns = [
            column_label(source_start_column + index) for index in source_column_indices
        ]
        sheet_reference = calc_formula_sheet_reference(source_sheet)
        values: list[list[dict[str, Any]]] = [
            [
                {"kind": "string", "value": header}
                for header in request["output_headers"]
            ]
        ]
        formulas: list[list[str]] = []
        for year in years:
            formula_row = [
                f"={sheet_reference}.{column}{row_by_year[year]}/"
                f"{sheet_reference}.{column}{row_by_year[year - 1]}-1"
                for column in source_columns
            ]
            formulas.append(formula_row)
            values.append(
                [
                    {"kind": "number", "value": year},
                    *[{"kind": "formula", "value": formula} for formula in formula_row],
                ]
            )

        last_column = column_label(len(request["output_headers"]))
        last_row = len(years) + 1
        write_arguments = {
            "sheet": request["target_sheet"],
            "range": f"A1:{last_column}{last_row}",
            "values": values,
        }
        format_arguments = {
            "sheet": request["target_sheet"],
            "range": f"B2:{last_column}{last_row}",
            "format": {"number_format": "0.00%"},
        }
        return {
            **request,
            "source_sheet": source_sheet,
            "source_range": source_range,
            "source_columns": source_columns,
            "years": years,
            "formulas": formulas,
            "target_range": write_arguments["range"],
            "write_arguments": write_arguments,
            "format_arguments": format_arguments,
        }

    def annual_percentage_change_target_created(self) -> bool:
        request = self.annual_percentage_change_request()
        return bool(
            request
            and any(
                event.proposed.get("arguments") == {"name": request["target_sheet"]}
                for event in self.successful_action_events("sheet.create")
            )
        )

    def annual_percentage_change_mutations_satisfied(self) -> bool:
        plan = self.annual_percentage_change_plan()
        if plan is None or not self.annual_percentage_change_target_created():
            return False
        return bool(
            any(
                event.proposed.get("arguments") == plan["write_arguments"]
                for event in self.successful_action_events("range.write")
            )
            and any(
                event.proposed.get("arguments") == plan["format_arguments"]
                for event in self.successful_action_events("range.format")
            )
        )

    def next_annual_percentage_change_action(self) -> dict[str, Any] | None:
        request = self.annual_percentage_change_request()
        if request is None:
            return None
        if not self.successful_action_events("workbook.inspect"):
            return {"action": "workbook.inspect", "arguments": {}}
        used_range = self.latest_workbook_used_range()
        if self.annual_percentage_change_source_read() is None:
            if used_range is None:
                return None
            return {
                "action": "range.read",
                "arguments": {"sheet": used_range[0], "range": used_range[1]},
            }
        plan = self.annual_percentage_change_plan()
        if plan is None:
            return None
        if not self.annual_percentage_change_target_created():
            return {
                "action": "sheet.create",
                "arguments": {"name": plan["target_sheet"]},
            }
        for action, arguments in (
            ("range.write", plan["write_arguments"]),
            ("range.format", plan["format_arguments"]),
        ):
            if not any(
                event.proposed.get("arguments") == arguments
                for event in self.successful_action_events(action)
            ):
                return {"action": action, "arguments": arguments}
        mutations = [
            *self.successful_action_events("sheet.create"),
            *self.successful_action_events("range.write"),
            *self.successful_action_events("range.format"),
        ]
        last_mutation_step = max(event.step for event in mutations)
        saves = [
            event
            for event in self.successful_action_events("workbook.save")
            if event.step > last_mutation_step
        ]
        if not saves:
            return {"action": "workbook.save", "arguments": {}}
        if not any(
            event.step > saves[-1].step
            and event.proposed.get("arguments")
            == {"sheet": plan["target_sheet"], "range": plan["target_range"]}
            for event in self.successful_action_events("range.read")
        ):
            return {
                "action": "range.read",
                "arguments": {
                    "sheet": plan["target_sheet"],
                    "range": plan["target_range"],
                },
            }
        return None

    def annual_percentage_change_readback_satisfied(self) -> bool:
        plan = self.annual_percentage_change_plan()
        if plan is None or not self.annual_percentage_change_mutations_satisfied():
            return False
        saves = self.successful_action_events("workbook.save")
        if not saves:
            return False
        for event in reversed(self.successful_action_events("range.read")):
            if event.step <= saves[-1].step or event.proposed.get("arguments") != {
                "sheet": plan["target_sheet"],
                "range": plan["target_range"],
            }:
                continue
            rows = display_rows(event.result)
            formulas = matrix_field(event.result, "formulas")
            format_ids = matrix_field(event.result, "number_format_ids")
            if len(rows) != len(plan["years"]) + 1 or len(formulas) != len(rows):
                return False
            if rows[0] != plan["output_headers"]:
                return False
            if [row[0] for row in rows[1:]] != [str(year) for year in plan["years"]]:
                return False
            for actual, expected in zip(formulas[1:], plan["formulas"], strict=True):
                if [normalized_calc_formula(value) for value in actual[1:]] != [
                    normalized_calc_formula(value) for value in expected
                ]:
                    return False
            data_format_ids = [
                value
                for row in format_ids[1:]
                for value in row[1:]
                if isinstance(value, int) and not isinstance(value, bool)
            ]
            display_has_percent = all(
                value.strip().endswith("%") for row in rows[1:] for value in row[1:]
            )
            return (
                bool(data_format_ids)
                and all(value != 0 for value in data_format_ids)
                and display_has_percent
            )
        return False

    def monthly_column_totals_request(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc":
            return None
        return requested_monthly_column_totals_summary(self.instruction)

    def monthly_column_totals_source_read(self) -> ExecutionEvent | None:
        request = self.monthly_column_totals_request()
        used_range = self.latest_workbook_used_range()
        if request is None or used_range is None:
            return None
        source_sheet, source_range = used_range
        if source_sheet == request["target_sheet"]:
            return None
        return next(
            (
                event
                for event in self.successful_action_events("range.read")
                if event.proposed.get("arguments")
                == {"sheet": source_sheet, "range": source_range}
            ),
            None,
        )

    def monthly_column_totals_plan(self) -> dict[str, Any] | None:
        request = self.monthly_column_totals_request()
        source_event = self.monthly_column_totals_source_read()
        if request is None or source_event is None:
            return None
        arguments = source_event.proposed.get("arguments", {})
        source_sheet = str(arguments.get("sheet", ""))
        source_range = str(arguments.get("range", ""))
        geometry = a1_geometry(source_range)
        rows = display_rows(source_event.result)
        if geometry is None or not rows:
            return None
        header_index = None
        month_columns: list[tuple[str, int]] = []
        for row_index, row in enumerate(rows):
            candidates = [
                (str(value).strip(), column_index)
                for column_index, value in enumerate(row)
                if str(value).strip().casefold() in MONTH_TOKENS
            ]
            if len(candidates) >= 2:
                header_index = row_index
                month_columns = candidates
                break
        if header_index is None or not month_columns:
            return None
        data_start_row = geometry[1] + header_index + 1
        data_end_row = geometry[3]
        if data_start_row > data_end_row:
            return None
        source_start_column = column_number(geometry[0])
        sheet_reference = calc_formula_sheet_reference(source_sheet)
        formulas = [
            f"=SUM({sheet_reference}.{column_label(source_start_column + column_index)}"
            f"{data_start_row}:{column_label(source_start_column + column_index)}{data_end_row})"
            for _month, column_index in month_columns
        ]
        values = [
            [
                {"kind": "string", "value": request["output_headers"][0]},
                {"kind": "string", "value": request["output_headers"][1]},
            ],
            *[
                [
                    {"kind": "string", "value": month},
                    {"kind": "formula", "value": formula},
                ]
                for (month, _column_index), formula in zip(
                    month_columns, formulas, strict=True
                )
            ],
        ]
        target_range = f"A1:B{len(values)}"
        return {
            **request,
            "source_sheet": source_sheet,
            "source_range": source_range,
            "months": [month for month, _column_index in month_columns],
            "formulas": formulas,
            "target_range": target_range,
            "write_arguments": {
                "sheet": request["target_sheet"],
                "range": target_range,
                "values": values,
            },
        }

    def monthly_column_totals_target_created(self) -> bool:
        request = self.monthly_column_totals_request()
        return bool(
            request
            and any(
                event.proposed.get("arguments") == {"name": request["target_sheet"]}
                for event in self.successful_action_events("sheet.create")
            )
        )

    def monthly_column_totals_mutations_satisfied(self) -> bool:
        plan = self.monthly_column_totals_plan()
        return bool(
            plan
            and self.monthly_column_totals_target_created()
            and any(
                event.proposed.get("arguments") == plan["write_arguments"]
                for event in self.successful_action_events("range.write")
            )
        )

    def next_monthly_column_totals_action(self) -> dict[str, Any] | None:
        request = self.monthly_column_totals_request()
        if request is None:
            return None
        if not self.successful_action_events("workbook.inspect"):
            return {"action": "workbook.inspect", "arguments": {}}
        used_range = self.latest_workbook_used_range()
        if self.monthly_column_totals_source_read() is None:
            if used_range is None:
                return None
            return {
                "action": "range.read",
                "arguments": {"sheet": used_range[0], "range": used_range[1]},
            }
        plan = self.monthly_column_totals_plan()
        if plan is None:
            return None
        if not self.monthly_column_totals_target_created():
            return {
                "action": "sheet.create",
                "arguments": {"name": plan["target_sheet"]},
            }
        if not any(
            event.proposed.get("arguments") == plan["write_arguments"]
            for event in self.successful_action_events("range.write")
        ):
            return {"action": "range.write", "arguments": plan["write_arguments"]}
        mutations = [
            *self.successful_action_events("sheet.create"),
            *self.successful_action_events("range.write"),
        ]
        last_mutation_step = max(event.step for event in mutations)
        saves = [
            event
            for event in self.successful_action_events("workbook.save")
            if event.step > last_mutation_step
        ]
        if not saves:
            return {"action": "workbook.save", "arguments": {}}
        read_arguments = {
            "sheet": plan["target_sheet"],
            "range": plan["target_range"],
        }
        if not any(
            event.step > saves[-1].step
            and event.proposed.get("arguments") == read_arguments
            for event in self.successful_action_events("range.read")
        ):
            return {"action": "range.read", "arguments": read_arguments}
        return None

    def monthly_column_totals_readback_satisfied(self) -> bool:
        plan = self.monthly_column_totals_plan()
        if plan is None or not self.monthly_column_totals_mutations_satisfied():
            return False
        saves = self.successful_action_events("workbook.save")
        if not saves:
            return False
        expected_rows = [
            plan["output_headers"],
            *[
                [month, formula]
                for month, formula in zip(plan["months"], plan["formulas"], strict=True)
            ],
        ]
        for event in reversed(self.successful_action_events("range.read")):
            if event.step <= saves[-1].step or event.proposed.get("arguments") != {
                "sheet": plan["target_sheet"],
                "range": plan["target_range"],
            }:
                continue
            rows = display_rows(event.result)
            formulas = matrix_field(event.result, "formulas")
            if len(rows) != len(expected_rows) or len(formulas) != len(expected_rows):
                return False
            if (
                rows[0] != plan["output_headers"]
                or [row[0] for row in rows[1:]] != plan["months"]
            ):
                return False
            return [normalized_calc_formula(row[1]) for row in formulas[1:]] == [
                normalized_calc_formula(formula) for formula in plan["formulas"]
            ]
        return False

    def scaled_number_display_request(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc":
            return None
        return requested_scaled_number_displays(self.instruction)

    def scaled_number_display_source_read(self) -> ExecutionEvent | None:
        request = self.scaled_number_display_request()
        used_range = self.latest_workbook_used_range()
        if request is None or used_range is None:
            return None
        sheet, cell_range = used_range
        return next(
            (
                event
                for event in self.successful_action_events("range.read")
                if event.proposed.get("arguments")
                == {"sheet": sheet, "range": cell_range}
            ),
            None,
        )

    def scaled_number_display_plan(self) -> dict[str, Any] | None:
        request = self.scaled_number_display_request()
        source_event = self.scaled_number_display_source_read()
        if request is None or source_event is None:
            return None
        arguments = source_event.proposed.get("arguments", {})
        sheet = str(arguments.get("sheet", ""))
        cell_range = str(arguments.get("range", ""))
        geometry = a1_geometry(cell_range)
        rows = display_rows(source_event.result)
        values = matrix_field(source_event.result, "values")
        kinds = matrix_field(source_event.result, "kinds")
        if geometry is None or not rows:
            return None
        source_header = str(request["source_header"]).strip().casefold()
        header_position = next(
            (
                (row_index, column_index)
                for row_index, row in enumerate(rows)
                for column_index, value in enumerate(row)
                if str(value).strip().casefold() == source_header
            ),
            None,
        )
        if header_position is None:
            return None
        header_row_offset, source_column_offset = header_position
        data_start_offset = header_row_offset + 1
        if data_start_offset >= len(rows):
            return None
        source_values: list[Any] = []
        for row_offset in range(data_start_offset, len(rows)):
            display_value = (
                rows[row_offset][source_column_offset]
                if source_column_offset < len(rows[row_offset])
                else ""
            )
            kind = (
                str(kinds[row_offset][source_column_offset])
                if row_offset < len(kinds)
                and source_column_offset < len(kinds[row_offset])
                else ""
            )
            if not str(display_value).strip():
                break
            if kind and kind not in {"number", "formula"}:
                return None
            raw_value = (
                values[row_offset][source_column_offset]
                if row_offset < len(values)
                and source_column_offset < len(values[row_offset])
                else display_value
            )
            try:
                Decimal(str(raw_value))
            except (InvalidOperation, TypeError, ValueError):
                return None
            source_values.append(raw_value)
        if not source_values:
            return None
        used_start_column = column_number(geometry[0])
        source_column = used_start_column + source_column_offset
        header_row = geometry[1] + header_row_offset
        first_data_row = header_row + 1
        last_data_row = first_data_row + len(source_values) - 1
        output_specs: list[dict[str, Any]] = []
        for output in request["outputs"]:
            destination_column = column_number(output["destination_column"])
            if destination_column == source_column:
                return None
            spec = {
                **output,
                "destination_column_number": destination_column,
                "arguments": {
                    "source_sheet": sheet,
                    "source_range": (
                        f"{column_label(source_column)}{first_data_row}:"
                        f"{column_label(source_column)}{last_data_row}"
                    ),
                    "destination_sheet": sheet,
                    "destination": f"{column_label(destination_column)}{first_data_row}",
                    "divisor": output["divisor"],
                    "decimal_places": output["decimal_places"],
                    "unit": output["unit"],
                    "separator": output["separator"],
                    "rounding_mode": output["rounding_mode"],
                    "preserve_format": False,
                },
            }
            output_specs.append(spec)
        minimum_column = min(
            column_number(geometry[0]),
            source_column,
            *(item["destination_column_number"] for item in output_specs),
        )
        maximum_column = max(
            column_number(geometry[2]),
            source_column,
            *(item["destination_column_number"] for item in output_specs),
        )
        read_range = (
            f"{column_label(minimum_column)}{geometry[1]}:"
            f"{column_label(maximum_column)}{max(geometry[3], last_data_row)}"
        )
        return {
            **request,
            "sheet": sheet,
            "source_column_number": source_column,
            "source_values": source_values,
            "first_data_row": first_data_row,
            "last_data_row": last_data_row,
            "outputs": output_specs,
            "read_range": read_range,
        }

    def scaled_number_display_mutation_events(self) -> list[ExecutionEvent]:
        return sorted(
            [
                *self.successful_action_events("range.copy"),
                *self.successful_action_events("range.set_scaled_display"),
            ],
            key=lambda event: event.step,
        )

    def scaled_number_display_mutations_satisfied(self) -> bool:
        request = self.scaled_number_display_request()
        if request is None:
            return False
        required = len(request["outputs"])
        return (
            len(self.successful_action_events("range.copy")) >= required
            and len(self.successful_action_events("range.set_scaled_display")) >= required
        )

    def next_scaled_number_display_action(self) -> dict[str, Any] | None:
        # Atomic copy and formatting arguments remain model-selected.
        return None

    def scaled_number_display_readback_satisfied(self) -> bool:
        events = self.scaled_number_display_mutation_events()
        if not events or not self.scaled_number_display_mutations_satisfied():
            return False
        last_mutation = max(events, key=lambda event: event.step)
        saves = [
            event
            for event in self.successful_action_events("workbook.save")
            if event.step > last_mutation.step
        ]
        if not saves:
            return False
        return any(
            event.step > saves[-1].step
            for event in self.successful_action_events("range.read")
        )

    def labeled_concatenation_request(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc":
            return None
        return requested_labeled_concatenation(self.instruction)

    def labeled_concatenation_source_read(self) -> ExecutionEvent | None:
        if self.labeled_concatenation_request() is None:
            return None
        used_range = self.latest_workbook_used_range()
        if used_range is None:
            return None
        sheet, cell_range = used_range
        return next(
            (
                event
                for event in self.successful_action_events("range.read")
                if event.proposed.get("arguments")
                == {"sheet": sheet, "range": cell_range}
            ),
            None,
        )

    def labeled_concatenation_plan(self) -> dict[str, Any] | None:
        request = self.labeled_concatenation_request()
        source_event = self.labeled_concatenation_source_read()
        used_range = self.latest_workbook_used_range()
        if request is None or source_event is None or used_range is None:
            return None
        sheet, observed_range = used_range
        geometry = a1_geometry(observed_range)
        display = display_rows(source_event.result)
        formulas = matrix_field(source_event.result, "formulas")
        if geometry is None or not display:
            return None
        source_start = column_number(request["source_start_column"])
        source_end = column_number(request["source_end_column"])
        observed_start = column_number(geometry[0])
        observed_end = column_number(geometry[2])
        source_row = int(request["source_row"])
        if not (
            observed_start <= source_start <= source_end <= observed_end
            and geometry[1] <= source_row <= geometry[3]
        ):
            return None
        header_row = geometry[1]
        header_offset = header_row - geometry[1]
        source_row_offset = source_row - geometry[1]
        headers = []
        for column in range(source_start, source_end + 1):
            offset = column - observed_start
            try:
                header = str(display[header_offset][offset]).strip()
            except IndexError:
                return None
            if not header:
                return None
            headers.append(header)
        fill_specs = []
        for label in request["fill_columns"]:
            column = column_number(label)
            offset = column - observed_start
            try:
                source_formula = str(formulas[source_row_offset][offset]).strip()
            except IndexError:
                return None
            if not source_formula.startswith("="):
                return None
            fill_specs.append(
                {
                    "sheet": sheet,
                    "range": f"{label}{source_row}:{label}{geometry[3]}",
                    "mode": "formula_pattern",
                    "source_rows": 1,
                    "only_blank": True,
                    "preserve_format": False,
                }
            )
        destination_column = observed_end + 1
        destination = f"{column_label(destination_column)}{header_row}"
        compose_arguments = {
            "source_sheet": sheet,
            "source_range": (
                f"{request['source_start_column']}{header_row}:"
                f"{request['source_end_column']}{geometry[3]}"
            ),
            "destination_sheet": sheet,
            "destination": destination,
            "header": request["header"],
            "include_headers": request["include_headers"],
            "decimal_places": request["decimal_places"],
            "field_separator": request["field_separator"],
            "label_separator": request["label_separator"],
        }
        read_range = (
            f"{geometry[0]}{geometry[1]}:"
            f"{column_label(destination_column)}{geometry[3]}"
        )
        return {
            **request,
            "sheet": sheet,
            "headers": headers,
            "first_row": header_row,
            "last_row": geometry[3],
            "fill_specs": fill_specs,
            "compose_arguments": compose_arguments,
            "read_range": read_range,
            "destination_column": destination_column,
        }

    def labeled_concatenation_mutation_events(self) -> list[ExecutionEvent]:
        plan = self.labeled_concatenation_plan()
        if plan is None:
            return []
        events = []
        for arguments in plan["fill_specs"]:
            event = next(
                (
                    item
                    for item in self.successful_action_events("range.fill_down")
                    if item.proposed.get("arguments") == arguments
                ),
                None,
            )
            if event is not None:
                events.append(event)
        compose = next(iter(self.successful_action_events("range.write")), None)
        if compose is not None:
            events.append(compose)
        return events

    def labeled_concatenation_mutations_satisfied(self) -> bool:
        plan = self.labeled_concatenation_plan()
        if plan is None:
            return False
        events = self.labeled_concatenation_mutation_events()
        return len(events) == len(plan["fill_specs"]) + 1

    def next_labeled_concatenation_action(self) -> dict[str, Any] | None:
        if self.labeled_concatenation_request() is None:
            return None
        if not self.successful_action_events("workbook.inspect"):
            return {"action": "workbook.inspect", "arguments": {}}
        used_range = self.latest_workbook_used_range()
        if self.labeled_concatenation_source_read() is None:
            if used_range is None:
                return None
            return {
                "action": "range.read",
                "arguments": {"sheet": used_range[0], "range": used_range[1]},
            }
        plan = self.labeled_concatenation_plan()
        if plan is None:
            return None
        completed_fill = {
            json.dumps(event.proposed.get("arguments", {}), sort_keys=True)
            for event in self.successful_action_events("range.fill_down")
        }
        for arguments in plan["fill_specs"]:
            if json.dumps(arguments, sort_keys=True) not in completed_fill:
                return {"action": "range.fill_down", "arguments": arguments}
        if not self.successful_action_events("range.write"):
            # The model chooses the destination range and composed values.
            return None
        mutations = self.labeled_concatenation_mutation_events()
        last_mutation = max(mutations, key=lambda event: event.step)
        saves = [
            event
            for event in self.successful_action_events("workbook.save")
            if event.step > last_mutation.step
        ]
        if not saves:
            return {"action": "workbook.save", "arguments": {}}
        read_arguments = {"sheet": plan["sheet"], "range": plan["read_range"]}
        if not any(
            event.step > saves[-1].step
            and event.proposed.get("arguments") == read_arguments
            for event in self.successful_action_events("range.read")
        ):
            return {"action": "range.read", "arguments": read_arguments}
        return None

    def labeled_concatenation_readback_satisfied(self) -> bool:
        plan = self.labeled_concatenation_plan()
        if plan is None or not self.labeled_concatenation_mutations_satisfied():
            return False
        mutations = self.labeled_concatenation_mutation_events()
        last_mutation = max(mutations, key=lambda event: event.step)
        saves = [
            event
            for event in self.successful_action_events("workbook.save")
            if event.step > last_mutation.step
        ]
        if not saves:
            return False
        compose_event = mutations[-1]
        expected_output = display_rows(compose_event.result)
        expected_summary = mapping_field(compose_event.result, "display_summary")
        read_geometry = a1_geometry(plan["read_range"])
        if (not expected_output and not expected_summary) or read_geometry is None:
            return False
        destination_offset = plan["destination_column"] - column_number(
            read_geometry[0]
        )
        for event in reversed(self.successful_action_events("range.read")):
            if event.step <= saves[-1].step or event.proposed.get("arguments") != {
                "sheet": plan["sheet"],
                "range": plan["read_range"],
            }:
                continue
            display = display_rows(event.result)
            observed_summary = mapping_field(event.result, "display_summary")
            if expected_summary and observed_summary:
                expected_hashes = expected_summary.get("column_sha256", [])
                observed_hashes = observed_summary.get("column_sha256", [])
                try:
                    summary_matches = (
                        expected_summary.get("rows") == observed_summary.get("rows")
                        and expected_hashes[0] == observed_hashes[destination_offset]
                        and observed_summary.get("headers", [])[destination_offset]
                        == plan["header"]
                        and observed_summary.get("error_count") == 0
                    )
                except IndexError:
                    summary_matches = False
                if summary_matches:
                    return True
            if not expected_output:
                return False
            try:
                observed_output = [
                    [row[destination_offset]] for row in display[: len(expected_output)]
                ]
            except IndexError:
                return False
            if observed_output != expected_output:
                return False
            if observed_output[0][0] != plan["header"]:
                return False
            for row in observed_output[1:]:
                text = str(row[0])
                if not text or text.upper().startswith(
                    ("#NAME?", "#VALUE!", "#REF!", "#DIV/0!", "#N/A")
                ):
                    return False
                if not all(
                    f"{header}{plan['label_separator']}" in text
                    for header in plan["headers"]
                ):
                    return False
            return True
        return False

    def successful_action_events(self, action: str) -> list[ExecutionEvent]:
        requested_identity = canonical_action_request(self.domain, action, {})[:2]
        return [
            event
            for event in self.successful_adapter_events()
            if effective_canonical_action(event, self.domain)[:2] == requested_identity
        ]

    def requested_save_files(self) -> list[str]:
        if self.domain == "multi_apps":
            produced_files = self.successful_saved_output_files()
            if produced_files:
                return produced_files
        files = requested_files(self.instruction)
        action_set = set(self.recommended_actions) | set(
            instruction_required_actions(self.domain, self.instruction)
        )
        input_suffixes: set[str] = set()
        if self.domain == "libreoffice_impress" and "audio.insert" in action_set:
            input_suffixes.update({".mp3", ".wav", ".ogg", ".m4a"})
        if self.domain == "libreoffice_impress" and "shape.insert_image" in action_set:
            input_suffixes.update({".png", ".jpg", ".jpeg"})
        return [
            filename
            for filename in files
            if Path(filename).suffix.casefold() not in input_suffixes
        ]

    @staticmethod
    def _result_mappings(result: Any) -> list[dict[str, Any]]:
        mappings = []
        pending = [result]
        for _depth in range(8):
            if not pending:
                break
            next_pending = []
            for value in pending:
                if not isinstance(value, dict):
                    continue
                mappings.append(value)
                for key in ("adapter_response", "response", "result"):
                    child = value.get(key)
                    if isinstance(child, dict):
                        next_pending.append(child)
            pending = next_pending
        return mappings

    def successful_saved_output_files(self) -> list[str]:
        files = []
        for event in self.successful_adapter_events():
            action = effective_canonical_action(event, self.domain)[1]
            if not is_save(action) and not self.event_has_save_evidence(event):
                continue
            arguments = event.proposed.get("arguments", {})
            candidates = []
            if isinstance(arguments, dict):
                candidates.extend(
                    arguments.get(field) for field in ("output_path", "url")
                )
                payload = arguments.get("payload")
                params = payload.get("params") if isinstance(payload, dict) else None
                if isinstance(params, dict):
                    candidates.extend(
                        params.get(field) for field in ("output_path", "url")
                    )
            for body in self._result_mappings(event.result):
                candidates.extend(
                    body.get(field) for field in ("path", "url", "output_path")
                )
            for candidate in candidates:
                if not isinstance(candidate, str) or not candidate.strip():
                    continue
                parsed_path = (
                    unquote(urlparse(candidate).path)
                    if candidate.startswith("file:")
                    else candidate
                )
                filename = Path(parsed_path).name
                if filename and filename not in files:
                    files.append(filename)
        return files

    def latest_context_hint(self, action: str) -> dict[str, Any]:
        for event in reversed(self.successful_action_events(action)):
            if isinstance(event.result, dict) and isinstance(
                event.result.get("context_hint"), dict
            ):
                return event.result["context_hint"]
        return {}

    def inspected_presentation_shape(
        self, slide_index: int, selector: dict[str, Any]
    ) -> dict[str, Any] | None:
        slides = self.latest_context_hint("presentation.inspect").get("slides", [])
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == slide_index
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        shapes = [
            item for item in slide.get("text_shapes", []) if isinstance(item, dict)
        ]
        if "index" in selector:
            return next(
                (item for item in shapes if item.get("index") == selector["index"]),
                None,
            )
        if "name" in selector:
            return next(
                (item for item in shapes if item.get("name") == selector["name"]), None
            )
        if "text" in selector:
            needle = str(selector["text"])
            return next(
                (
                    item
                    for item in shapes
                    if needle in "\n".join(str(line) for line in item.get("lines", []))
                ),
                None,
            )
        return None

    def presentation_text_shapes(self, slide_index: int) -> list[dict[str, Any]]:
        slides = self.latest_context_hint("presentation.inspect").get("slides", [])
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == slide_index
            ),
            None,
        )
        if not isinstance(slide, dict):
            return []
        return [
            shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict) and isinstance(shape.get("index"), int)
        ]

    def cover_image_mutation_applied(self) -> bool:
        return impress_cover_semantics.mutation_applied(self)

    def cover_image_readback_satisfied(self) -> bool:
        return impress_cover_semantics.readback_satisfied(self)

    def audio_insert_readback_satisfied(self) -> bool:
        requested_path = requested_audio_path(self.instruction)
        if requested_path is None:
            return False
        insertions = [
            event
            for event in self.successful_action_events("audio.insert")
            if event.proposed.get("arguments", {}).get("path") == requested_path
        ]
        if not insertions:
            return False
        insertion = insertions[-1]
        slide_index = insertion.proposed.get("arguments", {}).get("slide")
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > insertion.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slides = readbacks[-1].result["context_hint"].get("slides", [])
        for slide in slides:
            if not isinstance(slide, dict) or slide.get("slide") != slide_index:
                continue
            for shape in slide.get("media_shapes", []):
                if not isinstance(shape, dict):
                    continue
                media_url = str(shape.get("media_url", ""))
                if media_url.removeprefix("file://") == requested_path:
                    return True
        return False

    def initial_presentation_context_hint(self) -> dict[str, Any]:
        initial: dict[str, Any] | None = None
        pages: dict[int, dict[str, Any]] = {}
        for event in self.successful_adapter_events():
            domain, action, _ = effective_canonical_action(event, self.domain)
            if domain != "libreoffice_impress":
                continue
            if initial is not None and action in {
                "slide.create", "slide.delete", "slide.duplicate", "slide.move"
            }:
                break
            if action != "presentation.inspect" or not isinstance(event.result, dict):
                continue
            hint = event.result.get("context_hint")
            if not isinstance(hint, dict):
                continue
            if initial is None:
                initial = hint
            elif any(
                hint.get(key) != initial.get(key) for key in ("identity", "slide_count")
            ):
                break
            # Focused reads can discover new pages later. Keep each page's
            # first observation, never its post-mutation formatting or geometry.
            for page in hint.get("slides", []):
                if isinstance(page, dict) and type(page.get("slide")) is int:
                    pages.setdefault(page["slide"], page)
        if initial is None:
            return {}
        if len(pages) <= len(initial.get("slides", [])):
            return initial
        return {
            **initial,
            "slides": [pages[index] for index in sorted(pages)],
            "inspected_slides": sorted(pages),
        }

    def next_ordered_image_slide_action(self) -> dict[str, Any] | None:
        request = requested_ordered_image_slides(self.instruction)
        if request is None:
            return None
        initial = self.initial_presentation_context_hint()
        initial_count = initial.get("slide_count")
        if not isinstance(initial_count, int) or initial_count < 1:
            return {"action": "presentation.inspect", "arguments": {}}

        deleted_slides = len(self.successful_action_events("slide.delete"))
        if deleted_slides < max(0, initial_count - 1):
            return {
                "action": "slide.delete",
                "arguments": {"slide": initial_count - deleted_slides - 1},
            }

        first_slide = next(
            (
                slide
                for slide in initial.get("slides", [])
                if isinstance(slide, dict) and slide.get("slide") == 0
            ),
            {},
        )
        deleted_paths = {
            tuple(
                event.proposed.get("arguments", {}).get("selector", {}).get("path", [])
            )
            for event in self.successful_action_events("shape.delete")
        }
        for shape in reversed(first_slide.get("all_shapes", [])):
            path = shape.get("path") if isinstance(shape, dict) else None
            if isinstance(path, list) and tuple(path) not in deleted_paths:
                return {
                    "action": "shape.delete",
                    "arguments": {"slide": 0, "selector": {"path": path}},
                }

        created = len(self.successful_action_events("slide.create"))
        current_count = 1 + created
        if current_count < request["slide_count"]:
            return {
                "action": "slide.create",
                "arguments": {"index": current_count, "layout": 20},
            }

        successful_images = {
            (
                event.proposed.get("arguments", {}).get("slide"),
                event.proposed.get("arguments", {}).get("path"),
            )
            for event in self.successful_action_events("shape.insert_image")
        }
        for slide_index, path in enumerate(request["files"]):
            if (slide_index, path) not in successful_images:
                return {
                    "action": "shape.insert_image",
                    "arguments": {"slide": slide_index, "path": path},
                }
        return None

    def ordered_image_slide_mutations_satisfied(self) -> bool:
        return (
            requested_ordered_image_slides(self.instruction) is not None
            and bool(self.initial_presentation_context_hint())
            and self.next_ordered_image_slide_action() is None
        )

    def ordered_image_slide_readback_satisfied(self) -> bool:
        request = requested_ordered_image_slides(self.instruction)
        if request is None or not self.ordered_image_slide_mutations_satisfied():
            return False
        image_events = self.successful_action_events("shape.insert_image")
        last_mutation_step = max(event.step for event in image_events)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation_step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        hint = readbacks[-1].result["context_hint"]
        slides = hint.get("slides", [])
        if (
            hint.get("slide_count") != request["slide_count"]
            or len(slides) != request["slide_count"]
        ):
            return False
        for slide_index, expected_path in enumerate(request["files"]):
            slide = next(
                (
                    item
                    for item in slides
                    if isinstance(item, dict) and item.get("slide") == slide_index
                ),
                None,
            )
            if not isinstance(slide, dict) or slide.get("shape_count") != 1:
                return False
            images = slide.get("graphic_shapes", [])
            if len(images) != 1:
                return False
            if str(images[0].get("name", "")) != Path(expected_path).name:
                return False
        return True

    def presentation_paragraphs(self, slide_index: int) -> list[dict[str, Any]]:
        paragraphs = []
        for shape in self.presentation_text_shapes(slide_index):
            for paragraph in shape.get("paragraphs", []):
                if not isinstance(paragraph, dict):
                    continue
                paragraphs.append(
                    {
                        **paragraph,
                        "shape_index": shape.get("index"),
                        "shape_name": shape.get("name"),
                    }
                )
        return paragraphs

    def matching_indent_spec(self) -> dict[str, Any] | None:
        request = requested_matching_indent_without_bullet(self.instruction)
        if request is None:
            return None
        paragraphs = self.presentation_paragraphs(request["slide"])
        target = next(
            (
                paragraph
                for paragraph in paragraphs
                if str(paragraph.get("text", "")).strip().casefold()
                == request["target_text"].strip().casefold()
            ),
            None,
        )
        reference_names = {
            value.strip().casefold() for value in request["reference_texts"]
        }
        references = [
            paragraph
            for paragraph in paragraphs
            if str(paragraph.get("text", "")).strip().casefold() in reference_names
        ]
        if (
            target is None
            or not references
            or not isinstance(target.get("shape_index"), int)
        ):
            return None
        reference = references[0]
        reference_left = int(reference.get("left_margin", 0)) + max(
            int(reference.get("first_line_indent", 0)), 0
        )
        return {
            "slide": request["slide"],
            "selector": {"index": target["shape_index"]},
            "match_text": request["target_text"],
            "bullet": False,
            "left_margin": reference_left,
            "first_line_indent": 0,
            "target": target,
            "references": references,
        }

    def matching_indent_satisfied(self) -> bool:
        spec = self.matching_indent_spec()
        if spec is None:
            return False
        target = spec["target"]
        target_left = int(target.get("left_margin", 0)) + max(
            int(target.get("first_line_indent", 0)), 0
        )
        reference_lefts = {
            int(reference.get("left_margin", 0))
            + max(int(reference.get("first_line_indent", 0)), 0)
            for reference in spec["references"]
        }
        return target.get("bullet") is False and target_left in reference_lefts

    def matching_indent_mutation_applied(self) -> bool:
        spec = self.matching_indent_spec()
        if spec is None:
            return False
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
        return any(
            event.proposed.get("arguments", {}) == expected
            for event in self.successful_action_events("shape.format_text")
        )

    def content_textbox_spec(self) -> dict[str, Any] | None:
        request = requested_content_textbox_insert(self.instruction)
        if request is None:
            return None
        shapes = self.presentation_text_shapes(request["slide"])
        candidates = [
            shape
            for shape in shapes
            if any(
                token in str(shape.get("kind", "")).casefold()
                for token in ("outlinershape", "bodyshape")
            )
        ]
        if not candidates:
            candidates = [
                shape
                for shape in shapes
                if not any(
                    token in str(shape.get("kind", "")).casefold()
                    for token in ("titletextshape", "subtitleshape")
                )
            ]
        if len(candidates) != 1:
            return None
        target = candidates[0]
        return {
            "slide": request["slide"],
            "selector": {"index": target["index"]},
            "text": request["text"],
            "replace": True,
            "shape_name": target.get("name"),
        }

    def content_textbox_mutation_applied(self) -> bool:
        spec = self.content_textbox_spec()
        if spec is None:
            return False
        expected = {key: spec[key] for key in ("slide", "selector", "text", "replace")}
        return any(
            event.proposed.get("arguments", {}) == expected
            for event in self.successful_action_events("shape.write_text_native")
        )

    def content_textbox_readback_satisfied(self) -> bool:
        spec = self.content_textbox_spec()
        matching_mutations = [
            event
            for event in self.successful_action_events("shape.write_text_native")
            if spec is not None
            and event.proposed.get("arguments", {})
            == {key: spec[key] for key in ("slide", "selector", "text", "replace")}
        ]
        if spec is None or not matching_mutations:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > matching_mutations[-1].step
        ]
        if not saves:
            return False
        for event in reversed(self.successful_action_events("presentation.inspect")):
            if event.step <= saves[-1].step:
                continue
            hint = (
                event.result.get("context_hint")
                if isinstance(event.result, dict)
                else None
            )
            slides = hint.get("slides", []) if isinstance(hint, dict) else []
            slide = next(
                (
                    item
                    for item in slides
                    if isinstance(item, dict) and item.get("slide") == spec["slide"]
                ),
                None,
            )
            shapes = slide.get("text_shapes", []) if isinstance(slide, dict) else []
            target = next(
                (
                    shape
                    for shape in shapes
                    if isinstance(shape, dict)
                    and shape.get("index") == spec["selector"]["index"]
                ),
                None,
            )
            lines = target.get("lines", []) if isinstance(target, dict) else []
            return "\n".join(str(line) for line in lines).strip() == spec["text"]
        return False

    def source_read_end_row(self) -> int | None:
        for event in self.successful_action_events("range.read"):
            cell_range = str(event.proposed.get("arguments", {}).get("range", ""))
            match = re.fullmatch(r"[A-Za-z]+\d+:[A-Za-z]+(\d+)", cell_range)
            if match:
                return int(match.group(1))
        return None

    def source_read_geometry(self) -> tuple[str, str, int, int, int] | None:
        for event in self.successful_action_events("range.read"):
            cell_range = str(event.proposed.get("arguments", {}).get("range", ""))
            match = re.fullmatch(r"([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)", cell_range)
            if not match:
                continue

            start_column, start_row, end_column, end_row = match.groups()
            width = column_number(end_column) - column_number(start_column) + 1
            return (
                start_column.upper(),
                end_column.upper(),
                int(start_row),
                int(end_row),
                width,
            )
        return None

    def latest_workbook_used_range(self) -> tuple[str, str] | None:
        for event in reversed(self.successful_action_events("workbook.inspect")):
            for result in self._result_mappings(event.result):
                sheets = result.get("sheets")
                if not isinstance(sheets, list) or not sheets:
                    continue
                active_sheet = str(result.get("active_sheet", ""))
                sheet = next(
                    (
                        item
                        for item in sheets
                        if isinstance(item, dict)
                        and str(item.get("name", "")) == active_sheet
                    ),
                    sheets[0],
                )
                if not isinstance(sheet, dict) or not isinstance(
                    sheet.get("used_range"), dict
                ):
                    continue
                used = sheet["used_range"]
                coordinates = [
                    used.get("start_column"),
                    used.get("start_row"),
                    used.get("end_column"),
                    used.get("end_row"),
                ]
                if any(
                    isinstance(value, bool) or not isinstance(value, int)
                    for value in coordinates
                ):
                    continue
                start_column, start_row, end_column, end_row = coordinates
                return (
                    str(sheet.get("name", active_sheet)),
                    f"{column_label(start_column + 1)}{start_row + 1}:"
                    f"{column_label(end_column + 1)}{end_row + 1}",
                )
        return None

    def _calc_used_range_read_segments(
        self,
        before_step: int | None = None,
    ) -> tuple[str, str, str, int, int, list[tuple[int, int, ExecutionEvent]]] | None:
        if self.domain != "libreoffice_calc":
            return None
        used_range = self.latest_workbook_used_range()
        if used_range is None:
            return None
        sheet, cell_range = used_range
        used = a1_geometry(cell_range)
        if used is None:
            return None
        start_column, start_row, end_column, end_row = used
        relevant_events = [
            event
            for event in self.events
            if before_step is None or event.step < before_step
        ]
        latest_mutation_step = max(
            (
                event.step
                for event in relevant_events
                if event.executed
                and (
                    event.proposed.get("kind") == "gui"
                    or (
                        event.proposed.get("kind") == "adapter"
                        and not is_read_only(str(event.proposed.get("action", "")))
                        and str(event.proposed.get("action", "")) != "chart.create"
                    )
                )
            ),
            default=0,
        )
        segments: list[tuple[int, int, ExecutionEvent]] = []
        for event in self.successful_action_events("range.read"):
            if before_step is not None and event.step >= before_step:
                continue
            if event.step <= latest_mutation_step:
                continue
            arguments = event.proposed.get("arguments", {})
            if str(arguments.get("sheet", "")) != sheet:
                continue
            geometry = a1_geometry(str(arguments.get("range", "")))
            if geometry is None:
                continue
            read_start_column, read_start_row, read_end_column, read_end_row = geometry
            if (
                read_start_column != start_column
                or read_end_column != end_column
                or read_start_row < start_row
                or read_end_row > end_row
            ):
                continue
            segments.append((read_start_row, read_end_row, event))
        return sheet, start_column, end_column, start_row, end_row, segments

    def next_calc_read_range(self) -> tuple[str, str] | None:
        read_state = self._calc_used_range_read_segments()
        if read_state is None:
            return None
        sheet, start_column, end_column, start_row, end_row, segments = read_state
        if not segments:
            return None
        latest_start, latest_end, _event = segments[-1]
        if latest_start == start_row and latest_end < end_row:
            return sheet, f"{start_column}{latest_end + 1}:{end_column}{end_row}"
        if latest_end == end_row and latest_start > start_row:
            return sheet, f"{start_column}{start_row}:{end_column}{latest_start - 1}"
        return None

    def calc_used_range_read_covered(self, before_step: int | None = None) -> bool:
        read_state = self._calc_used_range_read_segments(before_step)
        if read_state is None:
            return False
        _sheet, _start_column, _end_column, start_row, end_row, segments = read_state
        intervals = []
        for read_start, read_end, event in segments:
            is_full_range = read_start == start_row and read_end == end_row
            is_truncated = (
                isinstance(event.result, dict) and event.result.get("truncated") is True
            )
            parsed_row_count = len(display_rows(event.result))
            expected_row_count = read_end - read_start + 1
            if is_full_range and is_truncated and parsed_row_count < expected_row_count:
                continue
            intervals.append((read_start, read_end))
        if not intervals:
            return False
        cursor = start_row
        for interval_start, interval_end in sorted(intervals):
            if interval_end < cursor:
                continue
            if interval_start > cursor:
                return False
            cursor = max(cursor, interval_end + 1)
            if cursor > end_row:
                return True
        return False

    def latest_workbook_sheet_names(self) -> list[str]:
        for event in reversed(self.successful_action_events("workbook.inspect")):
            body = event.result
            if not isinstance(body, dict):
                continue
            result = body.get("result")
            sheets = result.get("sheets") if isinstance(result, dict) else None
            if isinstance(sheets, list):
                return [
                    str(sheet["name"])
                    for sheet in sheets
                    if isinstance(sheet, dict) and isinstance(sheet.get("name"), str)
                ]
        return []

    def initial_workbook_sheet_names(self) -> list[str]:
        for event in self.successful_action_events("workbook.inspect"):
            body = event.result
            if not isinstance(body, dict):
                continue
            result = body.get("result")
            sheets = result.get("sheets") if isinstance(result, dict) else None
            if isinstance(sheets, list):
                return [
                    str(sheet["name"])
                    for sheet in sheets
                    if isinstance(sheet, dict) and isinstance(sheet.get("name"), str)
                ]
        return []

    def sheet_copy_lifecycle_plan(self) -> dict[str, Any] | None:
        spec = requested_sheet_copy_lifecycle(self.instruction)
        names = self.initial_workbook_sheet_names()
        if self.domain != "libreoffice_calc" or spec is None or not names:
            return None

        def resolve(requested: str, candidates: list[str]) -> str | None:
            key = re.sub(r"\s+", "", requested).casefold()
            matches = [
                candidate
                for candidate in candidates
                if re.sub(r"\s+", "", candidate).casefold() == key
            ]
            return matches[0] if len(matches) == 1 else None

        current_names = list(names)
        source = resolve(spec["source"], current_names)
        if source is None or spec["renamed_source"] in current_names:
            return None
        steps: list[dict[str, Any]] = [
            {
                "action": "sheet.rename",
                "arguments": {"sheet": source, "new_name": spec["renamed_source"]},
            }
        ]
        current_names[current_names.index(source)] = spec["renamed_source"]

        anchor = resolve(spec["anchor"], current_names)
        if anchor is None or spec["copy_name"] in current_names:
            return None
        copy_index = current_names.index(anchor)
        if spec["placement"] == "after":
            copy_index += 1
        steps.append(
            {
                "action": "sheet.copy",
                "arguments": {
                    "sheet": spec["renamed_source"],
                    "new_name": spec["copy_name"],
                    "index": copy_index,
                },
            }
        )
        current_names.insert(copy_index, spec["copy_name"])

        for rename in spec["renames"][1:]:
            rename_source = resolve(rename["source"], current_names)
            if rename_source is None or rename["target"] in current_names:
                return None
            steps.append(
                {
                    "action": "sheet.rename",
                    "arguments": {
                        "sheet": rename_source,
                        "new_name": rename["target"],
                    },
                }
            )
            current_names[current_names.index(rename_source)] = rename["target"]

        return {"steps": steps, "final_names": current_names}

    def completed_sheet_copy_lifecycle_steps(self) -> int:
        plan = self.sheet_copy_lifecycle_plan()
        if plan is None:
            return 0
        completed = 0
        last_step = 0
        for expected in plan["steps"]:
            match = next(
                (
                    event
                    for event in self.successful_action_events(expected["action"])
                    if event.step > last_step
                    and event.proposed.get("arguments") == expected["arguments"]
                ),
                None,
            )
            if match is None:
                break
            completed += 1
            last_step = match.step
        return completed

    def next_sheet_copy_lifecycle_action(self) -> dict[str, Any] | None:
        plan = self.sheet_copy_lifecycle_plan()
        if plan is None:
            return None
        completed = self.completed_sheet_copy_lifecycle_steps()
        if completed >= len(plan["steps"]):
            return None
        return {
            **plan["steps"][completed],
            "index": completed,
            "count": len(plan["steps"]),
        }

    def sheet_copy_lifecycle_mutations_satisfied(self) -> bool:
        plan = self.sheet_copy_lifecycle_plan()
        return bool(
            plan and self.completed_sheet_copy_lifecycle_steps() == len(plan["steps"])
        )

    def sheet_copy_lifecycle_readback_satisfied(self) -> bool:
        plan = self.sheet_copy_lifecycle_plan()
        if plan is None or not self.sheet_copy_lifecycle_mutations_satisfied():
            return False
        mutation_events = [
            event
            for event in self.successful_adapter_events()
            if event.proposed.get("action") in {"sheet.rename", "sheet.copy"}
        ]
        if not mutation_events:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation_events[-1].step
        ]
        if not saves:
            return False
        for event in reversed(self.successful_action_events("workbook.inspect")):
            if event.step <= saves[-1].step:
                continue
            body = event.result if isinstance(event.result, dict) else {}
            result = body.get("result") if isinstance(body.get("result"), dict) else {}
            sheets = result.get("sheets") if isinstance(result, dict) else None
            if not isinstance(sheets, list):
                return False
            observed = [
                str(item["name"])
                for item in sheets
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            ]
            return observed == plan["final_names"]
        return False

    def reorder_table_spec(self) -> dict[str, Any] | None:
        headers = requested_column_order(self.instruction)
        geometry = self.source_read_geometry()
        read_events = self.successful_action_events("range.read")
        if not headers or geometry is None or not read_events:
            return None
        observed_headers = first_display_row(read_events[0].result)
        nonempty_indices = [
            index for index, value in enumerate(observed_headers) if str(value).strip()
        ]
        if not nonempty_indices:
            return None
        first_index, last_index = min(nonempty_indices), max(nonempty_indices)
        start_column, _end_column, start_row, end_row, width = geometry
        if last_index >= width:
            return None
        table_start_column = column_label(column_number(start_column) + first_index)
        table_end_column = column_label(column_number(start_column) + last_index)
        return {
            "sheet": str(read_events[0].proposed.get("arguments", {}).get("sheet", "")),
            "range": f"{table_start_column}{start_row}:{table_end_column}{end_row}",
            "headers": headers,
            "observed_headers": observed_headers[first_index : last_index + 1],
        }

    def period_rate_request(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc":
            return None
        return requested_period_rate_column(self.instruction)

    def period_rate_plan(self) -> dict[str, Any] | None:
        request = self.period_rate_request()
        geometry = self.source_read_geometry()
        read_events = self.successful_action_events("range.read")
        if request is None or geometry is None or not read_events:
            return None
        source_event = read_events[0]
        rows = display_rows(source_event.result)
        if len(rows) < 2:
            return None
        start_column, end_column, start_row, end_row, width = geometry
        headers = rows[0]
        if len(headers) < width or len(rows) < end_row - start_row + 1:
            return None
        normalized_headers: list[set[str]] = []
        for header in headers[:width]:
            raw_tokens = re.sub(r"[^a-z0-9]+", " ", header.casefold()).split()
            tokens = set(raw_tokens)
            tokens.update(
                token[:-1]
                for token in raw_tokens
                if len(token) > 3 and token.endswith("s")
            )
            if "yearly" in tokens:
                tokens.add("year")
            normalized_headers.append(tokens)
        numerator_candidates = [
            index
            for index, tokens in enumerate(normalized_headers)
            if "rate" in tokens
            and "period" not in tokens
            and {"annual", "year"}.intersection(tokens)
        ]
        denominator_candidates = [
            index
            for index, tokens in enumerate(normalized_headers)
            if "period" in tokens and {"year", "annual"}.intersection(tokens)
        ]
        if len(numerator_candidates) != 1 or len(denominator_candidates) != 1:
            return None
        numerator_index = numerator_candidates[0]
        denominator_index = denominator_candidates[0]
        if numerator_index == denominator_index:
            return None
        ratios: list[Decimal] = []
        for row in rows[1 : end_row - start_row + 1]:
            if max(numerator_index, denominator_index) >= len(row):
                return None
            try:
                numerator = Decimal(
                    str(row[numerator_index]).replace(",", "").rstrip("%").strip()
                )
                denominator = Decimal(
                    str(row[denominator_index]).replace(",", "").rstrip("%").strip()
                )
            except InvalidOperation:
                return None
            if denominator == 0:
                return None
            ratios.append(numerator / denominator)
        if not ratios:
            return None
        numerator_column = column_label(column_number(start_column) + numerator_index)
        denominator_column = column_label(
            column_number(start_column) + denominator_index
        )
        target_column = column_label(column_number(end_column) + 1)
        values = [[{"kind": "string", "value": request["header"]}]]
        values.extend(
            [
                {
                    "kind": "formula",
                    "value": f"={numerator_column}{row_number}/{denominator_column}{row_number}",
                    "number_format": request["number_format"],
                }
            ]
            for row_number in range(start_row + 1, end_row + 1)
        )
        maximum_index = max(range(len(ratios)), key=ratios.__getitem__)
        maximum_row = start_row + 1 + maximum_index
        sheet = str(source_event.proposed.get("arguments", {}).get("sheet", ""))
        if not sheet:
            return None
        return {
            "sheet": sheet,
            "source_range": f"{start_column}{start_row}:{end_column}{end_row}",
            "output_range": f"{target_column}{start_row}:{target_column}{end_row}",
            "readback_range": f"{start_column}{start_row}:{target_column}{end_row}",
            "header": request["header"],
            "numerator_header": headers[numerator_index],
            "denominator_header": headers[denominator_index],
            "maximum_row": maximum_row,
            "maximum_cell": f"{target_column}{maximum_row}",
            "font_color": request["font_color"],
            "values": values,
            "steps": [
                {
                    "action": "range.write",
                    "arguments": {
                        "sheet": sheet,
                        "range": f"{target_column}{start_row}:{target_column}{end_row}",
                        "values": values,
                    },
                },
                {
                    "action": "range.format",
                    "arguments": {
                        "sheet": sheet,
                        "range": f"{target_column}{maximum_row}",
                        "format": {"font_color": request["font_color"]},
                    },
                },
                {"action": "workbook.save", "arguments": {}},
                {
                    "action": "range.read",
                    "arguments": {
                        "sheet": sheet,
                        "range": f"{start_column}{start_row}:{target_column}{end_row}",
                    },
                },
            ],
        }

    def next_period_rate_action(self) -> dict[str, Any] | None:
        if self.period_rate_request() is None:
            return None
        if not self.successful_action_events("workbook.inspect"):
            return {"action": "workbook.inspect", "arguments": {}, "index": 0}
        if not self.successful_action_events("range.read"):
            used_range = self.latest_workbook_used_range()
            if used_range is None:
                return None
            sheet, cell_range = used_range
            return {
                "action": "range.read",
                "arguments": {"sheet": sheet, "range": cell_range},
                "index": 1,
            }
        plan = self.period_rate_plan()
        if plan is None:
            return None
        for index, step in enumerate(plan["steps"], start=2):
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return {"index": index, **step}
        return None

    def period_rate_readback_satisfied(self) -> bool:
        plan = self.period_rate_plan()
        if plan is None or self.next_period_rate_action() is not None:
            return False
        read_events = self.successful_action_events("range.read")
        if not read_events:
            return False
        event = read_events[-1]
        if event.proposed.get("arguments") != plan["steps"][-1]["arguments"]:
            return False
        rows = display_rows(event.result)
        formulas = matrix_field(event.result, "formulas")
        style_cells = mapping_field(event.result, "style_cells")
        target_geometry = a1_geometry(plan["output_range"])
        read_geometry = a1_geometry(plan["readback_range"])
        if target_geometry is None or read_geometry is None or not rows or not formulas:
            return False
        target_offset = column_number(target_geometry[0]) - column_number(
            read_geometry[0]
        )
        if rows[0][target_offset] != plan["header"]:
            return False
        expected_formulas = [row[0]["value"] for row in plan["values"][1:]]
        observed_formulas = [
            formulas[row_index][target_offset]
            for row_index in range(1, len(expected_formulas) + 1)
            if row_index < len(formulas) and target_offset < len(formulas[row_index])
        ]
        if observed_formulas != expected_formulas:
            return False
        maximum_style = style_cells.get(plan["maximum_cell"])
        return (
            isinstance(maximum_style, dict)
            and str(maximum_style.get("font_color", "")).casefold()
            == str(plan["font_color"]).casefold()
        )

    def written_row_labels(self) -> set[str]:
        labels: set[str] = set()
        for event in self.successful_action_events("range.write"):
            values = event.proposed.get("arguments", {}).get("values", [])
            for row in values if isinstance(values, list) else []:
                for cell in row if isinstance(row, list) else []:
                    if (
                        isinstance(cell, dict)
                        and cell.get("kind") == "string"
                        and isinstance(cell.get("value"), str)
                    ):
                        labels.add(cell["value"].strip().casefold())
        return labels

    def requested_row_labels_satisfied(self) -> bool:
        labels = requested_row_labels(self.instruction)
        return bool(labels) and all(
            label.casefold() in self.written_row_labels() for label in labels
        )

    def next_chart_spec(self) -> dict[str, Any] | None:
        labels = requested_row_labels(self.instruction)
        chart_types = requested_chart_types(self.instruction)
        chart_index = len(self.successful_action_events("chart.create"))
        geometry = self.source_read_geometry()
        if (
            geometry is None
            or chart_index >= len(labels)
            or chart_index >= len(chart_types)
        ):
            return None
        start_column, end_column, start_row, end_row, width = geometry
        if width < 2:
            return None
        label = labels[chart_index]
        output_row = end_row + 1 + chart_index
        omit_first_category = bool(
            chart_index > 0
            and re.search(
                r"(?i)\b(?:Jan(?:uary)?|first (?:month|category))\b[^.]{0,80}\bomit(?:ted)?\b"
                r"|\bomit(?:ted)?\b[^.]{0,80}\b(?:Jan(?:uary)?|first (?:month|category))\b",
                self.instruction,
            )
        )
        if omit_first_category and width >= 3:
            first_included_column = column_label(column_number(start_column) + 2)
            source_ranges = [
                f"{start_column}{start_row}",
                f"{first_included_column}{start_row}:{end_column}{start_row}",
                f"{start_column}{output_row}",
                f"{first_included_column}{output_row}:{end_column}{output_row}",
            ]
        else:
            source_ranges = [
                f"{start_column}{start_row}:{end_column}{start_row}",
                f"{start_column}{output_row}:{end_column}{output_row}",
            ]
        return {
            "index": chart_index,
            "label": label,
            "type": chart_types[chart_index],
            "source_ranges": source_ranges,
            "max_row": end_row + len(labels),
            "min_column": column_number(start_column),
            "max_column": column_number(end_column),
        }

    def axis_chart_spec(self) -> dict[str, Any] | None:
        """Derive a vertical X/Y chart from observed headers and axis wording."""
        if self.domain != "libreoffice_calc":
            return None
        chart_types = requested_chart_types(self.instruction)
        geometry = self.source_read_geometry()
        read_events = self.successful_action_events("range.read")
        if len(chart_types) != 1 or geometry is None or not read_events:
            return None
        start_column, _end_column, start_row, end_row, width = geometry
        headers = first_display_row(read_events[0].result)
        if len(headers) < width:
            return None

        def axis_index(axis: str) -> int | None:
            matches = []
            for index, header in enumerate(headers[:width]):
                text = str(header).strip()
                if not text:
                    continue
                quoted = rf'["\u201c\u201d\']?{re.escape(text)}["\u201c\u201d\']?'
                if re.search(
                    rf"(?i)(?<!\w){quoted}\s+(?:column\s+)?(?:on|as)\s+(?:the\s+)?{axis}[- ]?axis\b",
                    self.instruction,
                ):
                    matches.append(index)
            return matches[0] if len(matches) == 1 else None

        x_index = axis_index("x")
        y_index = axis_index("y")
        if x_index is None or y_index is None or x_index == y_index:
            return None
        x_column = column_label(column_number(start_column) + x_index)
        y_column = column_label(column_number(start_column) + y_index)
        sheet = str(read_events[0].proposed.get("arguments", {}).get("sheet", ""))
        return {
            "sheet": sheet,
            "type": chart_types[0],
            "source_ranges": [
                f"{x_column}{start_row}:{x_column}{end_row}",
                f"{y_column}{start_row}:{y_column}{end_row}",
            ],
            "column_headers": True,
            "row_headers": True,
            "data_row_source": "columns",
            "x_header": str(headers[x_index]).strip(),
            "y_header": str(headers[y_index]).strip(),
        }

    def new_sheet_chart_spec(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc" or not re.search(
            r"(?i)\bnew\s+(?:sheet|worksheet)\b", self.instruction
        ):
            return None
        target_sheets = requested_sheet_names(self.instruction)
        chart_types = requested_chart_types(self.instruction)
        title = requested_chart_title(self.instruction)
        reads = self.successful_action_events("range.read")
        if (
            len(target_sheets) != 1
            or len(chart_types) != 1
            or title is None
            or not reads
        ):
            return None
        source_sheet = str(reads[0].proposed.get("arguments", {}).get("sheet", ""))
        source_range = str(reads[0].proposed.get("arguments", {}).get("range", ""))
        target_sheet = target_sheets[0]
        if not source_sheet or not source_range or source_sheet == target_sheet:
            return None
        return {
            "sheet": target_sheet,
            "source_sheet": source_sheet,
            "name": title,
            "title": title,
            "source_ranges": [source_range],
            "type": chart_types[0],
            "data_row_source": "columns",
            "column_headers": True,
            "row_headers": True,
        }

    def new_sheet_chart_readback_satisfied(self) -> bool:
        spec = self.new_sheet_chart_spec()
        if spec is None:
            return True
        for event in reversed(self.successful_action_events("workbook.inspect")):
            body = event.result if isinstance(event.result, dict) else {}
            result = body.get("result") if isinstance(body.get("result"), dict) else {}
            sheets = result.get("sheets") if isinstance(result, dict) else None
            if not isinstance(sheets, list):
                continue
            sheet = next(
                (
                    item
                    for item in sheets
                    if isinstance(item, dict) and item.get("name") == spec["sheet"]
                ),
                None,
            )
            charts = sheet.get("charts", []) if isinstance(sheet, dict) else []
            return any(
                isinstance(chart, dict)
                and all(
                    chart.get(key) == spec[key]
                    for key in (
                        "source_sheet",
                        "name",
                        "title",
                        "source_ranges",
                        "type",
                        "column_headers",
                        "row_headers",
                    )
                )
                for chart in charts
            )
        return False

    def axis_chart_readback_satisfied(self) -> bool:
        spec = self.axis_chart_spec()
        if spec is None:
            return True
        for event in reversed(self.successful_action_events("workbook.inspect")):
            body = event.result if isinstance(event.result, dict) else {}
            result = body.get("result") if isinstance(body.get("result"), dict) else {}
            sheets = result.get("sheets") if isinstance(result, dict) else None
            if not isinstance(sheets, list):
                continue
            sheet = next(
                (
                    item
                    for item in sheets
                    if isinstance(item, dict) and item.get("name") == spec["sheet"]
                ),
                None,
            )
            if not isinstance(sheet, dict) or not isinstance(sheet.get("charts"), list):
                continue
            for chart in sheet["charts"]:
                if not isinstance(chart, dict):
                    continue
                if (
                    chart.get("source_ranges") == spec["source_ranges"]
                    and chart.get("column_headers") is True
                    and chart.get("row_headers") is True
                    and chart.get("type") == spec["type"]
                ):
                    return True
            return False
        return False

    def decimal_separator_spec(self) -> dict[str, Any] | None:
        if self.domain != "libreoffice_calc" or not re.search(
            r"(?i)\bdecimal\s+separator\b[^.]{0,80}(?:comma|\(,\)|[,])",
            self.instruction,
        ):
            return None
        geometry = self.source_read_geometry()
        read_events = self.successful_action_events("range.read")
        if geometry is None or not read_events:
            return None
        rows = display_rows(read_events[0].result)
        if len(rows) < 2:
            return None

        number = re.compile(r"^-?\d+(?:[.,](\d+))?$")
        first_is_header = not any(number.fullmatch(value.strip()) for value in rows[0])
        data_rows = rows[1:] if first_is_header else rows
        decimal_places = [
            len(match.group(1))
            for row in data_rows
            for value in row
            if (match := number.fullmatch(value.strip())) and match.group(1)
        ]
        if not decimal_places:
            return None
        start_column, end_column, start_row, end_row, _width = geometry
        target_start_row = start_row + 1 if first_is_header else start_row
        sheet = str(read_events[0].proposed.get("arguments", {}).get("sheet", ""))
        places = max(decimal_places)
        return {
            "sheet": sheet,
            "range": f"{start_column}{target_start_row}:{end_column}{end_row}",
            "number_format": f"0,{'0' * places}",
            "locale": "de-DE",
            "decimal_places": places,
        }

    def decimal_separator_readback_satisfied(self) -> bool:
        spec = self.decimal_separator_spec()
        if spec is None:
            return True
        saves = self.successful_action_events("workbook.save")
        if not saves:
            return False
        last_save_step = saves[-1].step
        for event in reversed(self.successful_action_events("range.read")):
            if event.step <= last_save_step:
                continue
            arguments = event.proposed.get("arguments", {})
            if (
                arguments.get("sheet") != spec["sheet"]
                or arguments.get("range") != spec["range"]
            ):
                continue
            body = event.result if isinstance(event.result, dict) else {}
            result = body.get("result") if isinstance(body.get("result"), dict) else {}
            formats = result.get("number_formats") if isinstance(result, dict) else None
            if not isinstance(formats, list) and body.get("truncated"):
                preview = str(body.get("preview", ""))
                return (
                    f'"code": "{spec["number_format"]}"' in preview
                    and f'"locale": "{spec["locale"]}"' in preview
                )
            flat = [
                item for row in formats or [] for item in row if isinstance(item, dict)
            ]
            return bool(flat) and all(
                item.get("code") == spec["number_format"]
                and item.get("locale") == spec["locale"]
                for item in flat
            )
        return False

    def unique_pivot_events(self) -> list[ExecutionEvent]:
        unique: dict[tuple[str, str, str], ExecutionEvent] = {}
        for event in self.successful_action_events("pivot.create"):
            arguments = event.proposed.get("arguments", {})
            identity = (
                str(arguments.get("destination_sheet", "")),
                str(arguments.get("destination", "")),
                str(arguments.get("name", "")),
            )
            unique[identity] = event
        return list(unique.values())

    def valid_pivot_events(self) -> list[ExecutionEvent]:
        valid = []
        for event in self.unique_pivot_events():
            arguments = event.proposed.get("arguments", {})
            grouping_fields = [
                str(field)
                for key in ("row_fields", "column_fields", "page_fields")
                for field in arguments.get(key, [])
            ]
            if len(grouping_fields) == 1 and arguments.get("data_fields"):
                valid.append(event)
        return valid

    def pivot_grouping_candidates(self) -> list[str]:
        headers = []
        for event in self.successful_action_events("range.read"):
            headers = first_display_row(event.result)
            if headers:
                break
        if not headers:
            return []
        instruction_normalized = re.sub(r"\s+", " ", self.instruction).casefold()
        matches = [
            (
                instruction_normalized.find(re.sub(r"\s+", " ", header).casefold()),
                header,
            )
            for header in headers
            if header
            and re.sub(r"\s+", " ", header).casefold() in instruction_normalized
        ]
        return [header for _position, header in sorted(matches)]

    def stacked_percentage_pivot_specs(self) -> list[dict[str, Any]]:
        required = requested_pivot_count(self.instruction)
        fields = self.pivot_grouping_candidates()
        requested_sheets = requested_sheet_names(self.instruction)
        if (
            self.domain != "libreoffice_calc"
            or required is None
            or required < 2
            or len(fields) < required
            or len(requested_sheets) != 1
            or not re.search(r"(?i)\bpercent(?:age|ages)?\b", self.instruction)
        ):
            return []
        source_event = next(
            (
                event
                for event in self.successful_action_events("range.read")
                if len(first_display_row(event.result)) >= len(fields)
            ),
            None,
        )
        if source_event is None:
            return []
        rows = display_rows(source_event.result)
        headers = first_display_row(source_event.result)
        source_arguments = source_event.proposed.get("arguments", {})
        source_sheet = str(source_arguments.get("sheet", ""))
        source_range = str(source_arguments.get("range", ""))
        if not rows or not source_sheet or a1_geometry(source_range) is None:
            return []
        header_indices = {header: headers.index(header) for header in fields[:required]}
        merged_regions = self.merged_text_region_specs()
        start_column = "A"
        next_row = 1
        if merged_regions:
            geometries = [a1_geometry(str(spec["range"])) for spec in merged_regions]
            valid = [geometry for geometry in geometries if geometry is not None]
            if valid:
                start_column = min(valid, key=lambda item: column_number(item[0]))[0]
                next_row = max(item[3] for item in valid) + 1
        blank_rows = requested_pivot_blank_rows(self.instruction)
        specs = []
        for index, field_name in enumerate(fields[:required], start=1):
            column_index = header_indices[field_name]
            distinct_values = {
                str(row[column_index]).strip().casefold()
                for row in rows[1:]
                if column_index < len(row) and str(row[column_index]).strip()
            }
            if not distinct_values:
                return []
            height = len(distinct_values) + 2
            arguments = {
                "source_sheet": source_sheet,
                "source_range": source_range,
                "destination_sheet": requested_sheets[0],
                "destination": f"{start_column}{next_row}",
                "name": f"PivotTable{index}",
                "row_fields": [field_name],
                "data_fields": [
                    {
                        "field": field_name,
                        "aggregation": "count",
                        "show_data_as": "total_percentage",
                    }
                ],
                "replace": False,
                "show_filter_button": False,
            }
            specs.append(
                {
                    "index": index - 1,
                    "field": field_name,
                    "height": height,
                    "blank_rows_after": blank_rows if index < required else 0,
                    "arguments": arguments,
                }
            )
            next_row += height + blank_rows
        return specs

    def next_stacked_percentage_pivot_action(self) -> dict[str, Any] | None:
        for spec in self.stacked_percentage_pivot_specs():
            if not any(
                event.proposed.get("arguments") == spec["arguments"]
                for event in self.successful_action_events("pivot.create")
            ):
                return {"action": "pivot.create", **spec}
        return None

    def stacked_percentage_pivot_readback_range(self) -> str | None:
        specs = self.stacked_percentage_pivot_specs()
        if not specs:
            return None
        first = a1_geometry(specs[0]["arguments"]["destination"])
        last = a1_geometry(specs[-1]["arguments"]["destination"])
        if first is None or last is None:
            return None
        merged = self.merged_text_readback_range()
        merged_geometry = a1_geometry(merged) if merged else None
        start_column = merged_geometry[0] if merged_geometry else first[0]
        start_row = merged_geometry[1] if merged_geometry else first[1]
        end_column = (
            merged_geometry[2]
            if merged_geometry
            else column_label(column_number(first[0]) + 1)
        )
        end_row = last[1] + int(specs[-1]["height"]) - 1
        return f"{start_column}{start_row}:{end_column}{end_row}"

    def stacked_percentage_pivot_readback_satisfied(self) -> bool:
        specs = self.stacked_percentage_pivot_specs()
        readback_range = self.stacked_percentage_pivot_readback_range()
        if (
            not specs
            or readback_range is None
            or self.next_stacked_percentage_pivot_action()
        ):
            return False
        mutations = self.successful_action_events("pivot.create")
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and mutations
            and event.step > mutations[-1].step
        ]
        if not saves:
            return False
        readback_geometry = a1_geometry(readback_range)
        if readback_geometry is None:
            return False
        for event in reversed(self.successful_action_events("range.read")):
            arguments = event.proposed.get("arguments", {})
            if (
                event.step <= saves[-1].step
                or arguments.get("sheet") != specs[0]["arguments"]["destination_sheet"]
                or arguments.get("range") != readback_range
            ):
                continue
            rows = display_rows(event.result)
            if not rows:
                return False
            for spec in specs:
                destination = a1_geometry(spec["arguments"]["destination"])
                if destination is None:
                    return False
                row_offset = destination[1] - readback_geometry[1]
                column_offset = column_number(destination[0]) - column_number(
                    readback_geometry[0]
                )
                if (
                    row_offset < 0
                    or row_offset >= len(rows)
                    or column_offset < 0
                    or column_offset >= len(rows[row_offset])
                    or rows[row_offset][column_offset] != spec["field"]
                ):
                    return False
                blank_rows_after = int(spec["blank_rows_after"])
                for blank_offset in range(blank_rows_after):
                    blank_row = row_offset + int(spec["height"]) + blank_offset
                    if blank_row >= len(rows) or any(
                        str(value).strip() for value in rows[blank_row]
                    ):
                        return False
            return True
        return False

    def pivot_count_satisfied(self) -> bool:
        required = requested_pivot_count(self.instruction)
        return required is None or self.successful_pivot_count() >= required
