"""Small generic-only action-contract transformations.

The legacy runtime still recognizes a few instruction-shaped recipes for
historical experiments.  Strict episodes expose the corresponding public
facade instead of forcing those recipes.  This module only transforms action
names; it never derives arguments or reads task identity.
"""

from __future__ import annotations

from collections.abc import Iterable


RANGE_WRITE_FACADES: frozenset[str] = frozenset()


def public_action_contract(actions: Iterable[str]) -> list[str]:
    selected = list(actions)
    if "range.set_decimal_separator" in selected:
        selected = [action for action in selected if action != "range.format"]
    if "view.freeze_range" in selected:
        selected = [action for action in selected if action != "view.freeze_panes"]
    if {"slide.format_text_roles", "slides.format_text_roles"}.intersection(selected):
        selected = [
            action
            for action in selected
            if action not in {"shape.format_text", "table.format_text"}
        ]
    return list(dict.fromkeys(selected))
