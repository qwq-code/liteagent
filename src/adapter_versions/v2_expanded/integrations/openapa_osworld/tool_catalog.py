from __future__ import annotations

from importlib import import_module
from typing import Iterable


DOMAIN_SCHEMA_MODULES = {
    "libreoffice_calc": "calc_adapter.schema",
    "libreoffice_impress": "impress_adapter.schema",
    "chrome": "chrome_adapter.schema",
    "gimp": "gimp_adapter.schema",
    "os": "os_adapter.schema",
    "libreoffice_writer": "writer_adapter.schema",
    "vs_code": "vscode_adapter.schema",
    "vlc": "vlc_adapter.schema",
    "thunderbird": "thunderbird_adapter.schema",
    "multi_apps": "multi_apps_adapter.schema",
}

TARGET_SELECTOR = (
    'target={one or more of "target_id"|"url"|"title"|"index": value} required; '
    "copy an exact selector from tab.list; combinations must identify the same unique tab"
)
LOCATOR = (
    '{exactly one of "css", "xpath", "text", "label", "role": str; '
    '"name"?: str, "index"?: nonnegative int, "exact"?: bool}; '
    "omit index only when the locator has exactly one match"
)


CHROME_SIGNATURES = {
    "browser.inspect": "params={}",
    "browser.ensure_running": "params={}",
    "browser.restart": "params={}",
    "tab.list": "params={}",
    "tab.open": 'params={"url": str}',
    "tab.activate": (
        'params={one or more of "target_id": str, "url": str, "title": str, '
        '"index": nonnegative int}'
    ),
    "tab.close": (
        'params={one or more of "target_id": str, "url": str, "title": str, '
        '"index": nonnegative int}'
    ),
    "tab.restore_last_closed": "params={}",
    "page.snapshot": f"params={{}}; {TARGET_SELECTOR}",
    "page.goto": f'params={{"url": str}}; {TARGET_SELECTOR}',
    "page.click": f'params={{"locator": {LOCATOR}}}; {TARGET_SELECTOR}',
    "page.fill": (f'params={{"locator": {LOCATOR}, "value": str}}; {TARGET_SELECTOR}'),
    "page.select": (
        f'params={{"locator": {LOCATOR}, "value": str}}; {TARGET_SELECTOR}'
    ),
    "page.press": (f'params={{"key": str, "locator"?: {LOCATOR}}}; {TARGET_SELECTOR}'),
    "page.wait_for": (
        'params={at least one of "url_contains": str, "url_matches": str, '
        f'"text": str, "locator": {LOCATOR}, "ready_state": str; '
        f'"timeout_ms"?: int}}; {TARGET_SELECTOR}'
    ),
    "page.read": f'params={{"locator"?: {LOCATOR}}}; {TARGET_SELECTOR}',
    "bookmark.create_folder": 'params={"name": str}',
    "bookmark.add_current": f"params={{}}; {TARGET_SELECTOR}",
    "settings.set": (
        'params={"settings": {"font_size"?: positive int, '
        '"do_not_track"?: bool, "safe_browsing"?: bool, '
        '"profile_name"?: str, "search_engine"?: "bing"|"google", '
        '"appearance"?: "light"|"dark"|"system", '
        '"startup_mode"?: "new_tab"|"continue", "clear_on_exit"?: bool}}; '
        "font_size aliases are normalized and the action verifies preferences by default"
    ),
    "privacy.delete_cookies": 'params={"domain": str}',
    "privacy.delete_history": 'params={"contains": str}',
    "extension.load_unpacked": (
        'params={"path": str}; path may be the extension root containing manifest.json '
        "or a parent directory with exactly one immediate extension child"
    ),
    "shortcut.create_current": (f'params={{"name"?: str}}; {TARGET_SELECTOR}'),
    "page.print_pdf": (
        f'params={{"path": absolute or ~/ str, "landscape"?: bool, '
        f'"print_background"?: bool}}; {TARGET_SELECTOR}'
    ),
}


