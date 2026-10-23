from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.adapter_results import adapter_context_hint
from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools, search_actions
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params
from writer_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from writer_adapter import uno_worker


STOPS = [
    {"position": {"value": 0, "unit": "mm"}, "alignment": "left"},
    {"position": {"value": 1.5, "unit": "in"}, "alignment": "center"},
    {
        "position": {"value": 6.75, "unit": "cm"},
        "alignment": "decimal",
        "decimal_character": ",",
        "fill_character": ".",
    },
]


def test_tab_alignment_usage_is_distinct_from_whole_paragraph_alignment():
    properties = STRICT_ACTION_PARAM_SCHEMAS["paragraph.set_format"]["properties"]
    assert "separate from tab_stops[].alignment" in properties["alignment"]["description"]
    tabs = properties["tab_stops"]
    usage = tabs["items"]["properties"]["alignment"]["description"]
    for semantic in (
        "left starts at position",
        "right ends at position",
        "center centers",
        "decimal places the decimal separator",
        "does not right-align the entire paragraph",
    ):
        assert semantic in usage
    assert "JSON \\t escape" in tabs["description"]
    assert "text.find_replace" in tabs["description"]
    assert "page_layouts" in tabs["description"]
    assert "omitted words are deleted" in STRICT_ACTION_PARAM_SCHEMAS[
        "paragraph.replace_text"
    ]["description"]


@pytest.mark.parametrize("wrapped", [False, True])
def test_tab_stop_schema_is_exposed_directly_and_through_forwarding(wrapped):
    if wrapped:
        tools = constrain_adapter_call_routes(
            build_tools("multi_apps", ["adapter.call"], include_gui=False),
            [("libreoffice_writer", "paragraph.set_format")],
        )
        function = next(
            tool["function"]
            for tool in tools
            if tool["function"]["name"] == "adapter__adapter_call"
        )
        schema = function["parameters"]["oneOf"][0]["properties"]["payload"][
            "properties"
        ]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer",
            ["paragraph.set_format"],
            include_gui=False,
            include_control_tools=False,
        )[0]["function"]["parameters"]
    owner = STRICT_ACTION_PARAM_SCHEMAS["paragraph.set_format"]
    assert schema["properties"]["tab_stops"] == owner["properties"]["tab_stops"]
    for stops in (STOPS, []):
        params = {"indices": [0, 2], "tab_stops": deepcopy(stops)}
        original = deepcopy(params)
        jsonschema.validate(params, schema)
        validate_action_params("paragraph.set_format", params)
        assert params == original


@pytest.fixture
def paragraphs(monkeypatch):
    paragraphs = [
        SimpleNamespace(
            String=text,
            ParaTabStops=(),
            ParaAdjust=0,
            ParaLineSpacing=SimpleNamespace(Mode=0, Height=100),
            CharHeight=12,
        )
        for text in (
            "Product\tQuantity\tCost",
            "Leave this paragraph unchanged.",
            "Total\t4\t12,50",
        )
    ]
    monkeypatch.setattr(uno_worker, "_paragraphs", lambda _: paragraphs)
    monkeypatch.setattr(uno_worker, "_select_paragraph", lambda _: SimpleNamespace())
    monkeypatch.setattr(
        uno_worker,
        "_uno_modules",
        lambda: (
            SimpleNamespace(
                createUnoStruct=lambda name: SimpleNamespace(),
                Enum=lambda name, value: SimpleNamespace(value=value),
                Char=lambda value: SimpleNamespace(value=value),
            ),
            None,
        ),
    )
    return paragraphs


def test_tab_stops_convert_units_without_splitting_text_or_changing_other_paragraphs(
    paragraphs,
):
    params = {"indices": [0, 2], "tab_stops": deepcopy(STOPS)}
    original = deepcopy(params)
    text_before = [paragraph.String for paragraph in paragraphs]
    result = uno_worker.GENERIC_ACTIONS["paragraph.set_format"](
        SimpleNamespace(doc=SimpleNamespace(Text=object())),
        params,
    )

    for index in (0, 2):
        native = paragraphs[index].ParaTabStops
        assert [stop.Position for stop in native] == [0, 3810, 6750]
        assert [stop.Alignment.value for stop in native] == [
            "LEFT",
            "CENTER",
            "DECIMAL",
        ]
        assert native[-1].DecimalChar.value == ","
        assert native[-1].FillChar.value == "."
    assert paragraphs[1].ParaTabStops == ()
    assert [paragraph.String for paragraph in paragraphs] == text_before
    assert params == original
    assert result["formats"]["tab_stops"] == STOPS
    assert result["paragraph_details"][0]["tab_stops"][1]["position"] == {
        "value": 38.1,
        "unit": "mm",
    }
    uno_worker.GENERIC_ACTIONS["paragraph.set_format"](
        SimpleNamespace(doc=SimpleNamespace(Text=object())),
        {"indices": [2], "tab_stops": []},
    )
    assert paragraphs[2].ParaTabStops == ()
    assert len(paragraphs[0].ParaTabStops) == 3


