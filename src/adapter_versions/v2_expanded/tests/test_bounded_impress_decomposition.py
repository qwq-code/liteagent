from __future__ import annotations

import pytest

from integrations.lite_agent.agent import LiteAgent
from integrations.lite_agent.completion import CompletionMixin
from integrations.lite_agent.instruction_semantics import (
    instruction_required_actions,
    requested_audio_path,
    requests_presentation_audio_insertion,
    strict_instruction_required_actions,
)
from integrations.lite_agent.state_model import RuntimeState
from integrations.lite_agent.tool_catalog import (
    DIRECT_ACTION_SCHEMAS,
    public_actions,
    search_actions,
    select_actions,
)
from impress_adapter.errors import AdapterError as ImpressAdapterError
from impress_adapter.schema import ACTIONS as IMPRESS_ACTIONS
from impress_adapter.schema import validate_action_params
from impress_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS
from impress_adapter.uno_worker import ACTIONS as IMPRESS_WORKERS


RETIRED_WORKFLOWS = {
    "picture.fit_to_slide",
    "picture.set_size",
    "slide.create_summary",
    "slide.copy_title_to_notes",
    "slide.format_textboxes",
    "slide.remove_personal_information",
    "slide.set_orientation",
    "slides.format_textboxes",
}
ATOMIC_REPLACEMENTS = {
    "presentation.inspect",
    "shape.create_text",
    "shape.delete",
    "shape.fit_to_slide",
    "slide.set_notes",
    "slide.create",
    "shape.format_text",
    "shape.write_text",
}


def test_impress_macros_are_absent_and_atomic_replacements_are_public() -> None:
    surfaces = (
        set(IMPRESS_ACTIONS),
        set(IMPRESS_WORKERS),
        set(STRICT_ACTION_PARAM_SCHEMAS),
        set(DIRECT_ACTION_SCHEMAS["libreoffice_impress"]),
        set(public_actions("libreoffice_impress")),
    )

    assert all(RETIRED_WORKFLOWS.isdisjoint(surface) for surface in surfaces)
    assert ATOMIC_REPLACEMENTS.issubset(set(IMPRESS_ACTIONS))
    assert ATOMIC_REPLACEMENTS.issubset(set(IMPRESS_WORKERS))
    assert "shape.format_text" in STRICT_ACTION_PARAM_SCHEMAS
    assert ATOMIC_REPLACEMENTS.issubset(
        set(DIRECT_ACTION_SCHEMAS["libreoffice_impress"])
    )
    assert ATOMIC_REPLACEMENTS.issubset(set(public_actions("libreoffice_impress")))


def test_title_to_notes_is_observation_then_explicit_note_write() -> None:
    instruction = "Copy the title of slide 2 into its speaker notes."

    assert strict_instruction_required_actions("libreoffice_impress", instruction) == [
        "presentation.inspect",
        "slide.set_notes",
    ]
    arguments = {"slide": 1, "text": "Observed title from a different deck"}
    validate_action_params("slide.set_notes", arguments)

    state = RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_impress",
        instruction=instruction,
    )
    LiteAgent._validate_stateful_arguments(state, "slide.set_notes", arguments)
    assert arguments == {
        "slide": 1,
        "text": "Observed title from a different deck",
    }


def test_shape_fit_requires_an_exact_observed_selector() -> None:
    validate_action_params(
        "shape.fit_to_slide",
        {"slide": 0, "selector": {"path": [2, 0]}, "mode": "cover"},
    )

    with pytest.raises(ImpressAdapterError, match="exact path or only an exact index"):
        validate_action_params(
            "shape.fit_to_slide",
            {
                "slide": 0,
                "selector": {
                    "kind": "graphic",
                    "orientation": "landscape",
                    "rank": "largest_area",
                },
                "mode": "cover",
            },
        )


def test_picture_requests_route_to_exact_shape_primitives() -> None:
    cover = (
        "On slide 2, make the wide image cover the entire slide while preserving "
        "its proportions."
    )
    height = "Change the picture height to 4 cm on slide 1."
    orientation = "Change the presentation from landscape to portrait."

    assert strict_instruction_required_actions(
        "libreoffice_impress", cover
    ) == ["presentation.inspect", "shape.fit_to_slide"]
    assert strict_instruction_required_actions(
        "libreoffice_impress", height
    ) == ["presentation.inspect", "shape.set_geometry"]
    assert strict_instruction_required_actions(
        "libreoffice_impress", orientation
    ) == []


