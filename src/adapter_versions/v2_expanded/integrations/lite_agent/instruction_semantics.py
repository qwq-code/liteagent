"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any


from . import (
    calc_semantics,
    clipboard_path_semantics,
    filesystem_permission_semantics,
    filesystem_rename_semantics,
    git_semantics,
    impress_page_number,
    impress_table_row,
    impress_semantics,
    terminal_capture_semantics,
    terminal_output_semantics,
    vlc_semantics,
    vscode_configuration_semantics,
    workspace_open_semantics,
)
from .adapter_results import (
    a1_geometry,
    adapter_context_hint as adapter_context_hint,
    column_number,
    compact_adapter_body as compact_adapter_body,
)
from .calc_column_reorder import parse_column_reorder_intent
from .completion_policy import (
    completion_claim_contradictions as completion_claim_contradictions,
)
from .impress_background import parse_background_intent, requests_all_slide_scope
from .impress_colors import (
    CSS_BASIC_COLORS,
    LIBREOFFICE_IMPRESS_PALETTE_COLORS,
)
from .impress_image_insertion import is_sized_image_insertion_instruction
from .impress_personal_information import parse_personal_information_removal_intent
from .impress_role_formatting import parse_multislide_role_format_intent
from .impress_textboxes import parse_all_textbox_color_intent
from .strict_contracts import public_action_contract
from .thunderbird_filter_semantics import requests_filter_configuration
from .impress_role_text_update import parse_role_text_update_intent
from .writer_image_semantics import requests_single_cursor_image_insertion


REQUESTED_FILE_RE = re.compile(
    r"(?i)([\w.-]+\.(?:pptx|odp|pdf|xlsx|ods|docx|odt|png|jpe?g|xcf|mp3|wav|ogg|m4a|mp4|webm|mkv|avi|mov))"
)


REQUESTED_SHEET_RE = re.compile(
    r"(?i)(?:sheet|worksheet)(?:\s+name)?\s+(?:named|called|as)\s+"
    r"[\"']?([^\"'\s.,]+)"
)


MERGED_TEXT_REGION_RE = re.compile(
    r"(?is)\bmerge\s+cells?\s+"
    r"(\$?[A-Z]{1,3}\$?\d+\s*:\s*\$?[A-Z]{1,3}\$?\d+)"
    r"(?:(?!\bmerge\s+cells?\b).){0,160}?[\"“]([^\"”\r\n]+)[\"”]"
)


PIVOT_COUNT_RE = re.compile(
    r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+pivot\s+tables?\b"
)


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


MONTH_TOKENS = {
    "jan",
    "january",
    "feb",
    "february",
    "mar",
    "march",
    "apr",
    "april",
    "may",
    "jun",
    "june",
    "jul",
    "july",
    "aug",
    "august",
    "sep",
    "sept",
    "september",
    "oct",
    "october",
    "nov",
    "november",
    "dec",
    "december",
}


def requested_files(instruction: str) -> list[str]:
    return REQUESTED_FILE_RE.findall(instruction)


def requested_desktop_file_paths(instruction: str) -> list[str]:
    if not re.search(r"(?i)\bdesktop\b", instruction):
        return []
    return [
        f"/home/user/Desktop/{Path(filename).name}"
        for filename in requested_files(instruction)
    ]


def requested_audio_path(instruction: str) -> str | None:
    audio_paths = [
        path
        for path in requested_desktop_file_paths(instruction)
        if Path(path).suffix.casefold() in {".mp3", ".wav", ".ogg", ".m4a"}
    ]
    return audio_paths[0] if len(audio_paths) == 1 else None


def requests_presentation_audio_insertion(instruction: str) -> bool:
    """Return whether a unique Desktop audio file is requested in a deck."""

    audio_path = requested_audio_path(instruction)
    if audio_path is None or not re.search(
        r"(?i)\b(?:deck|impress|pptx?|presentation|slides?|slideshow)\b",
        instruction,
    ):
        return False

    audio_object = (
        r"(?:audio(?:\s+file)?|music|sound(?:track)?|"
        + re.escape(Path(audio_path).name)
        + r")"
    )
    non_insert_operation = (
        r"(?:captions?|convert|delete|extract|play|remove|transcrib(?:e|ing)|"
        r"transcript(?:ion)?)"
    )
    insertion_action = r"(?:add|attach|embed|include|insert|place|put)"
    insertion_result = r"(?:added|attached|embedded|included|inserted|placed|put)"
    bounded_object = rf"(?:(?!\b{non_insert_operation}\b).){{0,100}}"
    if re.search(
        rf"(?is)\b{insertion_action}\b{bounded_object}\b{audio_object}\b",
        instruction,
    ) or re.search(
        rf"(?is)\b{audio_object}\b{bounded_object}\b{insertion_result}\b",
        instruction,
    ):
        return True

    # "Use it" is accepted only when the instruction assigns an audio role;
    # the unique filename and presentation destination make the pronoun bounded.
    return bool(
        re.search(
            rf"(?is)\buse\b(?:(?!\b{non_insert_operation}\b).){{0,100}}"
            rf"\b(?:{audio_object}|it)\b(?:(?!\b{non_insert_operation}\b).){{0,80}}"
            r"\bas\b.{0,40}\b(?:audio|music|sound(?:track)?)\b",
            instruction,
        )
    )


def requested_sized_slide_image(instruction: str) -> dict[str, Any] | None:
    image_paths = [
        path
        for path in requested_desktop_file_paths(instruction)
        if Path(path).suffix.casefold() in {".png", ".jpg", ".jpeg"}
    ]
    slide_match = re.search(r"(?i)\bslide\s+(\d+)\b", instruction)
    size_match = re.search(
        r"(?i)\b(\d+(?:\.\d+)?)\s*(cm|mm|in(?:ch(?:es)?)?)\s*"
        r"(?:\*|x|×)\s*(\d+(?:\.\d+)?)\s*(cm|mm|in(?:ch(?:es)?)?)\b",
        instruction,
    )
    if (
        len(image_paths) != 1
        or slide_match is None
        or int(slide_match.group(1)) < 1
        or size_match is None
    ):
        return None

    def to_hundredth_mm(value: str, unit: str) -> int:
        normalized = unit.casefold()
        factor = 1000.0 if normalized == "cm" else 100.0
        if normalized.startswith("in"):
            factor = 2540.0
        return round(float(value) * factor)

    width = to_hundredth_mm(size_match.group(1), size_match.group(2))
    height = to_hundredth_mm(size_match.group(3), size_match.group(4))
    if width <= 0 or height <= 0:
        return None
    return {
        "slide": int(slide_match.group(1)) - 1,
        "path": image_paths[0],
        "width": width,
        "height": height,
    }


def requested_picture_heights_by_slide(
    instruction: str,
) -> dict[str, Any] | None:
    return impress_semantics.picture_height_request(instruction)


def requested_table_row_replacement(instruction: str) -> dict[str, Any] | None:
    intent = impress_table_row.parse_table_row_intent(instruction)
    if intent is None:
        return None
    return {
        "slide": intent.slide_number - 1,
        "row": intent.row_number - 1,
        "values": list(intent.values),
    }


def requested_first_textbox_alignments_by_slide(
    instruction: str,
) -> dict[str, Any] | None:
    if not re.search(r"(?i)\bfirst\s+(?:text\s*box|textbox)\b", instruction):
        return None
    matches = re.findall(
        r"(?i)\b(?:on\s+)?slide\s+(\d+)\s+(?:to\s+)?(?:the\s+)?"
        r"(left|center|right)\b",
        instruction,
    )
    if not matches:
        return None
    targets = []
    seen_slides: set[int] = set()
    for slide_text, alignment in matches:
        slide = int(slide_text)
        if slide < 1 or slide in seen_slides:
            return None
        seen_slides.add(slide)
        targets.append({"slide": slide - 1, "alignment": alignment.casefold()})
    return {"role": "first_textbox", "targets": targets}


