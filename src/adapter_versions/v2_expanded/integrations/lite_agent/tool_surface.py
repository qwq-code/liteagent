"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
from . import (
    batch_table_semantics,
    calc_semantics,
    clipboard_path_semantics,
    completion_recovery,
    source_execution_semantics,
    spreadsheet_open_semantics,
    verified_artifact_handoff,
    workspace_file_semantics,
    workspace_open_semantics,
)
from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
)
from .filesystem_copy_semantics import (
    requested_collection_copy,
    requested_copy_destinations,
    resolved_collection_copy_destination,
    completion_errors as collection_copy_completion_errors,
)
from .completion_policy import (
    action_is_read_only as is_read_only,
    action_is_save as is_save,
    canonical_action_request,
    completion_claim_contradictions as completion_claim_contradictions,
    effective_adapter_action,
    effective_canonical_action,
)
from .generic_routing import discovered_adapter_routes, recovery_search_actions
from .local_file_discovery import (
    constrain_failed_path_discovery_tools,
    constrain_zero_match_find_tools,
    has_positive_local_file_discovery,
    local_file_discovery_stage_active,
    unresolved_zero_match_find,
)
from .positive_find_handoff import (
    age_organization_complete,
    constrain_age_organization_find_tools,
)
from .recovery_alternative import filter_requested_alternative_actions
from .recovery_surface import (
    bounded_recovery_actions,
    decorate_recovery_tools,
    soft_recovery_tools,
)
from .search_recovery_tools import constrain_adapter_call_routes
from .semantic_requirements import strict_semantic_action_equivalents
from .standard_location_semantics import constrain_output_tools
from .tool_catalog import (
    INSPECT_ACTIONS,
    FORBIDDEN_DATASET_ACTIONS,
    action_from_tool_name,
    build_tools,
    tool_name,
)
from .instruction_semantics import (
    requested_pivot_count,
    requested_max_system_volume,
    strict_instruction_required_actions,
)
from .impress_title_formatting import (
    constrain_tool_schema as constrain_title_format_tool_schema,
)
from .impress_image_insertion import (
    constrain_image_insertion_tool_schema,
    is_sized_image_insertion_instruction,
)
from .state_model import RuntimeState
from .visual_file_identity import pending_visual_image
from .structural_observation_recovery import recover_structural_tool_surface
from .bounded_recovery import recent_failure, repeated_tool, recover_tools
from .completion_outcomes import completion_outcome_issues
from .terminal_tool_constraints import constrain_terminal_provenance_tools
from .vscode_workspace_context import (
    constrain_workspace_add_tools,
    has_verified_workspace_addition,
)


