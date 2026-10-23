from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from typing import Any

from calc_adapter.schema import PIVOT_DESTINATION_SCHEMA
from calc_adapter.tool_manifest import (
    PIVOT_DATA_FIELD as CALC_PIVOT_DATA_FIELD,
    STRICT_ACTION_PARAM_SCHEMAS as CALC_STRICT_ACTION_PARAM_SCHEMAS,
)
from chrome_adapter.schema import (
    TARGET_REQUIRED_ACTIONS as CHROME_TARGET_REQUIRED_ACTIONS,
)
from gimp_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as GIMP_STRICT_ACTION_PARAM_SCHEMAS,
)
from impress_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as IMPRESS_STRICT_ACTION_PARAM_SCHEMAS,
)
from thunderbird_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as THUNDERBIRD_STRICT_ACTION_PARAM_SCHEMAS,
)
from vscode_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as VSCODE_STRICT_ACTION_PARAM_SCHEMAS,
)
from vlc_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as VLC_STRICT_ACTION_PARAM_SCHEMAS,
)
from writer_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as WRITER_STRICT_ACTION_PARAM_SCHEMAS,
)
from multi_apps_adapter.tool_manifest import (
    DOWNSTREAM_ADAPTER_DOMAINS,
    STRICT_ACTION_PARAM_SCHEMAS as MULTI_APPS_STRICT_ACTION_PARAM_SCHEMAS,
)
from integrations.openapa_osworld.tool_catalog import action_signature, public_actions
from os_adapter.tool_manifest import (
    STRICT_ACTION_PARAM_SCHEMAS as OS_STRICT_ACTION_PARAM_SCHEMAS,
)
from .completion_policy import COMPLETION_ARGUMENT_SCHEMA
from .gui_actions import GUI_ACTION_SCHEMA, GUI_REQUEST_SCHEMA
from . import impress_page_number, impress_table_row
from .impress_colors import model_color_schema
from .impress_tool_routing import suppress_whole_slide_move
from .local_file_discovery import requires_local_input_discovery
from .semantic_search_scope import scope_semantic_search_actions
from .workspace_file_semantics import requests_active_workspace_files


FORBIDDEN_TASK_ROUTE_ACTIONS = frozenset({"task.execute", "task.inspect"})
FORBIDDEN_DATASET_ACTIONS = frozenset(
    {
        *FORBIDDEN_TASK_ROUTE_ACTIONS,
        "artifact.materialize",
        # This route reads authoritative answer markers and is not a generic
        # desktop operation.  Keep it out of strict search, ranking, and
        # execution surfaces even when a legacy manifest still contains it.
        "assessment.grade_multiple_choice_documents",
    }
)
INSPECT_ACTIONS = {
    "libreoffice_calc": ("workbook.inspect", "range.read"),
    "libreoffice_impress": ("presentation.inspect",),
    "libreoffice_writer": ("document.inspect",),
    "chrome": ("browser.inspect", "page.snapshot"),
    "gimp": ("image.inspect",),
    "vs_code": ("workspace.inspect",),
    "vlc": ("playback.status",),
    "multi_apps": (),
}

SAVE_ACTIONS = {
    "libreoffice_calc": ("workbook.save",),
    "libreoffice_impress": ("presentation.save",),
    "libreoffice_writer": ("document.save",),
    "gimp": ("image.export",),
}

SYNONYMS = {
    "pivot": {"pivot", "data", "table", "透视", "数据透视"},
    "chart": {"chart", "graph", "plot", "图表"},
    "format": {
        "format", "font", "color", "bold", "style",
        "highlight", "highlighting", "background", "格式", "字体", "颜色",
    },
    "write": {
        "write",
        "replace",
        "edit",
        "enter",
        "insert",
        "写",
        "替换",
        "编辑",
        "插入",
    },
    "read": {"read", "inspect", "query", "find", "检查", "读取", "查找"},
    "save": {"save", "export", "保存", "导出"},
    "slide": {"slide", "presentation", "deck", "impress", "幻灯片", "演示文稿"},
    "shape": {"shape", "text", "textbox", "image", "形状", "文本", "图片"},
    "notes": {
        "comment",
        "comments",
        "note",
        "notes",
        "presenter",
        "remark",
        "remarks",
        "speaker",
    },
    "range": {
        "range",
        "cell",
        "row",
        "column",
        "sheet",
        "单元格",
        "行",
        "列",
        "工作表",
    },
    "bookmark": {"bookmark", "favorite", "收藏"},
    "tab": {"tab", "browser", "page", "标签", "浏览器", "网页"},
    "file": {"file", "folder", "path", "archive", "文件", "目录", "路径", "压缩"},
    "notifications": {
        "notification",
        "notifications",
        "banner",
        "banners",
        "disturb",
        "quiet",
    },
    "mail": {
        "mail",
        "email",
        "signature",
        "reply",
        "quote",
        "quoting",
        "filter",
        "filters",
        "subfolder",
        "subfolders",
        "unified",
        "inbox",
        "dark",
        "theme",
    },
}

ROUTING_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "or",
    "the",
    "to",
    "with",
}

DOMAIN_CONTEXT_TOKENS = {
    "libreoffice_calc": {"calc", "libreoffice"},
    "libreoffice_impress": {"impress", "libreoffice"},
    "libreoffice_writer": {"libreoffice", "writer"},
}

VISUAL_IMAGE_TOKENS = frozenset(
    {
        "bmp", "gif", "image", "images", "jpeg", "jpg", "ora", "photo",
        "photos", "picture", "pictures", "png", "psd", "svg", "tif", "tiff",
        "webp", "xcf",
    }
)
VISUAL_IDENTIFICATION_TOKENS = frozenset(
    {"classify", "identify", "recognise", "recognize"}
)
VISUAL_RENAME_TOKENS = frozenset(
    {
        "change", "filename", "filenames", "modify", "name", "names",
        "rename", "renamed", "renaming", "update",
    }
)
FILE_ORGANIZATION_TOKENS = frozenset(
    {"directory", "directories", "file", "files", "folder", "folders"}
)
FILE_ORGANIZATION_ACTION_TOKENS = frozenset(
    {"move", "moved", "organize", "organized", "organization", "relocate", "rename", "renaming"}
)
AGE_ORGANIZATION_TOKENS = frozenset(
    {
        "age",
        "days",
        "modified",
        "modification",
        "older",
        "old",
        "recent",
        "recently",
    }
)
AGE_ORGANIZATION_ACTION_TOKENS = frozenset(
    {"archive", "compress", "compressed", "move", "moved", "organize", "relocate"}
)

COMMAND_INTENT_TOKENS = {
    "bash",
    "cli",
    "command",
    "commandline",
    "console",
    "git",
    "powershell",
    "shell",
    "terminal",
}

# Keep generic command discovery useful for common archive and text-processing
# verbs.  These are only retrieval synonyms; command.run still receives the
# complete model-selected argv and never infers or rewrites a command.

TRANSFER_INTENT_TOKENS = {
    "copy",
    "copied",
    "copying",
    "create",
    "created",
    "creating",
    "embed",
    "embedded",
    "embedding",
    "extract",
    "extracted",
    "extracting",
    "insert",
    "inserted",
    "inserting",
    "move",
    "moved",
    "moving",
    "paste",
    "pasted",
    "pasting",
    "place",
    "placed",
    "placing",
    "transfer",
    "transferred",
    "transferring",
}

