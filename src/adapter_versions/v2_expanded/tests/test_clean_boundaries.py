from __future__ import annotations

import contextlib
import inspect
import io
import json
from pathlib import Path

import pytest

from integrations.lite_agent.adapter_results import execution_context_summary
from integrations.lite_agent.adapter_executor import AdapterExecutor
from integrations.lite_agent.runtime import (
    ExecutionEvent,
    LiteAgent,
    LiteAgentConfig,
    RuntimeState,
)
from integrations.lite_agent.safety import (
    assert_agent_surface_safe,
    sanitize_agent_visible_result,
)
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    FORBIDDEN_DATASET_ACTIONS,
    public_actions,
    search_actions,
)
from integrations.openapa_osworld.network_policy import (
    install_agent_egress_policy,
    verify_agent_egress_policy,
)
from integrations.openapa_osworld.provider import (
    AdapterDockerProvider,
    run_vm_readiness_attempts,
)
from multi_apps_adapter.deploy_host import package_paths
from multi_apps_adapter.actions import MultiAppsActions
from multi_apps_adapter.errors import AdapterError as MultiAppsAdapterError
from multi_apps_adapter.schema import ACTIONS as MULTI_APPS_ACTIONS
from scripts import run_lite_agent_pilot as runner
from scripts.frozen_condition import CONDITION_SCHEMA, validate_frozen_config
from scripts.strict_deployment import (
    STRICT_DENIED_FILENAMES,
    STRICT_EXCLUDED_FILES,
    validate_strict_source_files,
    filter_source_files,
)


class NoAdapterExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("Adapter execution is not expected")


class AdapterFailureExecutor:
    def execute(self, *_args, **_kwargs):
        return {
            "executed": False,
            "error": {
                "Evaluator": {"expected": "answer-sentinel"},
                "detail": (
                    "https://example.invalid/ubuntu_osworld_file_cache/"
                    "task_manifest.json"
                ),
            },
        }


class AdapterExceptionExecutor:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("do not expose a golden evaluator route")


class FakeExecResult:
    def __init__(self, exit_code: int, output: bytes = b"") -> None:
        self.exit_code = exit_code
        self.output = output


class FakePolicyContainer:
    def __init__(self, *, verify_exit_code: int = 0) -> None:
        self.calls: list[tuple[list[str], str]] = []
        self.verify_exit_code = verify_exit_code

    def exec_run(self, command: list[str], *, user: str):
        self.calls.append((command, user))
        script = command[-1]
        if "ipv4=blocked" in script:
            return FakeExecResult(
                self.verify_exit_code,
                b"ipv4=blocked\nipv6=blocked\n"
                if self.verify_exit_code == 0
                else b"drift",
            )
        return FakeExecResult(0)


class LocalPythonController:
    def execute_python_command(self, code: str) -> dict[str, str]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(compile(code, "<guest-sanitizer>", "exec"), {})
        return {"output": output.getvalue()}


@pytest.mark.parametrize("package_name", ["multi_apps_adapter", "os_adapter"])
@pytest.mark.parametrize(
    "manifest_name",
    ["task_manifest.json", "TASK_MANIFEST.JSON", "TaSk_MaNiFeSt.JsOn"],
)
def test_strict_filter_rejects_task_manifest_by_filename(
    tmp_path: Path, package_name: str, manifest_name: str
) -> None:
    package = tmp_path / package_name
    package.mkdir()
    safe = package / "service.py"
    safe.write_text("STATUS = 'ok'\n", encoding="utf-8")
    manifest = package / manifest_name
    manifest.write_text('{"tasks": {}}\n', encoding="utf-8")

    assert "task_manifest.json" in STRICT_DENIED_FILENAMES
    assert "task_manifest.json" in STRICT_EXCLUDED_FILES["multi_apps_adapter"]
    with pytest.raises(RuntimeError, match="forbidden dataset manifests"):
        filter_source_files(package, [safe, manifest])


