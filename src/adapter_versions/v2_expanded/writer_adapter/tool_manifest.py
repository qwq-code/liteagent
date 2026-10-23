from __future__ import annotations

from typing import Any

from .schema import (
    BOOKMARK_NAME_PATTERN,
    REFERENCE_DISPLAY_MODES,
    RGB_COLOR_PATTERN,
    TAB_STOP_ALIGNMENTS,
    TAB_STOP_UNITS,
    TABLE_DELIMITER_PATTERN,
    TEXT_FIND_MAX_LITERAL_LENGTH,
    TEXT_FIND_MAX_RESULTS,
)


CHARACTER_FORMAT_PROPERTIES = {
    "font_size": {
        "type": "number",
        "minimum": 1,
        "maximum": 1000,
        "description": "Font size in points.",
    },
    "bold": {"type": "boolean"},
    "italic": {"type": "boolean"},
    "script": {
        "type": "string",
        "enum": ["normal", "subscript", "superscript"],
        "description": "Character position; normal is neither raised nor lowered.",
    },
}


PARAGRAPH_FORMAT_FIELDS = {
    "line_spacing": {
        "type": "number",
        "exclusiveMinimum": 0,
        "description": (
            "Line-spacing multiplier: use 1 for single, 1.5 for one-and-a-half, "
            "and 2 for double spacing."
        ),
    },
    "alignment": {
        "type": "string",
        "enum": ["left", "right", "center", "justify"],
        "description": (
            "Whole-paragraph alignment, independent of font family and size. "
            "This is separate from tab_stops[].alignment, which aligns the text "
            "following a tab at its stop."
        ),
    },
    "font_size": {
        "type": "number",
        "exclusiveMinimum": 0,
        "description": (
            "Character size in points, for example 12 for 12 pt. This does not "
            "change the font family."
        ),
    },
    "strikethrough": {
        "type": "boolean",
        "description": "Whether the selected paragraph text is struck through.",
    },
    "tab_stops": {
        "type": "array",
        "description": (
            "Replace the explicit tab stops on each selected paragraph; [] clears them. "
            "Positions are distances from the paragraph's left margin. This changes "
            "formatting only, not text. A tab character separates text runs; the stop "
            "aligns the following run, while preceding text keeps paragraph alignment. "
            "For local tab insertion, use text.find_replace with a short unique observed "
            "anchor and a JSON \\t escape for an actual tab; text outside the anchor is "
            "preserved. document.inspect returns page_layouts with page body widths and "
            "margins in mm; do not guess a right-edge position. Read-back reports positions in mm."
        ),
        "items": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "position": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "value": {"type": "number", "minimum": 0},
                        "unit": {"type": "string", "enum": list(TAB_STOP_UNITS)},
                    },
                    "required": ["value", "unit"],
                },
                "alignment": {
                    "type": "string",
                    "enum": list(TAB_STOP_ALIGNMENTS),
                    "description": (
                        "Alignment of text after a tab, independently of paragraph alignment: "
                        "left starts at position; right ends at position; center centers "
                        "the text there; decimal places the decimal separator there. "
                        "A right tab stop does not right-align the entire paragraph."
                    ),
                },
                "decimal_character": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1,
                    "description": "Decimal separator for decimal alignment; omitted means '.'.",
                },
                "fill_character": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1,
                    "description": "Tab leader character; omitted means a space (no visible leader).",
                },
            },
            "required": ["position", "alignment"],
        },
    },
}

NONBLANK_AUTOMATIC_PARAGRAPH_SPACING = {
    "if": {
        "properties": {"blank_paragraphs_between": {"type": "integer", "minimum": 1}},
        "required": ["blank_paragraphs_between"],
    },
    "then": {
        "properties": {
            "paragraphs": {
                "items": {"type": "string", "pattern": r"\S"},
            }
        }
    },
}


def rgb_color_schema(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "oneOf": [
            {"type": "string", "pattern": RGB_COLOR_PATTERN},
            {"type": "integer", "minimum": 0, "maximum": 0xFFFFFF},
        ],
    }