ACTION_KEYWORDS = {
    ("libreoffice_impress", "master.set_page_number"): {
        "automatic",
        "color",
        "colour",
        "display",
        "field",
        "footer",
        "hide",
        "master",
        "number",
        "numbering",
        "numbers",
        "page",
        "pages",
        "show",
        "slide",
        "slides",
        "visibility",
        "visible",
    },
    ("libreoffice_calc", "sheet.create"): {
        "add",
        "create",
        "insert",
        "new",
        "sheet",
        "spreadsheet",
        "tab",
        "worksheet",
    },
    ("vs_code", "extension.install"): {
        "add",
        "extension",
        "extensions",
        "install",
        "installation",
        "local",
        "marketplace",
        "vsix",
    },
    ("vs_code", "explorer.set_exclusion"): {
        "all",
        "exclude",
        "excluded",
        "explorer",
        "file",
        "files",
        "folder",
        "folders",
        "hide",
        "hidden",
        "nested",
        "show",
        "visible",
    },
    ("vs_code", "workspace.add_folders"): {
        "add",
        "adding",
        "existing",
        "folder",
        "folders",
        "preserve",
        "workspace",
    },
    ("vs_code", "workspace.find_files"): {
        "active",
        "current",
        "discover",
        "editor",
        "file",
        "files",
        "find",
        "glob",
        "locate",
        "name",
        "named",
        "path",
        "paths",
        "pattern",
        "patterns",
        "project",
        "search",
        "workspace",
    },
    ("vs_code", "keybindings.ensure"): {
        "disable",
        "editor",
        "enable",
        "find",
        "focus",
        "hotkey",
        "keyboard",
        "keybinding",
        "keybindings",
        "shortcut",
        "terminal",
        "tree",
    },
    ("vs_code", "debugging.configure"): {
        "automatically",
        "break",
        "breakpoint",
        "console",
        "cursor",
        "debug",
        "debugger",
        "debugging",
        "editor",
        "focus",
        "focused",
        "inline",
        "ruler",
        "variables",
    },
    ("vs_code", "debug.variables.read"): {
        "array",
        "arrays",
        "debug",
        "debugger",
        "inspect",
        "numpy",
        "paused",
        "read",
        "session",
        "value",
        "values",
        "variable",
        "variables",
        "visualization",
        "visualize",
        "visualized",
    },
    ("vs_code", "debug.start"): {
        "array",
        "arrays",
        "debug",
        "debugger",
        "debugging",
        "execute",
        "f5",
        "launch",
        "run",
        "runtime",
        "session",
        "start",
        "variable",
        "variables",
        "visualize",
    },
    ("vs_code", "editor.configure"): {
        "column",
        "editor",
        "layout",
        "length",
        "line",
        "lines",
        "minimap",
        "multiple",
        "numbers",
        "scroll",
        "sticky",
        "tab",
        "tabs",
        "whitespace",
        "wrap",
        "wrapped",
        "wrapping",
    },
    ("vs_code", "editor.open_file"): {
        "current",
        "editor",
        "file",
        "open",
        "path",
        "python",
        "vscode",
    },
    ("vs_code", "ui.open_view"): {
        "array",
        "arrays",
        "debug",
        "extensions",
        "explorer",
        "numpy",
        "run",
        "search",
        "source",
        "variable",
        "variables",
        "view",
        "visualization",
        "visualize",
        "visualized",
    },
    ("vs_code", "ui.expand_section"): {
        "array",
        "arrays",
        "expand",
        "panel",
        "section",
        "variable",
        "variables",
        "view",
    },
    ("vs_code", "diagnostics.configure"): {
        "disable",
        "error",
        "errors",
        "import",
        "imports",
        "missing",
        "python",
        "report",
        "reporting",
        "severity",
        "suppress",
        "undefined",
        "unused",
        "warning",
    },
    ("vs_code", "files.configure"): {
        "auto",
        "autosave",
        "delay",
        "exit",
        "file",
        "files",
        "focus",
        "newline",
        "save",
        "trim",
        "whitespace",
        "window",
    },
    ("gimp", "image.adjust"): {
        "adjust",
        "bright",
        "brighten",
        "brighter",
        "brightness",
        "contrast",
        "dark",
        "darken",
        "darker",
        "desaturate",
        "image",
        "photo",
        "photograph",
        "picture",
        "raster",
        "saturate",
        "saturation",
    },
    ("gimp", "image.crop"): {
        "bottom",
        "crop",
        "cropped",
        "cropping",
        "edge",
        "image",
        "left",
        "percent",
        "percentage",
        "picture",
        "pixels",
        "remove",
        "right",
        "top",
        "trim",
    },
    ("libreoffice_writer", "document.export_file_pdf"): {
        "convert", "doc", "docx", "document", "export", "file", "odt",
        "pdf", "saved", "source", "writer",
    },
    ("libreoffice_writer", "document.read_file"): {
        "body",
        "content",
        "doc",
        "docx",
        "document",
        "extract",
        "file",
        "odt",
        "paragraph",
        "read",
        "rtf",
        "table",
        "text",
        "word",
        "writer",
    },
    ("libreoffice_writer", "document.extract_images"): {
        "doc",
        "docx",
        "document",
        "embedded",
        "export",
        "extract",
        "image",
        "images",
        "odt",
        "picture",
        "word",
    },
    ("os", "filesystem.find"): {
        "desktop",
        "directories",
        "directory",
        "discover",
        "document",
        "documents",
        "downloads",
        "file",
        "files",
        "find",
        "folder",
        "folders",
        "glob",
        "home",
        "local",
        "locate",
        "name",
        "named",
        "path",
        "paths",
        "pattern",
        "patterns",
        "recursive",
        "recursively",
        "saved",
        "search",
    },
    ("os", "desktop.open_path"): {
        "application",
        "default",
        "desktop",
        "doc",
        "document",
        "docx",
        "file",
        "files",
        "folder",
        "folders",
        "image",
        "local",
        "odt",
        "open",
        "opening",
        "path",
        "paths",
        "registered",
        "rtf",
        "show",
        "visible",
        "word",
        "writer",
    },
    ("os", "desktop.set_wallpaper"): {
        "background",
        "desktop",
        "image",
        "picture",
        "set",
        "wallpaper",
    },
    ("os", "desktop.applications.inspect"): {
        "app",
        "application",
        "applications",
        "association",
        "audio",
        "default",
        "desktop",
        "installed",
        "mime",
        "open",
        "player",
        "video",
        "viewer",
    },
    ("os", "desktop.mime_associations.set"): {
        "app",
        "application",
        "associate",
        "association",
        "associations",
        "audio",
        "default",
        "desktop",
        "mime",
        "set",
        "types",
        "video",
    },
    ("chrome", "extension.load_unpacked"): {
        "browser",
        "chrome",
        "directory",
        "extension",
        "folder",
        "install",
        "load",
        "local",
        "manual",
        "path",
        "unpacked",
    },
    ("os", "clipboard.set"): {
        "clipboard",
        "content",
        "copy",
        "exact",
        "paste",
        "path",
        "requested",
        "set",
        "text",
        "write",
    },
    ("os", "clipboard.get"): {
        "clipboard",
        "get",
        "paste",
        "read",
        "text",
    },
    ("libreoffice_calc", "workbook.inspect"): {
        "active",
        "calc",
        "current",
        "identity",
        "open",
        "path",
        "read",
        "ranges",
        "spreadsheet",
        "url",
        "workbook",
        "worksheet",
    },
    ("libreoffice_calc", "workbook.read_file"): {
        "calc",
        "cell",
        "display",
        "displayed",
        "extract",
        "header",
        "ods",
        "read",
        "row",
        "spreadsheet",
        "table",
        "trailing",
        "workbook",
        "xlsx",
        "zero",
        "zeros",
    },
    ("libreoffice_impress", "shape.export_image"): {
        "background",
        "embedded",
        "export",
        "extract",
        "graphic",
        "image",
        "picture",
        "save",
        "slide",
    },
    ("libreoffice_writer", "table.insert_after_text"): {
        "anchor",
        "document",
        "header",
        "heading",
        "insert",
        "paragraph",
        "report",
        "row",
        "section",
        "table",
        "values",
        "writer",
    },
    ("libreoffice_writer", "table.convert_text"): {
        "comma",
        "commas",
        "convert",
        "delimited",
        "delimiter",
        "paragraph",
        "paragraphs",
        "separated",
        "semicolon",
        "tab",
        "table",
        "text",
    },
    ("os", "command.run"): {
        "app",
        "application",
        "command",
        "commandline",
        "awk",
        "decompress",
        "default",
        "desktop",
        "git",
        "gunzip",
        "gzip",
        "json",
        "kill",
        "line",
        "lines",
        "mime",
        "parse",
        "parsing",
        "pkill",
        "player",
        "process",
        "pull",
        "push",
        "commit",
        "status",
        "shell",
        "system",
        "terminal",
        "unzip",
        "ubuntu",
        "wc",
    },
    ("os", "window.capture"): {
        "capture",
        "image",
        "png",
        "save",
        "screenshot",
        "window",
    },
    ("os", "archive.create_zip"): {
        "archive",
        "bundle",
        "compress",
        "compression",
        "create",
        "file",
        "files",
        "folder",
        "pack",
        "package",
        "zip",
    },
    ("os", "archive.extract_zip"): {
        "archive",
        "extract",
        "file",
        "files",
        "folder",
        "package",
        "unpack",
        "unzip",
        "zip",
    },
    ("os", "archive.compress_file"): {
        "age",
        "archive",
        "compress",
        "days",
        "file",
        "gzip",
        "modification",
        "modified",
        "old",
        "older",
        "single",
    },
    ("os", "filesystem.copy"): {
        "copy",
        "duplicate",
        "exact",
        "file",
        "path",
        "source",
        "destination",
    },
    ("os", "filesystem.rename"): {
        "move",
        "rename",
        "relocate",
    },
    ("os", "filesystem.copy_to_directories"): {
        "copy",
        "copies",
        "duplicate",
        "each",
        "file",
        "folder",
        "folders",
        "directories",
        "directory",
        "destinations",
        "multiple",
        "place",
        "same",
        "source",
        "targets",
    },
    ("os", "pdf.extract_text_batch"): {
        "article",
        "articles",
        "author",
        "batch",
        "content",
        "document",
        "documents",
        "extract",
        "metadata",
        "paper",
        "papers",
        "pdf",
        "read",
        "text",
    },
    ("os", "pdf.tables.inspect"): {
        "pdf", "table", "tables", "read", "inspect", "extract", "rows", "columns",
        "cells", "merged", "headers", "tabular", "layout", "alignment",
    },
    ("os", "pdf.form.inspect"): {
        "pdf", "form", "forms", "field", "fields", "fillable", "acroform",
        "inspect", "read", "template", "labels", "fill",
    },
    ("os", "pdf.form.fill"): {
        "pdf", "form", "forms", "field", "fields", "fillable", "acroform",
        "fill", "populate", "enter", "text", "template", "save",
    },
    ("os", "pdf.outline.inspect"): {
        "book",
        "bookmark",
        "bookmarks",
        "chapter",
        "chapters",
        "inspect",
        "outline",
        "pdf",
        "pdfs",
        "range",
        "ranges",
        "read",
        "section",
        "sections",
    },
    ("os", "pdf.pages.extract"): {
        "book",
        "chapter",
        "chapters",
        "divide",
        "export",
        "extract",
        "outline",
        "page",
        "pages",
        "pdf",
        "pdfs",
        "separate",
        "split",
    },
    ("os", "image.extract_text_batch"): {
        "batch",
        "content",
        "document",
        "extract",
        "image",
        "images",
        "invoice",
        "ocr",
        "pdf",
        "photo",
        "read",
        "receipt",
        "scan",
        "scanned",
        "screenshot",
        "text",
    },
    ("os", "terminal.default_profile.inspect"): {
        "terminal",
        "gnome",
        "profile",
        "preferences",
        "settings",
        "default",
        "size",
        "columns",
        "rows",
        "font",
        "scrollback",
        "inspect",
        "read",
    },
    ("os", "terminal.default_profile.set_setting"): {
        "terminal",
        "gnome",
        "profile",
        "preferences",
        "settings",
        "default",
        "size",
        "columns",
        "rows",
        "font",
        "scrollback",
        "permanent",
        "permanently",
        "reboot",
    },
    ("os", "terminal.launch"): {
        "application",
        "calc",
        "command",
        "document",
        "launch",
        "libreoffice",
        "new",
        "open",
        "process",
        "terminal",
        "tty",
        "writer",
    },
    ("os", "terminal.show_output"): {
        "command",
        "commandline",
        "count",
        "current",
        "directory",
        "display",
        "execute",
        "line",
        "lines",
        "output",
        "recursive",
        "result",
        "run",
        "shell",
        "show",
        "terminal",
        "visible",
    },
    ("vlc", "config.update"): {
        "directory",
        "folder",
        "path",
        "preference",
        "recording",
        "recordings",
        "setting",
        "store",
    },
    ("vlc", "media.extract_audio"): {
        "audio",
        "convert",
        "extract",
        "media",
        "mp3",
        "music",
        "output",
        "save",
        "song",
        "soundtrack",
        "video",
        "wav",
    },
    ("vlc", "media.extract_frame"): {
        "capture",
        "frame",
        "image",
        "photo",
        "picture",
        "screenshot",
        "snapshot",
        "still",
    },
    ("vlc", "media.transcode_clip"): {
        "animated",
        "beginning",
        "clip",
        "conversion",
        "convert",
        "duration",
        "gif",
        "media",
        "segment",
        "start",
        "time",
        "transcode",
        "trim",
        "video",
    },
    ("vlc", "media.flip_video"): {
        "correct",
        "flip",
        "flipped",
        "mirror",
        "orientation",
        "right",
        "save",
        "screen",
        "upside",
        "video",
    },
    ("vlc", "media.extract_subtitles"): {
        "caption",
        "captions",
        "embedded",
        "export",
        "extract",
        "media",
        "remove",
        "srt",
        "subtitle",
        "subtitles",
        "video",
        "vtt",
    },
    ("libreoffice_writer", "paragraph.replace_text"): {
        "blank",
        "clear",
        "delete",
        "empty",
        "line",
        "lines",
        "readability",
        "remove",
        "separate",
        "separated",
        "sentence",
        "sentences",
        "space",
        "split",
        "replace",
        "rewrite",
    },
    ("libreoffice_writer", "paragraph.clear_text"): {
        "clear", "delete", "empty", "paragraph", "paragraphs", "remove", "text",
    },
    ("libreoffice_writer", "paragraph.split"): {
        "blank",
        "break",
        "empty",
        "line",
        "paragraph",
        "separate",
        "split",
    },
    ("libreoffice_writer", "paragraph.apply_numbering"): {
        "bibliography", "citation", "citations", "continue", "list", "number",
        "numbered", "numbering", "reference", "references",
    },
    ("libreoffice_writer", "bookmark.create"): {
        "bibliography", "bookmark", "citation", "citations", "cross",
        "crossreference", "reference", "references", "source",
    },
    ("libreoffice_writer", "paragraph.set_format"): {
        "align",
        "aligned",
        "alignment",
        "crossed",
        "crossout",
        "font",
        "format",
        "formatting",
        "line",
        "out",
        "paragraph",
        "paragraphs",
        "size",
        "spacing",
        "strike",
        "strikethrough",
        "struck",
        "tab",
        "tabs",
        "tabstop",
        "tabstops",
        "decimal",
        "leader",
        "through",
    },
    ("libreoffice_writer", "text.find"): {
        "bold",
        "bookmark",
        "character",
        "characters",
        "citation",
        "cross",
        "find",
        "font",
        "format",
        "formatting",
        "italic",
        "italicized",
        "literal",
        "locate",
        "marked",
        "marker",
        "offset",
        "offsets",
        "placeholder",
        "reference",
        "references",
        "search",
        "size",
        "subscript",
        "substring",
        "superscript",
        "word",
        "words",
    },
    ("libreoffice_writer", "text.set_format"): {
        "bold",
        "character",
        "characters",
        "font",
        "format",
        "formatting",
        "italic",
        "italicized",
        "size",
        "subscript",
        "superscript",
        "word",
        "words",
    },
    ("libreoffice_writer", "text.find_replace"): {
        "change",
        "clear",
        "delete",
        "find",
        "insert",
        "literal",
        "marker",
        "placeholder",
        "remove",
        "replace",
        "substitute",
        "tab",
        "tabs",
        "tabstop",
        "tabstops",
        "text",
    },
    ("libreoffice_writer", "document.append_paragraphs"): {
        "add",
        "append",
        "bibliography",
        "citation",
        "citations",
        "end",
        "numbered",
        "paragraph",
        "paragraphs",
        "reference",
        "references",
    },
    ("libreoffice_writer", "table.read"): {
        "cell",
        "cells",
        "inspect",
        "read",
        "table",
        "values",
    },
    ("libreoffice_writer", "table.set_cell_text_color"): {
        "cell",
        "cells",
        "color",
        "colour",
        "font",
        "table",
        "text",
        "words",
    },
    ("libreoffice_impress", "slide.set_notes"): {
        "comment",
        "comments",
        "copy",
        "heading",
        "note",
        "notes",
        "presenter",
        "remark",
        "remarks",
        "speaker",
        "title",
    },
    ("thunderbird", "accounts.remove"): {
        "account",
        "accounts",
        "delete",
        "email",
        "mail",
        "remove",
        "server",
    },
    ("thunderbird", "filters.configure"): {
        "auto",
        "automatic",
        "automatically",
        "configure",
        "contains",
        "create",
        "email",
        "emails",
        "filter",
        "filters",
        "folder",
        "forward",
        "inbox",
        "local",
        "mail",
        "message",
        "messages",
        "move",
        "rule",
        "rules",
        "sender",
        "subject",
        "thunderbird",
    },
    ("thunderbird", "folders.ensure_local"): {
        "create",
        "ensure",
        "folder",
        "folders",
        "local",
        "mail",
        "new",
        "thunderbird",
    },
    ("thunderbird", "mail.identities.list"): {
        "account", "email", "identity", "identities", "signature", "reply",
        "name", "list", "inspect", "thunderbird",
    },
    ("thunderbird", "contacts.export_csv"): {
        "address",
        "addressbook",
        "book",
        "contact",
        "contacts",
        "csv",
        "export",
        "people",
        "thunderbird",
    },
    ("thunderbird", "messages.query"): {
        "attachment",
        "attachments",
        "cc",
        "date",
        "email",
        "emails",
        "extract",
        "folder",
        "get",
        "latest",
        "list",
        "mail",
        "message",
        "messages",
        "query",
        "read",
        "recipient",
        "sender",
        "subject",
        "thunderbird",
    },
    ("thunderbird", "compose.set_recipients"): {
        "email",
        "receiver",
        "recipient",
        "thunderbird",
    },
    ("thunderbird", "ui.prefill_account_setup"): {
        "account",
        "email",
        "login",
        "mail",
        "password",
        "setup",
        "sign",
    },
    ("vs_code", "file.replace_literal"): {
        "change",
        "code",
        "complete",
        "completion",
        "edit",
        "editing",
        "file",
        "files",
        "find",
        "fix",
        "literal",
        "modify",
        "modifying",
        "py",
        "python",
        "replace",
        "replacement",
        "replacing",
        "script",
        "source",
        "text",
        "todo",
    },
    ("vs_code", "file.read_text"): {
        "code",
        "complete",
        "content",
        "contents",
        "edit",
        "file",
        "files",
        "inspect",
        "json",
        "py",
        "python",
        "read",
        "script",
        "source",
        "text",
        "todo",
    },
    ("os", "notifications.configure"): {
        "desktop",
        "notification",
        "notifications",
        "banner",
        "banners",
        "disturb",
        "quiet",
    },
    ("os", "desktop.set_dim_inactive"): {
        "dim",
        "dimming",
        "inactive",
        "off",
        "on",
        "power",
        "screen",
        "setting",
    },
    ("os", "desktop.set_accessibility_scale"): {
        "accessibility",
        "bigger",
        "display",
        "enlarge",
        "font",
        "large",
        "larger",
        "magnification",
        "magnifier",
        "read",
        "readable",
        "scale",
        "screen",
        "small",
        "text",
        "vision",
        "zoom",
    },
    ("thunderbird", "mail.configure"): {
        "mail",
        "email",
        "signature",
        "reply",
        "quote",
        "quoting",
        "automatic",
        "filter",
        "filters",
        "subfolder",
        "subfolders",
        "unified",
        "inbox",
        "dark",
        "theme",
    },
    ("vlc", "preferences.configure"): {
        "vlc",
        "preference",
        "preferences",
        "hotkey",
        "shortcut",
        "volume",
        "slider",
        "minimal",
        "interface",
        "exit",
        "close",
        "instance",
        "cone",
        "splash",
        "recording",
        "recordings",
        "directory",
        "folder",
        "location",
        "path",
    },
    ("vlc", "playback.open"): {
        "audio",
        "desktop",
        "downloads",
        "file",
        "home",
        "local",
        "media",
        "movie",
        "music",
        "open",
        "play",
        "song",
        "video",
        "vlc",
    },
    ("libreoffice_writer", "document.transform_case"): {
        "capitalisation",
        "capitalise",
        "capitalization",
        "capitalize",
        "case",
        "lower",
        "lowercase",
        "titlecase",
        "uppercase",
    },
    ("libreoffice_calc", "range.fill_down"): {
        "fill",
        "down",
        "blank",
        "blanks",
        "above",
        "formula",
        "formulas",
        "propagate",
        "extend",
    },
    ("libreoffice_calc", "range.text_transform"): {
        "text",
        "trim",
        "whitespace",
        "whitespaces",
        "collapse",
        "case",
        "capitalizing",
        "capitalize",
        "title",
        "lowercase",
        "uppercase",
        "clean",
    },
    ("libreoffice_calc", "range.write"): {
        "cell",
        "cells",
        "concatenate",
        "decimal",
        "decimals",
        "digits",
        "fixed",
        "formula",
        "formulas",
        "padding",
        "text",
        "write",
    },
    ("libreoffice_calc", "range.set_decimal_separator"): {
        "comma",
        "decimal",
        "decimal separator",
        "dot",
        "format",
        "locale",
        "localized",
        "number",
        "numbers",
        "precision",
        "separator",
    },
    ("libreoffice_calc", "view.freeze_range"): {
        "a1",
        "always visible",
        "freeze",
        "frozen",
        "range",
        "scroll",
        "visible",
    },
    ("libreoffice_calc", "view.freeze_panes"): {
        "column",
        "columns",
        "freeze",
        "frozen",
        "header",
        "headers",
        "pane",
        "panes",
        "row",
        "rows",
        "scroll",
        "visible",
    },
    ("libreoffice_calc", "cells.set_formulas"): {
        "batch",
        "cell",
        "cells",
        "explicit",
        "fill",
        "formula",
        "formulas",
        "missing",
        "column",
        "columns",
        "row",
        "rows",
        "set",
        "sum",
        "total",
        "totals",
        "write",
    },
    ("libreoffice_calc", "workbook.convert_file"): {
        "calc",
        "convert",
        "conversion",
        "csv",
        "file",
        "format",
        "import",
        "libreoffice",
        "ods",
        "spreadsheet",
        "workbook",
        "xlsx",
    },
    ("libreoffice_calc", "workbook.create_new"): {
        "calc",
        "create",
        "data",
        "file",
        "headers",
        "libreoffice",
        "new",
        "ods",
        "report",
        "rows",
        "save",
        "spreadsheet",
        "table",
        "workbook",
        "write",
        "xlsx",
    },
    ("libreoffice_calc", "view.set_zoom"): {
        "cell",
        "cells",
        "larger",
        "magnification",
        "smaller",
        "view",
        "zoom",
    },
    ("libreoffice_impress", "shape.format_text"): {
        "all",
        "align",
        "alignment",
        "body",
        "bottom",
        "center",
        "color",
        "dark",
        "first",
        "font",
        "format",
        "indent",
        "italic",
        "left",
        "ordered",
        "palette",
        "paragraph",
        "point",
        "position",
        "red",
        "respectively",
        "right",
        "second",
        "size",
        "text",
        "textbox",
        "textboxes",
        "title",
        "top",
        "underline",
    },
    ("libreoffice_impress", "shape.align_to_slide"): {
        "align", "edge", "bottom", "top", "left", "right", "flush", "picture", "image", "shape",
    },
    ("libreoffice_impress", "shape.move"): {
        "move", "position", "coordinate", "x", "y", "picture", "image", "shape",
    },
    ("libreoffice_impress", "shape.resize"): {
        "resize", "size", "width", "height", "cm", "mm", "inch", "picture", "image", "shape",
    },
    ("libreoffice_impress", "shape.set_geometry"): {
        "align",
        "bottom",
        "edge",
        "graphic",
        "height",
        "image",
        "left",
        "move",
        "object",
        "photo",
        "picture",
        "position",
        "resize",
        "right",
        "shape",
        "side",
        "table",
        "top",
        "width",
    },
    ("libreoffice_impress", "presentation.set_page_size"): {
        "canvas",
        "custom",
        "dimensions",
        "height",
        "landscape",
        "orientation",
        "page",
        "portrait",
        "presentation",
        "size",
        "slide",
        "slides",
        "square",
        "width",
    },
    ("libreoffice_impress", "shape.fit_to_slide"): {
        "background",
        "center",
        "centering",
        "cover",
        "entire",
        "fill",
        "full",
        "graphic",
        "image",
        "landscape",
        "largest",
        "page",
        "photo",
        "picture",
        "portrait",
        "proportion",
        "ratio",
        "slide",
        "square",
        "whole",
    },
    ("libreoffice_impress", "slide.move"): {
        "after",
        "before",
        "deck",
        "first",
        "index",
        "last",
        "move",
        "order",
        "page",
        "position",
        "rearrange",
        "reorder",
        "slide",
        "whole",
    },
    ("libreoffice_impress", "presentation.inspect"): {"extract", "text"},
    ("libreoffice_impress", "slide.format_text_roles"): {
        "all",
        "body",
        "color",
        "content",
        "font",
        "format",
        "formatting",
        "palette",
        "role",
        "roles",
        "shared",
        "slide",
        "table",
        "text",
        "textbox",
        "textboxes",
        "title",
        "underline",
    },
    ("libreoffice_impress", "slide.set_role_text"): {
        "add",
        "align",
        "body",
        "content",
        "font",
        "heading",
        "insert",
        "replace",
        "role",
        "set",
        "slide",
        "text",
        "title",
        "write",
    },
    ("libreoffice_impress", "slides.format_text_roles"): {
        "color",
        "font",
        "format",
        "formatting",
        "heading",
        "headings",
        "multiple",
        "role",
        "roles",
        "several",
        "shared",
        "slide",
        "slides",
        "title",
        "titles",
        "underline",
    },
    ("libreoffice_impress", "table.format_text"): {
        "all",
        "body",
        "cell",
        "color",
        "dark",
        "font",
        "format",
        "table",
        "text",
        "title",
    },
    ("libreoffice_impress", "table.replace_row"): {
        "cell",
        "cells",
        "change",
        "complete",
        "edit",
        "replace",
        "row",
        "slide",
        "table",
        "update",
        "value",
        "values",
        "write",
    },
    ("libreoffice_impress", "shape.insert_image"): {
        "add",
        "centimeter",
        "cm",
        "desktop",
        "file",
        "height",
        "image",
        "inch",
        "insert",
        "millimeter",
        "mm",
        "photo",
        "picture",
        "png",
        "size",
        "slide",
        "width",
    },
}

