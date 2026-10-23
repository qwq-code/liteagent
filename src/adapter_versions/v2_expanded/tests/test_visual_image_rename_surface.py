from types import SimpleNamespace

from integrations.lite_agent.agent import LiteAgent, LiteAgentConfig
from integrations.lite_agent.state_model import ExecutionEvent, RuntimeState


def _adapter_event(step: int, action: str, params: dict, result: dict) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="x",
        proposed={
            "kind": "adapter",
            "action": "adapter.call",
            "arguments": {"adapter": "os", "action": action, "payload": {"params": params}},
        },
        validated=True,
        executed=True,
        result=result,
    )


def _catalog_event(step: int) -> ExecutionEvent:
    return ExecutionEvent(
        step=step,
        timestamp_utc="x",
        proposed={"kind": "catalog", "tool": "tools_search", "arguments": {"query": "os.image.extract_text_batch"}},
        executed=True,
        result={
            "status": "ok",
            "matches": [
                {"action": "adapter.call", "adapter": "os", "downstream_action": action}
                for action in ("filesystem.find", "desktop.open_path", "filesystem.rename")
            ],
        },
    )


def _route_and_source(agent: LiteAgent, state: RuntimeState) -> tuple[str, list[str]]:
    tool = next(tool for tool in agent.tools(state) if tool["function"]["name"] == "adapter__adapter_call")
    parameters = tool["function"]["parameters"]
    action = parameters["properties"]["action"]["const"]
    params = parameters["properties"]["payload"]["properties"]["params"]
    field = "path" if action == "desktop.open_path" else "source"
    return action, params["properties"][field]["enum"]


def test_visual_rename_opens_each_observed_image_before_renaming() -> None:
    agent = LiteAgent(
        LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
        SimpleNamespace(execute=lambda *_args, **_kwargs: None),
    )
    first = "/home/u/Pictures/first.jpg"
    second = "/home/u/Pictures/second.jpg"
    state = RuntimeState(
        task_id="synthetic-visual-rename",
        domain="multi_apps",
        instruction="Identify the landmarks in these pictures and rename each picture.",
        events=[
            _adapter_event(1, "filesystem.find", {}, {
                "adapter_response": {"result": {"matches": [
                    {"path": first, "kind": "file"},
                    {"path": second, "kind": "file"},
                ]}}
            }),
            _catalog_event(2),
        ],
    )
    try:
        assert _route_and_source(agent, state) == ("desktop.open_path", [first])
        state.events.extend([
            _adapter_event(3, "desktop.open_path", {"path": "/home/u/Pictures"}, {}),
            _catalog_event(4),
        ])
        assert _route_and_source(agent, state) == ("desktop.open_path", [first])
        state.events.extend([
            _adapter_event(5, "desktop.open_path", {"path": first}, {}),
            _catalog_event(6),
        ])
        assert _route_and_source(agent, state) == ("filesystem.rename", [first])
        state.events.extend([
            _adapter_event(7, "filesystem.rename", {"source": first, "destination": "new name.jpg"}, {}),
            _catalog_event(8),
        ])
        assert _route_and_source(agent, state) == ("desktop.open_path", [second])
    finally:
        agent.client.close()


def _identity_state(*, destination="/pictures/named.jpg", extra=None, error=None):
    source = "/pictures/original.jpg"
    renamed = _adapter_event(3, "filesystem.rename", {"source": source, "destination": destination}, {})
    renamed.error = error
    state = RuntimeState(
        task_id="synthetic-identity", domain="multi_apps",
        instruction="Identify the objects in these pictures and rename each picture.",
        events=[
            _adapter_event(1, "filesystem.find", {}, {"matches": [
                {"path": source, "kind": "file", "size_bytes": 10, "modified_at": "a"}]}),
            _adapter_event(2, "desktop.open_path", {"path": source}, {}),
            renamed,
            _adapter_event(4, "filesystem.find", {}, {"matches": extra or [
                {"path": "/pictures/named.jpg", "kind": "file", "size_bytes": 10, "modified_at": "a"}]}),
            _catalog_event(5),
        ])
    return state