@pytest.mark.parametrize(
    "instruction",
    [
        (
            "I am making PPT about the history of baseball. I want to add an "
            'introduction audio named "Baseball.mp3" on the Desktop into my PPT, '
            "but I do not know how. Could you help me add audio into my presentation file?"
        ),
        (
            "Insert the introduction audio file 'QuarterlyIntro.ogg' from the Desktop "
            "into the open presentation."
        ),
        (
            'The Desktop contains "Theme.m4a". Use it as background music in this '
            "slideshow."
        ),
    ],
)
def test_audio_instruction_routes_inspect_then_model_selected_insert(
    instruction: str,
) -> None:
    assert requests_presentation_audio_insertion(instruction)

    expected = ["presentation.inspect", "audio.insert"]
    assert (
        strict_instruction_required_actions("libreoffice_impress", instruction)
        == expected
    )
    assert instruction_required_actions("libreoffice_impress", instruction) == expected
    assert set(expected).issubset(
        select_actions(
            "libreoffice_impress",
            instruction,
            recommended=expected,
            limit=7,
        )
    )

    audio_path = requested_audio_path(instruction)
    assert audio_path is not None
    state = RuntimeState(
        task_id="synthetic-audio-task",
        domain="libreoffice_impress",
        instruction=instruction,
    )
    assert any(
        "insert the requested Desktop audio" in item
        for item in CompletionMixin._completion_gate(state)["missing"]
    )
    good_arguments = {"slide": 0, "path": audio_path}
    LiteAgent._validate_stateful_arguments(state, "audio.insert", good_arguments)
    assert good_arguments == {
        "slide": 0,
        "path": audio_path,
    }

    with pytest.raises(ValueError, match="audio.insert path"):
        LiteAgent._validate_stateful_arguments(
            state,
            "audio.insert",
            {"slide": 0, "path": "/home/user/Desktop/other.ogg"},
        )


@pytest.mark.parametrize(
    "instruction",
    [
        'Play "QuarterlyIntro.ogg" from the Desktop while I review the presentation.',
        'Remove "QuarterlyIntro.ogg" from the Desktop copy of this presentation.',
        'Transcribe "QuarterlyIntro.ogg" from the Desktop into presentation notes.',
        'Delete "QuarterlyIntro.ogg" from the Desktop after opening this slideshow.',
    ],
)
def test_desktop_audio_non_insertion_does_not_route_or_validate(
    instruction: str,
) -> None:
    assert not requests_presentation_audio_insertion(instruction)
    assert "audio.insert" not in strict_instruction_required_actions(
        "libreoffice_impress", instruction
    )
    assert "audio.insert" not in instruction_required_actions(
        "libreoffice_impress", instruction
    )
    assert "audio.insert" not in strict_instruction_required_actions(
        "libreoffice_writer", instruction
    )

    state = RuntimeState(
        task_id="synthetic-non-insertion-audio-task",
        domain="libreoffice_impress",
        instruction=instruction,
    )
    assert all(
        "requested Desktop audio" not in item
        for item in CompletionMixin._completion_gate(state)["missing"]
    )
    with pytest.raises(ValueError, match="explicit presentation audio insertion"):
        LiteAgent._validate_stateful_arguments(
            state,
            "audio.insert",
            {"slide": 0, "path": "/home/user/Desktop/QuarterlyIntro.ogg"},
        )


def test_heterogeneous_textbox_formats_are_independent_model_calls() -> None:
    instruction = (
        "On slide 4, set the first text box to 18 point and the second text box "
        "to 11 point."
    )
    required = strict_instruction_required_actions("libreoffice_impress", instruction)

    assert required == ["presentation.inspect", "shape.format_text"]
    first = {
        "slide": 3,
        "selector": {"path": [2, 0]},
        "font_size": 18,
    }
    second = {
        "slide": 3,
        "selector": {"path": [5]},
        "font_size": 11,
    }
    validate_action_params("shape.format_text", first)
    validate_action_params("shape.format_text", second)

    state = RuntimeState(
        task_id="synthetic-task",
        domain="libreoffice_impress",
        instruction=instruction,
    )
    LiteAgent._validate_stateful_arguments(state, "shape.format_text", first)
    LiteAgent._validate_stateful_arguments(state, "shape.format_text", second)
    assert first["selector"] != second["selector"]


def test_search_recalls_atomic_tools_without_retired_workflows() -> None:
    title_query = "copy the observed slide title into its speaker notes"
    textbox_query = "set first text box to 18 point and second text box to 11 point"
    title_matches = {
        item["action"]
        for item in search_actions(
            "libreoffice_impress",
            title_query,
            instruction=title_query,
            limit=8,
            strict_generic=True,
        )
    }
    textbox_matches = {
        item["action"]
        for item in search_actions(
            "libreoffice_impress",
            textbox_query,
            instruction=textbox_query,
            limit=8,
            strict_generic=True,
        )
    }

    assert "slide.set_notes" in title_matches
    assert "shape.format_text" in textbox_matches
    assert RETIRED_WORKFLOWS.isdisjoint(title_matches | textbox_matches)