IMPRESS_SELECTOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "minProperties": 1,
    "properties": {
        "index": {"type": "integer", "minimum": 0},
        "path": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 0},
        },
        "name": {"type": "string", "minLength": 1},
        "text": {"type": "string"},
        "kind": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}

DIRECT_ACTION_SCHEMAS: dict[str, dict[str, dict[str, Any]]] = {
    "chrome": {
        "browser.inspect": {"properties": {}, "required": []},
        "settings.set": {
            "properties": {
                "settings": {
                    "type": "object",
                    "minProperties": 1,
                    "properties": {
                        "font_size": {"type": "integer", "minimum": 1},
                        "do_not_track": {"type": "boolean"},
                        "safe_browsing": {"type": "boolean"},
                        "profile_name": {"type": "string", "minLength": 1},
                        "search_engine": {"type": "string", "enum": ["bing", "google"]},
                        "appearance": {
                            "type": "string",
                            "enum": ["light", "dark", "system"],
                        },
                        "startup_mode": {
                            "type": "string",
                            "enum": ["new_tab", "continue"],
                        },
                        "clear_on_exit": {"type": "boolean"},
                    },
                    "additionalProperties": False,
                }
            },
            "required": ["settings"],
        },
    },
    "gimp": {},
    "os": {
        "user.ensure_account": {
            "properties": {
                "username": {
                    "type": "string",
                    "pattern": "^[a-z_][a-z0-9_-]{0,31}$",
                },
                "password": {"type": "string", "minLength": 1},
                "home": {
                    "type": "string",
                    "pattern": "^/.*",
                    "description": "Absolute home directory path requested for the account.",
                },
                "shell": {
                    "type": "string",
                    "pattern": "^/.*",
                    "description": "Optional absolute login shell path; defaults to /bin/bash.",
                },
                "mode": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 511,
                    "description": "Optional Unix permission bits as a decimal integer; defaults to 488 (0750 octal).",
                },
            },
            "required": ["username", "password", "home"],
        },
        "command.run": {
            "properties": {
                "argv": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                    "description": "Command and arguments as separate strings; shell parsing is not used.",
                },
                "cwd": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional absolute working directory.",
                },
                "input": {
                    "type": "string",
                    "description": "Optional standard input passed to the command.",
                },
                "expected_returncodes": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "integer"},
                    "description": "Accepted process return codes; defaults to [0].",
                },
            },
            "required": ["argv"],
        },
        "notifications.configure": {
            "properties": {
                "do_not_disturb": {
                    "type": "boolean",
                    "description": "True suppresses desktop notification banners; false enables them.",
                }
            },
            "required": ["do_not_disturb"],
        },
    },
    "libreoffice_impress": {
        "presentation.save": {
            "description": (
                "Save the open Impress presentation. Pass empty parameters to write changes "
                "to the current file in its existing format. Supply url only for Save As. "
                "The result reports the saved file URL, title and byte size."
            ),
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Optional file URL or absolute path for Save As, e.g. file:///home/user/Desktop/pre.pptx.",
                },
                "filter_name": {"type": "string"},
            },
            "required": [],
        },
        "slide.duplicate": {
            "properties": {
                "slide": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Zero-based source slide index.",
                },
                "index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Optional zero-based insertion index; omit to insert after the source.",
                },
            },
            "required": ["slide"],
        },
        "slide.set_background": {
            "description": (
                "Change the selected slide background in the open Impress presentation. "
                "Use image_path for a background image or color for a solid fill. "
                "This edits the open document only; call presentation.save to persist "
                "the changes, then inspect the presentation and screenshot."
            ),
            "properties": {
                "slide": {
                    "type": "integer",
                    "minimum": 0,
                    "description": (
                        "Zero-based slide index for one specific slide. Convert user-facing "
                        "slide N to N-1; never use all_slides for a single numbered slide."
                    ),
                },
                "all_slides": {
                    "type": "boolean",
                    "enum": [True],
                    "description": (
                        "Apply the background to every slide. Use only when the instruction "
                        "explicitly says all, every, or each slide; never use for one numbered slide."
                    ),
                },
                "color": model_color_schema(),
                "image_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Alternative background image path; omit for a solid color.",
                },
            },
            "required": [],
            "oneOf": [
                {"required": ["slide"], "not": {"required": ["all_slides"]}},
                {"required": ["all_slides"], "not": {"required": ["slide"]}},
            ],
            "anyOf": [{"required": ["color"]}, {"required": ["image_path"]}],
        },
    },
    "libreoffice_calc": {
        "workbook.inspect": {
            "description": (
                "Inspect the currently open Calc workbook: its identity (including saved "
                "file URL), worksheet used ranges, and embedded chart "
                "settings in sheets[].charts. data_series_count and data_series report "
                "plotted value series; category_axes reports category labels separately. "
                "sheets[].pivot_tables reports each native pivot name and occupied "
                "output_range. Different pivot names still share worksheet cells; "
                "compare their rectangles when checking placement. "
                "Use this for chart read-back; range.read "
                "returns cells, not charts. Adjacent chart source_ranges may be merged "
                "into an equivalent rectangle: compare covered cells and header flags, "
                "not the number of ranges. No file path is required; pass {} for the "
                "active workbook. This does not return cell values; use "
                "range.read over the observed used_range_a1 before editing cells."
            ),
            "properties": {},
            "required": [],
        },
        "workbook.save": {
            "description": (
                "Save the active workbook. Pass {} to save the current file in its existing "
                "format. For Save As, pass url ending in .ods or .xlsx; the Adapter selects "
                "that file format from the extension. Use workbook.export for CSV or PDF."
            ),
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Optional output file path or file URL for Save As; omit to save the current file.",
                },
                "filter_name": {"type": "string"},
            },
            "required": [],
        },
        "workbook.export": {
            "properties": {
                "format": {"type": "string", "enum": ["csv", "pdf"]},
                "url": {
                    "type": "string",
                    "pattern": "^(?:file://)?/",
                    "description": "Absolute output path or file URL.",
                },
                "sheet": {"type": "string", "minLength": 1},
                "filter_options": {"type": "string"},
            },
            "required": ["format", "url"],
        },
        "page.fit_to_pages": {
            "properties": {
                "sheet": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Exact worksheet name returned by workbook.inspect.",
                },
                "print_range": {"type": "string", "minLength": 1},
                "pages_wide": {"type": "integer", "minimum": 1},
                "pages_tall": {"type": "integer", "minimum": 1},
            },
            "required": ["sheet"],
        },
        "range.read": {
            "description": (
                "Read worksheet cells in one contiguous A1 range, not chart objects. "
                "A chart sheet can have empty cells; use workbook.inspect for charts. "
                "The range must be a single "
                "rectangle such as F3:F20; do not join non-contiguous ranges with commas. "
                "Issue separate range.read calls when disjoint regions must be checked. "
                "The result includes cell_addresses aligned one-for-one with the returned "
                "display_text, formulas, and kinds matrices; use cell_addresses[i][j] as "
                "the exact A1 address for each observed cell. Native date cells also "
                "have date_cells[A1] with an ISO date and weekday. background_cells "
                "reports non-white cell backgrounds by A1 address."
            ),
            "properties": {
                "sheet": {"type": "string"},
                "range": {"type": "string"},
            },
            "required": ["sheet", "range"],
        },
        "sheet.create": {
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "index": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        },
        "pivot.create": {
            "description": (
                "Create one pivot table, writing worksheet cells at destination. "
                "Different names do not allocate separate output areas; reusing an "
                "occupied destination overlaps the earlier table. Choose a non-overlapping "
                "destination from the observed output_range. For stacked tables, use destination={below_range, "
                "blank_rows} to express the exact gap without row arithmetic. Use an A1 "
                "cell when an exact anchor is requested. The response preserves "
                "requested_destination and resolved destination. "
                "Returns destination_sheet and output_range, "
                "the actual occupied A1 rectangle including headings and totals. "
                "output_last_row is its one-based final occupied row; output_row_count "
                "includes all headings and totals. readback contains actual displayed "
                "cells from at most the first 32 rows and 16 columns of that output; "
                "check these computed values against your intended aggregation and "
                "percentage denominator. Its range identifies the preview and truncated "
                "marks omitted cells; range.read can read more of output_range. "
                "If readback_error is present, the pivot was created but its display "
                "could not be read; inspect the output before retrying creation. "
                "To leave n blank rows below it, "
                "choose the next table's start row as output_last_row + n + 1; do not "
                "guess the table height or add it again to output_last_row. "
                "Every reference range and gap must be explicitly model-selected."
            ),
            "properties": {
                "source_sheet": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "^[^!]+$",
                    "description": "Exact source worksheet name only, without ! or a cell range.",
                },
                "source_range": {
                    "type": "string",
                    "pattern": "^\\$?[A-Za-z]{1,4}\\$?[1-9][0-9]*:\\$?[A-Za-z]{1,4}\\$?[1-9][0-9]*$",
                    "description": (
                        "A1 source range only, without a worksheet prefix. Read the "
                        "source cells from the observed used_range_a1 before choosing "
                        "the table range; include its header and all selected records, "
                        "including the last data row. A record count is not a worksheet "
                        "row number because the header also occupies a row."
                    ),
                },
                "destination_sheet": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "^[^!]+$",
                    "description": "Exact destination worksheet name only, without ! or a cell.",
                },
                "destination": copy.deepcopy(PIVOT_DESTINATION_SCHEMA),
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Unique internal pivot-table name. This is not a source field or output label. "
                        "A different name does not move the output: destination selects its cells."
                    ),
                },
                "row_fields": {
                    "type": "array",
                    "description": (
                        "Group records by the distinct values of these category columns. "
                        "For a category frequency or percentage distribution, put the "
                        "requested category here. Grouping by a unique record identifier "
                        "instead produces one group per record, not a category summary."
                    ),
                    "items": {
                        "type": "string",
                        "description": "Exact source column header used for row grouping.",
                    },
                },
                "column_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "Exact source column header used for column grouping.",
                    },
                },
                "page_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "Exact source column header used as a page filter.",
                    },
                },
                "data_fields": {
                    "type": "array",
                    "minItems": 1,
                    "description": (
                        "Values to aggregate. field is an exact source header; aggregation is the "
                        "operation. Do not put an output label in field and do not use "
                        "reference_field to identify the value column."
                    ),
                    "items": copy.deepcopy(CALC_PIVOT_DATA_FIELD),
                },
                "replace": {"type": "boolean"},
                "show_filter_button": {"type": "boolean"},
            },
            "required": [
                "source_sheet",
                "source_range",
                "destination_sheet",
                "destination",
                "name",
                "data_fields",
            ],
        },
        "chart.create": {
            "description": (
                "Create one chart from the model-selected source ranges. Select only "
                "the category field and the value series requested by the instruction. "
                "When a total or derived column is requested, do not pass a rectangle "
                "that also contains its component columns; pass the category range and "
                "that single total/value range instead. For series in columns, pass "
                "the category column first, then each requested value-series range, "
                "and set row_headers=true. This flag makes the first column category "
                "labels; row_headers=false instead plots it as another value series "
                "and supplies no category labels. If source_ranges exclude "
                "the header row, set column_headers=false even when the worksheet "
                "has headers above them. True consumes the first selected row as "
                "labels; it never reads the row above your selection. For series "
                "in rows, select the category row first and set column_headers=true; "
                "row_headers controls whether the leftmost selected column contains "
                "series names. To correct an existing chart, reuse its exact name "
                "and explicitly set replace=true."
            ),
            "properties": {
                "sheet": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Existing destination worksheet returned by workbook.inspect. "
                        "It may differ from source_sheet. chart.create does not create "
                        "a worksheet; when no separate "
                        "destination is requested, use source_sheet."
                    ),
                },
                "source_sheet": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Exact worksheet containing every A1 range in source_ranges. "
                        "Copy the worksheet name from range.read, even when the chart "
                        "is placed on a different existing sheet."
                    ),
                },
                "name": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Unique internal Calc chart-object name. It is not the text "
                        "shown as the chart title. To replace a chart seen in "
                        "workbook.inspect, reuse that exact name and set replace=true."
                    ),
                },
                "source_ranges": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                    "description": (
                        "A1 ranges on source_sheet: each array item is exactly one "
                        "contiguous range string. For separate category and value "
                        'series pass two items such as ["D8:D10", "G8:G10"], '
                        'never one comma-joined item such as "D8:D10,G8:G10". '
                        "Ranges must have aligned observations. Each numeric "
                        "series is plotted separately, not summed. Select only the "
                        "category and value series requested. If the instruction names "
                        "a total or derived value column, pass the category range and "
                        "that one value-column range; never include component columns "
                        "in the same rectangle. Set header flags for the selected "
                        "ranges, not the whole worksheet. For series in rows, the "
                        "category and value ranges must span the same columns; for "
                        "series in columns, they must span the same rows. Read each "
                        "source table's header and boundary rows before selecting "
                        "its ranges; a second table may have different boundaries. "
                        "Include summary rows only if they are requested chart data."
                    ),
                },
                "type": {
                    "type": "string",
                    "enum": ["column", "bar", "line"],
                    "description": (
                        "Chart geometry: column creates vertical columns, bar creates "
                        "horizontal bars, and line creates a line chart."
                    ),
                },
                "data_row_source": {
                    "type": "string",
                    "enum": ["rows", "columns"],
                    "description": (
                        "Series orientation: rows means one value series per data "
                        "row; columns means one per data column. When omitted, "
                        "the Adapter infers orientation from the selected ranges' "
                        "shape and returns the effective direction. Header flags "
                        "always refer to the physical first row and first column."
                    ),
                },
                "column_headers": {
                    "type": "boolean",
                    "description": (
                        "Controls the first row inside source_ranges: true consumes "
                        "it as labels rather than data; false plots it. A header "
                        "row outside source_ranges is not read. Choose true only "
                        "when the selected ranges include that header row. If they "
                        "start with observations below the header, set false so the "
                        "first data row is not omitted. With series in rows, this "
                        "first row supplies category-axis labels; with series in "
                        "columns, it supplies series names. This is "
                        "independent of row_headers. Defaults to true when omitted."
                    ),
                },
                "row_headers": {
                    "type": "boolean",
                    "description": (
                        "Controls the selected leftmost column. For series in columns, "
                        "true uses it as category-axis labels; false plots it as an "
                        "additional value series and supplies no category labels. "
                        "Choose true when that column is your category field, whether "
                        "its labels are text, numbers, or dates. For series in rows, "
                        "true uses the leftmost column as series labels instead. "
                        "Independent of column_headers. Defaults to true when omitted."
                    ),
                },
                "replace": {
                    "type": "boolean",
                    "description": (
                        "Defaults to false: an existing chart with this name is "
                        "preserved and a CONFLICT error is returned. Set true to "
                        "remove that chart and recreate it from this call's full "
                        "ranges, type, header flags, title and position. Replacement "
                        "does not reuse omitted settings from the old chart."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Optional displayed main chart title. When the instruction "
                        "requests a title, pass its exact text here even if it is "
                        "also used as the internal name."
                    ),
                },
                "position": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer", "minimum": 1},
                        "height": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                },
            },
            "required": ["sheet", "name", "source_ranges", "type"],
        },
    },
    "libreoffice_writer": {
        "document.inspect": {
            "description": (
                "Read the current Writer structure, including exact table names in tables. "
                "When tables is empty, no table action is applicable: do not guess a table "
                "name; use paragraph or text actions instead."
            ),
            "properties": {},
            "required": [],
        },
        "document.save": {"properties": {}, "required": []},
        "paragraph.set_format": {
            "properties": {
                "indices": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "integer", "minimum": 0},
                },
                "line_spacing": {"type": "number", "exclusiveMinimum": 0},
                "alignment": {
                    "type": "string",
                    "enum": ["left", "right", "center", "justify"],
                },
                "font_size": {"type": "number", "exclusiveMinimum": 0},
                "strikethrough": {"type": "boolean"},
            },
            "required": [],
        },
    },
    "vs_code": {
        "workspace.open": {
            "description": (
                "Open the exact model-selected file, folder, or .code-workspace path in VS Code. "
                "When the instruction names a nested project, open that complete path directly; "
                "do not open its parent directory first."
            ),
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute file, folder, or .code-workspace path to open in VS Code.",
                },
                "reuse_window": {
                    "type": "boolean",
                    "description": "Reuse an existing VS Code window; defaults to true.",
                },
                "close_existing": {
                    "type": "boolean",
                    "description": "Close existing VS Code windows before opening the requested path.",
                },
            },
            "required": ["path"],
        },
        "file.create": {
            "description": (
                "Create a UTF-8 text file from the content string. Omitting content creates "
                "an empty text file. A .docx, .pptx or .pdf suffix does not produce that "
                "document format; use the owning application's native document operations "
                "for those formats."
            ),
            "properties": {
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute path of the UTF-8 text file to create.",
                },
                "content": {
                    "type": "string",
                    "description": "Exact text to write as UTF-8; defaults to an empty string.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether an existing file may be overwritten; defaults to false.",
                },
                "open": {
                    "type": "boolean",
                    "description": "Open the created file in VS Code after writing it.",
                },
            },
            "required": ["path"],
        },
        "settings.update": {
            "properties": {
                "values": {
                    "type": "object",
                    "minProperties": 1,
                    "description": "Exact VS Code setting identifiers mapped to JSON values.",
                    "additionalProperties": True,
                },
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional settings.json path; omit for the active user settings.",
                },
            },
            "required": ["values"],
        },
    },
    "vlc": {
        "media.extract_audio": {
            "properties": {
                "input_path": {"type": "string", "minLength": 1},
                "output_path": {"type": "string", "minLength": 1},
            },
            "required": ["input_path", "output_path"],
        },
        "media.extract_subtitles": {
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute path of the source video containing embedded subtitles or captions.",
                },
                "output_path": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": r"^.*\.(?:[sS][rR][tT]|[vV][tT][tT])$",
                    "description": "Absolute destination path ending in .srt or .vtt.",
                },
                "subtitle_stream_index": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 1024,
                    "default": 0,
                    "description": "Zero-based embedded subtitle stream index; omit to extract the first stream.",
                },
            },
            "required": ["input_path", "output_path"],
        },
        "media.transcode_clip": {
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute path of the source audio or video file.",
                },
                "output_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": (
                        "Absolute output path. Use .gif for an animated GIF, or a supported "
                        "video extension such as .mp4 or .webm."
                    ),
                },
                "start_time_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 86400,
                    "description": "Start offset in seconds; for 00:03 use 3.",
                },
                "duration_seconds": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": 86400,
                    "description": "Length of the extracted clip in seconds.",
                },
                "frame_rate": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": 60,
                    "description": "Optional animated-GIF frame rate; omit to use 15 fps.",
                },
            },
            "required": [
                "input_path",
                "output_path",
                "start_time_seconds",
                "duration_seconds",
            ],
        },
        "config.update": {
            "properties": {
                "values": {
                    "type": "object",
                    "minProperties": 1,
                    "description": "VLC preference names mapped to string, integer, or boolean values.",
                    "additionalProperties": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "integer"},
                            {"type": "boolean"},
                        ]
                    },
                },
                "path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional vlcrc path; omit to update the active user configuration.",
                },
            },
            "required": ["values"],
        },
        "preferences.configure": {
            "properties": {
                "global_play_pause_hotkey": {
                    "type": "string",
                    "minLength": 1,
                    "description": "VLC global Play/Pause key name, for example Media Play Pause.",
                },
                "maximum_volume_percent": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 300,
                    "description": "Maximum volume shown by the VLC Qt interface, as a percentage.",
                },
                "volume_slider_color": {
                    "type": "string",
                    "pattern": "^#[0-9A-Fa-f]{6}$",
                    "description": "One #RRGGBB color applied to all VLC volume-slider states.",
                },
                "minimal_interface": {
                    "type": "boolean",
                    "description": "True hides the normal playback controls in window mode.",
                },
                "exit_after_playback": {
                    "type": "boolean",
                    "description": "Whether VLC exits automatically when playback ends.",
                },
                "allow_multiple_instances": {
                    "type": "boolean",
                    "description": "Whether files opened from the desktop may start independent VLC instances.",
                },
                "show_background_cone": {
                    "type": "boolean",
                    "description": "Whether the VLC cone is shown in the empty-player background.",
                },
                "recording_directory": {
                    "type": "string",
                    "minLength": 1,
                    "pattern": "^/.*",
                    "description": "Explicit absolute directory for VLC recordings.",
                },
                "recording_location": {
                    "type": "string",
                    "enum": ["desktop", "downloads", "videos", "music", "home"],
                    "description": "Standard directory under the active user's home for VLC recordings.",
                },
            },
            "required": [],
            "oneOf": [
                {"required": ["global_play_pause_hotkey"]},
                {"required": ["maximum_volume_percent"]},
                {"required": ["volume_slider_color"]},
                {"required": ["minimal_interface"]},
                {"required": ["exit_after_playback"]},
                {"required": ["allow_multiple_instances"]},
                {"required": ["show_background_cone"]},
                {"required": ["recording_directory"]},
                {"required": ["recording_location"]},
            ],
            "additionalProperties": False,
        },
        "playback.open": {
            "properties": {
                "source": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute local media path or HTTP(S) stream URL.",
                },
                "media_kind": {
                    "type": "string",
                    "enum": ["audio", "video"],
                    "description": "Resolve the unique audio or video file when no exact filename is given.",
                },
                "source_query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Optional filename keywords used to narrow semantic media lookup.",
                },
                "search_roots": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                    "description": "Directories searched recursively for a unique matching media file.",
                },
                "loop": {"type": "boolean"},
            },
            "required": [],
            "oneOf": [
                {
                    "required": ["source"],
                    "not": {
                        "anyOf": [
                            {"required": ["media_kind"]},
                            {"required": ["source_query"]},
                            {"required": ["search_roots"]},
                        ]
                    },
                },
                {"required": ["media_kind"], "not": {"required": ["source"]}},
            ],
        },
        "playback.status": {"properties": {}, "required": []},
        "window.set_fullscreen": {
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
        "media.extract_frame": {
            "description": (
                "Extract one PNG image directly from a local video file at the selected "
                "time_seconds or zero-based frame_index; provide exactly one of these. "
                "This does not require seeking or pausing VLC. A whole-second playback "
                "display or an approximate progress-bar click does not identify an exact "
                "frame. Use playback.status or filesystem.find to observe the input path "
                "when it is unknown, and choose a writable output_path."
            ),
            "properties": {
                "input_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Exact local source-video path selected from observed state.",
                },
                "output_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute writable PNG output path.",
                },
                "frame_index": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10000000,
                    "description": "Zero-based source-video frame index for the requested visible moment.",
                },
                "time_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 86400,
                    "description": "Source-video timestamp in seconds; fractional seconds are supported.",
                },
            },
            "required": ["input_path", "output_path"],
            "oneOf": [
                {
                    "required": ["input_path", "frame_index"],
                    "not": {"required": ["time_seconds"]},
                },
                {
                    "required": ["input_path", "time_seconds"],
                    "not": {"required": ["frame_index"]},
                },
            ],
        },
    },
    "thunderbird": {
        "folders.ensure_local": {
            "properties": {
                "names": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string", "minLength": 1},
                }
            },
            "required": ["names"],
        },
        "compose.attach": {
            "properties": {
                "subject": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Exact subject of the already-open compose window.",
                },
                "attachment_path": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Absolute path, or a home-relative path beginning with ~/.",
                },
            },
            "required": ["subject", "attachment_path"],
        },
        "preferences.update": {
            "description": "Set or remove exactly one explicit Thunderbird preference per call.",
            "properties": {
                "values": {
                    "type": "object", "minProperties": 1, "maxProperties": 1,
                    "description": "Exactly one preference name mapped to its typed value.",
                    "additionalProperties": {"type": ["string", "boolean", "integer"]},
                },
                "remove_keys": {
                    "type": "array", "minItems": 1, "maxItems": 1,
                    "items": {"type": "string", "minLength": 1},
                    "description": "Exactly one preference name to remove.",
                },
            },
            "required": [],
            "oneOf": [{"required": ["values"]}, {"required": ["remove_keys"]}],
        },
    },
    "multi_apps": {},
}

