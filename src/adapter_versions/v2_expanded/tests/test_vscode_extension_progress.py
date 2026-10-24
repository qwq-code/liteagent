from types import SimpleNamespace

import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.stall_policy import detect_no_progress_stall
from integrations.lite_agent.state_model import ExecutionEvent
from vscode_adapter import actions


@pytest.mark.parametrize("installed", [False, True])
def test_install_receipt_distinguishes_mutation_from_noop(monkeypatch, installed):
    calls = []
    observations = iter([
        {"installed": installed, "ids": ["example.debug"] if installed else []},
        {"installed": True, "ids": ["example.debug"]},
    ])
    monkeypatch.setattr(actions, "offline_extension_path", lambda _: None)
    monkeypatch.setattr(actions, "extension_state", lambda *_: next(observations))

    def run(argv, **kwargs):
        calls.append(argv)
        return {"stdout": "installed", "returncode": 0}

    result = actions.VscodeActions(SimpleNamespace(run=run)).extension_install(
        {"source_type": "marketplace", "source": "example.debug"}, 10,
    )
    assert result["changed"] is (not installed)
    assert len(calls) == (0 if installed else 1)
    assert result["already_installed"] is installed
    context = adapter_context_hint("vs_code", "extension.install", {"result": result})
    assert context["changed"] is (not installed)
    assert "Inspect" in context["guidance"]

    # A successful no-op must not reset the stalled-loop detector, including
    # when alternating with clicks on the old installation dialog.
    events = []
    for step in range(1, 17):
        gui = step % 2 == 0
        events.append(ExecutionEvent(
            step=step, timestamp_utc="2026-10-24T00:00:00Z", executed=True,
            proposed={"kind": "gui" if gui else "adapter",
                      "action": "gui_action" if gui else "extension.install",
                      "arguments": {"x": 42, "y": 42} if gui else
                      {"source_type": "marketplace", "source": "example.debug"}},
            result={"environment_acknowledged": True} if gui else {"result": result},
        ))
    if installed:
        assert detect_no_progress_stall(events, window=8) is not None
    else:
        assert detect_no_progress_stall(events, window=8) is None