def _identity_agent():
    return LiteAgent(LiteAgentConfig(base_url="http://unused/v1", include_gui=False),
                     SimpleNamespace(), model_client=SimpleNamespace(client=object()))


def test_rediscovery_does_not_restart_renamed_image():
    agent = _identity_agent()
    names = [t["function"]["name"] for t in agent.tools(_identity_state())]
    assert "adapter__adapter_call" not in names
    assert "tools_search" in names
    assert "propose_done" in names


def test_basename_destination_keeps_file_identity():
    names = [t["function"]["name"] for t in _identity_agent().tools(_identity_state(destination="named.jpg"))]
    assert "adapter__adapter_call" not in names


def test_recreated_source_is_a_new_pending_image():
    state = _identity_state(extra=[
        {"path": "/pictures/original.jpg", "kind": "file", "size_bytes": 20},
        {"path": "/pictures/named.jpg", "kind": "file", "size_bytes": 10}])
    assert _route_and_source(_identity_agent(), state) == ("desktop.open_path", ["/pictures/original.jpg"])


def test_changed_destination_requires_fresh_visual_inspection():
    state = _identity_state(extra=[
        {"path": "/pictures/named.jpg", "kind": "file", "size_bytes": 20}])
    assert _route_and_source(_identity_agent(), state) == ("desktop.open_path", ["/pictures/named.jpg"])


def test_failed_rename_does_not_consume_source():
    state = _identity_state(error={"code": "DESTINATION_EXISTS"})
    assert _route_and_source(_identity_agent(), state) == ("filesystem.rename", ["/pictures/original.jpg"])


def test_verified_result_resolves_basename_source_and_destination():
    state = _identity_state()
    event = state.events[2]
    event.proposed["arguments"]["payload"]["params"] = {"source": "original.jpg", "destination": "named.jpg"}
    event.result = {"context_hint": {"verification_passed": True, "downstream_context": {
        "source": "/pictures/original.jpg", "destination": "/pictures/named.jpg", "moved": True}}}
    assert "adapter__adapter_call" not in [t["function"]["name"] for t in _identity_agent().tools(state)]


def test_failed_verification_does_not_complete_rename():
    state = _identity_state()
    state.events[2].result = {"context_hint": {"verification_passed": False}}
    assert _route_and_source(_identity_agent(), state) == ("filesystem.rename", ["/pictures/original.jpg"])


def test_rename_chain_and_collision_keep_only_current_identity():
    from integrations.lite_agent.visual_file_identity import pending_visual_image
    state = _identity_state()
    state.events.extend([
        _adapter_event(6, "filesystem.find", {}, {"matches": [
            {"path": "/pictures/other.jpg", "kind": "file", "size_bytes": 99}]}),
        _adapter_event(7, "filesystem.rename", {"source": "/pictures/named.jpg",
            "destination": "/pictures/other.jpg", "replace": True}, {}),
        _adapter_event(8, "filesystem.find", {}, {"matches": [
            {"path": "/pictures/other.jpg", "kind": "file", "size_bytes": 10}]}),
    ])
    assert pending_visual_image(state) == (None, False)
    state.events.append(_adapter_event(9, "filesystem.find", {}, {"matches": [
        {"path": "/pictures/other.jpg", "kind": "file", "size_bytes": 100}]}))
    assert pending_visual_image(state) == ("/pictures/other.jpg", False)


def test_new_image_remains_pending_after_previous_rename():
    state = _identity_state(extra=[
        {"path": "/pictures/named.jpg", "kind": "file", "size_bytes": 10},
        {"path": "/pictures/new.jpg", "kind": "file", "size_bytes": 20}])
    assert _route_and_source(_identity_agent(), state) == ("desktop.open_path", ["/pictures/new.jpg"])