# Adapter-owned structured manifests replace the legacy opaque params wrapper
# for actions with explicit model-facing contracts.
DIRECT_ACTION_SCHEMAS["libreoffice_calc"].update(
    copy.deepcopy(CALC_STRICT_ACTION_PARAM_SCHEMAS)
)
DIRECT_ACTION_SCHEMAS["libreoffice_impress"].update(
    copy.deepcopy(IMPRESS_STRICT_ACTION_PARAM_SCHEMAS)
)
# The generic model-facing contract for fitting a graphic is stricter than the
# legacy selector contract: stable observation-derived selectors prevent a
# duplicate display name from silently targeting the wrong shape.
DIRECT_ACTION_SCHEMAS["gimp"].update(copy.deepcopy(GIMP_STRICT_ACTION_PARAM_SCHEMAS))
DIRECT_ACTION_SCHEMAS["os"].update(copy.deepcopy(OS_STRICT_ACTION_PARAM_SCHEMAS))
DIRECT_ACTION_SCHEMAS["libreoffice_writer"].update(
    copy.deepcopy(WRITER_STRICT_ACTION_PARAM_SCHEMAS)
)
DIRECT_ACTION_SCHEMAS["multi_apps"].update(
    copy.deepcopy(MULTI_APPS_STRICT_ACTION_PARAM_SCHEMAS)
)
DIRECT_ACTION_SCHEMAS["vs_code"].update(
    copy.deepcopy(VSCODE_STRICT_ACTION_PARAM_SCHEMAS)
)
DIRECT_ACTION_SCHEMAS["thunderbird"].update(
    copy.deepcopy(THUNDERBIRD_STRICT_ACTION_PARAM_SCHEMAS)
)
DIRECT_ACTION_SCHEMAS["vlc"].update(copy.deepcopy(VLC_STRICT_ACTION_PARAM_SCHEMAS))