@pytest.mark.parametrize(
    "route",
    [
        "task%2eexecute",
        r"task\u002eexecute",
        "ｔａｓｋ．ｅｘｅｃｕｔｅ",
        "assessment/grade/multiple_choice_documents",
    ],
)
def test_strict_source_scan_rejects_encoded_forbidden_routes(
    tmp_path: Path, route: str
) -> None:
    package = tmp_path / "os_adapter"
    package.mkdir()
    source = package / "service.py"
    source.write_text(f"ROUTE = {route!r}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="forbidden route"):
        validate_strict_source_files(package, [source])


def test_strict_source_scan_accepts_exact_multiline_runtime_denylist(
    tmp_path: Path,
) -> None:
    package = tmp_path / "multi_apps_adapter"
    package.mkdir()
    source = package / "actions.py"
    source.write_text(
        "FORBIDDEN_DATASET_ACTIONS = {\n"
        '    "task.execute",\n'
        '    "task.inspect",\n'
        '    "artifact.materialize",\n'
        '    "assessment.grade_multiple_choice_documents",\n'
        "}\n",
        encoding="utf-8",
    )

    validate_strict_source_files(package, [source])


def test_strict_source_scan_rejects_forbidden_route_outside_exact_denylist(
    tmp_path: Path,
) -> None:
    package = tmp_path / "multi_apps_adapter"
    package.mkdir()
    source = package / "actions.py"
    source.write_text(
        "FORBIDDEN_DATASET_ACTIONS = {\n"
        '    "task.execute",\n'
        '    "task.inspect",\n'
        '    "artifact.materialize",\n'
        '    "assessment.grade_multiple_choice_documents",\n'
        "}\n"
        'ACTIVE_ROUTE = "task.execute"\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="forbidden route"):
        validate_strict_source_files(package, [source])


def test_strict_source_scan_rejects_incomplete_runtime_denylist(
    tmp_path: Path,
) -> None:
    package = tmp_path / "multi_apps_adapter"
    package.mkdir()
    source = package / "actions.py"
    source.write_text(
        'FORBIDDEN_DATASET_ACTIONS = {"task.execute"}\n',
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="forbidden route"):
        validate_strict_source_files(package, [source])


def test_answer_marker_assessment_route_is_absent_from_strict_surfaces() -> None:
    action = "assessment.grade_multiple_choice_documents"
    assert action in FORBIDDEN_DATASET_ACTIONS
    assert action not in MULTI_APPS_ACTIONS
    assert action not in DIRECT_ACTION_SCHEMAS["multi_apps"]
    assert action not in public_actions("multi_apps")
    matches = search_actions(
        "multi_apps",
        "grade multiple choice documents using the reference answers",
        instruction="grade the documents",
        strict_generic=True,
        limit=20,
    )
    assert all(item.get("action") != action for item in matches)


def test_forbidden_assessment_route_is_removed_from_event_errors_and_messages() -> None:
    action = "assessment.grade_multiple_choice_documents"
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Inspect the current workbook.",
    )
    state.events.append(
        ExecutionEvent(
            step=1,
            timestamp_utc="2026-08-30T00:00:00Z",
            proposed={
                "kind": "adapter",
                "tool": "adapter_assessment_grade_multiple_choice_documents",
                "action": action,
                "arguments": {},
            },
            executed=False,
            error={"message": f"{action} failed"},
        )
    )

    context = json.dumps(
        execution_context_summary(
            state.events,
            state.domain,
            strict_generic=True,
        ),
        ensure_ascii=False,
    ).casefold()
    assert action.casefold() not in context
    assert "assessment_grade_multiple_choice_documents" not in context

    with pytest.raises(RuntimeError, match="forbidden dataset routes"):
        from integrations.lite_agent.safety import assert_agent_surface_safe

        assert_agent_surface_safe(
            task_id=state.task_id,
            messages=[{"role": "user", "content": action}],
            tools=[],
        )


def test_multi_apps_adapter_rejects_answer_marker_route_even_when_called_directly() -> (
    None
):
    with pytest.raises(MultiAppsAdapterError, match="disabled in generic-only mode"):
        MultiAppsActions().dispatch(
            "assessment.grade_multiple_choice_documents", {}, 1.0
        )


@pytest.mark.parametrize(
    "route",
    [
        "TASK.EXECUTE",
        "task-execute",
        "task/execute",
        "task execute",
        "taskexecute",
        "Assessment.Grade.Multiple.Choice.Documents",
        "assessment-grade-multiple-choice-documents",
        "assessment/grade/multiple_choice_documents",
        "assessmentgrademultiplechoicedocuments",
        "artifact_materialize",
    ],
)
def test_forbidden_route_variants_are_rejected_before_adapter_http(route: str) -> None:
    executor = AdapterExecutor({"multi_apps": "http://unused"})

    direct = executor._policy_error("multi_apps", route, {})
    nested = executor._policy_error(
        "multi_apps",
        "adapter.call",
        {
            "adapter": "os",
            "action": route,
            "params": {},
        },
    )

    assert direct is not None
    assert nested is not None
    with pytest.raises(MultiAppsAdapterError, match="disabled"):
        MultiAppsActions().dispatch(route, {}, 1.0)


@pytest.mark.parametrize(
    "route",
    [
        "task%2Eexecute",
        "task%252Eexecute",
        "task%25252Eexecute",
        r"task%255Cu002Eexecute",
        r"task\u002Eexecute",
        "ｔａｓｋ．ｅｘｅｃｕｔｅ",
        "Assessment/Grade/Multiple_Choice_Documents",
    ],
)
def test_encoded_forbidden_routes_are_rejected_before_adapter_http(route: str) -> None:
    executor = AdapterExecutor({"multi_apps": "http://unused"})

    assert executor._policy_error("multi_apps", route, {}) is not None
    assert (
        executor._policy_error(
            "multi_apps",
            "adapter.call",
            {"adapter": "os", "action": route, "params": {}},
        )
        is not None
    )
    with pytest.raises(MultiAppsAdapterError, match="disabled"):
        MultiAppsActions().dispatch(route, {}, 1.0)


@pytest.mark.parametrize(
    "encoded_domain, encoded_action",
    [
        (
            "".join(f"%{ord(character):02X}" for character in "vlc"),
            "".join(f"%{ord(character):02X}" for character in "media.extract_audio"),
        ),
        ("ＶＬＣ", "ｍｅｄｉａ．ｅｘｔｒａｃｔ＿ａｕｄｉｏ"),
    ],
)
def test_encoded_nested_vlc_profile_is_rejected_before_adapter_http(
    encoded_domain: str, encoded_action: str
) -> None:
    executor = AdapterExecutor({"multi_apps": "http://unused"})
    payload = {
        "adapter": encoded_domain,
        "action": encoded_action,
        "params": {"profile": "user-provided"},
    }

    assert (
        executor._policy_error(
            "multi_apps",
            "adapter.call",
            {"payload": payload},
        )
        is not None
    )
    with pytest.raises(MultiAppsAdapterError, match="profiles are disabled"):
        MultiAppsActions._enforce_downstream_policy(
            encoded_domain,
            encoded_action,
            {"profile": "user-provided"},
        )


def test_deeply_encoded_forbidden_route_fails_closed() -> None:
    encoded_separator = "%2E"
    for _ in range(20):
        encoded_separator = encoded_separator.replace("%", "%25", 1)
    route = f"task{encoded_separator}execute"

    executor = AdapterExecutor({"multi_apps": "http://unused"})
    assert executor._policy_error("multi_apps", route, {}) is not None
    assert sanitize_agent_visible_result({"action": route}, "synthetic-task") == {
        "action": "<internal-benchmark-metadata>"
    }


def test_strict_multi_apps_package_excludes_answer_marker_implementation() -> None:
    package_root = Path(__file__).parents[1]
    packaged = {
        path.relative_to(package_root / "multi_apps_adapter").as_posix()
        for path in package_paths(package_root)
    }
    assert "assessment_grading.py" not in packaged


def test_runner_separates_model_protocol_failure_from_environment_failure() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Inspect the current workbook.",
    )
    failure = runner.ModelRequestFailure(
        [{"type": "StructuredToolProtocolError"}],
        protocol_failure=True,
    )

    assert runner.classify_runner_exception("agent", failure, state) == (
        "model_protocol_failure",
        "generic_api_only",
    )
    assert runner.classify_runner_exception("setup", RuntimeError("setup"), state) == (
        "environment_failure",
        "environment_failure",
    )


