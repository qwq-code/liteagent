"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

from __future__ import annotations

import json
import re
from typing import Any


from . import (
    calc_semantics,
    impress_semantics,
)
from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
)
from .completion_policy import (
    action_is_read_only as is_read_only,
    action_is_save as is_save,
    canonical_action_request,
    collect_initial_completion_evidence,
    completion_claim_contradictions as completion_claim_contradictions,
    effective_canonical_action,
)
from .generic_completion import strict_completion_gate
from .semantic_requirements import (
    strict_semantic_action_equivalents,
    strict_semantic_requirement_errors,
)
from .tool_catalog import (
    FORBIDDEN_DATASET_ACTIONS,
    action_relevance_score,
)


from .instruction_semantics import (
    requests_presentation_audio_insertion,
    requested_sized_slide_image,
    requested_table_row_replacement,
    requested_ordered_image_slides,
    requested_sheet_renames,
    requested_sheet_copy_lifecycle,
    requested_pivot_count,
    requested_row_labels,
    requests_appended_named_rows,
    requested_vlc_recording_path,
    requested_chart_count,
    requested_last_slide_duplicate_count,
    requested_os_account,
    requested_slide_background_color,
    requests_all_slide_backgrounds,
    requested_title_edge_position,
    requested_slide_title_update,
    requested_slide_title_formatting,
    requested_named_slide_table,
    requested_image_edge_position,
    requested_table_edge_position,
    requested_title_range_personal_info_cleanup,
    requested_slide_role_text_formatting,
    requested_slide_content_formatting,
    requested_content_textbox_insert,
    requested_matching_indent_without_bullet,
    requested_cover_image_slide,
    requested_calc_export_format,
    strict_instruction_required_actions,
)
from .state_model import RuntimeState