def _tokens(value: str) -> set[str]:
    ascii_tokens = set(re.findall(r"[a-z0-9]+", value.lower())).difference(
        ROUTING_STOPWORDS
    )
    normalized = re.sub(r"[-_]+", " ", value.casefold())
    for canonical, phrase in (
        ("lowercase", r"\blower\s+case\b"),
        ("titlecase", r"\btitle\s+case\b"),
        ("uppercase", r"\bupper\s+case\b"),
    ):
        if re.search(phrase, normalized):
            ascii_tokens.add(canonical)
    chinese_tokens = {
        token
        for terms in SYNONYMS.values()
        for token in terms
        if any("\u4e00" <= char <= "\u9fff" for char in token) and token in value
    }
    return ascii_tokens | chinese_tokens


def _expanded_instruction_tokens(instruction: str) -> set[str]:
    tokens = _tokens(instruction)
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    if re.search(r"\bcross(?:ed|ing)?\s+out\b", normalized):
        tokens.add("crossout")
    if re.search(r"\bcross\s+references?\b", normalized):
        tokens.add("crossreference")
    for canonical, terms in SYNONYMS.items():
        if tokens.intersection(terms):
            tokens.add(canonical)
            tokens.update(terms)
    return tokens


def instruction_requests_command_tool(instruction: str) -> bool:
    """Return whether the user explicitly requested command-style execution."""
    tokens = _expanded_instruction_tokens(instruction)
    if tokens.intersection(COMMAND_INTENT_TOKENS):
        return True
    if instruction_requests_code_execution(instruction):
        return True
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    return bool(
        re.search(
            r"\b(?:commit|push|pull|checkout|clone)\b.{0,48}\b(?:branch|repository|repo|origin)\b",
            normalized,
        )
    )


def instruction_requests_code_execution(instruction: str) -> bool:
    """Return whether source execution is explicit or required for a saved result."""
    normalized = re.sub(r"[-_]+", " ", instruction.casefold())
    source_file = r"\.(?:c|cc|cpp|cs|go|java|js|jsx|mjs|php|pl|py|rb|rs|sh|ts|tsx)\b"
    if re.search(
        rf"\b(?:run|execute)\b.{{0,64}}(?:\b(?:code|script|program|tests?|pytest|python|npm)\b|{source_file})",
        normalized,
    ):
        return True

    has_source_mutation = bool(
        re.search(
            r"\b(?:complet(?:e|ed|ing)|correct(?:ed|ing)?|debug(?:ged|ging)?|"
            r"finish(?:ed|ing)?|fix(?:ed|ing)?|implement(?:ed|ing)?|repair(?:ed|ing)?)\b",
            normalized,
        )
        and re.search(
            rf"(?:\b(?:code|function|method|program|script|source)\b|{source_file})",
            normalized,
        )
    )
    has_saved_execution_result = bool(
        re.search(
            r"\b(?:save|store|write|capture|record)\b.{0,80}\b(?:output|result|stdout|log)\b",
            normalized,
        )
        or re.search(
            r"\b(?:output|result|stdout|log)\b.{0,80}\b(?:save|store|write|capture|record)\b",
            normalized,
        )
    )
    return has_source_mutation and has_saved_execution_result


def instruction_requires_local_file_discovery(instruction: str) -> bool:
    """Return whether a described local artifact needs an exact path before use."""
    return requires_local_input_discovery(instruction)


def _pdf_split_intent(tokens: set[str]) -> bool:
    """Recognize outline-based PDF composition without exposing it for plain reading."""
    return bool(
        tokens.intersection({"book", "pdf", "pdfs"})
        and tokens.intersection(
            {
                "bookmark",
                "bookmarks",
                "chapter",
                "chapters",
                "outline",
                "section",
                "sections",
            }
        )
        and tokens.intersection({"divide", "separate", "split", "splitting"})
    )


def _desktop_association_intent(tokens: set[str]) -> bool:
    """Recognize requests that need application discovery and MIME mutation."""
    return bool(
        tokens.intersection(
            {"app", "application", "applications", "desktop", "viewer", "handler", "player"}
        )
        and tokens.intersection(
            {"default", "associate", "association", "associations", "mime"}
        )
    )


def tool_name(action: str) -> str:
    return "adapter__" + re.sub(r"[^a-zA-Z0-9_]", "_", action)


def action_from_tool_name(domain: str, name: str) -> str | None:
    mapping = {tool_name(action): action for action in public_actions(domain)}
    return mapping.get(name)


def _action_tokens(domain: str, action: str) -> set[str]:
    return _tokens(action).union(ACTION_KEYWORDS.get((domain, action), set()))


def action_relevance_score(domain: str, action: str, instruction: str) -> int:
    """Score semantic overlap without task identity or evaluator information."""
    exact_instruction = _tokens(instruction)
    expanded_instruction = _expanded_instruction_tokens(instruction)
    name_tokens = _tokens(action)
    keyword_tokens = ACTION_KEYWORDS.get((domain, action), set())
    return (
        (20 if name_tokens and name_tokens.issubset(exact_instruction) else 0)
        + 4 * len(exact_instruction.intersection(name_tokens))
        + 2 * len(exact_instruction.intersection(keyword_tokens))
        + len(expanded_instruction.intersection(name_tokens | keyword_tokens))
    )


def _vscode_debug_search_bonus(action: str, query_tokens: set[str]) -> int:
    """Prefer observation over launch for variable-inspection searches."""
    if action not in {"debug.start", "debug.variables.read"}:
        return 0
    observation_terms = {
        "inspect",
        "read",
        "value",
        "values",
        "variable",
        "variables",
        "visualize",
        "visualization",
    }
    launch_terms = {
        "execute",
        "f5",
        "launch",
        "run",
        "start",
    }
    if action == "debug.variables.read":
        return (
            8
            if query_tokens.intersection(observation_terms)
            and not query_tokens.intersection(launch_terms)
            else 0
        )
    return 8 if query_tokens.intersection(launch_terms) else 0


def _catalog_signature(
    domain: str, action: str, *, strict_generic: bool = False
) -> str:
    direct_schema = DIRECT_ACTION_SCHEMAS.get(domain, {}).get(action)
    if direct_schema is None:
        return action_signature(domain, action)
    description = direct_schema.get("description")
    if strict_generic:
        parameters = {
            "type": "object",
            "properties": copy.deepcopy(direct_schema.get("properties", {})),
            "required": list(direct_schema.get("required", [])),
            "additionalProperties": False,
        }
        for keyword in ("allOf", "anyOf", "oneOf", "not"):
            if keyword in direct_schema:
                parameters[keyword] = copy.deepcopy(direct_schema[keyword])
        direct_schema = _strict_generic_schema_overlay(domain, action, parameters)
    properties = direct_schema.get("properties", {})
    required = direct_schema.get("required", [])
    alternatives = direct_schema.get("oneOf")
    suffix = f"; oneOf={alternatives!r}" if alternatives else ""
    prefix = f"{description} " if isinstance(description, str) else ""
    return f"{prefix}properties={properties!r}; required={required!r}{suffix}"


def _schema_type_label(schema: Any) -> str:
    """Return a compact, non-value-bearing type label for search results."""
    if not isinstance(schema, dict):
        return "unknown"
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return "|".join(str(item) for item in schema_type[:4])
    if isinstance(schema_type, str):
        return schema_type
    if "enum" in schema:
        return "enum"
    if "properties" in schema:
        return "object"
    return "value"


def _search_contract_metadata(
    domain: str,
    action: str,
    *,
    route_domain: str | None = None,
    route_action: str | None = None,
    strict_generic: bool = False,
) -> dict[str, Any]:
    """Describe how a search hit maps to the next model-visible callable.

    Search is only discovery.  This metadata does not select an action or fill
    arguments; it removes the ambiguous dotted-name/flattened-tool-name bridge
    while keeping the full schema in the following tool definition.
    """
    contract_domain = route_domain or domain
    contract_action = route_action or action
    schema = DIRECT_ACTION_SCHEMAS.get(contract_domain, {}).get(contract_action)
    if not isinstance(schema, dict):
        return {
            "tool_name": tool_name(action),
            "parameter_summary": {"required": [], "fields": {}},
        }
    description = schema.get("description")
    if strict_generic:
        parameters = {
            "type": "object",
            "properties": copy.deepcopy(schema.get("properties", {})),
            "required": list(schema.get("required", [])),
            "additionalProperties": False,
        }
        for keyword in ("allOf", "anyOf", "oneOf", "not"):
            if keyword in schema:
                parameters[keyword] = copy.deepcopy(schema[keyword])
        schema = _strict_generic_schema_overlay(
            contract_domain, contract_action, parameters
        )
    properties = schema.get("properties", {})
    fields: dict[str, Any] = {}
    if isinstance(properties, dict):
        for name in sorted(properties)[:24]:
            spec = properties[name]
            field: dict[str, Any] = {"type": _schema_type_label(spec)}
            if isinstance(spec, dict) and isinstance(spec.get("enum"), list):
                # Enums are bounded public protocol values, unlike task data.
                field["enum"] = [item for item in spec["enum"][:8]]
            fields[str(name)] = field
    metadata: dict[str, Any] = {
        "tool_name": tool_name(action),
        "parameter_summary": {
            "required": [str(item) for item in schema.get("required", [])[:24]],
            "fields": fields,
        },
    }
    if isinstance(description, str) and description:
        metadata["description"] = description
    if route_domain and route_action:
        metadata["downstream"] = {
            "adapter": route_domain,
            "action": route_action,
        }
    return metadata


