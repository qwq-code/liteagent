from __future__ import annotations

from typing import Any

from .debugging import DEBUG_WAIT_STATES
from .editor import EDITOR_ENUM_SETTINGS
from .files import AUTO_SAVE_MODES, HOT_EXIT_MODES
from .keybindings import KEYBINDING_OPERATION_COMMANDS


NONEMPTY_STRING = {"type": "string", "minLength": 1}


def _workspace_param_schema() -> dict[str, Any]:
    return {
        "description": (
            "The path is a complete workspace filename, never a directory: it must end "
            "with .code-workspace (for example /home/user/project/project.code-workspace). "
            "When the instruction gives a directory and workspace name, append the name and "
            ".code-workspace to form this path. folders must contain the observed project root."
        ),
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "pattern": r"^/.*[.]code-workspace$",
                "description": (
                    "Complete absolute output filename ending in .code-workspace; do not pass "
                    "the containing directory. For directory /home/user/project/ and name "
                    "project, use /home/user/project/project.code-workspace."
                ),
            },
            "folders": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {
                            **NONEMPTY_STRING,
                            "description": (
                                "Project folder to include. Absolute paths are converted by the "
                                "Adapter to portable paths relative to the workspace file when possible."
                            ),
                        },
                        "name": {
                            **NONEMPTY_STRING,
                            "description": "Optional display name for this workspace folder.",
                        },
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
                "description": "One or more project folders included in the saved workspace.",
            },
        },
        "required": ["path", "folders"],
    }


def _workspace_add_param_schema() -> dict[str, Any]:
    schema = _workspace_param_schema()
    schema["properties"]["path"]["pattern"] = r"[.]code-workspace$"
    schema["properties"]["path"]["description"] = (
        "Absolute path of an existing .code-workspace file to update, or an observed root "
        "of the active workspace when a unique saved workspace file can be resolved."
    )
    schema["properties"]["folders"]["description"] = (
        "Only the project folders to add. The Adapter preserves every existing workspace "
        "folder and setting, converts new absolute paths to portable relative paths when "
        "possible, and skips folders already present. Set name only for a custom display "
        "label; a name identical to the folder basename is omitted as redundant."
    )
    return schema