def test_runner_stops_and_classifies_provider_attestation_failure_as_invalid_configuration() -> (
    None
):
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Inspect the current workbook.",
    )
    failure = runner.ModelRequestFailure(
        [
            {
                "type": "StructuredToolProtocolError",
                "protocol": {"configuration_failure": True},
            }
        ],
        protocol_failure=True,
        configuration_failure=True,
    )

    assert runner.classify_runner_exception("agent", failure, state) == (
        "invalid_configuration",
        "invalid_configuration",
    )


@pytest.mark.parametrize(
    "manifest_name",
    ["task_manifest.json", "TASK_MANIFEST.JSON", "TaSk_MaNiFeSt.JsOn"],
)
def test_multi_apps_recursive_packaging_fails_if_manifest_appears(
    tmp_path: Path, manifest_name: str
) -> None:
    package = tmp_path / "multi_apps_adapter"
    package.mkdir()
    (package / "service.py").write_text("STATUS = 'ok'\n", encoding="utf-8")
    (package / manifest_name).write_text('{"tasks": {}}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="forbidden manifests"):
        package_paths(tmp_path)


def test_guest_sanitizer_removes_top_level_and_nested_manifests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "multi_apps_adapter"
    nested = package / "stale"
    nested.mkdir(parents=True)
    top_level = package / "TASK_MANIFEST.JSON"
    nested_manifest = nested / "TaSk_MaNiFeSt.JsOn"
    top_level.write_text('{"tasks": {}}\n', encoding="utf-8")
    nested_manifest.write_text('{"tasks": {}}\n', encoding="utf-8")
    monkeypatch.setattr(runner, "GENERIC_GUEST_PACKAGE_ROOTS", (str(package),))

    result = runner.sanitize_generic_guest_deployment(LocalPythonController())

    assert result["remaining"] == []
    assert not top_level.exists()
    assert not nested_manifest.exists()


def test_gui_executor_metadata_never_reaches_model_context() -> None:
    leaked_value = "future-osworld-evaluator-metadata"

    def gui_executor(_arguments: dict) -> dict:
        return {
            "status": "ok",
            "executed": True,
            "result": {
                "info": {
                    "evaluator": leaked_value,
                    "task_id": "task-id-sentinel",
                }
            },
        }

    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        NoAdapterExecutor(),  # type: ignore[arg-type]
        gui_executor=gui_executor,
    )
    state = RuntimeState(
        task_id="task-id-sentinel",
        domain="os",
        instruction="Use GUI fallback to open the visible application.",
    )

    event = agent.execute_proposal(
        state,
        {
            "tool": "gui_action",
            "arguments_raw": json.dumps(
                {
                    "action": "click",
                    "x": 100,
                    "y": 200,
                    "fallback_reason": "No deterministic application API is available.",
                }
            ),
        },
    )

    assert event.executed is True
    assert event.result == {"environment_acknowledged": True}
    model_context = json.dumps(execution_context_summary(state.events, state.domain))
    assert leaked_value not in model_context
    assert "task-id-sentinel" not in model_context


