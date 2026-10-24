from __future__ import annotations

from typing import Any


NONEMPTY_STRING = {"type": "string", "minLength": 1}

# Model-visible parameter contracts owned by the Adapter. Runtime validation
# remains in thunderbird_adapter.schema and is checked against this manifest.
STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "mail.identities.list": {
        "description": (
            "Read configured mail identities and their account, name and email. "
            "Use the returned identity key with mail.configure for signatures or "
            "reply settings; choose the identity matching the user's account. "
            "Does not modify settings or expose credentials."
        ),
        "properties": {},
        "required": [],
    },
    "filters.configure": {
        "properties": {
            "filters": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1,
                "description": (
                    "Set exactly one named filter, preserving every other rule. "
                    "A move_to_local_folder destination must already exist; "
                    "create it first with folders.ensure_local."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            **NONEMPTY_STRING,
                            "maxLength": 255,
                            "description": "Explicit unique rule name; only the rule with this exact name is replaced.",
                        },
                        "enabled": {
                            "type": "boolean",
                            "default": True,
                            "description": "Whether the filter is active; defaults to true.",
                        },
                        "match": {
                            "type": "string",
                            "enum": ["all", "any"],
                            "default": "all",
                            "description": "Require all conditions or any condition; defaults to all.",
                        },
                        "condition_mode": {
                            "type": "string",
                            "enum": ["criteria", "all_messages"],
                            "description": (
                                "Use criteria when the request names message conditions. "
                                "Use all_messages only when it explicitly applies to every incoming message."
                            ),
                        },
                        "conditions": {
                            "type": "array",
                            "maxItems": 10,
                            "description": (
                                "Explicit message conditions. Supply at least one item for "
                                "condition_mode=criteria, or an empty array for all_messages."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "field": {
                                        "type": "string",
                                        "enum": [
                                            "subject",
                                            "sender",
                                            "recipient",
                                            "cc",
                                            "body",
                                        ],
                                        "description": "Message field to test.",
                                    },
                                    "operator": {
                                        "type": "string",
                                        "enum": [
                                            "contains",
                                            "does_not_contain",
                                            "is",
                                            "is_not",
                                            "begins_with",
                                            "ends_with",
                                        ],
                                        "description": "Comparison applied to the selected field.",
                                    },
                                    "value": {
                                        **NONEMPTY_STRING,
                                        "maxLength": 1024,
                                        "description": "Literal text to compare with the selected message field.",
                                    },
                                },
                                "required": ["field", "operator", "value"],
                                "additionalProperties": False,
                            },
                        },
                        "action": {
                            "type": "string",
                            "enum": ["move_to_local_folder", "forward"],
                            "description": "Move matching messages to a local folder or forward them.",
                        },
                        "destination": {
                            **NONEMPTY_STRING,
                            "maxLength": 512,
                            "description": (
                                "For move_to_local_folder, the visible local-folder name. "
                                "For forward, the destination email address."
                            ),
                        },
                    },
                    "required": [
                        "name",
                        "condition_mode",
                        "conditions",
                        "action",
                        "destination",
                    ],
                    "allOf": [
                        {
                            "if": {
                                "properties": {"condition_mode": {"const": "criteria"}},
                                "required": ["condition_mode"],
                            },
                            "then": {"properties": {"conditions": {"minItems": 1}}},
                        },
                        {
                            "if": {
                                "properties": {
                                    "condition_mode": {"const": "all_messages"}
                                },
                                "required": ["condition_mode"],
                            },
                            "then": {"properties": {"conditions": {"maxItems": 0}}},
                        },
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["filters"],
    },
    "mail.configure": {
        "description": "Change exactly one semantic mail setting per call. Keep unrelated settings unchanged.",
        "properties": {
            "identity": {
                **NONEMPTY_STRING,
                "description": (
                    "Thunderbird identity identifier. Required when setting signature_text "
                    "or quote_original_on_reply; no identity is inferred."
                ),
            },
            "signature_text": {
                "type": "string",
                "description": (
                    "Plain-text email signature. Use newline characters between lines. "
                    "For robustness, literal \\n and \\r\\n sequences are also interpreted as line breaks."
                ),
            },
            "quote_original_on_reply": {
                "type": "boolean",
                "description": "Whether replies include the quoted original message.",
            },
            "automatic_filters_on_subfolders": {
                "type": "boolean",
                "description": (
                    "Whether incoming message filters run automatically on IMAP subfolders."
                ),
            },
            "unified_inbox": {
                "type": "boolean",
                "description": (
                    "Whether Thunderbird combines account inboxes in Unified Folders view."
                ),
            },
            "dark_mode": {
                "type": "boolean",
                "description": "Whether Thunderbird uses its built-in complete dark theme.",
            },
        },
        "required": [],
        "oneOf": [
            {"required": ["signature_text"]},
            {"required": ["quote_original_on_reply"]},
            {"required": ["automatic_filters_on_subfolders"]},
            {"required": ["unified_inbox"]},
            {"required": ["dark_mode"]},
        ],
        "allOf": [
            {
                "if": {
                    "anyOf": [
                        {"required": ["signature_text"]},
                        {"required": ["quote_original_on_reply"]},
                    ]
                },
                "then": {"required": ["identity"]},
            }
        ],
    },
    "compose.set_recipients": {
        "description": (
            "Add or replace recipient email addresses in the To (receiver) field of an "
            "already-open Thunderbird compose window, including an opened draft. If the "
            "intended draft is not open, open it in Thunderbird first. Append keeps existing "
            "addresses; replace clears them. Omit subject when exactly one compose window "
            "is open; otherwise use its observed exact subject. This edits recipients only "
            "and does not create or send a message."
        ),
        "properties": {
            "recipients": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "minLength": 3,
                    "description": (
                        "One plain email address selected from the instruction or current application data."
                    ),
                },
                "description": (
                    "Exact recipient email addresses selected by the model. Do not include names, "
                    "commas, semicolons, or addresses not observed in the task data."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["append", "replace"],
                "default": "append",
                "description": (
                    "Append preserves existing recipient pills; replace removes them first. "
                    "Use append when the instruction says add recipients."
                ),
            },
            "subject": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional exact subject used to select one compose window. Omit only when "
                    "one compose window is open; ambiguous matches are rejected."
                ),
            },
        },
        "required": ["recipients"],
    },
    "messages.query": {
        "properties": {
            "folder_name": {
                **NONEMPTY_STRING,
                "description": (
                    "Thunderbird folder name or slash-separated folder path to query, "
                    "for example daily or Projects/Invoices."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "default": 50,
                "description": (
                    "Maximum number of matching messages to return. For a task that modifies every "
                    "message in the folder, set limit=500 and verify returned_count equals matched_count."
                ),
            },
            "select_from": {
                "type": "string",
                "enum": ["latest", "earliest"],
                "default": "latest",
                "description": (
                    "Which end of the date-sorted matches to select before arranging the response."
                ),
            },
            "order": {
                "type": "string",
                "enum": ["ascending", "descending"],
                "default": "descending",
                "description": (
                    "Date order of returned messages. For the latest N messages arranged from "
                    "earliest to most recent, use select_from='latest' and order='ascending'."
                ),
            },
            "sender_contains": {
                **NONEMPTY_STRING,
                "description": "Optional case-insensitive substring of sender name or address.",
            },
            "subject_contains": {
                **NONEMPTY_STRING,
                "description": "Optional case-insensitive subject substring.",
            },
            "after": {
                **NONEMPTY_STRING,
                "description": "Optional inclusive ISO-8601 lower date or date-time bound.",
            },
            "before": {
                **NONEMPTY_STRING,
                "description": "Optional exclusive ISO-8601 upper date or date-time bound.",
            },
            "has_attachments": {
                "type": "boolean",
                "description": "Optional filter for messages with or without attachments.",
            },
        },
        "required": ["folder_name"],
    },
    "messages.update_flags": {
        "description": (
            "Update exactly one supported flag on explicitly selected messages in one local folder. "
            "First call messages.query and copy mailbox_indices from its returned rows; this action "
            "does not search, select, or infer which messages the user meant. Supports flag='starred'. "
            "value=true adds stars and value=false removes them. The persisted flag state is read back."
        ),
        "properties": {
            "folder_name": {
                **NONEMPTY_STRING,
                "description": "Exact visible folder name returned by messages.query.",
            },
            "mailbox_indices": {
                "type": "array",
                "minItems": 1,
                "maxItems": 500,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": 0},
                "description": (
                    "Exact zero-based mailbox_index values returned by messages.query for this folder."
                ),
            },
            "flag": {
                "type": "string",
                "enum": ["starred"],
                "description": "The explicit message flag to update.",
            },
            "value": {
                "type": "boolean",
                "description": "true adds the star; false removes the star.",
            },
        },
        "required": ["folder_name", "mailbox_indices", "flag", "value"],
        "additionalProperties": False,
    },
    "messages.export_eml": {
        "properties": {
            "folder_name": {
                **NONEMPTY_STRING,
                "description": (
                    "Thunderbird folder name or slash-separated folder path to export, "
                    "for example Inbox or Projects/Invoices. The Adapter resolves the "
                    "current profile's mailbox storage; do not supply an internal mbox path."
                ),
            },
            "output_dir": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Absolute or ~/ destination directory. Every message is written as a "
                    "separate .eml file with a subject-derived filename. The destination "
                    "must not already contain any .eml entries."
                ),
            },
        },
        "required": ["folder_name", "output_dir"],
    },
    "attachments.save": {
        "properties": {
            "folder_name": {
                **NONEMPTY_STRING,
                "description": (
                    "Thunderbird folder name or slash-separated folder path returned by "
                    "messages.query."
                ),
            },
            "message_id": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact non-empty message_id returned by messages.query. Omit this field "
                    "when the query row has no Message-ID and use mailbox_index instead; never "
                    "send an empty string. Providing both is allowed when they identify the same message."
                ),
            },
            "mailbox_index": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based mailbox_index returned by messages.query. Use this exact selector "
                    "when the message_id field is absent (the normal representation for a missing "
                    "Message-ID)."
                ),
            },
            "attachment_name": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact attachment name returned by messages.query. It may be omitted only "
                    "when the selected message has exactly one attachment."
                ),
            },
            "attachment_index": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based attachment index. Use it to disambiguate duplicate or unnamed "
                    "attachments."
                ),
            },
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Absolute or ~/ destination including the final filename selected from the "
                    "instruction or observed local naming pattern. Parent directories are created."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Replace an existing regular file only when explicitly true.",
            },
        },
        "required": ["folder_name", "output_path"],
        "anyOf": [
            {"required": ["message_id"]},
            {"required": ["mailbox_index"]},
        ],
    },
    "contacts.export_csv": {
        "properties": {
            "address_book": {
                **NONEMPTY_STRING,
                "description": (
                    "Visible Thunderbird address-book name, for example Personal Address Book or "
                    "Collected Addresses."
                ),
            },
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Absolute writable .csv path, or a home-relative path beginning with ~/. "
                    "Use a separate LibreOffice action or command when another spreadsheet format is required."
                ),
            },
        },
        "required": ["address_book", "output_path"],
    },
    "accounts.remove": {
        "properties": {
            "email": {
                **NONEMPTY_STRING,
                "description": "Email address of the account to remove.",
            },
            "hostname": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional incoming server hostname used only to disambiguate. Omit it to resolve "
                    "the server from the current Thunderbird profile by email address."
                ),
            },
        },
        "required": ["email"],
    },
    "ui.prefill_account_setup": {
        "properties": {
            "full_name": {
                **NONEMPTY_STRING,
                "description": "Display name to enter in Thunderbird's account setup form.",
            },
            "email": {
                **NONEMPTY_STRING,
                "description": "Email address to enter in the account setup form.",
            },
            "password": {
                **NONEMPTY_STRING,
                "description": "Password supplied by the user for this account setup.",
            },
        },
        "required": ["full_name", "email", "password"],
    },
}
