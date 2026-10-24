from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import Any, Callable

from .command import CommandRunner
from .errors import AdapterError
from .filter_contract import compile_filter_configuration
from .schema import validate_action_params
from .profile import (
    ensure_local_folders,
    export_contacts_csv,
    export_folder_messages,
    export_mbox_messages,
    find_profile,
    query_messages,
    read_preferences,
    remove_account,
    resolve_filter_rules_path,
    save_attachment,
    update_message_flags,
    update_json_path,
    update_preferences,
    write_filters,
)
from .ui import (
    compose_attachment,
    compose_set_recipients,
    prefill_account_setup,
)


def normalize_plain_text_line_breaks(value: str) -> str:
    """Accept common model-produced escaped line breaks as plain-text newlines."""
    return value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")


def semantic_preference_update(params: dict[str, Any]) -> dict[str, Any]:
    identity_settings = {"signature_text", "quote_original_on_reply"}.intersection(
        params
    )
    identity = params.get("identity")
    if identity_settings and (not isinstance(identity, str) or not identity.strip()):
        raise AdapterError(
            "INVALID_REQUEST",
            "params.identity is required for identity-specific mail settings",
            {"settings": sorted(identity_settings)},
        )
    if isinstance(identity, str):
        identity = identity.strip()
    values: dict[str, Any] = {}
    remove_keys: list[str] = []
    if "signature_text" in params:
        values[f"mail.identity.{identity}.htmlSigText"] = (
            normalize_plain_text_line_breaks(params["signature_text"])
        )
        values[f"mail.identity.{identity}.htmlSig"] = False
    if "quote_original_on_reply" in params:
        values[f"mail.identity.{identity}.auto_quote"] = params[
            "quote_original_on_reply"
        ]
    if "automatic_filters_on_subfolders" in params:
        enabled = params["automatic_filters_on_subfolders"]
        values["mail.server.default.applyIncomingFilters"] = enabled
        if enabled:
            values["mail.imap.use_status_for_biff"] = False
            remove_keys.append("mail.server.default.autosync_offline_stores")
    if "dark_mode" in params:
        values["extensions.activeThemeID"] = (
            "firefox-compact-dark@mozilla.org"
            if params["dark_mode"]
            else "default-theme@mozilla.org"
        )
    return {"values": values, "remove_keys": remove_keys}


def semantic_xulstore_update(params: dict[str, Any]) -> dict[str, Any] | None:
    if "unified_inbox" not in params:
        return None
    return {
        "keys": [
            "chrome://messenger/content/messenger.xhtml",
            "folderTree",
            "mode",
        ],
        "value": "smart" if params["unified_inbox"] else "all",
    }