def test_result_sanitizer_removes_case_variant_task_identity() -> None:
    state = RuntimeState(
        task_id="task-id-sentinel",
        domain="os",
        instruction="Read the current clipboard text.",
    )
    executor = AdapterFailureExecutor()
    original_execute = executor.execute

    def execute_with_identity(*args, **kwargs):
        result = original_execute(*args, **kwargs)
        result["error"]["identity"] = "TASK-ID-SENTINEL"
        return result

    executor.execute = execute_with_identity  # type: ignore[method-assign]
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        executor,  # type: ignore[arg-type]
    )

    event = agent.execute_proposal(
        state,
        {"tool": "adapter__clipboard_get", "arguments_raw": "{}"},
    )

    assert "TASK-ID-SENTINEL" not in json.dumps(event.error)


def test_result_sanitizer_removes_expected_state_recursively() -> None:
    value = {
        "passed": False,
        "observed_state": {"path": "/tmp/report.xlsx", "sha256": "observed"},
        "expected_state": {"path": "/tmp/report.xlsx", "sha256": "gold-hash"},
        "checks": [
            {
                "type": "sha256",
                "passed": False,
                "expected": "gold-hash",
                "nested": {"reference_state": {"sha256": "gold-hash"}},
            }
        ],
    }

    sanitized = sanitize_agent_visible_result(value, "synthetic-task")

    encoded = json.dumps(sanitized, ensure_ascii=False)
    assert sanitized["observed_state"]["sha256"] == "observed"
    assert "expected_state" not in sanitized
    assert "reference_state" not in encoded
    assert "gold-hash" not in encoded