def requested_numbered_desktop_files(instruction: str) -> list[str]:
    if not re.search(r"(?i)\bdesktop\b", instruction):
        return []
    match = re.search(
        r"(?i)\b([\w.-]*?)(\d+)\.(png|jpe?g)\s+(?:to|through|-)\s+"
        r"([\w.-]*?)(\d+)\.(png|jpe?g)\b",
        instruction,
    )
    if match is None:
        return []
    (
        first_prefix,
        first_index,
        first_extension,
        last_prefix,
        last_index,
        last_extension,
    ) = match.groups()
    start = int(first_index)
    end = int(last_index)
    if (
        first_prefix.casefold() != last_prefix.casefold()
        or first_extension.casefold() != last_extension.casefold()
        or start < 0
        or end < start
        or end - start > 100
    ):
        return []
    return [
        f"/home/user/Desktop/{first_prefix}{index}.{first_extension}"
        for index in range(start, end + 1)
    ]


def requested_blank_slide_count(instruction: str) -> int | None:
    match = re.search(
        r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+blank\s+slides?\b",
        instruction,
    )
    if match is None:
        return None
    token = match.group(1).casefold()
    return NUMBER_WORDS.get(token, int(token) if token.isdigit() else 0) or None


def requested_ordered_image_slides(instruction: str) -> dict[str, Any] | None:
    files = requested_numbered_desktop_files(instruction)
    slide_count = requested_blank_slide_count(instruction)
    if not files or slide_count != len(files):
        return None
    if not re.search(r"(?is)\bone\s+image\s+per\s+slide\b", instruction):
        return None
    if not re.search(
        r"(?i)\b(?:in order|numerical order|numeric order)\b", instruction
    ):
        return None
    return {"slide_count": slide_count, "files": files}


def requested_sheet_names(instruction: str) -> list[str]:
    return REQUESTED_SHEET_RE.findall(instruction)


def _quoted_texts(value: str) -> list[str]:
    return [
        next(group for group in match.groups() if group is not None).strip()
        for match in re.finditer(
            r'"([^"\r\n]+)"|“([^”\r\n]+)”|\'([^\'\r\n]+)\'|‘([^’\r\n]+)’',
            value,
        )
        if any(group and group.strip() for group in match.groups())
    ]


def requested_annual_percentage_change_summary(
    instruction: str,
) -> dict[str, Any] | None:
    if not (
        re.search(r"(?i)\bpercentage\b", instruction)
        and (
            re.search(
                r"(?is)\bannual\s+changes?\b.{0,80}\b(?:last|previous|prior)\s+year\b",
                instruction,
            )
            or re.search(r"(?i)\byear[- ]over[- ]year\b", instruction)
        )
    ):
        return None

    target_match = re.search(
        r"(?is)\bnew\s+(?:sheet|worksheet)\s*"
        r"(?:\(\s*)?[\"'“‘]([^\"'”’\r\n]+)[\"'”’](?:\s*\))?",
        instruction,
    ) or re.search(
        r"(?is)\b(?:new|create\s+(?:a\s+)new)\s+(?:sheet|worksheet)\s+"
        r"(?:named|called)\s+[\"'“‘]([^\"'”’\r\n]+)[\"'”’]",
        instruction,
    )
    years_match = re.search(
        r"(?i)\b(?:in|from|for)\s+(\d{4})\s+(?:to|through|thru|[-–])\s+(\d{4})\b",
        instruction,
    )
    headers_match = re.search(
        r"(?is)\b(?:with|using)\s+(?:\d+\s+)?headers?\s+(.{1,500}?)"
        r"(?=,?\s*\b(?:calculate|compute|derive)\b)",
        instruction,
    )
    columns_match = re.search(
        r"(?is)\bfor\s+the\s+(.{1,500}?)\s+columns?\b",
        instruction,
    )
    if not all((target_match, years_match, headers_match, columns_match)):
        return None

    output_headers = _quoted_texts(headers_match.group(1))
    raw_columns = columns_match.group(1).strip()
    source_headers = _quoted_texts(raw_columns)
    if not source_headers:

        def clean_list_item(value: str) -> str:
            return (
                re.sub(r"(?i)^(?:and|or)\s+", "", value.strip())
                .strip()
                .strip("\"'“”‘’")
            )

        source_headers = [
            clean_list_item(item)
            for item in re.split(r"\s*,\s*|\s+and\s+", raw_columns)
            if clean_list_item(item)
        ]
    start_year, end_year = (int(value) for value in years_match.groups())
    if (
        not target_match.group(1).strip()
        or len(output_headers) < 2
        or len(source_headers) != len(output_headers) - 1
        or start_year > end_year
        or end_year - start_year > 200
    ):
        return None
    return {
        "target_sheet": target_match.group(1).strip(),
        "output_headers": output_headers,
        "source_headers": source_headers,
        "start_year": start_year,
        "end_year": end_year,
    }


def requested_monthly_column_totals_summary(
    instruction: str,
) -> dict[str, Any] | None:
    if not (
        re.search(r"(?i)\btotal\b", instruction)
        and re.search(r"(?i)\ball\s+months?\b", instruction)
        and re.search(r"(?i)\btable\b", instruction)
    ):
        return None
    target_match = re.search(
        r"(?is)\bnew\s+(?:sheet|worksheet)\s+"
        r"(?:named|called)\s+[\"'“‘]([^\"'”’\r\n]+)[\"'”’]",
        instruction,
    ) or re.search(
        r"(?is)\bnew\s+(?:sheet|worksheet)\s*"
        r"(?:\(\s*)?[\"'“‘]([^\"'”’\r\n]+)[\"'”’](?:\s*\))?",
        instruction,
    )
    headers_match = re.search(
        r"(?is)\bheaders?\s*\((.{1,300}?)\)\s+in\s+(?:a\s+)?new\b",
        instruction,
    ) or re.search(
        r"(?is)\b(?:with|using)\s+(?:two|2)\s+(?:column\s+)?headers?\s+"
        r"(.{1,300}?)(?=\s+in\s+(?:a\s+)?new\b)",
        instruction,
    )
    if target_match is None or headers_match is None:
        return None
    output_headers = _quoted_texts(headers_match.group(1))
    if len(output_headers) != 2 or not target_match.group(1).strip():
        return None
    return {
        "target_sheet": target_match.group(1).strip(),
        "output_headers": output_headers,
    }


SCALED_DISPLAY_DIVISORS = {
    "thousand": 1_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "trillion": 1_000_000_000_000,
}


SCALED_DISPLAY_UNITS = {
    "thousand": "K",
    "million": "M",
    "billion": "B",
    "trillion": "T",
}


def requested_scaled_number_displays(instruction: str) -> dict[str, Any] | None:
    if not re.search(
        r"(?i)\b(?:represent(?:ation)?|display|show|format)\b", instruction
    ):
        return None
    source_match = re.search(
        r"(?is)\bcolumn\s+[\"'“‘]([^\"'”’\r\n]+)[\"'”’]", instruction
    )
    if source_match is None:
        return None
    places_match = re.search(
        r"(?i)\b(\d+|zero|one|two|three|four|five|six)\s+decimal\s+places?\b",
        instruction,
    )
    if places_match is None:
        return None
    token = places_match.group(1).lower()
    decimal_places = NUMBER_WORDS.get(token, int(token) if token.isdigit() else -1)
    if not 0 <= decimal_places <= 6:
        return None
    scale_names = "thousands?|millions?|billions?|trillions?"
    outputs: list[dict[str, Any]] = []
    for match in re.finditer(
        rf"(?i)\b(?P<scale>{scale_names})\b\s*"
        r"(?:\(\s*(?P<unit>[^)]+?)\s*\))?\s+in\s+"
        r"(?:column\s+)?(?P<column>[A-Z]{1,3})\b",
        instruction,
    ):
        scale = match.group("scale").lower().removesuffix("s")
        unit = (match.group("unit") or SCALED_DISPLAY_UNITS[scale]).strip()
        if not unit or '"' in unit:
            return None
        outputs.append(
            {
                "destination_column": match.group("column").upper(),
                "divisor": SCALED_DISPLAY_DIVISORS[scale],
                "decimal_places": decimal_places,
                "unit": unit,
                "separator": " "
                if re.search(r"(?i)\b(?:white\s+space|space)\b", instruction)
                else "",
                "rounding_mode": "half_up",
            }
        )
    if not outputs:
        return None
    if not re.search(r"(?i)\bhalf\b.{0,40}\b(?:up|away\s+from\s+zero)\b", instruction):
        return None
    destination_columns = [item["destination_column"] for item in outputs]
    if len(destination_columns) != len(set(destination_columns)):
        return None
    return {
        "source_header": source_match.group(1).strip(),
        "outputs": outputs,
    }


