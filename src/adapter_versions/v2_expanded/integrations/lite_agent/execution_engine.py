"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations
import copy
import json
import time
from typing import Any
import jsonschema
from . import (
    batch_table_semantics,
    calc_semantics,
    completion_recovery,
    impress_cover_semantics,
    impress_table_row,
    spreadsheet_open_semantics,
    verified_artifact_handoff,
)
from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
    utc_now,
)
from .completion_policy import (
    action_is_read_only as is_read_only,
    canonical_action_request,
    command_is_read_only,
    effective_canonical_action,
    completion_claim_contradictions as completion_claim_contradictions,
    completion_response_contract_errors,
)
from .clipboard_path_semantics import (
    argument_contract_errors as clipboard_path_argument_contract_errors,
)
from .gui_policy import repeated_gui_action_error
from .gui_actions import GUI_REQUEST_SCHEMA, build_gui_command
from .impress_background import background_argument_contract_errors
from .impress_page_number import page_number_argument_contract_errors
from .impress_role_formatting import multislide_role_argument_contract_errors
from .impress_role_text_update import role_text_update_argument_contract_errors
from .impress_title_formatting import title_format_argument_contract_errors
from .impress_image_insertion import image_insertion_argument_contract_errors
from .impress_personal_information import personal_information_argument_contract_errors
from .impress_textboxes import textbox_color_argument_contract_errors
from .instruction_semantics import strict_instruction_required_actions
from .semantic_requirements import strict_semantic_action_equivalents
from .standard_location_semantics import (
    argument_contract_errors as standard_location_argument_contract_errors,
)
from .workspace_open_semantics import (
    argument_contract_errors as workspace_open_argument_contract_errors,
)
from .generic_routing import (
    discovered_adapter_routes,
    recovery_blocked_actions,
)
from .recovery_surface import last_failure_summary
from .request_blocks import request_block_is_stale
from .context_projection import safe_action
from .safety import sanitize_agent_visible_result, sanitize_gui_result_for_model
from .tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    FORBIDDEN_DATASET_ACTIONS,
    action_from_tool_name,
    build_tools,
    search_actions,
    tool_name,
)
from .tool_validation import validate_model_visible_tool_arguments
from .runtime_policy import (
    ACTION_BLOCK_WINDOW_STEPS,
    RepeatedRequestBlocked,
    argument_signature,
    error_signature,
)
from .state_model import ExecutionEvent, RuntimeState


def _visual_rename_underscore_error(
    state: RuntimeState, action: str, arguments: dict[str, Any]
) -> str | None:
    """Reject underscore substitutions when the visual task explicitly forbids them."""
    instruction = str(getattr(state, "instruction", "")).casefold()
    if (
        getattr(state, "domain", None) != "multi_apps"
        or action != "adapter.call"
        or "underscore" not in instruction
        or "space" not in instruction
    ):
        return None
    route_action = arguments.get("action")
    payload = arguments.get("payload")
    params = payload.get("params") if isinstance(payload, dict) else None
    destination = params.get("destination") if isinstance(params, dict) else None
    if route_action == "filesystem.rename" and isinstance(destination, str):
        if "_" in destination.rsplit("/", 1)[-1]:
            return (
                "The instruction requires literal spaces in the filename; do not replace "
                "spaces with underscores in filesystem.rename destination."
            )
    return None


