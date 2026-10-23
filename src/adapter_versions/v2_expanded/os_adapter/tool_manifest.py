from __future__ import annotations

from typing import Any

from .local_paths import NON_ROOT_LOCAL_PATH_PATTERN


NONEMPTY_STRING = {"type": "string", "minLength": 1}
_PYTHON_SCRIPT_ARGUMENT_GUIDANCE = (
    " For python3 -c, put the complete Python script in one argv item after -c. "
    "Preserve line breaks and indentation, encoding line breaks as \\n in JSON. "
    "JSON string escaping still applies even though shell escaping is not used. "
    "A Python # comment lasts until a newline and will hide later code on the same "
    "line. Semicolons do not replace the required line structure of def/if/for/else blocks."
)
_PDF_FORM_PATH = {
    **NONEMPTY_STRING,
    "pattern": "^(?:/|~/|file://(?:localhost)?/).+\\.[pP][dD][fF]$",
}

_ARCHIVE_CREATE_PROPERTIES = {
    "archive_path": {
        **NONEMPTY_STRING,
        "pattern": r"^(?:/|~/).+\.[zZ][iI][pP]$",
        "description": "Absolute or ~/ ZIP output path selected by the model.",
    },
    "input_paths": {
        "type": "array",
        "minItems": 1,
        "maxItems": 256,
        "uniqueItems": True,
        "items": {**NONEMPTY_STRING, "pattern": "^(?:/|~/).*"},
        "description": (
            "Exact existing files or directories to include. Direct files use their basenames "
            "unless base_directory is supplied."
        ),
    },
    "base_directory": {
        **NONEMPTY_STRING,
        "pattern": "^(?:/|~/).*",
        "description": (
            "Optional existing directory used to derive relative ZIP member paths; every "
            "input_path must be inside it."
        ),
    },
    "overwrite": {
        "type": "boolean",
        "description": "Replace an existing output ZIP only when true; defaults to false.",
    },
}
_ARCHIVE_EXTRACT_PROPERTIES = {
    "archive_path": {
        **NONEMPTY_STRING,
        "pattern": r"^(?:/|~/).+\.[zZ][iI][pP]$",
        "description": "Absolute or ~/ path to an existing ZIP selected by the model.",
    },
    "destination_directory": {
        **NONEMPTY_STRING,
        "pattern": "^(?:/|~/).*",
        "description": (
            "Directory selected by the model where the ZIP is extracted. Unsafe members and "
            "symbolic links are rejected before writing."
        ),
    },
    "overwrite": {
        "type": "boolean",
        "description": "Replace existing extracted members only when true; defaults to false.",
    },
}