# Model-visible parameter contracts owned by the Adapter. Runtime validation
# remains in vscode_adapter.schema and is checked against this manifest.
STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "workspace.inspect": {
        "description": (
            "Read the exact active VS Code workspace name, roots, window identity, and "
            "resolution source from observable desktop and workspace-storage state. When "
            "the active workspace is a saved .code-workspace file, return its exact path for "
            "a later explicit workspace.add_folders call. If no workspace can be resolved, "
            "use editor.open_file with an exact model-selected path to obtain a usable "
            "window identifier. This action does not modify state."
        ),
        "properties": {},
        "required": [],
    },
    "workspace.find_files": {
        "description": (
            "Resolve the currently active VS Code workspace from live desktop state, then "
            "find files or directories beneath its roots. Use this when the instruction "
            "refers to files in the current VS Code project but gives no filesystem path."
        ),
        "properties": {
            "name_patterns": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "uniqueItems": True,
                "items": NONEMPTY_STRING,
                "description": (
                    "Basename globs selected from the instruction or observed application state, such as "
                    "['*.txt'] or ['pyproject.toml', '*.py']."
                ),
            },
            "kind": {
                "type": "string",
                "enum": ["file", "directory", "any"],
                "description": "Return files, directories, or either; defaults to file.",
            },
            "recursive": {
                "type": "boolean",
                "description": "Search nested workspace directories; defaults to true.",
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Include dot-prefixed entries; defaults to false.",
            },
            "max_depth": {
                "type": "integer",
                "minimum": 1,
                "maximum": 8,
                "description": "Maximum recursive depth below each workspace root; defaults to 8.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Maximum returned matches; defaults to 200.",
            },
        },
        "required": ["name_patterns"],
    },
    "extension.install": {
        "properties": {
            "source": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact Marketplace extension identifier such as redhat.vscode-yaml, or "
                    "the absolute path of a local .vsix file."
                ),
            },
            "source_type": {
                "type": "string",
                "enum": ["marketplace", "vsix"],
                "description": (
                    "Use marketplace for a publisher.name identifier and vsix for a local "
                    "VSIX file path. When a verified offline VSIX for the selected Marketplace "
                    "identifier is deployed, the Adapter may use that local file without changing "
                    "the model-selected extension identity."
                ),
            },
            "force": {
                "type": "boolean",
                "description": "Allow VS Code to replace an existing version; defaults to true.",
            },
        },
        "required": ["source", "source_type"],
    },
    "debugging.configure": {
        "properties": {
            "focus_editor_on_break": {
                "type": "boolean",
                "description": (
                    "Whether a debugger break moves cursor focus to the editor. Set false to "
                    "preserve focus in the Debug Console or other current debug view."
                ),
            },
            "inline_values": {
                "type": "string",
                "enum": ["auto", "off", "on"],
                "description": "Whether variable values appear inline while debugging.",
            },
            "internal_console": {
                "type": "string",
                "enum": [
                    "neverOpen",
                    "openOnFirstSessionStart",
                    "openOnSessionStart",
                ],
                "description": "When the internal Debug Console opens automatically.",
            },
            "open_debug_view": {
                "type": "string",
                "enum": [
                    "neverOpen",
                    "openOnDebugBreak",
                    "openOnFirstSessionStart",
                    "openOnSessionStart",
                ],
                "description": "When VS Code opens the Run and Debug view automatically.",
            },
            "show_breakpoints_in_overview_ruler": {
                "type": "boolean",
                "description": "Whether the editor overview ruler shows breakpoints.",
            },
            "show_inline_breakpoint_candidates": {
                "type": "boolean",
                "description": "Whether inline breakpoint candidates are shown in the editor.",
            },
            "path": {
                **NONEMPTY_STRING,
                "description": "Optional settings.json path; omit for active user settings.",
            },
        },
        "required": [],
        "oneOf": [
            {"required": ["focus_editor_on_break"]},
            {"required": ["inline_values"]},
            {"required": ["internal_console"]},
            {"required": ["open_debug_view"]},
            {"required": ["show_breakpoints_in_overview_ruler"]},
            {"required": ["show_inline_breakpoint_candidates"]},
        ],
    },
    "editor.configure": {
        "description": (
            "Configure one VS Code editor preference. For multiple rows of open-file "
            "tabs, use wrap_tabs (tab bar layout, not text wrapping). Use word_wrap "
            "only for text wrapping; word_wrap_column is the text column and may be "
            "paired with word_wrap. Omit path to update active user settings."
        ),
        "properties": {
            "wrap_tabs": {
                "type": "boolean",
                "description": (
                    "Whether the VS Code tab bar wraps open file tabs onto multiple rows "
                    "when horizontal space is insufficient. This controls tab layout, "
                    "not text or line wrapping; use wrap_tabs for this setting."
                ),
            },
            "word_wrap": {
                "type": "string",
                "enum": sorted(EDITOR_ENUM_SETTINGS["word_wrap"][1]),
                "description": (
                    "Text wrapping behavior: off, on at the viewport, at_column at the "
                    "configured column, or bounded at the smaller of viewport and column."
                ),
            },
            "word_wrap_column": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "description": (
                    "Positive editor column used by at_column or bounded wrapping. This may "
                    "also be changed independently of the current word-wrap mode. Pass "
                    "only this field when changing the column; do not include word_wrap "
                    "in the same call."
                ),
            },
            "minimap_enabled": {
                "type": "boolean",
                "description": "Whether the editor minimap is visible.",
            },
            "line_numbers": {
                "type": "string",
                "enum": sorted(EDITOR_ENUM_SETTINGS["line_numbers"][1]),
                "description": "Editor line-number display mode.",
            },
            "sticky_scroll_enabled": {
                "type": "boolean",
                "description": "Whether sticky scopes remain visible at the editor top.",
            },
            "smooth_scrolling": {
                "type": "boolean",
                "description": "Whether editor scrolling is animated smoothly.",
            },
            "render_whitespace": {
                "type": "string",
                "enum": sorted(EDITOR_ENUM_SETTINGS["render_whitespace"][1]),
                "description": "Which whitespace characters the editor renders visibly.",
            },
            "path": {
                **NONEMPTY_STRING,
                "pattern": r"^(?:/|~/|file://(?:localhost)?/).+",
                "description": (
                    "Optional settings.json path. Omit this field unless the user "
                    "explicitly supplies a settings.json path; active user settings "
                    "are the default."
                ),
            },
        },
        "required": [],
        "oneOf": [
            {"required": ["wrap_tabs"]},
            {
                "required": ["word_wrap"],
                "not": {"required": ["word_wrap_column"]},
            },
            {
                "required": ["word_wrap_column"],
                "not": {"required": ["word_wrap"]},
            },
            {"required": ["word_wrap", "word_wrap_column"]},
            {"required": ["minimap_enabled"]},
            {"required": ["line_numbers"]},
            {"required": ["sticky_scroll_enabled"]},
            {"required": ["smooth_scrolling"]},
            {"required": ["render_whitespace"]},
        ],
    },
    "editor.open_file": {
        "description": (
            "Open exactly one model-selected existing file in VS Code and return the observed "
            "window identifier. This action does not change views, execute code, inspect source, "
            "or expand UI sections. Use it first when a window-dependent action needs a fresh "
            "identifier; copy the returned window_id exactly and never invent or normalize one."
        ),
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Exact existing file path selected by the model, usually from file.read_text "
                    "or workspace.find_files. If the path is unknown, use workspace.find_files "
                    "first; do not infer a path from the visible editor or retry PATH_NOT_FOUND "
                    "with another guessed path."
                ),
            },
            "reuse_window": {
                "type": "boolean",
                "description": "Reuse the existing VS Code window when true; defaults to true.",
            },
        },
        "required": ["path"],
        "additionalProperties": False,
    },
    "ui.open_view": {
        "description": (
            "Open one standard VS Code activity view in one explicitly selected observed window. "
            "The window_id must be copied exactly from a successful observation such as "
            "editor.open_file; do not invent, normalize, or default it. This action does not "
            "open files, expand sections, run code, or infer the desired view. Opening "
            "run_and_debug only shows the view; use debug.start to start a debug session."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID copied from a successful editor.open_file or workspace.open result; never use a guessed/default ID.",
            },
            "view": {
                "type": "string",
                "enum": [
                    "explorer",
                    "search",
                    "source_control",
                    "run_and_debug",
                    "extensions",
                ],
                "description": "One model-selected standard VS Code activity view.",
            },
        },
        "required": ["window_id", "view"],
        "additionalProperties": False,
    },
    "ui.expand_section": {
        "description": (
            "Expand one exact accessible VS Code section in one explicitly selected window. The "
            "window_id must be copied exactly from a successful observation; if it is stale, "
            "obtain a fresh one with editor.open_file before retrying. The Adapter does not "
            "discover variable names, choose a section, open a view, or open a file. Only "
            "expand a section currently exposed in the UI. For runtime VARIABLES, first "
            "start debugging with debug.start and pause at a model-selected breakpoint; "
            "opening Run and Debug alone does not create variables. SECTION_NOT_FOUND "
            "means the window was found but the section is absent, not that its ID is wrong."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID copied from a successful observation action; never use a guessed/default ID.",
            },
            "name": {
                **NONEMPTY_STRING,
                "maxLength": 256,
                "description": (
                    "Accessible section name selected from current UI state; matching ignores "
                    "case and repeated or surrounding whitespace."
                ),
            },
        },
        "required": ["window_id", "name"],
        "additionalProperties": False,
    },
    "debug.breakpoint.set": {
        "description": (
            "Set a standard line breakpoint at one explicit path and one-based line in one "
            "explicitly selected active VS Code window. The Adapter validates the file and line, "
            "opens that exact location in the selected window, sends VS Code's standard F9 command "
            "when needed, and succeeds only after the visible Breakpoints tree exposes one checked "
            "entry for that exact path and line. It does not inspect the task, choose a path or "
            "line, edit source, or start debugging."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID returned by an observation action.",
            },
            "path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": "Exact absolute or ~/ source path selected from live read-back.",
            },
            "line": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": "Explicit natural one-based source line selected from live read-back.",
            },
        },
        "required": ["window_id", "path", "line"],
        "additionalProperties": False,
    },
    "debug.start": {
        "description": (
            "Start debugging the active source file or existing launch configuration in one "
            "explicitly selected active VS Code window. Use this to start the session needed "
            "to observe runtime arrays and other variables; ui.open_view does not run code. "
            "A paused session needs an existing or separately model-selected breakpoint. "
            "This action uses the existing debugger extension and sends only VS Code's "
            "standard F5 command and waits for observable Continue/Pause plus Stop/Disconnect "
            "controls. It does not install an extension, edit source, create a launch "
            "configuration, add a breakpoint, select a debugger, or synthesize variables. "
            "F5 may open a debugger or launch-configuration picker: the error observation "
            "includes its visible quick_inputs prompts and options. Use gui_request to "
            "choose an appropriate displayed option and continue from the new screen; "
            "do not repeat F5 or reinstall an available debugger while a picker is open. "
            "If VS Code requests a missing debugger extension, stop retrying F5: use "
            "tools_search with an extension/install query, then call extension.install "
            "with the model-selected Marketplace identifier or local VSIX path and "
            "matching source_type before retrying debug.start. Reopening the view "
            "cannot install an extension."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID copied from a successful workspace.inspect or editor.open_file result; never guess an ID.",
            },
        },
        "required": ["window_id"],
        "additionalProperties": False,
    },
    "debug.session.wait": {
        "description": (
            "Wait until one explicitly selected active VS Code window exposes an exact debugger "
            "state through its standard Continue or Pause control and Stop/Disconnect control. "
            "Paused requires exactly one visible Continue control and no Pause control; running "
            "requires exactly one visible Pause control and no Continue control. Ambiguous or "
            "duplicate controls never satisfy the wait."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID returned by an observation action.",
            },
            "state": {
                "type": "string",
                "enum": sorted(DEBUG_WAIT_STATES),
                "description": "Exact observable debugger state to wait for.",
            },
        },
        "required": ["window_id", "state"],
        "additionalProperties": False,
    },
    "debug.continue": {
        "description": (
            "Continue one observably paused debug session in one explicitly selected active VS "
            "Code window. This presses the unique visible Continue control through AT-SPI and "
            "succeeds only after that window observably becomes running or inactive. It does not "
            "select a stack frame, add a breakpoint, or evaluate an expression."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID returned by an observation action.",
            },
        },
        "required": ["window_id"],
        "additionalProperties": False,
    },
    "debug.stop": {
        "description": (
            "Stop one observable debug session in one explicitly selected active VS Code window. "
            "This presses the unique visible Stop control through AT-SPI and succeeds only after "
            "that window exposes no active debug controls. A Disconnect-only session fails closed."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID returned by an observation action.",
            },
        },
        "required": ["window_id"],
        "additionalProperties": False,
    },
    "debug.variables.read": {
        "description": (
            "Read the currently visible tree items from VS Code's standard VARIABLES pane "
            "during an observable paused debug session. This read-only action does not parse "
            "source, evaluate expressions, infer variable names, open a view, expand a scope, "
            "or create display content. Reading or increasing max_items does not run code. "
            "A breakpoint pauses before its line executes; later assignments have not yet "
            "run. Choose a separate execution/GUI step to advance or expand the view. "
            "The window_id must be copied exactly from a successful "
            "observation; if it is stale, obtain a fresh one with editor.open_file before "
            "retrying. Open Run and Debug and expand VARIABLES separately when needed."
        ),
        "properties": {
            "window_id": {
                "type": "string",
                "pattern": "^0x[0-9A-Fa-f]+$",
                "description": "Exact wmctrl window ID copied from a successful observation action; never use a guessed/default ID.",
            },
            "max_items": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1024,
                "description": "Maximum currently visible VARIABLES tree items to return.",
            },
        },
        "required": ["window_id"],
        "additionalProperties": False,
    },
    "diagnostics.configure": {
        "properties": {
            "language": {
                "type": "string",
                "enum": ["python"],
                "description": "Language whose editor diagnostics should be configured.",
            },
            "diagnostic": {
                "type": "string",
                "enum": [
                    "general_type_issues",
                    "incompatible_method_override",
                    "missing_imports",
                    "missing_module_source",
                    "optional_member_access",
                    "undefined_variables",
                    "unused_imports",
                    "unused_variables",
                ],
                "description": (
                    "Semantic diagnostic category. Use missing_imports for unresolved or "
                    "missing Python import reports."
                ),
            },
            "severity": {
                "type": "string",
                "enum": ["error", "warning", "information", "none"],
                "description": "Desired reporting level; none disables this diagnostic report.",
            },
            "path": {
                **NONEMPTY_STRING,
                "description": "Optional settings.json path; omit for active user settings.",
            },
        },
        "required": ["language", "diagnostic", "severity"],
    },
    "files.configure": {
        "description": (
            "Change exactly one semantic VS Code file preference per call. The autosave "
            "mode and delay may be supplied together as one coupled preference."
        ),
        "properties": {
            "auto_save": {
                "type": "string",
                "enum": sorted(AUTO_SAVE_MODES),
                "description": (
                    "Automatic save mode: off, after_delay, on_focus_change, or "
                    "on_window_change."
                ),
            },
            "auto_save_delay_ms": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3_600_000,
                "description": (
                    "Delay in milliseconds used by after_delay autosave; it may be paired "
                    "with auto_save."
                ),
            },
            "trim_trailing_whitespace": {
                "type": "boolean",
                "description": "Whether saving removes trailing whitespace.",
            },
            "insert_final_newline": {
                "type": "boolean",
                "description": "Whether saving inserts a final newline when missing.",
            },
            "trim_final_newlines": {
                "type": "boolean",
                "description": "Whether saving removes extra final newlines.",
            },
            "hot_exit": {
                "type": "string",
                "enum": sorted(HOT_EXIT_MODES),
                "description": "Whether unsaved editors are restored after exit.",
            },
            "path": {
                **NONEMPTY_STRING,
                "description": "Optional settings.json path; omit for active user settings.",
            },
        },
        "required": [],
        "oneOf": [
            {"anyOf": [{"required": ["auto_save"]}, {"required": ["auto_save_delay_ms"]}], "not": {"anyOf": [{"required": ["hot_exit"]}, {"required": ["trim_trailing_whitespace"]}, {"required": ["insert_final_newline"]}, {"required": ["trim_final_newlines"]}]}},
            {"required": ["hot_exit"], "not": {"anyOf": [{"required": ["auto_save"]}, {"required": ["auto_save_delay_ms"]}, {"required": ["trim_trailing_whitespace"]}, {"required": ["insert_final_newline"]}, {"required": ["trim_final_newlines"]}]}},
            {"required": ["trim_trailing_whitespace"], "not": {"anyOf": [{"required": ["auto_save"]}, {"required": ["auto_save_delay_ms"]}, {"required": ["hot_exit"]}, {"required": ["insert_final_newline"]}, {"required": ["trim_final_newlines"]}]}},
            {"required": ["insert_final_newline"], "not": {"anyOf": [{"required": ["auto_save"]}, {"required": ["auto_save_delay_ms"]}, {"required": ["hot_exit"]}, {"required": ["trim_trailing_whitespace"]}, {"required": ["trim_final_newlines"]}]}},
            {"required": ["trim_final_newlines"], "not": {"anyOf": [{"required": ["auto_save"]}, {"required": ["auto_save_delay_ms"]}, {"required": ["hot_exit"]}, {"required": ["trim_trailing_whitespace"]}, {"required": ["insert_final_newline"]}]}},
        ],
    },
    "file.read_text": {
        "description": (
            "Read a character window from one existing UTF-8 text or source file without "
            "opening an editor window. This reads the saved file on disk; an unsaved "
            "editor buffer can differ and is not synchronized by this call. "
            "Offsets count Unicode characters, not bytes. "
            "Use next_start_char to read the following window when source_truncated=true."
        ),
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "description": (
                    "Absolute or ~/ path observed in file discovery. A project label in the editor "
                    "does not reveal its filesystem root. If the path is unknown or returned "
                    "PATH_NOT_FOUND, use workspace.find_files with name_patterns first; "
                    "use tools_search if that action is not exposed. Read an exact returned path."
                ),
            },
            "max_chars": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100_000,
                "description": "Maximum Unicode characters returned from start_char; defaults to 20000.",
            },
            "start_char": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based Unicode character offset; defaults to 0. "
                    "Copy an observed next_start_char to continue reading the same file."
                ),
            },
        },
        "required": ["path"],
    },
    "file.replace_literal": {
        "description": (
            "Replace every exact occurrence of old with new in one saved disk file. "
            "This does not edit or synchronize an unsaved editor buffer. "
            "Surrounding and following lines stay unchanged; this does not "
            "automatically replace a whole function or block."
        ),
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "description": "Absolute path of the text file to edit.",
            },
            "old": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact literal text to replace everywhere in the file, including "
                    "whitespace and newlines. Copy old from the latest file.read_text "
                    "disk result, not from an unsaved editor screenshot. "
                    "To replace a whole function or block, "
                    "include its complete current text in old; a declaration alone "
                    "does not include its body. Multiline strings are supported. "
                    "No match returns TEXT_NOT_FOUND without editing the file."
                ),
            },
            "new": {
                "type": "string",
                "description": (
                    "Literal replacement text; an empty string deletes matches. "
                    "Supply the intended whitespace on each line: lines after a newline "
                    "do not inherit indentation from the first line."
                ),
            },
        },
        "required": ["path", "old", "new"],
    },
    "file.indent_lines": {
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "description": "Absolute path of the text or source file to indent.",
            },
            "start_line": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": "First line to indent, using natural one-based line numbers.",
            },
            "end_line": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": "Last line to indent, inclusive and one-based.",
            },
            "levels": {
                "type": "integer",
                "minimum": 1,
                "maximum": 16,
                "description": (
                    "Number of existing editor indentation levels to add. Use 1 for one "
                    "tab or one indentation level. The Adapter detects whether the file "
                    "uses tabs or spaces and its current indentation width."
                ),
            },
        },
        "required": ["path", "start_line", "end_line", "levels"],
    },
    "explorer.set_exclusion": {
        "properties": {
            "pattern": {
                **NONEMPTY_STRING,
                "description": (
                    "File or folder name or VS Code glob pattern to configure, such as "
                    "node_modules, build/*.tmp, or **/.cache."
                ),
            },
            "scope": {
                "type": "string",
                "enum": ["any_depth", "workspace_root"],
                "description": (
                    "Use any_depth when every matching nested file or folder should be "
                    "affected; use workspace_root when the pattern is relative only to the "
                    "workspace root."
                ),
            },
            "hidden": {
                "type": "boolean",
                "description": (
                    "True hides matching Explorer entries; false makes the configured "
                    "pattern visible again."
                ),
            },
            "path": {
                **NONEMPTY_STRING,
                "description": "Optional settings.json path; omit for active user settings.",
            },
        },
        "required": ["pattern", "scope", "hidden"],
    },
    "workspace.write": _workspace_param_schema(),
    "workspace.set_folders": _workspace_param_schema(),
    "workspace.add_folders": _workspace_add_param_schema(),
    "keybindings.ensure": {
        "properties": {
            "key": {
                **NONEMPTY_STRING,
                "description": "VS Code key chord such as ctrl+f or ctrl+j.",
            },
            "operation": {
                "type": "string",
                "enum": sorted(KEYBINDING_OPERATION_COMMANDS),
                "description": (
                    "Complete user-facing shortcut operation. The Adapter maps both the stable "
                    "VS Code command and its natural trigger context. For example, tree_view_find "
                    "means Explorer list find when listFocus && listSupportsFind, while "
                    "focus_active_editor means moving from a focused terminal to the editor."
                ),
            },
            "disabled": {
                "type": "boolean",
                "description": (
                    "True removes/disables the shortcut by persisting VS Code's negative "
                    "command form; false ensures an enabled binding."
                ),
            },
            "path": {
                **NONEMPTY_STRING,
                "description": "Optional keybindings.json path; omit for active user bindings.",
            },
        },
        "required": ["key", "operation", "disabled"],
    },
}