@pytest.mark.parametrize(
    ("indices", "with_tabs", "without_tabs"),
    [([0, 2], 2, 0), ([0, 1], 1, 1), ([1], 0, 1)],
)
def test_tab_stop_feedback_counts_selected_native_text_without_inserting_tabs(
    paragraphs, indices, with_tabs, without_tabs,
):
    params = {"indices": indices, "tab_stops": deepcopy(STOPS)}
    original = deepcopy(params)
    text_before = [paragraph.String for paragraph in paragraphs]

    result = uno_worker.GENERIC_ACTIONS["paragraph.set_format"](
        SimpleNamespace(doc=SimpleNamespace(Text=object())), params,
    )

    observation = result["tab_stop_observation"]
    assert observation["selected_paragraph_count"] == len(indices)
    assert observation["paragraphs_with_tabs_count"] == with_tabs
    assert observation["paragraphs_without_tabs_count"] == without_tabs
    assert ("no following text" in observation["guidance"]) == bool(without_tabs)
    if without_tabs:
        assert "text.find_replace" in observation["guidance"]
    assert [paragraph.String for paragraph in paragraphs] == text_before
    assert params == original
    assert result["formats"]["tab_stops"] == STOPS
    for index in indices:
        assert len(paragraphs[index].ParaTabStops) == len(STOPS)


def test_clearing_tab_stops_does_not_suggest_inserting_tabs(paragraphs):
    result = uno_worker.GENERIC_ACTIONS["paragraph.set_format"](
        SimpleNamespace(doc=SimpleNamespace(Text=object())),
        {"indices": [1], "tab_stops": []},
    )

    observation = result["tab_stop_observation"]
    assert observation["paragraphs_without_tabs_count"] == 1
    assert "cleared" in observation["guidance"]
    assert "text.find_replace" not in observation["guidance"]
    assert paragraphs[1].ParaTabStops == ()


def test_unrelated_paragraph_format_does_not_add_tab_stop_feedback(paragraphs):
    result = uno_worker.GENERIC_ACTIONS["paragraph.set_format"](
        SimpleNamespace(doc=SimpleNamespace(Text=object())),
        {"indices": [1], "line_spacing": 2},
    )

    assert "tab_stop_observation" not in result


@pytest.mark.parametrize(
    ("text", "offsets", "literal_count"),
    [
        ("No tab here", [], 0),
        ("West\\tDock\tPrice\t", [10, 16], 1),
        ("雪🙂\\t" + "x" * 500 + "\tend\t", [504, 508], 1),
    ],
)
def test_native_tab_positions_distinguish_literal_escapes_and_include_full_text(
    paragraphs, text, offsets, literal_count,
):
    paragraphs[0].String = text
    params = {"indices": [0], "tab_stops": deepcopy(STOPS)}
    original = deepcopy(params)

    result = uno_worker.GENERIC_ACTIONS["paragraph.set_format"](
        SimpleNamespace(doc=SimpleNamespace(Text=object())), params,
    )

    detail = result["paragraph_details"][0]
    assert detail["text"] == text[:500]
    assert detail["text_length"] == len(text)
    assert detail["has_tab_character"] == bool(offsets)
    assert detail["tab_character_offsets"] == offsets
    assert detail["literal_tab_escape_count"] == literal_count
    assert paragraphs[0].String == text
    assert params == original
    assert len(paragraphs[0].ParaTabStops) == len(STOPS)


@pytest.mark.parametrize("action", ["document.inspect", "paragraph.set_format"])
def test_native_tab_stop_observations_survive_model_projection(paragraphs, action):
    paragraphs[0].ParaTabStops = (
        SimpleNamespace(
            Position=4250,
            Alignment=SimpleNamespace(value="RIGHT"),
            DecimalChar=SimpleNamespace(value="."),
            FillChar=SimpleNamespace(value=" "),
        ),
    )
    details = uno_worker._paragraph_details(paragraphs)
    body = {
        "status": "ok",
        "result": {
            "paragraphs": [paragraph.String for paragraph in paragraphs],
            "paragraph_details": details,
            "paragraph_count": len(paragraphs),
            "nonempty_paragraph_count": len(paragraphs),
        },
    }
    context = adapter_context_hint("libreoffice_writer", action, body)
    observed = context.get("paragraph_details", context.get("formatted_paragraphs"))[0]

    assert observed["has_tab_character"] is True
    assert observed["tab_stops"] == [
        {
            "position": {"value": 42.5, "unit": "mm"},
            "alignment": "right",
            "decimal_character": ".",
            "fill_character": " ",
        }
    ]


