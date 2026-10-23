from __future__ import annotations

import copy
import json

import pytest

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from integrations.lite_agent.tool_catalog import build_tools
from integrations.lite_agent.workspace_open_semantics import (
    argument_contract_errors,
    completion_errors,
    path_binds_target,
    requested_workspace_open_intent,
    requested_workspace_open_target,
    required_actions,
)


INSTRUCTION = (
    'Please help me use VS Code to open the "project" in the "user" folder '
    'under "home".'
)
TARGET_PATH = "/home/user/project"
HOME_PATH = "/home/user"


def _event(
    step: int,
    model_path: str,
    observed_path: str,
    *,
    verified: bool = True,
) -> ExecutionEvent:
    arguments = {"path": model_path, "reuse_window": False}
    adapter_result = {
        "status": "ok",
        "result": {
            "expected_name": observed_path.rstrip("/").rsplit("/", 1)[-1],
            "path": observed_path,
            "window_id": "0x04000001",
            "window": {"expected_name": observed_path.rstrip("/").rsplit("/", 1)[-1]},
        },
        "verification": {"passed": verified},
    }
    proposed = {
        "kind": "adapter",
        "action": "workspace.open",
        "arguments": copy.deepcopy(arguments),
    }
    return ExecutionEvent(
        step=step,
        timestamp_utc="2026-09-01T00:00:00Z",
        proposed=proposed,
        executed=True,
        result=adapter_result,
    )


def _state(
    events: list[ExecutionEvent],
    *,
    instruction: str = INSTRUCTION,
    domain: str = "vs_code",
) -> RuntimeState:
    return RuntimeState(
        task_id="synthetic-workspace-open",
        domain=domain,
        instruction=instruction,
        events=events,
    )


@pytest.mark.parametrize(
    ("instruction", "expected"),
    [
        (INSTRUCTION, "project"),
        (
            "Open the folder named `analytics-dashboard` in VS Code.",
            "analytics-dashboard",
        ),
        ('Load "Alpha Workspace" as a workspace in VS Code.', "Alpha Workspace"),
        ('Open the "project" in VS Code.', "project"),
        ("Use VS Code to open project named phoenix.", "phoenix"),
        (
            "Open workspace called team.code-workspace in VS Code.",
            "team.code-workspace",
        ),
    ],
)
def test_explicit_workspace_open_paraphrases_extract_one_target(
    instruction: str, expected: str
) -> None:
    assert requested_workspace_open_target(instruction) == expected


def test_order175_instruction_preserves_explicit_ordered_hierarchy() -> None:
    intent = requested_workspace_open_intent(INSTRUCTION)

    assert intent is not None
    assert intent.target == "project"
    assert intent.ancestors == ("home", "user")
    assert intent.allow_code_workspace is False


@pytest.mark.parametrize(
    ("instruction", "ancestors"),
    [
        (
            'Open the "widget" project in the "repos" folder under the "user" folder.',
            ("user", "repos"),
        ),
        (
            'Open the "widget-app" folder in the "repos" directory under '
            'the "user" folder.',
            ("user", "repos"),
        ),
    ],
)
def test_generic_location_paraphrases_preserve_named_ancestors(
    instruction: str, ancestors: tuple[str, ...]
) -> None:
    intent = requested_workspace_open_intent(instruction)

    assert intent is not None
    assert intent.ancestors == ancestors


