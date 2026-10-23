from pathlib import Path

import jsonschema
import pytest

from integrations.lite_agent.tool_catalog import DIRECT_ACTION_SCHEMAS, search_actions
from vlc_adapter.actions import VlcActions
from vlc_adapter.errors import AdapterError
from vlc_adapter.schema import validate_action_params
from vlc_adapter.tool_manifest import STRICT_ACTION_PARAM_SCHEMAS


ACTION = "media.flip_video"


def test_flip_is_discoverable_and_requires_one_axis() -> None:
    instruction = "Flip an upside-down video vertically and save a new MP4 on Desktop."
    matches = search_actions(
        "vlc", instruction, limit=7, instruction=instruction, strict_generic=True
    )
    assert matches[0]["action"] == ACTION

    valid = {
        "input_path": "/home/user/Desktop/source.mp4",
        "output_path": "/home/user/Desktop/corrected.mp4",
        "axis": "vertical",
    }
    for schema in (
        STRICT_ACTION_PARAM_SCHEMAS[ACTION],
        DIRECT_ACTION_SCHEMAS["vlc"][ACTION],
    ):
        validator = jsonschema.Draft202012Validator(schema)
        assert validator.is_valid(valid)
        assert not validator.is_valid({**valid, "axis": "diagonal"})
        assert not validator.is_valid({**valid, "duration_seconds": 10})

    validate_action_params(ACTION, valid)
    with pytest.raises(AdapterError, match="one axis"):
        validate_action_params(ACTION, {**valid, "duration_seconds": 10})
    with pytest.raises(AdapterError, match="separate output_path"):
        validate_action_params(ACTION, {**valid, "output_path": valid["input_path"]})


@pytest.mark.parametrize(
    ("axis", "filter_name"),
    [("vertical", "vflip"), ("horizontal", "hflip")],
)
def test_flip_command_preserves_full_video_and_writes_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, axis: str, filter_name: str
) -> None:
    source = tmp_path / "source.mp4"
    output = tmp_path / "output.mp4"
    source.write_bytes(b"source")

    class Runner:
        argv: list[str]

        def run(self, argv: list[str], **_kwargs: object) -> dict[str, object]:
            self.argv = argv
            Path(argv[-1]).write_bytes(b"transformed")
            return {"returncode": 0}

    runner = Runner()
    monkeypatch.setattr(
        "vlc_adapter.actions.probe_media",
        lambda _runner, path: {"path": str(path), "streams": [{"codec_type": "video"}]},
    )
    result = VlcActions(runner).media_flip_video(
        {"input_path": str(source), "output_path": str(output), "axis": axis}, 30
    )

    assert runner.argv[runner.argv.index("-vf") + 1] == filter_name
    assert "-ss" not in runner.argv and "-t" not in runner.argv
    assert source.read_bytes() == b"source"
    assert output.read_bytes() == b"transformed"
    assert result["axis"] == axis
