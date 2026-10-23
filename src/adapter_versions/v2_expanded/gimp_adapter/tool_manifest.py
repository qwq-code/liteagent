from __future__ import annotations

from typing import Any


STRICT_ACTION_PARAM_SCHEMAS: dict[str, dict[str, Any]] = {
    "image.inspect": {
        "properties": {
            "path": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Exact local path or file URL of the image to inspect. Use "
                    "filesystem.find first when only a basename or unknown location is given."
                ),
            }
        },
        "required": ["path"],
    },
    "image.adjust": {
        "description": (
            "Adjust brightness, contrast, or saturation of a local image and save "
            "the adjusted image to a different file. Supply at least one adjustment; "
            "omitted adjustments are zero. This edits the image file, not an "
            "image object's appearance inside a presentation."
        ),
        "properties": {
            "input_path": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Exact local source image path, such as a PNG or JPEG; not "
                    "a presentation path or a file URL. Discover an unknown "
                    "location with filesystem.find first."
                ),
            },
            "output_path": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Destination for the adjusted image: a different file from "
                    "input_path. Use PNG, JPEG, or XCF. Existing output files "
                    "are replaced; the source is retained for verification."
                ),
            },
            "brightness": {
                "type": "number",
                "minimum": -127,
                "maximum": 127,
                "description": (
                    "Brightness offset: positive values brighten, negative values "
                    "darken, and zero leaves brightness unchanged. This is GIMP's "
                    "-127 to 127 scale, not a percent or target brightness. "
                    "Fractional values are truncated toward zero."
                ),
            },
            "contrast": {
                "type": "number",
                "minimum": -127,
                "maximum": 127,
                "description": (
                    "Contrast offset: positive increases, negative decreases, "
                    "zero leaves it unchanged. GIMP's -127 to 127 scale, not "
                    "percent; fractional values are truncated toward zero."
                ),
            },
            "saturation": {
                "type": "number",
                "minimum": -100,
                "maximum": 100,
                "description": (
                    "Relative saturation adjustment: positive increases color "
                    "intensity, negative decreases it, zero leaves it unchanged, "
                    "and -100 removes color. Fractional amounts are supported."
                ),
            },
            "open_in_gui": {
                "type": "boolean",
                "description": (
                    "Defaults to false. True saves a GIMP project and opens it; "
                    "use an XCF output_path in that mode. For a PNG or JPEG "
                    "export, omit this field or set it to false."
                ),
            },
        },
        "required": ["input_path", "output_path"],
        "anyOf": [
            {"required": ["brightness"]},
            {"required": ["contrast"]},
            {"required": ["saturation"]},
        ],
    },
    "image.crop": {
        "properties": {
            "input_path": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Exact local path or file URL of the source raster image. Use "
                    "filesystem.find first when only a basename or unknown location is given."
                ),
            },
            "output_path": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "Destination raster path. A basename with no directory is saved beside "
                    "input_path; it is not saved in the process home or working directory."
                ),
            },
            "unit": {
                "type": "string",
                "enum": ["percent", "pixels"],
                "description": (
                    "How all four edge amounts are interpreted. In percent mode, 20 means "
                    "twenty percent of that edge's image dimension, not 0.20."
                ),
            },
            "top": {
                "type": "number",
                "minimum": 0,
                "description": "Amount removed from the top edge; defaults to 0.",
            },
            "right": {
                "type": "number",
                "minimum": 0,
                "description": "Amount removed from the right edge; defaults to 0.",
            },
            "bottom": {
                "type": "number",
                "minimum": 0,
                "description": "Amount removed from the bottom edge; defaults to 0.",
            },
            "left": {
                "type": "number",
                "minimum": 0,
                "description": "Amount removed from the left edge; defaults to 0.",
            },
            "overwrite": {
                "type": "boolean",
                "default": False,
                "description": "Replace an existing destination only when true.",
            },
        },
        "required": ["input_path", "output_path", "unit"],
        "anyOf": [
            {"required": ["top"]},
            {"required": ["right"]},
            {"required": ["bottom"]},
            {"required": ["left"]},
        ],
    },
}