@pytest.mark.parametrize(
    "instruction",
    [
        "Open VS Code.",
        "Open the project in VS Code.",
        "Open a folder in VS Code.",
        "Open README.md in VS Code.",
        'Open the file "project" in VS Code.',
        'Open "project" file in VS Code.',
        'Open "README" in the current project in VS Code.',
        "Open project named alpha and then open project named beta in VS Code.",
        (
            'Open project named alpha in the "one" folder, then open project named alpha '
            'in the "two" folder.'
        ),
        'Open VS Code and search for the "project" folder.',
        'Open the command palette and choose the "project" workspace.',
        'Open "project" view in VS Code.',
        'Open "project" settings in VS Code.',
        'Open the "project" in the editor.',
        'Open the "project" in a new tab.',
        'Open the "project" under Source Control.',
        'Don\'t open the "project" folder in VS Code.',
        'Do not open the "project" folder in VS Code.',
        'Please avoid open the "project" folder in VS Code.',
        'Do everything except open the "project" folder in VS Code.',
        "Open project named alpha and project named beta.",
        'Open the "alpha" project and the "beta" project in VS Code.',
        'Open the project "alpha" and "beta" in VS Code.',
        'Open project named "alpha" and "beta" in VS Code.',
        'Open the "alpha" project together with "beta" in VS Code.',
        'Open the project "alpha", "beta", and "gamma" in VS Code.',
        "Open project named alpha and beta in VS Code.",
        "Open folder named alpha, beta in VS Code.",
        "Open project named alpha along with workspace named beta.",
        "Open project settings in VS Code.",
        "Open the /home/user/project folder in VS Code.",
        "Inspect the workspace named alpha in VS Code.",
    ],
)
def test_file_open_non_open_and_ambiguous_instructions_do_not_activate(
    instruction: str,
) -> None:
    assert requested_workspace_open_target(instruction) is None
    assert required_actions("vs_code", instruction) == []
    assert completion_errors(_state([], instruction=instruction)) == []


def test_required_action_is_scoped_to_vs_code() -> None:
    assert required_actions("vs_code", INSTRUCTION) == ["workspace.open"]
    assert strict_instruction_required_actions("vs_code", INSTRUCTION) == [
        "workspace.open"
    ]
    for domain in ("os", "multi_apps", "chrome", "libreoffice_writer"):
        assert required_actions(domain, INSTRUCTION) == []
        assert (
            argument_contract_errors(
                _state([], domain=domain), "workspace.open", {"path": HOME_PATH}
            )
            == []
        )


def test_conjunction_followed_by_new_verb_is_not_a_second_target() -> None:
    instruction = 'Open the "alpha" project and change setting "beta".'

    assert requested_workspace_open_target(instruction) == "alpha"


@pytest.mark.parametrize(
    "path",
    [
        TARGET_PATH,
        "/home/user/project/",
    ],
)
def test_target_binding_accepts_exact_name_and_hierarchy(path: str) -> None:
    assert path_binds_target(path, "project") is True
    assert argument_contract_errors(_state([]), "workspace.open", {"path": path}) == []


def test_code_workspace_stem_can_bind_an_instruction_named_workspace() -> None:
    instruction = 'Open the workspace named "team" in VS Code.'
    state = _state([], instruction=instruction)

    assert (
        argument_contract_errors(
            state,
            "workspace.open",
            {"path": "/home/user/team.code-workspace"},
        )
        == []
    )
    assert argument_contract_errors(
        state,
        "workspace.open",
        {"path": "/home/user/team.txt"},
    )


@pytest.mark.parametrize(
    "path",
    [
        "~/",
        HOME_PATH,
        "/",
        "/home/user/other",
        "/tmp/project",
        "/home/other/project",
        "/home/user/work/project",
        "/home/user/PROJECT",
        "/home/user/project.txt",
        "/home/user/project.code-workspace",
        "home/user/project",
        "\\home\\user\\project",
    ],
)
def test_wrong_hierarchy_case_extension_or_separator_is_rejected(path: str) -> None:
    errors = argument_contract_errors(_state([]), "workspace.open", {"path": path})

    assert errors and "explicit instruction hierarchy" in errors[0]


def test_argument_contract_does_not_rewrite_model_selected_window_options() -> None:
    arguments = {
        "path": HOME_PATH,
        "reuse_window": False,
        "close_existing": True,
    }
    original = copy.deepcopy(arguments)

    assert argument_contract_errors(_state([]), "workspace.open", arguments)
    assert arguments == original


def test_completion_binds_direct_model_and_adapter_result_paths() -> None:
    state = _state([_event(1, TARGET_PATH, TARGET_PATH)])

    assert completion_errors(state) == []