def test_result_sanitizer_preserves_natural_document_language() -> None:
    value = {
        "text": (
            "The answer column is on the right. Expected annual return is 5%. "
            "Reference document title and dataset overview."
        ),
        "task_name": "Quarterly review",
        "task_description": "Read the reference dataset and summarize it.",
    }

    sanitized = sanitize_agent_visible_result(value, "synthetic-task")

    assert sanitized == value


def test_result_sanitizer_does_not_corrupt_short_identity_like_error_text() -> None:
    value = {"detail": "the exact request is blocked; choose another action"}

    assert sanitize_agent_visible_result(value, "x") == value


def test_result_sanitizer_still_redacts_short_identity_as_a_token() -> None:
    value = {"detail": "request x failed"}

    assert sanitize_agent_visible_result(value, "x") == {
        "detail": "request <internal-benchmark-task> failed"
    }


def test_surface_boundary_allows_natural_document_language() -> None:
    assert_agent_surface_safe(
        task_id="synthetic-task",
        messages=[
            {
                "role": "user",
                "content": (
                    "Please answer from the reference dataset; the expected "
                    "column is part of the visible document."
                ),
            }
        ],
        tools=[],
    )


def test_surface_boundary_does_not_join_route_tokens_across_json_fields() -> None:
    state = json.dumps(
        [{"reason": "Proceed with the task", "executed": True}],
        ensure_ascii=False,
    )

    assert_agent_surface_safe(
        task_id="synthetic-task",
        messages=[{"role": "user", "content": state}],
        tools=[],
    )


def test_surface_boundary_preserves_punctuation_separated_document_prose() -> None:
    text = "The agent can select actions, execute subtasks, and evaluate results."
    sanitized = sanitize_agent_visible_result({"text": text}, "synthetic-task")
    assert sanitized["text"] == text
    assert_agent_surface_safe(
        task_id="synthetic-task",
        messages=[{"role": "user", "content": text}],
        tools=[],
    )

@pytest.mark.parametrize(
    "route",
    [
        "task.execute",
        "task execute",
        "task_execute",
        "task%2Eexecute",
        r"task\u002Eexecute",
    ],
)
def test_surface_boundary_rejects_routes_inside_serialized_state(route: str) -> None:
    state = json.dumps([{"detail": route}], ensure_ascii=False)

    with pytest.raises(RuntimeError, match="forbidden dataset routes"):
        assert_agent_surface_safe(
            task_id="synthetic-task",
            messages=[{"role": "user", "content": state}],
            tools=[],
        )


@pytest.mark.parametrize(
    "route",
    [
        "task.execute",
        "task.inspect",
        "task_execute",
        "task_inspect",
    ],
)
def test_result_sanitizer_removes_forbidden_task_routes(route: str) -> None:
    sanitized = sanitize_agent_visible_result({"action": route}, "synthetic-task")

    assert route not in json.dumps(sanitized, ensure_ascii=False)


@pytest.mark.parametrize(
    "key",
    [
        "task-id",
        "TASKUUID",
        "expected-state",
        "golden-file",
        "dataset-order",
        "evaluator-url",
        "reference-profile",
        "assessment-grade-multiple-choice-documents",
    ],
)
def test_result_sanitizer_removes_sensitive_key_variants(key: str) -> None:
    sanitized = sanitize_agent_visible_result({key: "secret"}, "synthetic-task")

    assert sanitized == {}


def test_encoded_task_identity_is_redacted_and_rejected() -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    encoded = "".join(f"%{ord(character):02X}" for character in task_id)

    sanitized = sanitize_agent_visible_result({"message": encoded}, task_id)
    assert sanitized == {"message": "<internal-benchmark-metadata>"}

    with pytest.raises(RuntimeError, match="task identity"):
        assert_agent_surface_safe(
            task_id=task_id,
            messages=[{"role": "user", "content": encoded}],
            tools=[],
        )


def test_unicode_escaped_task_identity_is_redacted_and_rejected() -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    encoded = "".join(f"\\u{ord(character):04x}" for character in task_id)
    doubly_escaped = encoded.replace("\\", "\\\\")

    for value in (encoded, doubly_escaped):
        sanitized = sanitize_agent_visible_result({"message": value}, task_id)
        assert sanitized == {"message": "<internal-benchmark-metadata>"}
        with pytest.raises(RuntimeError, match="task identity"):
            assert_agent_surface_safe(
                task_id=task_id,
                messages=[{"role": "user", "content": value}],
                tools=[],
            )


