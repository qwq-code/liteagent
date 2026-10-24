from __future__ import annotations

import copy
import re
from typing import Any

from .geometry_contract import ATOMIC_GEOMETRY_FIELDS, MEASUREMENT_UNITS, SHAPE_EDGES
from .image_contract import (
    IMAGE_PATH_OR_FILE_URL_PATTERN,
)
from .table_contract import TABLE_GEOMETRY_FIELDS, TABLE_PLACEMENTS


NONEMPTY_STRING = {"type": "string", "minLength": 1}
POSITIVE_SIZE = {"type": "integer", "minimum": 1}
SLIDE_INDEX = {
    "type": "integer",
    "minimum": 0,
    "description": (
        "Zero-based slide index: slide = display_slide_number - 1. "
        "Human slide 1 is index 0; copy slide from presentation.inspect."
    ),
}
SLIDE_NUMBER = {
    "type": "integer",
    "minimum": 1,
    "description": (
        "Human-facing one-based slide number. Use this for a slide number stated in "
        "the instruction or copied from presentation.inspect tool_target."
    ),
}
SLIDE_INDICES = {
    "type": "array",
    "minItems": 1,
    "maxItems": 100,
    "uniqueItems": True,
    "items": SLIDE_INDEX,
}


def _case_insensitive_name_pattern(name: str) -> str:
    """Build a provider-portable pattern for the runtime's normalized names."""
    pieces: list[str] = []
    for char in name:
        if char.isspace():
            pieces.append(r"\s+")
        elif char.isascii() and char.isalpha():
            pieces.append(f"[{char.lower()}{char.upper()}]")
        else:
            pieces.append(re.escape(char))
    return "".join(pieces)


