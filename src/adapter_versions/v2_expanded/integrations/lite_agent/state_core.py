"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state_model import ExecutionEvent
from urllib.parse import unquote, urlparse


from . import (
    impress_semantics,
)
from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
    execution_context_summary,
    has_passed_verification,
)
from .completion_policy import (
    action_is_read_only as is_read_only,
    canonical_action_request,
    action_is_save as is_save,
    effective_canonical_action,
    completion_claim_contradictions as completion_claim_contradictions,
    required_mutation_actions as collect_required_mutation_actions,
)
from .tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
)


from .instruction_semantics import (
    requested_files,
    requested_ordered_image_slides,
    requested_merged_text_regions,
    requested_sheet_copy_lifecycle,
    requested_pivot_count,
    requests_appended_named_rows,
    requested_chart_count,
    requested_last_slide_duplicate_count,
    requested_slide_title_formatting,
    requested_slide_role_text_formatting,
    requested_slide_content_formatting,
    requested_content_textbox_insert,
    requested_matching_indent_without_bullet,
    instruction_required_actions,
)
from .runtime_policy import (
    argument_signature,
)
from .request_blocks import request_block_is_stale


class RuntimeStateCoreMixin:
    def begin_same_vm_soft_restart(
        self,
        reason: str,
        *,
        max_retries: int = 1,
        trigger_step: int | None = None,
        context_limit: int = 8,
    ) -> Any:
        """Delegate the generic in-place recovery transition lazily."""
        from .episode_control import begin_same_vm_soft_restart

        return begin_same_vm_soft_restart(
            self,
            reason,
            max_retries=max_retries,
            trigger_step=trigger_step,
            context_limit=context_limit,
        )

    def mark_tool_result_for_audit(self, event: Any) -> dict[str, Any]:
        """Register an event as requiring the next model audit."""
        from .episode_control import mark_tool_result_for_audit

        return mark_tool_result_for_audit(self, event)

    def record_model_audit(self, proposal: Any) -> dict[str, Any] | None:
        """Record the next complete model turn as the pending event audit."""
        from .episode_control import record_model_audit

        return record_model_audit(self, proposal)

    def has_pending_model_audit(self) -> bool:
        return isinstance(getattr(self, "pending_model_audit", None), dict)

    def successful_adapter_events(self) -> list[ExecutionEvent]:
        return [
            event
            for event in self.events
            if event.executed and event.proposed.get("kind") == "adapter"
        ]

    def context_summary(
        self, limit: int = 12, *, strict_generic: bool = False
    ) -> list[dict[str, Any]]:
        summary = execution_context_summary(
            self.events,
            self.domain,
            limit=limit,
            strict_generic=strict_generic,
        )
        # A soft restart replaces only the transient reasoning context.  Keep
        # the compact recovery handoff visible for its bounded follow-up
        # window, while leaving the immutable event ledger untouched underneath.
        recovery = getattr(self, "recovery_context", None)
        pending_audit = getattr(self, "pending_model_audit", None)
        pending_terminal = getattr(self, "pending_terminal", None)
        if (
            not isinstance(recovery, dict)
            and not isinstance(pending_audit, dict)
            and not isinstance(pending_terminal, dict)
        ) or limit <= 0:
            return summary
        markers: list[dict[str, Any]] = []
        if isinstance(recovery, dict):
            # Keep the successful mutation ledger in its own bounded marker.
            # The pending-audit and recovery markers can consume the whole
            # compact limit; promoting this projection preserves the latest
            # model-selected targets without changing the authoritative events.
            recovery_view = dict(recovery)
            mutation_ledger = recovery_view.pop("successful_mutation_ledger", None)
            if isinstance(mutation_ledger, list) and mutation_ledger:
                markers.append({"recovery_mutation_ledger": mutation_ledger})
            markers.append({"recovery_context": recovery_view})
        if isinstance(pending_audit, dict):
            markers.append(
                {
                    "model_audit_required": {
                        key: pending_audit[key]
                        for key in ("event_step", "tool_class", "status")
                        if key in pending_audit
                    }
                }
            )
        if isinstance(pending_terminal, dict):
            markers.append(
                {
                    "terminal_result_pending_audit": {
                        key: pending_terminal[key]
                        for key in ("event_step", "tool", "status")
                        if key in pending_terminal
                    }
                }
            )
        # The limit already bounds recent events. Trimming this chronological
        # summary again would remove the newest result named by the audit marker.
        return [*markers[:limit], *summary]

    def requires_replan(self) -> bool:
        if not self.events:
            return False
        error = self.events[-1].error
        return isinstance(error, dict) and error.get("type") == "RepeatedActionBlocked"

    def active_request_blocks(self) -> dict[str, dict[str, Any]]:
        next_step = len(self.events) + 1
        blocks: dict[str, dict[str, Any]] = {}
        for event in self.events:
            error = event.error
            if (
                not isinstance(error, dict)
                or error.get("type") != "RepeatedActionBlocked"
            ):
                continue
            action = error.get("blocked_action")
            arguments_signature = error.get("argument_signature")
            blocked_until_step = error.get("blocked_until_step")
            if not isinstance(action, str) or not isinstance(arguments_signature, str):
                continue
            block_scope = error.get("block_scope", "window")
            if block_scope == "episode" or (
                isinstance(blocked_until_step, int) and next_step <= blocked_until_step
            ):
                if request_block_is_stale(self.events, blocked_at_step=event.step):
                    continue
                key = f"{action}:{arguments_signature}:{error.get('error_signature')!r}"
                blocks[key] = {
                    "action": action,
                    "argument_signature": arguments_signature,
                    "blocked_at_step": event.step,
                    "blocked_until_step": blocked_until_step,
                    "block_scope": block_scope,
                    "error_signature": error.get("error_signature"),
                    "previous_error": error.get("previous_error"),
                    "fallback_reason": error.get("fallback_reason"),
                }
                arguments = event.proposed.get("arguments")
                canonical_domain, canonical_action, canonical_arguments = (
                    canonical_action_request(
                        self.domain,
                        action,
                        arguments,
                    )
                )
                blocks[key]["canonical_domain"] = canonical_domain
                blocks[key]["canonical_action"] = canonical_action
                blocks[key]["canonical_argument_signature"] = argument_signature(
                    canonical_arguments
                )
                if action == "adapter.call" and isinstance(arguments, dict):
                    downstream_adapter = arguments.get("adapter")
                    downstream_action = arguments.get("action")
                    if isinstance(downstream_adapter, str) and isinstance(
                        downstream_action, str
                    ):
                        blocks[key]["downstream_route"] = {
                            "adapter": downstream_adapter,
                            "action": downstream_action,
                        }
        return blocks

    def blocked_routes(self) -> set[tuple[str, str]]:
        routes: set[tuple[str, str]] = set()
        for block in self.active_request_blocks().values():
            route = block.get("downstream_route")
            if (
                isinstance(route, dict)
                and isinstance(route.get("adapter"), str)
                and isinstance(route.get("action"), str)
            ):
                routes.add((route["adapter"], route["action"]))
        return routes

    def active_request_block(
        self, action: str, arguments: dict[str, Any]
    ) -> dict[str, Any] | None:
        canonical_domain, canonical_action, canonical_arguments = (
            canonical_action_request(self.domain, action, arguments)
        )
        signature = argument_signature(canonical_arguments)
        return next(
            (
                block
                for block in self.active_request_blocks().values()
                if block.get("canonical_domain", self.domain) == canonical_domain
                and block.get("canonical_action", block["action"]) == canonical_action
                and block.get(
                    "canonical_argument_signature", block["argument_signature"]
                )
                == signature
            ),
            None,
        )

    def active_action_blocks(self) -> dict[str, dict[str, Any]]:
        blocks: dict[str, dict[str, Any]] = {}
        for block in self.active_request_blocks().values():
            blocks.setdefault(block["action"], block)
        return blocks

    def blocked_actions(self) -> set[str]:
        blocked: set[str] = set()
        read_only_variants: dict[str, set[str]] = {}
        for block in self.active_request_blocks().values():
            action = block["action"]
            schema = DIRECT_ACTION_SCHEMAS.get(self.domain, {}).get(action)
            if schema is not None and not schema.get("properties"):
                blocked.add(action)
            elif is_read_only(action):
                read_only_variants.setdefault(action, set()).add(
                    block["argument_signature"]
                )
        blocked.update(
            action
            for action, variants in read_only_variants.items()
            if len(variants) >= 2
        )
        return blocked

    def recovery_search_pending_choice(self) -> bool:
        if not self.events:
            return False
        event = self.events[-1]
        if not event.executed or event.proposed.get("kind") != "catalog":
            return False
        result = event.result
        return bool(
            isinstance(result, dict)
            and isinstance(result.get("recovery"), dict)
            and result["recovery"].get("trigger") == "repeated_action"
        )

    def recommended_mutations_satisfied(self) -> bool:
        required = self.required_mutation_actions()
        if not required:
            return False
        if self.annual_percentage_change_request() is not None:
            return self.annual_percentage_change_mutations_satisfied()
        if self.monthly_column_totals_request() is not None:
            return self.monthly_column_totals_mutations_satisfied()
        if requested_sheet_copy_lifecycle(self.instruction) is not None:
            return self.sheet_copy_lifecycle_mutations_satisfied()
        if requested_slide_title_formatting(self.instruction) is not None:
            return self.slide_title_format_mutations_satisfied()
        if requested_slide_content_formatting(self.instruction) is not None:
            return self.slide_content_format_mutations_satisfied()
        if requested_slide_role_text_formatting(self.instruction) is not None:
            return self.slide_role_text_format_mutations_satisfied()
        for action in required:
            if (
                action
                in {
                    "slide.delete",
                    "shape.delete",
                    "slide.create",
                    "shape.insert_image",
                }
                and requested_ordered_image_slides(self.instruction) is not None
            ):
                if not self.ordered_image_slide_mutations_satisfied():
                    return False
            elif action == "slide.duplicate":
                count = requested_last_slide_duplicate_count(self.instruction)
                if (
                    count is not None
                    and len(self.successful_action_events(action)) < count
                ):
                    return False
            elif action == "pivot.create":
                count = requested_pivot_count(self.instruction)
                if count is not None and len(self.valid_pivot_events()) < count:
                    return False
            elif action == "chart.create":
                count = requested_chart_count(self.instruction)
                if count > 0 and len(self.successful_action_events(action)) < count:
                    return False
            elif (
                action == "shape.format_text"
                and requested_matching_indent_without_bullet(self.instruction)
                is not None
            ):
                if not self.matching_indent_mutation_applied():
                    return False
            elif (
                action == "shape.write_text_native"
                and requested_content_textbox_insert(self.instruction) is not None
            ):
                if not self.content_textbox_mutation_applied():
                    return False
            elif action == "range.write" and requests_appended_named_rows(
                self.instruction
            ):
                if not self.requested_row_labels_satisfied():
                    return False
            elif action in {
                "range.merge",
                "range.write",
            } and requested_merged_text_regions(self.instruction):
                if not self.merged_text_mutations_satisfied():
                    return False
            elif not self.successful_action_events(
                action
            ) and not impress_semantics.satisfies_unexecuted_mutation(self, action):
                return False
        return True

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

    def successful_chart_count(self) -> int:
        return len(self.successful_action_events("chart.create"))

    def successful_pivot_count(self) -> int:
        return len(self.valid_pivot_events())

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

    @staticmethod
    def event_has_verifier_evidence(event: ExecutionEvent) -> bool:
        return event.executed and has_passed_verification(event.result)

    def event_has_save_evidence(self, event: ExecutionEvent) -> bool:
        if not event.executed or not isinstance(event.result, dict):
            return False
        action = effective_canonical_action(event, self.domain)[1]
        event_verified = has_passed_verification(event.result)
        for result in RuntimeStateCoreMixin._result_mappings(event.result):
            saved = result.get("saved")
            if (
                isinstance(saved, dict)
                and saved.get("exists") is True
                and saved.get("valid") is True
            ):
                return True
            has_output = isinstance(result.get("path") or result.get("url"), str)
            size = result.get("size")
            if saved is True and has_output and isinstance(size, int) and size > 0:
                return True
            if is_save(action) and has_output and isinstance(size, int) and size > 0:
                return True
            output_path = result.get("output_path")
            output_bytes = result.get("output_bytes")
            output_sha256 = result.get("output_sha256")
            has_artifact_integrity = (
                isinstance(output_bytes, int)
                and not isinstance(output_bytes, bool)
                and output_bytes > 0
            ) or (
                isinstance(output_sha256, str)
                and re.fullmatch(r"[0-9a-fA-F]{64}", output_sha256) is not None
            )
            if (
                isinstance(output_path, str)
                and output_path.strip()
                and has_artifact_integrity
                and event_verified
            ):
                return True
        verification = event.result.get("verification")
        checks = verification.get("checks") if isinstance(verification, dict) else None
        return bool(
            isinstance(checks, list)
            and any(
                isinstance(check, dict)
                and check.get("type") == "file_saved"
                and check.get("passed") is True
                for check in checks
            )
        )

    def stage_read_satisfied(self, action: str) -> bool:
        """Track Calc source-read stages, not whether an observation may refresh."""
        if action == "range.read" and self.calc_used_range_read_covered():
            return True
        is_pivot_source_read = bool(
            action == "range.read"
            and re.search(r"(?i)\bpivot\b|数据透视", self.instruction)
        )
        if not is_pivot_source_read:
            return False

        if not self.pivot_count_satisfied():
            return bool(self.successful_action_events(action))

        latest_mutation_step = max(
            (
                event.step
                for event in self.events
                if event.executed
                and (
                    event.proposed.get("kind") == "gui"
                    or (
                        event.proposed.get("kind") == "adapter"
                        and not is_read_only(
                            effective_canonical_action(event, self.domain)[1]
                        )
                    )
                )
            ),
            default=0,
        )
        return any(
            event.step > latest_mutation_step
            and event.executed
            and event.proposed.get("kind") == "adapter"
            and effective_canonical_action(event, self.domain)[:2]
            == canonical_action_request(self.domain, action, {})[:2]
            for event in self.events
        )