def scaled_display_text(value: Any, spec: dict[str, Any]) -> str | None:
    try:
        scaled = Decimal(str(value)) / Decimal(int(spec["divisor"]))
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None
    places = int(spec["decimal_places"])
    quantum = Decimal(1).scaleb(-places)
    rounded = scaled.quantize(quantum, rounding=ROUND_HALF_UP)
    return f"{rounded:.{places}f}{spec.get('separator', ' ')}{spec['unit']}"


def requested_labeled_concatenation(instruction: str) -> dict[str, Any] | None:
    if not re.search(r"(?i)\b(?:concatenate|combine)\b", instruction):
        return None
    if not re.search(r"(?i)\bheaders?\b", instruction):
        return None
    span_match = re.search(
        r"(?i)\bcolumns?\s+([A-Z]{1,3})\s+(?:to|through|thru|[-–])\s+([A-Z]{1,3})\b",
        instruction,
    )
    header_match = re.search(
        r"(?is)\bnew\s+column\s+named\s+[\"'“‘]([^\"'”’\r\n]+)[\"'”’]",
        instruction,
    )
    decimal_match = re.search(
        r"(?i)\b(\d+|zero|one|two|three|four|five|six)\s+decimal\s+digits?\b",
        instruction,
    )
    if not all((span_match, header_match, decimal_match)):
        return None
    token = decimal_match.group(1).casefold()
    decimal_places = NUMBER_WORDS.get(token, int(token) if token.isdigit() else -1)
    start_column, end_column = (value.upper() for value in span_match.groups())
    if (
        column_number(start_column) > column_number(end_column)
        or not 0 <= decimal_places <= 12
    ):
        return None
    source_row_match = re.search(r"(?i)\brow\s+(\d+)\b", instruction)
    fill_match = re.search(
        r"(?is)\bfill(?:\s+out|\s+down)?\b.{0,120}?\bcolumns?\s+(.{1,120}?)(?=\.|\bnext\b|\bthen\b|$)",
        instruction,
    )
    fill_columns = []
    if fill_match is not None:
        fill_columns = list(
            dict.fromkeys(
                value.upper()
                for value in re.findall(r"\b([A-Z]{1,3})\b", fill_match.group(1))
                if column_number(start_column)
                <= column_number(value.upper())
                <= column_number(end_column)
            )
        )
    return {
        "source_start_column": start_column,
        "source_end_column": end_column,
        "source_row": int(source_row_match.group(1)) if source_row_match else 2,
        "fill_columns": fill_columns,
        "header": header_match.group(1).strip(),
        "decimal_places": decimal_places,
        "include_headers": True,
        "field_separator": ", ",
        "label_separator": ": ",
    }


def _last_requested_color(value: str) -> str | None:
    matches = [
        (match.start(), color)
        for name, color in CSS_BASIC_COLORS.items()
        for match in re.finditer(rf"(?i)\b{re.escape(name)}\b", value)
    ]
    matches.extend(
        (match.start(), match.group(0).upper())
        for match in re.finditer(r"(?i)#[0-9a-f]{6}\b", value)
    )
    return max(matches, default=(0, None))[1]


def requested_merged_text_format(value: str) -> dict[str, Any]:
    requested: dict[str, Any] = {}
    fill_match = re.search(r"(?is)(.{0,80})\b(?:fill|background)\b", value)
    if fill_match is not None:
        color = _last_requested_color(fill_match.group(1))
        if color is not None:
            requested["background_color"] = color
    text_match = re.search(r"(?is)(.{0,80})\b(?:font|text)\b", value)
    if text_match is not None:
        color = _last_requested_color(text_match.group(1))
        if color is not None:
            requested["font_color"] = color
    if re.search(r"(?i)\bbold\b", value):
        requested["bold"] = True
    return requested


def requested_merged_text_regions(instruction: str) -> list[dict[str, Any]]:
    sheet_names = requested_sheet_names(instruction)
    if len(sheet_names) != 1:
        return []
    sheet = sheet_names[0]
    regions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in MERGED_TEXT_REGION_RE.finditer(instruction):
        raw_range, raw_text = match.groups()
        cell_range = re.sub(r"[\s$]", "", raw_range).upper()
        geometry = a1_geometry(cell_range)
        text = raw_text.strip()
        if geometry is None or not text:
            continue
        start_column, start_row, end_column, end_row = geometry
        if (
            column_number(end_column) < column_number(start_column)
            or end_row < start_row
            or (start_column == end_column and start_row == end_row)
        ):
            continue
        key = (cell_range, text)
        if key in seen:
            continue
        seen.add(key)
        region: dict[str, Any] = {
            "sheet": sheet,
            "range": cell_range,
            "anchor": f"{start_column}{start_row}",
            "text": text,
        }
        local_context = instruction[
            match.start() : min(len(instruction), match.end() + 180)
        ]
        requested_format = requested_merged_text_format(local_context)
        if requested_format:
            region["format"] = requested_format
        regions.append(region)
    return regions


def requested_pivot_blank_rows(instruction: str) -> int:
    match = re.search(
        r"(?i)(?:separat(?:ed|e)|between|stack(?:ed)?[^.;]{0,40}?with)[^.;]{0,80}?"
        r"(?:(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+|an?\s+)?"
        r"blank\s+(?:rows?|lines?)",
        instruction,
    )
    if match is None:
        return 0
    token = (match.group(1) or "one").casefold()
    return NUMBER_WORDS.get(token, int(token) if token.isdigit() else 1)


def requested_sheet_renames(instruction: str) -> list[dict[str, str]]:
    renames = [
        {"source": source.strip(), "target": target.strip()}
        for source, target in re.findall(
            r"(?i)\brename\s+[\"'“‘]([^\"'”’]+)[\"'”’]\s+to\s+"
            r"[\"'“‘]([^\"'”’]+)[\"'”’]",
            instruction,
        )
        if source.strip() and target.strip()
    ]
    return list({(item["source"], item["target"]): item for item in renames}.values())


def requested_sheet_copy_lifecycle(instruction: str) -> dict[str, Any] | None:
    renames = requested_sheet_renames(instruction)
    if not renames or not re.search(r"(?i)\b(?:make|create)\s+a\s+copy\b", instruction):
        return None
    placement = re.search(
        r"(?i)\bplace\s+(?:the\s+)?copy\s+(before|after)\s+"
        r"[\"'“‘]([^\"'”’]+)[\"'”’]",
        instruction,
    )
    suffix = re.search(
        r"(?i)\bappend(?:ing)?\s+(?:a\s+)?suffix\s+"
        r"[\"'“‘]([^\"'”’]+)[\"'”’]",
        instruction,
    )
    if placement is None or suffix is None:
        return None
    first_rename = renames[0]
    separator = " " if re.search(r"(?i)\b(?:white\s+)?space\b", instruction) else ""
    suffix_text = suffix.group(1).strip()
    if not suffix_text:
        return None
    return {
        "source": first_rename["source"],
        "renamed_source": first_rename["target"],
        "copy_name": f"{first_rename['target']}{separator}{suffix_text}",
        "placement": placement.group(1).casefold(),
        "anchor": placement.group(2).strip(),
        "renames": renames,
    }


def requested_pivot_count(instruction: str) -> int | None:
    match = PIVOT_COUNT_RE.search(instruction)
    if match:
        token = match.group(1).lower()
        return NUMBER_WORDS.get(token, int(token) if token.isdigit() else 1)
    chinese = re.search(
        r"([一二两三四五六七八九十\d]+)\s*(?:个|张)?\s*数据透视表", instruction
    )
    if chinese:
        token = chinese.group(1)
        chinese_numbers = {
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
            "十": 10,
        }
        return int(token) if token.isdigit() else chinese_numbers.get(token, 1)
    return 1 if re.search(r"(?i)\bpivot\s+table\b|数据透视表", instruction) else None


def requested_row_labels(instruction: str) -> list[str]:
    return list(
        dict.fromkeys(
            match.strip()
            for match in re.findall(
                r'(?i)\brow\s+called\s+["\']([^"\']+)["\']', instruction
            )
            if match.strip()
        )
    )