def select_actions(
    domain: str,
    instruction: str,
    recommended: Iterable[str] = (),
    expanded: Iterable[str] = (),
    limit: int | None = 7,
    *,
    allow_task_routes: bool = False,
) -> list[str]:
    if allow_task_routes:
        raise ValueError("task routes are not available")
    available = set(public_actions(domain))
    available.difference_update(FORBIDDEN_DATASET_ACTIONS)
    if domain == "libreoffice_impress" and suppress_whole_slide_move(instruction):
        available.discard("slide.move")
    if (
        domain == "libreoffice_impress"
        and impress_page_number.suppress_page_number_action(instruction)
    ):
        available.discard(impress_page_number.ACTION)
    recommended_set = set(recommended).intersection(available)
    expanded_set = set(expanded).intersection(available)
    fixed = [
        action
        for action in (*INSPECT_ACTIONS.get(domain, ()), *SAVE_ACTIONS.get(domain, ()))
        if action in available
    ]
    instruction_tokens = _expanded_instruction_tokens(instruction)
    image_subject_intent = bool(
        instruction_tokens.intersection(VISUAL_IMAGE_TOKENS)
    )
    image_crop_intent = bool(
        image_subject_intent
        and instruction_tokens.intersection(
            {"crop", "cropped", "cropping", "trim", "trimmed", "trimming"}
        )
    )
    document_image_extraction_intent = bool(
        image_subject_intent
        and instruction_tokens.intersection(
            {"doc", "docx", "document", "odt", "word", "writer"}
        )
        and instruction_tokens.intersection(
            TRANSFER_INTENT_TOKENS | {"export", "exported", "save", "saved"}
        )
    )
    desktop_wallpaper_intent = bool(
        "wallpaper" in instruction_tokens
        or (
            "desktop" in instruction_tokens
            and "background" in instruction_tokens
            and image_subject_intent
        )
    )
    visual_image_identification_intent = bool(
        image_subject_intent
        and instruction_tokens.intersection(VISUAL_IDENTIFICATION_TOKENS)
    )
    visual_image_rename_intent = bool(
        visual_image_identification_intent
        and instruction_tokens.intersection(VISUAL_RENAME_TOKENS)
    )
    local_file_discovery_intent = instruction_requires_local_file_discovery(instruction)
    file_organization_search = bool(
        instruction_tokens.intersection(FILE_ORGANIZATION_TOKENS)
        and instruction_tokens.intersection(FILE_ORGANIZATION_ACTION_TOKENS)
    )
    age_organization_search = bool(
        instruction_tokens.intersection(AGE_ORGANIZATION_TOKENS)
        and instruction_tokens.intersection(AGE_ORGANIZATION_ACTION_TOKENS)
        and instruction_tokens.intersection({"file", "files"})
    )
    pdf_split_intent = _pdf_split_intent(instruction_tokens)
    desktop_association_intent = _desktop_association_intent(instruction_tokens)
    active_workspace_file_intent = bool(
        domain == "multi_apps" and requests_active_workspace_files(instruction)
    )
    thunderbird_filter_intent = bool(
        domain == "thunderbird"
        and instruction_tokens.intersection({"filter", "filters", "rule", "rules"})
        and instruction_tokens.intersection(
            {
                "auto",
                "automatic",
                "automatically",
                "configure",
                "create",
                "forward",
                "move",
                "route",
                "routes",
                "routing",
            }
        )
    )
    scored: list[tuple[float, int, str]] = []
    for action in available:
        if (
            action == "workspace.find_files"
            and action not in recommended_set
            and action not in expanded_set
            and not active_workspace_file_intent
        ):
            continue
        if (
            action == "image.crop"
            and action not in expanded_set
            and not image_crop_intent
        ):
            continue
        if (
            action == "document.extract_images"
            and action not in expanded_set
            and not document_image_extraction_intent
        ):
            continue
        if (
            action == "desktop.set_wallpaper"
            and action not in expanded_set
            and not desktop_wallpaper_intent
        ):
            continue
        if (
            action in {"desktop.applications.inspect", "desktop.mime_associations.set"}
            and action not in expanded_set
            and action not in recommended_set
            and not desktop_association_intent
        ):
            continue
        if (
            action in {"pdf.outline.inspect", "pdf.pages.extract"}
            and action not in expanded_set
            and action not in recommended_set
            and not pdf_split_intent
        ):
            continue
        if (
            action in {"command.run", "command.capture_output"}
            and action not in expanded_set
            and not instruction_requests_command_tool(instruction)
        ):
            continue
        if (
            action == "window.capture"
            and action not in recommended_set
            and action not in expanded_set
        ):
            continue
        haystack_tokens = _action_tokens(domain, action).union(
            _tokens(_catalog_signature(domain, action))
        )
        overlap = instruction_tokens.intersection(haystack_tokens)
        score = float(len(overlap))
        if action in recommended_set:
            score += 100.0
        if action in expanded_set:
            score += 80.0
        if action in fixed:
            score += 40.0
        if action == "workspace.find_files" and active_workspace_file_intent:
            score += 1300.0
        if action == "document.extract_images" and document_image_extraction_intent:
            score += 900.0
        if action == "desktop.set_wallpaper" and desktop_wallpaper_intent:
            score += 850.0
        if desktop_association_intent:
            score += {
                "desktop.applications.inspect": 1400.0,
                "desktop.mime_associations.set": 1300.0,
            }.get(action, 0.0)
        if pdf_split_intent:
            score += {
                "pdf.outline.inspect": 1400.0,
                "filesystem.find": 1300.0,
                "pdf.pages.extract": 1200.0,
            }.get(action, 0.0)
        if action == "filesystem.find" and local_file_discovery_intent:
            score += 5.0
        if file_organization_search and action == "filesystem.rename":
            score += 900.0
        if age_organization_search:
            score += {
                "filesystem.find": 1_400.0,
                "archive.compress_file": 1_300.0,
                "filesystem.rename": 1_200.0,
                "filesystem.create_directory": 1_100.0,
            }.get(action, 0.0)
        if image_crop_intent:
            score += {
                "image.crop": 1200.0,
                "filesystem.find": 1100.0,
                "command.run": (
                    1000.0 if instruction_requests_command_tool(instruction) else 0.0
                ),
            }.get(action, 0.0)
        if visual_image_rename_intent:
            score += {
                "filesystem.find": 1000.0,
                "desktop.open_path": 900.0,
                "filesystem.rename": 800.0,
            }.get(action, 0.0)
        if action == "filters.configure" and thunderbird_filter_intent:
            score += 100.0
        if action.endswith(".inspect") or action.endswith(".read"):
            score += 1.0
        scored.append(
            (score, action_relevance_score(domain, action, instruction), action)
        )
    age_priority = {
        "filesystem.find": 4,
        "archive.compress_file": 3,
        "filesystem.rename": 2,
        "filesystem.create_directory": 1,
    }
    ordered = [
        action
        for _score, _semantic_score, action in sorted(
            scored,
            key=(
                lambda item: (
                    -age_priority.get(item[2], 0),
                    -item[0],
                    -item[1],
                    item[2],
                )
                if age_organization_search
                else (-item[0], -item[1], item[2])
            ),
        )
    ]
    selected = list(dict.fromkeys([*fixed, *ordered]))
    if (
        domain == "multi_apps"
        and "adapter.call" in available
        and limit is not None
        and limit > 0
    ):
        selected = [action for action in selected if action != "adapter.call"]
        return [*selected[: limit - 1], "adapter.call"]
    return selected[:limit]


def search_actions(
    domain: str,
    query: str,
    limit: int = 6,
    *,
    instruction: str = "",
    stage_actions: Iterable[str] = (),
    semantic_actions: Iterable[str] = (),
    recent_error: str = "",
    excluded_actions: Iterable[str] = (),
    excluded_routes: Iterable[tuple[str, str]] = (),
    allow_task_routes: bool = False,
    strict_generic: bool = False,
    completed_routes: Iterable[tuple[str, str]] = (),
) -> list[dict[str, Any]]:
    if allow_task_routes:
        raise ValueError("task routes are not available")
    domain_context = DOMAIN_CONTEXT_TOKENS.get(domain, set())
    exact_query_tokens = _tokens(query).difference(domain_context)
    query_tokens = _expanded_instruction_tokens(query).difference(domain_context)
    instruction_tokens = _expanded_instruction_tokens(instruction).difference(
        domain_context
    )
    error_tokens = _expanded_instruction_tokens(recent_error).difference(domain_context)
    if domain == "multi_apps":
        return _search_multi_app_actions(
            query=query,
            exact_query_tokens=exact_query_tokens,
            query_tokens=query_tokens,
            instruction_tokens=instruction_tokens,
            error_tokens=error_tokens,
            limit=limit,
            excluded_actions=set(excluded_actions),
            excluded_routes=set(excluded_routes),
            query_requests_command=instruction_requests_command_tool(query),
            active_workspace_files=(
                requests_active_workspace_files(query)
                or requests_active_workspace_files(instruction)
            ),
            strict_generic=strict_generic,
            semantic_actions=semantic_actions,
            completed_routes=completed_routes,
        )
    age_search_tokens = exact_query_tokens | query_tokens | instruction_tokens
    age_organization_search = bool(
        age_search_tokens.intersection(AGE_ORGANIZATION_TOKENS)
        and age_search_tokens.intersection(AGE_ORGANIZATION_ACTION_TOKENS)
        and age_search_tokens.intersection({"file", "files"})
    )
    explicit_file_read_search = bool(
        domain == "vs_code"
        and "file.read_text" in public_actions(domain)
        and query_tokens.intersection({"read", "inspect"})
        and ("/" in query or re.search(r"\.[a-z0-9]{1,8}\b", query.casefold()))
    )
    staged = list(stage_actions)
    semantic = list(semantic_actions)
    available = set(
        scope_semantic_search_actions(
            public_actions(domain),
            semantic,
            strict_generic=strict_generic,
        )
    )
    available.difference_update(FORBIDDEN_DATASET_ACTIONS)
    if domain == "libreoffice_impress" and suppress_whole_slide_move(
        query, instruction
    ):
        available.discard("slide.move")
    if (
        domain == "libreoffice_impress"
        and impress_page_number.suppress_page_number_action(query)
    ):
        available.discard(impress_page_number.ACTION)
    excluded = set(excluded_actions).intersection(available)
    stage = set(staged).intersection(available).difference(excluded)
    matches: list[tuple[int, str]] = []
    for action in available.difference(excluded):
        action_tokens = _action_tokens(domain, action)
        name_tokens = _tokens(action)
        contract_tokens = _tokens(
            _catalog_signature(domain, action, strict_generic=strict_generic)
        )
        exact_identifier_match = bool(
            re.search(
                rf"(?<![\w.]){re.escape(action.casefold())}(?![\w.])",
                query.casefold(),
            )
        )
        score = (
            impress_page_number.search_relevance_bonus(action, query)
            + impress_table_row.search_relevance_bonus(action, query, instruction)
            if domain == "libreoffice_impress"
            else 0
        ) + (
            (10_000 if exact_identifier_match else 0)
            + (250 if name_tokens and name_tokens.issubset(exact_query_tokens) else 0)
            + 100 * len(exact_query_tokens.intersection(action_tokens))
            + 10 * len(exact_query_tokens.intersection(contract_tokens))
            + 5 * len(query_tokens.intersection(action_tokens))
            + len(query_tokens.intersection(contract_tokens))
            + 4 * len(instruction_tokens.intersection(action_tokens))
            + len(instruction_tokens.intersection(contract_tokens))
            + 2 * len(error_tokens.intersection(action_tokens))
            + len(error_tokens.intersection(contract_tokens))
            + (20 if action in stage else 0)
            + _vscode_debug_search_bonus(action, query_tokens)
        )
        if explicit_file_read_search and action == "file.read_text":
            score += 50
        if score:
            matches.append((score, action))
    fallback = None
    age_priority = {
        "filesystem.find": 4,
        "archive.compress_file": 3,
        "filesystem.rename": 2,
        "filesystem.create_directory": 1,
    }
    ranked = [
        item
        for item in sorted(
            matches,
            key=(
                lambda item: (
                    -age_priority.get(item[1], 0),
                    -item[0],
                    item[1],
                )
                if age_organization_search
                else (-item[0], item[1])
            ),
        )
        if item[1] != fallback
    ]
    ordered = ranked[: max(0, limit - 1 if fallback else limit)]
    results = [
        {
            "action": action,
            "signature": _catalog_signature(
                domain, action, strict_generic=strict_generic
            ),
            **_search_contract_metadata(domain, action, strict_generic=strict_generic),
        }
        for _score, action in ordered
    ]
    if fallback:
        results.append(
            {
                "action": fallback,
                "signature": _catalog_signature(
                    domain, fallback, strict_generic=strict_generic
                ),
                **_search_contract_metadata(
                    domain, fallback, strict_generic=strict_generic
                ),
            }
        )
    return results