@pytest.mark.parametrize(
    "encoded",
    [
        "".join(f"%{ord(character):02X}" for character in "osworld_baby_justin_bieber"),
        "".join(
            f"\\u{ord(character):04x}" for character in "osworld_baby_justin_bieber"
        ),
    ],
)
def test_encoded_dataset_reference_marker_is_redacted_and_rejected(
    encoded: str,
) -> None:
    sanitized = sanitize_agent_visible_result({"message": encoded}, "safe-task")
    assert sanitized == {"message": "<internal-benchmark-metadata>"}

    with pytest.raises(RuntimeError, match="hidden benchmark metadata"):
        assert_agent_surface_safe(
            task_id="safe-task",
            messages=[{"role": "user", "content": encoded}],
            tools=[],
        )


@pytest.mark.parametrize("key", ["expected_state", "golden_file", "evaluator_url"])
def test_hidden_metadata_key_is_rejected_by_first_request_boundary(key: str) -> None:
    encoded_key = "".join(f"%{ord(character):02X}" for character in key)
    assert sanitize_agent_visible_result({encoded_key: "secret"}, "safe-task") == {}

    with pytest.raises(RuntimeError, match="metadata keys"):
        assert_agent_surface_safe(
            task_id="safe-task",
            messages=[{"role": "user", "content": {encoded_key: "secret"}}],
            tools=[],
        )


def test_strict_source_scan_rejects_encoded_task_identity(tmp_path: Path) -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    encoded = "".join(f"%{ord(character):02X}" for character in task_id)
    package = tmp_path / "os_adapter"
    package.mkdir()
    source = package / "service.py"
    source.write_text(f"TASK = {encoded!r}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="UUID constant"):
        validate_strict_source_files(package, [source])


def test_strict_source_scan_rejects_unicode_escaped_task_identity(
    tmp_path: Path,
) -> None:
    task_id = "123e4567-e89b-12d3-a456-426614174000"
    encoded = "".join(f"\\u{ord(character):04x}" for character in task_id)
    package = tmp_path / "os_adapter"
    package.mkdir()
    source = package / "service.py"
    source.write_text(f"TASK = {encoded!r}\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="UUID constant"):
        validate_strict_source_files(package, [source])


class VerificationResultExecutor:
    def execute(self, *_args, **_kwargs):
        return {
            "executed": True,
            "result": {
                "passed": False,
                "observed_state": {"path": "/tmp/report.xlsx"},
                "expected_state": {"path": "/tmp/report.xlsx", "sha256": "gold-hash"},
            },
        }


def test_verifier_expected_state_never_reaches_model_context() -> None:
    state = RuntimeState(
        task_id="synthetic-task",
        domain="multi_apps",
        instruction="Verify the current artifact.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-08-29T00:00:00Z",
                proposed={
                    "kind": "catalog",
                    "tool": "tools_search",
                    "arguments": {"query": "filesystem.find"},
                },
                executed=True,
                result={
                    "status": "ok",
                    "matches": [
                        {
                            "action": "adapter.call",
                            "adapter": "os",
                            "downstream_action": "filesystem.find",
                        }
                    ],
                },
            )
        ],
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        VerificationResultExecutor(),  # type: ignore[arg-type]
    )

    event = agent.execute_proposal(
        state,
        {
            "tool": "adapter__adapter_call",
            "arguments_raw": json.dumps(
                {
                    "adapter": "os",
                    "action": "filesystem.find",
                    "payload": {
                        "params": {
                            "roots": ["/tmp"],
                            "name_contains": "report.xlsx",
                        }
                    },
                }
            ),
        },
    )

    assert event.executed is True
    model_context = json.dumps(execution_context_summary(state.events, state.domain))
    assert "expected_state" not in model_context
    assert "gold-hash" not in model_context
    assert "/tmp/report.xlsx" in model_context


