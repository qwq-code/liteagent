from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import jsonschema
import pytest

from integrations.lite_agent.search_recovery_tools import constrain_adapter_call_routes
from integrations.lite_agent.tool_catalog import build_tools
from writer_adapter import uno_worker
from writer_adapter.errors import AdapterError
from writer_adapter.schema import validate_action_params


ACTION = "table.set_cell_text_color"


@pytest.mark.parametrize("forwarded", [False, True])
def test_repeated_color_targets_are_valid_without_argument_rewriting(forwarded):
    params = {
        "name": "Inventory",
        "cells": ["B2", "A1", "B2"],
        "color": "#146C94",
    }
    before = deepcopy(params)
    if forwarded:
        tools = constrain_adapter_call_routes(
            build_tools(
                "multi_apps", ["adapter.call"], include_gui=False, strict_generic=True
            ),
            [("libreoffice_writer", ACTION)],
        )
        schema = next(
            tool["function"]["parameters"]
            for tool in tools
            if tool["function"]["name"] == "adapter__adapter_call"
        )["oneOf"][0]["properties"]["payload"]["properties"]["params"]
    else:
        schema = build_tools(
            "libreoffice_writer", [ACTION], include_gui=False,
            include_control_tools=False, strict_generic=True,
        )[0]["function"]["parameters"]

    jsonschema.validate(params, schema)
    validate_action_params(ACTION, params)
    assert params == before


@pytest.mark.parametrize("missing", [False, True])
def test_worker_reapplies_one_color_without_expanding_targets(monkeypatch, missing):
    cells = {
        name: SimpleNamespace(String=f"Text at {name}", Text=SimpleNamespace(name=name))
        for name in ("A1", "B2", "C3")
    }
    cursors = {name: SimpleNamespace(CharColor=0) for name in cells}
    table = SimpleNamespace(
        Name="Inventory", getCellNames=lambda: tuple(cells), getCellByName=cells.__getitem__
    )
    selected = []

    def cursor(text):
        selected.append(text.name)
        return cursors[text.name]

    monkeypatch.setattr(uno_worker, "_named_table", lambda doc, name: table)
    monkeypatch.setattr(uno_worker, "_whole_text_cursor", cursor)
    params = {
        "name": "Inventory",
        "cells": ["B2", "D4" if missing else "A1", "B2"],
        "color": "#146C94",
    }
    before = deepcopy(params)
    if missing:
        with pytest.raises(AdapterError) as caught:
            uno_worker._set_table_cell_text_color(SimpleNamespace(doc=object()), params)
        assert caught.value.code == "CELL_NOT_FOUND"
        assert selected == []
        assert all(item.CharColor == 0 for item in cursors.values())
    else:
        result = uno_worker._set_table_cell_text_color(SimpleNamespace(doc=object()), params)
        assert selected == params["cells"]
        assert [item["name"] for item in result["cells"]] == params["cells"]
        assert result["cells_changed"] == 2
        assert cursors["A1"].CharColor == cursors["B2"].CharColor == 0x146C94
        assert cursors["C3"].CharColor == 0
    assert params == before