# Model-visible contracts owned by the OS Adapter. Runtime validation remains
# in os_adapter.schema and is checked against this manifest.
STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "clipboard.set": {
        "properties": {
            "text": {
                "type": "string",
                "maxLength": 1_000_000,
                "description": (
                    "Exact text selected by the model to place on the desktop clipboard. "
                    "Newlines and an empty string are preserved exactly."
                ),
            },
        },
        "required": ["text"],
    },
    "clipboard.get": {
        "properties": {
            "max_chars": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": (
                    "Maximum characters returned to the model; defaults to 100000. "
                    "The result reports whether the clipboard text was truncated."
                ),
            },
        },
        "required": [],
    },
    "trash.list": {
        "description": (
            "Read a bounded page of current Trash entries and expose each exact trash URI "
            "with its exact original path. This action never selects or restores an entry."
        ),
        "properties": {
            "offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100_000,
                "description": "Zero-based entry offset; defaults to 0.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Maximum entries returned; defaults to 100.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    "trash.restore": {
        "description": (
            "Restore exactly one current Trash entry. Copy both identifiers from the same "
            "trash.list result; the Adapter rejects a missing URI or mismatched pair instead "
            "of searching by filename."
        ),
        "properties": {
            "trash_uri": {
                **NONEMPTY_STRING,
                "pattern": "^trash:///.+",
                "description": "Exact trash:/// URI returned by trash.list.",
            },
            "original_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Exact original absolute or ~/ path paired with trash_uri by trash.list."
                ),
            },
        },
        "required": ["trash_uri", "original_path"],
        "additionalProperties": False,
    },
    "filesystem.create_directory": {
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Absolute or ~/ directory path selected by the model. Creates this directory "
                    "idempotently and returns whether it was newly created."
                ),
            },
            "parents": {
                "type": "boolean",
                "description": (
                    "Create missing parent directories; defaults to true. Set false only when "
                    "the immediate parent is known to exist."
                ),
            },
        },
        "required": ["path"],
    },
    "filesystem.copy": {
        "description": (
            "Copy exactly one model-selected regular file to exactly one model-selected output "
            "path. Use filesystem.find first when the source path is unknown. Set create_parents=true "
            "to create missing destination parents as part of this single-file copy, or use "
            "filesystem.create_directory first. If the "
            "Adapter reports PATH_NOT_FOUND, discover the exact path before retrying; it does "
            "not resolve guessed paths."
        ),
        "properties": {
            "source": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": "Exact existing regular-file path returned by observation or named by the user.",
            },
            "destination": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": "Exact output file path, including its final basename.",
            },
            "create_parents": {
                "type": "boolean",
                "description": (
                    "Create any missing parent directories for the exact destination file when true; "
                    "defaults to false. Does not choose paths, copy a tree, or authorize replacement."
                ),
            },
            "replace": {
                "type": "boolean",
                "description": "Replace an existing destination only when explicitly true; defaults to false.",
            },
        },
        "required": ["source", "destination"],
        "additionalProperties": False,
    },
    "filesystem.copy_to_directories": {
        "description": (
            "Copy one regular file into each model-selected destination directory using its "
            "original basename. The same source file is duplicated into EVERY directory; "
            "this does not copy different source files. Use filesystem.copy separately for "
            "different source/output file pairs. This does not recreate the source directory hierarchy. "
            "To preserve a layout, choose each file's destination directory from its observed "
            "relative path, including the required subdirectories."
        ),
        "properties": {
            "source": {
                **NONEMPTY_STRING,
            "description": (
                "Existing regular-file path selected by the model. Use an exact path returned "
                "by filesystem.find, or a basename/relative path from the active terminal "
                "working directory. Relative paths are resolved deterministically by the "
                "Adapter; do not use / or ~/ as placeholder values. After PATH_NOT_FOUND, "
                "run filesystem.find instead of repeating the same source."
                ),
            },
            "destinations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 64,
                "uniqueItems": True,
                "items": {
                    **NONEMPTY_STRING,
                },
                "description": (
                    "Directory paths only, not complete output file paths. "
                    "Destination directories selected by the model. Basenames and relative paths "
                    "are resolved from the active terminal working directory; absolute and ~/ "
                    "paths are also accepted. ~/ means home, not the current folder. If the "
                    "terminal directory is unavailable, preserve the intended location by "
                    "resolving its parent from the instruction or observed state. "
                    "For a collection copy after filesystem.find, use the exact absolute "
                    "destination derived from the collection-copy path guidance; do not reuse "
                    "the source root or submit a relative source-folder name. "
                    "Include every requested directory instead of using "
                    "/ as a placeholder. Missing directories are created and every copy is "
                    "verified."
                ),
            },
        },
        "required": ["source", "destinations"],
    },
    "filesystem.rename": {
        "description": (
            "Rename exactly one model-selected filesystem object. Use exact absolute paths when "
            "known, or provide one source basename and one destination basename; basename sources "
            "are resolved uniquely under Desktop/home defaults. When the instruction gives only a "
            "quoted name and no path, pass that name unchanged as the basename (for example, "
            "source='todo_list_Jan_1', destination='todo_list_Jan_2'); do not invent a "
            "'/Desktop/home' prefix. Ambiguous matches are rejected."
        ),
        "properties": {
            "source": {
                **NONEMPTY_STRING,
                "pattern": r"^(?:/.+|~/.+|[^/\\]+)$",
                "description": (
                    "Exact path or one concrete source basename resolved under bounded roots. "
                    "If the instruction supplies only a name, pass the name unchanged without "
                    "adding a directory prefix."
                ),
            },
            "destination": {
                **NONEMPTY_STRING,
                "pattern": r"^(?:/.+|~/.+|[^/\\]+)$",
                "description": (
                    "Exact destination path or one basename kept beside the resolved source. "
                    "If the instruction supplies only a new name, pass that name unchanged."
                ),
            },
            "source_query": {
                **NONEMPTY_STRING,
                "pattern": r"^[^/\\]+$",
                "description": "Compatibility basename form for source.",
            },
            "new_name": {
                **NONEMPTY_STRING,
                "pattern": r"^[^/\\]+$",
                "description": "Compatibility basename form for destination.",
            },
            "search_roots": {
                "type": "array",
                "maxItems": 8,
                "uniqueItems": True,
                "items": {**NONEMPTY_STRING, "pattern": r"^(?:/.*|~/.*|~$)"},
                "description": "Optional absolute roots used to resolve a basename source.",
            },
            "replace": {
                "type": "boolean",
                "description": "Replace an existing destination only when explicitly true; defaults to false.",
            },
        },
        "oneOf": [
            {"required": ["source", "destination"]},
            {"required": ["source_query", "new_name"]},
        ],
        "additionalProperties": False,
    },
    "filesystem.find": {
        "description": (
            "Find local files or directories under the model-selected roots using basename "
            "patterns. Use this to discover an existing file path before opening, reading "
            "or processing it. This searches the filesystem directly and does not require "
            "an active application workspace. Never use illustrative placeholders such as "
            "'/path/to/your/folder'; when an instruction refers to a supplied or provided "
            "folder without naming its path, start with ~/Desktop and adjust the roots "
            "after a zero-match result."
        ),
        "properties": {
            "roots": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "uniqueItems": True,
                "items": {
                    **NONEMPTY_STRING,
                    "pattern": "^(?:/.*|~/.*|~$)",
                },
                "description": (
                "Directories to search, selected explicitly by the model. Paths may be "
                "absolute or begin with ~/. When the instruction names Desktop, Documents, "
                "or Downloads, pass that directory, for example ~/Desktop. Use ~/ to search "
                "the active user's home directory and recursive=true when the desired file "
                "may be below it. Do not send a placeholder path; use ~/Desktop when the "
                "provided folder has no more specific path."
                ),
            },
            "name_patterns": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "uniqueItems": True,
                "items": {
                    **NONEMPTY_STRING,
                    "description": (
                        "One basename glob, for example report* or *.pdf. Brace expansion "
                        "is not supported; use separate patterns for different extensions."
                    ),
                },
                "description": "One or more basename globs; a path matches when any glob matches.",
            },
            "kind": {
                "type": "string",
                "enum": ["file", "directory", "any"],
                "description": (
                    "Return files, directories, or both; defaults to file. If the requested "
                    "object is described as a directory or folder, set kind='directory' "
                    "explicitly; do not rely on the file default."
                ),
            },
            "recursive": {
                "type": "boolean",
                "description": (
                    "Search below each root; defaults to true. With recursive=false, only entries "
                    "directly inside each selected root are inspected, so an omitted home root does "
                    "not inspect files inside Desktop, Documents, or Downloads. After a zero-match "
                    "result, change roots, recursion, or basename globs before retrying."
                ),
            },
            "max_depth": {
                "type": "integer",
                "minimum": 1,
                "maximum": 8,
                "description": "Maximum levels below each root; defaults to 4.",
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Include entries whose basename begins with a dot; defaults to false.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Maximum sorted matches returned; defaults to 50.",
            },
        },
        "required": ["roots", "name_patterns"],
    },
    "filesystem.set_permissions": {
        "description": (
            "Set the Unix permission mode on exactly one model-selected regular file. Use "
            "filesystem.find first when its exact path is unknown. Directories and symbolic "
            "links are rejected."
        ),
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "pattern": NON_ROOT_LOCAL_PATH_PATTERN,
                "description": "Exact absolute or ~/ path of one existing regular file.",
            },
            "mode": {
                "type": "string",
                "pattern": "^[0-7]{3,4}$",
                "description": (
                    "Unix permission digits selected from the instruction, as a quoted octal string "
                    "such as 644, 0600, or 0755. Do not convert the digits to decimal."
                ),
            },
        },
        "required": ["path", "mode"],
        "additionalProperties": False,
    },
    "desktop.open_path": {
        "properties": {
            "path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Existing absolute path or ~/ path to open with the registered desktop application. "
                    "Use filesystem.find first when the path is unknown."
                ),
            },
            "wait_seconds": {
                "type": "number",
                "minimum": 0,
                "maximum": 10,
                "description": "Optional bounded wait after launch so the opened window can render.",
            },
        },
        "required": ["path"],
    },
    "desktop.set_setting": {
        "description": (
            "Set one scalar GSettings value and read it back. For read-only discovery, use "
            "command.run with gsettings list-schemas or gsettings list-relocatable-schemas. "
            "Read a value with gsettings get SCHEMA[:PATH] KEY, or its accepted type/range "
            "with gsettings range SCHEMA[:PATH] KEY. For a relocatable schema, first obtain "
            "the concrete instance path from the owning registry, then use the combined "
            "SCHEMA:/instance/path/ form for list-keys/get/range/set; never guess a bare "
            "relocatable schema or key. Each argv element is a separate string."
        ),
        "properties": {
            "schema": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact GSettings schema identifier. For relocatable (per-instance) settings, "
                    "use SCHEMA:/instance/path/ with the instance path observed from application "
                    "configuration. This is a settings path, not a filesystem path; a bare "
                    "relocatable schema does not identify an instance."
                ),
            },
            "key": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact key listed by gsettings list-keys SCHEMA[:PATH]. No such key means "
                    "the selected schema has no key by that name; the setting may belong to a "
                    "different schema. Inspect the keys instead of guessing another name."
                ),
            },
            "value": {
                "description": (
                    "Scalar GSettings value selected by the model. Strings are quoted by the "
                    "Adapter; booleans and numbers are passed using their native GVariant form."
                ),
                "anyOf": [
                    {"type": "string"},
                    {"type": "boolean"},
                    # JSON Schema's number type already includes integer values. Keeping one
                    # numeric branch avoids the overlapping integer/number oneOf failure.
                    {"type": "number"},
                ],
            },
        },
        "required": ["schema", "key", "value"],
    },
    "desktop.set_wallpaper": {
        "properties": {
            "image_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Exact absolute or ~/ path to an existing BMP, GIF, JPEG, PNG, TIFF, "
                    "or WebP image selected by the model. Sets both available GNOME light "
                    "and dark wallpaper URIs and verifies them by read-back."
                ),
            },
        },
        "required": ["image_path"],
    },
    "desktop.applications.inspect": {
        "properties": {
            "query": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional application-name or Desktop Entry ID terms used only to filter candidates. "
                    "mime_type_prefixes is required; query alone is not a complete request. "
                    "The Adapter never selects a target."
                ),
            },
            "mime_type_prefixes": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9.+-]*$",
                },
                "description": (
                    "One or more model-selected top-level MIME tokens (the part before "
                    "the slash) used to filter each candidate's public Desktop Entry "
                    "declarations. This selector is required and is never inferred from "
                    "the application name."
                ),
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum candidate Desktop Entries returned; defaults to 20.",
            },
            "mime_offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100000,
                "description": (
                    "Zero-based offset into each candidate's matching MIME declarations; "
                    "defaults to 0. Use next_mime_offset from a prior result to read the "
                    "next page."
                ),
            },
            "max_mime_types_per_application": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": (
                    "Maximum exact MIME declarations returned per candidate; defaults "
                    "to 12 so the model can copy an explicit bounded batch."
                ),
            },
        },
        "required": ["mime_type_prefixes"],
    },
    "desktop.favorites.list": {
        "description": (
            "Read a bounded page of the current GNOME favorite-apps list, preserving order "
            "and returning exact Desktop Entry IDs without selecting a mutation target."
        ),
        "properties": {
            "offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10_000,
                "description": "Zero-based favorite offset; defaults to 0.",
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "description": "Maximum favorite IDs returned; defaults to 100.",
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    "desktop.remove_favorite": {
        "description": (
            "Remove exactly one current GNOME favorite by its full Desktop Entry ID. "
            "Copy desktop_id from desktop.favorites.list; application names are not resolved."
        ),
        "properties": {
            "desktop_id": {
                **NONEMPTY_STRING,
                "pattern": "^[^/]+\\.desktop$",
                "description": "Exact favorite Desktop Entry ID returned by desktop.favorites.list.",
            },
        },
        "required": ["desktop_id"],
        "additionalProperties": False,
    },
    "desktop.mime_associations.set": {
        "properties": {
            "desktop_id": {
                **NONEMPTY_STRING,
                "pattern": "^[^/]+\\.desktop$",
                "description": (
                    "Exact installed Desktop Entry ID selected by the model, normally "
                    "copied from desktop.applications.inspect. Names are not resolved."
                ),
            },
            "mime_types": {
                "type": "array",
                "minItems": 1,
                "maxItems": 20,
                "uniqueItems": True,
                "items": {
                    "type": "string",
                    "pattern": "^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*$",
                },
                "description": (
                    "Exact MIME types selected by the model. Every type must be "
                    "advertised by desktop_id; no category expansion occurs."
                ),
            },
        },
        "required": ["desktop_id", "mime_types"],
    },
    "audio.set_volume": {
        "properties": {
            "percent": {
                "type": "number",
                "minimum": 0,
                "maximum": 150,
                "description": (
                    "Target volume percentage for the selected sink: 0% is silent; "
                    "100% is full normal volume (0 dB). Above 100% is over-amplification "
                    "and may distort sound; use it only when explicitly requested. "
                    "The 150% parameter limit is not the normal volume maximum."
                ),
            },
            "sink": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional exact PulseAudio sink name. Omit to use the current default sink."
                ),
            },
        },
        "required": ["percent"],
    },
    "text.append_each_line": {
        "properties": {
            "lines": {
                "type": "array",
                "maxItems": 10000,
                "items": NONEMPTY_STRING,
                "description": (
                    "Exact ordered line strings selected from inline text in the instruction. Preserve each "
                    "line's content and omit line-ending characters. Use input_path instead for an existing "
                    "text file. Provide exactly one of lines or input_path."
                ),
            },
            "input_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": (
                    "Existing absolute or ~/ UTF-8 text file whose lines should be transformed. Use this "
                    "instead of lines when the source is a file. Provide exactly one of lines or input_path."
                ),
            },
            "suffix": {
                **NONEMPTY_STRING,
                "maxLength": 10000,
                "description": "Exact text appended once to every input line.",
            },
            "output_path": {
                **NONEMPTY_STRING,
                "description": (
                    "Destination selected from the instruction. Basenames and relative paths are resolved "
                    "from the active terminal working directory; absolute and ~/ paths are also accepted. "
                    "The action creates missing parent directories and atomically replaces this text file."
                ),
            },
        },
        "required": ["suffix", "output_path"],
        "oneOf": [{"required": ["lines"]}, {"required": ["input_path"]}],
    },
    "terminal.default_profile.inspect": {
        "description": (
            "Read the current default GNOME Terminal profile without opening or changing a window. "
            "With no key, list available preference keys. With key, read its current value and native type/range. "
            "The Adapter resolves the live default profile; no schema, UUID, or settings path is needed."
        ),
        "properties": {
            "key": {
                **NONEMPTY_STRING,
                "description": (
                    "One native preference key to inspect, such as default-size-columns (character columns), "
                    "default-size-rows (text rows), font, or scrollback-lines. Omit to list keys."
                ),
            },
        },
        "required": [],
        "additionalProperties": False,
    },
    "terminal.default_profile.set_setting": {
        "description": (
            "Persist exactly one scalar preference in the current default GNOME Terminal profile and read it back. "
            "The Adapter resolves the live default profile. This does not resize, close, or restart existing "
            "windows. Saved defaults apply to newly opened terminals, including after reboot. "
            "Use terminal.default_profile.inspect to discover keys or inspect a value/type. "
            "Verify startup preferences in a new terminal using terminal.launch (for example, argv=[\"bash\"]); "
            "stored-value read-back does not inspect window behavior. Do not supply a geometry override "
            "when checking saved defaults."
        ),
        "properties": {
            "key": {
                **NONEMPTY_STRING,
                "description": (
                    "One exact native preference key. default-size-columns counts character columns; "
                    "default-size-rows counts text rows. Select each requested preference separately."
                ),
            },
            "value": {
                "description": "One model-selected scalar value. Strings, booleans, and numbers retain their native types.",
                "anyOf": [{"type": "string"}, {"type": "boolean"}, {"type": "number"}],
            },
        },
        "required": ["key", "value"],
        "additionalProperties": False,
    },
    "terminal.launch": {
        "description": (
            "Use for launching an application in a visible GNOME Terminal when the child should keep running. "
            "Success verifies the terminal launch only, not the child exit status or any output file. "
            "Use command.run for a finite command and terminal.show_output when the visible transcript matters."
        ),
        "properties": {
            "argv": {
                "type": "array",
                "minItems": 1,
                "items": NONEMPTY_STRING,
                "description": (
                    "Application command and arguments as separate strings. The exact argv is launched in a "
                    "visible GNOME Terminal so the child process inherits a TTY; shell parsing is not used."
                    " Tilde paths and environment variables are not expanded. Use absolute file paths or paths "
                    "relative to the selected working directory."
                ),
            },
            "cwd": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional absolute terminal working directory; relative values are resolved from the "
                    "Adapter process directory and should not be used. Defaults to the user's home."
                ),
            },
            "record_shell_history": {
                "type": "boolean",
                "description": "Optionally record the launched command in the active user's shell history.",
            },
        },
        "required": ["argv"],
    },
    "terminal.show_output": {
        "description": (
            "Run one finite model-selected command in a visible GNOME Terminal, wait for its real "
            "exit status, and leave the command and combined standard output/error visible. This "
            "does not require the output value in advance and does not interpret shell syntax. "
                "When the instruction names an explicit working directory, copy that complete absolute "
                "path exactly into cwd_path; never shorten it to a parent or root directory."
                " When a pipeline, conditional, or other shell syntax is required, select argv=[\"bash\", "
                "\"-c\", <one complete model-authored script>] so the script is the single third argument; "
                "do not place standalone shell operators such as |, >, or && in separate argv items."
            ),
        "properties": {
            "argv": {
                "type": "array",
                "minItems": 1,
                "items": NONEMPTY_STRING,
                "description": (
                    "Finite command and arguments as separate strings: one command word or argument per item. "
                    "Shell parsing is not used, so do not add shell quotes or escapes. "
                    "Tilde paths and environment variables are not expanded. Use absolute file paths or paths "
                    "relative to the selected working directory. "
                    "Wildcards such as *.txt stay literal: select bash -c for shell expansion, or pass "
                    "a pattern to a program that interprets it, such as find -name. "
                    "Do not include >, >>, |, "
                    "||, &&, or ; as shell operators; they are rejected. "
                    "A ; terminating find's -exec, -execdir, -ok, or -okdir is a native argument "
                    "and is accepted without shell quoting."
                    + _PYTHON_SCRIPT_ARGUMENT_GUIDANCE
                ),
            },
            "cwd_source": {
                "type": "string",
                "enum": ["active_context", "active_terminal", "home", "explicit"],
                "description": (
                    "How to resolve the command working directory. Use active_context for the folder "
                    "currently focused in Files or an active terminal, active_terminal only when an "
                    "existing shell is already visible, home for the active user's home, or explicit "
                    "only with cwd_path."
                ),
            },
            "cwd_path": {
                **NONEMPTY_STRING,
                "pattern": "^/.*",
                "description": (
                    "Complete absolute working-directory path used only when cwd_source is explicit. "
                    "Copy every path segment exactly from the instruction: for example, an instruction "
                    "that names /srv/team/project requires cwd_path=/srv/team/project, never /srv or /. "
                    "Omit cwd_path for active_context, active_terminal, and home."
                ),
            },
            "expected_returncodes": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": -255, "maximum": 255},
                "description": "Accepted process return codes; defaults to [0].",
            },
            "provenance": {
                "type": "string",
                "enum": ["none", "shell_history"],
                "description": (
                    "Use shell_history when the instruction explicitly requires terminal or "
                    "command-line execution; use none otherwise. The exact model-selected argv is "
                    "recorded only for shell_history."
                ),
            },
        },
        "required": ["argv", "cwd_source", "provenance"],
    },
    "window.capture": {
        "description": (
            "Save a PNG of exactly one desktop window selected by a title substring. This action "
            "only captures the existing window: it does not execute commands, launch applications, "
            "or choose a title on the model's behalf."
        ),
        "properties": {
            "title_contains": {
                **NONEMPTY_STRING,
                "maxLength": 256,
                "description": (
                    "Title substring selected by the model from an observed window or a preceding "
                    "tool result. The call fails when zero or multiple windows match."
                ),
            },
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).+\\.[pP][nN][gG]$",
                "description": (
                    "Absolute or ~/ PNG destination selected by the model. The parent directory "
                    "must already exist."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "description": "Replace an existing PNG only when explicitly true; defaults to false.",
            },
        },
        "required": ["title_contains", "output_path"],
        "additionalProperties": False,
    },
    "document.convert": {
        "description": (
            "Convert exactly one model-selected local document to exactly one output path. "
            "The destination extension selects the LibreOffice format. Use filesystem.find "
            "first when the source is unknown, and filesystem.create_directory first when the "
            "destination parent is absent. Use command.run instead when the user explicitly "
            "requires a command-line invocation or shell-history provenance."
        ),
        "properties": {
            "source": {
                **NONEMPTY_STRING,
                "pattern": NON_ROOT_LOCAL_PATH_PATTERN,
                "description": (
                    "Exact absolute or ~/ path of one existing input file selected by the model."
                ),
            },
            "destination": {
                **NONEMPTY_STRING,
                "pattern": NON_ROOT_LOCAL_PATH_PATTERN,
                "description": (
                    "Exact absolute or ~/ output file path. Its extension must be pdf, docx, "
                    "odt, xlsx, ods, pptx, odp, csv, txt, or html."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "description": "Replace an existing destination only when explicitly true; defaults to false.",
            },
        },
        "required": ["source", "destination"],
        "additionalProperties": False,
    },
    "archive.create_zip": {
        "description": (
            "Create exactly one ZIP from the model-selected input_paths. This action only creates "
            "archives; use archive.extract_zip to unpack one."
        ),
        "properties": _ARCHIVE_CREATE_PROPERTIES,
        "required": ["archive_path", "input_paths"],
        "additionalProperties": False,
    },
    "archive.extract_zip": {
        "description": (
            "Extract exactly one existing ZIP into the model-selected destination_directory. "
            "This action only extracts archives; use archive.create_zip to create one."
        ),
        "properties": _ARCHIVE_EXTRACT_PROPERTIES,
        "required": ["archive_path", "destination_directory"],
        "additionalProperties": False,
    },
    "archive.compress_file": {
        "description": (
            "Gzip-compress exactly one observed regular file to one explicit .gz output. The "
            "model selects both paths and whether the source is removed; the Adapter performs no "
            "file discovery, age classification, grouping, or destination naming."
        ),
        "properties": {
            "source": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).*",
                "description": "Exact existing regular-file path selected by the model.",
            },
            "destination": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/).+\\.[gG][zZ]$",
                "description": "Exact gzip output path, including the .gz suffix.",
            },
            "remove_source": {
                "type": "boolean",
                "description": "Remove the source after verified compression only when explicitly true.",
            },
            "overwrite": {
                "type": "boolean",
                "description": "Replace an existing destination only when explicitly true; defaults to false.",
            },
        },
        "required": ["source", "destination", "remove_source"],
        "additionalProperties": False,
    },
    "pdf.tables.inspect": {
        "description": (
            "Read one detected table from one page of a PDF as aligned rows and columns. "
            "Preserves merged cells, multirow headers, empty cells and multiline cell text. "
            "Use this for tabular data when plain PDF text loses column alignment. "
            "It does not interpret labels, calculate values or modify files. "
            "Scanned images without native table text may yield no table."
        ),
        "properties": {
            "input_path": {**_PDF_FORM_PATH, "description": "Exact existing local PDF path: absolute, ~/ or file URI."},
            "page": {"type": "integer", "minimum": 1, "maximum": 100_000, "description": "One-based page number; defaults to 1."},
            "table_index": {"type": "integer", "minimum": 0, "maximum": 100_000, "description": "Zero-based detected table on this page; defaults to 0. table_count reports how many exist."},
            "row_offset": {"type": "integer", "minimum": 0, "maximum": 100_000, "description": "Zero-based first table row; defaults to 0, including all header rows. Use next_row_offset for a later window."},
            "max_rows": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Maximum complete rows returned; defaults to 40. Columns are never sampled. Read smaller windows if context_truncated is true."},
        },
        "required": ["input_path"],
        "additionalProperties": False,
    },
    "pdf.form.inspect": {
        "description": (
            "Read the existing PDF's AcroForm fields, their exact field_name, labels, "
            "types and current values. This reads fillable fields, not just page text. "
            "Use filesystem.find to locate an unknown PDF path."
        ),
        "properties": {
            "input_path": {**_PDF_FORM_PATH, "description": "Exact existing PDF path or local file URI."},
            "field_offset": {"type": "integer", "minimum": 0, "maximum": 1000000, "description": "Zero-based field offset; defaults to 0. Use next_offset when truncated is true."},
            "max_fields": {"type": "integer", "minimum": 1, "maximum": 256, "description": "Maximum fields returned; defaults to 128."},
        },
        "required": ["input_path"],
        "additionalProperties": False,
    },
    "pdf.form.fill": {
        "description": (
            "Fill explicitly selected text fields in one PDF and save one output PDF, "
            "preserving its layout and unselected fields. First use pdf.form.inspect "
            "to read exact field_name values and writable flags. Select the value for "
            "each field yourself from the requested source data. One call creates one "
            "document; it does not read a spreadsheet, choose field mappings or name outputs."
        ),
        "properties": {
            "input_path": {**_PDF_FORM_PATH, "description": "Exact existing PDF form to copy and fill."},
            "output_path": {**_PDF_FORM_PATH, "description": "Exact new PDF filename selected by the model; must differ from input_path. Missing parent directories are created."},
            "fields": {
                "type": "array", "minItems": 1, "maxItems": 128,
                "description": "Explicit field/value pairs for this one output. Send each field_name once; omitted fields stay unchanged. Only writable /Tx fields are supported.",
                "items": {
                    "type": "object",
                    "properties": {
                        "field_name": {**NONEMPTY_STRING, "description": "Exact full field_name returned by pdf.form.inspect; keep spaces and punctuation."},
                        "value": {"type": "string", "description": "Literal text to insert, including any requested mark or date formatting. Empty string clears the selected field."},
                    },
                    "required": ["field_name", "value"],
                    "additionalProperties": False,
                },
            },
            "overwrite": {"type": "boolean", "description": "Replace the exact output only if true; defaults to false."},
        },
        "required": ["input_path", "output_path", "fields"],
        "additionalProperties": False,
    },
    "pdf.outline.inspect": {
        "properties": {
            "input_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file://(?:localhost)?/).+\\.[pP][dD][fF]$",
                "description": (
                    "Exact local path of the existing PDF to inspect, expressed as an absolute "
                    "path, ~/ path, /~/ home alias, or local file URI. Percent escapes are "
                    "decoded once. The action reads the PDF's own outline/bookmarks and "
                    "never creates, names, or modifies an output file."
                ),
            },
            "outline_level": {
                "type": "integer",
                "minimum": 1,
                "maximum": 32,
                "description": (
                    "One-based bookmark depth selected by the model. Returned sections "
                    "contain exact inclusive start_page and end_page values."
                ),
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100000,
                "description": "Zero-based section offset for pagination; defaults to 0.",
            },
            "max_sections": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": (
                    "Maximum section records returned in this read-only page; defaults to 20. "
                    "Use next_offset to request another page when truncated is true."
                ),
            },
        },
        "required": ["input_path", "outline_level"],
    },
    "pdf.pages.extract": {
        "properties": {
            "input_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file://(?:localhost)?/).+\\.[pP][dD][fF]$",
                "description": "Exact existing source PDF selected by the model.",
            },
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": "^(?:/|~/|file://(?:localhost)?/).+\\.[pP][dD][fF]$",
                "description": (
                    "Exact destination PDF path selected and named by the model. The action "
                    "creates at most this one output and creates missing parent directories."
                ),
            },
            "start_page": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": "First source page to export, one-based and inclusive.",
            },
            "end_page": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1_000_000,
                "description": "Last source page to export, one-based and inclusive.",
            },
            "overwrite": {
                "type": "boolean",
                "description": (
                    "Explicitly select whether to replace the exact output_path. Existing files "
                    "are never interpreted as examples and are never silently reused."
                ),
            },
            "output_backend": {
                "type": "string",
                "enum": ["preserve_pages", "cairo"],
                "description": (
                    "Explicit model-selected writing backend. preserve_pages copies "
                    "source page objects, while cairo reproduces the selected range with pdftocairo."
                ),
            },
        },
        "required": [
            "input_path",
            "output_path",
            "start_page",
            "end_page",
            "overwrite",
            "output_backend",
        ],
    },
    "pdf.extract_text_batch": {
        "description": (
            "Read text from matching PDF documents without modifying them. Choose a page "
            "range and text window; the response reports any remaining source text. "
            "For a later window, select one observed filename and its next_start_char. "
            "Text is returned as it appears in the document, not interpreted or summarized. "
            "Use pdf.tables.inspect for cell boundaries and merged table headers."
        ),
        "properties": {
            "input_pattern": {
                **NONEMPTY_STRING,
                "description": (
                    "PDF filename or basename glob matched inside the selected directory, for example "
                    "*.pdf or paper-*.pdf. The action reads matching PDFs without changing them."
                ),
            },
            "cwd_source": {
                "type": "string",
                "enum": ["active_terminal", "home", "explicit"],
                "description": (
                    "Directory containing the PDFs. Use active_terminal for the current visible terminal, "
                    "home for files directly in the active user's home, or explicit only with cwd_path. "
                    "If home has no direct match, NO_MATCHES returns bounded suggested subdirectories "
                    "discovered from the current filesystem for an explicit retry."
                ),
            },
            "cwd_path": {
                **NONEMPTY_STRING,
                "pattern": "^/.*",
                "description": (
                    "Absolute PDF directory used only when cwd_source is explicit. Omit it for "
                    "active_terminal and home."
                ),
            },
            "start_page": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100_000,
                "description": "First one-based page to extract; defaults to page 1.",
            },
            "page_count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100_000,
                "description": (
                    "Number of pages to extract from each PDF. Omit to read from start_page through the end."
                ),
            },
            "max_chars_per_file": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20_000,
                "description": (
                    "Maximum characters returned from start_char in each PDF extraction; "
                    "defaults to 8000. A truncated window is not the whole document. Use "
                    "next_start_char with one observed filename to read a later window."
                ),
            },
            "start_char": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100_000_000,
                "description": (
                    "Zero-based offset in the extracted text after any layout compaction. "
                    "Use the exact observed file basename and a prior file's next_start_char "
                    "to request the next window; omit for the first window."
                ),
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Include hidden matching PDF files; defaults to false.",
            },
            "preserve_layout": {
                "type": "boolean",
                "description": (
                    "Preserve the source page's approximate physical text layout; defaults to true so "
                    "columns and tables remain aligned. Set false for prose when compact reading order "
                    "is more useful."
                ),
            },
        },
        "required": ["input_pattern", "cwd_source"],
    },
    "image.extract_text_batch": {
        "properties": {
            "input_pattern": {
                **NONEMPTY_STRING,
                "description": (
                    "Image or PDF filename/basename glob matched inside the selected directory, for "
                    "example *.png, scan-*.jpg, or supplied-*. The action performs read-only OCR on "
                    "matching PNG, JPEG, TIFF, BMP, WebP, and PDF files. Use one basename glob "
                    "such as receipt_*; do not send paths or a list of path objects."
                ),
            },
            "cwd_source": {
                "type": "string",
                "enum": ["active_terminal", "home", "explicit"],
                "description": (
                    "Directory containing the images or scanned PDFs. Use active_terminal for the current "
                    "visible terminal, home for files directly in the active user's home, or explicit only "
                    "with cwd_path. A no-match response supplies bounded candidate directories when found. "
                    "For a known Desktop directory, use cwd_source=explicit with cwd_path=/home/user/Desktop."
                ),
            },
            "cwd_path": {
                **NONEMPTY_STRING,
                "pattern": "^/.*",
                "description": (
                    "Absolute input directory used only when cwd_source is explicit. Omit it for "
                    "active_terminal and home."
                ),
            },
            "max_chars_per_file": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20_000,
                "description": (
                    "Maximum OCR text characters returned from each file; defaults to 8000."
                ),
            },
            "max_files": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 50,
                "description": (
                    "Maximum number of matching files to inspect; defaults to 50. "
                    "The action rejects a larger match set instead of choosing a subset."
                ),
            },
            "start_char": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100_000_000,
                "description": (
                    "Zero-based offset in the extracted OCR text. Use the exact observed "
                    "file basename and next_start_char from a prior result to continue; "
                    "omit for the first window."
                ),
            },
            "max_pages_per_pdf": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": (
                    "Maximum pages rendered and read from each PDF; defaults to 8. Ignored for images."
                ),
            },
            "include_hidden": {
                "type": "boolean",
                "description": "Include hidden matching files; defaults to false.",
            },
        },
        "required": ["input_pattern", "cwd_source"],
    },
    "command.run": {
            "description": (
                "Use for one finite command whose exit status or captured output must be verified. "
                "To save its standard output, set stdout_path alongside argv; omitting it returns text without "
                "saving a file. For example, argv=[\"uname\", \"-a\"] with stdout_path=\"/tmp/system.txt\" "
                "saves that command's output. "
                "When a pipeline, conditional, or other shell syntax is required, select argv=[\"bash\", "
                "\"-c\", <one complete model-authored script>] so the script is the single third argument; "
                "do not place standalone shell operators such as |, >, or && in separate argv items. "
                "For a long-running GUI launch, set terminal=true; for a visible terminal transcript, use "
            "terminal.show_output instead. A nonzero result includes the real stderr/stdout; "
            "use that error to correct the model-selected argv rather than repeating an unchanged command."
        ),
        "properties": {
            "argv": {
                "type": "array",
                "minItems": 1,
                "items": NONEMPTY_STRING,
                "description": (
                    "Command and arguments as separate strings; shell parsing is not used. "
                    "Use one command word or argument per item and do not add shell quotes or escapes. "
                    "Tilde paths and environment variables are not expanded. Use absolute file paths or paths "
                    "relative to the selected working directory. "
                    "Wildcards such as *.txt stay literal: select bash -c for shell expansion, or pass "
                    "a pattern to a program that interprets it, such as find -name. "
                    "A ; terminating find's -exec, -execdir, -ok, or -okdir is a native argument "
                    "and is accepted without shell quoting. "
                    "An attached >file argument is literal text, not redirection; use stdout_path instead."
                    + _PYTHON_SCRIPT_ARGUMENT_GUIDANCE
                ),
            },
            "cwd_source": {
                "type": "string",
                "enum": ["active_terminal", "home", "explicit"],
                "description": (
                    "How to resolve the command working directory. Use active_terminal for the current "
                    "visible terminal, home for the active user's home, or explicit only with cwd_path. "
                    "This selects a directory only; active_terminal does not run the command in a terminal. "
                    "Select terminal=true separately for a visible-terminal GUI launch."
                ),
            },
            "cwd_path": {
                **NONEMPTY_STRING,
                "pattern": "^/.*",
                "description": (
                    "Absolute working directory used only when cwd_source is explicit. Omit it for "
                    "active_terminal and home."
                ),
            },
            "input": {"type": "string", "description": "Optional standard input."},
            "expected_returncodes": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": -255, "maximum": 255},
                "description": "Accepted process return codes; defaults to [0].",
            },
            "stdout_path": {
                **NONEMPTY_STRING,
                "description": (
                    "Optional destination file for the command's complete standard output. Use this instead "
                    "of putting shell redirection tokens such as > or >> inside argv. "
                    "Unlike argv items, a leading ~/ here expands to the user's home. "
                    "Relative paths are resolved from the selected command working directory (cwd_source/cwd_path). "
                    "The parent directory must already exist. stdout_path must be distinct from every existing "
                    "input file named in argv; redirecting output onto an input would truncate it."
                ),
            },
            "append_stdout": {
                "type": "boolean",
                "description": (
                    "Append standard output to stdout_path like shell >>. Defaults to false, which replaces "
                    "the destination like shell >. Valid only together with stdout_path."
                ),
            },
            "stdout_contains": {
                "type": "array",
                "items": NONEMPTY_STRING,
            },
            "stdout_excludes": {
                "type": "array",
                "items": NONEMPTY_STRING,
            },
            "stderr_contains": {
                "type": "array",
                "items": NONEMPTY_STRING,
            },
            "stderr_excludes": {
                "type": "array",
                "items": NONEMPTY_STRING,
            },
            "provenance": {
                "type": "string",
                "enum": ["none", "shell_history"],
                "description": (
                    "Explicit command provenance policy. Use shell_history when the instruction requires "
                    "command-line or terminal execution; use none otherwise. The Adapter records the exact "
                    "model-selected argv only for shell_history. Recording shell history does not give the "
                    "process a terminal; select terminal=true separately for a visible-terminal GUI launch. "
                    "The Runner never infers this value."
                ),
            },
            "terminal": {
                "type": "boolean",
                "description": (
                    "Set true when launching a long-running GUI application such as GIMP, LibreOffice, "
                    "or VLC from a visible GNOME Terminal. Without terminal=true, command.run waits for the "
                    "process to exit and a GUI application will usually time out. This mode "
                    "returns after a verified launch and does not capture the child command's output or final "
                    "exit status. Omit input, stdout_path, and stdout/stderr assertions in terminal mode."
                ),
            },
        },
        "required": ["argv", "cwd_source", "provenance"],
    },
    "desktop.set_dim_inactive": {
        "description": (
            "Persist exactly one desktop inactivity setting. Use this action for either the idle delay or the dimming toggle, not both together. "
            "For a separate delay or dimming change, call desktop.set_setting directly with the exact GNOME key."
        ),
        "required": [],
        "properties": {
            "idle_dim": {
                "type": "boolean",
                "description": "Whether GNOME dims the screen while the desktop is inactive.",
            },
            "idle_delay": {
                "type": "integer",
                "minimum": 0,
                "maximum": 4294967295,
                "description": "Optional blank-screen delay in seconds. Select either this value or idle_dim, not both.",
            },
        },
        "oneOf": [
            {"required": ["idle_dim"], "not": {"required": ["idle_delay"]}},
            {"required": ["idle_delay"], "not": {"required": ["idle_dim"]}},
        ],
        "additionalProperties": False,
    },
    "desktop.set_accessibility_scale": {
        "description": (
            "Set the GNOME text scaling factor in one setting update. "
            "For screen magnification, use separate desktop.set_setting calls for "
            "screen-magnifier-enabled and mag-factor."
        ),
        "properties": {
            "text_factor": {
                "type": "number",
                "minimum": 0.5,
                "maximum": 3.0,
                "description": (
                    "GNOME desktop text scaling factor selected by the model. 1.0 is normal size; choose a "
                    "value greater than 1.0 when the user requests larger on-screen text."
                ),
            },
        },
        "required": ["text_factor"],
        "additionalProperties": False,
    },
    "system.set_timezone": {
        "properties": {
            "timezone": {
                **NONEMPTY_STRING,
                "description": (
                    "Standard system zoneinfo identifier selected from the instruction, such as UTC, "
                    "Europe/Berlin, Asia/Tokyo, or America/New_York. Use UTC for a requested zero-offset "
                    "UTC+0/GMT+0 time zone."
                ),
            },
        },
        "required": ["timezone"],
    },
}
