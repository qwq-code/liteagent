from __future__ import annotations

import mailbox
from email.message import EmailMessage
from pathlib import Path

import jsonschema
import pytest

import thunderbird_adapter.ui as thunderbird_ui
from integrations.lite_agent.adapter_results import thunderbird_message_query_context
from integrations.lite_agent.instruction_semantics import (
    strict_instruction_required_actions,
)
from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, build_tools
from integrations.openapa_osworld.tool_catalog import public_actions
from thunderbird_adapter.actions import ThunderbirdActions, semantic_preference_update
from thunderbird_adapter.errors import AdapterError as ThunderbirdAdapterError
from thunderbird_adapter.profile import (
    export_mbox_messages,
    query_messages,
    resolve_filter_rules_path,
    save_attachment,
    update_message_flags,
)
from thunderbird_adapter.verifier import verify_check
from thunderbird_adapter.schema import ACTIONS as THUNDERBIRD_ACTIONS
from thunderbird_adapter.schema import parse_action_request
from thunderbird_adapter.schema import validate_action_params as validate_thunderbird
from thunderbird_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as THUNDERBIRD_SCHEMAS,
)
from thunderbird_adapter.worker import execute as execute_thunderbird


DOWNSTREAM_ACTION = "attachments.save"
RETIRED_ACTIONS = {
    "filters.upsert",
    "messages.star_folder",
    "ui.open_about_profiles",
}