def test_preserved_home_only_trajectory_is_rejected() -> None:
    errors = completion_errors(_state([_event(1, "~/", HOME_PATH)]))

    assert errors and "model-selected path" in errors[0]


@pytest.mark.parametrize(
    ("model_path", "observed_path", "message"),
    [
        (TARGET_PATH, HOME_PATH, "does not bind both"),
        (HOME_PATH, TARGET_PATH, "model-selected path"),
    ],
)
def test_model_and_adapter_paths_must_each_bind_the_target(
    model_path: str, observed_path: str, message: str
) -> None:
    errors = completion_errors(_state([_event(1, model_path, observed_path)]))

    assert errors and message in errors[0]


def test_last_verified_workspace_open_defines_completion_state() -> None:
    state = _state(
        [
            _event(1, TARGET_PATH, TARGET_PATH),
            _event(2, HOME_PATH, HOME_PATH),
        ]
    )

    assert completion_errors(state)


def test_unverified_later_open_makes_final_state_unprovable() -> None:
    state = _state(
        [
            _event(1, TARGET_PATH, TARGET_PATH),
            _event(2, HOME_PATH, HOME_PATH, verified=False),
        ]
    )

    errors = completion_errors(state)

    assert errors and "last executed" in errors[0]


def test_completion_requires_adapter_observed_resolved_path() -> None:
    event = _event(1, TARGET_PATH, TARGET_PATH)
    event.result["result"].pop("path")

    errors = completion_errors(_state([event]))

    assert errors and "resolved path" in errors[0]


def test_unrelated_envelope_path_is_not_workspace_observation() -> None:
    event = _event(1, TARGET_PATH, HOME_PATH)
    event.result["path"] = TARGET_PATH

    errors = completion_errors(_state([event]))

    assert errors and "does not bind both" in errors[0]


def test_workspace_result_expected_name_must_bind_the_same_target() -> None:
    event = _event(1, TARGET_PATH, TARGET_PATH)
    event.result["result"]["expected_name"] = "other"

    errors = completion_errors(_state([event]))

    assert errors and "expected workspace name" in errors[0]


def test_adapter_observed_path_must_be_absolute() -> None:
    event = _event(1, TARGET_PATH, "home/user/project")

    errors = completion_errors(_state([event]))

    assert errors and "does not bind both" in errors[0]


def test_generic_completion_gate_rejects_home_only_and_accepts_target() -> None:
    completion = {"reason": "done", "evidence": ["workspace opened"]}

    rejected = CompletionMixin._generic_completion_gate(
        _state([_event(1, "~/", HOME_PATH)]), completion
    )
    accepted = CompletionMixin._generic_completion_gate(
        _state([_event(1, TARGET_PATH, TARGET_PATH)]), completion
    )

    assert rejected["passed"] is False
    assert any("model-selected path" in item for item in rejected["missing"])
    assert accepted == {"passed": True, "missing": []}


class _NoAdapterExecutor:
    def execute(self, *_args, **_kwargs):
        raise AssertionError("invalid workspace path reached the Adapter")


def test_initial_strict_surface_exposes_workspace_open() -> None:
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        _NoAdapterExecutor(),  # type: ignore[arg-type]
    )

    names = {tool["function"]["name"] for tool in agent.tools(_state([]))}

    assert "adapter__workspace_open" in names


def test_execution_boundary_rejects_home_before_adapter_execution() -> None:
    state = _state([])
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1"),
        _NoAdapterExecutor(),  # type: ignore[arg-type]
    )
    visible_tools = build_tools(
        "vs_code",
        ["workspace.open"],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )

    event = agent.execute_proposal(
        state,
        {
            "tool": "adapter__workspace_open",
            "arguments_raw": json.dumps(
                {"path": "~/", "reuse_window": False, "close_existing": True}
            ),
            "_model_visible_tools": visible_tools,
        },
    )

    assert event.executed is False
    assert "explicit instruction hierarchy" in event.error["detail"]
    assert event.proposed["arguments"] == {
        "path": "~/",
        "reuse_window": False,
        "close_existing": True,
    }