DOMAIN_SIGNATURES = {
    "libreoffice_calc": {
        "workbook.inspect": "params={}",
        "workbook.read_file": (
            'params={"path": absolute local CSV|ODS|XLSX path, "sheet"?: exact str, '
            '"range"?: A1 range, "start_row"?: positive one-based int, '
            '"start_column"?: positive one-based int, "max_rows"?: int[1,1000], '
            '"max_columns"?: int[1,256], "max_sheets"?: int[1,32]}; '
            "reads bounded cell text exactly as displayed by LibreOffice Calc, including trailing zeros"
        ),
        "workbook.create_new": (
            'params={"output_path": absolute local ODS|XLSX path, "sheet_name"?: str, '
            '"headers"?: [unique str], "rows"?: [[string|number|boolean|null]], '
            '"overwrite"?: bool}; headers and rows must be supplied together; creates, '
            "optionally populates, and saves a new workbook"
        ),
        "workbook.save": (
            'params={"url"?: str, "filter_name"?: str}; the URL extension selects the '
            "format, so omit filter_name normally; when supplied it must match the extension "
            "(for example .xlsx uses Calc MS Excel 2007 XML)"
        ),
        "workbook.convert_file": (
            'params={"input_path": absolute local CSV|ODS|XLSX path, '
            '"output_path": different absolute local CSV|ODS|XLSX path}; '
            "the output extension selects the destination spreadsheet format"
        ),
        "sheet.create": 'params={"name": str, "index"?: nonnegative int}',
        "range.read": 'params={"sheet": str, "range": str}',
        "range.write": (
            'params={"sheet": str, "range": str, "values": '
            '[[{"kind": "string"|"number"|"boolean"|"date"|"formula"|'
            '"blank"|"formatted_text", "value"?: scalar|{"parts": ['
            '{"text": str}|{"cell": A1 cell, "decimal_places"?: 0..12}]}]]}; '
            "use formatted_text for formula-backed concatenation with exact decimal digits; "
            "values must be nonempty and rectangular; use formatted_text rather than "
            "retrying a locale-invalid formula"
        ),
        "range.fill_down": (
            'params={"sheet": str, "range": A1 range, '
            '"mode": "previous_nonblank"|"formula_pattern", '
            '"source_rows"?: positive int, "only_blank"?: bool, '
            '"preserve_format"?: bool}; the range includes its source row(s) at the top; '
            "previous_nonblank fills blank cells from immediately above, while "
            "formula_pattern extends relative formulas from the top source row(s) and "
            "requires at least one formula in those top rows"
        ),
        "range.text_transform": (
            'params={"source_sheet": str, "source_range": A1 range, '
            '"destination_sheet": str, "destination": top-left A1 cell, '
            '"operation": "trim"|"collapse_whitespace"|"title_case"|'
            '"lowercase"|"uppercase", "skip_blank"?: bool}; applies one '
            "text-only transformation and writes a same-sized output range; use separate calls for multiple transforms. "
            "For an in-place final result, destination may equal the source column; do not create temporary columns."
        ),
        "range.set_scaled_display": (
            'params={"sheet": str, "range": A1 range, "divisor": positive power of 1000, '
            '"decimal_places": 0..12, "unit": str, "separator": "space"|"none", '
            '"rounding_mode": "half_up", "locale"?: str}; changes only the number format '
            "of one explicit existing range; use range.copy separately when values must be copied"
        ),
        "cells.set_formulas": (
            'params={"sheet": str, "writes": [{"cell": unqualified A1 cell, '
            '"formula": str beginning with "="}]}; atomically writes only the explicit '
            "model-selected cells and formulas; it never discovers or calculates them. "
            "Use range.write for literal years or labels. For percentage changes, store the "
            "decimal ratio and apply a percent number format unless numeric percent points are requested."
        ),
        "range.set_validation": (
            'params={"sheet": str, "range": str, "values": [str], '
            '"allow_blank"?: bool, "show_error"?: bool}'
        ),
        "range.merge": (
            'params={"sheet": str, "range": str, "merge"?: bool}; '
            "merge defaults to true"
        ),
        "range.format": (
            'params={"sheet": str, "range": str, "format": {'
            '"background_color"?: "#RRGGBB", "font_color"?: "#RRGGBB", '
            '"bold"?: bool, "number_format"?: str, "locale"?: str, '
            '"horizontal_alignment"?: "left"|"center"|"right"|"standard", '
            '"vertical_alignment"?: "top"|"center"|"bottom"|"standard"}}'
        ),
        "range.set_decimal_separator": (
            'params={"sheet": str, "range": A1 range, '
            '"separator": "comma"|"dot"}; changes numeric/formula display separators '
            "while preserving values, formulas, and each cell's visible decimal precision; "
            "ignores text and date-formatted cells"
        ),
        "chart.create": (
            'params={"sheet": destination sheet, "source_sheet"?: str, '
            '"name": str, "source_ranges": [A1 ranges], '
            '"type": "column"|"bar"|"line", '
            '"data_row_source"?: "auto"|"rows"|"columns", '
            '"column_headers"?: bool, "row_headers"?: bool, '
            '"title"?: str, "replace"?: bool, '
            '"position"?: {"x"?: int,"y"?: int,"width"?: positive int,'
            '"height"?: positive int}}; source_ranges contain ranges only, '
            "not objects. `column` creates vertical columns and `bar` creates "
            "horizontal bars. Omit data_row_source or use auto to infer whether each "
            "series occupies a row or column from the source-range shape. Use "
            "non-contiguous existing source ranges directly; "
            "for row-oriented charts, include the series-label cell and category "
            "header range alongside the value range, and keep row_headers=True. "
            "do not copy data into helper cells unless the chart cannot represent "
            "the original ranges, because extra cells change sheet_data"
        ),
        "pivot.create": (
            'params={"source_sheet": str, "source_range": str, '
            '"destination_sheet": str, "destination": top-left A1 cell or '
            '{"below_range": explicit A1 range in destination_sheet, "blank_rows": nonnegative int}, '
            '"name": str, "row_fields"?: [header], '
            '"column_fields"?: [header], "page_fields"?: [header], '
            '"data_fields": [{"field": exact source header, '
            '"aggregation"?: "sum"|"count"|"average"|"max"|"min", '
            '"show_data_as"?: "none"|"row_percentage"|'
            '"column_percentage"|"total_percentage"|"running_total"|'
            '"item_difference"|"item_percentage"|'
            '"item_percentage_difference"|"index", '
            '"reference_field"?: str,"reference_item"?: str}], '
            '"replace"?: bool,"show_filter_button"?: bool}; data field and orientation names '
            "must exactly match source headers and each orientation field may appear once. "
            "Omit unused optional row/column/page fields or pass [], and never invent "
            "an extra orientation field merely to satisfy validation. Omit "
            "show_filter_button or set it to False unless the instruction explicitly "
            "requests a visible filter selector; enabling it adds a Filter row to the "
            "pivot output and changes the worksheet layout. Returns destination_sheet "
            "and output_range, the actual occupied rectangle including headings and totals; "
            "output_last_row is the one-based last occupied row and output_row_count "
            "includes headings and totals. For n blank rows below, choose the next start "
            "row as output_last_row + n + 1, without guessing or adding the height again. "
            "The relative destination form aligns below the reference range's leftmost "
            "column, preserving requested_destination and the resolved A1 destination. "
            "Use blank_rows=0 immediately below a title when no title gap was requested; "
            "table-to-table spacing applies between tables. No content search or next "
            "table is executed; every call creates only the model-selected single pivot"
        ),
        "view.freeze_panes": (
            'params={"sheet": str, "columns": nonnegative int, '
            '"rows": nonnegative int}; freezing A1:B1 means rows=1 and columns=2'
        ),
        "view.freeze_range": (
            'params={"sheet": str, "range": A1-anchored range}; derives frozen '
            "leading row and column counts from the live range bottom-right cell"
        ),
    },
    "libreoffice_impress": {
        "presentation.inspect": (
            "params={}; returns zero-based slide and shape indices, nested paths, "
            "names, kinds, exact text and geometry; use these values instead of "
            "guessing selectors. For spatial wording such as first or top textbox, "
            "use the text shapes' geometry and reading order rather than assuming "
            "the lowest shape index, and select grouped children by path."
        ),
        "presentation.save": 'params={"url"?: str, "filter_name"?: str}',
        "presentation.export": (
            'params={"format": "pptx"|"odp"|"pdf"|"png"|"jpg", '
            '"url": absolute output path, "slide"?: nonnegative 0-based int, '
            '"pixel_width"?: positive int, "pixel_height"?: positive int}; '
            "pixel dimensions must be supplied together and are valid only for "
            "PNG/JPEG"
        ),
        "shape.export_image": (
            'params={"slide": nonnegative zero-based int, "selector": '
            '{one of "index": int, "path": [indices], "name": exact str, or '
            '"kind": substring str}, "output_path": absolute .png/.jpg path, '
            '"overwrite"?: bool}; exports the selected embedded picture itself rather '
            "than rendering the whole slide. Copy the slide index and shape selector "
            "from presentation.inspect; do not pass a PPTX/ODP file to an image editor"
        ),
        "slide.duplicate": (
            'params={"slide": nonnegative zero-based source index, '
            '"index"?: nonnegative zero-based insertion index}; omit index to insert immediately '
            "after the source"
        ),
        "slide.set_background": (
            'params={"slide": nonnegative 0-based int, '
            'one of "color": "#RRGGBB" or "image_path": str}'
        ),
        "shape.write_text": (
            'params={"slide": nonnegative 0-based int, "selector": '
            '{one or more of "index": nonnegative int,"path": [indices],"name": exact str,'
            '"text": exact str,"kind": substring str}, "text": str}; '
            "replaces text using the shape's current direct text properties; for an "
            "empty presentation placeholder, including TitleTextShape and "
            "Outliner/content placeholders, use shape.write_text_native when "
            "native inherited font, alignment, outline level, or bullet defaults matter "
            "instead of asking the Agent to enter the text through the GUI"
        ),
        "shape.write_text_native": (
            'params={"slide": nonnegative 0-based int, "selector": '
            '{one or more of "index": nonnegative int,"path": [indices],"name": exact str,'
            '"text": exact str,"kind": substring str}, "text": str, "replace"?: bool}; '
            "writes through LibreOffice native text-edit mode after deterministic UNO "
            "slide and shape selection, preserving inherited placeholder formatting. "
            "Use this for empty TitleTextShape or Outliner/content placeholders instead "
            "of manual GUI clicking; non-empty placeholders require replace=true"
        ),
        "shape.format_text": (
            'params={"slide": nonnegative 0-based int, "selector": '
            '{one or more of "index": nonnegative int,"path": [indices],"name": exact str,'
            '"text": exact str,"kind": substring str}, '
            '"color"?: "#RRGGBB"|palette name (for example "dark red 2"), "font_size"?: number, '
            '"font_name"?: str, "bold"?: bool, "italic"?: bool, '
            '"underline"?: bool, "strike"?: bool, "bullet"?: bool, '
            '"alignment"?: "left"|"center"|"right"|"justify", '
            '"match_text"?: str, "lines"?: [zero-based line index]}; '
            "selector is required and underline is boolean; optional verify uses "
            'verify=[{"type":"text_properties","slide":int,"selector":object,'
            '"expected":{"font_name"?:str,"font_size"?:number,"color"?:int,'
            '"bold"?:bool}}] (do not invent verifier type names)'
        ),
        "slide.format_text_roles": (
            'params={"slide": nonnegative 0-based int, "roles": ['
            '"all"|"title"|"content"|"body"|"table"|"text"], one or more of '
            '"color": color, "font_size": number, "font_name": str, "bold": bool, '
            '"italic": bool, "underline": bool, "strike": bool, "alignment": alignment, '
            '"overrides"?: [{"roles": [role], one or more formatting fields}]}; '
            "resolves roles from live UNO shape services, changes only supplied properties, "
            "and applies overrides after the shared base rule"
        ),
        "slide.set_role_text": (
            'params={"slide": nonnegative 0-based int, "role": '
            '"title"|"content"|"body"|"text", "text": non-empty str, '
            'optional "color": color, "font_size": number, "font_name": str, '
            '"bold": bool, "italic": bool, "underline": bool, "strike": bool, '
            '"alignment": "left"|"center"|"right"|"justify"}; resolves exactly one '
            "live semantic text role, replaces its text, applies only model-selected "
            "formatting, and verifies the resulting text and properties"
        ),
        "slides.format_text_roles": (
            'params={"slides": [unique nonnegative zero-based ints], "roles": ['
            '"all"|"title"|"content"|"body"|"table"|"text"], one or more of '
            '"color": color, "font_size": number, "font_name": str, "bold": bool, '
            '"italic": bool, "underline": bool, "strike": bool, "alignment": alignment, '
            '"overrides"?: [{"roles": [role], one or more formatting fields}]}; '
            "applies one shared rule atomically after every selected slide and live semantic "
            "role has passed preflight; use slide.format_text_roles for one slide"
        ),
        "shape.align_to_slide": (
            'params={"slide"?: zero-based int, "slide_number"?: one-based int, '
            '"selector": observed selector, "edge": "top"|"bottom"|"left"|"right"}; '
            "provide a slide reference; align to live page bounds without resizing"
        ),
        "shape.move": (
            'params={"slide"?: zero-based int, "slide_number"?: one-based int, '
            '"selector": observed selector, "x"?: int, "y"?: int}; '
            "provide a slide reference and at least one coordinate in 1/100 mm; size is preserved"
        ),
        "shape.resize": (
            'params={"slide"?: zero-based int, "slide_number"?: one-based int, '
            '"selector": observed selector, "width"?: positive int, "height"?: positive int, '
            '"width_measurement"?: {"value": number,"unit": "mm"|"cm"|"in"}, '
            '"height_measurement"?: measurement}; native sizes use 1/100 mm; '
            "position is preserved; use one representation per requested dimension"
        ),
        "shape.set_geometry": (
            'params={"slide": nonnegative 0-based int, "selector": object, '
            '"x"?: int,"y"?: int,"width"?: int,"height"?: int}; '
            "dimensions are LibreOffice 1/100 mm units; omit width when only height should change"
        ),
        "shape.fit_to_slide": (
            'params={"slide": nonnegative 0-based int, "selector": exact path or index, '
            '"mode"?: "cover"|"contain"|"stretch"}; cover centers and clips while '
            "preserving aspect ratio, so negative x/y or oversize geometry is expected"
        ),
        "table.write": (
            'params={"slide": nonnegative 0-based int, "selector"?: object, '
            '"cells": [object]}; cells must be an array, not a 2D values matrix'
        ),
        "table.replace_row": (
            'params={"slide_number": positive one-based int, "row_number": positive '
            'one-based int, "values": [strings in left-to-right column order]}; '
            "recursively resolves exactly one live table on the slide, rejects missing or "
            "ambiguous tables and dimension mismatches before mutation, then reads the row back"
        ),
        "table.format_text": (
            'params={"slide": nonnegative 0-based int, "selector": object, '
            '"cells"?: [{"row": nonnegative int,"column": nonnegative int}], '
            'one or more of "color": "#RRGGBB"|palette name (for example "dark red 2"), "font_size": number, '
            '"font_name": str, "bold": bool, "italic": bool, '
            '"underline": bool, "strike": bool, '
            '"alignment": "left"|"center"|"right"|"justify"}; '
            "omitting cells formats every cell and the action verifies the resulting "
            "text properties by reading each cell back; use this for TableShape text "
            "instead of shape.format_text or GUI formatting"
        ),
        "table.create": (
            'params={"slide": nonnegative 0-based int, "rows": positive int, '
            '"columns": positive int, "x"?: int, "y"?: int, '
            '"width"?: positive int, "height"?: positive int}; creates a new '
            "shape and does not replace an existing content placeholder; inspect "
            "the target slide and delete an empty placeholder first when the table "
            "is intended to occupy that placeholder. Reuse the placeholder x, y, "
            "and width, but omit height unless the task explicitly requests a "
            "height; the omitted-height default matches Impress native row height"
        ),
    },
    "gimp": {
        "image.export": (
            'params={"input_path": saved image filesystem path, "output_path": separate image path, '
            '"loader"?: "auto"|"jpeg", "quality"?: number[0,1]}; the output extension selects '
            "PNG, JPEG or XCF; target.path and file_type are not source/output parameters"
        ),
        "image.adjust": (
            'params={"input_path": str, "output_path": str, '
            '"brightness"?: number[-127,127], "contrast"?: number[-127,127], '
            '"saturation"?: number[-100,100], "open_in_gui"?: bool}'
        ),
        "image.crop": (
            'params={"input_path": local raster image path, "output_path": raster image path or basename, '
            '"unit": "percent"|"pixels", "top"?: nonnegative number, '
            '"right"?: nonnegative number, "bottom"?: nonnegative number, '
            '"left"?: nonnegative number, "overwrite"?: bool}; removes the requested '
            "amount from any combination of image edges, atomically saves and verifies the result. "
            "In percent mode 20 means 20 percent; a basename output is saved beside input_path"
        ),
    },
    "os": {
        "clipboard.set": (
            'params={"text": str}; writes the exact model-selected text, including '
            "newlines or an empty string, to the desktop clipboard and verifies it by read-back"
        ),
        "clipboard.get": (
            'params={"max_chars"?: int[1,1000000]}; reads desktop clipboard text '
            "without changing it and reports truncation"
        ),
        "filesystem.create_directory": (
            'params={"path": absolute|~/ directory path, "parents"?: bool}; creates the '
            "model-selected directory idempotently and verifies it exists"
        ),
        "filesystem.find": (
            'params={"name_patterns": [basename glob], "roots"?: [absolute|~/ path], '
            '"kind"?: "file"|"directory"|"any", "recursive"?: bool, '
            '"max_depth"?: int[1,8], "include_hidden"?: bool, '
            '"max_results"?: int[1,200]}; returns sorted paths and stat metadata without mutation'
        ),
        "desktop.open_path": (
            'params={"path": existing absolute|~/ path, "wait_seconds"?: number[0,10]}; '
            "opens the path with its registered desktop application"
        ),
        "desktop.set_wallpaper": (
            'params={"image_path": existing absolute|~/ raster image path}; sets the '
            "GNOME light and available dark wallpaper URIs and verifies both by read-back"
        ),
        "desktop.applications.inspect": (
            'params={"mime_type_prefixes": [MIME category], "query"?: app-name or '
            'Desktop Entry terms, "max_results"?: int[1,100], "mime_offset"?: nonnegative '
            'int, "max_mime_types_per_application"?: int[1,20]}; read-only bounded '
            "inspection of installed Desktop Entries and their advertised MIME types"
        ),
        "desktop.mime_associations.set": (
            'params={"desktop_id": exact installed .desktop ID, select exactly one: '
            '"mime_types": [1-20 exact advertised MIME] or "mime_type_prefixes": '
            "[MIME category]}; categories expand all matching advertised types for "
            "that application; verifies each selected association by read-back"
        ),
        "filesystem.rename": (
            'params={"source": absolute existing path, "destination": absolute new path, '
            '"replace"?: bool}; moves exactly the selected object without searching for it'
        ),
        "trash.list": (
            'params={"offset"?: nonnegative int, "max_results"?: int[1,200]}; '
            "read-only bounded enumeration of exact trash_uri/original_path pairs"
        ),
        "trash.restore": (
            'params={"trash_uri": exact URI from trash.list, "original_path": exact paired '
            "absolute or ~/ path}; rejects missing or mismatched pairs without filename search"
        ),
        "desktop.favorites.list": (
            'params={"offset"?: nonnegative int, "max_results"?: int[1,200]}; '
            "read-only bounded enumeration of exact current favorite Desktop Entry IDs"
        ),
        "desktop.remove_favorite": (
            'params={"desktop_id": exact ID from desktop.favorites.list ending in .desktop}; '
            "application names are not resolved"
        ),
        "terminal.show_output": (
            'params={"argv": [str], "cwd_source": "active_context"|"active_terminal"|'
            '"home"|"explicit", "cwd_path"?: absolute str, "expected_returncodes"?: [int], '
            '"provenance": "none"|"shell_history"}; runs the exact finite argv in a visible '
            "terminal, waits for its real exit status, and leaves its real output visible without "
            "requiring the output value in advance"
        ),
        "notifications.configure": (
            'params={"do_not_disturb": bool}; configures GNOME notification '
            "banners and verifies the resulting desktop state"
        ),
        "desktop.set_setting": ('params={"schema": str, "key": str, "value": scalar}'),
        "command.run": (
            'params={"argv": [str], "cwd_source": '
            '"active_terminal"|"home"|"explicit", "cwd_path"?: absolute str, '
            '"provenance": "none"|"shell_history", "input"?: str, '
            '"expected_returncodes"?: [int], "stdout_contains"?: [str], '
            '"stdout_excludes"?: [str], "stderr_contains"?: [str], '
            '"stderr_excludes"?: [str]}'
        ),
        "window.capture": (
            'params={"title_contains": observed window-title substring, "output_path": '
            'absolute|~/ PNG path, "overwrite"?: bool}; captures exactly one matching '
            "existing desktop window without running a command or launching an application"
        ),
        "filesystem.set_permissions": (
            'params={"path": exact absolute|~/ regular-file path, "mode": octal str}; '
            "changes one explicit file and rejects directories and symbolic links"
        ),
        "document.convert": (
            'params={"source": exact absolute|~/ input file, "destination": exact absolute|~/ '
            'output file, "overwrite"?: bool}; converts one selected document; the destination '
            "extension selects the LibreOffice output format"
        ),
        "pdf.form.inspect": (
            'params={"input_path": absolute|~/|local-file-URI PDF path, '
            '"field_offset"?: nonnegative int, "max_fields"?: int[1,256]}; '
            "read exact AcroForm field names, labels, types, values and writable flags"
        ),
        "pdf.form.fill": (
            'params={"input_path": PDF path, "output_path": different PDF path, '
            '"fields": [{"field_name": exact observed name, "value": literal str}], '
            '"overwrite"?: bool}; fill selected text fields and save exactly one PDF'
        ),
        "pdf.outline.inspect": (
            'params={"input_path": absolute|~/ PDF path, "outline_level": int[1,32], '
            '"offset"?: nonnegative int, "max_sections"?: int[1,50]}; read-only bounded '
            "inspection of exact outline titles and inclusive page ranges; creates no outputs"
        ),
        "pdf.pages.extract": (
            'params={"input_path": absolute|~/ PDF path, "output_path": absolute|~/ PDF '
            'path, "start_page": positive int, "end_page": positive int, "overwrite": '
            'bool, "output_backend": "preserve_pages"|"cairo"}; persists and verifies '
            "exactly one model-named inclusive page range"
        ),
        "pdf.extract_text_batch": (
            'params={"input_pattern": PDF basename glob, "cwd_source": '
            '"active_terminal"|"home"|"explicit", "cwd_path"?: absolute str, '
            '"start_page"?: positive one-based int, "page_count"?: positive int, '
            '"start_char"?: nonnegative int, "max_chars_per_file"?: int[1,20000], '
            '"include_hidden"?: bool, '
            '"preserve_layout"?: bool (defaults true; set false for prose)}; returns bounded raw text from the beginning of each '
            "matching PDF extraction, or from start_char when supplied, without modifying "
            "the files. For subsequent windows use one observed filename and its next_start_char"
        ),
        "image.extract_text_batch": (
            'params={"input_pattern": image/PDF basename glob, "cwd_source": '
            '"active_terminal"|"home"|"explicit", "cwd_path"?: absolute str, '
            '"max_chars_per_file"?: int[1,20000], "max_pages_per_pdf"?: int[1,20], '
            '"include_hidden"?: bool}; performs bounded read-only OCR on matching PNG, JPEG, '
            "TIFF, BMP, WebP, and scanned PDF files and returns per-file text and status"
        ),
    },
    "thunderbird": {
        "mail.configure": (
            'params={"identity"?: str (required for identity-specific settings), '
            '"signature_text"?: str, '
            '"quote_original_on_reply"?: bool, '
            '"automatic_filters_on_subfolders"?: bool, "unified_inbox"?: bool, '
            '"dark_mode"?: bool}; provide exactly one '
            "semantic setting; the adapter resolves and verifies Thunderbird preference keys"
        ),
        "folders.ensure_local": 'params={"names": [str]}',
        "messages.query": (
            'params={"folder_name": str, "limit"?: int[1,500], '
            '"select_from"?: "latest"|"earliest", '
            '"order"?: "ascending"|"descending", "sender_contains"?: str, '
            '"subject_contains"?: str, "after"?: ISO-8601 str, '
            '"before"?: ISO-8601 str, "has_attachments"?: bool}; returns sender name/address, '
            "subject, recipients, CC, date, message ID and attachment metadata without message bodies"
        ),
        "compose.attach": (
            'params={"subject": exact open compose subject, '
            '"attachment_path": absolute or home-relative file path}'
        ),
        "compose.set_recipients": (
            'params={"recipients": [plain email str], "mode"?: "append"|"replace", '
            '"subject"?: exact open compose subject}; updates and verifies recipient pills '
            "in one existing Thunderbird compose window and rejects ambiguous matches"
        ),
    },
    "vs_code": {
        "debugging.configure": (
            'params={"focus_editor_on_break"?: bool, "inline_values"?: '
            '"auto"|"off"|"on", "internal_console"?: "neverOpen"|'
            '"openOnFirstSessionStart"|"openOnSessionStart", "open_debug_view"?: '
            '"neverOpen"|"openOnDebugBreak"|"openOnFirstSessionStart"|'
            '"openOnSessionStart", "show_breakpoints_in_overview_ruler"?: bool, '
            '"show_inline_breakpoint_candidates"?: bool, "path"?: str}; provide at '
            "exactly one semantic debugger preference per call; repeat the action for "
            "independent settings; maps and verifies VS Code settings"
        ),
        "editor.configure": (
            'params={"wrap_tabs"?: bool, "word_wrap"?: "off"|"on"|'
            '"at_column"|"bounded", "word_wrap_column"?: int[1,1000], '
            '"minimap_enabled"?: bool, "line_numbers"?: "off"|"on"|'
            '"relative"|"interval", "sticky_scroll_enabled"?: bool, '
            '"smooth_scrolling"?: bool, "render_whitespace"?: "none"|'
            '"boundary"|"selection"|"trailing"|"all", "path"?: str}; '
            "For multi-row open-file tabs use wrap_tabs (tab bar layout, not text wrapping); "
            "provide one semantic editor preference per call; word_wrap and its related "
            "word_wrap_column may be supplied together; omit path unless the user explicitly "
            "supplies a settings.json path; repeat the action for independent settings; "
            "maps and verifies stable VS Code settings"
        ),
        "editor.open_file": (
            'params={"path": exact absolute|~/ file path, "reuse_window"?: bool}; '
            "opens only that existing file and returns the observed VS Code window ID; "
            "use workspace.find_files or filesystem.find first when the exact path is unknown"
        ),
        "ui.open_view": (
            'params={"window_id": observed wmctrl ID, "view": "explorer"|"search"|'
            '"source_control"|"run_and_debug"|"extensions"}; opens one selected activity view'
        ),
        "ui.expand_section": (
            'params={"window_id": observed wmctrl ID, "name": accessible section name}; '
            "matching is case-insensitive with repeated whitespace ignored; expands only that "
            "section in the selected VS Code window"
        ),
        "diagnostics.configure": (
            'params={"language": "python", "diagnostic": '
            '"missing_imports"|"missing_module_source"|"unused_imports"|'
            '"undefined_variables"|"unused_variables"|"optional_member_access"|'
            '"general_type_issues"|"incompatible_method_override", "severity": '
            '"error"|"warning"|"information"|"none", "path"?: str}; maps semantic '
            "diagnostic categories to verified VS Code language settings"
        ),
        "files.configure": (
            'params={"auto_save"?: "off"|"after_delay"|"on_focus_change"|'
            '"on_window_change", "auto_save_delay_ms"?: int[1,3600000], '
            '"trim_trailing_whitespace"?: bool, "insert_final_newline"?: bool, '
            '"trim_final_newlines"?: bool, "hot_exit"?: "off"|"on_exit"|'
            '"on_exit_and_window_close", "path"?: str}; provide exactly one semantic '
            "file preference per call; auto_save and auto_save_delay_ms may be paired; "
            "maps and verifies stable VS Code settings"
        ),
        "keybindings.ensure": (
            'params={"key": str, "operation": "find_in_files"|"focus_active_editor"|'
            '"focus_terminal"|"quick_open"|"save_file"|"show_command_palette"|'
            '"toggle_terminal"|"tree_view_find", "context": "always"|'
            '"debug_console_focused"|"editor_focused"|"list_find_available"|'
            '"terminal_focused", "disabled": bool, "path"?: str}; maps reusable '
            "operation and context semantics to stable VS Code identifiers, persists the "
            "negative-command form when disabled=true, and verifies the exact binding"
        ),
        "extension.install": (
            'params={"source": Marketplace publisher.name identifier or absolute local .vsix '
            'path, "source_type": "marketplace"|"vsix", "force"?: bool}; derives a local '
            "VSIX identity from its public package metadata and verifies the installed extension"
        ),
        "workspace.open": (
            'params={"path": absolute file, folder, or .code-workspace path, '
            '"reuse_window"?: bool, "close_existing"?: bool}'
        ),
        "workspace.inspect": (
            "params={}; reads the exact active VS Code workspace name, roots, window "
            "identity, and resolution source without modifying files or application state; "
            "for a saved workspace, also returns its exact .code-workspace path for a later "
            "explicit workspace.add_folders call"
        ),
        "workspace.write": (
            'params={"path": complete absolute output filename ending in .code-workspace '
            '(never the containing directory; e.g. /home/user/project/project.code-workspace), '
            '"folders": [{"path": project folder, "name"?: display name}]}; creates and '
            "verifies a VS Code workspace file, converting absolute folders to portable "
            "paths relative to the workspace when possible"
        ),
        "workspace.add_folders": (
            'params={"path": exact existing .code-workspace path or an observed active workspace root, '
            '"folders": [{"path": folder to add, "name"?: display name}]}; adds only '
            "the listed folders while preserving all existing workspace folders, settings, "
            "and other keys; skips duplicate folder paths and verifies the merged workspace. "
            "A directory is accepted only when it is the unique active workspace root and "
            "the saved workspace file is observable."
        ),
        "file.read_text": (
            'params={"path": absolute UTF-8 text or source file, "max_chars"?: int[1,100000]}; '
            "returns bounded file content, total character and line counts, and truncation state"
        ),
        "file.replace_literal": (
            'params={"path": absolute text file, "old": exact nonempty literal, "new": str}; '
            "replaces every exact occurrence and returns the updated content"
        ),
        "file.create": (
            'params={"path": absolute output file path, "content"?: str, '
            '"overwrite"?: bool, "open"?: bool}'
        ),
        "explorer.set_exclusion": (
            'params={"pattern": file or folder name or VS Code glob, '
            '"scope": "any_depth"|"workspace_root", "hidden": bool, '
            '"path"?: settings.json path}; maps the selected semantic scope to files.exclude, '
            "preserves existing exclusions and other settings, and verifies the exact result"
        ),
        "settings.update": (
            'params={"values": object, "path"?: str}; use exact VS Code '
            "setting identifiers. To keep focus away from the editor when a "
            "debugger breaks, set debug.focusEditorOnBreak=false"
        ),
        "workspace.set_folders": (
            'params={"path": absolute .code-workspace path, '
            '"folders": [{"path": str}]}; replaces the complete folders array while '
            "preserving other workspace keys; use workspace.add_folders when existing "
            "folders must remain"
        ),
        "file.indent_lines": (
            'params={"path": absolute file path, "start_line": 1-based int, '
            '"end_line": 1-based inclusive int, "levels": int[1,16]}; prefix each '
            "selected line with the requested number of existing editor indentation units; "
            "the Adapter detects tabs versus spaces and the current indentation width"
        ),
    },
    "vlc": {
        "preferences.configure": (
            'params={"global_play_pause_hotkey"?: str, '
            '"maximum_volume_percent"?: int[0,300], '
            '"volume_slider_color"?: "#RRGGBB", "minimal_interface"?: bool, '
            '"exit_after_playback"?: bool, "allow_multiple_instances"?: bool, '
            '"show_background_cone"?: bool, "recording_directory"?: absolute path, '
            '"recording_location"?: "desktop"|"downloads"|"videos"|"music"|"home"}; '
            "provide exactly one semantic setting per call; repeat the action for independent settings; "
            "the adapter maps and verifies VLC vlcrc preference keys"
        ),
        "config.update": (
            'params={"values": {preference name: string|integer|boolean}, '
            '"path"?: absolute vlcrc path}'
        ),
        "playback.open": 'params={"source": absolute local path or HTTP(S) URL, "loop"?: bool}',
        "playback.status": "params={}; returns playback state, time, position, metadata, and source",
        "window.set_fullscreen": 'params={"enabled": bool}',
        "media.extract_audio": (
            'params={"input_path": absolute path, "output_path": absolute path}'
        ),
        "media.extract_subtitles": (
            'params={"input_path": absolute video path, "output_path": absolute .srt or .vtt '
            'path, "subtitle_stream_index"?: nonnegative zero-based int}; extracts one embedded '
            "subtitle/caption stream atomically and verifies timed cues, size, and SHA-256"
        ),
        "media.transcode_clip": (
            'params={"input_path": absolute source media path, "output_path": absolute output '
            'path ending in .gif or a supported video extension, "start_time_seconds": '
            'nonnegative number, "duration_seconds": positive number, "frame_rate"?: number[1,60]}; '
            "extracts a time-bounded segment and converts it to an animated GIF or video based on "
            "the output extension"
        ),
        "media.flip_video": (
            'params={"input_path": absolute source video path, "output_path": distinct '
            'absolute .mp4 path, "axis": "vertical"|"horizontal"}; flips the complete '
            "video once and saves a new MP4 without trimming"
        ),
        "media.extract_frame": (
            'params={"input_path": absolute video path, "output_path": absolute PNG path, '
            '"frame_index": nonnegative zero-based int}'
        ),
    },
    "libreoffice_writer": {
        "document.inspect": (
            'params={"paragraph_start"?: zero-based raw index, "paragraph_limit"?: int[1,12]}; '
            "omit both for the usual overview, or read paragraph previews in pages using "
            "next_paragraph_start; returns exact table names in tables; when tables is empty, "
            "do not guess a table name and use paragraph/text actions instead"
        ),
        "document.extract_images": (
            'params={"source_path": absolute|~/|file URL DOCX|ODT path, '
            '"output_directory": absolute|~/|file URL directory, '
            '"selection"?: "first"|"all", "overwrite"?: bool}; exports embedded images '
            "in main-document reference order and returns exact paths, sizes, and SHA-256 digests"
        ),
        "document.deduplicate_records": (
            'params={"delimiter": one character, "key_column": zero-based int, '
            '"trim_key"?: bool, "case_sensitive"?: bool, "skip_blank"?: bool}; '
            "removes later duplicate body paragraphs by the selected delimited field, "
            "keeps the first occurrence and original order, and preserves complete records; "
            "inspect first and save/read back after the mutation"
        ),
        "table.read": (
            'params={"name": exact table name from document.inspect}; returns every '
            "Writer cell name and exact text without modifying the document"
        ),
        "table.set_cell_text_color": (
            'params={"name": exact table name, "cells": [explicit unique cell names], '
            '"color": "#RRGGBB"|named color}; applies one color only to the selected cells'
        ),
        "paragraph.replace_text": (
            'params={"index": zero-based raw paragraph index, "paragraphs": [exact str], '
            '"blank_paragraphs_between"?: int[0,10]}; replaces one paragraph with exact '
            "model-authored paragraphs and performs no hidden sentence splitting"
        ),
        "text.find_replace": (
            'params={"find": exact nonempty str, "replacement": str, "replace_all": bool, '
            '"case_sensitive": bool}; replaces only the literal selected by the model'
        ),
        "document.append_text_file": (
            'params={"path": exact observed text file path, "separator"?: literal str, "encoding"?: "utf-8"|"utf-8-sig"}; append ONE file verbatim to the active Writer document without retyping or changing existing content'
        ),
        "document.append_paragraphs": (
            'params={"paragraphs": [exact str], "blank_paragraphs_before"?: int[0,10], '
            '"blank_paragraphs_between"?: int[0,10]}; appends explicit paragraphs in order'
        ),
    },
    "multi_apps": {
        "adapter.call": (
            'params={"adapter": owning downstream domain, "action": exact downstream public '
            'action, "payload"?: {"params"?: object, "target"?: object, '
            '"document"?: object, "verify"?: [object], "timeout_ms"?: int}}; '
            "the model selects the owning Adapter, one public action, and every semantic argument"
        ),
    },
    "chrome": CHROME_SIGNATURES,
}