def _message(
    subject: str,
    *,
    message_id: str | None = None,
    attachment_name: str | None = None,
    mozilla_status: str | None = None,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "sender@example.test"
    message["To"] = "recipient@example.test"
    message["Subject"] = subject
    message["Date"] = "Tue, 01 Jan 2030 00:00:00 +0000"
    if mozilla_status is not None:
        message["X-Mozilla-Status"] = mozilla_status
    if message_id is not None:
        message["Message-ID"] = f"<{message_id}>"
    message.set_content("synthetic message body")
    if attachment_name is not None:
        message.add_attachment(
            b"synthetic attachment payload",
            maintype="application",
            subtype="octet-stream",
            filename=attachment_name,
        )
    return message


def _profile_with_messages(tmp_path: Path) -> Path:
    profile = tmp_path / "profile"
    mailbox_dir = profile / "Mail" / "Local Folders"
    mailbox_dir.mkdir(parents=True)
    box = mailbox.mbox(mailbox_dir / "Archive")
    try:
        box.add(_message("missing selector", attachment_name="missing.bin"))
        box.add(
            _message(
                "stable selector",
                message_id="stable@example.test",
                attachment_name="stable.bin",
                mozilla_status="0001",
            )
        )
        box.flush()
    finally:
        box.close()
    return profile


def _save_arguments(**overrides: object) -> dict[str, object]:
    arguments: dict[str, object] = {
        "folder_name": "Archive",
        "mailbox_index": 4,
        "attachment_name": "report.bin",
        "output_path": "~/receipts/report.bin",
    }
    arguments.update(overrides)
    return arguments


def _exposed_schema(action: str = DOWNSTREAM_ACTION) -> dict:
    tools = build_tools(
        "thunderbird",
        [action],
        include_gui=False,
        include_control_tools=False,
        strict_generic=True,
    )
    return tools[0]["function"]["parameters"]


def test_query_omits_missing_message_id_and_preserves_real_id(tmp_path: Path) -> None:
    result = query_messages(
        _profile_with_messages(tmp_path),
        "Archive",
        select_from="earliest",
        order="ascending",
    )

    rows = result["messages"]
    assert rows[0]["mailbox_index"] == 0
    assert "message_id" not in rows[0]
    assert rows[1]["mailbox_index"] == 1
    assert rows[1]["message_id"] == "stable@example.test"


def test_save_result_omits_missing_message_id_and_preserves_real_id(
    tmp_path: Path,
) -> None:
    profile = _profile_with_messages(tmp_path)
    missing_output = tmp_path / "missing.bin"
    missing = save_attachment(
        profile,
        "Archive",
        missing_output,
        mailbox_index=0,
        attachment_name="missing.bin",
    )
    assert missing_output.read_bytes() == b"synthetic attachment payload"
    assert "message_id" not in missing
    assert missing["mailbox_index"] == 0

    stable = save_attachment(
        profile,
        "Archive",
        tmp_path / "stable.bin",
        message_id="stable@example.test",
        attachment_name="stable.bin",
    )
    assert stable["message_id"] == "stable@example.test"
    assert stable["mailbox_index"] == 1


@pytest.mark.parametrize("empty_value", ["", "  ", None])
def test_query_projection_omits_empty_message_id_sentinels(empty_value: object) -> None:
    context = thunderbird_message_query_context(
        {
            "folder": "Archive",
            "matched_count": 1,
            "returned_count": 1,
            "select_from": "latest",
            "order": "descending",
            "messages": [
                {
                    "mailbox_index": 7,
                    "message_id": empty_value,
                    "sender_name": "sender",
                    "subject": "subject",
                    "attachment_names": ["report.bin"],
                    "number_of_attachments": 1,
                }
            ],
        }
    )

    row = context["messages"][0]
    assert row["mailbox_index"] == 7
    assert "message_id" not in row
    assert "mailbox_index" in context["selector_guidance"]


def test_query_projection_keeps_nonempty_message_id() -> None:
    context = thunderbird_message_query_context(
        {
            "folder": "Archive",
            "messages": [{"mailbox_index": 2, "message_id": "stable@example.test"}],
        }
    )

    assert context["messages"][0]["message_id"] == "stable@example.test"


def test_folder_flag_update_uses_observed_indices_and_reads_back(tmp_path: Path) -> None:
    profile = _profile_with_messages(tmp_path)
    query = query_messages(profile, "Archive", limit=500)
    assert query["matched_count"] == query["returned_count"] == 2
    rows = {item["mailbox_index"]: item for item in query["messages"]}
    assert rows[0]["starred"] is False
    assert rows[1]["starred"] is False

    updated = update_message_flags(
        profile,
        "Archive",
        mailbox_indices=[0, 1],
        flag="starred",
        value=True,
    )
    assert updated["verification_passed"] is True
    assert updated["changed_count"] == 2
    assert updated["after"] == {0: True, 1: True}
    assert verify_check(
        {
            "type": "message_flags",
            "profile": str(profile),
            "folder_name": "Archive",
            "mailbox_indices": [0, 1],
            "flag": "starred",
            "value": True,
        }
    )["passed"]

    # A different Mozilla status bit survives setting and clearing the star.
    box = mailbox.mbox(profile / "Mail" / "Local Folders" / "Archive", create=False)
    try:
        assert int(box[1]["X-Mozilla-Status"], 16) & 0x0001
    finally:
        box.close()
    cleared = update_message_flags(
        profile,
        "Archive",
        mailbox_indices=[1],
        flag="starred",
        value=False,
    )
    assert cleared["verification_passed"] is True
    box = mailbox.mbox(profile / "Mail" / "Local Folders" / "Archive", create=False)
    try:
        assert int(box[1]["X-Mozilla-Status"], 16) == 0x0001
    finally:
        box.close()


def test_folder_flag_update_contract_is_typed_and_bounded() -> None:
    action = "messages.update_flags"
    arguments = {
        "folder_name": "Bills",
        "mailbox_indices": [0, 1],
        "flag": "starred",
        "value": True,
    }
    exposed = _exposed_schema(action)
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert not list(jsonschema.Draft202012Validator(exposed).iter_errors(arguments))
    validate_thunderbird(action, arguments)
    with pytest.raises(ThunderbirdAdapterError, match="unique"):
        validate_thunderbird(
            action,
            {**arguments, "mailbox_indices": [0, 0]},
        )


def test_mailbox_index_only_contract_is_identical_across_owning_surfaces() -> None:
    manifest = THUNDERBIRD_SCHEMAS[DOWNSTREAM_ACTION]
    direct = DIRECT_ACTION_SCHEMAS["thunderbird"][DOWNSTREAM_ACTION]
    exposed = _exposed_schema()

    assert direct == manifest
    jsonschema.Draft202012Validator.check_schema(exposed)
    assert exposed["properties"] == manifest["properties"]
    assert exposed["anyOf"] == manifest["anyOf"]
    assert "params" not in exposed["properties"]

    arguments = _save_arguments()
    assert not list(jsonschema.Draft202012Validator(exposed).iter_errors(arguments))
    validate_thunderbird(DOWNSTREAM_ACTION, arguments)


def test_real_message_id_is_valid_selector_across_surfaces() -> None:
    arguments = _save_arguments(message_id="stable@example.test")
    arguments.pop("mailbox_index")

    assert not list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )
    validate_thunderbird(DOWNSTREAM_ACTION, arguments)