# Model-visible parameter contracts owned by the Adapter. Raw document indices stay
# zero-based; natural paragraph and delimited-column ordinals are explicitly one-based.
STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "document.create": {
        "description": (
            "Create and activate one empty Writer document at a new .docx or .odt path. "
            "The parent directory must exist; existing files are rejected. This creates "
            "no text or tables. Use separate append/format operations after creation. "
            "The returned identity identifies the new saved document for later edits."
        ),
        "properties": {
            "path": {"type": "string", "pattern": r"^(?:/|~/|file://(?:localhost)?/).+\.(?:[dD][oO][cC][xX]|[oO][dD][tT])$"},
        },
        "required": ["path"],
    },
    "document.inspect": {
        "description": (
            "Read the current Writer structure, including the exact table names returned "
            "in tables. If tables is empty, the document has no selectable table: do not "
            "invent a table name; use paragraph or text actions instead. Overview paragraph "
            "text is a preview; text_length is the full native character count. Before "
            "replacing a paragraph, read its live text with paragraph_start=<observed index> "
            "and paragraph_limit=1. Explicit pages return selected text before context "
            "compaction; context_truncated or ...<truncated>... means the result is still "
            "partial. Do not reconstruct missing wording. Read omitted paragraphs with "
            "paragraph_start and paragraph_limit; next_paragraph_start continues the page. "
            "Indices and text ordinals always refer to the whole document. Raw indices "
            "and paragraph_limit count blank separator paragraphs too; nonempty_ordinal "
            "counts only paragraphs containing text and is null for blank paragraphs. "
            "tab_character_offsets gives zero-based character positions of real Tabs in "
            "the full paragraph, not screen coordinates. literal_tab_escape_count counts "
            "the ordinary backslash and t characters written as \\t; those are not Tabs. "
            "footers reports native page-style footer variants and actual page_number_fields "
            "with alignment and offset; a literal digit is not a page-number field. "
            "paragraph_details.strikethrough is native read-back: true or false for uniform "
            "formatting, mixed for mixed runs, null when unknown. "
            "fonts reads native font families across body text and table cells, separately "
            "for western, Asian and complex scripts. names lists fonts of uniform text "
            "objects; mixed_text_objects and unknown_text_objects count objects whose "
            "font cannot be summarized as one known name."
        ),
        "properties": {
            "paragraph_start": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based raw paragraph index at which to start the page, including "
                    "blank paragraphs. Defaults to 0 when paragraph_limit is supplied."
                ),
            },
            "paragraph_limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 12,
                "description": (
                    "Maximum raw paragraphs in this page, including blank separators, "
                    "1 to 12. This is not a count of paragraphs containing text. Defaults to 12 when "
                    "paragraph_start is supplied. Use 1 for focused live text before editing. "
                    "Omit both parameters for the usual preview overview."
                ),
            },
        },
        "required": [],
    },
    "document.read_file": {
        "description": (
            "Read body text and table cells from one local DOC, DOCX, ODT or RTF file "
            "without opening a visible window or modifying the file. Paragraphs and "
            "table rows are separated by newlines, table cells by tabs. This reads the "
            "saved file, not unsaved editor changes, headers, footers or image text. "
            "It does not change the active Writer document or select this file for "
            "later editing or export. "
            "For an already-open document's live formatting, use document.inspect."
        ),
        "properties": {
            "path": {
                "type": "string",
                "pattern": r"^(?:/|~/|file://(?:localhost)?/).+",
                "description": "Exact observed absolute path, ~/ path or local file URL.",
            },
            "start_char": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based character offset in extracted text; omitted means 0. "
                    "Use the observed next_start_char for the next page."
                ),
            },
            "max_chars": {
                "type": "integer",
                "minimum": 1,
                "maximum": 12000,
                "description": "Maximum text characters to return; omitted means 2000.",
            },
        },
        "required": ["path"],
    },
    "document.extract_images": {
        "properties": {
            "source_path": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^(?:/|~/|file://(?:localhost)?/).+",
                "description": (
                    "Exact absolute, ~/, or local file URL of an existing DOCX or ODT "
                    "document. Embedded images are resolved in main-document reference order."
                ),
            },
            "output_directory": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^(?:/|~/|file://(?:localhost)?/).+",
                "description": (
                    "Absolute, ~/, or local file URL of the destination directory. Missing "
                    "directories are created and exact output paths are returned."
                ),
            },
            "selection": {
                "type": "string",
                "enum": ["first", "all"],
                "default": "all",
                "description": (
                    "Use first when the instruction asks for the first embedded image; use all "
                    "to export every image in document reference order. Defaults to all."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "default": True,
                "description": "Replace generated image files with the same names. Defaults to true.",
            },
        },
        "required": ["source_path", "output_directory"],
    },
    "document.export_file_pdf": {
        "description": (
            "Export one explicitly selected saved Writer file to one PDF. "
            "source_path identifies the input file; output_path identifies the PDF. "
            "Reads a private disk snapshot without activating, saving, or closing any "
            "open editor document. Unsaved editor changes are not included; save them "
            "first, or use document.export_pdf for the current open document. "
            "Returns the actual source and output identities."
        ),
        "properties": {
            "source_path": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^(?:/|~/).+",
                "description": "Exact observed absolute path of the saved input document.",
            },
            "output_path": {
                "type": "string",
                "minLength": 1,
                "pattern": r"^(?:/|~/).+\.[Pp][Dd][Ff]$",
                "description": "Explicit output PDF path; must differ from the source file.",
            },
            "preserve_soft_wrap_spaces": {
                "type": "boolean",
                "default": True,
                "description": "Preserve DOCX paragraph spaces at visual soft line wraps.",
            },
        },
        "required": ["source_path", "output_path"],
    },
    "document.export_pdf": {
        "description": (
            "Export the currently open Writer document to PDF. path is an output "
            "destination, not a source file to open. document.read_file does not "
            "activate its source. Open or activate the intended source in Writer "
            "before exporting; document.inspect reports the current document identity."
        ),
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "pattern": "\\.[Pp][Dd][Ff]$",
                "description": (
                    "Explicit destination path ending in .pdf for the exported PDF. "
                    "Do not use the source .docx path. Use this when the requested "
                    "output directory or filename differs from the active document."
                ),
            },
            "same_basename": {
                "type": "boolean",
                "const": True,
                "description": (
                    "Set true to export beside the active saved document with the same "
                    "filename stem and a .pdf extension."
                ),
            },
            "preserve_soft_wrap_spaces": {
                "type": "boolean",
                "default": True,
                "description": (
                    "For DOCX sources, preserve source paragraph spaces that LibreOffice "
                    "may omit at visual soft line wraps. Defaults to true; set false only "
                    "when the unnormalized LibreOffice PDF text stream is required."
                ),
            },
        },
        "required": [],
        "oneOf": [
            {"required": ["path"]},
            {"required": ["same_basename"]},
        ],
    },
    "document.add_page_numbers": {
        "properties": {
            "position": {
                "type": "string",
                "enum": ["bottom_left", "bottom_center", "bottom_right"],
                "description": (
                    "Footer position for the page-number field on every active page style."
                ),
            },
        },
        "required": ["position"],
    },
    "document.set_font": {
        "description": (
            "Set font families in body text and table cells. The returned font_name is the "
            "request; fonts is native read-back, also available through document.inspect."
        ),
        "properties": {
            "font_name": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Exact font-family name, such as Liberation Serif, to apply "
                    "throughout every text object. This does not change point size; "
                    "use paragraph formatting when the instruction asks for font size."
                ),
            },
        },
        "required": ["font_name"],
    },
    "document.transform_case": {
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["lower", "title"],
                "description": (
                    "Case transformation for every paragraph in the active Writer "
                    "document, including table-cell paragraphs. Use lower to convert "
                    "all text to lowercase. Use title to capitalize the first "
                    "alphabetic character of each whitespace-delimited token while "
                    "preserving the remaining characters."
                ),
            },
        },
        "required": ["mode"],
    },
    "document.remove_highlighting": {
        "description": (
            "Remove character background highlighting from every text run in the active "
            "Writer document. This action takes no arguments."
        ),
        "properties": {},
        "required": [],
    },
    "paragraph.set_format": {
        "description": (
            "Apply one explicit paragraph format to the selected paragraphs, or all body "
            "paragraphs when selectors are omitted. Raw indices include blank separators; "
            "use nonempty_ordinals for positions among paragraphs containing text. "
            "Does not split or rewrite text."
        ),
        "properties": {
            "indices": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": 0},
                "description": (
                    "Exact zero-based raw paragraph indices from document.inspect, "
                    "including blank separators. Consecutive raw indices may not identify "
                    "consecutive text paragraphs; check each observed nonempty_ordinal."
                ),
            },
            "nonempty_ordinals": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": 1},
                "description": (
                    "One-based ordinals among nonempty body paragraphs, for example [1, 2] "
                    "for the first two paragraphs containing text."
                ),
            },
            **PARAGRAPH_FORMAT_FIELDS,
        },
        "required": [],
        "allOf": [
            {
                "not": {
                    "required": ["indices", "nonempty_ordinals"],
                }
            },
            {"anyOf": [{"required": [field]} for field in PARAGRAPH_FORMAT_FIELDS]},
        ],
    },
    "paragraph.clear_text": {
        "description": (
            "Clear the text of every explicitly selected body paragraph in one call. "
            "The model chooses every index; this action does not select paragraphs by "
            "their content. Paragraph boundaries and paragraph formatting remain, so "
            "raw indices stay stable and cleared paragraphs become empty. Other "
            "paragraphs are unchanged. There is no default selection."
        ),
        "properties": {
            "indices": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer", "minimum": 0},
                "description": (
                    "Required exact zero-based raw paragraph indices from current "
                    "document.inspect or text.find paragraph_index observations. "
                    "Raw indices count blank paragraphs too."
                ),
            },
        },
        "required": ["indices"],
    },
    "paragraph.apply_numbering": {
        "description": (
            "Apply native Writer numbering copied from one explicit numbered paragraph to "
            "one explicit target paragraph. This does not insert, remove, or rewrite text."
        ),
        "properties": {
            "source_index": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based raw index of the existing numbered paragraph whose native "
                    "numbering rules are copied."
                ),
            },
            "target_index": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based raw index of the paragraph that receives the numbering rules."
                ),
            },
            "level": {
                "type": "integer",
                "minimum": 0,
                "maximum": 9,
                "description": "Explicit zero-based Writer list level for the target.",
            },
            "restart": {
                "type": "boolean",
                "description": (
                    "False continues the source numbering; true starts a new sequence at "
                    "start_value."
                ),
            },
            "start_value": {
                "type": "integer",
                "minimum": 1,
                "description": "Required only when restart is true.",
            },
        },
        "required": ["source_index", "target_index", "level", "restart"],
        "allOf": [
            {
                "if": {"properties": {"restart": {"const": True}}},
                "then": {"required": ["start_value"]},
                "else": {"not": {"required": ["start_value"]}},
            }
        ],
    },
    "paragraph.replace_text": {
        "description": (
            "Replace one explicitly selected Writer paragraph with model-authored paragraph "
            "strings. This replaces the entire paragraph: omitted words are deleted. "
            'Use paragraphs:[""] to clear that paragraph\'s text while keeping its paragraph boundary. '
            "For a local character insertion or replacement, use text.find_replace with "
            "a unique observed anchor instead of retyping the whole paragraph. "
            "The Adapter performs no sentence segmentation or text generation. "
            "Choose either automatic spacing between non-blank strings or explicit blank "
            "strings with automatic spacing set to zero."
        ),
        "properties": {
            "index": {
                "type": "integer",
                "minimum": 0,
                "description": "Exact zero-based raw paragraph index from document.inspect.",
            },
            "paragraphs": {
                "type": "array",
                "minItems": 1,
                "maxItems": 256,
                "items": {"type": "string"},
                "description": (
                    "Exact replacement paragraphs in output order. Every string is supplied "
                    "by the model; no hidden splitting or rewriting is performed. Blank or "
                    "whitespace-only strings require blank_paragraphs_between to be zero or "
                    "omitted."
                ),
            },
            "blank_paragraphs_between": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": (
                    "Number of empty paragraphs inserted between replacements. A positive "
                    "value requires every paragraphs item to be non-blank; use zero with "
                    "explicit blank strings."
                ),
            },
        },
        "required": ["index", "paragraphs"],
        "allOf": [NONBLANK_AUTOMATIC_PARAGRAPH_SPACING],
    },
    "paragraph.split": {
        "description": (
            "Split one Writer paragraph after one exact text anchor or an ordered list "
            "of anchors. For several boundaries in the same paragraph, pass them together "
            "in after_text so paragraph indices do not change between calls. Each anchor "
            "matches its first occurrence after the previous boundary. Only native "
            "paragraph breaks are inserted; existing characters and spaces stay unchanged. "
            "The caller selects every boundary; sentences are not detected automatically. "
            "Returns the observed parts and each new right_paragraph_index. "
            "After splitting, the old index refers only to the left part. "
            "The original paragraph's text now spans the returned parts; when a right "
            "part still contains text, inspecting only the old index omits that text."
        ),
        "properties": {
            "index": {
                "type": "integer",
                "minimum": 0,
                "description": "Zero-based raw paragraph index from the current observation.",
            },
            "after_text": {
                "anyOf": [
                    {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": TEXT_FIND_MAX_LITERAL_LENGTH,
                    },
                    {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 32,
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": TEXT_FIND_MAX_LITERAL_LENGTH,
                        },
                    },
                ],
                "description": (
                    'Exact case-sensitive literal or ordered list, e.g. [";", ";"] '
                    "splits after the first two semicolons, not every semicolon. Search "
                    "starts at the paragraph beginning, then resumes immediately after "
                    "each match. Include existing spaces in an anchor to leave those "
                    "spaces on the left. All anchors must match before any edit is made."
                ),
            },
            "blank_paragraphs_between": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": (
                    "Empty paragraphs at each selected boundary: 0 for adjacent paragraphs "
                    "(default), 1 for one empty paragraph. Existing characters are preserved."
                ),
            },
        },
        "required": ["index", "after_text"],
    },
    "bookmark.create": {
        "description": (
            "Create one native Writer bookmark over an explicit character range in one "
            "paragraph. Existing text is preserved and duplicate names fail closed. "
            "Use text.find to locate the source text and its offsets. The chosen bookmark "
            "name can then be used as the source of a cross_reference.insert field. "
            "For a cross-reference, bookmark the content being cited, such as a list entry. "
            "The place where the reference will be displayed is a separate destination."
        ),
        "properties": {
            "name": {
                "type": "string",
                "pattern": BOOKMARK_NAME_PATTERN,
                "maxLength": 40,
                "description": "Caller-selected DOCX-portable bookmark name.",
            },
            "paragraph_index": {
                "type": "integer",
                "minimum": 0,
                "description": "Exact zero-based raw paragraph index from document.inspect.",
            },
            "start_offset": {
                "type": "integer",
                "minimum": 0,
                "description": "Inclusive character offset inside the selected paragraph.",
            },
            "end_offset": {
                "type": "integer",
                "minimum": 0,
                "description": "Exclusive character offset inside the selected paragraph.",
            },
            "expected_text": {
                "type": "string",
                "description": (
                    "Exact text currently occupying [start_offset, end_offset); an empty "
                    "string creates a position bookmark."
                ),
            },
        },
        "required": [
            "name",
            "paragraph_index",
            "start_offset",
            "end_offset",
            "expected_text",
        ],
    },
    "cross_reference.insert": {
        "description": (
            "Replace one explicit character range with a native Writer GetReference field "
            "that points to an existing caller-selected bookmark; surrounding text is "
            "preserved. For a new reference source, use bookmark.create first and pass its "
            "chosen name here. Use text.find to locate the destination substring: copy its "
            "paragraph_index, start_offset and end_offset, with matched_text as expected_text. "
            "The bookmark identifies the content being cited; paragraph_index and offsets "
            "identify where its reference will be displayed. Only the bookmark's source "
            "needs native numbering; the destination can remain ordinary unnumbered text. "
            "Number modes reject an unnumbered bookmark source before replacing the destination. "
            "A later native failure reports whether the original destination was restored."
        ),
        "properties": {
            "bookmark_name": {
                "type": "string",
                "pattern": BOOKMARK_NAME_PATTERN,
                "maxLength": 40,
                "description": "Exact existing bookmark name used as the reference source.",
            },
            "paragraph_index": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Zero-based raw paragraph index at the insertion destination, not the "
                    "bookmark source. Copy it from text.find or document.inspect."
                ),
            },
            "start_offset": {
                "type": "integer",
                "minimum": 0,
                "description": "Inclusive character offset of the replaced range.",
            },
            "end_offset": {
                "type": "integer",
                "minimum": 0,
                "description": "Exclusive character offset of the replaced range.",
            },
            "expected_text": {
                "type": "string",
                "description": (
                    "Exact current text in the replaced range. Use an empty string to insert "
                    "without replacing text."
                ),
            },
            "display": {
                "type": "string",
                "enum": sorted(REFERENCE_DISPLAY_MODES),
                "description": (
                    "Native reference presentation: number_no_context shows only the target "
                    "list label; number and number_full_context include list context. "
                    "These number modes read native paragraph numbering, not digits typed "
                    "in its text. paragraph.apply_numbering can copy numbering from an "
                    "existing list item to the source paragraph."
                ),
            },
        },
        "required": [
            "bookmark_name",
            "paragraph_index",
            "start_offset",
            "end_offset",
            "expected_text",
            "display",
        ],
    },
    "text.find": {
        "description": (
            "Find text by literal, current character format, or both, without modifying or "
            "saving the Writer document. For a literal-only search, supply literal, "
            "case_sensitive and max_results; omit format. "
            "For a format-only search, omit literal and use "
            'format, e.g. format={"bold":true}. Format fields describe the CURRENT text to '
            "find, not a replacement style. Results return exact matched_text, zero-based "
            "paragraph_index and half-open offsets. Format searches also return the observed "
            "format. Combine current properties to narrow remaining work, e.g. "
            'format={"bold":true,"font_size":9}; after a size change those matches leave '
            "that search. For text.set_format, copy one match's paragraph_index, start_offset, "
            "end_offset and matched_text together (matched_text becomes expected_text). "
            "Choose each range and its new formatting yourself. "
            "Literal markers and placeholders can also supply ranges for bookmark.create "
            "or cross_reference.insert."
        ),
        "properties": {
            "literal": {
                "type": "string",
                "minLength": 1,
                "maxLength": TEXT_FIND_MAX_LITERAL_LENGTH,
                "description": "Exact literal substring to locate; it is never treated as a regex.",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Required with literal: whether character case must match exactly.",
            },
            "format": {
                "type": "object",
                "description": (
                    "Optional current-format filter; omit it for a literal-only search, "
                    "never send an empty object. All supplied conditions must match. "
                    "This does not edit text."
                ),
                "properties": CHARACTER_FORMAT_PROPERTIES,
                "minProperties": 1,
                "additionalProperties": False,
            },
            "max_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": TEXT_FIND_MAX_RESULTS,
                "description": (
                    "Maximum matches returned in document order. has_more reports whether "
                    "additional matches were omitted."
                ),
            },
        },
        "required": ["max_results"],
        "anyOf": [
            {"required": ["literal", "case_sensitive"]},
            {"required": ["format"]},
        ],
        "dependentRequired": {"literal": ["case_sensitive"]},
    },
    "text.set_format": {
        "description": (
            "Set character formatting on exactly one explicit range inside one body paragraph. "
            "Only supplied formatting fields change; text and other ranges stay unchanged. "
            "Use document.inspect or text.find to locate the text first. Offsets are zero-based "
            "Python string positions: start is included, end is excluded. For example, in "
            "'value X is ready', X occupies start_offset=6, end_offset=7. "
            "expected_text is an exact precondition, not replacement text."
        ),
        "properties": {
            "paragraph_index": {
                "type": "integer",
                "minimum": 0,
                "description": "Zero-based raw body paragraph index from document.inspect or text.find.",
            },
            "start_offset": {"type": "integer", "minimum": 0},
            "end_offset": {"type": "integer", "minimum": 1},
            "expected_text": {
                "type": "string",
                "minLength": 1,
                "description": "Exact text currently inside the selected range; must match before editing.",
            },
            **CHARACTER_FORMAT_PROPERTIES,
        },
        "required": ["paragraph_index", "start_offset", "end_offset", "expected_text"],
        "additionalProperties": False,
        "anyOf": [
            {"required": [field]} for field in ("font_size", "bold", "italic", "script")
        ],
    },
    "text.find_replace": {
        "description": (
            "Replace an exact model-selected literal in the active Writer document. The "
            "model explicitly chooses the literal, replacement, match cardinality, and case policy. "
            "An empty replacement deletes the matched literal; it does not choose which "
            "matches to retain. "
            "For local insertion, copy a short unique observed anchor into find and add "
            "the new characters inside that anchor in replacement. Text outside the "
            "matched literal is not rewritten."
        ),
        "properties": {
            "find": {"type": "string", "minLength": 1},
            "replacement": {
                "type": "string",
                "description": (
                    "Exact replacement characters; an empty string deletes the matched text. "
                    "An actual CR character (JSON \\r) creates "
                    "a paragraph boundary; \\r\\r inserts an empty paragraph. LF (JSON \\n) "
                    "is not the hard-paragraph delimiter. Do not send literal backslash-r. "
                    "For insertion-only edits, retain the anchor's original characters, "
                    "including its spaces. JSON \\t inserts an actual tab character; replace "
                    "an observed separating space with it when changing that separator."
                ),
            },
            "replace_all": {
                "type": "boolean",
                "description": (
                    "False replaces only the first matching literal in document order. "
                    "True replaces every match in the whole document, not only the "
                    "last inspected paragraph. Use a unique literal for a local edit."
                ),
            },
            "case_sensitive": {"type": "boolean"},
        },
        "required": ["find", "replacement", "replace_all", "case_sensitive"],
    },
    "table.insert_at_cursor": {
        "properties": {
            "rows": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of rows in the new empty table.",
            },
            "columns": {
                "type": "integer",
                "minimum": 1,
                "description": "Number of columns in the new empty table.",
            },
            "fallback_to_last_paragraph": {
                "type": "boolean",
                "description": (
                    "Set true only when the intended insertion point is explicitly the last "
                    "body paragraph rather than the current Writer view cursor."
                ),
            },
        },
        "required": ["rows", "columns"],
    },
    "table.convert_text": {
        "description": (
            "Convert an explicit contiguous range of existing Writer body paragraphs "
            "into a table in place. Each selected paragraph becomes a row and the "
            "model-selected delimiter separates cells. Select the inclusive raw paragraph "
            "indices observed in document.inspect; do not retype the cell contents. "
            "All rows must have the same number of fields. Original spaces and text "
            "inside each field are preserved; source paragraphs are replaced by the table. "
            "This is literal delimiter conversion, not quoted CSV parsing. "
            "Use the returned table name with table.read to inspect the result."
        ),
        "properties": {
            "start_index": {
                "type": "integer",
                "minimum": 0,
                "description": "First selected zero-based raw body paragraph index, inclusive.",
            },
            "end_index": {
                "type": "integer",
                "minimum": 0,
                "description": "Last selected zero-based raw body paragraph index, inclusive.",
            },
            "delimiter": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1,
                "pattern": TABLE_DELIMITER_PATTERN,
                "description": (
                    "Exact single character separating fields, such as comma or semicolon. "
                    "NUL and emoji delimiters are not supported by Writer's native converter. "
                    "For tab-separated text pass one actual Tab character, not backslash-t. "
                    "Paragraph breaks already separate rows."
                ),
            },
        },
        "required": ["start_index", "end_index", "delimiter"],
    },
    "table.insert_after_text": {
        "description": (
            "Insert a new table of model-supplied values after an observed text anchor. "
            "The existing anchor and source text stay in the document. To convert "
            "existing delimited paragraphs in place without retyping their contents, "
            "use table.convert_text."
        ),
        "properties": {
            "anchor_text": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Text of the unique body paragraph after which the table belongs, "
                    "such as a section heading observed in the document or stated in the "
                    "instruction. The Adapter locates the paragraph; no GUI cursor move is needed."
                ),
            },
            "rows": {
                "type": "array",
                "minItems": 1,
                "maxItems": 200,
                "description": (
                    "Complete rectangular table matrix, including any header row. Use "
                    "strings for values whose displayed spelling, trailing zeros, or fixed "
                    "decimal places must be preserved exactly. An identical existing table "
                    "is reported with changed=false instead of being inserted again."
                ),
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {"type": ["string", "number", "boolean", "null"]},
                },
            },
            "match_mode": {
                "type": "string",
                "enum": ["exact", "contains"],
                "default": "exact",
                "description": (
                    "How anchor_text matches a body paragraph after trimming edge "
                    "whitespace. Defaults to exact; use contains only when the observed "
                    "paragraph has additional text."
                ),
            },
            "case_sensitive": {
                "type": "boolean",
                "default": False,
                "description": "Whether anchor matching is case-sensitive. Defaults to false.",
            },
        },
        "required": ["anchor_text", "rows"],
    },
    "table.read": {
        "description": (
            "Read every cell name, row_index, column_index, text, and current font color from one selected Writer "
            "table without modifying it. font_color is #RRGGBB for a uniform color, "
            "automatic for application-selected color, mixed for multiple colors, "
            "or null when formatting is unavailable. row_index increases top-to-bottom and "
            "column_index increases left-to-right; for example, A1 is column_index 1, "
            "row_index 1, while A2 is the same column and the next row. "
            "When an instruction says a word starts with something, compare only the "
            "first character of the observed text. "
            "Use this read-back to inspect formatting after table.set_cell_text_color."
        ),
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
                "description": "Exact table name returned by document.inspect.",
            },
        },
        "required": ["name"],
    },
    "table.set_cell_text_color": {
        "description": (
            "Apply one model-selected font color to an explicit homogeneous batch of Writer "
            "table cells. The Adapter never classifies cell text or expands the target list."
            " Repeated names reapply the same color; cells_changed counts distinct targets."
        ),
        "properties": {
            "name": {
                "type": "string",
                "minLength": 1,
                "description": "Exact table name returned by document.inspect.",
            },
            "cells": {
                "type": "array",
                "minItems": 1,
                "maxItems": 1024,
                "items": {"type": "string", "minLength": 1},
                "description": "Exact Writer table cell names returned by table.read.",
            },
            "color": rgb_color_schema(
                "Exact font color to apply to every selected cell. Use a six-digit "
                "#RRGGBB value when the instruction names a color; standard names are "
                "also accepted (for example, red is #FF0000 and blue is #0000FF)."
            ),
        },
        "required": ["name", "cells", "color"],
    },
    "image.insert_at_cursor": {
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Path to an existing image in the guest. Use the exact filename and "
                    "location stated in the instruction; the image is inserted at the "
                    "current Writer view cursor."
                ),
            },
        },
        "required": ["path"],
    },
    "document.append_paragraphs": {
        "description": (
            "Append explicit model-authored paragraphs to the active Writer document. "
            "Each array item becomes a separate paragraph, even with zero extra blank "
            "spacing. For concatenation without any separator, supply one string with "
            "the selected texts joined exactly, adding no spaces or line breaks. The "
            "Adapter does not derive numbering, citation text, or placement policy. Choose "
            "either automatic spacing between non-blank strings or explicit blank strings "
            "with automatic spacing set to zero."
        ),
        "properties": {
            "paragraphs": {
                "type": "array",
                "minItems": 1,
                "maxItems": 256,
                "items": {"type": "string"},
                "description": (
                    "One exact string per paragraph in append order. Separate items insert "
                    "paragraph breaks; one item is needed for an unbroken concatenation. "
                    "Blank or whitespace-only "
                    "strings require blank_paragraphs_between to be zero or omitted."
                ),
            },
            "blank_paragraphs_before": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
            },
            "blank_paragraphs_between": {
                "type": "integer",
                "minimum": 0,
                "maximum": 10,
                "description": (
                    "Number of additional empty paragraphs between appended strings. Zero "
                    "still leaves one paragraph break between items; it does not join them "
                    "without a separator. A positive "
                    "value requires every paragraphs item to be non-blank; use zero with "
                    "explicit blank strings."
                ),
            },
        },
        "required": ["paragraphs"],
        "allOf": [NONBLANK_AUTOMATIC_PARAGRAPH_SPACING],
    },
    "settings.set_default_font": {
        "description": (
            "Persist Writer's default font in the user profile and read it back from "
            "native configuration. This does not reformat or save the active document; "
            "verification describes the application setting, not the document file."
        ),
        "properties": {
            "font_name": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Exact font-family name to persist as Writer's default font, "
                    "such as Liberation Serif or Noto Sans. This changes the Writer "
                    "user-profile default and does not reformat existing document text."
                ),
            },
        },
        "required": ["font_name"],
    },
}