@pytest.mark.parametrize(
    "query", ["tabstop configuration", "center tab stops", "decimal tab leader"]
)
def test_tab_format_queries_recall_the_existing_format_action(query):
    matches = search_actions(
        "libreoffice_writer", query, instruction=query, limit=3, strict_generic=True
    )
    assert any(item["action"] == "paragraph.set_format" for item in matches)
    assert all(item["action"] != "paragraph.apply_split_tabstop" for item in matches)


@pytest.mark.parametrize("query", ["insert tab", "tabstops", "replace separator with tab"])
def test_tab_insertion_queries_recall_local_literal_edit(query):
    matches = search_actions(
        "libreoffice_writer", query, instruction=query, limit=3, strict_generic=True
    )
    assert any(item["action"] == "text.find_replace" for item in matches)


def test_local_tab_insertion_preserves_model_selected_anchor_and_other_text():
    descriptor = SimpleNamespace()
    match = SimpleNamespace(String="North Pier ")
    untouched = SimpleNamespace(String="Unrelated paragraph.")
    document = SimpleNamespace(
        createReplaceDescriptor=lambda: descriptor,
        findFirst=lambda _: match,
    )
    arguments = {
        "find": "North Pier ",
        "replacement": "North Pier\t",
        "replace_all": False,
        "case_sensitive": True,
    }
    original = deepcopy(arguments)

    validate_action_params("text.find_replace", arguments)
    result = uno_worker.GENERIC_ACTIONS["text.find_replace"](
        SimpleNamespace(doc=document), arguments
    )

    assert arguments == original
    assert descriptor.SearchRegularExpression is False
    assert match.String == "North Pier\t"
    assert untouched.String == "Unrelated paragraph."
    assert result["replacement_count"] == 1


@pytest.mark.parametrize(
    "dimensions", [(21000, 29700, 2200, 1800), (21600, 27900, 1500, 2700)]
)
def test_native_page_layout_is_observed_and_preserved_in_context(dimensions):
    width, height, left, right = dimensions
    style = SimpleNamespace(
        Width=width, Height=height, LeftMargin=left, RightMargin=right,
        isInUse=lambda: True,
    )
    unused = SimpleNamespace(isInUse=lambda: False)
    styles = {"Report": style, "Unused": unused}
    family = SimpleNamespace(
        getElementNames=lambda: list(styles), getByName=styles.__getitem__,
    )
    document = SimpleNamespace(
        StyleFamilies=SimpleNamespace(getByName=lambda _: family),
    )

    observed = uno_worker._page_layout_summary(document)
    assert observed == [{
        "page_style": "Report",
        "width_mm": width / 100, "height_mm": height / 100,
        "left_margin_mm": left / 100, "right_margin_mm": right / 100,
        "body_width_mm": (width - left - right) / 100,
    }]
    context = adapter_context_hint(
        "libreoffice_writer", "document.inspect",
        {"status": "ok", "result": {"paragraphs": [], "page_layouts": observed}},
    )
    assert context["page_layouts"] == observed
    assert "before paragraph indents or text columns" in context["page_layout_guidance"]
    assert (style.Width, style.Height, style.LeftMargin, style.RightMargin) == dimensions


@pytest.mark.parametrize(
    "stop",
    [
        {"position": {"value": -1, "unit": "cm"}, "alignment": "right"},
        {"position": {"value": 5, "unit": "pixels"}, "alignment": "right"},
        {"position": {"value": 5, "unit": "cm"}, "alignment": "justify"},
        {
            "position": {"value": 5, "unit": "cm"},
            "alignment": "right",
            "fill_character": "...",
        },
    ],
)
def test_invalid_tab_settings_return_parameter_errors_without_rewriting(stop):
    params = {"indices": [0], "tab_stops": [stop]}
    original = deepcopy(params)
    schema = STRICT_ACTION_PARAM_SCHEMAS["paragraph.set_format"]
    assert not jsonschema.Draft202012Validator(schema).is_valid(params)
    with pytest.raises(AdapterError, match="tab_stops"):
        validate_action_params("paragraph.set_format", params)
    assert params == original