def test_empty_message_id_is_rejected_even_with_mailbox_index() -> None:
    arguments = _save_arguments(message_id="")
    errors = list(
        jsonschema.Draft202012Validator(_exposed_schema()).iter_errors(arguments)
    )

    assert errors
    with pytest.raises(ThunderbirdAdapterError, match="non-empty"):
        validate_thunderbird(DOWNSTREAM_ACTION, arguments)


def test_task_shaped_mail_actions_are_absent_from_runtime_surfaces() -> None:
    surfaces = (
        set(THUNDERBIRD_ACTIONS),
        set(THUNDERBIRD_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["thunderbird"]),
        set(public_actions("thunderbird")),
    )
    assert all(RETIRED_ACTIONS.isdisjoint(surface) for surface in surfaces)
    assert "filters.configure" in THUNDERBIRD_ACTIONS
    assert "filters.configure" in THUNDERBIRD_SCHEMAS

    for action in RETIRED_ACTIONS:
        with pytest.raises(ThunderbirdAdapterError) as parsed_error:
            parse_action_request({"action": action, "params": {}})
        assert parsed_error.value.code == "UNSUPPORTED_ACTION"

        with pytest.raises(ThunderbirdAdapterError) as worker_error:
            execute_thunderbird({"action": action, "params": {}})
        assert worker_error.value.code == "UNSUPPORTED_ACTION"
        assert not hasattr(ThunderbirdActions, action.replace(".", "_"))

    required = strict_instruction_required_actions(
        "thunderbird",
        "Create a mail filter that forwards every message.",
    )
    assert "filters.configure" in required
    assert RETIRED_ACTIONS.isdisjoint(required)


def _write_account_preferences(profile: Path, servers: list[tuple[str, str]]) -> None:
    accounts = [f"account{index}" for index in range(1, len(servers) + 1)]
    lines = [f'user_pref("mail.accountmanager.accounts", "{",".join(accounts)}");']
    for index, (server_type, hostname) in enumerate(servers, start=1):
        root = "ImapMail" if server_type == "imap" else "Mail"
        lines.extend(
            [
                f'user_pref("mail.account.account{index}.server", "server{index}");',
                f'user_pref("mail.server.server{index}.type", "{server_type}");',
                f'user_pref("mail.server.server{index}.hostname", "{hostname}");',
                f'user_pref("mail.server.server{index}.directory-rel", "[ProfD]{root}/{hostname}");',
            ]
        )
        (profile / root / hostname).mkdir(parents=True)
    profile.mkdir(parents=True, exist_ok=True)
    (profile / "prefs.js").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_filter_configuration_resolves_one_live_incoming_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = tmp_path / "profile"
    _write_account_preferences(
        profile,
        [("imap", "mail.example.test"), ("none", "Local Folders")],
    )
    expected = profile / "ImapMail" / "mail.example.test" / "msgFilterRules.dat"
    assert resolve_filter_rules_path(profile) == expected

    actions = ThunderbirdActions(object())
    monkeypatch.setattr(
        actions,
        "_profile_action",
        lambda operation, _timeout: operation(profile),
    )
    result = actions.filters_configure(
        {
            "filters": [
                {
                    "name": "Synthetic filter",
                    "condition_mode": "all_messages",
                    "conditions": [],
                    "action": "forward",
                    "destination": "archive@example.test",
                }
            ]
        },
        1,
    )

    assert Path(result["path"]) == expected
    assert 'actionValue="archive@example.test"' in expected.read_text(encoding="utf-8")


def test_filter_target_resolution_fails_closed_for_missing_or_ambiguous_accounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing"
    _write_account_preferences(missing, [("none", "Local Folders")])
    with pytest.raises(ThunderbirdAdapterError) as missing_error:
        resolve_filter_rules_path(missing)
    assert missing_error.value.code == "FILTER_TARGET_NOT_FOUND"

    ambiguous = tmp_path / "ambiguous"
    _write_account_preferences(
        ambiguous,
        [("imap", "one.example.test"), ("imap", "two.example.test")],
    )
    with pytest.raises(ThunderbirdAdapterError) as ambiguous_error:
        resolve_filter_rules_path(ambiguous)
    assert ambiguous_error.value.code == "AMBIGUOUS_FILTER_TARGET"

    actions = ThunderbirdActions(object())
    monkeypatch.setattr(
        actions,
        "_profile_action",
        lambda operation, _timeout: operation(ambiguous),
    )
    with pytest.raises(ThunderbirdAdapterError) as configure_error:
        actions.filters_configure(
            {
                "filters": [
                    {
                        "name": "Synthetic filter",
                    "condition_mode": "all_messages",
                        "conditions": [],
                        "action": "move_to_local_folder",
                        "destination": "MustNotBeCreated",
                    }
                ]
            },
            1,
        )
    assert configure_error.value.code == "AMBIGUOUS_FILTER_TARGET"
    assert not (ambiguous / "Mail" / "Local Folders" / "MustNotBeCreated").exists()