class ThunderbirdActions:
    def __init__(self, runner: CommandRunner | None = None) -> None:
        self.runner = runner or CommandRunner()

    def stop_thunderbird(self, timeout: float = 15) -> dict[str, Any]:
        before = self.runner.run(
            ["pgrep", "-x", "thunderbird"], check=False, timeout=5
        )["stdout"].split()
        self.runner.run(["pkill", "-TERM", "-x", "thunderbird"], check=False, timeout=5)
        deadline = time.monotonic() + min(timeout, 15)
        while time.monotonic() < deadline:
            running = self.runner.run(
                ["pgrep", "-x", "thunderbird"], check=False, timeout=5
            )["stdout"]
            if not running.strip():
                return {"stopped": True, "process_ids": before}
            time.sleep(0.2)
        self.runner.run(["pkill", "-KILL", "-x", "thunderbird"], check=False, timeout=5)
        time.sleep(0.5)
        return {"stopped": True, "process_ids": before, "forced": True}

    def start_thunderbird(self, timeout: float = 30) -> dict[str, Any]:
        command = shlex.join(["/usr/bin/thunderbird"])
        self.runner.run(
            [
                "bash",
                "-lc",
                f"nohup {command} >/tmp/osworld-thunderbird-adapter.log 2>&1 </dev/null &",
            ],
            timeout=5,
        )
        deadline = time.monotonic() + min(timeout, 45)
        observed = ""
        while time.monotonic() < deadline:
            observed = self.runner.run(["wmctrl", "-lx"], check=False, timeout=5)[
                "stdout"
            ]
            if "thunderbird" in observed.lower():
                return {
                    "started": True,
                    "windows": [
                        line
                        for line in observed.splitlines()
                        if "thunderbird" in line.lower()
                    ],
                }
            time.sleep(0.25)
        raise AdapterError(
            "APPLICATION_NOT_READY",
            "Thunderbird did not create a window",
            {"wmctrl": observed},
            503,
        )

    def activate(self) -> None:
        self.runner.run(["wmctrl", "-xa", "Mail.thunderbird"], check=False, timeout=5)
        time.sleep(0.3)

    def _profile_action(
        self, operation: Callable[[Path], dict[str, Any]], timeout: float
    ) -> dict[str, Any]:
        stopped = self.stop_thunderbird(min(timeout, 15))
        profile = find_profile()
        result = operation(profile)
        started = self.start_thunderbird(max(5, timeout - 15))
        return {
            **result,
            "profile": str(profile),
            "lifecycle": {"stop": stopped, "start": started},
        }

    def mail_identities_list(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        prefs = read_preferences(find_profile() / "prefs.js")
        accounts = str(prefs.get("mail.accountmanager.accounts", "")).split(",")
        identities = []
        for account in accounts:
            account = account.strip()
            if not account:
                continue
            for identity in str(prefs.get(f"mail.account.{account}.identities", "")).split(","):
                identity = identity.strip()
                if not identity:
                    continue
                prefix = f"mail.identity.{identity}."
                identities.append({
                    "account": account, "identity": identity,
                    "name": prefs.get(prefix + "fullName", ""),
                    "email": prefs.get(prefix + "useremail", ""),
                })
        return {"identities": identities, "count": len(identities)}

    def preferences_update(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        return self._profile_action(
            lambda profile: update_preferences(
                profile / "prefs.js",
                dict(params.get("values", {})),
                params.get("remove_keys", []),
            ),
            timeout,
        )

    def mail_configure(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        preference_update = semantic_preference_update(params)
        xulstore_update = semantic_xulstore_update(params)
        stopped = self.stop_thunderbird(min(timeout, 15))
        profile = find_profile()
        preference_result = None
        if preference_update["values"] or preference_update["remove_keys"]:
            preference_result = update_preferences(
                profile / "prefs.js",
                preference_update["values"],
                preference_update["remove_keys"],
            )
        xulstore_result = None
        if xulstore_update is not None:
            xulstore_result = update_json_path(
                profile / "xulstore.json",
                xulstore_update["keys"],
                xulstore_update["value"],
            )
        started = self.start_thunderbird(max(5, timeout - 15))
        configured = {
            key: value
            for key, value in params.items()
            if key
            in {
                "identity",
                "signature_text",
                "quote_original_on_reply",
                "automatic_filters_on_subfolders",
                "unified_inbox",
                "dark_mode",
            }
        }
        if "signature_text" in configured:
            configured["signature_text"] = normalize_plain_text_line_breaks(
                configured["signature_text"]
            )
        return {
            "profile": str(profile),
            "preferences": preference_result,
            "xulstore": xulstore_result,
            "lifecycle": {"stop": stopped, "start": started},
            "configured": configured,
        }

    def xulstore_update(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._profile_action(
            lambda profile: update_json_path(
                profile / "xulstore.json", list(params["keys"]), params["value"]
            ),
            timeout,
        )

    def folders_ensure_local(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        return self._profile_action(
            lambda profile: ensure_local_folders(profile, params["names"]), timeout
        )

    def filters_configure(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        configuration = compile_filter_configuration(params)

        def operation(profile: Path) -> dict[str, Any]:
            path = resolve_filter_rules_path(profile)
            root = profile / "Mail" / "Local Folders"
            missing = [name for name in configuration["local_folders"] if not (root / name).is_file()]
            if missing:
                raise AdapterError(
                    "PATH_NOT_FOUND", "Create the destination with folders.ensure_local before configuring a filter",
                    {"missing_folders": missing}, 404,
                )
            result = write_filters(path, configuration["filters"])
            return {**result, "local_folders": configuration["local_folders"]}

        return self._profile_action(operation, timeout)

    def messages_export_eml(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        if "folder_name" in params:
            return self._profile_action(
                lambda profile: export_folder_messages(
                    profile,
                    params["folder_name"],
                    Path(params["output_dir"]).expanduser(),
                ),
                timeout,
            )
        return self._profile_action(
            lambda profile: export_mbox_messages(
                profile / params["source"], Path(params["destination"]).expanduser()
            ),
            timeout,
        )

    def contacts_export_csv(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        return self._profile_action(
            lambda profile: export_contacts_csv(
                profile,
                params["address_book"],
                Path(params["output_path"]),
            ),
            timeout,
        )

    def messages_query(self, params: dict[str, Any], _timeout: float) -> dict[str, Any]:
        profile = find_profile()
        return {
            **query_messages(
                profile,
                params["folder_name"],
                limit=params.get("limit", 50),
                select_from=params.get("select_from", "latest"),
                order=params.get("order", "descending"),
                sender_contains=params.get("sender_contains"),
                subject_contains=params.get("subject_contains"),
                after=params.get("after"),
                before=params.get("before"),
                has_attachments=params.get("has_attachments"),
            ),
            "profile": str(profile),
        }

    def attachments_save(
        self, params: dict[str, Any], _timeout: float
    ) -> dict[str, Any]:
        profile = find_profile()
        return {
            **save_attachment(
                profile,
                params["folder_name"],
                Path(params["output_path"]),
                message_id=params.get("message_id"),
                mailbox_index=params.get("mailbox_index"),
                attachment_name=params.get("attachment_name"),
                attachment_index=params.get("attachment_index"),
                overwrite=params.get("overwrite", False),
            ),
            "profile": str(profile),
        }

    def messages_update_flags(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        return self._profile_action(
            lambda profile: update_message_flags(
                profile,
                params["folder_name"],
                mailbox_indices=params["mailbox_indices"],
                flag=params["flag"],
                value=params["value"],
            ),
            timeout,
        )

    def accounts_remove(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        return self._profile_action(
            lambda profile: remove_account(
                profile, params["email"], params.get("hostname")
            ),
            timeout,
        )

    def compose_attach(self, params: dict[str, Any], timeout: float) -> dict[str, Any]:
        self.runner.run(
            ["wmctrl", "-a", f"Write: {params['subject']} - Thunderbird"],
            check=False,
            timeout=5,
        )
        return compose_attachment(params["subject"], params["attachment_path"], timeout)

    def compose_set_recipients(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        return compose_set_recipients(
            params["recipients"],
            params.get("mode", "append"),
            params.get("subject"),
            timeout,
        )

    def ui_prefill_account_setup(
        self, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        self.activate()
        return prefill_account_setup(
            params["full_name"], params["email"], params["password"], timeout
        )

    def dispatch(
        self, action: str, params: dict[str, Any], timeout: float
    ) -> dict[str, Any]:
        validate_action_params(action, params)
        method = getattr(self, action.replace(".", "_"), None)
        if method is None:
            raise AdapterError(
                "UNSUPPORTED_ACTION",
                "unsupported Thunderbird action",
                {"action": action},
            )
        return method(params, timeout)
