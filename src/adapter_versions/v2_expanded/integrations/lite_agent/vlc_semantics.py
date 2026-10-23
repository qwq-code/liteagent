from __future__ import annotations

import re


_PLAY_RE = re.compile(r"(?i)(?<![/\w])(?:open|play|start)\b")
_FUTURE_USE_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:so\s+(?:that\s+)?)?(?:I|we)\s+(?:can|could|may|might|will|would)\s+"
    r"(?:open|play|start)\b|"
    r"to\s+(?:open|play|start)\s+(?:(?:it|them)\s+)?"
    r"\b(?:later|whenever|anytime|tomorrow|eventually|in\s+the\s+future)\b)"
)
_LOCAL_LOCATION_RE = re.compile(r"(?i)\b(?:desktop|downloads?|videos|music|home)\b")
_MEDIA_RE = re.compile(r"(?i)\b(?:audio|clip|movie|music|song|track|video)\b")
_RECORDING_RE = re.compile(r"(?i)\brecord(?:ed|ing|ings)?\b")
_DIRECTORY_RE = re.compile(r"(?i)\b(?:directory|folder|path|location)\b")
_EXPLICIT_PATH_RE = re.compile(r"(?<![\w])(?:/|~/)[^\s\"']+")


def required_actions(domain: str, instruction: str) -> list[str]:
    """Return reusable VLC operation classes without extracting their arguments."""
    if domain != "vlc":
        return []
    actions: list[str] = []
    if _RECORDING_RE.search(instruction) and (
        _DIRECTORY_RE.search(instruction)
        or re.search(r"(?<![\w.-])/[\w .~/-]+", instruction)
    ):
        actions.append("preferences.configure")
    if (
        _PLAY_RE.search(_FUTURE_USE_RE.sub("", instruction))
        and _LOCAL_LOCATION_RE.search(instruction)
        and _MEDIA_RE.search(instruction)
    ):
        if not _EXPLICIT_PATH_RE.search(instruction):
            actions.append("playback.find_local")
        actions.append("playback.open")
    return actions