@pytest.mark.parametrize(
    "executor",
    [AdapterFailureExecutor(), AdapterExceptionExecutor()],
)
def test_adapter_failure_and_exception_metadata_never_reaches_model_context(
    executor,
) -> None:
    state = RuntimeState(
        task_id="task-id-sentinel",
        domain="os",
        instruction="Read the current clipboard text.",
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        executor,  # type: ignore[arg-type]
    )

    event = agent.execute_proposal(
        state,
        {"tool": "adapter__clipboard_get", "arguments_raw": "{}"},
    )

    assert event.executed is False
    model_context = json.dumps(execution_context_summary(state.events, state.domain))
    for forbidden in (
        "answer-sentinel",
        "task_manifest.json",
        "ubuntu_osworld_file_cache",
        "golden",
        "evaluator",
    ):
        assert forbidden not in model_context.casefold()


def test_gui_failure_metadata_never_reaches_model_context() -> None:
    def gui_executor(_arguments: dict) -> dict:
        return {
            "executed": False,
            "error": {
                "EXPECTED": "answer-sentinel",
                "detail": "ubuntu_osworld_file_cache/golden",
            },
        }

    state = RuntimeState(
        task_id="task-id-sentinel",
        domain="os",
        instruction="Use GUI fallback for the visible application.",
    )
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        NoAdapterExecutor(),  # type: ignore[arg-type]
        gui_executor=gui_executor,
    )

    event = agent.execute_proposal(
        state,
        {
            "tool": "gui_action",
            "arguments_raw": json.dumps(
                {
                    "action": "click",
                    "x": 100,
                    "y": 200,
                    "fallback_reason": "No deterministic application API is available.",
                }
            ),
        },
    )

    assert event.executed is False
    model_context = json.dumps(execution_context_summary(state.events, state.domain))
    assert "answer-sentinel" not in model_context
    assert "ubuntu_osworld_file_cache" not in model_context
    assert "golden" not in model_context.casefold()


def test_network_policy_installs_ipv4_and_ipv6_fail_closed_rules() -> None:
    container = FakePolicyContainer()

    evidence = install_agent_egress_policy(container)

    assert evidence["agent_initiated_public_or_private_egress_allowed"] is False
    assert evidence["host_initiated_reply_traffic_allowed"] is True
    assert len(container.calls) == 2
    install_script = container.calls[0][0][-1]
    assert "iptables ip6tables" in install_script
    assert "--ctdir REPLY" in install_script
    assert "-j DROP" in install_script
    assert all(user == "root" for _command, user in container.calls)


def test_network_policy_verification_fails_closed_on_rule_drift() -> None:
    container = FakePolicyContainer(verify_exit_code=1)

    with pytest.raises(RuntimeError, match="verification failed"):
        verify_agent_egress_policy(container)


def test_provider_installs_egress_policy_after_vm_ready() -> None:
    source = inspect.getsource(AdapterDockerProvider.create)

    assert source.index("self._wait_for_vm_ready()") < source.index(
        "install_agent_egress_policy("
    )


def test_provider_rebuilds_once_after_vm_readiness_timeout() -> None:
    events: list[str] = []

    def wait_until_ready() -> None:
        events.append("wait")
        if events.count("wait") == 1:
            raise TimeoutError("VM did not become ready")

    run_vm_readiness_attempts(
        lambda: events.append("start"),
        wait_until_ready,
        lambda: events.append("cleanup"),
    )

    assert events == ["start", "wait", "cleanup", "start", "wait"]


def test_provider_preserves_second_vm_readiness_timeout() -> None:
    events: list[str] = []

    def wait_until_ready() -> None:
        events.append("wait")
        raise TimeoutError("VM did not become ready")

    with pytest.raises(TimeoutError, match="VM did not become ready"):
        run_vm_readiness_attempts(
            lambda: events.append("start"),
            wait_until_ready,
            lambda: events.append("cleanup"),
        )

    assert events == [
        "start",
        "wait",
        "cleanup",
        "start",
        "wait",
        "cleanup",
    ]


def test_frozen_condition_forbids_guest_proxy() -> None:
    config = {
        "status": "frozen",
        "condition": {
            "schema_version": CONDITION_SCHEMA,
            "enforced": True,
            "source_tree": {},
            "result_directory": "experiments/new-condition",
        },
        "protocol": {
            "runs": 1,
            "best_of": False,
            "preserve_every_attempt": True,
            "task_specific_or_golden_exposed": False,
            "guest_proxy": True,
        },
        "model": {"base_urls": ["http://model.invalid/v1"]},
        "vm": {"screen_size": [1920, 1080]},
    }

    with pytest.raises(RuntimeError, match="guest_proxy=false"):
        validate_frozen_config(config)