def public_actions(domain: str) -> list[str]:
    module_name = DOMAIN_SCHEMA_MODULES.get(domain)
    if module_name is None:
        raise ValueError(f"unsupported OSWorld domain: {domain}")
    actions = getattr(import_module(module_name), "ACTIONS")
    return sorted(actions)


def action_signature(domain: str, action: str) -> str:
    return DOMAIN_SIGNATURES.get(domain, {}).get(
        action,
        "public action; params are action-specific, use the exact public action name",
    )


def ordered_actions(domain: str, recommended: Iterable[str]) -> list[tuple[str, bool]]:
    available = public_actions(domain)
    recommended_set = set(recommended).intersection(available)
    return [
        (action, action in recommended_set)
        for action in sorted(
            available, key=lambda item: (item not in recommended_set, item)
        )
    ]


def format_domain_tool_catalog(domain: str, recommended: Iterable[str]) -> str:
    lines = [
        f"Public Adapter actions for this task domain ({domain}):",
        "Call as agent.adapter_call(adapter, action, params=..., target=..., "
        "document=..., verify=...).",
    ]
    for action, is_recommended in ordered_actions(domain, recommended):
        marker = " [recommended from prior evidence]" if is_recommended else ""
        lines.append(
            f'- agent.adapter_call("{domain}", "{action}", ...){marker}: '
            f"{action_signature(domain, action)}"
        )
    return "\n".join(lines)