def test_export_eml_rejects_existing_entries_without_deleting_or_overwriting(
    tmp_path: Path,
) -> None:
    source = _profile_with_messages(tmp_path) / "Mail" / "Local Folders" / "Archive"
    destination = tmp_path / "eml"
    destination.mkdir()
    existing = destination / "keep.eml"
    existing.write_bytes(b"preserve me")

    with pytest.raises(ThunderbirdAdapterError) as conflict:
        export_mbox_messages(source, destination)
    assert conflict.value.code == "PATH_EXISTS"
    assert existing.read_bytes() == b"preserve me"
    assert list(destination.iterdir()) == [existing]

    fresh = tmp_path / "fresh-eml"
    first = export_mbox_messages(source, fresh)
    exported = {
        Path(item["path"]): Path(item["path"]).read_bytes()
        for item in first["messages"]
    }
    with pytest.raises(ThunderbirdAdapterError) as repeat_conflict:
        export_mbox_messages(source, fresh)
    assert repeat_conflict.value.code == "PATH_EXISTS"
    assert {path: path.read_bytes() for path in exported} == exported


@pytest.mark.parametrize(
    ("setting", "value"),
    [("signature_text", "Regards"), ("quote_original_on_reply", True)],
)
def test_identity_specific_mail_settings_require_explicit_identity(
    setting: str, value: object
) -> None:
    params = {setting: value}
    manifest = THUNDERBIRD_SCHEMAS["mail.configure"]
    exposed = _exposed_schema("mail.configure")

    assert DIRECT_ACTION_SCHEMAS["thunderbird"]["mail.configure"] == manifest
    assert exposed["allOf"] == manifest["allOf"]
    assert list(jsonschema.Draft202012Validator(exposed).iter_errors(params))
    with pytest.raises(ThunderbirdAdapterError) as validation_error:
        validate_thunderbird("mail.configure", params)
    assert validation_error.value.code == "INVALID_REQUEST"
    with pytest.raises(ThunderbirdAdapterError) as action_error:
        semantic_preference_update(params)
    assert action_error.value.code == "INVALID_REQUEST"

    explicit = {**params, "identity": "id7"}
    assert not list(jsonschema.Draft202012Validator(exposed).iter_errors(explicit))
    validate_thunderbird("mail.configure", explicit)
    update = semantic_preference_update(explicit)
    assert update["values"]
    assert all(key.startswith("mail.identity.id7.") for key in update["values"])


class _FakeAccessibleNode:
    def __init__(
        self,
        name: str,
        role: str,
        children: tuple["_FakeAccessibleNode", ...] = (),
    ) -> None:
        self.name = name
        self._role = role
        self._children = children
        self.childCount = len(children)

    def getRoleName(self) -> str:
        return self._role

    def getChildAtIndex(self, index: int) -> "_FakeAccessibleNode":
        return self._children[index]


def _compose_tree(*subjects: str) -> _FakeAccessibleNode:
    frames = tuple(
        _FakeAccessibleNode(f"Write: {subject} - Thunderbird", "frame")
        for subject in subjects
    )
    return _FakeAccessibleNode("Thunderbird", "application", frames)


def test_compose_frame_requires_one_unambiguous_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        thunderbird_ui, "thunderbird_app", lambda: _compose_tree("First", "Second")
    )
    with pytest.raises(ThunderbirdAdapterError) as unspecified_error:
        thunderbird_ui.compose_frame(None, 0.1)
    assert unspecified_error.value.code == "AMBIGUOUS_COMPOSE_WINDOW"

    selected = thunderbird_ui.compose_frame("Second", 0.1)
    assert selected.name == "Write: Second - Thunderbird"

    monkeypatch.setattr(
        thunderbird_ui,
        "thunderbird_app",
        lambda: _compose_tree("Duplicate", "Duplicate"),
    )
    with pytest.raises(ThunderbirdAdapterError) as duplicate_error:
        thunderbird_ui.compose_frame("Duplicate", 0.1)
    assert duplicate_error.value.code == "AMBIGUOUS_COMPOSE_WINDOW"