_NAMED_COLOR_PATTERN = "|".join(
    _case_insensitive_name_pattern(name)
    for name in (
        "black",
        "white",
        "red",
        "green",
        "blue",
        "yellow",
        "orange",
        "purple",
        "gray",
        "grey",
        "cyan",
        "magenta",
        "dark red 2",
    )
)
RGB_COLOR = {
    "oneOf": [
        {
            "type": "string",
            "description": (
                "Use a CSS color name or #RRGGBB. Prefer names for named colors; "
                "for example yellow=#FFFF00, red=#FF0000, and LibreOffice palette green=#00A933. "
                "Use #008000 only when CSS green is specifically requested. Integer "
                "values use packed 24-bit RGB; 65535 is cyan (#00FFFF), while "
                "yellow is 16776960 (#FFFF00)."
            ),
            "pattern": (rf"^\s*(?:#[0-9A-Fa-f]{{6}}|{_NAMED_COLOR_PATTERN})\s*$"),
        },
        {
            "type": "integer",
            "minimum": 0,
            "maximum": 16777215,
            "description": (
                "Packed 24-bit RGB decimal. Yellow is 16776960; 65535 is cyan; "
                "LibreOffice palette green is 43571 (#00A933). "
                "A color name or #RRGGBB is easier to interpret."
            ),
        },
    ]
}
SELECTOR: dict[str, Any] = {
    "type": "object",
    "description": (
        "Select one shape using fields copied from presentation.inspect. "
        "index/path are native IDs, not visual positions; the inspection declares "
        "text_shape_order separately. Copy the chosen shape's complete tool_target. "
        "A path addresses nested shapes; index alone addresses a top-level shape. "
        "You may combine path or index with name, text, or kind; every supplied field "
        "must match the same shape. Name and text match exactly; kind is a "
        "case-insensitive ShapeType substring. Without path or index, the combined "
        "fields must identify exactly one shape."
    ),
    "minProperties": 1,
    "properties": {
        "index": {"type": "integer", "minimum": 0},
        "path": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 0},
        },
        "name": {
            **NONEMPTY_STRING,
            "description": "Exact shape name returned by presentation.inspect, such as PlaceHolder 2.",
        },
        "text": {
            **NONEMPTY_STRING,
            "description": "Exact current shape text returned by presentation.inspect.",
        },
        "kind": {
            **NONEMPTY_STRING,
            "description": "Case-insensitive ShapeType substring, such as OutlinerShape or TitleTextShape.",
        },
    },
    "additionalProperties": False,
}
FIT_GRAPHIC_SELECTOR: dict[str, Any] = {
    "description": (
        "Select one graphic by an exact path or index copied from presentation.inspect."
    ),
    "oneOf": [
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "integer", "minimum": 0},
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        {
            "type": "object",
            "properties": {"index": {"type": "integer", "minimum": 0}},
            "required": ["index"],
            "additionalProperties": False,
        },
    ],
}
NATIVE_PLACEHOLDER_SELECTOR: dict[str, Any] = {
    "type": "object",
    "description": (
        "Select one top-level presentation placeholder by its exact zero-based shape index "
        "from presentation.inspect."
    ),
    "properties": {
        "index": {"type": "integer", "minimum": 0},
    },
    "required": ["index"],
    "additionalProperties": False,
}
GEOMETRY = {
    "x": {"type": "integer", "description": "Horizontal position in hundredths of a millimeter from the slide left edge."},
    "y": {"type": "integer", "description": "Vertical position in hundredths of a millimeter from the slide top edge."},
    "width": {**POSITIVE_SIZE, "description": "Raw width in hundredths of a millimeter, the same unit as presentation.inspect width."},
    "height": {**POSITIVE_SIZE, "description": "Raw height in hundredths of a millimeter, the same unit as presentation.inspect height."},
}
PHYSICAL_MEASUREMENT = {
    "type": "object",
    "description": (
        "A physical size copied from the instruction. The Adapter converts this "
        "model-selected value to LibreOffice hundredth-millimeter units."
    ),
    "properties": {
        "value": {"type": "number", "exclusiveMinimum": 0},
        "unit": {"type": "string", "enum": list(MEASUREMENT_UNITS)},
    },
    "required": ["value", "unit"],
    "additionalProperties": False,
}
TABLE_CELL = {
    "type": "object",
    "properties": {
        "row": {"type": "integer", "minimum": 0},
        "column": {"type": "integer", "minimum": 0},
        "text": {"type": "string"},
        "color": RGB_COLOR,
    },
    "required": ["row", "column"],
    "additionalProperties": False,
}
TABLE_CELL_SELECTOR = {
    "type": "object",
    "properties": {
        "row": {"type": "integer", "minimum": 0},
        "column": {"type": "integer", "minimum": 0},
    },
    "required": ["row", "column"],
    "additionalProperties": False,
}
TEXT_FORMAT_PROPERTIES = {
    "color": RGB_COLOR,
    "font_size": {"type": "number", "exclusiveMinimum": 0},
    "font_name": NONEMPTY_STRING,
    "bold": {"type": "boolean"},
    "italic": {"type": "boolean"},
    "underline": {"type": "boolean"},
    "strike": {"type": "boolean"},
    "alignment": {
        "type": "string",
        "enum": ["left", "center", "right", "justify"],
    },
}
TEXT_FORMAT_REQUIRED = [{"required": [field]} for field in TEXT_FORMAT_PROPERTIES]
TEXT_ROLE = {
    "type": "string",
    "enum": ["all", "title", "content", "body", "table", "text"],
}
TEXT_ROLE_LIST = {
    "type": "array",
    "minItems": 1,
    "uniqueItems": True,
    "items": TEXT_ROLE,
    "description": (
        "Semantic roles resolved from the live slide: title is a native title placeholder, "
        "or the unique visually dominant upper-slide heading when an imported deck has no "
        "native title placeholder; content or body is an Outliner/subtitle content "
        "placeholder; table means all table cells; text means other text boxes; all means "
        "every text-bearing shape and table. Instructions saying all or every text box use "
        "roles=['all'], not roles=['text']; use text only when ordinary non-placeholder text "
        "boxes are requested separately from titles, content placeholders, and tables. "
        "Ambiguous visual headings fail without mutation."
    ),
}
TEXT_ROLE_OVERRIDE = {
    "type": "object",
    "properties": {"roles": TEXT_ROLE_LIST, **TEXT_FORMAT_PROPERTIES},
    "required": ["roles"],
    "anyOf": TEXT_FORMAT_REQUIRED,
    "additionalProperties": False,
}
# Structured action contracts used to expose strict native tool schemas. The
# corresponding runtime validation remains in impress_adapter.schema.
STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "presentation.inspect": {
        "description": (
            "Read current slide shapes, text lines, native paragraph formatting "
            "and existing speaker notes. "
            "Text shapes include grouped children; use their full observed selector.path. "
            "Title and subtitle placeholders remain slide objects even when their text is empty. "
            "When verifying a picture-only slide, check for remaining text placeholders "
            "and other non-picture objects. "
            "text_style contains native formatting, including named alignment. "
            "bold is true/false (null when unknown); bold_weight is UNO weight, "
            "where 100 is normal and 150 is bold. "
            "For work on particular pages, supply slides to read only those pages "
            "and keep their full detail. Indices are zero-based; human page 1 is index 0. "
            "Omit slides to read the whole presentation. slide_count is the total "
            "document count; inspected_slides identifies the returned pages."
        ),
        "properties": {
            "slides": {
                **SLIDE_INDICES,
                "description": "Explicit zero-based slide indices to inspect, in the requested order.",
            },
        },
        "required": [],
    },
    "presentation.create_summary_slide": {
        "description": (
            "Create one new blank summary slide from titles observed on existing slides. "
            "Pass the exact source slide indices from presentation.inspect. The Adapter "
            "copies their observed titles as a concise list, adds a title, and verifies "
            "the new slide contains the selected items. It does not invent slide content."
        ),
        "properties": {
            "slides": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "uniqueItems": True,
                "items": SLIDE_INDEX,
                "description": "Existing zero-based source slide indices copied from presentation.inspect.",
            },
            "index": {
                "type": "integer",
                "minimum": 0,
                "description": "Insertion index; omit to append the summary slide.",
            },
            "title": {
                **NONEMPTY_STRING,
                "description": "Optional heading; defaults to Summary Slide.",
            },
        },
        "required": ["slides"],
        "additionalProperties": False,
    },
    "presentation.set_page_size": {
        "description": (
            "Set the canvas size of every slide and master in the presentation. "
            "Supply explicit width and height in 1/100 mm (100 = 1 mm). "
            "Portrait means height > width; landscape means width > height. "
            "Read current dimensions with presentation.inspect. This changes only "
            "the canvas, not shape positions, sizes or content. Save separately "
            "with presentation.save."
        ),
        "properties": {
            "width": {
                "type": "integer", "minimum": 1, "maximum": 2147483647,
                "description": "Canvas width in 1/100 mm.",
            },
            "height": {
                "type": "integer", "minimum": 1, "maximum": 2147483647,
                "description": "Canvas height in 1/100 mm.",
            },
        },
        "required": ["width", "height"],
    },
    "presentation.export": {
        "properties": {
            "format": {
                "type": "string",
                "enum": ["pptx", "odp", "pdf", "png", "jpg"],
                "description": (
                    "Output representation. It must match the destination extension: "
                    "pptx=.pptx, odp=.odp, pdf=.pdf, png=.png, and jpg=.jpg or .jpeg."
                ),
            },
            "url": {
                **NONEMPTY_STRING,
                "pattern": (
                    r"^.+\.([Pp][Pp][Tt][Xx]|[Oo][Dd][Pp]|[Pp][Dd][Ff]|"
                    r"[Pp][Nn][Gg]|[Jj][Pp][Ee]?[Gg])$"
                ),
                "description": (
                    "Exact local destination path or file URL. Keep its extension "
                    "consistent with format; for example format=pdf uses report.pdf, "
                    "while format=png uses preview.png."
                ),
            },
            "slide": {
                **SLIDE_INDEX,
                "description": "Zero-based slide index for PNG or JPEG export.",
            },
            "pixel_width": POSITIVE_SIZE,
            "pixel_height": POSITIVE_SIZE,
        },
        "required": ["format", "url"],
    },
    "audio.insert": {
        "description": (
            "Insert one audio object on the selected slide from an existing local file. "
            "The result reads back that object's media URL. Playback across slides, "
            "looping and slide-transition sound require separate presentation settings; "
            "this action does not configure them or save the presentation."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "path": {
                **NONEMPTY_STRING,
                "description": (
                    "Exact local audio path, including an absolute path, ~/ path, "
                    "or local file:// URL. File URL percent escapes are decoded once."
                ),
            },
            **GEOMETRY,
        },
        "required": ["slide", "path"],
    },
    "shape.fit_to_slide": {
        "description": (
            "Resize only the explicitly selected picture to the slide. Match its "
            "observed content and geometry to the instruction using presentation.inspect "
            "and the screenshot; cover does not choose a picture or change other pictures."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": FIT_GRAPHIC_SELECTOR,
            "mode": {
                "type": "string",
                "enum": ["cover", "contain", "stretch"],
                "description": (
                    "cover preserves aspect ratio and fills the whole slide, cropping overflow; "
                    "contain preserves the whole image and may leave margins; stretch fills the "
                    "slide by distorting the image. Choose cover when proportions must be kept. "
                    "With cover, negative x/y or a width/height beyond the slide is expected "
                    "because the image is centered and clipped; do not retry for that geometry."
                ),
            },
        },
        "required": ["slide", "selector", "mode"],
    },
    "master.set_page_number": {
        "description": (
            "Set the automatic slide/page-number field on one presentation master or "
            "all masters. This does not format an ordinary text box and master is not a "
            "slide number. Omit master to update every master."
        ),
        "properties": {
            "master": {
                "type": "integer",
                "minimum": 0,
                "description": (
                    "Optional zero-based presentation-master index; omit to update all masters."
                ),
            },
            "color": {
                **RGB_COLOR,
                "description": (
                    "Automatic page-number field color. Use the exact named color from "
                    "the instruction when one is given."
                ),
            },
            "visible": {
                "type": "boolean",
                "description": "Show (true) or hide (false) the automatic number field.",
            },
        },
        "required": [],
    },
    "settings.set": {
        "properties": {
            "key": {
                "type": "string",
                "enum": ["auto_save", "presenter_screen", "left_panel"],
            },
            "value": {"type": "boolean"},
            "minutes": {"type": "integer", "minimum": 1},
        },
        "required": ["key", "value"],
    },
    "shape.create_text": {
        "properties": {
            "slide": SLIDE_INDEX,
            "text": {"type": "string"},
            "name": NONEMPTY_STRING,
            **GEOMETRY,
        },
        "required": ["slide", "text"],
    },
    "shape.delete": {
        "description": (
            "Delete one observed shape. Supply the zero-based slide and a selector "
            "copied from that same slide's inspection. Deletion can shift index/path "
            "addresses: use an observed unique name or inspect that slide again before "
            "selecting the next object. The result identifies the object removed."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": SELECTOR,
        },
        "required": ["slide", "selector"],
    },
    "shape.insert_image": {
        "description": (
            "Insert one local image into one slide. Supply slide_number as the human-facing "
            "one-based number, slide as the zero-based index, or both only when "
            "slide_number equals slide plus one. Pass a physical width or height from the instruction as a "
            "measurement object without converting it; the Adapter converts mm, cm, or "
            "inches to LibreOffice hundredth-millimeter geometry and verifies the inserted "
            "shape. Explicit integer geometry remains available for callers that already "
            "have LibreOffice coordinates. Omitted position defaults to the slide origin."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "slide_number": SLIDE_NUMBER,
            "path": {
                **NONEMPTY_STRING,
                "pattern": IMAGE_PATH_OR_FILE_URL_PATTERN,
                "description": (
                    "Exact absolute local image path, ~/ path, or local file URL selected "
                    "from the instruction or live file discovery. Do not invent or rename it."
                ),
            },
            **GEOMETRY,
            "width_measurement": PHYSICAL_MEASUREMENT,
            "height_measurement": PHYSICAL_MEASUREMENT,
        },
        "required": ["path"],
        "allOf": [
            {
                "anyOf": [
                    {"required": ["slide"]},
                    {"required": ["slide_number"]},
                ]
            },
            {"not": {"required": ["width", "width_measurement"]}},
            {"not": {"required": ["height", "height_measurement"]}},
        ],
    },
    "shape.export_image": {
        "description": (
            "Export one observed embedded source bitmap to a PNG or JPEG file. "
            "This does not apply the shape's on-slide brightness or crop effects. Use "
            "presentation.inspect for its zero-based slide and exact selector. "
            "An embedded picture may have no filesystem path until this export; "
            "pass the returned output_path to a file-based image tool such as GIMP "
            "to edit the exported image."
        ),
        "properties": {
            "slide": {
                **SLIDE_INDEX,
                "description": (
                    "Zero-based slide index copied from presentation.inspect; "
                    "the second slide is 1."
                ),
            },
            "selector": SELECTOR,
            "output_path": {
                **NONEMPTY_STRING,
                "pattern": r"^.+\.([Pp][Nn][Gg]|[Jj][Pp][Ee]?[Gg])$",
                "description": (
                    "Exact destination image path or local file URL, for example "
                    "/home/user/Desktop/picture.png. This exports the selected embedded "
                    "picture itself, not a rendering of the whole slide."
                ),
            },
            "overwrite": {
                "type": "boolean",
                "description": "Replace an existing destination; defaults to true.",
            },
        },
        "required": ["slide", "selector", "output_path"],
    },
    "shape.format_text": {
        "description": (
            "Copy one inspected text shape's complete tool_target (slide and selector), "
            "then add the desired formatting. "
            "The selector identifies a whole text shape, not an individual paragraph. "
            "For character, bullet, or indent changes to only part of that shape, "
            "pass lines or match_text. lines selects the inspected zero-based text "
            "line indices; match_text selects every exact literal occurrence in the "
            "shape. Omitting both formats all text in the shape. "
            "alignment applies to the whole shape. The response alignment is native "
            "whole-shape read-back, not an echo of the requested value."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": SELECTOR,
            **TEXT_FORMAT_PROPERTIES,
            "bullet": {"type": "boolean"},
            "level": {"type": "integer", "minimum": 0},
            "left_margin": {"type": "integer", "minimum": 0},
            "first_line_indent": {"type": "integer"},
            "match_text": NONEMPTY_STRING,
            "lines": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "integer", "minimum": 0},
                "description": (
                    "Zero-based newline-delimited text-line indices from the inspected "
                    "shape's lines array, including interior blank lines. These are not "
                    "screen-wrapped lines. Use either lines or match_text."
                ),
            },
        },
        "required": ["slide", "selector"],
        "anyOf": [
            {"required": [field]}
            for field in (
                *TEXT_FORMAT_PROPERTIES,
                "bullet",
                "level",
                "left_margin",
                "first_line_indent",
            )
        ],
    },
    "slide.format_text_roles": {
        "description": (
            "Format live text on exactly one zero-based slide by semantic role, without "
            "shape names, paths, or GUI selection. Only supplied properties change. Base "
            "formatting applies to roles first; optional overrides then apply in array order, "
            "which supports a shared all-text format plus a role-specific difference. Use "
            "slides.format_text_roles when the same rule targets several slides."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "roles": TEXT_ROLE_LIST,
            **TEXT_FORMAT_PROPERTIES,
            "color": {
                **RGB_COLOR,
                "description": (
                    "Font color for every selected semantic role. For all text boxes or "
                    "all text on one slide, pass roles=['all']; when the instruction names "
                    "a color, pass that exact name instead of guessing another RGB value."
                ),
            },
            "overrides": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": TEXT_ROLE_OVERRIDE,
                "description": (
                    "Optional role-specific formatting applied after the base rule. Each "
                    "override changes only its supplied properties."
                ),
            },
        },
        "required": ["slide", "roles"],
        "anyOf": TEXT_FORMAT_REQUIRED,
    },
    "slide.set_role_text": {
        "description": (
            "Replace the text of exactly one live semantic text role on one zero-based "
            "slide and optionally apply only the supplied formatting. The Adapter resolves "
            "the role from the current presentation, rejects zero or multiple matches before "
            "mutation, and verifies text and formatting by read-back. Use this instead of a "
            "shape selector when the instruction names a title or another unique text role."
        ),
        "properties": {
            "slide": {
                **SLIDE_INDEX,
                "description": "Zero-based slide index; slide 1 is 0 and slide 14 is 13.",
            },
            "role": {
                "type": "string",
                "enum": ["title", "content", "body", "text"],
                "description": (
                    "One unique live semantic role. body aliases content. The Adapter fails "
                    "closed if the role is absent or ambiguous."
                ),
            },
            "text": {
                "type": "string",
                "minLength": 1,
                "description": "Exact replacement text selected from the instruction.",
            },
            **TEXT_FORMAT_PROPERTIES,
        },
        "required": ["slide", "role", "text"],
    },
    "slides.format_text_roles": {
        "description": (
            "Apply one shared semantic-role text-format rule atomically to several explicitly "
            "selected zero-based slides. Pass every target in slides and all shared style "
            "properties in this one call. The Adapter resolves live roles and preflights every "
            "slide before changing any of them. Use slide.format_text_roles for one slide."
        ),
        "properties": {
            "slides": {
                **SLIDE_INDICES,
                "description": (
                    "Unique zero-based slide indices that receive the same role-format "
                    "rules; use this for an instruction that names multiple slides."
                ),
            },
            "roles": TEXT_ROLE_LIST,
            **TEXT_FORMAT_PROPERTIES,
            "color": {
                **RGB_COLOR,
                "description": (
                    "Font color for every selected semantic role. For all text boxes or "
                    "all text on one slide, pass roles=['all']; when the instruction names "
                    "a color, pass that exact name instead of guessing another RGB value."
                ),
            },
            "overrides": {
                "type": "array",
                "minItems": 1,
                "maxItems": 8,
                "items": TEXT_ROLE_OVERRIDE,
                "description": (
                    "Optional role-specific formatting applied after the base rule. Each "
                    "override changes only its supplied properties."
                ),
            },
        },
        "required": ["slides", "roles"],
        "anyOf": TEXT_FORMAT_REQUIRED,
    },
    "shape.set_fill": {
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": SELECTOR,
            "color": RGB_COLOR,
            "transparency": {"type": "integer", "minimum": 0, "maximum": 100},
        },
        "required": ["slide", "selector", "color"],
    },
    "shape.set_geometry": {
        "description": (
            "Move or resize one shape selected from presentation.inspect. For an "
            "instruction to place a shape at a slide edge, pass edge instead of "
            "guessing x or y; the Adapter derives the exact coordinate from the live "
            "slide and shape bounds. When a size is stated in mm, cm, or inches, pass "
            "width_measurement or height_measurement without converting units yourself. "
            "Use width or height only for explicit LibreOffice hundredth-millimeter "
            "geometry. Supply slide_number as the natural one-based number shown to users, "
            "slide as the legacy zero-based index, or both only when slide_number equals "
            "slide plus one. "
            "Edge mode and numeric or measured geometry are mutually exclusive."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "slide_number": SLIDE_NUMBER,
            "selector": SELECTOR,
            **GEOMETRY,
            "width_measurement": PHYSICAL_MEASUREMENT,
            "height_measurement": PHYSICAL_MEASUREMENT,
            "edge": {
                "type": "string",
                "enum": list(SHAPE_EDGES),
                "description": (
                    "Align the selected shape flush with this slide edge while "
                    "preserving its size and orthogonal coordinate."
                ),
            },
        },
        "required": ["selector"],
        "oneOf": [
            {
                "required": ["edge"],
                "not": {
                    "anyOf": [
                        {"required": [field]}
                        for field in (
                            *GEOMETRY,
                            "width_measurement",
                            "height_measurement",
                        )
                    ],
                },
            },
            {
                "anyOf": [
                    {"required": [field]}
                    for field in (*GEOMETRY, "width_measurement", "height_measurement")
                ],
                "not": {"required": ["edge"]},
            },
        ],
        "allOf": [
            {
                "anyOf": [
                    {"required": ["slide"]},
                    {"required": ["slide_number"]},
                ]
            },
            {"not": {"required": ["width", "width_measurement"]}},
            {"not": {"required": ["height", "height_measurement"]}},
        ],
    },
    "shape.write_text": {
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": SELECTOR,
            "text": {"type": "string"},
        },
        "required": ["slide", "selector", "text"],
    },
    "shape.write_text_native": {
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": NATIVE_PLACEHOLDER_SELECTOR,
            "text": {"type": "string"},
            "replace": {"type": "boolean"},
        },
        "required": ["slide", "selector", "text"],
    },
    "slide.create": {
        "description": (
            "Insert a new slide. index is its insertion position, not navigation to an "
            "existing slide; omit index to append. Native layout codes: 20 = blank, "
            "0 = title and subtitle placeholders. Omit layout to keep the native default."
        ),
        "properties": {
            "index": {
                **SLIDE_INDEX,
                "description": "Zero-based insertion position for the new slide; omit to append.",
            },
            "layout": {"type": "integer", "minimum": 0},
        },
        "required": [],
    },
    "slides.create_from_images": {
        "description": (
            "Create one blank slide per observed image and insert that image in order. "
            "Set replace_existing_slides=true when the request asks for a new image-only "
            "presentation from the current template; this removes the template pages only "
            "after every new slide and image has been created successfully. Save separately."
        ),
        "properties": {
            "image_paths": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {
                    **NONEMPTY_STRING,
                    "pattern": IMAGE_PATH_OR_FILE_URL_PATTERN,
                },
                "description": "Ordered list of exact local image paths observed from the instruction or filesystem discovery.",
            },
            "replace_existing_slides": {
                "type": "boolean",
                "description": "Whether to replace all current slides with the new image-only slides.",
            },
            "fit_mode": {
                "type": "string",
                "enum": ["original", "cover", "contain", "stretch"],
                "default": "original",
            },
        },
        "required": ["image_paths", "replace_existing_slides"],
        "additionalProperties": False,
    },
    "slide.delete": {
        "properties": {"slide": SLIDE_INDEX},
        "required": ["slide"],
    },
    "slide.move": {
        "description": (
            "Reorder one whole slide/page within the presentation deck. This changes the "
            "slide sequence; never use it to move an image, table, title, textbox, or "
            "other object inside a slide."
        ),
        "properties": {
            "slide": SLIDE_INDEX,
            "index": SLIDE_INDEX,
        },
        "required": ["slide", "index"],
    },
    "slide.set_notes": {
        "description": (
            "Replace the entire speaker-notes text of one slide. Read its existing "
            "notes with presentation.inspect and preserve completed notes that the "
            "instruction does not ask to change. When transferring existing notes "
            "or a script, read the instruction's specified source and use its original "
            "text; do not generate a summary of the slide content."
        ),
        "properties": {
            "slide": {
                "type": "integer",
                "minimum": 0,
                "description": "Zero-based slide index.",
            },
            "text": {
                "type": "string",
                "description": (
                    "Exact speaker-note text to write. When the requested note copies "
                    "existing slide content such as its title, call presentation.inspect "
                    "first and pass the observed text."
                ),
            },
        },
        "required": ["slide", "text"],
    },
    "slide.set_transition": {
        "properties": {
            "slide": SLIDE_INDEX,
            "transition": {"type": "string", "enum": ["none", "fade", "dissolve"]},
        },
        "required": ["slide", "transition"],
    },
    "table.create": {
        "properties": {
            "slide": SLIDE_INDEX,
            "rows": POSITIVE_SIZE,
            "columns": POSITIVE_SIZE,
            "placement": {
                "type": "string",
                "enum": sorted(TABLE_PLACEMENTS),
                "default": "auto",
                "description": (
                    "auto (default) replaces the single empty content placeholder and "
                    "inherits its position and width when no geometry is supplied; "
                    "otherwise it uses standalone defaults. content_placeholder requires "
                    "exactly one empty content placeholder. custom always retains existing "
                    "placeholders and uses explicit or standalone-default geometry."
                ),
            },
            **GEOMETRY,
        },
        "required": ["slide", "rows", "columns"],
        "allOf": [
            {
                "if": {
                    "properties": {
                        "placement": {"const": "content_placeholder"},
                    },
                    "required": ["placement"],
                },
                "then": {
                    "not": {
                        "anyOf": [
                            {"required": [field]}
                            for field in sorted(TABLE_GEOMETRY_FIELDS)
                        ]
                    }
                },
            }
        ],
    },
    "table.format_text": {
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": SELECTOR,
            "cells": {
                "type": "array",
                "minItems": 1,
                "items": TABLE_CELL_SELECTOR,
            },
            **TEXT_FORMAT_PROPERTIES,
        },
        "required": ["slide", "selector"],
        "anyOf": TEXT_FORMAT_REQUIRED,
    },
    "table.write": {
        "properties": {
            "slide": SLIDE_INDEX,
            "selector": SELECTOR,
            "shape": {"type": "integer", "minimum": 0},
            "cells": {"type": "array", "items": TABLE_CELL},
        },
        "required": ["slide", "cells"],
    },
    "table.replace_row": {
        "description": (
            "Replace one complete row in the unique live table on a slide. The Adapter "
            "recursively resolves the table from current document state, rejects zero or "
            "multiple matches and dimension mismatches before mutation, then reads the row back."
        ),
        "properties": {
            "slide_number": SLIDE_NUMBER,
            "row_number": {
                "type": "integer",
                "minimum": 1,
                "description": "Human-facing one-based table row number.",
            },
            "values": {
                "type": "array",
                "minItems": 1,
                "maxItems": 100,
                "items": {"type": "string"},
                "description": (
                    "Complete left-to-right replacement row. Its length must equal the "
                    "live table column count."
                ),
            },
        },
        "required": ["slide_number", "row_number", "values"],
    },
}