class ToolSurfaceMixin:
    @staticmethod
    def _constrain_max_system_volume(
        tools: list[dict[str, Any]], state: RuntimeState
    ) -> list[dict[str, Any]]:
        """Map qualitative 'maximum volume' wording to normal 100% volume.

        The adapter intentionally accepts explicit over-amplification values for
        expert requests.  Only a natural-language maximum request gets the
        narrower model-facing enum, so a model cannot confuse the API ceiling
        (150) with the operating-system maximum (100).
        """
        if not requested_max_system_volume(state.domain, str(state.instruction)):
            return tools

        def constrain(parameters: Any, *, force_volume: bool = False) -> None:
            if not isinstance(parameters, dict):
                return
            route = parameters.get("x-route")
            if force_volume or (isinstance(route, dict) and (
                route.get("adapter"), route.get("action")
            ) == ("os", "audio.set_volume")):
                properties = parameters.get("properties")
                if isinstance(properties, dict) and isinstance(
                    properties.get("percent"), dict
                ):
                    percent = properties["percent"]
                    percent.pop("maximum", None)
                    percent["enum"] = [100]
                    percent["description"] = (
                        "For a qualitative maximum-volume request, use exactly 100: "
                        "the normal system maximum (0 dB). Values above 100 are explicit "
                        "over-amplification requests and are not selected here."
                    )
            properties = parameters.get("properties")
            if isinstance(properties, dict):
                nested = properties.get("params")
                if isinstance(nested, dict):
                    constrain(nested, force_volume=force_volume)
            for keyword in ("oneOf", "anyOf", "allOf"):
                branches = parameters.get(keyword)
                if isinstance(branches, list):
                    for branch in branches:
                        constrain(branch, force_volume=force_volume)

        for tool in tools:
            function = tool.get("function")
            if not isinstance(function, dict):
                continue
            action = action_from_tool_name(state.domain, str(function.get("name", "")))
            if action == "audio.set_volume":
                constrain(function.get("parameters"), force_volume=True)
            else:
                constrain(function.get("parameters"))
        return tools

    @staticmethod
    def _successful_route_pairs(state: RuntimeState) -> set[tuple[str, str]]:
        """Return owning Adapter routes already executed successfully."""
        return {
            effective_canonical_action(event, state.domain)[:2]
            for event in state.events
            if event.executed
            and not event.error
            and isinstance(event.proposed, dict)
            and event.proposed.get("kind") == "adapter"
        }

    @staticmethod
    def _observed_find_suffixes(state: RuntimeState) -> set[str]:
        """Read only suffixes returned by a successful filesystem.find.

        Reader selection is allowed to use the public discovery result, but it
        must never guess a path or a document type from the instruction alone.
        """
        suffixes: set[str] = set()
        for event in state.events:
            if not event.executed or event.error:
                continue
            if effective_canonical_action(event, state.domain)[:2] != (
                "os",
                "filesystem.find",
            ):
                continue
            pending: list[Any] = [event.result]
            for _ in range(6):
                if not pending:
                    break
                children: list[Any] = []
                for value in pending:
                    if isinstance(value, dict):
                        matches = value.get("matches")
                        if isinstance(matches, list):
                            for item in matches:
                                if isinstance(item, dict) and isinstance(item.get("path"), str):
                                    suffix = Path(item["path"]).suffix.casefold()
                                    if suffix:
                                        suffixes.add(suffix)
                        for key in ("context_hint", "downstream_context", "result", "adapter_response"):
                            child = value.get(key)
                            if isinstance(child, (dict, list)):
                                children.append(child)
                    elif isinstance(value, list):
                        children.extend(value)
                pending = children
        return suffixes

    @staticmethod
    def _compatible_reader_routes(
        suffixes: set[str],
    ) -> set[tuple[str, str]]:
        """Map observed local file extensions to native public readers."""
        routes: set[tuple[str, str]] = set()
        if suffixes.intersection({".csv", ".ods", ".xls", ".xlsx"}):
            routes.add(("libreoffice_calc", "workbook.read_file"))
        if suffixes.intersection({".doc", ".docx", ".odt", ".rtf"}):
            routes.add(("libreoffice_writer", "document.read_file"))
        if suffixes.intersection({".pdf"}):
            routes.update(
                {
                    ("os", "pdf.extract_text_batch"),
                    ("os", "pdf.form.inspect"),
                    ("os", "pdf.tables.inspect"),
                    ("os", "pdf.outline.inspect"),
                }
            )
        return routes

    @staticmethod
    def _vlc_preference_field(instruction: str) -> str | None:
        text = str(instruction)
        if re.search(r"(?i)\b(?:hotkey|shortcut|keyboard)\b", text) and re.search(
            r"(?i)\b(?:play|pause|start)\b", text
        ):
            return "global_play_pause_hotkey"
        if re.search(r"(?i)\b(?:maximum|max)\b.{0,30}\bvolume\b", text):
            return "maximum_volume_percent"
        if re.search(r"(?i)\b(?:slider|volume\s+control)\b.{0,30}\bcolou?r\b", text):
            return "volume_slider_color"
        if re.search(r"(?i)\bminimal\s+interface\b", text):
            return "minimal_interface"
        if re.search(
            r"(?i)(?:\b(?:exit|close|closing|closes|closing\s+automatically|auto[- ]?clos(?:e|ing))\b"
            r".{0,45}\b(?:playback|playing|video|end(?:s|ed|ing)?)\b|"
            r"\b(?:playback|playing|video)\b.{0,45}\b(?:exit|close|closing|closes|auto[- ]?clos(?:e|ing))\b)",
            text,
        ):
            return "exit_after_playback"
        if re.search(r"(?i)\bmultiple\s+instances?\b", text):
            return "allow_multiple_instances"
        if re.search(r"(?i)\b(?:cone|splash)\b", text):
            return "show_background_cone"
        if re.search(r"(?i)\brecord(?:ed|ing|ings)?\b", text):
            return None
        return None

    @staticmethod
    def _directory_table_instruction(state: RuntimeState) -> bool:
        tokens = {
            token.strip(".,:;!?()[]{}")
            for token in str(state.instruction).casefold().replace("/", " ").split()
        }
        return bool(
            tokens.intersection({"folder", "directory"})
            and tokens.intersection({"sheet", "spreadsheet", "workbook", "table"})
            and tokens.intersection(
                {"add", "append", "enter", "import", "populate", "record", "update"}
            )
        )

    @staticmethod
    def _directory_table_observed_roots(
        state: RuntimeState, suffixes: set[str]
    ) -> list[str]:
        """Return directories supported by observed file paths."""
        roots: set[str] = set()
        for event in state.events:
            if not event.executed or event.error or not isinstance(event.result, dict):
                continue
            context = event.result.get("context_hint")
            if not isinstance(context, dict):
                continue
            if context.get("downstream_action") == "filesystem.find":
                context = context.get("downstream_context")
            if not isinstance(context, dict):
                continue
            matches = context.get("matches")
            if not isinstance(matches, list):
                continue
            for item in matches:
                path = item.get("path") if isinstance(item, dict) else None
                if isinstance(path, str) and Path(path).suffix.casefold() in suffixes:
                    roots.add(str(Path(path).parent))
        return sorted(roots)

    @staticmethod
    def _directory_table_ocr_roots(state: RuntimeState) -> list[str]:
        return ToolSurfaceMixin._directory_table_observed_roots(
            state, {".bmp", ".jpeg", ".jpg", ".pdf", ".png", ".tif", ".tiff", ".webp"}
        )

    @staticmethod
    def _directory_table_reader_pending(state: RuntimeState) -> bool:
        """Require content extraction before editing a discovered file set."""
        if not ToolSurfaceMixin._directory_table_instruction(state):
            return False
        discovered = False
        zero_match_only = unresolved_zero_match_find(state)
        reader_completed = False
        for event in state.events:
            proposed = event.proposed
            if not isinstance(proposed, dict) or not event.executed or event.error:
                continue
            arguments = proposed.get("arguments")
            action = (
                arguments.get("action", proposed.get("action"))
                if isinstance(arguments, dict)
                else proposed.get("action")
            )
            if action == "filesystem.find":
                discovered = not zero_match_only
            elif action in {"image.extract_text_batch", "pdf.extract_text_batch"}:
                reader_completed = True
        return discovered and not reader_completed

    @staticmethod
    def _financial_amount_route_guidance(state: RuntimeState) -> str:
        """Expose OCR-derived payment hints as bounded write-route evidence."""
        def find_files(value: Any) -> list[dict[str, Any]]:
            if isinstance(value, dict):
                files = value.get("files")
                if isinstance(files, list) and any(
                    isinstance(item, dict) and isinstance(item.get("financial_amount_hint"), dict)
                    for item in files
                ):
                    return [item for item in files if isinstance(item, dict)]
                for child in value.values():
                    found = find_files(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = find_files(child)
                    if found:
                        return found
            return []

        for event in reversed(getattr(state, "events", [])):
            files = find_files(getattr(event, "result", None))
            records = []
            for item in files:
                hint = item.get("financial_amount_hint")
                path = item.get("path")
                if not isinstance(hint, dict) or not isinstance(path, str):
                    continue
                amount = hint.get("amount")
                label = hint.get("label")
                if isinstance(amount, (int, float)) and not isinstance(amount, bool):
                    records.append(f"{path} -> {amount:g} ({label})")
            if records:
                return (
                    " Observed OCR payment hints, in source-file order: "
                    + "; ".join(records)
                    + ". Write one ledger row for every listed source file, preserving this order; "
                    "put the negative amount in the Amount column, Type=Expense, and leave optional "
                    "description/category cells blank when not requested."
                )
        return ""

    @staticmethod
    def _catalog_search_streak(state: RuntimeState) -> int:
        """Count consecutive catalog searches since the last executable action."""
        streak = 0
        for event in reversed(state.events):
            if event.proposed.get("kind") == "catalog":
                streak += 1
                continue
            break
        return streak

    def _holo_gui_configured(self) -> bool:
        """Return whether GUI turns are delegated to the visual model.

        The attribute checks keep this mixin compatible with small test doubles
        and with the legacy direct-GUI constructor.
        """
        return bool(
            getattr(self, "holo_grounder", None) is not None
            or getattr(self, "holo_gui_gateway", None) is not None
        )

    def _gui_execution_configured(self) -> bool:
        """Return whether direct or delegated GUI execution is available."""
        return bool(
            getattr(self, "gui_executor", None) is not None
            or getattr(self, "holo_gui_gateway", None) is not None
        )

    def _build_tools(
        self,
        domain: str,
        actions: list[str],
        include_gui: bool,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        """Build a surface using the configured direct or delegated GUI tool."""
        if domain == "libreoffice_impress":
            actions = list(dict.fromkeys(
                atomic
                for action in actions
                for atomic in (
                    ("shape.align_to_slide", "shape.move", "shape.resize")
                    if action == "shape.set_geometry" else (action,)
                )
            ))
        return build_tools(
            domain,
            actions,
            include_gui,
            gui_request=bool(include_gui and self._holo_gui_configured()),
            **kwargs,
        )

    @staticmethod
    def _move_named_tools_to_end(
        tools: list[dict[str, Any]], names: set[str]
    ) -> list[dict[str, Any]]:
        """Keep a fallback action available without making it the attractor."""
        if not names:
            return tools
        retained: list[dict[str, Any]] = []
        moved: list[dict[str, Any]] = []
        for tool in tools:
            function = tool.get("function")
            name = function.get("name") if isinstance(function, dict) else None
            (moved if name in names else retained).append(tool)
        return [*retained, *moved]

    @staticmethod
    def _keep_search_control(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only the bounded catalog-search control on a consumer retry."""
        terminal_controls = {
            "gui_action",
            "gui_request",
            "propose_done",
            "fail_task",
        }
        return [
            tool
            for tool in tools
            if not isinstance(tool.get("function"), dict)
            or tool["function"].get("name") not in terminal_controls
        ]

    def _completion_claim_only_retry(self, state: RuntimeState) -> bool:
        """Keep a complete-state completion retry on terminal controls only."""
        if not self._generic_completion_gate(state).get("passed"):
            return False
        verified_mutation = any(
            getattr(previous, "executed", False)
            and isinstance(getattr(previous, "proposed", None), dict)
            and previous.proposed.get("kind") == "adapter"
            and not is_read_only(effective_adapter_action(previous, state.domain)[1])
            and not is_save(effective_adapter_action(previous, state.domain)[1])
            and isinstance(getattr(previous, "result", None), dict)
            and isinstance(
                (
                    previous.result.get("verification")
                    or (
                        previous.result.get("result", {}).get("verification")
                        if isinstance(previous.result.get("result"), dict)
                        else None
                    )
                ),
                dict,
            )
            and (
                previous.result.get("verification")
                or previous.result.get("result", {}).get("verification")
            ).get("passed")
            is True
            for previous in getattr(state, "events", ())
        )
        if not verified_mutation:
            return False
        for event in reversed(getattr(state, "events", ())):
            if getattr(event, "executed", False):
                return False
            proposed = getattr(event, "proposed", None)
            error = getattr(event, "error", None)
            if not isinstance(proposed, dict) or proposed.get("kind") != "completion":
                continue
            if not isinstance(error, dict) or error.get("status") != "rejected":
                return False
            recovery = error.get("recovery")
            missing = error.get("missing")
            # A verified mutation can still be rejected when a model writes a
            # contradictory completion explanation (for example, mentioning
            # both the requested false value and its opposite).  There is no
            # remaining application action in that case.  Keep the retry on
            # terminal controls so a provider cannot replay the broad setting
            # schema and emit an empty union branch.
            if (
                isinstance(missing, list)
                and "the completion claim describes work that still needs to happen"
                in missing
            ):
                return True
            if isinstance(proposed, dict) and proposed.get("kind") == "completion":
                # RepeatedActionBlocked is emitted after the first rejected
                # claim; the verified mutation still leaves only completion
                # controls valid for the next turn.
                return True
            return bool(
                isinstance(recovery, dict)
                and recovery.get("mode") == "claim_only"
            ) or bool(
                isinstance(missing, list)
                and any("response was incomplete" in str(item) for item in missing)
            )
        return False

    @staticmethod
    def _recovery_gui_enabled(state: RuntimeState, configured: bool) -> bool:
        """Suppress GUI for a bounded turn after a repeated GUI rejection.

        ``gui_policy`` already records a materially equivalent GUI request as an
        episode/window block.  Keeping the same GUI tool on that immediate
        replan surface invites a small model to emit the same invalid shape
        again, while hiding it for all other failures would remove a legitimate
        fallback.  Adapter routes, ``tools_search``, and terminal controls stay
        available to make the replan explicit and model-selected.
        """
        if not configured:
            return False
        error = state.events[-1].error if state.events else None
        return not (
            isinstance(error, dict)
            and error.get("type") == "RepeatedActionBlocked"
            and (
                error.get("blocked_action") in {"gui_action", "gui_request"}
                or error.get("fallback_reason") == "repeated_gui_pattern"
            )
        )

    @staticmethod
    def _apply_common_tool_constraints(
        tools: list[dict[str, Any]], state: RuntimeState, *, completion_recovery_surface: bool = False
    ) -> list[dict[str, Any]]:
        """Apply the same model-facing contracts on every action surface.

        Search and error-recovery are alternate routes into the normal action
        catalog.  They must not silently drop the existing, instruction-local
        schema constraints just because the route was recovered.
        """
        tools = constrain_workspace_add_tools(tools, state)
        tools = ToolSurfaceMixin._constrain_max_system_volume(tools, state)
        if state.domain == "multi_apps":
            # Keep initial multi-app discovery compatible with local tool-call endpoints.
            if not state.events and any(
                isinstance(tool.get("function"), dict)
                and tool["function"].get("name") == "tools_search"
                for tool in tools
            ):
                tools = [
                    tool
                    for tool in tools
                    if not isinstance(tool.get("function"), dict)
                    or tool["function"].get("name") == "tools_search"
                    or tool["function"].get("name", "").startswith("adapter__")
                ]
            if any(
                isinstance(tool.get("function"), dict)
                and tool["function"].get("name", "").startswith("adapter__")
                for tool in tools
            ) and not any(
                event.executed
                and not event.error
                and isinstance(event.proposed, dict)
                and event.proposed.get("kind") == "adapter"
                for event in state.events
            ):
                tools = [
                    tool
                    for tool in tools
                    if not isinstance(tool.get("function"), dict)
                    or tool["function"].get("name", "") not in {"propose_done", "fail_task"}
                ]
            latest_catalog_step = max(
                (
                    event.step
                    for event in state.events
                    if event.executed
                    and isinstance(event.proposed, dict)
                    and event.proposed.get("kind") == "catalog"
                ),
                default=-1,
            )
            adapter_since_catalog = any(
                event.executed
                and isinstance(event.proposed, dict)
                and event.proposed.get("kind") == "adapter"
                and event.step > latest_catalog_step
                for event in state.events
            )
            adapter_attempt_since_catalog = any(
                isinstance(event.proposed, dict)
                and event.proposed.get("kind") == "adapter"
                and event.step > latest_catalog_step
                for event in state.events
            )
            if not adapter_attempt_since_catalog and any(
                isinstance(tool.get("function"), dict)
                and tool["function"].get("name", "").startswith("adapter__")
                for tool in tools
            ):
                tools = [
                    tool
                    for tool in tools
                    if not isinstance(tool.get("function"), dict)
                    or tool["function"].get("name", "").startswith("adapter__")
                ]
            route_pairs = discovered_adapter_routes(state)
            adapter_call_name = tool_name("adapter.call")
            if adapter_since_catalog and not completion_recovery_surface:
                # Reuse the model-selected atom for another target, without
                # reopening unrelated candidates from the same catalog result.
                # Changing operation still requires a new model-selected search.
                last_route = next((
                    effective_canonical_action(event, state.domain)[:2]
                    for event in reversed(state.events)
                    if event.executed and not event.error
                    and event.proposed.get('kind') == 'adapter'
                    and event.step > latest_catalog_step
                ), None)
                route_pairs = [pair for pair in route_pairs if pair == last_route]
            if route_pairs:
                successful_actions = list(
                    ToolSurfaceMixin._successful_route_pairs(state)
                )
                instruction_tokens = {
                    token.strip(".,:;!?()[]{}")
                    for token in str(state.instruction).casefold().replace("/", " ").split()
                }
                visual_identification = bool(
                    instruction_tokens.intersection(
                        {"image", "images", "picture", "pictures", "photo", "photos"}
                    )
                    and instruction_tokens.intersection(
                        {"identify", "identification", "classify", "recognize", "visual"}
                    )
                )
                visual_source_path = None
                visual_rename_finished = False
                if visual_identification:
                    visual_source_path, visual_source_opened = pending_visual_image(state)
                    visual_rename_finished = (
                        visual_source_path is None
                        and ("os", "filesystem.rename") in successful_actions
                    )
                    if ("os", "filesystem.find") not in successful_actions:
                        target_route = ("os", "filesystem.find")
                    else:
                        if visual_source_path is None:
                            target_route = None
                        elif not visual_source_opened:
                            target_route = ("os", "desktop.open_path")
                        else:
                            target_route = ("os", "filesystem.rename")
                    route_pairs = [
                        pair for pair in route_pairs
                        if target_route is not None and pair == target_route
                    ]
                if visual_identification:
                    tools = [
                        tool
                        for tool in tools
                        if not isinstance(tool.get("function"), dict)
                        or tool["function"].get("name") not in {"gui_action", "gui_request"}
                    ]
                # Once discovery has returned a document, select its native
                # reader from the observed suffix.  This prevents a PDF/XLSX
                # from being sent to Writer merely because the query said
                # "read the document" and makes the route deterministic for
                # small models.
                if ("os", "filesystem.find") in successful_actions:
                    observed_suffixes = ToolSurfaceMixin._observed_find_suffixes(state)
                    compatible = ToolSurfaceMixin._compatible_reader_routes(
                        observed_suffixes
                    )
                    reader_routes = {
                        ("libreoffice_writer", "document.read_file"),
                        ("libreoffice_calc", "workbook.read_file"),
                        ("os", "pdf.extract_text_batch"),
                        ("os", "pdf.form.inspect"),
                        ("os", "pdf.tables.inspect"),
                        ("os", "pdf.outline.inspect"),
                    }
                    if compatible:
                        route_pairs = [
                            pair
                            for pair in route_pairs
                            if pair not in reader_routes or pair in compatible
                        ]
                    if (
                        ("libreoffice_writer", "document.read_file") in route_pairs
                        and ("libreoffice_writer", "document.read_file")
                        not in successful_actions
                        and (
                            not observed_suffixes
                            or ("libreoffice_writer", "document.read_file")
                            in compatible
                        )
                    ):
                        route_pairs = [
                            pair
                            for pair in route_pairs
                            if pair == ("libreoffice_writer", "document.read_file")
                        ]
                if not successful_actions and set(route_pairs) == {
                    ("os", "filesystem.find"),
                    ("libreoffice_writer", "document.read_file"),
                }:
                    # Resolve the generic discovery stage first; after it succeeds
                    # the existing state transition exposes only the document reader.
                    route_pairs = [("os", "filesystem.find")]
                # A mailbox folder is an application object. After querying it,
                # the only next step in an attachment workflow is saving the
                # selected attachment; never route the folder through a local
                # filesystem reader.
                if (
                    ("thunderbird", "messages.query") in successful_actions
                    and ("thunderbird", "attachments.save") in route_pairs
                    and ("thunderbird", "attachments.save") not in successful_actions
                ):
                    route_pairs = [
                        pair
                        for pair in route_pairs
                        if pair == ("thunderbird", "attachments.save")
                    ]
                elif (
                    ("thunderbird", "attachments.save") in successful_actions
                    and ("libreoffice_writer", "document.extract_images") in route_pairs
                ):
                    route_pairs = [
                        pair
                        for pair in route_pairs
                        if pair == ("libreoffice_writer", "document.extract_images")
                    ]
                if ToolSurfaceMixin._directory_table_reader_pending(state):
                    ocr_roots = ToolSurfaceMixin._directory_table_ocr_roots(state)
                    workbook_roots = ToolSurfaceMixin._directory_table_observed_roots(
                        state, {".csv", ".ods", ".xls", ".xlsx"}
                    )
                    source_roots = ocr_roots or workbook_roots
                    reader_pairs = [
                        pair
                        for pair in route_pairs
                        if pair[0] == "os"
                        and pair[1]
                        in {"image.extract_text_batch", "pdf.extract_text_batch"}
                    ]
                    image_reader = ("os", "image.extract_text_batch")
                    if image_reader in reader_pairs:
                        reader_pairs = [image_reader]
                    if not source_roots:
                        route_pairs = [
                            pair for pair in route_pairs
                            if pair == ("os", "filesystem.find")
                        ]
                    elif reader_pairs:
                        route_pairs = reader_pairs
                else:
                    successful = [
                        effective_canonical_action(event, state.domain)[:2]
                        for event in state.events
                        if event.executed
                        and not event.error
                        and event.proposed.get("kind") == "adapter"
                    ]
                    reader_done = any(
                        pair in successful
                        for pair in {
                            ("os", "image.extract_text_batch"),
                            ("os", "pdf.extract_text_batch"),
                        }
                    ) or any(
                        event.executed
                        and not event.error
                        and isinstance(event.proposed, dict)
                        and isinstance(event.proposed.get("arguments"), dict)
                        and event.proposed["arguments"].get("action")
                        in {"image.extract_text_batch", "pdf.extract_text_batch"}
                        for event in state.events
                    )
                    if reader_done and ToolSurfaceMixin._directory_table_instruction(state):
                        inspect = ("libreoffice_calc", "workbook.inspect")
                        read = ("libreoffice_calc", "range.read")
                        write = ("libreoffice_calc", "range.write")
                        save = ("libreoffice_calc", "workbook.save")
                        if inspect not in successful:
                            route_pairs = [pair for pair in route_pairs if pair == inspect]
                        elif read not in successful:
                            route_pairs = [pair for pair in route_pairs if pair == read]
                        elif write not in successful:
                            route_pairs = [pair for pair in route_pairs if pair == write]
                        elif sum(pair == read for pair in successful) < 2:
                            route_pairs = [
                                pair for pair in route_pairs if pair in {read, save}
                            ]
                        elif save not in successful:
                            route_pairs = [pair for pair in route_pairs if pair == save]
                if not route_pairs:
                    # Workflow filtering can remove every catalog candidate.
                    # An empty set must not become the unrestricted transport
                    # schema: the model would see routes execution rejects.
                    # Restore discovery so it can select another operation.
                    tools = [
                        tool for tool in tools
                        if tool.get("function", {}).get("name") != adapter_call_name
                    ]
                    if not any(
                        tool.get("function", {}).get("name") == "tools_search"
                        for tool in tools
                    ):
                        tools.extend(
                            tool for tool in build_tools(
                                state.domain, [], include_gui=False, strict_generic=True,
                            )
                            if tool["function"]["name"] == "tools_search"
                        )
                    if visual_rename_finished:
                        # Catalog filtering must not trap completed image work
                        # in search-only turns. Completion still uses the normal
                        # gate when the model selects propose_done.
                        names = {tool.get("function", {}).get("name") for tool in tools}
                        tools.extend(
                            tool for tool in build_tools(
                                state.domain, [], include_gui=False, strict_generic=True,
                            )
                            if tool["function"]["name"] in {"propose_done", "fail_task"} - names
                        )
                    return soft_recovery_tools(
                        constrain_terminal_provenance_tools(tools, state.instruction), state
                    )
                tools = constrain_adapter_call_routes(tools, route_pairs)
                if (
                    ToolSurfaceMixin._directory_table_reader_pending(state)
                    and route_pairs == [("os", "filesystem.find")]
                ):
                    for tool in tools:
                        function = tool.get("function")
                        if isinstance(function, dict) and function.get("name") == adapter_call_name:
                            function["description"] += (
                                " Find the source image or PDF files in the provided folder; "
                                "a workbook or text file alone does not establish the receipt inputs."
                            )
                if (
                    ToolSurfaceMixin._directory_table_reader_pending(state)
                    and source_roots
                    and route_pairs == [("os", "image.extract_text_batch")]
                ):
                    for tool in tools:
                        function = tool.get("function")
                        if not isinstance(function, dict) or function.get("name") != adapter_call_name:
                            continue
                        params = (
                            function.get("parameters", {}).get("properties", {})
                            .get("payload", {}).get("properties", {}).get("params", {})
                        )
                        properties = params.get("properties") if isinstance(params, dict) else None
                        if isinstance(properties, dict):
                            properties["cwd_source"]["enum"] = ["explicit"]
                            properties["cwd_path"]["enum"] = source_roots
                            properties["input_pattern"]["enum"] = ["*"]
                if visual_source_path and len(route_pairs) == 1 and route_pairs[0] in {
                    ("os", "desktop.open_path"), ("os", "filesystem.rename")
                }:
                    field = "path" if route_pairs[0][1] == "desktop.open_path" else "source"
                    for tool in tools:
                        function = tool.get("function")
                        if not isinstance(function, dict) or function.get("name") != adapter_call_name:
                            continue
                        params = (function.get("parameters", {}).get("properties", {})
                                  .get("payload", {}).get("properties", {}).get("params", {}))
                        source = params.get("properties", {}).get(field) if isinstance(params, dict) else None
                        if isinstance(source, dict):
                            source["enum"] = [visual_source_path]
                            source["description"] = (
                                "Use this exact image path observed by filesystem.find."
                            )
                if route_pairs and not tools:
                    tools = build_tools(
                        state.domain, ["adapter.call"], include_gui=False,
                        include_control_tools=False, strict_generic=True,
                    )
                    tools = constrain_adapter_call_routes(tools, route_pairs)
                tools = constrain_zero_match_find_tools(tools, state)
                if (
                    ("libreoffice_calc", "range.read") in successful_actions
                    and ("libreoffice_calc", "range.write") in route_pairs
                    and ToolSurfaceMixin._directory_table_instruction(state)
                ):
                    for tool in tools:
                        function = tool.get("function")
                        if (
                            isinstance(function, dict)
                            and function.get("name") == adapter_call_name
                        ):
                            params = (
                                function.get("parameters", {}).get("properties", {})
                                .get("payload", {}).get("properties", {}).get("params", {})
                            )
                            properties = params.get("properties", {})
                            if isinstance(properties, dict) and isinstance(
                                properties.get("values"), dict
                            ):
                                properties["values"]["items"] = {
                                    "type": "array",
                                    "minItems": 1,
                                    "items": {"type": ["string", "number", "boolean", "null"]},
                                }
                            function["description"] = (
                                "For a document-to-ledger append, use the structured OCR "
                                "files[].expense_entry or financial_amount_hint values in source "
                                "order and write only new rows below the observed used range. "
                                + function["description"]
                                + " For an import after reading an existing workbook, preserve "
                                "the observed rows and append only new records below the observed "
                                "used range; do not rewrite the existing table. When several rows are known, write them together in one contiguous range rather than issuing one write per row. For a document-to-ledger import, write one row per source document using its final paid/total amount, not a line item or subtotal; expenses are negative with Type=Expense, and optional description or category cells stay blank unless requested. If the prior OCR result has files[].financial_amount_hint, use the matching file's financial_amount_hint.amount verbatim for the Amount cell and do not infer a different number from raw OCR text. Formula cells must use a typed value object such as {\"kind\":\"formula\",\"value\":\"=E8+D9\"}; a plain string beginning with '=' is literal text."
                                + ToolSurfaceMixin._financial_amount_route_guidance(state)
                            )
                            break
                # Once a valid route has been returned, require the model to
                # select that route (or a control action) on the next turn.
                # A later executed action re-enables search for the next
                # workflow stage.
                if ToolSurfaceMixin._catalog_search_streak(state) >= 1:
                    tools = [
                        tool
                        for tool in tools
                        if not isinstance(tool.get("function"), dict)
                        or tool["function"].get("name") != "tools_search"
                    ]
            else:
                tools = [
                    tool
                    for tool in tools
                    if not isinstance(tool.get("function"), dict)
                    or tool["function"].get("name") != adapter_call_name
                ]
            return soft_recovery_tools(
                constrain_terminal_provenance_tools(tools, state.instruction), state
            )
        if spreadsheet_open_semantics.gui_request_contract_errors(state):
            tools = [
                tool
                for tool in tools
                if not isinstance(tool.get("function"), dict)
                or tool["function"].get("name") not in {"gui_action", "gui_request"}
            ]
        for tool in tools:
            function = tool.get("function")
            if not isinstance(function, dict):
                continue
            batch_table_semantics.constrain_tool_schema(function, state)
            calc_semantics.constrain_sort_tool_schema(function, state)
            calc_semantics.constrain_stacked_aggregate_tool_schema(
                function,
                state.instruction,
                requested_pivot_count(state.instruction),
            )
            constrain_title_format_tool_schema(function, state.instruction)
            constrain_image_insertion_tool_schema(function, state)
            verified_artifact_handoff.constrain_tool_schema(function, state)
        constrained = constrain_zero_match_find_tools(
            constrain_failed_path_discovery_tools(
                constrain_output_tools(
                constrain_terminal_provenance_tools(tools, state.instruction),
                state,
                ),
                state,
            ),
            state,
        )
        if state.domain == "os":
            explicit_destinations = requested_copy_destinations(state.instruction)
            if explicit_destinations:
                for tool in constrained:
                    function = tool.get("function")
                    if not isinstance(function, dict) or function.get("name") != "adapter__filesystem_copy_to_directories":
                        continue
                    parameters = function.get("parameters")
                    properties = parameters.get("properties") if isinstance(parameters, dict) else None
                    destinations = properties.get("destinations") if isinstance(properties, dict) else None
                    if isinstance(destinations, dict):
                        destinations["minItems"] = len(explicit_destinations)
                        destinations["maxItems"] = len(explicit_destinations)
                        items = destinations.get("items")
                        if isinstance(items, dict):
                            items["enum"] = explicit_destinations
                        destinations["description"] = (
                            "Use exactly the explicitly named destination directories from the instruction: "
                            + ", ".join(explicit_destinations)
                            + ". Do not add other directories."
                        )
        if state.domain == "os" and requested_collection_copy(state.instruction) is not None:
            find_done = any(
                event.executed
                and not event.error
                and isinstance(event.proposed, dict)
                and event.proposed.get("action") == "filesystem.find"
                for event in state.events
            )
            successful_copy = any(
                event.executed
                and not event.error
                and isinstance(event.proposed, dict)
                and event.proposed.get("action")
                in {"filesystem.copy_to_directories", "filesystem.copy"}
                for event in state.events
            )
            copy_complete = bool(
                find_done
                and successful_copy
                and not collection_copy_completion_errors(state)
            )
            # Collection copies are staged: discover once, copy each observed
            # source, then close with the normal completion controls. Keeping
            # find exposed after discovery invites small models to repeat the
            # same search instead of consuming the returned file set.
            if not find_done:
                allowed = {
                    "adapter__filesystem_find",
                    "propose_done",
                    "fail_task",
                }
            elif copy_complete:
                allowed = {"propose_done", "fail_task"}
            else:
                allowed = {
                    "adapter__filesystem_copy_to_directories",
                    "adapter__filesystem_copy",
                    "propose_done",
                    "fail_task",
                }
            constrained = [
                tool
                for tool in constrained
                if not isinstance(tool.get("function"), dict)
                or tool["function"].get("name") in allowed
            ]
            # A hierarchy-preserving collection copy has one destination for
            # each source: the destination root plus that source's relative
            # parent. Keep the general multi-destination API unchanged for
            # ordinary single-source duplication workflows.
            for tool in constrained:
                function = tool.get("function")
                if (
                    not isinstance(function, dict)
                    or function.get("name") != "adapter__filesystem_copy_to_directories"
                ):
                    continue
                parameters = function.get("parameters")
                if not isinstance(parameters, dict):
                    continue
                destinations = parameters.get("properties", {}).get("destinations")
                if isinstance(destinations, dict):
                    destinations["maxItems"] = 1
                    resolved_destination = resolved_collection_copy_destination(state)
                    if resolved_destination and not requested_collection_copy(state.instruction).get(
                        "preserve_hierarchy"
                    ):
                        items = destinations.get("items")
                        if isinstance(items, dict):
                            items["enum"] = [resolved_destination]
                        destinations["description"] = (
                            "Use the exact absolute flat destination directory derived from the "
                            "successful filesystem.find result: "
                            f"{resolved_destination}. Copy each source directly into it."
                        )
                    else:
                        if requested_collection_copy(state.instruction).get("preserve_hierarchy"):
                            # The instruction names the collection root, while each
                            # atomic copy targets that root plus the source's relative
                            # parent. Do not retain the earlier root-only enum here.
                            items = destinations.get("items")
                            if isinstance(items, dict):
                                items.pop("enum", None)
                        destinations["description"] = (
                            "Exactly one destination directory is required for each source in this "
                        "hierarchy-preserving collection copy. Use the destination root joined "
                        "with that source's relative parent directory. Do not include sibling "
                        "directories or the destination root as extra entries."
                        )
        return constrain_age_organization_find_tools(
            soft_recovery_tools(constrained, state), state
        )

    def tools(self, state: RuntimeState) -> list[dict[str, Any]]:
        tools = self._tools_for_state(state)
        issues = completion_outcome_issues(state)
        if issues:
            # Preserve model choice while keeping real, unresolved defects repairable.
            actions = list(dict.fromkeys(action for issue in issues
                                        for action in issue["repair_actions"]))
            recovery = self._build_tools(state.domain, actions, include_gui=False,
                                         include_control_tools=True, strict_generic=True)
            names = {t["function"]["name"] for t in tools}
            tools = [*tools, *[t for t in recovery if t["function"]["name"] not in names]]
        # A catalog hit is an executable promise. Keep the compatibility route
        # callable when discovery explicitly exposed it, alongside the atoms.
        if (
            state.domain == "libreoffice_impress"
            and "shape.set_geometry" in state.expanded_actions
            and any(tool.get("function", {}).get("name") in {
                "adapter__shape_align_to_slide", "adapter__shape_move", "adapter__shape_resize"
            } for tool in tools)
        ):
            tools = [*tools, *build_tools(
                state.domain, ["shape.set_geometry"], include_gui=False,
                include_control_tools=False, strict_generic=True,
            )]
        tools = recover_structural_tool_surface(tools, state)
        recovery_failures = [event for event in state.events[-5:]
                             if event.error and not event.executed
                             and event.proposed.get('kind') == 'adapter']
        if (recent_failure(state) and len(recovery_failures) >= 2) or repeated_tool(state):
            # A failed phase must retain a route to observation/discovery and
            # completion review. Selecting a control still goes through the
            # normal catalog, provenance and completion validation.
            controls = self._build_tools(state.domain, [], include_gui=False,
                                         include_control_tools=True, strict_generic=True)
            names = {tool.get('function', {}).get('name') for tool in tools}
            tools = [*tools, *[tool for tool in controls
                if tool.get('function', {}).get('name') in {'tools_search', 'propose_done', 'fail_task'} - names]]
        if repeated_tool(state) and self.config.include_gui and self._gui_execution_configured():
            recovery = self._build_tools(state.domain, [], include_gui=True)
            names = {tool.get("function", {}).get("name") for tool in tools}
            tools = [*tools, *[tool for tool in recovery
                              if tool.get("function", {}).get("name") in {"gui_action", "gui_request"}
                              and tool.get("function", {}).get("name") not in names]]
        return recover_tools(tools, state)

    def _tools_for_state(self, state: RuntimeState) -> list[dict[str, Any]]:
        multi_app = state.domain == "multi_apps"
        pending_terminal = getattr(state, "pending_terminal", None)
        pending_model_audit = getattr(state, "pending_model_audit", None)
        if (
            age_organization_complete(state)
            and self._generic_completion_gate(state).get("passed")
        ):
            controls = self._build_tools(
                state.domain, [], include_gui=False,
                include_control_tools=True, strict_generic=True,
            )
            return [
                tool for tool in controls
                if isinstance(tool.get("function"), dict)
                and tool["function"].get("name") in {"propose_done", "fail_task"}
            ]
        if (
            state.domain == "vs_code"
            and has_verified_workspace_addition(state)
            and self._generic_completion_gate(state).get("passed")
        ):
            controls = self._build_tools(
                state.domain, [], include_gui=False,
                include_control_tools=True, strict_generic=True,
            )
            for tool in controls:
                function = tool.get("function")
                if isinstance(function, dict) and function.get("name") == "propose_done":
                    function["description"] = (
                        "The requested workspace folders are present in the saved workspace "
                        "and the Adapter structural verification passed. Propose completion "
                        "using the observed workspace.add_folders result as evidence."
                    )
            return [
                tool for tool in controls
                if isinstance(tool.get("function"), dict)
                and tool["function"].get("name") in {"propose_done", "fail_task"}
            ]
        if (
            isinstance(pending_model_audit, dict)
            and not isinstance(pending_terminal, dict)
            and state.domain in {"vlc", "vs_code"}
            and getattr(state, "events", None)
        ):
            latest = state.events[-1]
            if (
                latest.executed
                and not latest.error
                and latest.proposed.get("action")
                == (
                    "preferences.configure"
                    if state.domain == "vlc"
                    else "debugging.configure"
                )
            ):
                audit_tools = self._build_tools(
                    state.domain,
                    [],
                    include_gui=False,
                    include_control_tools=True,
                    strict_generic=True,
                )
                if state.domain == "vs_code":
                    for tool in audit_tools:
                        function = tool.get("function")
                        if (
                            isinstance(function, dict)
                            and function.get("name") == "propose_done"
                        ):
                            function["description"] = (
                                "The VS Code debugging setting was executed successfully and verified. "
                                "Call propose_done now with a short completed reason and evidence "
                                "from the verified result. Do not repeat the setting change."
                            )
                return [
                    tool
                    for tool in audit_tools
                    if isinstance(tool.get("function"), dict)
                    and tool["function"].get("name") in {"propose_done", "fail_task"}
                ]
        if isinstance(pending_terminal, dict):
            # A terminal control is a model-visible result first, not an
            # immediate loop break.  Keep the normal public alternatives
            # available so Qwen can either confirm the result or choose a
            # different action after auditing it; bypassing the stage-specific
            # early returns here guarantees the two control Tools are present
            # on every audit turn.
            clipboard_path_complete = (
                False
                if multi_app
                else clipboard_path_semantics.path_clipboard_satisfied(state)
            )
            audit_actions = (
                []
                if clipboard_path_complete
                else [
                    action
                    for action in self.selected_actions(state)
                    if action not in FORBIDDEN_DATASET_ACTIONS
                ]
            )
            audit_tools = self._build_tools(
                state.domain,
                list(dict.fromkeys(audit_actions)),
                include_gui=(
                    self.config.include_gui
                    and self._gui_execution_configured()
                    and not clipboard_path_complete
                ),
                include_control_tools=True,
                strict_generic=True,
            )
            if clipboard_path_complete:
                audit_tools = [
                    tool
                    for tool in audit_tools
                    if not isinstance(tool.get("function"), dict)
                    or tool["function"].get("name") != "tools_search"
                ]
            audit_tools = self._apply_common_tool_constraints(audit_tools, state)
            workspace_terminal_audit = (
                state.domain == "vs_code"
                and workspace_open_semantics.workflow_intent(state) is not None
                and not workspace_open_semantics.completion_errors(state)
            )
            debugging_terminal_audit = state.domain == "vs_code" and any(
                event.executed
                and not event.error
                and event.proposed.get("action") == "debugging.configure"
                for event in state.events
            )
            if state.domain == "vlc" or debugging_terminal_audit or workspace_terminal_audit:
                if workspace_terminal_audit:
                    for tool in audit_tools:
                        function = tool.get("function")
                        if (
                            isinstance(function, dict)
                            and function.get("name") == "propose_done"
                        ):
                            function["description"] = (
                                "Audit only: the previous propose_done already passed and the "
                                "workspace.open verification succeeded. Return one short propose_done "
                                "call with concise reason and evidence to confirm it. Do not describe "
                                "future work, repeat workspace.open, or call any other tool."
                            )
                return [
                    tool
                    for tool in audit_tools
                    if isinstance(tool.get("function"), dict)
                    and tool["function"].get("name") in {"propose_done", "fail_task"}
                ]
            expected_tool = pending_terminal.get("tool", "terminal control")
            for tool in audit_tools:
                function = tool.get("function")
                if not isinstance(function, dict):
                    continue
                name = function.get("name")
                if name in {"propose_done", "fail_task"}:
                    function["description"] = (
                        f"Audit the previous {expected_tool} result. Confirm it only "
                        "if it is still correct; otherwise choose another public Tool."
                    )
            return audit_tools

        if (
            multi_app
            and self._directory_table_instruction(state)
            and unresolved_zero_match_find(state)
        ):
            discovery_tools = self._build_tools(
                state.domain, ["adapter.call"], include_gui=False,
                include_control_tools=False, strict_generic=True,
            )
            discovery_tools = constrain_adapter_call_routes(
                discovery_tools, [("os", "filesystem.find")]
            )
            return constrain_zero_match_find_tools(discovery_tools, state)

        clipboard_stage = (
            None if multi_app else clipboard_path_semantics.pending_actions(state)
        )
        if clipboard_stage is not None:
            terminal_only = not clipboard_stage
            tools = self._build_tools(
                state.domain,
                clipboard_stage,
                include_gui=False,
                include_control_tools=terminal_only,
                strict_generic=True,
            )
            if terminal_only:
                tools = [
                    tool
                    for tool in tools
                    if not isinstance(tool.get("function"), dict)
                    or tool["function"].get("name") != "tools_search"
                ]
            return self._apply_common_tool_constraints(tools, state)

        spreadsheet_open_stage = (
            None if multi_app else spreadsheet_open_semantics.pending_actions(state)
        )
        if spreadsheet_open_stage is not None:
            tools = self._build_tools(
                state.domain,
                spreadsheet_open_stage,
                include_gui=False,
                include_control_tools=False,
                strict_generic=True,
            )
            return self._apply_common_tool_constraints(tools, state)

        strict_required_actions = [
            action
            for action in strict_instruction_required_actions(
                state.domain, state.instruction
            )
            if action not in FORBIDDEN_DATASET_ACTIONS
        ]
        required_mutations = [
            action
            for action in strict_required_actions
            if not is_read_only(action) and (not is_save(action))
        ]
        workspace_open_required = (
            state.domain == "vs_code"
            and "workspace.open" in strict_required_actions
        )
        workspace_open_success = any(
            event.executed
            and not event.error
            and isinstance(event.proposed, dict)
            and event.proposed.get("action") == "workspace.open"
            for event in state.events
        )
        attempted_action_ids = {
            effective_canonical_action(event, state.domain)[:2]
            for event in state.events
            if event.executed and event.proposed.get("kind") == "adapter"
        }
        untried_required_mutations = [
            action
            for action in required_mutations
            if canonical_action_request(state.domain, action, {})[:2]
            not in attempted_action_ids
        ]
        phase_tools = (
            [] if multi_app else source_execution_semantics.build_phase_tools(state)
        )
        consumer_recovery_actions = (
            None
            if multi_app
            else batch_table_semantics.pending_consumer_recovery_actions(
                state, self.selected_actions(state)
            )
        )
        if consumer_recovery_actions:
            # A failed read-only consumer leaves the observed target unchanged.
            # Keep the model on the bounded consumer surface while preserving
            # model-authored arguments.  A pre-mutation write contract error
            # also gets one bounded catalog-search control so the model can
            # discover a reusable route/schema before choosing its next call.
            allow_search = batch_table_semantics.consumer_recovery_allows_search(state)
            consumer_recovery_tools = self._build_tools(
                state.domain,
                list(consumer_recovery_actions),
                include_gui=False,
                include_control_tools=allow_search,
                strict_generic=True,
            )
            if allow_search:
                consumer_recovery_tools = self._keep_search_control(
                    consumer_recovery_tools
                )
            consumer_recovery_tools = self._apply_common_tool_constraints(
                consumer_recovery_tools, state
            )
            continuation_names = {
                tool_name(action)
                for action in consumer_recovery_actions
                if action in batch_table_semantics.BATCH_READ_ACTIONS
            }
            return self._move_named_tools_to_end(
                consumer_recovery_tools, continuation_names
            )
        producer_actions = (
            None
            if multi_app
            else batch_table_semantics.pending_producer_actions(
                state, self.selected_actions(state)
            )
        )
        if producer_actions:
            # A batch workflow must establish its source records before GUI
            # fallback or completion controls compete for the first action.
            # The model still supplies every producer argument unchanged.
            producer_tools = self._build_tools(
                state.domain,
                list(producer_actions),
                include_gui=False,
                include_control_tools=False,
                strict_generic=True,
            )
            return self._apply_common_tool_constraints(producer_tools, state)
        # A rejected completion claim is a bounded recovery transition.  Run
        # this surface before repeated-action/replan handling so a missing
        # persistence step cannot send the model back to the successful write
        # or to an unconstrained GUI fallback.  The phase helper itself still
        # requires real mutation evidence and save/read-back-only obligations.
        if getattr(state, "completion_rejections", 0) > 0 and self._completion_claim_only_retry(state):
            completion_tools = self._build_tools(
                state.domain, [], include_gui=False,
                include_control_tools=True, strict_generic=True,
            )
            last_verified_mutation = next(
                (
                    event
                    for event in reversed(getattr(state, "events", ()))
                    if getattr(event, "executed", False)
                    and getattr(event, "proposed", {}).get("kind") == "adapter"
                    and isinstance(getattr(event, "proposed", {}).get("arguments"), dict)
                ),
                None,
            )
            verified_arguments_hint = ""
            if last_verified_mutation is not None:
                verified_arguments_hint = (
                    " The last verified mutation arguments were "
                    + json.dumps(
                        last_verified_mutation.proposed["arguments"],
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + ". Treat those arguments as the completed requested change."
                )
            for tool in completion_tools:
                function = tool.get("function")
                if isinstance(function, dict) and function.get("name") == "propose_done":
                    function["description"] = (
                        "The successful mutation already satisfies the completion gate. "
                        "Retry propose_done now with one short reason and one to three concise "
                        "evidence strings or records; do not call tools_search or repeat any mutation. "
                        "Do not say the task is incomplete, request another setting value, or discuss "
                        "an opposite value."
                        + verified_arguments_hint
                    )
            return [
                tool for tool in completion_tools
                if isinstance(tool.get("function"), dict)
                and tool["function"].get("name") in {"propose_done", "fail_task"}
            ]
        if getattr(state, "completion_rejections", 0) > 0:
            proactive_tools = completion_recovery.strict_proactive_completion_tools(
                state,
                self._generic_completion_gate(state),
                strict_instruction_required_actions,
                FORBIDDEN_DATASET_ACTIONS,
                is_read_only,
                self.selected_actions,
                strict_semantic_action_equivalents,
            )
            if proactive_tools:
                return self._apply_common_tool_constraints(
                    proactive_tools, state, completion_recovery_surface=True
                )
        recovery_actions = recovery_search_actions(state)
        if recovery_actions is not None:
            recovery_actions = filter_requested_alternative_actions(
                state, recovery_actions
            )
            recovery_actions = bounded_recovery_actions(
                state,
                required_actions=untried_required_mutations,
                searched_actions=recovery_actions,
                selected_actions=self.selected_actions(state),
                limit=max(1, self.config.top_k_actions),
            )
            # A failed required mutation is precisely when a GUI fallback may
            # be useful; keeping it visible does not choose the route.
            recovery_tools = self._build_tools(
                state.domain,
                recovery_actions,
                include_gui=self._recovery_gui_enabled(
                    state,
                    self.config.include_gui and self._gui_execution_configured(),
                ),
                include_control_tools=True,
                strict_generic=True,
            )
            return decorate_recovery_tools(
                self._apply_common_tool_constraints(recovery_tools, state),
                state,
                mode="catalog_search",
            )
        if state.requires_replan() or state.active_request_blocks():
            recovery_actions = bounded_recovery_actions(
                state,
                required_actions=untried_required_mutations,
                searched_actions=list(getattr(state, "expanded_actions", ()))[-4:],
                selected_actions=self.selected_actions(state),
                limit=max(1, self.config.top_k_actions),
            )
            tools = self._build_tools(
                state.domain,
                recovery_actions,
                include_gui=self._recovery_gui_enabled(
                    state,
                    self.config.include_gui and self._gui_execution_configured(),
                ),
                include_control_tools=True,
                strict_generic=True,
            )
            blocked = list(state.active_request_blocks().values())
            if blocked:
                blocked_action_count = len(
                    {item.get("action") for item in blocked if item.get("action")}
                )
                fully_blocked_count = len(state.blocked_actions())
                for tool in tools:
                    function = tool.get("function")
                    if (
                        isinstance(function, dict)
                        and function.get("name") == "tools_search"
                    ):
                        function["description"] += (
                            f" {blocked_action_count} exact request variant(s) are temporarily blocked; "
                            f"{fully_blocked_count} public action(s) have no remaining read variant. "
                            "Choose a different public action or materially different arguments."
                        )
                        break
            return decorate_recovery_tools(
                self._apply_common_tool_constraints(tools, state),
                state,
                mode="replan",
            )
        consumer_actions = (
            None
            if multi_app
            else batch_table_semantics.pending_consumer_actions(
                state, self.selected_actions(state)
            )
        )
        if consumer_actions:
            # Keep the post-inspection handoff small until the model selects a
            # real downstream operation.  Errors still fall through to the
            # normal recovery surface above.
            consumer_tools = self._build_tools(
                state.domain,
                list(consumer_actions),
                include_gui=False,
                include_control_tools=False,
                strict_generic=True,
            )
            return self._apply_common_tool_constraints(consumer_tools, state)
        post_mutation_actions = (
            None
            if multi_app
            else batch_table_semantics.pending_post_mutation_actions(
                state, self.selected_actions(state)
            )
        )
        if post_mutation_actions:
            # After a batch consumer mutation, verify and persist it before
            # exposing unrelated GUI or terminal fallbacks.
            post_mutation_tools = self._build_tools(
                state.domain,
                list(post_mutation_actions),
                include_gui=False,
                include_control_tools=False,
                strict_generic=True,
            )
            return self._apply_common_tool_constraints(post_mutation_tools, state)
        proactive_tools = completion_recovery.strict_proactive_completion_tools(
            state,
            self._generic_completion_gate(state),
            strict_instruction_required_actions,
            FORBIDDEN_DATASET_ACTIONS,
            is_read_only,
            self.selected_actions,
            strict_semantic_action_equivalents,
        )
        if proactive_tools:
            return self._apply_common_tool_constraints(proactive_tools, state)
        if phase_tools:
            return self._apply_common_tool_constraints(phase_tools, state)
        actions = calc_semantics.stage_new_sheet_prerequisites(
            state, self.selected_actions(state), strict_required_actions
        )
        if workspace_open_required and not workspace_open_success:
            # An explicit open instruction already supplies the target. Keep
            # failed workspace inspection and catalog controls from competing
            # with the one required model-authored open call.
            actions = ["workspace.open"]
        if state.domain == "vlc" and "playback.find_local" in strict_required_actions:
            local_find_done = has_positive_local_file_discovery(
                state, "playback.find_local"
            )
            local_open_done = any(
                event.executed
                and not event.error
                and event.proposed.get("action") == "playback.open"
                for event in state.events
            )
            if not local_find_done:
                actions = ["playback.find_local"]
            elif not local_open_done:
                actions = ["playback.open"]
        # A preference request may mention media that is already playing, but
        # it does not need playback discovery or media operations. Keep the
        # first model surface on the single semantic settings API so a small
        # provider does not spend its request budget ranking unrelated VLC
        # actions.
        if (
            state.domain == "vlc"
            and "preferences.configure" in strict_required_actions
            and self._vlc_preference_field(state.instruction)
        ):
            actions = ["preferences.configure"]
        if (
            state.domain == "vs_code"
            and "debugging.configure" in strict_required_actions
        ):
            actions = ["debugging.configure"]
        batch_inspection_pending = (
            False if multi_app else batch_table_semantics.inspection_pending(state)
        )
        if batch_inspection_pending:
            # A successful producer does not establish which application
            # object is the consumer.  Force the model to make the generic
            # zero-argument probe before GUI or terminal controls compete for
            # the next turn.  The probe result remains model-visible and all
            # later mutation arguments are still model-selected.
            actions = [batch_table_semantics.INSPECT_ACTION]
        discovery_only = bool(
            not state.events
            and len(actions) == 1
            and (actions[0] in INSPECT_ACTIONS.get(state.domain, ()))
        ) or local_file_discovery_stage_active(state, actions)
        if (
            not state.events
            and state.domain == "vlc"
            and "preferences.configure" in strict_required_actions
            and self._vlc_preference_field(state.instruction)
        ):
            discovery_only = True
        if (
            not state.events
            and state.domain == "vs_code"
            and "debugging.configure" in strict_required_actions
        ):
            discovery_only = True
        if workspace_open_required and not workspace_open_success:
            discovery_only = True
        # The physical-image route exposes its mutation schema on the first
        # turn so the model cannot conclude that the action is unavailable,
        # while retaining the discovery-only control surface (no search,
        # GUI, or terminal completion choices) and ordered inspection first.
        discovery_only = discovery_only or (
            not state.events
            and state.domain == "libreoffice_impress"
            and is_sized_image_insertion_instruction(str(state.instruction))
            and actions[:2] == ["presentation.inspect", "shape.insert_image"]
        )
        # After a successful image insertion, the owning stage deliberately
        # exposes only the next persistence/read-back action.  Keep the same
        # narrow surface free of search, GUI, and terminal controls so a small
        # model cannot bypass that existing sequence or propose completion
        # before its evidence is present.
        discovery_only = discovery_only or (
            state.domain == "libreoffice_impress"
            and is_sized_image_insertion_instruction(str(state.instruction))
            and state.successful_action_events("shape.insert_image")
            and actions in (["presentation.save"], ["presentation.inspect"])
        )
        discovery_only = discovery_only or batch_inspection_pending
        # A rename instruction already identifies the required mutation and
        # the rename adapter resolves basename sources under bounded defaults.
        # Keep unrelated filesystem tools and completion controls out of the
        # first model request; the next turn exposes completion after success.
        rename_events = state.successful_action_events("filesystem.rename")
        latest_rename_step = max(
            (event.step for event in rename_events), default=None
        )
        rename_readback = latest_rename_step is not None and any(
            event.step > latest_rename_step
            and event.executed
            and not event.error
            and event.proposed.get("kind") == "adapter"
            and effective_canonical_action(event, state.domain)[:2]
            == (state.domain, "filesystem.find")
            for event in state.events
        )
        if latest_rename_step is not None and not rename_readback:
            # The generic completion gate requires a structural read after the
            # final mutation. Keep that handoff to the bounded finder so the
            # model cannot repeat rename or wander into unrelated tools.
            readback_tools = self._build_tools(
                state.domain, ["filesystem.find"], include_gui=False,
                include_control_tools=False, strict_generic=True,
            )
            # The read-back target is observed in the successful rename result.
            # Bind the narrow finder to that destination so a small model cannot
            # search the now-absent source basename or use the file-only default.
            rename_event = max(
                (
                    event
                    for event in state.events
                    if event.step == latest_rename_step
                    and event.executed
                    and not event.error
                ),
                key=lambda event: event.step,
                default=None,
            )
            observed_destination = None
            observed_directory = False
            if rename_event is not None and isinstance(rename_event.result, dict):
                def _walk(value: Any) -> None:
                    nonlocal observed_destination, observed_directory
                    if isinstance(value, dict):
                        if observed_destination is None and isinstance(value.get("destination"), str):
                            observed_destination = value["destination"]
                        if value.get("is_directory") is True:
                            observed_directory = True
                        for child in value.values():
                            _walk(child)
                    elif isinstance(value, list):
                        for child in value:
                            _walk(child)
                _walk(rename_event.result)
            finder = next(
                (
                    tool
                    for tool in readback_tools
                    if isinstance(tool.get("function"), dict)
                    and tool["function"].get("name") == "adapter__filesystem_find"
                ),
                None,
            )
            if finder is not None and isinstance(finder["function"].get("parameters"), dict):
                parameters = finder["function"]["parameters"]
                destination_name = Path(observed_destination).name if observed_destination else None
                if destination_name:
                    finder["function"]["description"] += (
                        f" For this structural rename read-back, search the observed destination "
                        f"basename {destination_name!r}; do not search the old source basename."
                    )
                    name_schema = parameters.get("properties", {}).get("name_patterns")
                    if isinstance(name_schema, dict):
                        name_schema["description"] = (
                            f"Use the observed rename destination basename {destination_name!r} "
                            "for this read-back."
                        )
                if observed_directory:
                    kind_schema = parameters.get("properties", {}).get("kind")
                    if isinstance(kind_schema, dict):
                        kind_schema["enum"] = ["directory"]
                        kind_schema["description"] = (
                            "The renamed object was verified as a directory; set kind='directory' "
                            "for this structural read-back."
                        )
                    required = parameters.setdefault("required", [])
                    if "kind" not in required:
                        required.append("kind")
            return self._apply_common_tool_constraints(readback_tools, state)
        if rename_readback and self._generic_completion_gate(state).get("passed"):
            # Once the final rename has been read back, expose only terminal
            # controls. This keeps a completed mutation from re-entering the
            # normal action ranking and being repeated by a small model.
            completion_tools = self._build_tools(
                state.domain, [], include_gui=False,
                include_control_tools=True, strict_generic=True,
            )
            for tool in completion_tools:
                function = tool.get("function")
                if isinstance(function, dict) and function.get("name") == "propose_done":
                    function["description"] = (
                        "The requested filesystem rename and its destination read-back have both "
                        "succeeded. Call propose_done now with concise evidence; do not call "
                        "filesystem.find, repeat the rename, or choose another tool."
                    )
            completion_names = {"propose_done", "fail_task"}
            readback_find_events = [
                event
                for event in state.events
                if event.step > latest_rename_step
                and event.executed
                and not event.error
                and effective_canonical_action(event, state.domain)[:2]
                == (state.domain, "filesystem.find")
            ]
            readback_verified_directory = False
            if readback_find_events:
                def _contains_directory(value: Any) -> bool:
                    if isinstance(value, dict):
                        return value.get("kind") == "directory" or any(
                            _contains_directory(child) for child in value.values()
                        )
                    if isinstance(value, list):
                        return any(_contains_directory(child) for child in value)
                    return False
                readback_verified_directory = any(
                    _contains_directory(event.result) for event in readback_find_events
                )
            if readback_verified_directory:
                # Some small models continue to emit a stale source-name find even
                # after a successful destination read-back. Keep that read-only
                # fallback callable so the evaluator can still observe the completed
                # mutation instead of failing protocol validation.
                completion_tools.insert(0, self._build_tools(
                    state.domain, ["filesystem.find"], include_gui=False,
                    include_control_tools=False, strict_generic=True,
                )[0])
                completion_names.add("adapter__filesystem_find")
            return [
                tool
                for tool in completion_tools
                if tool["function"].get("name") in completion_names
            ]
        rename_only = (
            not state.events
            and state.domain == "os"
            and "filesystem.rename" in strict_required_actions
        )
        if rename_only:
            actions = ["filesystem.rename"]
            discovery_only = True
        if not multi_app:
            discovery_only = discovery_only or workspace_file_semantics.stage_active(
                state, actions
            )
        tools = self._build_tools(
            state.domain,
            actions,
            include_gui=self.config.include_gui
            and self._gui_execution_configured()
            and (not discovery_only)
            and (not untried_required_mutations),
            include_control_tools=not discovery_only,
            strict_generic=True,
        )
        tools = self._apply_common_tool_constraints(tools, state)
        if workspace_open_required and workspace_open_success:
            if not workspace_open_semantics.completion_errors(state):
                completion_tools = [
                    tool
                    for tool in tools
                    if isinstance(tool.get("function"), dict)
                    and tool["function"].get("name")
                    in {"propose_done", "fail_task"}
                ]
                for tool in completion_tools:
                    function = tool.get("function")
                    if (
                        isinstance(function, dict)
                        and function.get("name") == "propose_done"
                    ):
                        function["description"] = (
                            "The requested VS Code workspace.open call succeeded and its "
                            "verification passed. The requested workspace is now open. "
                            "Call propose_done with a short completed reason and evidence; "
                            "do not repeat workspace.open, inspect, or tools_search."
                        )
                return completion_tools
        if (
            not state.events
            and state.domain == "vlc"
            and "preferences.configure" in strict_required_actions
        ):
            preference_field = self._vlc_preference_field(state.instruction)
            if preference_field:
                for tool in tools:
                    function = tool.get("function")
                    if not isinstance(function, dict) or function.get("name") != (
                        "adapter__preferences_configure"
                    ):
                        continue
                    parameters = function.get("parameters")
                    if not isinstance(parameters, dict):
                        continue
                    properties = parameters.get("properties")
                    if isinstance(properties, dict) and preference_field in properties:
                        parameters["properties"] = {
                            preference_field: properties[preference_field]
                        }
                        parameters["required"] = [preference_field]
                        parameters.pop("oneOf", None)
                    break
        return tools
