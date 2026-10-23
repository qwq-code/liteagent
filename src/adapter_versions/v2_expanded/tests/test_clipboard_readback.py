from types import SimpleNamespace

import pytest

from os_adapter import worker
from os_adapter.actions import OSActions
from os_adapter.errors import AdapterError


def prepare_reader(monkeypatch, first, second):
    responses = iter([first, second])
    runner = SimpleNamespace(run=lambda *args, **kwargs: {
        "returncode": 0, "stdout": next(responses), "stderr": "",
    })
    actions = OSActions(runner=runner)
    monkeypatch.setattr(worker, "OSActions", lambda: actions)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/xsel" if name == "xsel" else None)


@pytest.mark.parametrize("text,limit", [("", 4), ("中文\n末行\n", 100), ("中文\n末行\n", 3)])
def test_clipboard_get_verifies_complete_and_truncated_reads(monkeypatch, text, limit):
    prepare_reader(monkeypatch, text, text)
    result = worker.execute({"action": "clipboard.get", "params": {"max_chars": limit}})
    assert result["verification"]["passed"]
    assert result["result"]["text"] == text[:limit]
    assert result["result"]["truncated"] is (len(text) > limit)


@pytest.mark.parametrize("changed", ["changed", "prefix extra"])
def test_clipboard_get_rejects_changed_snapshot(monkeypatch, changed):
    prepare_reader(monkeypatch, "prefix", changed)
    with pytest.raises(AdapterError, match="verification failed"):
        worker.execute({"action": "clipboard.get", "params": {"max_chars": 3}})


def test_clipboard_set_still_checks_the_entire_text(monkeypatch):
    monkeypatch.setattr(worker, "OSActions", lambda: SimpleNamespace(
        dispatch=lambda *args: {"text": "prefix"},
        runner=SimpleNamespace(run=lambda *args, **kwargs: {
            "returncode": 0, "stdout": "prefix extra", "stderr": "",
        }),
    ))
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/xsel")
    with pytest.raises(AdapterError, match="verification failed"):
        worker.execute({"action": "clipboard.set", "params": {"text": "prefix"}})