def requested_text_line_indices(instruction: str) -> list[int]:
    if not re.search(r"(?i)\blines?\b", instruction):
        return []
    ordinal_values = {
        "first": 1,
        "second": 2,
        "third": 3,
        "fourth": 4,
        "fifth": 5,
    }
    matches = [
        ordinal_values[token.lower()]
        for token in re.findall(
            r"(?i)\b(first|second|third|fourth|fifth)\b", instruction
        )
    ]
    numeric = [int(value) for value in re.findall(r"(?i)\bline\s+(\d+)\b", instruction)]
    return list(dict.fromkeys([*matches, *numeric]))


def requests_appended_named_rows(instruction: str) -> bool:
    return bool(
        requested_row_labels(instruction)
        and re.search(
            r"(?i)\b(?:new\s+rows?|underneath|below|append|after)\b",
            instruction,
        )
    )


def requested_calculated_column_header(instruction: str) -> str | None:
    if not re.search(
        r"(?i)\b(?:calculate|work\s+out|subtract(?:ing)?|compute|derive)\b",
        instruction,
    ):
        return None
    match = re.search(
        r"(?i)\bnew\s+column\s+(?:named|called|with\s+(?:the\s+)?header)\s*"
        r"[\"'“‘]([^\"'”’]+)[\"'”’]",
        instruction,
    )
    if not match:
        return None
    header = match.group(1).strip()
    return header or None


def requested_period_rate_column(instruction: str) -> dict[str, Any] | None:
    header = requested_calculated_column_header(instruction)
    if (
        header is None
        or not re.search(r"(?i)\bperiod\s+rate\b", instruction)
        or not re.search(r"(?i)\b(?:highest|maximum|max)\b", instruction)
        or not re.search(r"(?i)\bfont\b", instruction)
    ):
        return None
    color = _last_requested_color(instruction)
    if color is None:
        return None
    return {
        "header": header,
        "number_format": "0.00",
        "highlight": "maximum",
        "font_color": color,
    }


def requested_vscode_folder_exclusion(instruction: str) -> str | None:
    if not re.search(
        r"(?i)\bhide\b.*\b(?:folder|folders|directory|directories)\b", instruction
    ):
        return None
    quoted = re.findall(r"[\"'“‘]([^\"'”’]+)[\"'”’]", instruction)
    return quoted[0].strip() if len(quoted) == 1 and quoted[0].strip() else None


def requested_chrome_profile_name(instruction: str) -> str | None:
    match = re.search(
        r"(?i)\b(?:username|profile(?:\s+name)?|chrome\s+profiles?)\b[^.]{0,100}?"
        r"\bto\s+([A-Za-z][A-Za-z .'-]{0,63}?)(?:[?.!,]|$)",
        instruction,
    )
    return match.group(1).strip() if match else None


def requested_vlc_recording_path(instruction: str) -> str | None:
    if not re.search(
        r"(?i)\b(?:recording|recordings|recorded)\b.*\b(?:folder|directory|path)\b"
        r"|\b(?:folder|directory|path)\b.*\b(?:recording|recordings|recorded)\b",
        instruction,
    ):
        return None
    absolute_paths = re.findall(r"(?<![\w.-])(/[\w .~/-]+)", instruction)
    if absolute_paths:
        return absolute_paths[-1].strip().rstrip(".,;:!?\"'")
    if re.search(r"(?i)\bdesktop\b", instruction):
        return "/home/user/Desktop"
    if re.search(r"(?i)\bhome\s+(?:folder|directory)\b", instruction):
        return "/home/user"
    return None


def requested_chart_count(instruction: str) -> int:
    explicit = re.search(
        r"(?i)\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
        r"(?:(?:column|bar|line)\s+){0,2}charts?\b",
        instruction,
    )
    if explicit is not None:
        token = explicit.group(1).casefold()
        return NUMBER_WORDS.get(token, int(token) if token.isdigit() else 0)
    count = 0
    if re.search(r"(?i)\b(?:bar|bars|bar chart|column chart)\b", instruction):
        count += 1
    if re.search(r"(?i)\bline chart\b", instruction):
        count += 1
    return count


def requested_last_slide_duplicate_count(instruction: str) -> int | None:
    match = re.search(
        r"(?i)\bduplicate\s+(?:the\s+)?last\s+"
        r"(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+slides?\b",
        instruction,
    )
    if not match:
        return None
    token = match.group(1).lower()
    return NUMBER_WORDS.get(token, int(token) if token.isdigit() else 1)


def calc_formula_sheet_reference(sheet: str) -> str:
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", sheet):
        return sheet
    return f"'{sheet.replace(chr(39), chr(39) * 2)}'"


def normalized_calc_formula(formula: Any) -> str:
    return re.sub(r"[\s$]", "", str(formula)).casefold()


def valid_month_growth_formula(
    formula: str, current_cell: str, previous_cell: str
) -> bool:
    normalized = re.sub(r"[\s$]", "", formula).upper()
    if "*100" in normalized:
        return False
    references = re.findall(r"([A-Z]+\d+)", normalized)
    current = current_cell.upper()
    previous = previous_cell.upper()
    difference_ratio = references == [current, previous, previous] and "/" in normalized
    ratio_minus_one = bool(
        references == [current, previous]
        and re.search(rf"/{re.escape(previous)}\)*-1(?:\D|$)", normalized)
    )
    return normalized.startswith("=") and (difference_ratio or ratio_minus_one)