def _search_multi_app_actions(
    *,
    query: str,
    exact_query_tokens: set[str],
    query_tokens: set[str],
    instruction_tokens: set[str],
    error_tokens: set[str],
    limit: int,
    excluded_actions: set[str],
    excluded_routes: set[tuple[str, str]],
    query_requests_command: bool,
    active_workspace_files: bool,
    strict_generic: bool,
    semantic_actions: Iterable[str],
    completed_routes: Iterable[tuple[str, str]],
) -> list[dict[str, Any]]:
    if limit <= 0 or "adapter.call" in excluded_actions:
        return []

    # A fully qualified route in a catalog query is an explicit operation
    # choice. Keep that search atomic so the generic adapter.call surface does
    # not make a small model choose among unrelated downstream actions. A
    # successful call can be repeated for another file, so completion history
    # must not exclude an explicitly requested route.
    # Natural-language queries continue through the ranked multi-route search.
    completed_route_set = set(completed_routes)
    explicit_routes = [
        (adapter, action)
        for adapter in DOWNSTREAM_ADAPTER_DOMAINS
        for action in public_actions(adapter)
        if (adapter, action) not in excluded_routes
        and not (
            action == "image.extract_text_batch"
            and instruction_tokens.intersection(VISUAL_IMAGE_TOKENS)
            and instruction_tokens.intersection(VISUAL_IDENTIFICATION_TOKENS)
        )
        and re.search(
            rf"(?<![\w.]){re.escape(adapter)}(?:\.|\s+){re.escape(action)}(?![\w.])",
            query.casefold(),
        )
    ]
    if explicit_routes:
        route_domain, action = explicit_routes[0]
        return [
            {
                "action": "adapter.call",
                "adapter": route_domain,
                "downstream_action": action,
                **_search_contract_metadata(
                    "multi_apps",
                    "adapter.call",
                    route_domain=route_domain,
                    route_action=action,
                    strict_generic=strict_generic,
                ),
                "signature": (
                    "Call adapter.call with top-level arguments "
                    f'{{"adapter": {route_domain!r}, "action": {action!r}, '
                    '"payload": {"params": <object matching the downstream contract>}}}. '
                    "Downstream contract: "
                    f"{_catalog_signature(route_domain, action, strict_generic=strict_generic)}"
                ),
            }
        ]

    matches: list[tuple[int, str, str]] = []
    semantic = set(semantic_actions)
    search_tokens = exact_query_tokens | query_tokens | instruction_tokens
    # Opening a file changes the active application document. Background
    # readers and current-document inspectors cannot satisfy that operation,
    # even when their nouns overlap the larger task more strongly.
    file_activation_search = bool(
        re.search(r"(?:^|\bto\s+)(?:open|activate|load)\b", query.casefold().strip())
        and (
            exact_query_tokens.intersection(
                {"file", "document", "workbook", "spreadsheet", "presentation", "path"}
            )
            or re.search(r"\.(?:docx?|odt|xlsx?|ods|pptx?|odp|pdf)\b", query.casefold())
        )
    )
    editor_activation_search = bool(
        file_activation_search
        and exact_query_tokens.intersection({"vscode", "vs_code", "editor", "code"})
    )
    attachment_save_search = bool(
        exact_query_tokens.intersection({"attachment", "attachments"})
        and exact_query_tokens.intersection({"download", "save", "extract"})
    )
    thunderbird_filter_search = bool(
        search_tokens.intersection({"filter", "filters", "rule", "rules"})
        and search_tokens.intersection(
            {
                "auto",
                "automatic",
                "automatically",
                "configure",
                "create",
                "forward",
                "move",
                "route",
                "routes",
                "routing",
            }
        )
    )
    audio_extraction_search = bool(
        search_tokens.intersection({"audio", "music", "soundtrack"})
        and search_tokens.intersection({"convert", "extract", "save"})
    )
    current_audio_search = bool(
        audio_extraction_search
        and search_tokens.intersection({"current", "playing", "vlc"})
    )
    frame_extraction_search = bool(
        search_tokens.intersection({"frame", "snapshot"})
        and search_tokens.intersection({"time", "timestamp", "video", "vlc"})
    )
    presentation_background_search = bool(
        "background" in search_tokens
        and search_tokens.intersection(
            {"deck", "impress", "page", "presentation", "slide"}
        )
        and search_tokens.intersection(
            {"frame", "image", "photo", "picture", "snapshot"}
        )
    )
    presentation_audio_search = bool(
        search_tokens.intersection({"audio", "music", "sound", "soundtrack"})
        and search_tokens.intersection({"deck", "impress", "presentation", "slide"})
    )
    # A document-to-speaker-notes request is a generic composition of existing
    # public primitives. Keep the required discovery, read, inspect, mutate,
    # and persistence routes together in the small search result so the model
    # does not have to guess which owning Adapter to search for next.
    presentation_notes_transfer_search = bool(
        search_tokens.intersection(
            {
                "note",
                "notes",
                "remark",
                "remarks",
                "speaker",
                "speaking",
                "presenter",
            }
        )
        and search_tokens.intersection(
            {"deck", "impress", "page", "powerpoint", "presentation", "slide", "slides"}
        )
        and search_tokens.intersection(
            {"doc", "docx", "document", "desktop", "file", "files", "word"}
        )
        and search_tokens.intersection(
            {
                "add",
                "complete",
                "copy",
                "fill",
                "insert",
                "place",
                "put",
                "read",
                "transfer",
                "use",
                "write",
            }
        )
    )
    image_crop_search = bool(
        search_tokens.intersection(
            {"crop", "cropped", "cropping", "trim", "trimmed", "trimming"}
        )
        and search_tokens.intersection(
            {"bmp", "image", "jpeg", "jpg", "photo", "picture", "png", "webp"}
        )
    )
    visual_image_identification_search = bool(
        search_tokens.intersection(VISUAL_IMAGE_TOKENS)
        and search_tokens.intersection(VISUAL_IDENTIFICATION_TOKENS)
    )
    visual_image_rename_search = bool(
        visual_image_identification_search
        and search_tokens.intersection(VISUAL_RENAME_TOKENS)
    )
    file_organization_search = bool(
        search_tokens.intersection(FILE_ORGANIZATION_TOKENS)
        and search_tokens.intersection(FILE_ORGANIZATION_ACTION_TOKENS)
    )
    age_organization_search = bool(
        search_tokens.intersection(AGE_ORGANIZATION_TOKENS)
        and search_tokens.intersection(AGE_ORGANIZATION_ACTION_TOKENS)
        and search_tokens.intersection({"file", "files"})
    )
    text_file_document_search = bool(
        search_tokens.intersection({"file", "files", "text", "txt"})
        and query_tokens.intersection(
            {"append", "combine", "concatenate", "join", "merge"}
        )
        and search_tokens.intersection({"doc", "docx", "document", "word", "writer"})
    )
    document_content_search = bool(
        search_tokens.intersection({"doc", "docx", "document", "odt", "rtf", "writer"})
        and search_tokens.intersection(
            {"content", "details", "guideline", "guidelines", "inspect", "read", "requirements", "text"}
        )
        and not exact_query_tokens.intersection({"vs_code", "vscode", "editor", "code"})
        and not exact_query_tokens.intersection({"find", "locate", "search"})
    )
    staged_document_read_search = bool(
        document_content_search
        and not file_activation_search
        and not attachment_save_search
        and exact_query_tokens.intersection({"docx", "odt", "rtf"})
        and query_tokens.intersection(
            {"content", "details", "guideline", "guidelines", "inspect", "read", "requirements"}
        )
        and exact_query_tokens.intersection({"desktop", "directory", "downloads", "folder", "path"})
    )
    # A saved-document query starts with discovery and reading, but the
    # workflow may continue with a generic operation such as export or
    # archiving. Once the structured reader has completed, keep the next
    # catalog search open to those later public routes instead of trapping it
    # in the discovery/read pair.
    document_reader_completed = (
        "libreoffice_writer",
        "document.read_file",
    ) in set(completed_routes)
    if document_reader_completed:
        document_content_search = False
    document_packaging_search = bool(
        document_reader_completed
        and exact_query_tokens.intersection(
            {"archive", "bundle", "compress", "compression", "pack", "package", "zip"}
        )
    )
    document_pdf_export_search = bool(
        query_tokens.intersection({"convert", "export", "save", "write"})
        and exact_query_tokens.intersection({"pdf"})
        and search_tokens.intersection({"doc", "docx", "document", "odt", "writer"})
    )
    terminal_window_capture_search = bool(
        search_tokens.intersection({"capture", "screenshot", "snapshot"})
        and search_tokens.intersection({"command", "commandline", "shell", "terminal"})
        and search_tokens.intersection({"save", "store", "write"})
    )
    active_workspace_search = bool(
        (
            active_workspace_files
            and query_tokens.intersection(
                {
                    "file",
                    "files",
                    "project",
                    "workspace",
                    "combine",
                    "concatenate",
                    "join",
                    "merge",
                }
            )
        )
        or (
            "workspace" in query_tokens
            and query_tokens.intersection({"file", "files", "project", "vscode"})
        )
        or (
            exact_query_tokens.intersection({"editor", "vscode", "vs_code"})
            and exact_query_tokens.intersection({"file", "files", "source"})
        )
    )
    literal_file_edit_search = bool(
        exact_query_tokens.intersection({"replace", "substitute"})
        and "literal" in exact_query_tokens
        and ("/" in query or exact_query_tokens.intersection({"file", "files", "txt"}))
        and not exact_query_tokens.intersection({"writer", "docx", "odt"})
    )
    pdf_split_search = _pdf_split_intent(search_tokens)
    desktop_association_search = _desktop_association_intent(search_tokens)
    # A generic multi-application workflow that brings files from a directory
    # into a spreadsheet needs filesystem discovery before the spreadsheet
    # mutation.  Keep this based on operation words and application-neutral
    # nouns so the catalog does not infer a task-specific answer.
    file_to_table_search = bool(
        search_tokens.intersection({"file", "files", "folder", "directory"})
        and search_tokens.intersection(
            {"sheet", "spreadsheet", "workbook", "table"}
        )
        and search_tokens.intersection(
            {"add", "append", "enter", "import", "populate", "record", "update"}
        )
    )
    save_workbook_search = bool(
        exact_query_tokens.intersection({"save", "saving"})
        and query_tokens.intersection(
            {"workbook", "spreadsheet", "sheet", "calc"}
        )
    )

    for route_domain in DOWNSTREAM_ADAPTER_DOMAINS:
        available = set(public_actions(route_domain))
        available.difference_update(FORBIDDEN_DATASET_ACTIONS)
        for action in available:
            if action in excluded_actions or (route_domain, action) in excluded_routes:
                continue
            if (
                route_domain == "thunderbird"
                and action == "filters.configure"
                and not thunderbird_filter_search
            ):
                continue
            if (
                route_domain == "os"
                and action
                in {"desktop.applications.inspect", "desktop.mime_associations.set"}
                and not desktop_association_search
                and action not in semantic
            ):
                continue
            if (
                route_domain == "os"
                and action in {"pdf.outline.inspect", "pdf.pages.extract"}
                and not pdf_split_search
                and action not in semantic
            ):
                continue
            if (
                visual_image_identification_search
                and route_domain == "os"
                and action == "image.extract_text_batch"
            ):
                continue
            action_tokens = _action_tokens(route_domain, action)
            contract_tokens = _tokens(
                _catalog_signature(route_domain, action, strict_generic=strict_generic)
            )
            score = (
                100 * len(exact_query_tokens.intersection(action_tokens))
                + 10 * len(exact_query_tokens.intersection(contract_tokens))
                + 5 * len(query_tokens.intersection(action_tokens))
                + len(query_tokens.intersection(contract_tokens))
                + 4 * len(instruction_tokens.intersection(action_tokens))
                + len(instruction_tokens.intersection(contract_tokens))
                + 2 * len(error_tokens.intersection(action_tokens))
                + len(error_tokens.intersection(contract_tokens))
                + (20 if action in semantic else 0)
            )
            if query_requests_command and action == "command.run":
                score += 400
            if file_activation_search and (route_domain, action) == (
                ("vs_code", "editor.open_file")
                if editor_activation_search
                else ("os", "desktop.open_path")
            ):
                score += 20_000
            if attachment_save_search:
                score += {
                    ("thunderbird", "attachments.save"): 20_000,
                    ("thunderbird", "messages.query"): 19_000,
                }.get((route_domain, action), 0)
            # An exact public action named in a query is more precise than
            # workflow-level word overlap (e.g. document.save in a project).
            # Keep alternatives for natural-language or compound queries.
            if re.search(
                rf"(?<![\w.]){re.escape(action)}(?![\w.])", query.casefold()
            ):
                score += 10_000
            if (
                route_domain == "thunderbird"
                and action == "filters.configure"
                and thunderbird_filter_search
            ):
                score += 500
            if image_crop_search:
                score += {
                    ("gimp", "image.crop"): 5000,
                    ("os", "filesystem.find"): 4000,
                    ("os", "command.run"): 3000 if query_requests_command else 0,
                }.get((route_domain, action), 0)
            if visual_image_identification_search:
                score += {
                    ("os", "filesystem.find"): 6000,
                    ("os", "desktop.open_path"): 5900,
                }.get((route_domain, action), 0)
            if visual_image_rename_search:
                score += {
                    ("os", "filesystem.rename"): 5800,
                }.get((route_domain, action), 0)
            if file_organization_search:
                score += {
                    ("os", "filesystem.find"): 3500,
                    ("os", "filesystem.rename"): 3400,
                }.get((route_domain, action), 0)
            if age_organization_search:
                score += {
                    ("os", "filesystem.find"): 1_400,
                    ("os", "archive.compress_file"): 1_300,
                    ("os", "filesystem.rename"): 1_200,
                    ("os", "filesystem.create_directory"): 1_100,
                }.get((route_domain, action), 0)
            if text_file_document_search:
                score += {
                    ("vs_code", "file.read_text"): 5000,
                    ("os", "filesystem.find"): 4500,
                    ("libreoffice_writer", "document.append_paragraphs"): 4000,
                    ("libreoffice_writer", "document.set_font"): 1000,
                    ("libreoffice_writer", "document.save"): 1000,
                }.get((route_domain, action), 0)
            if staged_document_read_search:
                next_route = (
                    ("libreoffice_writer", "document.read_file")
                    if ("os", "filesystem.find") in completed_route_set
                    else ("os", "filesystem.find")
                )
                if (route_domain, action) != next_route:
                    continue
                score += 7000
            elif document_content_search:
                score += {
                    ("os", "filesystem.find"): 5000,
                    ("libreoffice_writer", "document.read_file"): 6000,
                }.get((route_domain, action), 0)
            if document_packaging_search:
                score += {
                    ("os", "archive.create_zip"): 5000,
                    ("os", "archive.extract_zip"): 100,
                }.get((route_domain, action), 0)
            if document_pdf_export_search:
                # An earlier open_path may have opened a directory or another
                # file. It is not evidence that the export source is active.
                # Offer explicit saved-file and active-document operations;
                # the model must select the source semantics and arguments.
                export_routes = {
                    ("libreoffice_writer", "document.export_file_pdf"): 6500,
                    ("libreoffice_writer", "document.export_pdf"): 6000,
                }
                if (route_domain, action) not in export_routes:
                    continue
                score += export_routes[(route_domain, action)]
            if audio_extraction_search:
                score += {
                    ("vlc", "media.extract_audio"): 800,
                    ("vlc", "playback.status"): 500 if current_audio_search else 100,
                }.get((route_domain, action), 0)
            if frame_extraction_search:
                score += {
                    ("vlc", "media.extract_frame"): 800,
                    ("vlc", "playback.status"): 200,
                }.get((route_domain, action), 0)
            if presentation_background_search:
                score += {
                    ("libreoffice_impress", "slide.set_background"): 800,
                    ("libreoffice_impress", "presentation.inspect"): 100,
                }.get((route_domain, action), 0)
            if presentation_audio_search:
                score += {
                    ("libreoffice_impress", "audio.insert"): 800,
                    ("libreoffice_impress", "presentation.inspect"): 100,
                }.get((route_domain, action), 0)
            if presentation_notes_transfer_search:
                score += {
                    ("os", "filesystem.find"): 6000,
                    ("libreoffice_writer", "document.read_file"): 5500,
                    ("libreoffice_impress", "presentation.inspect"): 5600,
                    ("libreoffice_impress", "slide.set_notes"): 5200,
                    ("libreoffice_impress", "presentation.save"): 4800,
                }.get((route_domain, action), 0)
            if terminal_window_capture_search:
                score += {
                    ("os", "terminal.show_output"): 5000,
                    ("os", "window.capture"): 5000,
                }.get((route_domain, action), 0)
            if active_workspace_search and (
                route_domain,
                action,
            ) == ("vs_code", "workspace.find_files"):
                score += 5000
            if (
                active_workspace_search
                and "open" in exact_query_tokens
                and (route_domain, action) == ("vs_code", "editor.open_file")
            ):
                score += 5200
            if literal_file_edit_search and (route_domain, action) == ("vs_code", "file.replace_literal"):
                score += 6000
            if desktop_association_search:
                score += {
                    ("os", "desktop.applications.inspect"): 5000,
                    ("os", "desktop.mime_associations.set"): 4500,
                }.get((route_domain, action), 0)
            if pdf_split_search:
                score += {
                    ("os", "pdf.outline.inspect"): 5000,
                    ("os", "filesystem.find"): 4500,
                    ("os", "pdf.pages.extract"): 4000,
                }.get((route_domain, action), 0)
            if file_to_table_search:
                score += {
                    ("os", "filesystem.find"): 6000,
                    ("os", "image.extract_text_batch"): 5600,
                    ("libreoffice_calc", "workbook.inspect"): 5000,
                    ("libreoffice_calc", "range.read"): 4900,
                    ("libreoffice_calc", "range.write"): 4800,
                    ("libreoffice_calc", "workbook.save"): 4700,
                }.get((route_domain, action), 0)
            if save_workbook_search:
                score += {
                    ("libreoffice_calc", "workbook.save"): 4050,
                    ("libreoffice_calc", "workbook.inspect"): 4500,
                    ("libreoffice_calc", "range.read"): 3500,
                }.get((route_domain, action), 0)
            if score:
                matches.append((score, route_domain, action))

    ranked = sorted(matches, key=lambda item: (-item[0], item[1], item[2]))
    if visual_image_identification_search:
        visual_routes = {
            ("os", "filesystem.find"),
            ("os", "desktop.open_path"),
            ("os", "filesystem.rename"),
        }
        ranked = [item for item in ranked if item[1:] in visual_routes]
    return [
        {
            "action": "adapter.call",
            "adapter": route_domain,
            "downstream_action": action,
            **_search_contract_metadata(
                "multi_apps",
                "adapter.call",
                route_domain=route_domain,
                route_action=action,
                strict_generic=strict_generic,
            ),
            "signature": (
                "Call adapter.call with top-level arguments "
                f'{{"adapter": {route_domain!r}, "action": {action!r}, '
                '"payload": {"params": <object matching the downstream contract>}}}. '
                "Downstream contract: "
                f"{_catalog_signature(route_domain, action, strict_generic=strict_generic)}"
            ),
        }
        for _score, route_domain, action in ranked[:limit]
    ]


