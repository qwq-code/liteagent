"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations
import base64
import copy
import hashlib
import json
import re
from typing import Any
from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
    compact_execution_summary_for_model as compact_execution_summary_for_model,
    contains_text_batch_context as contains_text_batch_context,
)
from .completion_policy import (
    completion_claim_contradictions as completion_claim_contradictions,
)
from .structural_observation_recovery import (
    repeated_structural_observation as _repeated_structural_observation,
)
from .filesystem_copy_semantics import (
    collection_copy_path_guidance,
    completion_errors as collection_copy_completion_errors,
)
from .safety import assert_agent_surface_safe as assert_safe_agent_surface
from .source_execution_semantics import protocol_guidance
from .tool_catalog import action_from_tool_name, instruction_requests_code_execution, tool_name
from .instruction_semantics import strict_instruction_required_actions
from .state_model import RuntimeState
from .strict_contracts import RANGE_WRITE_FACADES
from .recovery_surface import last_failure_summary
from .bounded_recovery import recovery_guidance as observed_recovery_guidance
from .completion_outcomes import completion_outcome_issues


# Ordinary protocol retries stay deliberately small.  A failed call after a
# successful multi-file read is different: the batch is the model's working
# set, so it gets a larger but still bounded projection budget.  The complete
# event ledger remains out of band and is never sent to the model.
MODEL_PROTOCOL_RECOVERY_MAX_CHARS = 9_000
MODEL_BATCH_RECOVERY_MAX_CHARS = 16_000
# Keep the existing 18K observation plus its event envelope on normal turns.
MODEL_BATCH_NORMAL_MAX_CHARS = 20_000
# A form transfer needs its exact field names and the previously read source
# together. The ordinary 9K retry discarded both after an output-token limit.
MODEL_FORM_RECOVERY_MAX_CHARS = 24_000
# A truncated tool call still needs enough room to emit a concrete tool call
# after inspecting a large table/document result.  2k was insufficient for
# the Writer table-color task: the model spent the whole recovery turn
# re-enumerating cells and never reached the first mutation.  Keep this
# bounded and below the provider context limit, but restore a usable budget.
MODEL_TRUNCATION_RECOVERY_MIN_TOKENS = 4_096