def requested_chart_types(instruction: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    for match in re.finditer(
        r"(?i)\b(?:bar|bars|bar chart|column chart)\b", instruction
    ):
        matches.append((match.start(), "column"))
    for match in re.finditer(r"(?i)\bline chart\b", instruction):
        matches.append((match.start(), "line"))
    return [chart_type for _offset, chart_type in sorted(matches)]


def requested_chart_title(instruction: str) -> str | None:
    match = re.search(
        r"(?i)\bchart\s+title\b\s*(?:as|to|of|:)?\s*[\"'“‘]([^\"'”’]+)[\"'”’]",
        instruction,
    )
    if not match:
        return None
    title = match.group(1).strip()
    return title or None


def requested_os_account(instruction: str) -> dict[str, str] | None:
    username_match = re.search(
        r"(?i)\buser (?:named|called)\s*[\"'“‘]([^\"'”’]+)[\"'”’]",
        instruction,
    )
    password_match = re.search(
        r"(?i)\bpassword\s*[\"'“‘]([^\"'”’]+)[\"'”’]",
        instruction,
    )
    home_match = re.search(
        r"(?i)\b(?:folder|directory)\s*[\"'“‘](/[^\"'”’]+)[\"'”’]",
        instruction,
    )
    if not username_match or not password_match or not home_match:
        return None
    username = username_match.group(1).strip()
    password = password_match.group(1)
    home = home_match.group(1).strip()
    if not username or not password or not home:
        return None
    return {"username": username, "password": password, "home": home}


def requested_slide_note(instruction: str) -> str | None:
    return impress_semantics.literal_note_text(instruction)


def requested_slide_background_color(instruction: str) -> str | None:
    color_names = "|".join(
        sorted((re.escape(name) for name in CSS_BASIC_COLORS), key=len, reverse=True)
    )
    match = re.search(
        rf"(?i)\b(?:(?P<before>{color_names})\s+background(?:\s+color)?|"
        rf"background(?:\s+color)?\s+(?:to\s+)?(?P<after>{color_names}))\b",
        instruction,
    )
    if not match:
        return None
    name = (match.group("before") or match.group("after")).lower()
    return LIBREOFFICE_IMPRESS_PALETTE_COLORS.get(name, CSS_BASIC_COLORS[name])


def requests_all_slide_backgrounds(instruction: str) -> bool:
    return bool(
        requested_slide_background_color(instruction)
        and requests_all_slide_scope(instruction)
    )


def requested_title_edge_position(instruction: str) -> dict[str, Any] | None:
    if not re.search(r"(?i)\b(?:move|place|position)\b", instruction):
        return None
    if not re.search(r"(?i)\btitles?\b", instruction):
        return None
    edge_match = re.search(r"(?i)\b(?:to|at|along)\s+the\s+(top|bottom)\b", instruction)
    slide_match = re.search(r"(?i)\b(?:page|slide)\s+(\d+)\b", instruction)
    if edge_match is None or slide_match is None or int(slide_match.group(1)) < 1:
        return None
    return {
        "slide": int(slide_match.group(1)) - 1,
        "role": "title",
        "edge": edge_match.group(1).casefold(),
    }


def requested_slide_title_update(instruction: str) -> dict[str, Any] | None:
    if not re.search(r"(?i)\btitle\b", instruction):
        return None
    slide_match = re.search(r"(?i)\bslide\s+(\d+)\b", instruction)
    alignment_match = re.search(
        r"(?i)\b(left|right|center)(?:-|\s*)align(?:ed|ment)?\b", instruction
    )
    quoted = re.findall(r'["“]([^"”\r\n]+)["”]', instruction)
    if (
        slide_match is None
        or int(slide_match.group(1)) < 1
        or alignment_match is None
        or len(quoted) != 1
    ):
        return None
    text = quoted[0].strip()
    if not text:
        return None
    return {
        "slide": int(slide_match.group(1)) - 1,
        "role": "title",
        "text": text,
        "alignment": alignment_match.group(1).casefold(),
    }


def requested_slide_title_formatting(instruction: str) -> dict[str, Any] | None:
    """Parse formatting applied to observed slide titles, without naming shapes."""
    if not re.search(r"(?i)\btitles?\b", instruction):
        return None
    if re.search(
        r"(?i)\bslides?\s+\d+\s+(?:to|through|-)\s*\d+\b|"
        r"\b(?:body|content|subtitle|table|text\s*box)\b",
        instruction,
    ):
        return None
    list_match = re.search(
        r"(?i)\b(?:slides|pages)\s+((?:\d+\s*,\s*)+\d+)\b",
        instruction,
    )
    if list_match is not None:
        slide_numbers = [
            int(value) for value in re.findall(r"\d+", list_match.group(1))
        ]
    else:
        slide_numbers = [
            int(value)
            for value in re.findall(r"(?i)\b(?:slide|page)\s+(\d+)\b", instruction)
        ]
    slide_numbers = list(dict.fromkeys(value for value in slide_numbers if value >= 1))
    if not slide_numbers:
        return None

    properties: dict[str, Any] = {}
    size_match = re.search(
        r"(?is)\btitles?\b.{0,50}?\b(?:font\s+)?size\b(?:\s+of)?\s*"
        r"(?:to\s+|at\s+)?(\d+(?:\.\d+)?)\s*(?:pt|points?)?\b|"
        r"\b(?:font\s+)?size\b.{0,50}?\btitles?\b.{0,30}?"
        r"(?:to\s+|at\s+)?(\d+(?:\.\d+)?)\s*(?:pt|points?)?\b",
        instruction,
    )
    if size_match is not None:
        size_value = float(size_match.group(1) or size_match.group(2))
        properties["font_size"] = (
            int(size_value) if size_value.is_integer() else size_value
        )

    if re.search(
        r"(?i)\bunderline\b[^.]{0,80}\btitles?\b|\btitles?\b[^.]{0,80}\bunderline\b",
        instruction,
    ):
        properties["underline"] = True

    title_bold = bool(
        re.search(
            r"(?i)\bbold\b[^.]{0,80}\btitles?\b|\btitles?\b[^.]{0,80}\bbold\b",
            instruction,
        )
    )
    generic_text_bold = bool(
        re.search(
            r"(?is)\bbold\s+the\s+text\b[^.]{0,80}"
            r"\b(?:slide|page)\s+\d+\b",
            instruction,
        )
    )
    if title_bold or generic_text_bold:
        properties["bold"] = True

    if re.search(
        r"(?i)\bitalic(?:ize|ise|ized|ised)?\b[^.]{0,80}\btitles?\b|"
        r"\btitles?\b[^.]{0,80}\bitalic(?:ize|ise|ized|ised)?\b",
        instruction,
    ):
        properties["italic"] = True

    if re.search(
        r"(?i)\bstrike(?:through|out)?\b[^.]{0,80}\btitles?\b|"
        r"\btitles?\b[^.]{0,80}\bstrike(?:through|out)?\b",
        instruction,
    ):
        properties["strike"] = True

    color_names = "|".join(
        sorted((re.escape(name) for name in CSS_BASIC_COLORS), key=len, reverse=True)
    )
    color_match = re.search(
        rf"(?is)\b(?:font\s+)?color\b[^.]*?\btitles?\b[^.]*?"
        rf"\b(?:as|to)\s+({color_names})\b|"
        rf"\btitles?\b[^.]*?\b(?:font\s+)?color\b[^.]*?"
        rf"\b(?:as|to)\s+({color_names})\b",
        instruction,
    )
    if color_match is not None:
        color_name = (color_match.group(1) or color_match.group(2)).casefold()
        properties["color"] = LIBREOFFICE_IMPRESS_PALETTE_COLORS.get(
            color_name,
            CSS_BASIC_COLORS[color_name],
        )

    if not properties:
        return None
    return {
        "slides": [value - 1 for value in slide_numbers],
        "role": "title",
        **properties,
    }


def requested_named_slide_table(instruction: str) -> dict[str, Any] | None:
    slide_match = re.search(
        r'(?i)\b(?:in|on)\s+(?:the\s+)?["“]([^"”\r\n]+)["”]\s+slide\b',
        instruction,
    )
    dimensions_match = re.search(
        r"(?i)\btable\b.{0,80}\b(\d+)\s+rows?\b.{0,40}\b(\d+)\s+columns?\b",
        instruction,
    )
    if slide_match is None or dimensions_match is None:
        return None
    rows = int(dimensions_match.group(1))
    columns = int(dimensions_match.group(2))
    title = slide_match.group(1).strip()
    if not title or rows < 1 or columns < 1:
        return None
    return {"slide_title": title, "rows": rows, "columns": columns}


def requested_image_edge_position(instruction: str) -> dict[str, Any] | None:
    if not re.search(r"(?i)\b(?:move|place|position)\b", instruction):
        return None
    if not re.search(r"(?i)\b(?:image|picture|photo)\b", instruction):
        return None
    edge_match = re.search(
        r"(?i)\b(?:to|on|at)\s+the\s+(left|right)\s+side\b", instruction
    )
    slide_match = re.search(r"(?i)\b(?:page|slide)\s+(\d+)\b", instruction)
    if edge_match is None or slide_match is None or int(slide_match.group(1)) < 1:
        return None
    return {
        "slide": int(slide_match.group(1)) - 1,
        "role": "image",
        "edge": edge_match.group(1).casefold(),
    }


def requested_table_edge_position(instruction: str) -> dict[str, Any] | None:
    if not re.search(r"(?i)\b(?:move|place|position)\b", instruction):
        return None
    if not re.search(r"(?i)\btable\b", instruction):
        return None
    edge_match = re.search(r"(?i)\b(?:to|at|along)\s+the\s+(top|bottom)\b", instruction)
    slide_match = re.search(r"(?i)\b(?:page|slide)\s+(\d+)\b", instruction)
    if edge_match is None or slide_match is None or int(slide_match.group(1)) < 1:
        return None
    return {
        "slide": int(slide_match.group(1)) - 1,
        "role": "table",
        "edge": edge_match.group(1).casefold(),
    }


def requested_title_range_personal_info_cleanup(
    instruction: str,
) -> dict[str, Any] | None:
    range_match = re.search(
        r"(?i)\bslides?\s+(\d+)\s+(?:to|through|-)\s*(\d+)\b",
        instruction,
    )
    cleanup_match = re.search(
        r"(?i)\b(?:delete|remove)\b.{0,80}\bpersonal information\b"
        r"(?:.{0,40}\bicons?\b)?[^.]*\bslide\s+(\d+)\b",
        instruction,
    )
    color_match = re.search(
        r"(?i)\bfont color\b.{0,60}\b(?:as|to)\s+([a-z]+)\b",
        instruction,
    )
    if range_match is None or cleanup_match is None or color_match is None:
        return None
    start, end = (int(value) for value in range_match.groups())
    cleanup_slide = int(cleanup_match.group(1))
    color = CSS_BASIC_COLORS.get(color_match.group(1).casefold())
    if start < 1 or end < start or cleanup_slide < 1 or color is None:
        return None
    if not re.search(
        r"(?i)\bbold\b.{0,40}\btitle\b|\btitle\b.{0,40}\bbold\b", instruction
    ):
        return None
    return {
        "title_slides": list(range(start - 1, end)),
        "color": color,
        "bold": True,
        "cleanup_slide": cleanup_slide - 1,
        "include_icons": bool(re.search(r"(?i)\bicons?\b", cleanup_match.group(0))),
    }


def looks_like_personal_information(text: str) -> bool:
    return bool(
        re.search(
            r"(?ix)(?:\b\d{3}[- .]\d{3}[- .]\d{4}\b|"
            r"\b[^\s@]+@[^\s@]+\.[a-z]{2,}\b|"
            r"(?:https?://|www\.)\S+|^@[a-z0-9_.-]+$|"
            r"\b\d+\s+[^\n,]+\b(?:st(?:reet)?|rd|road|ave(?:nue)?|blvd|lane|ln)\b|"
            r"\b[a-z0-9-]+\.(?:com|org|net|io|co)\b)",
            text,
        )
    )


def requested_slide_role_text_formatting(
    instruction: str,
) -> dict[str, Any] | None:
    """Parse role-scoped slide text formatting without choosing concrete shapes."""
    if not re.search(r"(?i)\bunderline\b.{0,80}\bbody\s+text\b", instruction):
        return None
    if not all(
        re.search(rf"(?i)\b{role}\b", instruction) for role in ("title", "table")
    ):
        return None
    if not re.search(r"(?i)\b(?:font|text)\s+color\b", instruction):
        return None

    quoted = re.search(
        r"(?i)[\"'“‘]([^\"'”’]+)[\"'”’]\s+color\b",
        instruction,
    )
    explicit = re.search(r"#[0-9a-fA-F]{6}\b", instruction)
    color_name = quoted.group(1).strip() if quoted else None
    normalized_name = (
        re.sub(r"[^a-z0-9]+", " ", color_name.casefold()).strip()
        if color_name
        else None
    )
    color = (
        explicit.group(0).upper()
        if explicit
        else LIBREOFFICE_IMPRESS_PALETTE_COLORS.get(normalized_name or "")
        or CSS_BASIC_COLORS.get(normalized_name or "")
    )
    if color is None:
        return None

    slide_match = re.search(r"(?i)\b(?:slide|page)\s+(\d+)\b", instruction)
    slide = int(slide_match.group(1)) - 1 if slide_match else None
    if slide is not None and slide < 0:
        return None
    return {
        "slide": slide,
        "color_name": color_name or explicit.group(0),
        "color": color,
        "body_underline": True,
        "non_body_underline": False,
    }


def requested_slide_content_formatting(
    instruction: str,
) -> dict[str, Any] | None:
    if not re.search(r"(?i)\bcontent\b", instruction):
        return None
    size_match = re.search(
        r"(?is)\bfont\s+size\b.{0,60}\bcontent\b.{0,30}?\b(?:to|at)\s+"
        r"(\d+(?:\.\d+)?)\b|"
        r"\bcontent\b.{0,60}\bfont\s+size\b.{0,20}?\b(?:to|at)\s+"
        r"(\d+(?:\.\d+)?)\b",
        instruction,
    )
    color_match = re.search(
        r"(?is)\bfont\s+color\b.{0,30}?\bto\s+([a-z][a-z0-9 ]*?)"
        r"(?=\s*[.,;]|\s+and\b|$)",
        instruction,
    )
    background = requested_slide_background_color(instruction)
    if size_match is None or color_match is None or background is None:
        return None
    size_value = float(size_match.group(1) or size_match.group(2))
    font_size: int | float = int(size_value) if size_value.is_integer() else size_value
    color_name = re.sub(r"[^a-z0-9]+", " ", color_match.group(1).casefold()).strip()
    font_color = LIBREOFFICE_IMPRESS_PALETTE_COLORS.get(
        color_name,
        CSS_BASIC_COLORS.get(color_name),
    )
    if font_color is None:
        return None
    slide_match = re.search(r"(?i)\b(?:slide|page)\s+(\d+)\b", instruction)
    slide = int(slide_match.group(1)) - 1 if slide_match else None
    if slide is not None and slide < 0:
        return None
    return {
        "slide": slide,
        "role": "content",
        "font_size": font_size,
        "font_color_name": color_name,
        "font_color": font_color,
        "background_color": background,
    }


def requested_title_to_notes(instruction: str) -> dict[str, Any] | None:
    if not re.search(
        r"(?i)\b(?:add|copy|put|write)\b.{0,40}\btitle\b.{0,30}\bnotes?\b",
        instruction,
    ):
        return None
    slide_match = re.search(r"(?i)\b(?:slide|page)\s+(\d+)\b", instruction)
    slide = int(slide_match.group(1)) - 1 if slide_match else None
    if slide is not None and slide < 0:
        return None
    return {
        "slide": slide,
        "source_role": "title",
        "background_color": requested_slide_background_color(instruction),
    }


def requested_all_textbox_color(instruction: str) -> tuple[int, str] | None:
    intent = parse_all_textbox_color_intent(instruction)
    return (intent.slide, intent.color) if intent is not None else None


def requested_textbox_font_sizes(instruction: str) -> dict[str, Any] | None:
    return impress_semantics.textbox_font_size_request(instruction)


def requested_content_textbox_insert(instruction: str) -> dict[str, Any] | None:
    if not re.search(
        r"(?i)\b(?:add|insert|write|type|put)\b.{0,100}\bcontent\s+text\s*box\b"
        r"|\bcontent\s+text\s*box\b.{0,100}\b(?:add|insert|write|type|put)\b",
        instruction,
    ):
        return None
    quoted = [value.strip() for value in re.findall(r'["“]([^"”]+)["”]', instruction)]
    location_text = re.sub(r'["“][^"”]*["”]', "", instruction)
    slide_match = re.search(r"(?i)\b(?:slide|page)\s+(\d+)\b", location_text)
    if slide_match is None or not quoted or int(slide_match.group(1)) < 1:
        return None
    return {"slide": int(slide_match.group(1)) - 1, "text": quoted[0]}


def requested_matching_indent_without_bullet(instruction: str) -> dict[str, Any] | None:
    if not re.search(
        r"(?is)\bindent(?:ed|ation)?\b.{0,100}\b(?:same|match)", instruction
    ):
        return None
    if not re.search(r"(?is)\b(?:without|no)\b.{0,30}\bbullet", instruction):
        return None
    page_match = re.search(r"(?i)\b(?:slide|page)\s+(\d+)\b", instruction)
    quoted = [value.strip() for value in re.findall(r'["“]([^"”]+)["”]', instruction)]
    if page_match is None or len(quoted) < 2 or int(page_match.group(1)) < 1:
        return None
    return {
        "slide": int(page_match.group(1)) - 1,
        "target_text": quoted[0],
        "reference_texts": quoted[1:],
    }


def requested_cover_image_slide(instruction: str) -> int | None:
    if not re.search(r"(?i)\b(?:image|photo|picture)\b", instruction):
        return None
    if not re.search(
        r"(?i)\b(?:fill|cover)\b[^.]{0,80}\b(?:entire|whole|full)\b[^.]{0,30}\b(?:page|slide)\b"
        r"|\b(?:entire|whole|full)\b[^.]{0,30}\b(?:page|slide)\b[^.]{0,80}\b(?:fill|cover)\b",
        instruction,
    ):
        return None
    page_match = re.search(r"(?i)\b(?:page|slide)\s+(\d+)\b", instruction)
    if page_match:
        return int(page_match.group(1)) - 1
    if re.search(r"(?i)\bfirst\s+(?:page|slide)\b", instruction):
        return 0
    return None


def semantic_configuration_action(domain: str, instruction: str) -> str | None:
    if domain == "os" and re.search(
        r"(?i)\b(?:notification|notifications|banner|banners|disturb|quiet)\b",
        instruction,
    ):
        return "notifications.configure"
    if domain == "vlc":
        is_global_play_pause = bool(
            re.search(r"(?i)\b(?:hotkey|shortcut|keyboard)\b", instruction)
            and re.search(r"(?i)\b(?:play|pause|start)\b", instruction)
        )
        is_maximum_volume = bool(
            re.search(r"(?i)\b(?:max|maximum)\b", instruction)
            and re.search(r"(?i)\bvolume\b", instruction)
        )
        is_slider_color = bool(
            re.search(r"(?i)\b(?:slider|volume\s+control)\b", instruction)
            and re.search(r"(?i)\bcolou?r\b", instruction)
        )
        is_persistent_interface_setting = bool(
            re.search(
                r"(?i)\b(?:minimal\s+interface|auto[- ]?clos(?:e|ing)|exit\s+after|"
                r"multiple\s+instances?|cone|splash)\b",
                instruction,
            )
        )
        if any(
            (
                is_global_play_pause,
                is_maximum_volume,
                is_slider_color,
                is_persistent_interface_setting,
            )
        ):
            return "preferences.configure"
        return None
    if domain != "thunderbird":
        return None
    if re.search(r"(?i)\bsignature\b", instruction):
        return "mail.configure"
    if re.search(r"(?i)\b(?:unified|combined)\b.{0,40}\binbox(?:es)?\b", instruction):
        return "mail.configure"
    if re.search(r"(?i)\b(?:dark\s+(?:mode|theme)|complete\s+dark)\b", instruction):
        return "mail.configure"
    if re.search(
        r"(?i)\b(?:reply|replies|quot(?:e|ed|es|ing))\b", instruction
    ) and re.search(
        r"(?i)\b(?:original|message|mail|quote|quoting)\b|[>]",
        instruction,
    ):
        return "mail.configure"
    if re.search(r"(?i)\bfilters?\b", instruction) and re.search(
        r"(?i)\bsubfolders?\b",
        instruction,
    ):
        return "mail.configure"
    return None


def requested_vscode_settings(instruction: str) -> dict[str, Any] | None:
    if re.search(r"(?i)\b(?:missing|unresolved)\s+imports?\b", instruction):
        if re.search(
            r"(?i)\b(?:disable|suppress|ignore|off|no\s+error)\b", instruction
        ):
            severity = "none"
        elif re.search(r"(?i)\bwarning\b", instruction):
            severity = "warning"
        elif re.search(r"(?i)\binformation|info\b", instruction):
            severity = "information"
        elif re.search(r"(?i)\berror\b", instruction):
            severity = "error"
        else:
            return None
        return {
            "python.analysis.diagnosticSeverityOverrides": {
                "reportMissingImports": severity
            }
        }
    if re.search(r"(?i)\bauto\s*save|autosave\b", instruction):
        if re.search(r"(?i)\b(?:disable|off|turn\s+off|switch\s+off)\b", instruction):
            return {"files.autoSave": "off"}
        delay = re.search(
            r"(?i)\b(\d+)\s*(milliseconds?|msecs?|ms|seconds?|secs?|s)\b",
            instruction,
        )
        values: dict[str, Any] = {"files.autoSave": "afterDelay"}
        if delay:
            amount = int(delay.group(1))
            unit = delay.group(2).lower()
            values["files.autoSaveDelay"] = amount * (
                1000 if unit.startswith("s") else 1
            )
        return values
    return None


def requests_vscode_keybinding_disable(instruction: str) -> bool:
    return bool(
        re.search(r"(?i)\b(?:shortcut|keybinding|key\s+binding|hotkey)\b", instruction)
        and re.search(r"(?i)\b(?:remove|disable|unbind|clear|delete)\b", instruction)
    )


def requested_calc_export_format(instruction: str) -> str | None:
    if not re.search(r"(?i)\bexport\b", instruction):
        return None
    for format_name in ("csv", "pdf"):
        if re.search(rf"(?i)\b{format_name}\b", instruction):
            return format_name
    return None


def requests_same_basename_export(instruction: str) -> bool:
    return bool(
        re.search(
            r"(?is)(?:\bsame\s+(?:file\s*)?name\b|\b(?:file\s*)?name\b.{0,50}\b(?:same|share)\b|\bshare\s+the\s+(?:file\s*)?name\b)",
            instruction,
        )
    )


def instruction_required_actions(
    domain: str, instruction: str, *, strict_generic: bool = False
) -> list[str]:
    if domain == "multi_apps":
        # Multi-application episodes discover owning Adapter actions through
        # tools_search and expose only the generic adapter.call facade.
        return []

    actions: list[str] = []
    actions.extend(
        impress_semantics.required_actions(
            domain, instruction, strict_generic=strict_generic
        )
    )
    actions.extend(git_semantics.required_actions(domain, instruction))
    actions.extend(vlc_semantics.required_actions(domain, instruction))
    actions.extend(terminal_capture_semantics.required_actions(domain, instruction))
    actions.extend(terminal_output_semantics.required_actions(domain, instruction))
    actions.extend(
        filesystem_permission_semantics.required_actions(domain, instruction)
    )
    actions.extend(filesystem_rename_semantics.required_actions(domain, instruction))
    actions.extend(clipboard_path_semantics.required_actions(domain, instruction))
    semantic_action = semantic_configuration_action(domain, instruction)
    if semantic_action is not None:
        actions.append(semantic_action)
        if domain == "vlc" and semantic_action == "preferences.configure":
            # Media words can describe the context of a preference request. They
            # do not turn the request into a playback workflow.
            actions = [
                action
                for action in actions
                if action not in {"playback.find_local", "playback.open"}
            ]
    actions.extend(vscode_configuration_semantics.required_actions(domain, instruction))
    actions.extend(workspace_open_semantics.required_actions(domain, instruction))
    if domain == "libreoffice_calc" and re.search(
        r"(?i)\bdecimal\s+separator\b",
        instruction,
    ):
        actions.append(
            "range.set_decimal_separator" if strict_generic else "range.format"
        )
    if domain == "libreoffice_calc":
        actions.extend(
            calc_semantics.operation_required_actions(
                instruction, strict_generic=strict_generic
            )
        )
    if (
        domain == "libreoffice_calc"
        and requested_calc_export_format(instruction) is not None
    ):
        actions.extend(["workbook.inspect", "workbook.export"])
    if domain == "libreoffice_calc" and calc_semantics.parse_sort_intent(instruction):
        actions.append("table.sort")
    if domain == "libreoffice_calc" and re.search(
        r"(?is)\b(?:fit|resize)\b.{0,100}\b(?:one|1)\s+page\b", instruction
    ):
        actions.append("page.fit_to_pages")
    if domain == "libreoffice_calc" and requested_merged_text_regions(instruction):
        actions.extend(["sheet.create", "range.merge", "range.write"])
        if any(
            spec.get("format") for spec in requested_merged_text_regions(instruction)
        ):
            actions.append("range.format")
    if domain == "libreoffice_calc" and requested_sheet_copy_lifecycle(instruction):
        actions.extend(["workbook.inspect", "sheet.rename", "sheet.copy"])
    if domain == "libreoffice_calc" and requested_pivot_count(instruction) is not None:
        actions.extend(["range.read", "pivot.create"])
    if domain == "libreoffice_calc" and requested_annual_percentage_change_summary(
        instruction
    ):
        actions.extend(
            [
                "workbook.inspect",
                "range.read",
                "sheet.create",
                "range.write",
                "range.format",
            ]
        )
    if domain == "libreoffice_calc" and requested_monthly_column_totals_summary(
        instruction
    ):
        actions.extend(
            ["workbook.inspect", "range.read", "sheet.create", "range.write"]
        )
    if domain == "libreoffice_calc" and requested_scaled_number_displays(instruction):
        actions.extend(
            [
                "workbook.inspect",
                "range.read",
                "range.copy",
                "range.set_scaled_display",
            ]
        )
    if domain == "libreoffice_calc" and requested_labeled_concatenation(instruction):
        actions.extend(
            [
                "workbook.inspect",
                "range.read",
                "range.write",
            ]
        )
    if domain == "libreoffice_calc" and requested_period_rate_column(instruction):
        actions.extend(
            ["workbook.inspect", "range.read", "range.write", "range.format"]
        )
    if domain == "libreoffice_calc" and (
        re.search(
            r"(?is)\bfill\b.{0,100}\bblank\s+cells?\b.{0,100}\b(?:above|previous)\b",
            instruction,
        )
        or re.search(
            r"(?is)\bfill\s+(?:out|down)\b.{0,100}\b(?:rows?|columns?|formula)",
            instruction,
        )
    ):
        actions.append("range.fill_down")
    if domain == "libreoffice_calc":
        case_transform = re.search(
            r"(?is)(?:\btitle\s+case\b|\bcapitaliz(?:e|ing)\b|\blower\s*case\b|"
            r"\bupper\s*case\b)",
            instruction,
        )
        whitespace_transform = re.search(r"(?i)\btrim\b", instruction) or re.search(
            r"(?is)(?:\b(?:remove|collapse|clean|normaliz(?:e|ing)|strip|eliminate)\b"
            r".{0,80}\b(?:white\s*spaces?|whitespaces?)\b|"
            r"\b(?:white\s*spaces?|whitespaces?)\b.{0,80}"
            r"\b(?:remove|collapse|clean|normaliz(?:e|ing)|strip|eliminate)\b)",
            instruction,
        )
        if case_transform or whitespace_transform:
            actions.append("range.text_transform")
    if domain == "libreoffice_writer" and requests_single_cursor_image_insertion(
        instruction
    ):
        actions.append("image.insert_at_cursor")
    if domain == "libreoffice_impress":
        actions.extend(impress_page_number.required_actions(domain, instruction))
        # Audio insertion is a public Impress composition: inspect the live
        # deck first, then let the model choose the target slide and exact
        # Adapter arguments.  The file path remains instruction-derived only
        # at the validation boundary; this route does not synthesize a call.
        if requests_presentation_audio_insertion(instruction):
            actions.extend(["presentation.inspect", "audio.insert"])
        role_text_update = parse_role_text_update_intent(instruction)
        if parse_multislide_role_format_intent(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "slides.format_text_roles"]
                if strict_generic
                else ["presentation.inspect", "shape.format_text"]
            )
        if requested_ordered_image_slides(instruction) is not None:
            if not strict_generic:
                actions.extend(["slide.delete", "shape.delete"])
            # Cleanup is a choice based on the live template, not an obligation
            # to execute both deletion strategies before completing the deck.
            actions.extend(["slide.create", "shape.insert_image"])
        if requested_slide_note(instruction) is not None and role_text_update is None:
            actions.append("slide.set_notes")
        if requested_title_to_notes(instruction) is not None:
            actions.extend(["presentation.inspect", "slide.set_notes"])
        if parse_background_intent(instruction) is not None:
            actions.append("slide.set_background")
        if requested_title_edge_position(instruction) is not None:
            actions.extend(["presentation.inspect", "shape.set_geometry"])
        if strict_generic and role_text_update is not None:
            actions.extend(["presentation.inspect", "slide.set_role_text"])
        elif requested_slide_title_update(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "shape.write_text", "shape.format_text"]
            )
        title_format_request = requested_slide_title_formatting(instruction)
        if title_format_request is not None:
            actions.extend(["presentation.inspect", "shape.format_text"])
        sized_image_insertion = (
            is_sized_image_insertion_instruction(instruction)
            if strict_generic
            else requested_sized_slide_image(instruction) is not None
        )
        if sized_image_insertion:
            actions.extend(["presentation.inspect", "shape.insert_image"])
        if requested_table_row_replacement(instruction) is not None:
            actions.extend(
                impress_table_row.required_actions(domain, instruction)
                if strict_generic
                else ["presentation.inspect", "table.write"]
            )
        if requested_first_textbox_alignments_by_slide(instruction) is not None:
            actions.extend(["presentation.inspect", "shape.format_text"])
        if requested_named_slide_table(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "table.create"]
                if strict_generic
                else ["presentation.inspect", "shape.delete", "table.create"]
            )
        if requested_image_edge_position(instruction) is not None:
            actions.extend(["presentation.inspect", "shape.set_geometry"])
        if requested_table_edge_position(instruction) is not None:
            actions.extend(["presentation.inspect", "shape.set_geometry"])
        if strict_generic and parse_personal_information_removal_intent(instruction):
            actions.extend(["presentation.inspect", "shape.delete"])
        elif requested_title_range_personal_info_cleanup(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "shape.format_text", "shape.delete"]
            )
        if requested_slide_content_formatting(instruction) is not None:
            actions.extend(
                [
                    "presentation.inspect",
                    "slide.format_text_roles"
                    if strict_generic
                    else "shape.format_text",
                    "slide.set_background",
                ]
            )
        if requested_slide_role_text_formatting(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "slide.format_text_roles"]
                if strict_generic
                else ["presentation.inspect", "shape.format_text", "table.format_text"]
            )
        if requested_all_textbox_color(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "slide.format_text_roles"]
                if strict_generic
                else ["shape.format_text"]
            )
        if requested_content_textbox_insert(instruction) is not None:
            actions.append("shape.write_text_native")
        if requested_matching_indent_without_bullet(instruction) is not None:
            actions.extend(
                ["presentation.inspect", "shape.format_text"]
            )
        if requested_cover_image_slide(instruction) is not None:
            actions.extend(["presentation.inspect", "shape.fit_to_slide"])
    if domain == "os" and requested_os_account(instruction) is not None:
        actions.append("user.ensure_account")
    if domain == "thunderbird":
        if requests_filter_configuration(domain, instruction):
            actions.append("filters.configure")
    if strict_generic:
        actions = public_action_contract(actions)
    return list(dict.fromkeys(actions))


