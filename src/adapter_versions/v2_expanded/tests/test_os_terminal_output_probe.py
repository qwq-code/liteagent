from __future__ import annotations

import io
from copy import deepcopy
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from integrations.lite_agent.agent_protocol import AgentProtocolMixin
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState
from os_adapter import verifier, visible_terminal, worker
from os_adapter.errors import AdapterError, error_payload


def test_terminal_output_allows_a_slow_accessibility_probe(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_urlopen(url: str, *, timeout: float):
        observed.update(url=url, timeout=timeout)
        if timeout < 6.2:
            raise TimeoutError("simulated slow OSWorld accessibility endpoint")
        return io.BytesIO(b'{"output": "command complete", "status": "success"}')

    monkeypatch.setattr(verifier.urllib.request, "urlopen", fake_urlopen)

    assert verifier.terminal_output() == "command complete"
    assert observed == {
        "url": "http://127.0.0.1:5000/terminal",
        "timeout": verifier.TERMINAL_OUTPUT_TIMEOUT_SECONDS,
    }


@pytest.fixture
def visible_command(monkeypatch, tmp_path):
    clock = SimpleNamespace(now=0.0)
    case = SimpleNamespace(
        launch_seconds=3.0,
        probe_seconds=15.0,
        returncode=0,
        observation=None,
        output="synthetic command output\n",
        probe_timeouts=[],
        calls=[],
        title="",
        existing_window=f"0x456 host {visible_terminal.TERMINAL_TITLE} Command existing",
        overview_open=False,
        overview_dismissal_succeeds=True,
        activation_states=[],
        execute_native=False,
    )

    def advance(seconds):
        clock.now += seconds

    def run(argv, **kwargs):
        case.calls.append(list(argv))
        if argv[0] == "gnome-terminal":
            case.title = argv[1].removeprefix("--title=")
            wrapper = argv.index("osworld-terminal-output")
            if case.execute_native:
                completed = subprocess.run(
                    argv[wrapper + 4 :],
                    cwd=tmp_path,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=5,
                    check=False,
                )
                case.output = completed.stdout
                case.returncode = completed.returncode
                case.observation = (
                    case.output + f"\n[command exited with status {case.returncode}]"
                )
            Path(argv[wrapper + 2]).write_text(case.output)
            Path(argv[wrapper + 3]).write_text(str(case.returncode))
            advance(case.launch_seconds)
        elif argv[0] == "gdbus":
            if case.overview_dismissal_succeeds:
                case.overview_open = False
            else:
                raise AdapterError("OPERATION_FAILED", "native focus is unavailable")
        elif argv[0] == "wmctrl":
            case.activation_states.append(not case.overview_open)
        return {"duration_ms": 0}

    def probe(*, timeout=verifier.TERMINAL_OUTPUT_TIMEOUT_SECONDS):
        case.probe_timeouts.append(timeout)
        advance(min(case.probe_seconds, timeout))
        return None if case.overview_open else case.observation

    monkeypatch.setattr(
        visible_terminal,
        "time",
        SimpleNamespace(monotonic=lambda: clock.now, monotonic_ns=lambda: 1, sleep=advance),
    )
    monkeypatch.setattr(visible_terminal, "terminal_output", probe)
    monkeypatch.setattr(visible_terminal.tempfile, "tempdir", str(tmp_path))
    def unexpected_shutdown():
        pytest.fail("showing output must not close an existing producer terminal")

    lifecycle = SimpleNamespace(
        shutdown=unexpected_shutdown,
        windows=lambda: [case.existing_window, f"0x123 host {case.title}"],
    )
    params = {"argv": ["printf", "synthetic"], "cwd_source": "home", "provenance": "none"}
    case.execute = lambda: visible_terminal.run_visible_terminal_command(
        SimpleNamespace(run=run), lifecycle, params, cwd=tmp_path, timeout=8.0
    )
    case.clock = clock
    case.params = params
    return case


def test_visible_terminal_readback_uses_remaining_command_deadline(visible_command):
    with pytest.raises(AdapterError) as raised:
        visible_command.execute()

    assert raised.value.code == "TERMINAL_UNAVAILABLE"
    assert visible_command.probe_timeouts == [5.0]
    assert visible_command.clock.now <= 8.0


@pytest.mark.parametrize("returncode", [0, 2])
def test_visible_terminal_missing_marker_preserves_completed_output(
    visible_command, returncode
):
    visible_command.returncode = returncode
    with pytest.raises(AdapterError) as raised:
        visible_command.execute()

    assert raised.value.code == "TERMINAL_UNAVAILABLE"
    details = raised.value.details
    assert details["returncode"] == returncode
    assert details["command_completed"] is True
    assert details["combined_output"] == visible_command.output
    assert details["output_truncated"] is False
    assert details["terminal_output"] is None


def test_visible_terminal_observed_marker_still_succeeds(visible_command):
    visible_command.observation = "synthetic command output\n[command exited with status 0]"
    visible_command.probe_seconds = 1.0
    result = visible_command.execute()

    assert result["verified"] is True
    assert result["argv"] == visible_command.params["argv"]
    assert result["combined_output"] == visible_command.output
    assert result["terminal"]["command_completed"] is True
    assert result["terminal"]["output_visible"] is True
    assert result["terminal"]["windows"] == [f"0x123 host {visible_command.title}"]
    assert sum(call[0] == "gnome-terminal" for call in visible_command.calls) == 1
    assert [call for call in visible_command.calls if call[0] == "wmctrl"] == [
        ["wmctrl", "-a", visible_command.title],
    ]


@pytest.mark.parametrize("argument", ["*.txt", "> notes.txt"])
def test_visible_terminal_native_literal_failure_explains_recovery(
    visible_command, argument
):
    visible_command.execute_native = True
    visible_command.probe_seconds = 1.0
    visible_command.params["argv"] = ["ls", "--", argument]
    original = deepcopy(visible_command.params)

    with pytest.raises(AdapterError) as raised:
        visible_command.execute()

    error = raised.value
    assert error.code == "COMMAND_FAILED"
    assert error.details["returncode"] == 2
    assert argument in error.details["combined_output"]
    assert "No such file or directory" in error.details["combined_output"]
    assert error.details["stdout"] == visible_command.output
    assert error.details["combined_output"] == visible_command.output
    assert error.details["stderr"] == ""
    assert error.details["argv"] == original["argv"]
    assert visible_command.params == original
    guidance = error.details["guidance"]
    assert "Native command output" in guidance
    assert "literally" in guidance
    assert '["bash", "-c", <one model-authored script>]' in guidance
    assert "stdout_path" not in guidance
    if argument.startswith(">"):
        assert "terminal.show_output already displays command output" in guidance
    else:
        assert "find -name" in guidance


def test_visible_terminal_native_program_pattern_stays_literal_and_succeeds(
    visible_command, tmp_path
):
    (tmp_path / "native note.txt").touch()
    visible_command.execute_native = True
    visible_command.probe_seconds = 1.0
    visible_command.params["argv"] = ["find", ".", "-name", "*.txt"]
    original = deepcopy(visible_command.params)

    result = visible_command.execute()

    assert result["returncode"] == 0
    assert result["stdout"] == "./native note.txt\n"
    assert result["combined_output"] == visible_command.output
    assert result["argv"] == original["argv"]
    assert "guidance" not in result
    assert visible_command.params == original


def test_visible_terminal_dismisses_overview_before_activating_window(visible_command):
    visible_command.overview_open = True
    visible_command.observation = "synthetic command output\n[command exited with status 0]"
    visible_command.probe_seconds = 1.0

    result = visible_command.execute()

    assert result["verified"] is True
    assert result["argv"] == visible_command.params["argv"]
    assert visible_command.activation_states == [True]
    dismissals = [call for call in visible_command.calls if call[0] == "gdbus"]
    assert len(dismissals) == 1
    assert dismissals[0][-4:] == [
        "org.freedesktop.DBus.Properties.Set",
        "org.gnome.Shell",
        "OverviewActive",
        "<false>",
    ]
    assert visible_command.clock.now <= 8.0


def test_worker_reuses_completed_visible_command_observation(
    visible_command, monkeypatch
):
    visible_command.observation = "synthetic command output\n[command exited with status 0]"
    visible_command.probe_seconds = 1.0
    result = visible_command.execute()
    original = deepcopy(result)
    params = deepcopy(visible_command.params)

    def dispatch(action, received_params, _timeout):
        assert action == "terminal.show_output"
        assert received_params == params
        return result

    monkeypatch.setattr(
        worker, "OSActions", lambda: SimpleNamespace(dispatch=dispatch, runner=object())
    )
    second_probes = []

    def unavailable_second_probe():
        second_probes.append(True)
        return None

    monkeypatch.setattr(verifier, "terminal_output", unavailable_second_probe)
    response = worker.execute({"action": "terminal.show_output", "params": params})

    assert response["verification"]["passed"] is True
    assert response["verification"]["checks"][1]["observed"] == result["terminal_output"]
    assert response["result"] == original
    assert visible_command.params == params
    assert second_probes == []


def test_visible_command_without_window_receipt_needs_live_observation(
    visible_command, monkeypatch
):
    visible_command.observation = "synthetic command output\n[command exited with status 0]"
    visible_command.probe_seconds = 1.0
    result = visible_command.execute()
    result["terminal"]["windows"] = []
    monkeypatch.setattr(verifier, "terminal_output", lambda: None)

    checked = verifier.verify_specs(
        worker._default_specs("terminal.show_output", visible_command.params, result),
        result,
    )

    assert checked["passed"] is False
    assert checked["checks"][0]["passed"] is True
    assert checked["checks"][1]["observed"] is None


def test_unrelated_terminal_check_reads_live_output(visible_command, monkeypatch):
    visible_command.observation = "synthetic command output\n[command exited with status 0]"
    visible_command.probe_seconds = 1.0
    result = visible_command.execute()
    probes = []

    def live_probe():
        probes.append(True)
        return "A different live terminal message"

    monkeypatch.setattr(verifier, "terminal_output", live_probe)
    checked = verifier.verify_specs(
        [{"type": "terminal", "contains": "different live terminal"}], result
    )

    assert checked["passed"] is True
    assert checked["checks"][0]["observed"] == "A different live terminal message"
    assert probes == [True]


def test_failed_overview_dismissal_does_not_claim_visible_success(visible_command):
    visible_command.overview_open = True
    visible_command.overview_dismissal_succeeds = False
    visible_command.observation = "synthetic command output\n[command exited with status 0]"

    with pytest.raises(AdapterError) as raised:
        visible_command.execute()

    assert raised.value.code == "TERMINAL_UNAVAILABLE"
    assert raised.value.details["combined_output"] == visible_command.output
    assert raised.value.details["returncode"] == 0
    assert raised.value.details["terminal_output"] is None
    assert visible_command.clock.now <= 8.0


@pytest.mark.parametrize("domain", ["os", "multi_apps"])
@pytest.mark.parametrize("recovery", [False, True])
def test_visible_terminal_failure_output_reaches_model_recovery(
    visible_command, domain, recovery
):
    with pytest.raises(AdapterError) as raised:
        visible_command.execute()
    error = {"status": "error", "error": error_payload(raised.value)}
    action = "terminal.show_output"
    arguments = visible_command.params
    if domain == "multi_apps":
        arguments = {"adapter": "os", "action": action, "params": arguments}
        action = "adapter.call"
        error = {"error_code": "DOWNSTREAM_FAILED", "details": {"response": error}}
    state = RuntimeState(
        task_id="synthetic-terminal-readback",
        domain=domain,
        instruction="Show the command output in a terminal.",
        events=[
            ExecutionEvent(
                step=1,
                timestamp_utc="2026-09-06T00:00:00Z",
                proposed={"kind": "adapter", "action": action, "arguments": arguments},
                executed=False,
                error=error,
            )
        ],
    )
    messages = AgentProtocolMixin()._messages(state, b"png", execution_recovery=recovery)
    state_text = messages[2]["content"][0]["text"]
    system_text = messages[0]["content"]

    assert "TERMINAL_UNAVAILABLE" in state_text
    assert '"returncode": 0' in state_text
    assert '"command_completed": true' in state_text
    assert visible_command.output.strip() in state_text
    assert state.task_id not in state_text
    assert "means no state changed" not in system_text
    assert "call was not executed" not in system_text
    assert "only executed=true changed the VM" not in state_text
    assert "inspect the error and any partial results" in system_text