def _ocr_expense_entries(state: RuntimeState) -> list[float]:
    """Collect structured OCR expense amounts already observed in this episode."""
    def walk(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, dict):
            files = value.get("files")
            if isinstance(files, list) and any(
                isinstance(item, dict) and isinstance(item.get("expense_entry"), dict)
                for item in files
            ):
                return [item for item in files if isinstance(item, dict)]
            for child in value.values():
                found = walk(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found:
                    return found
        return []

    for event in reversed(state.events):
        if not event.executed or event.error:
            continue
        files = walk(event.result)
        amounts = []
        for item in files:
            entry = item.get("expense_entry")
            amount = entry.get("amount") if isinstance(entry, dict) else None
            if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                amounts.append(float(amount))
        if amounts:
            return amounts
    return []


def _normalize_ocr_ledger_write(state: RuntimeState, arguments: dict[str, Any]) -> dict[str, Any]:
    """Build a generic ledger append from observed OCR expense entries."""
    if state.domain != "multi_apps" or arguments.get("action") != "range.write":
        return arguments
    if arguments.get("adapter") != "libreoffice_calc":
        return arguments
    payload = arguments.get("payload")
    params = payload.get("params") if isinstance(payload, dict) else None
    if not isinstance(params, dict):
        return arguments
    amounts = _ocr_expense_entries(state)
    if not amounts:
        return arguments
    values = params.get("values")
    if not isinstance(values, list) or len(values) < 2:
        return arguments
    target = params.get("range", params.get("used_range_a1"))
    import re
    match = re.search(r"[A-Za-z]+\$?(\d+)", str(target))
    start_row = int(match.group(1)) if match else 1
    normalized = copy.deepcopy(arguments)
    normalized_params = normalized["payload"]["params"]
    normalized_values = []
    for offset, amount in enumerate(amounts):
        row = start_row + offset
        normalized_values.append([
            "",
            "",
            "Expense",
            amount,
            {"kind": "formula", "value": f"=E{row - 1}+D{row}"},
        ])
    normalized_params["values"] = normalized_values
    return normalized


def _strict_search_semantic_actions(state: RuntimeState) -> list[str]:
    """Include declared public alternatives when disambiguating catalog results."""
    required = strict_instruction_required_actions(state.domain, state.instruction)
    equivalents = strict_semantic_action_equivalents(state)
    return list(
        dict.fromkeys(
            [
                candidate
                for action in required
                for candidate in (action, *sorted(equivalents.get(action, set())))
            ]
        )
    )


def _is_read_only_adapter_event(event: Any, default_domain: str) -> bool:
    """Classify a prior adapter event without treating read-only commands as writes."""
    _domain, action, arguments = effective_canonical_action(event, default_domain)
    return is_read_only(action) or command_is_read_only(action, arguments)


def _model_visible_recovery_blocks(
    blocks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project block state without exposing internal request/error signatures.

    Signatures are useful for duplicate detection inside the Runner, but they
    are opaque implementation details and have no value for model planning.
    Keep only bounded status fields and a generic reason in the model-facing
    search result; the complete block remains in the immutable event ledger.
    """
    visible: list[dict[str, Any]] = []
    for block in blocks.values():
        if not isinstance(block, dict):
            continue
        scope = block.get("block_scope")
        item: dict[str, Any] = {
            "action": safe_action(block.get("action")),
            "block_scope": scope if scope in {"window", "episode"} else "window",
            "fallback_reason": "choose different arguments or another public action",
        }
        for key in ("blocked_at_step", "blocked_until_step"):
            value = block.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                item[key] = value
        visible.append(item)
    return visible


class ExecutionEngineMixin:
    @staticmethod
    def _validate_adapter_arguments(
        domain: str,
        action: str,
        arguments: dict[str, Any],
        *,
        strict_generic: bool = False,
    ) -> None:
        direct_schema = DIRECT_ACTION_SCHEMAS.get(domain, {}).get(action)
        if direct_schema is not None:
            schema = {
                "type": "object",
                "properties": direct_schema["properties"],
                # Compatibility schemas may express required fields only in
                # oneOf branches; strict overlays provide their own required
                # list. Treat an omitted top-level list as empty here.
                "required": list(direct_schema.get("required", [])),
                "additionalProperties": False,
            }
            for keyword in ("allOf", "anyOf", "oneOf"):
                if keyword in direct_schema:
                    schema[keyword] = direct_schema[keyword]
            if strict_generic:
                strict_tool = next(
                    (
                        tool
                        for tool in build_tools(
                            domain,
                            [action],
                            include_gui=False,
                            include_control_tools=False,
                            strict_generic=True,
                        )
                        if tool["function"]["name"] == tool_name(action)
                    )
                )
                schema = strict_tool["function"]["parameters"]
            jsonschema.validate(arguments, schema)
            return
        for key in ("params", "target", "document"):
            if key in arguments and (not isinstance(arguments[key], dict)):
                raise ValueError(
                    f"{key} must be an object, got {type(arguments[key]).__name__}"
                )
        if "verify" in arguments and (
            not isinstance(arguments["verify"], list)
            or any((not isinstance(item, dict) for item in arguments["verify"]))
        ):
            raise ValueError("verify must be an array of objects")
        if "timeout_ms" in arguments and (
            isinstance(arguments["timeout_ms"], bool)
            or not isinstance(arguments["timeout_ms"], int)
            or (not 100 <= arguments["timeout_ms"] <= 120000)
        ):
            raise ValueError("timeout_ms must be an integer between 100 and 120000")

    @staticmethod
    def _gui_command(arguments: dict[str, Any]) -> str:
        return build_gui_command(arguments)

    def _execute_holo_gui_request(
        self,
        arguments: dict[str, Any],
        screenshot: bytes | None,
    ) -> dict[str, Any]:
        """Run one planner GUI delegation through the configured Holo boundary."""
        if screenshot is None:
            raise ValueError(
                "gui_request requires the latest screenshot for Holo grounding"
            )
        if not isinstance(screenshot, (bytes, bytearray, memoryview)) or not screenshot:
            raise ValueError("gui_request requires non-empty screenshot bytes")
        gateway = getattr(self, "holo_gui_gateway", None)
        if gateway is not None:
            result = gateway(arguments, bytes(screenshot))
        else:
            grounder = getattr(self, "holo_grounder", None)
            executor = getattr(self, "gui_executor", None)
            if grounder is None:
                raise RuntimeError("Holo GUI delegation is not configured")
            if executor is None:
                raise RuntimeError("GUI executor is not configured")
            # Import lazily so the legacy direct-GUI path does not load Holo's
            # optional visual client or image decoder.
            from integrations.holo_agent.gateway import HoloGuiGateway

            result = HoloGuiGateway(grounder, executor).execute(
                arguments, bytes(screenshot)
            )
        if not isinstance(result, dict):
            raise ValueError("Holo GUI gateway must return an object")
        return result

    @staticmethod
    def _holo_audit_arguments(result: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the bounded coordinate-bearing action for the audit ledger."""
        nested = result.get("result")
        if isinstance(nested, dict) and isinstance(nested.get("grounded_action"), dict):
            return copy.deepcopy(nested["grounded_action"])
        prepared = result.get("prepared_action")
        if isinstance(prepared, dict):
            model_arguments = prepared.get("model_arguments")
            name = prepared.get("name")
            if isinstance(model_arguments, dict) and isinstance(name, str):
                return {"action": name, **copy.deepcopy(model_arguments)}
        grounding = result.get("grounding")
        if isinstance(grounding, dict):
            name = grounding.get("name")
            model_arguments = grounding.get("arguments")
            if isinstance(name, str) and isinstance(model_arguments, dict):
                return {"action": name, **copy.deepcopy(model_arguments)}
        return None

    def execute_proposal(
        self,
        state: RuntimeState,
        proposal: dict[str, Any],
        screenshot_before: str | None = None,
        screenshot: bytes | None = None,
    ) -> ExecutionEvent:
        started = time.monotonic()
        model_visible_tools = proposal.get("_model_visible_tools")
        recorded_proposal = {
            key: value
            for key, value in proposal.items()
            if key != "_model_visible_tools"
        }
        if model_visible_tools is not None:
            recorded_proposal["model_visible_schema_enforced"] = True
        event = ExecutionEvent(
            step=len(state.events) + 1,
            timestamp_utc=utc_now(),
            proposed=recorded_proposal,
            screenshot_before=screenshot_before,
        )
        tool = proposal.get("tool")
        if tool == "propose_done":
            event.proposed["kind"] = "completion"
        try:
            arguments = json.loads(proposal.get("arguments_raw") or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must decode to an object")
            model_arguments = copy.deepcopy(arguments)
            event.parsed = True
            event.proposed["arguments"] = arguments
            action = action_from_tool_name(state.domain, str(tool))
            if action:
                if action in FORBIDDEN_DATASET_ACTIONS:
                    raise ValueError(
                        f"task-specific Adapter action is disabled in strict mode: {action}"
                    )
                event.proposed.update({"kind": "adapter", "action": action})
                if model_visible_tools is not None:
                    if not isinstance(model_visible_tools, list):
                        raise ValueError(
                            "captured model-visible tools must be an array"
                        )
                    validate_model_visible_tool_arguments(
                        model_visible_tools, str(tool), arguments
                    )
                elif action not in set(self.selected_actions(state)):
                    raise ValueError(
                        f"action is not in current Top-K exposure: {action}"
                    )
                if action == "adapter.call" and state.domain == "multi_apps":
                    # A constrained surface with one discovered route exposes
                    # only its payload. Reattach the server-selected route at
                    # dispatch while retaining the exact model payload in the
                    # event ledger.
                    if "adapter" not in arguments or "action" not in arguments:
                        routes = []
                        for visible_tool in model_visible_tools or []:
                            if not isinstance(visible_tool, dict):
                                continue
                            visible_function = visible_tool.get("function")
                            if not isinstance(visible_function, dict):
                                continue
                            if visible_function.get("name") != str(tool):
                                continue
                            visible_parameters = visible_function.get("parameters")
                            route_hint = (
                                visible_parameters.get("x-route")
                                if isinstance(visible_parameters, dict)
                                else None
                            )
                            if (
                                isinstance(route_hint, dict)
                                and isinstance(route_hint.get("adapter"), str)
                                and isinstance(route_hint.get("action"), str)
                            ):
                                routes = [
                                    (route_hint["adapter"], route_hint["action"])
                                ]
                            break
                        if not routes:
                            routes = discovered_adapter_routes(state)
                        if len(routes) == 1 and isinstance(
                            arguments.get("payload"), dict
                        ):
                            adapter, downstream_action = routes[0]
                            event.proposed["model_arguments"] = model_arguments
                            event.proposed["arguments_source"] = (
                                "single_discovered_adapter_route"
                            )
                            arguments = {
                                "adapter": adapter,
                                "action": downstream_action,
                                "payload": arguments["payload"],
                            }
                            event.proposed["arguments"] = arguments
                    discovered_routes = discovered_adapter_routes(state)
                    route = (arguments.get("adapter"), arguments.get("action"))
                    # Some OpenAI-compatible tool decoders retain the wrapper
                    # name in the nested action field even after a single
                    # route has been exposed. Preserve the model payload and
                    # bind only that already discovered route.
                    if (
                        route not in discovered_routes
                        and arguments.get("action") == "adapter.call"
                        and len(discovered_routes) == 1
                        and isinstance(arguments.get("payload"), dict)
                    ):
                        adapter, downstream_action = discovered_routes[0]
                        event.proposed["model_arguments"] = model_arguments
                        event.proposed["arguments_source"] = (
                            "nested_wrapper_single_discovered_adapter_route"
                        )
                        arguments = {
                            "adapter": adapter,
                            "action": downstream_action,
                            "payload": arguments["payload"],
                        }
                        event.proposed["arguments"] = arguments
                        route = (adapter, downstream_action)
                    if route in discovered_routes:
                        payload = arguments.get("payload")
                        params = payload.get("params") if isinstance(payload, dict) else None
                        if isinstance(params, dict) and isinstance(params.get("target"), dict):
                            target_action = params["target"].get("action")
                            if target_action == route[1]:
                                cleaned = dict(params)
                                cleaned.pop("target", None)
                                arguments = {**arguments, "payload": {**payload, "params": cleaned}}
                                event.proposed["model_arguments"] = model_arguments
                                event.proposed["arguments_source"] = "removed_nested_route_wrapper"
                                event.proposed["arguments"] = arguments
                    if route not in discovered_routes:
                        raise ValueError(
                            "multi_apps.adapter.call requires a matching public "
                            "tools_search result before execution"
                        )
                merged_text_step = state.next_merged_text_action()
                sheet_lifecycle_step = state.next_sheet_copy_lifecycle_action()
                annual_change_step = state.next_annual_percentage_change_action()
                monthly_totals_step = state.next_monthly_column_totals_action()
                scaled_display_step = state.next_scaled_number_display_action()
                labeled_concatenation_step = state.next_labeled_concatenation_action()
                period_rate_step = state.next_period_rate_action()
                stacked_pivot_step = state.next_stacked_percentage_pivot_action()
                all_slide_background_arguments = state.all_slide_background_arguments()
                title_edge_step = state.next_title_edge_position_action()
                title_update_step = state.next_slide_title_update_action()
                title_format_step = state.next_slide_title_format_action()
                sized_image_step = None
                picture_heights_step = state.next_picture_heights_by_slide_action()
                table_row_step = None
                named_table_step = state.next_named_slide_table_action()
                image_edge_step = state.next_image_edge_position_action()
                table_edge_step = state.next_table_edge_position_action()
                personal_cleanup_step = None
                role_text_step = state.next_slide_role_text_format_action()
                content_format_step = state.next_slide_content_format_action()
                calc_summary_step = (
                    annual_change_step
                    or monthly_totals_step
                    or scaled_display_step
                    or labeled_concatenation_step
                    or period_rate_step
                )
                merged_text_step = None
                sheet_lifecycle_step = None
                annual_change_step = None
                monthly_totals_step = None
                scaled_display_step = None
                labeled_concatenation_step = None
                period_rate_step = None
                stacked_pivot_step = None
                all_slide_background_arguments = None
                title_edge_step = None
                title_update_step = None
                title_format_step = None
                sized_image_step = None
                picture_heights_step = None
                table_row_step = None
                named_table_step = None
                image_edge_step = None
                table_edge_step = None
                personal_cleanup_step = None
                role_text_step = None
                content_format_step = None
                calc_summary_step = None
                if (
                    calc_summary_step is not None
                    and calc_summary_step["action"] == action
                ):
                    arguments = copy.deepcopy(calc_summary_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_source_table_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    action == "slide.set_background"
                    and all_slide_background_arguments is not None
                    and (not state.successful_action_events("slide.set_background"))
                ):
                    arguments = copy.deepcopy(all_slide_background_arguments)
                    event.proposed["arguments_source"] = "instruction_derived_scope"
                    event.proposed["arguments"] = arguments
                if title_edge_step is not None and action == title_edge_step["action"]:
                    arguments = copy.deepcopy(title_edge_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    title_update_step is not None
                    and action == title_update_step["action"]
                ):
                    arguments = copy.deepcopy(title_update_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    title_format_step is not None
                    and action == title_format_step["action"]
                ):
                    arguments = copy.deepcopy(title_format_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    sized_image_step is not None
                    and action == sized_image_step["action"]
                ):
                    arguments = copy.deepcopy(sized_image_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    picture_heights_step is not None
                    and action == picture_heights_step["action"]
                ):
                    arguments = copy.deepcopy(picture_heights_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if table_row_step is not None and action == table_row_step["action"]:
                    arguments = copy.deepcopy(table_row_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    named_table_step is not None
                    and action == named_table_step["action"]
                ):
                    arguments = copy.deepcopy(named_table_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if image_edge_step is not None and action == image_edge_step["action"]:
                    arguments = copy.deepcopy(image_edge_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if table_edge_step is not None and action == table_edge_step["action"]:
                    arguments = copy.deepcopy(table_edge_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    personal_cleanup_step is not None
                    and action == personal_cleanup_step["action"]
                ):
                    arguments = copy.deepcopy(personal_cleanup_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if role_text_step is not None and action == role_text_step["action"]:
                    arguments = copy.deepcopy(role_text_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    content_format_step is not None
                    and action == content_format_step["action"]
                ):
                    arguments = copy.deepcopy(content_format_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_presentation_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    sheet_lifecycle_step is not None
                    and sheet_lifecycle_step["action"] == action
                    and (action in {"sheet.rename", "sheet.copy"})
                ):
                    arguments = copy.deepcopy(sheet_lifecycle_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_workbook_observation"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    merged_text_step is not None
                    and merged_text_step["action"] == action
                    and (action in {"range.merge", "range.write", "range.format"})
                ):
                    arguments = copy.deepcopy(merged_text_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_derived_state_step"
                    )
                    event.proposed["arguments"] = arguments
                if (
                    action == "pivot.create"
                    and stacked_pivot_step is not None
                    and (stacked_pivot_step["action"] == action)
                ):
                    arguments = copy.deepcopy(stacked_pivot_step["arguments"])
                    event.proposed["arguments_source"] = (
                        "instruction_and_source_table_observation"
                    )
                    event.proposed["arguments"] = arguments
                self._validate_adapter_arguments(
                    state.domain, action, arguments, strict_generic=True
                )
                semantic_argument_errors = background_argument_contract_errors(
                    state, action, arguments
                )
                visual_rename_error = _visual_rename_underscore_error(
                    state, action, arguments
                )
                if visual_rename_error:
                    semantic_argument_errors.append(visual_rename_error)
                semantic_argument_errors.extend(
                    page_number_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    textbox_color_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    multislide_role_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    role_text_update_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    title_format_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    image_insertion_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    personal_information_argument_contract_errors(
                        state, action, arguments
                    )
                )
                semantic_argument_errors.extend(
                    standard_location_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    clipboard_path_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    workspace_open_argument_contract_errors(state, action, arguments)
                )
                semantic_argument_errors.extend(
                    spreadsheet_open_semantics.argument_contract_errors(
                        state, action, arguments
                    )
                )
                semantic_argument_errors.extend(
                    batch_table_semantics.argument_contract_errors(
                        state, action, arguments
                    )
                )
                semantic_argument_errors.extend(
                    verified_artifact_handoff.argument_contract_errors(
                        state, action, arguments
                    )
                )
                semantic_argument_errors.extend(
                    impress_cover_semantics.argument_contract_errors(
                        state, action, arguments
                    )
                )
                semantic_argument_errors.extend(
                    impress_table_row.argument_contract_errors(state, action, arguments)
                )
                if action == "table.sort":
                    calc_semantics.validate_sort_arguments(state, action, arguments)
                if semantic_argument_errors:
                    raise ValueError("; ".join(semantic_argument_errors))
                if action == "media.extract_audio" and "profile" in arguments:
                    raise ValueError(
                        "dataset-specific media extraction profiles are disabled in strict mode"
                    )
                route_dispatch_normalized = (
                    event.proposed.get("arguments_source")
                    == "single_discovered_adapter_route"
                )
                if (
                    (arguments != model_arguments and not route_dispatch_normalized)
                    or (
                        event.proposed.get("arguments_source") is not None
                        and not route_dispatch_normalized
                    )
                ):
                    raise RuntimeError(
                        "strict generic-only execution cannot rewrite or inject model arguments"
                    )
                active_block = state.active_request_block(action, arguments)
                if active_block is not None:
                    event.validated = True
                    raise RepeatedRequestBlocked(
                        {
                            "type": "RepeatedActionBlocked",
                            "detail": "this action and normalized argument combination is blocked for the remainder of the episode after reaching the same structured error twice; change the arguments or choose another action",
                            "executed": False,
                            "previous_step": active_block["blocked_at_step"],
                            "previous_error": active_block.get("previous_error"),
                            "blocked_action": action,
                            "argument_signature": active_block["argument_signature"],
                            "error_signature": active_block["error_signature"],
                            "block_scope": active_block["block_scope"],
                            "fallback_reason": "same_action_same_arguments_same_error_twice",
                        }
                    )
                current_identity = canonical_action_request(
                    state.domain, action, arguments
                )
                duplicate = next(
                    (
                        previous
                        for previous in reversed(state.events)
                        if previous.executed
                        and previous.proposed.get("kind") == "adapter"
                        and effective_canonical_action(previous, state.domain)
                        == current_identity
                    ),
                    None,
                )
                mutation_after_duplicate = bool(
                    duplicate is not None
                    and any(
                        (
                            previous.step > duplicate.step
                            and previous.executed
                            and (
                                previous.proposed.get("kind") == "gui"
                                or (
                                    previous.proposed.get("kind") == "adapter"
                                    and (
                                        not _is_read_only_adapter_event(
                                            previous, state.domain
                                        )
                                    )
                                )
                            )
                            for previous in state.events
                        )
                    )
                )
                if (
                    duplicate is not None
                    # Removing a shape shifts collection positions: the same
                    # selector can now identify another live object to delete.
                    and current_identity[:2] != ("libreoffice_impress", "shape.delete")
                    and not (
                        is_read_only(current_identity[1])
                        or command_is_read_only(
                            current_identity[1], current_identity[2]
                        )
                    )
                    and not mutation_after_duplicate
                    and not spreadsheet_open_semantics.inspection_retry_required(
                        state, action, arguments
                    )
                ):
                    raise ValueError(
                        f"identical successful action already executed at step {duplicate.step}; inspect state or choose a different action"
                    )
                normalized_arguments = _normalize_ocr_ledger_write(state, arguments)
                if normalized_arguments is not arguments:
                    event.proposed["model_arguments"] = model_arguments
                    event.proposed["arguments_source"] = "observed_ocr_expense_entries"
                    arguments = normalized_arguments
                    event.proposed["arguments"] = arguments
                event.validated = True
                result = self.adapter_executor.execute(
                    state.domain,
                    action,
                    arguments,
                    {"task_id": state.task_id, "step": event.step},
                )
                event.executed = bool(result.get("executed"))
                event.result = result.get("result") if event.executed else None
                event.error = result.get("error") if not event.executed else None
            elif tool == "tools_search":
                event.validated = True
                active_blocks = state.active_request_blocks()
                excluded_actions = recovery_blocked_actions(state)
                excluded_routes = state.blocked_routes()
                failure_summary = last_failure_summary(state)
                # Feed retrieval only coarse failure fields. Including the
                # failed action itself would boost that same action's lexical
                # score and recreate the recovery attractor we are removing.
                previous_error = (
                    {
                        key: value
                        for key, value in failure_summary.items()
                        if key != "action"
                    }
                    if failure_summary
                    else None
                )
                completed_routes = {
                    effective_canonical_action(event, state.domain)[:2]
                    for event in state.events
                    if event.executed
                    and not event.error
                    and event.proposed.get("kind") == "adapter"
                }
                search_limit = 5 if active_blocks else 6
                matches = search_actions(
                    state.domain,
                    arguments["query"],
                    limit=search_limit,
                    instruction=state.instruction,
                    stage_actions=self.selected_actions(state),
                    semantic_actions=_strict_search_semantic_actions(state),
                    recent_error=json.dumps(
                        previous_error, ensure_ascii=False, default=str
                    ),
                    excluded_actions=excluded_actions,
                    excluded_routes=excluded_routes,
                    strict_generic=True,
                    completed_routes=completed_routes,
                )
                state.expanded_actions = list(
                    dict.fromkeys(
                        [*state.expanded_actions, *(item["action"] for item in matches)]
                    )
                )
                event.executed = True
                event.proposed["kind"] = "catalog"
                visible_matches = [
                    {key: value for key, value in item.items() if key != "signature"}
                    for item in matches
                ]
                event.result = {
                    "status": "ok",
                    "executed": True,
                    "routing_guidance": (
                        "Executable routes are listed below. Call one listed adapter route now; "
                        "do not call tools_search again while a route is available."
                    ),
                    "matches": visible_matches,
                    "recovery": {
                        "trigger": "repeated_action" if active_blocks else None,
                        "excluded_actions": sorted(
                            {str(safe_action(action)) for action in excluded_actions}
                        ),
                        "excluded_routes": [
                            {
                                "adapter": safe_action(adapter),
                                "action": safe_action(action),
                            }
                            for adapter, action in sorted(excluded_routes)
                        ],
                        "blocks": _model_visible_recovery_blocks(active_blocks),
                        "last_failure": last_failure_summary(state),
                        "search_limit": search_limit,
                        "fallback_reason": "the same action and normalized arguments reached the same structured error twice; retry only with materially different arguments, choose another generic action, use GUI fallback, or fail explicitly"
                        if active_blocks
                        else None,
                    },
                }
            elif tool == "gui_action":
                if self.gui_executor is None:
                    raise RuntimeError("GUI executor is not configured")
                gui_contract_errors = (
                    spreadsheet_open_semantics.gui_request_contract_errors(state)
                )
                if gui_contract_errors:
                    raise ValueError(gui_contract_errors[0])
                event.validated = True
                command = self._gui_command(arguments)
                event.proposed.update({"kind": "gui", "command": command})
                event.proposed["gui_arguments"] = copy.deepcopy(arguments)
                if policy_error := repeated_gui_action_error(
                    state.events,
                    command=command,
                    arguments=arguments,
                    step=event.step,
                    block_window_steps=ACTION_BLOCK_WINDOW_STEPS,
                ):
                    raise RepeatedRequestBlocked(policy_error)
                result = self.gui_executor(
                    {**arguments, "command": event.proposed["command"]}
                )
                event.executed = bool(result.get("executed"))
                event.result = (
                    sanitize_gui_result_for_model(result.get("result"))
                    if event.executed
                    else None
                )
                event.error = result.get("error") if not event.executed else None
            elif tool == "gui_request":
                # The planner selects only the visual intent. Holo supplies the
                # coordinate-bearing action; the common GUI gateway executes it
                # and returns a result that is audited on the next turn.
                jsonschema.validate(arguments, GUI_REQUEST_SCHEMA)
                gui_contract_errors = (
                    spreadsheet_open_semantics.gui_request_contract_errors(
                        state, arguments.get("intent")
                    )
                )
                if gui_contract_errors:
                    raise ValueError(gui_contract_errors[0])
                event.validated = True
                event.proposed.update(
                    {
                        "kind": "gui",
                        "delegation": "planner_to_holo",
                        "planner_model_requested": self.config.model,
                    }
                )
                request_signature_arguments = {
                    "action": "gui_request",
                    **copy.deepcopy(arguments),
                }
                event.proposed["gui_request_arguments"] = copy.deepcopy(
                    request_signature_arguments
                )
                if policy_error := repeated_gui_action_error(
                    state.events,
                    command="holo.gui_request",
                    arguments=request_signature_arguments,
                    step=event.step,
                    block_window_steps=ACTION_BLOCK_WINDOW_STEPS,
                    blocked_action="gui_request",
                ):
                    raise RepeatedRequestBlocked(policy_error)
                grounding_result = self._execute_holo_gui_request(
                    arguments,
                    screenshot
                    if screenshot is not None
                    else getattr(self, "_latest_screenshot", None),
                )
                audit_arguments = self._holo_audit_arguments(grounding_result)
                if audit_arguments is not None:
                    event.proposed["gui_arguments"] = audit_arguments
                grounding = grounding_result.get("grounding")
                if isinstance(grounding, dict):
                    # Keep the exact Holo payload and prepared representation in
                    # the immutable event, while model projections retain only
                    # the sanitized action result.
                    event.proposed["holo_grounding"] = copy.deepcopy(grounding)
                prepared = grounding_result.get("prepared_action")
                if isinstance(prepared, dict):
                    command = prepared.get("command")
                    if isinstance(command, str):
                        event.proposed["command"] = command
                event.executed = bool(grounding_result.get("executed"))
                event.result = (
                    sanitize_gui_result_for_model(grounding_result.get("result"))
                    if event.executed
                    else None
                )
                event.error = (
                    None
                    if event.executed
                    else grounding_result.get(
                        "error",
                        {
                            "type": "HoloGuiExecutionError",
                            "detail": "the Holo GUI action was not executed",
                        },
                    )
                )
            elif tool == "propose_done":
                event.validated = True
                event.proposed["kind"] = "completion"
                completion_gate = self._generic_completion_gate
                structural_gate = completion_gate(state)
                gate = completion_gate(state, arguments)
                response_errors = completion_response_contract_errors(proposal)
                if response_errors:
                    gate = {
                        "passed": False,
                        "missing": list(
                            dict.fromkeys([*response_errors, *gate["missing"]])
                        ),
                    }
                event.executed = bool(gate["passed"])
                event.result = (
                    {"status": "ok", "executed": True, "gate": gate}
                    if gate["passed"]
                    else None
                )
                event.error = (
                    None
                    if gate["passed"]
                    else completion_recovery.completion_rejection_error(
                        gate,
                        structural_gate,
                        response_errors,
                        completion_claim_contradictions(arguments),
                    )
                )
                if gate["passed"]:
                    if getattr(state, "defer_terminal_audit", False):
                        state.pending_terminal = {
                            "status": "done",
                            "tool": "propose_done",
                            "event_step": event.step,
                        }
                    else:
                        state.done = True
                else:
                    state.completion_rejections += 1
            elif tool == "fail_task":
                event.validated = True
                event.executed = True
                event.proposed["kind"] = "failure"
                event.result = {
                    "status": "failed",
                    "executed": True,
                    "reason": arguments["reason"],
                }
                if getattr(state, "defer_terminal_audit", False):
                    state.pending_terminal = {
                        "status": "failed",
                        "tool": "fail_task",
                        "event_step": event.step,
                    }
                else:
                    state.failed = True
            else:
                raise ValueError(f"unknown or unavailable tool: {tool}")
        except RepeatedRequestBlocked as exc:
            event.error = exc.error
        except Exception as exc:
            if tool == "propose_done":
                completion_gate = self._generic_completion_gate
                event.error = completion_recovery.completion_parse_error(
                    completion_gate(state), exc
                )
                state.completion_rejections += 1
            else:
                event.error = {
                    "type": type(exc).__name__,
                    "detail": str(exc),
                    "executed": False,
                }
            event.executed = False
        event.duration_seconds = round(time.monotonic() - started, 3)
        event.result = sanitize_agent_visible_result(event.result, state.task_id)
        event.error = sanitize_agent_visible_result(event.error, state.task_id)
        state.events.append(event)
        self._block_repeated_error(state)
        event.error = sanitize_agent_visible_result(event.error, state.task_id)
        return event

    @staticmethod
    def _block_repeated_error(state: RuntimeState) -> None:
        if len(state.events) < 2:
            return
        current = state.events[-1]
        if current.executed or (
            isinstance(current.error, dict)
            and current.error.get("type") == "RepeatedActionBlocked"
        ):
            return

        def event_key(event: Any) -> tuple[Any, ...]:
            proposed = event.proposed
            action = str(proposed.get("action") or proposed.get("tool") or "")
            identity = canonical_action_request(
                state.domain,
                action,
                proposed.get("arguments", {}),
            )
            return (
                proposed.get("kind"),
                identity[:2],
                argument_signature(identity[2]),
                error_signature(event.error),
            )

        current_proposed = current.proposed
        current_action = str(
            current_proposed.get("action") or current_proposed.get("tool") or ""
        )
        current_identity = canonical_action_request(
            state.domain,
            current_action,
            current_proposed.get("arguments", {}),
        )
        current_key = event_key(current)
        repeated = next(
            (
                previous
                for previous in reversed(state.events[:-1])
                if not previous.executed
                and event_key(previous) == current_key
                and not request_block_is_stale(
                    state.events, blocked_at_step=previous.step
                )
            ),
            None,
        )
        if repeated is not None:
            signature = error_signature(current.error)
            arguments_signature = argument_signature(current_identity[2])
            blocked_action = current_proposed.get("action") or current_proposed.get(
                "tool"
            )
            current.error = {
                "type": "RepeatedActionBlocked",
                "detail": "the same action and normalized arguments reached the same structured error twice; the exact request is blocked for this episode, so change the arguments, replan, or search",
                "executed": False,
                "previous_step": repeated.step,
                "previous_error": current.error,
                "blocked_action": blocked_action,
                "argument_signature": arguments_signature,
                "error_signature": signature,
                "block_scope": "episode",
                "fallback_reason": "same_action_same_arguments_same_error_twice",
            }

    def step(
        self, state: RuntimeState, screenshot: bytes, screenshot_path: str | None = None
    ) -> ExecutionEvent:
        proposal = self.propose(state, screenshot)
        return self.execute_proposal(state, proposal, screenshot_before=screenshot_path)