def _contains_pdf_form_observation(value: Any) -> bool:
    if isinstance(value, dict):
        if (
            value.get("action") == "pdf.form.inspect"
            or value.get("downstream_action") == "pdf.form.inspect"
        ):
            return True
        return any(_contains_pdf_form_observation(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_pdf_form_observation(item) for item in value)
    return False


class AgentProtocolMixin:
    @staticmethod
    def _execution_recovery_pending(state: RuntimeState) -> bool:
        """Use a bounded state projection after a rejected model action.

        A validation or target error is part of the truthful episode ledger,
        but replaying the full batch observation on the next turn can consume
        the model's entire generation budget before it reaches a correction.
        Catalog and completion failures have their own bounded surfaces and do
        not need this projection.
        """
        # A same-VM soft restart can leave the triggering event executed while
        # its transient recovery handoff is still pending. Detect that state
        # before inspecting the latest event so the first replan turn remains
        # bounded instead of falling back to the full transcript.
        if isinstance(getattr(state, "recovery_context", None), dict) or isinstance(
            getattr(state, "pending_runner_replan", None), dict
        ):
            return True
        events = getattr(state, "events", ())
        if not events:
            return False
        latest = events[-1]
        proposed = getattr(latest, "proposed", None)
        return bool(
            not getattr(latest, "executed", False)
            and isinstance(getattr(latest, "error", None), dict)
            and isinstance(proposed, dict)
            and proposed.get("kind") in {"adapter", "gui"}
        )

    def tool_catalog_hash(self, state: RuntimeState) -> str:
        tools = self.tools(state)
        encoded = json.dumps(tools, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _system_message(
        self,
        state: RuntimeState,
        *,
        protocol_recovery: bool = False,
        execution_recovery: bool = False,
        protocol_error: dict[str, Any] | None = None,
    ) -> str:
        environment = (
            f" Active terminal working directory: {state.working_directory}."
            if state.working_directory
            else ""
        )
        source_workflow_guidance = (
            protocol_guidance(state.instruction)
            if state.domain == "multi_apps"
            else None
        )
        calc_guidance = (
            " For Calc table edits, use the observed cell labels and coordinates: a row "
            "whose first populated cell is Total or Subtotal is a row-wide summary. "
            "When its numeric cells are blank, fill every blank period cell and the "
            "final Total cell; do not treat only the last column as the target. For a "
            "summary row r over detail rows s:e, period column c is =SUM(c_s:c_e) "
            "(vertical), and the final Total cell is =SUM(first_period_r:last_period_r) "
            "(horizontal across the summary row); do not put a detail-row formula such "
            "as =SUM(B3:E3) into a summary cell. Also fill any blank trailing Total "
            "cells on detail rows; those use the horizontal detail-row formula "
            "=SUM(first_period_r:last_period_r). When both target lists are observed, "
            "cover their union in the same formula mutation. A summary entry's "
            "period_cells are vertical-SUM targets and its final_total_cell is the "
            "horizontal-SUM target."
            if state.domain == "libreoffice_calc"
            else ""
        )
        filesystem_guidance = (
            " When calling os.filesystem.find, use the exact public shape "
            "adapter=\"os\", action=\"filesystem.find\", payload.params with "
            "roots and name_patterns as native JSON arrays, for example "
            "{\"roots\":[\"~/Desktop\"],\"name_patterns\":[\"*\"]}. "
            "The params key does not accept path. If a supplied folder is unnamed, "
            "start with ~/Desktop; never emit /path/to placeholders. For "
            "os.image.extract_text_batch, payload.params is one object with "
            "input_pattern and cwd_source, for example "
            "{\"input_pattern\":\"*\",\"cwd_source\":\"explicit\","
            "\"cwd_path\":\"/home/user/Desktop\"}; never use path or paths. "
            "For a first batch OCR run, set payload.timeout_ms=300000 beside params. "
            "Choose readers by extension: .xlsx/.ods uses Calc workbook.read_file, "
            ".docx/.odt uses Writer, and PDF forms use os.pdf.form.inspect followed by "
            "os.pdf.form.fill. For spreadsheet-to-PDF work, read the workbook first, "
            "inspect the form fields, then make one explicitly named output per row "
            "using that employee's values. Mailbox folders are not filesystem paths: "
            "query the named Thunderbird folder with messages.query, then save the "
            "selected email attachment with attachments.save before opening it. Use "
            "the exact returned local path; never guess internal attachment paths."
            if state.domain == "multi_apps"
            else (
                " For character formatting inside a literal token, prefer "
                "text.set_format_in_match and select the occurrence plus relative "
                "substring offsets. To subscript the 2 in H2O, select literal H2O, "
                "occurrence 0, match_start_offset 1 and match_end_offset 2. Do not "
                "insert markup such as <sub>; Writer treats it as literal text. If "
                "using text.find with text.set_format, copy paragraph_index, absolute "
                "start/end offsets and matched_text from the same result exactly."
                if state.domain == "libreoffice_writer"
                else ""
            )
        )
        code_execution = source_workflow_guidance or (
            " For a source-code task that explicitly asks you to run or execute the code, read the relevant source and use command.run for a finite baseline reproduction before the first source mutation. After editing, use command.run again for finite verification before propose_done. For an interactive or long-running program, use a bounded import, syntax check, or focused test instead of launching it indefinitely."
            if state.domain == "multi_apps"
            and instruction_requests_code_execution(state.instruction)
            else ""
        )
        replan = (
            " The Runner detected a bounded no-progress cycle. Reconsider the remaining user-visible "
            "outcome and choose one materially different model-selected action or tool search; do not "
            "repeat the same operation and arguments."
            if state.pending_runner_replan is not None
            else ""
        )
        pending_terminal = getattr(state, "pending_terminal", None)
        terminal_audit_guidance = (
            " The previous terminal control result is waiting for your audit. "
            "Review the truthful result and screenshot now: select the same terminal "
            "Tool only to confirm it, or select another public Tool if the task still "
            "needs work. A completion result with status=ok or gate.passed=true "
            "acknowledges the submitted action evidence; it does not independently "
            "verify the final application state. Compare the current screenshot and "
            "tool observations with the user's request. Do not use your previous "
            "completion claim or its acceptance as proof that the task is complete."
            if isinstance(pending_terminal, dict)
            else ""
        )
        failure = last_failure_summary(state)
        failure_guidance = (
            " The latest model-selected call failed or was rejected. Inspect "
            "the reported cause and partial results: re-observe, search, choose a "
            "different public action, or retry only with materially different "
            "arguments. Never replay the identical request."
            if failure
            else ""
        )
        failure_guidance += " " + observed_recovery_guidance(state)
        missing_fields: list[str] = []
        if isinstance(protocol_error, dict):
            raw_fields = protocol_error.get("missing_fields")
            if isinstance(raw_fields, list):
                missing_fields = [
                    field
                    for field in raw_fields
                    if isinstance(field, str)
                    and re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", field)
                ][:8]
        missing_guidance = (
            " Required fields missing from the previous call: "
            + ", ".join(missing_fields)
            + "."
            if missing_fields
            else ""
        )
        # A schema-only list is easy for a small thinking model to acknowledge
        # without changing its next call.  Add one bounded, action-agnostic
        # repair sentence that makes the required fields operational while
        # leaving every semantic value to the model.  In particular, large
        # range writes can be built from a one-cell source followed by the
        # public fill action; this avoids spending the entire recovery budget
        # constructing a giant inline matrix before emitting a call.
        required_call_guidance = ""
        if missing_fields and isinstance(protocol_error, dict):
            failed_tool = protocol_error.get("tool")
            if isinstance(failed_tool, str) and re.fullmatch(
                r"[A-Za-z][A-Za-z0-9_.:-]{0,119}", failed_tool
            ):
                required_call_guidance = (
                    f" The previous {failed_tool} call was incomplete. Emit that "
                    "same public action only with every required top-level field "
                    "present; for a large range, use a small valid source write "
                    "and then the documented fill action instead of omitting a "
                    "required field."
                )
        search_route_guidance = ""
        if (
            isinstance(protocol_error, dict)
            and protocol_error.get("tool") == "tools_search"
            and protocol_recovery
        ):
            search_route_guidance = (
                " The previous tools_search call was not accepted because the public "
                "route was already returned. Choose its matching function from the "
                "current tools list with that function's parameter schema; do not search again."
            )
        repeat_cue = ""
        if protocol_recovery and isinstance(protocol_error, dict):
            recovery_attempt = protocol_error.get("recovery_attempt")
            if isinstance(recovery_attempt, int) and recovery_attempt >= 2:
                repeat_cue = (
                    f" Repeated protocol recovery after {recovery_attempt} rejected "
                    "responses. None of those calls executed. Reconsider the current "
                    "error; do not repeat the malformed call or end with reasoning alone."
                )
        schema_hints: list[str] = []
        if isinstance(protocol_error, dict):
            raw_hints = protocol_error.get("schema_hints")
            if isinstance(raw_hints, list):
                for raw_hint in raw_hints[:8]:
                    if not isinstance(raw_hint, str):
                        continue
                    # Hints are generated from schema keywords by the model
                    # client.  Bound and normalize them again at the prompt
                    # boundary so a malformed transport cannot add prose.
                    hint = " ".join(raw_hint.split())[:180]
                    if hint and hint not in schema_hints:
                        schema_hints.append(hint)
        schema_guidance = (
            " Public schema rules violated by the previous call: "
            + "; ".join(schema_hints)
            + ". Satisfy these rules exactly; do not copy the rejected arguments."
            if schema_hints
            else ""
        )
        if any(
            "roots" in hint and "name_patterns" in hint for hint in schema_hints
        ):
            schema_guidance += (
                " For filesystem.find, send roots and name_patterns as native JSON "
                "arrays. Never use an illustrative /path/to placeholder; when the "
                "provided directory is unnamed, start with ~/Desktop."
            )
        if any(
            "input_pattern" in hint and "cwd_source" in hint
            for hint in schema_hints
        ):
            schema_guidance += (
                " For OCR, payload.params must be one native JSON object such as "
                "{\"input_pattern\":\"receipt_*\",\"cwd_source\":\"explicit\","
                "\"cwd_path\":\"/home/user/Desktop\"}; do not send paths or a paths array."
            )
        if protocol_recovery or execution_recovery:
            recovery_guidance = (
                (
                    (
                        " Bounded execution recovery is active because the previous "
                        "model-selected action was rejected or did not execute. Use the "
                        "truthful error category and choose a materially different public "
                        "action or argument set; never replay the identical request."
                    )
                    if execution_recovery
                    else (
                        " Protocol recovery is active because the previous model response "
                        "was not one complete schema-valid structured call. Emit exactly "
                        "one complete call from the provided tools now; keep reasoning "
                        "brief and do not end with prose. Do not invent, rewrite, or "
                        "inherit arguments. If uncertain, choose the safest available "
                        "observation action."
                    )
                )
                + missing_guidance
                + required_call_guidance
                + schema_guidance
                + repeat_cue
                + search_route_guidance
            )
        else:
            recovery_guidance = ""
        if state.domain == "vlc":
            return (
                "You are a lightweight OSWorld desktop agent for VLC. Perform the user's "
                "task with exactly one complete structured tool call per turn. Prefer the "
                "provided deterministic Adapter tool; use only arguments allowed by its "
                "schema. Do not open or search media unless the user asks for playback. "
                "A rejected or executed=false call is not success. Before propose_done, "
                "use only truthful evidence from successful tool results and do not claim "
                "an unexecuted setting. The task domain is vlc."
                + recovery_guidance
            )
        hybrid_gui = (
            getattr(self, "holo_grounder", None) is not None
            or getattr(self, "holo_gui_gateway", None) is not None
        )
        gui_guidance = (
            " Use gui_request when a visible GUI operation is required: describe the "
            "single intended operation and target without coordinates; Holo will ground "
            "it against the latest screenshot and return one gui_action for the gateway."
            " When the user explicitly names a built-in application feature, invoke "
            "that feature, not a similar-looking result assembled with unrelated edits. "
            "If no Adapter exposes it, use the GUI to find its native command."
            " GUI changes can invalidate earlier inspection results. Before editing a "
            "newly created object, use an available structural inspection to read its "
            "current contents; a placeholder does not mean the whole object is blank."
            if hybrid_gui
            else " Use gui_action only with a concrete reason that deterministic tools cannot satisfy the operation."
        )
        completion_readback = (
            "Before propose_done, save the requested result and check it after the final change. "
            "For Adapter changes, use structural read-back. For Holo GUI changes, review the "
            "latest screenshot: executed=true confirms the input ran, not that the intended "
            "setting or saved file is correct. Do not repeat a GUI change through an Adapter "
            "merely to supply a mutation record. An Adapter result may describe an object on "
            "a non-active worksheet; the screenshot can remain on the active sheet and is not "
            "evidence that the Adapter result is absent. Use one structural inspect call "
            "instead of switching sheets or recreating the object."
            if hybrid_gui
            else "Before propose_done, save when the application has a save action and "
            "structurally inspect the result after the final mutation. An Adapter result may "
            "describe an object on a non-active worksheet; use structural inspect rather than "
            "switching sheets or recreating it."
        )
        return f"""You are a lightweight OSWorld desktop agent. Perform the user's task in the current VM. Call exactly one provided tool per turn. Prefer deterministic Adapter tools over GUI. If a structural inspection tool and a dependent mutation tool are both provided, call the inspection tool first, then use the mutation with the exact documented schema; if only inspection is provided, call it and do not stop with prose because a later turn may expose the dependent action. When structural inspect output already identifies the requested object and an exposed Adapter action accepts that identifier, call the Adapter directly; it does not require the object to be selected or visible in the GUI. Do not navigate or click merely to select an object that inspect already identified. A tool result with executed=false is not a confirmed success; inspect the error and any partial results before choosing a correction. A rejected call did not run, but an execution or verification failure may have changed state. Never claim success from a proposed call. Use only function names in the current tools list. At the start of a multi_apps task, use tools_search to discover an operation. After a successful search, choose the matching currently exposed function and follow its current parameter schema; do not search again merely to refine an available operation. Historical action records and search results describe internal adapter routes, not necessarily the callable function name or argument format for this turn. Put parameters directly in the selected function arguments object; never wrap that object in the function name or an action/arguments envelope. Use tools_search if a required public action is not exposed.{gui_guidance}{calc_guidance}{filesystem_guidance} For people, objects, scenes, layout, or other visual appearance in image files, open each relevant image and inspect the screenshot; OCR only extracts visible text and cannot classify visual subjects. When the instruction explicitly requires command-line or terminal execution, set provenance=\"shell_history\" on each relevant command.run or terminal.show_output call. {completion_readback} A successful Adapter result with verification_passed=true and a matching structural read-back already satisfies that requirement; propose_done instead of calling an unrelated verifier. The completion gate may reject unsupported completion and return missing items. Before propose_done, compare every clause in the instruction against the truthful action ledger. Never claim an argument, value, target, or operation that is absent from an executed=true event; use tools_search to continue when any clause lacks evidence. Benchmark task identifiers, evaluator state, golden artifacts, and task-specific execution routes are unavailable; solve only from the instruction, screenshot, and public generic tools. Task domain: {state.domain}.{code_execution}{environment}{replan}{failure_guidance}{recovery_guidance}{terminal_audit_guidance}"""

    def assert_agent_surface_safe(
        self,
        state: RuntimeState,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> None:
        assert_safe_agent_surface(task_id=state.task_id, messages=messages, tools=tools)

    @staticmethod
    def _image_url(screenshot: bytes) -> str:
        return "data:image/png;base64," + base64.b64encode(screenshot).decode("ascii")

    def _messages(
        self,
        state: RuntimeState,
        screenshot: bytes,
        *,
        protocol_recovery: bool = False,
        execution_recovery: bool | None = None,
        protocol_error: dict[str, Any] | None = None,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        if execution_recovery is None:
            execution_recovery = (
                not protocol_recovery and self._execution_recovery_pending(state)
            )
        bounded_recovery = protocol_recovery or execution_recovery
        if bounded_recovery:
            summary = state.context_summary(limit=4, strict_generic=True)
            recovery_budget = (
                MODEL_FORM_RECOVERY_MAX_CHARS
                if _contains_pdf_form_observation(summary)
                else MODEL_BATCH_RECOVERY_MAX_CHARS
                if contains_text_batch_context(summary)
                else MODEL_PROTOCOL_RECOVERY_MAX_CHARS
            )
            truthful_state = compact_execution_summary_for_model(
                summary,
                max_chars=recovery_budget,
            )
            # When a catalog call is rejected after its route was exposed,
            # omit prior catalog events from the bounded retry context.  Keeping
            # the old search transcript makes small models replay the same
            # unavailable control instead of selecting the exposed Adapter.
            if (
                protocol_recovery
                and isinstance(protocol_error, dict)
                and protocol_error.get("tool") == "tools_search"
                and isinstance(truthful_state, list)
            ):
                truthful_state = [
                    item
                    for item in truthful_state
                    if not (
                        isinstance(item, dict)
                        and item.get("tool") == "tools_search"
                    )
                ]
            state_text = (
                "Compact truthful execution state (failed calls may have partial effects):\n"
                + json.dumps(truthful_state, ensure_ascii=False)
                + "\nReturn exactly one tool call now."
            )
        else:
            summary = state.context_summary(strict_generic=True)
            normal_budget = (
                MODEL_FORM_RECOVERY_MAX_CHARS
                if _contains_pdf_form_observation(summary)
                else MODEL_BATCH_NORMAL_MAX_CHARS
                if contains_text_batch_context(summary)
                else MODEL_PROTOCOL_RECOVERY_MAX_CHARS
            )
            if state.domain == "multi_apps" and len(
                json.dumps(summary, ensure_ascii=False)
            ) > normal_budget:
                summary = compact_execution_summary_for_model(
                    summary, max_chars=normal_budget
                )
            state_text = (
                "Current truthful execution state (failed calls may have partial effects):\n"
                + json.dumps(summary, ensure_ascii=False)
                + "\nChoose the single next action using the instruction, latest tool results, "
                "and current screenshot."
            )
        outcome_issues = completion_outcome_issues(state)
        if outcome_issues:
            state_text += "\ncompletion_outcomes: " + json.dumps(outcome_issues, ensure_ascii=False)
        copy_guidance = collection_copy_path_guidance(state)
        if copy_guidance:
            state_text += "\nCollection-copy path guidance: " + copy_guidance
        copy_status = collection_copy_completion_errors(state)
        if copy_status:
            state_text += "\nOutstanding collection-copy evidence: " + copy_status[0]
        structural_recovery = bool(
            available_tools
            and not any(tool.get('function', {}).get('name') in {'gui_action', 'gui_request'} for tool in available_tools)
            and _repeated_structural_observation(state)
        )
        if structural_recovery:
            state_text += (
                '\nTwo consecutive structural inspections returned the same state. '
                'The screenshot is omitted on this recovery turn; use the observed document '
                'objects to choose the remaining edit, or tools_search for a missing operation. '
                'Another identical inspection does not change the document.'
            )
        request_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": state_text,
            }
        ]
        # API-only episodes do not need a visual input; omitting it keeps the
        # model request bounded when a desktop screenshot is large.
        if self.config.include_gui and not structural_recovery:
            request_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": self._image_url(screenshot)},
                }
            )
        message_content: str | list[dict[str, Any]] = (
            request_content if self.config.include_gui else state_text
        )
        system_message = self._system_message(
            state,
            protocol_recovery=protocol_recovery,
            execution_recovery=bool(execution_recovery),
            protocol_error=protocol_error,
        )
        if not self.config.include_gui:
            return [
                {"role": "system", "content": system_message},
                {
                    "role": "user",
                    "content": state_text + "\n\nTask instruction:\n" + state.instruction,
                },
            ]
        return [
            {"role": "system", "content": system_message},
            {"role": "user", "content": state.instruction},
            {
                "role": "user",
                "content": message_content,
            },
        ]

    def propose(
        self,
        state: RuntimeState,
        screenshot: bytes,
        *,
        protocol_recovery: bool = False,
        execution_recovery: bool | None = None,
        protocol_error: dict[str, Any] | None = None,
        request_timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        # The execution phase follows immediately after ``propose`` in the
        # Runner.  Retain the exact bytes so a delegated GUI request can be
        # grounded against the same observation without changing the Runner
        # or putting screenshot data into RuntimeState.
        self._latest_screenshot = bytes(screenshot)
        tools = self.tools(state)
        messages = self._messages(
            state,
            screenshot,
            protocol_recovery=protocol_recovery,
            execution_recovery=execution_recovery,
            protocol_error=protocol_error,
            available_tools=tools,
        )
        self.assert_agent_surface_safe(state, messages, tools)
        output_token_budget = self.output_token_budget(state)
        if (
            protocol_recovery
            and isinstance(protocol_error, dict)
            and protocol_error.get("finish_reason") == "length"
        ):
            # A recovery turn must have at least enough room to emit the next
            # structured call after a large inspection.  ``min`` preserved a
            # 2048-token caller cap, so the model kept re-enumerating the
            # Writer table and was truncated before selecting a tool.
            output_token_budget = max(
                output_token_budget,
                MODEL_TRUNCATION_RECOVERY_MIN_TOKENS,
            )
        proposal = self.model_client.propose(
            model=self.config.model,
            messages=messages,
            tools=tools,
            temperature=self.config.temperature,
            output_token_budget=output_token_budget,
            enable_thinking=self.config.enable_thinking,
            reasoning_effort=self.config.reasoning_effort,
            reasoning_mode=self.config.reasoning_mode,
            expected_model=self.config.model,
            request_timeout_seconds=request_timeout_seconds,
            presence_penalty=getattr(self.config, "presence_penalty", None),
            thinking_token_budget=getattr(self.config, "thinking_token_budget", None),
            tool_call_stop_sequence=getattr(self.config, "tool_call_stop_sequence", None),
        )
        proposal["_model_visible_tools"] = copy.deepcopy(tools)
        return proposal

    def output_token_budget(self, state: RuntimeState) -> int:
        exposed_tools = self.tools(state)
        exposed_names = {tool["function"]["name"] for tool in exposed_tools}
        # Content-bearing atomic writes can legitimately exceed a short control
        # call's budget. Give direct and discovered routes the same bounded room.
        content_actions = {
            "range.write", "cells.set_formulas", "workbook.create_new",
            "document.append_paragraphs", "table.insert_at_cursor",
            "table.insert_after_text", "text.find_replace", "slide.set_notes",
            "file.replace_literal",
        }

        def is_content_write(tool: dict[str, Any]) -> bool:
            function = tool.get("function", {})
            if not isinstance(function, dict):
                return False
            action = action_from_tool_name(state.domain, str(function.get("name", "")))
            if action in content_actions:
                return True
            parameters = tool.get("function", {}).get("parameters", {})
            candidates = [parameters.get("x-route")]
            candidates.extend(
                branch.get("x-route") for branch in parameters.get("oneOf", [])
                if isinstance(branch, dict)
            )
            return any(
                isinstance(route, dict)
                and route.get("action") in content_actions
                for route in candidates
            )

        if any(is_content_write(tool) for tool in exposed_tools):
            # The same matrix write needs the same room when discovered through
            # multi_apps. Flat atomic projection happens later in model_client.
            return max(self.config.max_output_tokens, 4096)
        if any(
            isinstance(route, dict)
            and route.get("adapter") == "os"
            and route.get("action") == "pdf.form.fill"
            for tool in exposed_tools
            for route in (
                [tool.get("function", {}).get("parameters", {}).get("x-route")]
                + [
                    branch.get("x-route")
                    for branch in tool.get("function", {}).get("parameters", {}).get("oneOf", [])
                    if isinstance(branch, dict)
                ]
            )
        ):
            return max(self.config.max_output_tokens, 4096)
        semantic_hints = set(
            strict_instruction_required_actions(state.domain, state.instruction)
        )
        generic_matrix_write = bool(
            state.domain == "libreoffice_calc"
            and tool_name("range.write") in exposed_names
            and (
                "range.write" in semantic_hints
                or bool(
                    not semantic_hints.intersection(RANGE_WRITE_FACADES)
                    and re.search(
                        "(?i)\\b(?:write|fill|formula|calculate|compute|enter)\\b",
                        state.instruction,
                    )
                    and re.search(
                        "(?i)\\b(?:table|column|columns|cell|cells|range|values?)\\b",
                        state.instruction,
                    )
                )
            )
        )
        return (
            max(self.config.max_output_tokens, 2048)
            if generic_matrix_write
            else self.config.max_output_tokens
        )