# The compatibility endpoint remains available to existing clients. New tools
# expose one geometry operation, so alignment cannot accidentally resize a shape.
_GEOMETRY_ATOM_DESCRIPTIONS = {
    "shape.align_to_slide": (
        "Align one observed shape to a slide edge. Supply only the slide reference, "
        "selector and edge. The Adapter reads live bounds to calculate position; "
        "width, height and the orthogonal position remain unchanged."
    ),
    "shape.move": (
        "Move one observed shape to x and/or y in hundredths of a millimeter. "
        "Omitted coordinates and both dimensions remain unchanged. "
        "Use shape.align_to_slide for a slide edge and shape.resize for size changes."
    ),
    "shape.resize": (
        "Resize one observed shape without moving it. Supply width/height in native "
        "hundredths of a millimeter, or width_measurement/height_measurement with "
        "physical mm, cm or in units. Omitted dimensions remain unchanged. "
        "For a size stated in physical units, copy that measurement directly."
    ),
}
for _action, _fields in ATOMIC_GEOMETRY_FIELDS.items():
    _owner = STRICT_ACTION_PARAM_SCHEMAS["shape.set_geometry"]
    _schema = {
        "description": _GEOMETRY_ATOM_DESCRIPTIONS[_action],
        "properties": {key: copy.deepcopy(_owner["properties"][key])
                       for key in ("slide", "slide_number", "selector", *_fields)},
        "required": ["selector"],
        "allOf": [{"anyOf": [{"required": ["slide"]}, {"required": ["slide_number"]}]}],
    }
    if _action == "shape.align_to_slide":
        _schema["required"].append("edge")
    else:
        _schema["anyOf"] = [{"required": [field]} for field in _fields]
    if _action == "shape.resize":
        _schema["allOf"].extend([
            {"not": {"required": ["width", "width_measurement"]}},
            {"not": {"required": ["height", "height_measurement"]}},
        ])
    STRICT_ACTION_PARAM_SCHEMAS[_action] = _schema