def strict_instruction_required_actions(domain: str, instruction: str) -> list[str]:
    return instruction_required_actions(domain, instruction, strict_generic=True)


def requested_column_order(instruction: str) -> list[str]:
    intent = parse_column_reorder_intent(instruction)
    return list(intent.headers) if intent is not None else []


__all__ = [
    "REQUESTED_FILE_RE",
    "REQUESTED_SHEET_RE",
    "MERGED_TEXT_REGION_RE",
    "PIVOT_COUNT_RE",
    "NUMBER_WORDS",
    "CSS_BASIC_COLORS",
    "LIBREOFFICE_IMPRESS_PALETTE_COLORS",
    "MONTH_TOKENS",
    "requested_files",
    "requested_desktop_file_paths",
    "requested_audio_path",
    "requests_presentation_audio_insertion",
    "requested_sized_slide_image",
    "requested_picture_heights_by_slide",
    "requested_table_row_replacement",
    "requested_first_textbox_alignments_by_slide",
    "requested_numbered_desktop_files",
    "requested_blank_slide_count",
    "requested_ordered_image_slides",
    "requested_sheet_names",
    "requested_annual_percentage_change_summary",
    "requested_monthly_column_totals_summary",
    "SCALED_DISPLAY_DIVISORS",
    "SCALED_DISPLAY_UNITS",
    "requested_scaled_number_displays",
    "scaled_display_text",
    "requested_labeled_concatenation",
    "requested_merged_text_format",
    "requested_merged_text_regions",
    "requested_pivot_blank_rows",
    "requested_sheet_renames",
    "requested_sheet_copy_lifecycle",
    "requested_pivot_count",
    "requested_row_labels",
    "requested_text_line_indices",
    "requests_appended_named_rows",
    "requested_calculated_column_header",
    "requested_period_rate_column",
    "requested_vscode_folder_exclusion",
    "requested_chrome_profile_name",
    "requested_vlc_recording_path",
    "requested_chart_count",
    "requested_last_slide_duplicate_count",
    "calc_formula_sheet_reference",
    "normalized_calc_formula",
    "valid_month_growth_formula",
    "requested_chart_types",
    "requested_chart_title",
    "requested_os_account",
    "requested_slide_note",
    "requested_slide_background_color",
    "requests_all_slide_backgrounds",
    "requested_title_edge_position",
    "requested_slide_title_update",
    "requested_slide_title_formatting",
    "requested_named_slide_table",
    "requested_image_edge_position",
    "requested_table_edge_position",
    "requested_title_range_personal_info_cleanup",
    "looks_like_personal_information",
    "requested_slide_role_text_formatting",
    "requested_slide_content_formatting",
    "requested_title_to_notes",
    "requested_all_textbox_color",
    "requested_textbox_font_sizes",
    "requested_content_textbox_insert",
    "requested_matching_indent_without_bullet",
    "requested_cover_image_slide",
    "semantic_configuration_action",
    "requested_vscode_settings",
    "requests_vscode_keybinding_disable",
    "requested_calc_export_format",
    "requests_same_basename_export",
    "instruction_required_actions",
    "strict_instruction_required_actions",
    "requested_column_order",
]