def _independent_schema_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _independent_schema_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_independent_schema_copy(item) for item in value]
    return copy.deepcopy(value)


def _strict_generic_schema_overlay(
    domain: str, action: str, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Apply only generic model-facing constraints for strict episodes.

    Legacy task-aware runs retain their historical permissive contracts.  The
    strict overlay removes ambiguity classes that otherwise reach the guest:
    invalid export defaults, filename extensions used as filter identifiers,
    directory URLs for file exports, and duplicate shape names.
    """
    if domain == "libreoffice_writer" and action == "document.export_pdf":
        properties = parameters["properties"]
        properties.pop("same_basename", None)
        properties["path"]["pattern"] = r"^(?:/|~/).+\.[Pp][Dd][Ff]$"
        parameters["required"] = ["path"]
        parameters.pop("oneOf", None)
    elif domain == "libreoffice_calc" and action == "chart.create":
        properties = parameters["properties"]
        # UNO's rows/columns terminology is easy to reverse. The strict small-model
        # surface delegates that representational choice to the reusable Adapter;
        # non-strict callers retain the explicit expert overrides.
        properties["data_row_source"] = {
            "type": "string",
            "enum": ["auto"],
            "description": (
                "Use auto so the Adapter infers whether series occupy rows or columns "
                "from the source-range geometry."
            ),
        }
        if "source_sheet" not in parameters["required"]:
            parameters["required"].append("source_sheet")
    elif domain == "os" and action == "filesystem.rename":
        # Keep the model-facing mutation contract small. The adapter still
        # accepts source_query/new_name and search_roots for compatibility,
        # but exposing those legacy alternatives creates an unnecessary
        # oneOf decision for small tool-calling models.
        properties = parameters["properties"]
        parameters["properties"] = {
            key: properties[key]
            for key in ("source", "destination", "replace")
            if key in properties
        }
        parameters["required"] = ["source", "destination"]
        parameters.pop("oneOf", None)
    elif domain == "libreoffice_calc" and action == "workbook.export":
        url_schema = parameters["properties"]["url"]
        url_schema.update(
            {
                "pattern": r"^(?:file://)?/.+\.(?:csv|pdf)$",
                "description": (
                    "Absolute output file path or file URL ending in .csv or .pdf. "
                    "It must contain a filename; never use / or file:/// because those "
                    "identify directories. When sharing the workbook basename, copy the "
                    "title returned by workbook.inspect and change only the extension."
                ),
            }
        )
        # Raw LibreOffice filter strings are an expert escape hatch, not part of
        # the deterministic default-export contract presented to a small model.
        parameters["properties"].pop("filter_options", None)
    elif (domain, action) in {
        ("libreoffice_calc", "workbook.save"),
        ("libreoffice_impress", "presentation.save"),
    }:
        # Save keeps the current format (or infers Save As from the URL). Format
        # export has its own public action. A raw UNO filter name is redundant
        # for the normal save contract and easily confused with an extension.
        parameters["properties"].pop("filter_name", None)
    elif domain == "libreoffice_impress" and action == "shape.fit_to_slide":
        parameters["properties"]["mode"]["description"] = (
            "cover preserves aspect ratio and fills the whole slide, cropping overflow; "
            "contain preserves the whole image and may leave margins; stretch fills the "
            "slide by distorting the image. For fill/cover plus preserved proportions, "
            "choose cover. With cover, negative x/y or dimensions beyond the slide are "
            "expected centered clipping; do not retry for that geometry."
        )
    return parameters


def _adapter_tool(
    domain: str, action: str, *, strict_generic: bool = False
) -> dict[str, Any]:
    direct_schema = DIRECT_ACTION_SCHEMAS.get(domain, {}).get(action)
    if direct_schema is not None:
        parameters = {
            "type": "object",
            "properties": _independent_schema_copy(direct_schema["properties"]),
            "required": list(direct_schema.get("required", [])),
            "additionalProperties": False,
        }
        for keyword in ("allOf", "anyOf", "oneOf", "not"):
            if keyword in direct_schema:
                parameters[keyword] = _independent_schema_copy(direct_schema[keyword])
        if strict_generic:
            parameters = _strict_generic_schema_overlay(domain, action, parameters)
        argument_note = (
            "Pass adapter, action, and payload as top-level tool arguments. "
            "Put the downstream action params inside payload.params."
            if domain == "multi_apps" and action == "adapter.call"
            else "Pass the documented action params directly as top-level tool arguments."
        )
    else:
        target_schema: dict[str, Any] = {
            "type": "object",
            "description": "Optional target selector for browser actions.",
        }
        if domain == "chrome":
            target_schema.update(
                {
                    "minProperties": 1,
                    "properties": {
                        "target_id": {"type": "string", "minLength": 1},
                        "url": {"type": "string", "minLength": 1},
                        "title": {"type": "string", "minLength": 1},
                        "index": {"type": "integer", "minimum": 0},
                    },
                    "additionalProperties": False,
                    "description": (
                        "Exact Chrome tab selector copied from tab.list. Multiple fields "
                        "must identify the same unique tab."
                    ),
                }
            )
        parameters = {
            "type": "object",
            "properties": {
                "params": {
                    "type": "object",
                    "description": "Action-specific params from the exact contract.",
                },
                "target": target_schema,
                "document": {
                    "type": "object",
                    "description": "Optional document selector; omit for active document.",
                },
                "verify": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "Optional documented Adapter verification checks.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 120000,
                },
            },
            "required": [],
            "additionalProperties": False,
        }
        if domain == "chrome" and action in CHROME_TARGET_REQUIRED_ACTIONS:
            parameters["required"].append("target")
        argument_note = "Pass action params inside the params object."
    contract = (
        direct_schema.get("description", "")
        if direct_schema is not None
        else f"Exact request contract: {_catalog_signature(domain, action, strict_generic=strict_generic)}."
    )
    return {
        "type": "function",
        "function": {
            "name": tool_name(action),
            "description": " ".join(
                part
                for part in (
                    f"Execute the deterministic {domain}.{action} Adapter action.",
                    contract,
                    argument_note,
                    "Use only documented parameter names.",
                )
                if part
            ),
            "parameters": parameters,
        },
    }


def build_tools(
    domain: str,
    actions: Iterable[str],
    include_gui: bool,
    *,
    include_control_tools: bool = True,
    strict_generic: bool = False,
    gui_request: bool = False,
) -> list[dict[str, Any]]:
    """Build the model-visible tools from the single public catalog.

    Strict discovery stages may intentionally expose only a deterministic
    inspection Adapter action.  Keeping control tools out of that first
    request prevents a small model from selecting ``propose_done`` or GUI
    before it has observed application state; the default remains unchanged
    for callers that need the complete control surface.
    """
    tools = [
        _adapter_tool(domain, action, strict_generic=strict_generic)
        for action in actions
    ]
    if not include_control_tools:
        return tools
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "tools_search",
                "description": (
                    (
                        "Adapter tools are revealed by this search in a multi-application "
                        "task. Search for the intended operation to receive its callable "
                        "API and parameter schema; an initial GUI-only surface does not "
                        "mean that no API exists. "
                        if domain == "multi_apps"
                        else ""
                    )
                    + "Search the public action catalog when the exposed actions are insufficient; "
                    "this does not execute a command or inspect application state. Read-only. "
                    "After a hit, call the returned public action with model-selected arguments; "
                    "do not repeat catalog searches to discover live values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "minLength": 1}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        }
    )
    if include_gui:
        gui_name = "gui_request" if gui_request else "gui_action"
        gui_schema = GUI_REQUEST_SCHEMA if gui_request else GUI_ACTION_SCHEMA
        gui_description = (
            "Delegate exactly one visible GUI operation to the Holo visual-grounding "
            "model. Describe the target and intended operation; do not provide coordinates."
            if gui_request
            else (
                "Perform exactly one visible GUI fallback action. Use only when no exposed or searchable "
                "Adapter action can deterministically perform the required operation."
            )
        )
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": gui_name,
                    "description": gui_description,
                    "parameters": copy.deepcopy(gui_schema),
                },
            }
        )
    tools.extend(
        [
            {
                "type": "function",
                "function": {
                    "name": "propose_done",
                    "description": "Propose completion only after structural read-back proves the requested state.",
                    "parameters": copy.deepcopy(COMPLETION_ARGUMENT_SCHEMA),
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "fail_task",
                    "description": "Stop only when the task is genuinely infeasible after concrete attempts.",
                    "parameters": {
                        "type": "object",
                        "properties": {"reason": {"type": "string", "minLength": 1}},
                        "required": ["reason"],
                        "additionalProperties": False,
                    },
                },
            },
        ]
    )
    return tools