class CompletionMixin:
    @staticmethod
    def _completion_gate(
        state: RuntimeState,
        completion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        successful, mutations, missing, required_mutations = (
            collect_initial_completion_evidence(
                state,
                completion,
                is_read_only_action=is_read_only,
                is_save_action=is_save,
                relevance_score=action_relevance_score,
            )
        )
        recommended_mutations = required_mutations
        successful_actions = {
            effective_canonical_action(event, state.domain)[:2] for event in successful
        }
        required_action_ids = {
            canonical_action_request(state.domain, action, {})[:2]
            for action in recommended_mutations
        }
        # Multi-Apps has no public facade-specific mutation names anymore. A
        # historical ``recommended_actions`` entry may therefore use a retired
        # alias even when the model selected and executed a valid owning-Adapter
        # route. The strict generic collector already accounts for that route;
        # do not impose a second alias-based requirement here.
        if (
            state.domain != "multi_apps"
            and recommended_mutations
            and not successful_actions.intersection(required_action_ids)
        ):
            missing.append(
                "perform a task-relevant mutation; none of the recommended actions "
                f"{sorted(recommended_mutations)} succeeded"
            )
        account_spec = requested_os_account(state.instruction)
        if account_spec is not None:
            matching_accounts = [
                event
                for event in state.successful_action_events("user.ensure_account")
                if all(
                    event.proposed.get("arguments", {}).get(key) == value
                    for key, value in account_spec.items()
                )
            ]
            if not matching_accounts:
                missing.append(
                    "create or update the requested account with the exact username, password, and home "
                    "directory from the instruction"
                )
        vlc_recording_path = requested_vlc_recording_path(state.instruction)
        if vlc_recording_path is not None and not any(
            event.proposed.get("arguments", {}).get("values")
            == {"input-record-path": vlc_recording_path}
            for event in state.successful_action_events("config.update")
        ):
            missing.append(
                "set the VLC input-record-path preference to the exact requested recording directory "
                f"{vlc_recording_path!r}"
            )
        background_color = requested_slide_background_color(state.instruction)
        if background_color is not None:
            if requests_all_slide_backgrounds(state.instruction):
                if not state.all_slide_background_readback_satisfied():
                    missing.append(
                        "set every slide to the requested solid background color, save, and "
                        "read back all slide backgrounds"
                    )
            elif not any(
                str(event.proposed.get("arguments", {}).get("color", "")).upper()
                == background_color
                for event in state.successful_action_events("slide.set_background")
            ):
                missing.append(
                    f"set the requested slide background color to {background_color}"
                )
        title_edge_request = requested_title_edge_position(state.instruction)
        if title_edge_request is not None:
            if state.next_title_edge_position_action() is not None:
                missing.append(
                    "inspect the requested slide and move its observed title shape to the "
                    f"requested {title_edge_request['edge']} edge"
                )
            elif not state.title_edge_position_readback_satisfied():
                missing.append(
                    "save and read back the target title shape at its observation-derived "
                    f"{title_edge_request['edge']} geometry"
                )
        title_update_request = requested_slide_title_update(state.instruction)
        if title_update_request is not None:
            if state.slide_title_update_plan() is None:
                missing.append(
                    "inspect the requested slide and resolve its unique title shape"
                )
            elif state.next_slide_title_update_action() is not None:
                missing.append(
                    "write the exact quoted title and apply the requested title alignment"
                )
            elif not state.slide_title_update_readback_satisfied():
                missing.append(
                    "save and read back the exact title text and paragraph alignment on the "
                    "observed title shape"
                )
        title_format_request = requested_slide_title_formatting(state.instruction)
        if title_format_request is not None:
            if state.slide_title_format_plan() is None:
                missing.append(
                    "inspect the requested slide and resolve its title from native role or "
                    "visual text order"
                )
            elif state.next_slide_title_format_action() is not None:
                missing.append(
                    "apply every requested bold, font-size, and underline property to the "
                    "observed title shape"
                )
            elif not state.slide_title_format_readback_satisfied():
                missing.append(
                    "save and structurally read back every requested title formatting property"
                )
        sized_image_request = requested_sized_slide_image(state.instruction)
        if sized_image_request is not None:
            if state.sized_slide_image_plan() is None:
                missing.append(
                    "inspect the requested slide before inserting the Desktop image"
                )
            elif state.next_sized_slide_image_action() is not None:
                missing.append(
                    "insert the requested Desktop image with dimensions converted to "
                    "LibreOffice hundredth-millimeter units"
                )
            elif not state.sized_slide_image_readback_satisfied():
                missing.append(
                    "save and read back exactly one new image with the requested width and height"
                )
        table_row_request = requested_table_row_replacement(state.instruction)
        if table_row_request is not None:
            if state.table_row_replacement_plan() is None:
                missing.append(
                    "inspect the requested slide and resolve its unique table matrix"
                )
            elif state.next_table_row_replacement_action() is not None:
                missing.append(
                    "replace the requested observed table row with the exact quoted values"
                )
            elif not state.table_row_replacement_readback_satisfied():
                missing.append(
                    "save and read back the exact replacement values from the observed table row"
                )
        named_table_request = requested_named_slide_table(state.instruction)
        if named_table_request is not None:
            if state.named_slide_table_plan() is None:
                missing.append(
                    "inspect and resolve the uniquely titled slide and its empty content placeholder"
                )
            elif state.next_named_slide_table_action() is not None:
                missing.append(
                    "replace the empty content placeholder with the requested rows-by-columns table"
                )
            elif not state.named_slide_table_readback_satisfied():
                missing.append(
                    "save and read back one new table at the observed content-placeholder geometry"
                )
        image_edge_request = requested_image_edge_position(state.instruction)
        if image_edge_request is not None:
            if state.next_image_edge_position_action() is not None:
                missing.append(
                    "inspect the requested slide and move its unique observed image to the "
                    f"requested {image_edge_request['edge']} side"
                )
            elif not state.image_edge_position_readback_satisfied():
                missing.append(
                    "save and read back the target image at its observation-derived "
                    f"{image_edge_request['edge']} geometry"
                )
        table_edge_request = requested_table_edge_position(state.instruction)
        if table_edge_request is not None:
            if state.next_table_edge_position_action() is not None:
                missing.append(
                    "inspect the requested slide and move its unique observed table to the "
                    f"requested {table_edge_request['edge']} edge"
                )
            elif not state.table_edge_position_readback_satisfied():
                missing.append(
                    "save and read back the target table at its observation-derived "
                    f"{table_edge_request['edge']} geometry"
                )
        personal_cleanup_request = requested_title_range_personal_info_cleanup(
            state.instruction
        )
        if personal_cleanup_request is not None:
            if state.title_range_personal_info_cleanup_plan() is None:
                missing.append(
                    "inspect the requested title slides and personal-information slide"
                )
            elif state.next_title_range_personal_info_cleanup_action() is not None:
                missing.append(
                    "format each observed top title and delete observed personal information "
                    "with its geometrically associated icons"
                )
            elif not state.title_range_personal_info_cleanup_readback_satisfied():
                missing.append(
                    "save and read back the title styles and absence of personal-information shapes"
                )
        content_format_request = requested_slide_content_formatting(state.instruction)
        if content_format_request is not None:
            if state.slide_content_format_plan() is None:
                missing.append(
                    "inspect the target slide and resolve its content placeholders from "
                    "observed presentation shape kinds"
                )
            elif state.next_slide_content_format_action() is not None:
                missing.append(
                    "apply the exact requested font size and Impress palette color only to "
                    "the observed content shapes, then set the requested slide background"
                )
            elif not state.slide_content_format_readback_satisfied():
                missing.append(
                    "save and structurally read back the content font size/color and solid "
                    "slide background without changing the title"
                )
        role_text_request = requested_slide_role_text_formatting(state.instruction)
        if role_text_request is not None:
            if state.slide_role_text_format_plan() is None:
                missing.append(
                    "inspect the target slide and resolve its title, body, and table shapes "
                    "from observed presentation shape kinds"
                )
            elif state.next_slide_role_text_format_action() is not None:
                missing.append(
                    "apply the instruction-derived font color to every observed text role, "
                    "underline body text only, and leave title/table text not underlined"
                )
            elif not state.slide_role_text_format_readback_satisfied():
                missing.append(
                    "save and structurally read back the exact font color and role-scoped "
                    "underline state for title, body, other text, and table cells"
                )
        content_text = requested_content_textbox_insert(state.instruction)
        if content_text is not None and not state.content_textbox_readback_satisfied():
            missing.append(
                "final presentation.inspect after saving must show the exact quoted text in the "
                "content textbox on the requested slide"
            )
        indent_request = requested_matching_indent_without_bullet(state.instruction)
        if indent_request is not None and not state.matching_indent_satisfied():
            missing.append(
                "final presentation.inspect must show the exact target paragraph without a bullet and "
                "with the same visual indentation as at least one named reference paragraph"
            )
        period_rate_request = state.period_rate_request()
        if period_rate_request is not None:
            period_rate_plan = state.period_rate_plan()
            if period_rate_plan is None:
                missing.append(
                    "inspect and read the complete source table so the annual-rate and "
                    "periods-per-year columns can be resolved"
                )
            elif state.next_period_rate_action() is not None:
                missing.append(
                    "complete the instruction-derived numeric period-rate column, maximum-cell "
                    "font highlight, save, and structural read-back"
                )
            elif not state.period_rate_readback_satisfied():
                missing.append(
                    "final range.read must confirm every period-rate formula and the requested "
                    "font color on the actual maximum result"
                )
        merged_text_specs = state.merged_text_region_specs()
        if merged_text_specs:
            next_merged_text = state.next_merged_text_action()
            if next_merged_text is not None:
                expected = next_merged_text["arguments"]
                if next_merged_text["action"] == "range.merge":
                    missing.append(
                        "merge every instruction-derived region before completion; next missing region is "
                        f"{expected['sheet']}!{expected['range']}"
                    )
                elif next_merged_text["action"] == "range.write":
                    missing.append(
                        "write every instruction-derived merged-region label before completion; next "
                        f"missing anchor is {expected['sheet']}!{expected['range']}"
                    )
                else:
                    missing.append(
                        "apply every instruction-derived merged-region format before completion; next "
                        f"missing range is {expected['sheet']}!{expected['range']}"
                    )
            elif not state.merged_text_readback_satisfied():
                missing.append(
                    "final range.read after saving must contain every instruction-derived merged-region "
                    "label at its requested anchor"
                )
        annual_change_request = state.annual_percentage_change_request()
        if annual_change_request is not None:
            annual_change_plan = state.annual_percentage_change_plan()
            if annual_change_plan is None:
                missing.append(
                    "inspect and read the complete source table so the requested year column, source "
                    "headers, requested years, and each prior-year row can be resolved"
                )
            elif not state.annual_percentage_change_mutations_satisfied():
                next_step = state.next_annual_percentage_change_action()
                missing.append(
                    "complete the instruction-derived annual percentage-change table, including exact "
                    f"headers, cross-sheet formulas, and percentage formatting; next step is {next_step}"
                )
            elif not state.annual_percentage_change_readback_satisfied():
                missing.append(
                    "save and read back the complete annual percentage-change table; verify every "
                    "requested header/year, prior-year formula, and percentage-formatted result"
                )
        monthly_totals_request = state.monthly_column_totals_request()
        if monthly_totals_request is not None:
            monthly_totals_plan = state.monthly_column_totals_plan()
            if monthly_totals_plan is None:
                missing.append(
                    "inspect and read the complete source table so every observed month column and "
                    "its data-row bounds can be resolved"
                )
            elif not state.monthly_column_totals_mutations_satisfied():
                next_step = state.next_monthly_column_totals_action()
                missing.append(
                    "complete the instruction-derived monthly totals table with exact headers, "
                    f"month labels, and full-column SUM formulas; next step is {next_step}"
                )
            elif not state.monthly_column_totals_readback_satisfied():
                missing.append(
                    "save and read back the complete monthly totals table; verify every observed "
                    "month label and source-range-derived SUM formula"
                )
        if requests_appended_named_rows(state.instruction):
            written_labels = state.written_row_labels()
            missing_labels = [
                label
                for label in requested_row_labels(state.instruction)
                if label.casefold() not in written_labels
            ]
            if missing_labels:
                missing.append(
                    "write every requested named output row; still missing "
                    f"{missing_labels}"
                )
        sheet_lifecycle = requested_sheet_copy_lifecycle(state.instruction)
        if sheet_lifecycle is not None:
            plan = state.sheet_copy_lifecycle_plan()
            if plan is None:
                missing.append(
                    "inspect the workbook before resolving instruction sheet names, copy name, "
                    "and relative insertion position"
                )
            elif not state.sheet_copy_lifecycle_mutations_satisfied():
                expected = state.next_sheet_copy_lifecycle_action()
                missing.append(
                    "complete every instruction-derived sheet rename/copy step in order; "
                    f"next required step is {expected}"
                )
            elif not state.sheet_copy_lifecycle_readback_satisfied():
                missing.append(
                    "save and inspect the workbook after all sheet operations; final sheet order "
                    f"must be exactly {plan['final_names']}"
                )
        sheet_renames = requested_sheet_renames(state.instruction)
        if sheet_renames:
            observed_names = state.latest_workbook_sheet_names()
            observed_normalized = {name.casefold(): name for name in observed_names}
            for rename in sheet_renames:
                source_normalized = re.sub(r"\s+", "", rename["source"]).casefold()
                matching_events = [
                    event
                    for event in state.successful_action_events("sheet.rename")
                    if re.sub(
                        r"\s+",
                        "",
                        str(event.proposed.get("arguments", {}).get("sheet", "")),
                    ).casefold()
                    == source_normalized
                    and str(event.proposed.get("arguments", {}).get("new_name", ""))
                    == rename["target"]
                ]
                if not matching_events:
                    missing.append(
                        f"rename sheet {rename['source']!r} to {rename['target']!r} with a successful "
                        "sheet.rename action"
                    )
                if rename["target"].casefold() not in observed_normalized:
                    missing.append(
                        f"final workbook.inspect must contain renamed sheet {rename['target']!r}"
                    )
        pivot_count = requested_pivot_count(state.instruction)
        if pivot_count is not None:
            actual_pivots = state.successful_pivot_count()
            if actual_pivots < pivot_count:
                missing.append(
                    f"create {pivot_count} pivot table(s); only {actual_pivots} successful pivot.create action(s) are recorded"
                )
            elif (
                state.stacked_percentage_pivot_specs()
                and not state.stacked_percentage_pivot_readback_satisfied()
            ):
                missing.append(
                    "save and read back the full stacked percentage-pivot layout, including each "
                    "instruction-derived field and requested blank separator row"
                )
        chart_count = requested_chart_count(state.instruction)
        actual_charts = state.successful_chart_count()
        if actual_charts < chart_count:
            missing.append(
                f"create {chart_count} chart(s); only {actual_charts} successful chart.create action(s) are recorded"
            )
        if (
            chart_count
            and state.axis_chart_spec() is not None
            and not state.axis_chart_readback_satisfied()
        ):
            missing.append(
                "final workbook.inspect must confirm the requested X/Y chart source ranges, "
                "header flags, and diagram type after saving"
            )
        missing.extend(calc_semantics.sort_completion_missing(state))
        missing.extend(impress_semantics.completion_missing(state))
        if (
            chart_count
            and state.new_sheet_chart_spec() is not None
            and not state.new_sheet_chart_readback_satisfied()
        ):
            missing.append(
                "final workbook.inspect must confirm the chart target sheet, source sheet, source "
                "range, title, type, and header flags after saving"
            )
        decimal_spec = state.decimal_separator_spec()
        if (
            decimal_spec is not None
            and not state.decimal_separator_readback_satisfied()
        ):
            missing.append(
                "final range.read after saving must confirm the requested comma decimal separator "
                "and preserved decimal precision on the numeric data region"
            )
        duplicate_count = requested_last_slide_duplicate_count(state.instruction)
        actual_duplicates = len(state.successful_action_events("slide.duplicate"))
        if duplicate_count is not None and actual_duplicates < duplicate_count:
            missing.append(
                f"duplicate {duplicate_count} slide(s); only {actual_duplicates} successful "
                "slide.duplicate action(s) are recorded"
            )
        if requested_cover_image_slide(state.instruction) is not None:
            if not state.cover_image_mutation_applied():
                missing.append(
                    "fit the requested image to the full slide with proportional cover mode"
                )
            elif not state.cover_image_readback_satisfied():
                missing.append(
                    "final presentation.inspect must confirm the requested image is proportionally "
                    "centered and covers the entire slide"
                )
        if state.domain in {
            "libreoffice_impress",
            "multi_apps",
        } and requests_presentation_audio_insertion(state.instruction):
            if not state.successful_action_events("audio.insert"):
                missing.append(
                    "insert the requested Desktop audio file into the presentation"
                )
            elif not state.audio_insert_readback_satisfied():
                missing.append(
                    "final presentation.inspect after saving must confirm the requested audio MediaShape URL"
                )
        if requested_ordered_image_slides(state.instruction) is not None:
            if not state.ordered_image_slide_mutations_satisfied():
                missing.append(
                    "finish the instruction-derived numbered image workflow: exact slide count, blank "
                    "template, and one ordered image per slide"
                )
            elif not state.ordered_image_slide_readback_satisfied():
                missing.append(
                    "final presentation.inspect after saving must confirm the exact slide count and one "
                    "ordered source image as the only shape on every slide"
                )
        requests_single_page = state.domain == "libreoffice_calc" and bool(
            re.search(
                r"(?is)\b(?:fit|resize)\b.{0,100}\b(?:one|1)\s+page\b",
                state.instruction,
            )
        )
        if requests_single_page and not any(
            event.proposed.get("arguments", {}).get("pages_wide", 1) == 1
            and event.proposed.get("arguments", {}).get("pages_tall", 1) == 1
            for event in state.successful_action_events("page.fit_to_pages")
        ):
            missing.append(
                "fit the requested Calc sheet to one page wide and one page tall"
            )
        export_format = requested_calc_export_format(state.instruction)
        if export_format is not None:
            export_spec = state.requested_calc_export_spec()
            matching_export = any(
                str(event.proposed.get("arguments", {}).get("format", "")).lower()
                == export_format
                and (
                    export_spec is None
                    or all(
                        event.proposed.get("arguments", {}).get(key) == value
                        for key, value in export_spec.items()
                    )
                )
                for event in state.successful_action_events("workbook.export")
            )
            if not matching_export:
                missing.append(
                    "export the Calc workbook to the requested PDF path"
                    if export_format == "pdf"
                    else "export the current Calc sheet to the requested CSV path"
                )
        files = state.requested_save_files()
        if files:
            file_evidence_results = [
                json.dumps(event.result, ensure_ascii=False, default=str).lower()
                for event in successful
                if is_save(event.proposed["action"])
                or state.event_has_save_evidence(event)
                or event.proposed["action"] in {"compose.attach", "media.extract_frame"}
            ]
            for filename in files:
                if not any(
                    filename.lower() in result for result in file_evidence_results
                ):
                    missing.append(
                        f"successful save/export result does not reference requested file {filename}"
                    )
            if "desktop" in state.instruction.lower() and not any(
                "/desktop/" in result for result in file_evidence_results
            ):
                missing.append(
                    "successful save/export result does not reference the Desktop directory"
                )
        return {"passed": not missing, "missing": missing}

    @staticmethod
    def _generic_completion_gate(
        state: RuntimeState,
        completion: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Apply only generic evidence checks for strict episodes."""
        return strict_completion_gate(
            state,
            completion,
            instruction_actions=strict_instruction_required_actions,
            legacy_actions=FORBIDDEN_DATASET_ACTIONS,
            is_read_only_action=is_read_only,
            is_save_action=is_save,
            relevance_score=action_relevance_score,
            semantic_requirement_errors=strict_semantic_requirement_errors,
            semantic_action_equivalents=strict_semantic_action_equivalents,
        )
