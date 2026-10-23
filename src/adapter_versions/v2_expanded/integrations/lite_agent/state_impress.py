"""Extracted LiteAgent support module; keep application semantics generic."""

from __future__ import annotations

import re
from typing import Any

from impress_adapter.slide_reference import slide_referenced_arguments_equal


from . import (
    impress_semantics,
)
from .adapter_results import (
    adapter_context_hint as adapter_context_hint,
    compact_adapter_body as compact_adapter_body,
)
from .completion_policy import (
    action_is_save as is_save,
    completion_claim_contradictions as completion_claim_contradictions,
)


from .instruction_semantics import (
    requested_sized_slide_image,
    requested_table_row_replacement,
    requested_last_slide_duplicate_count,
    requested_slide_background_color,
    requests_all_slide_backgrounds,
    requested_title_edge_position,
    requested_slide_title_update,
    requested_slide_title_formatting,
    requested_named_slide_table,
    requested_image_edge_position,
    requested_table_edge_position,
    requested_title_range_personal_info_cleanup,
    looks_like_personal_information,
    requested_slide_role_text_formatting,
    requested_slide_content_formatting,
)


class ImpressStateMixin:
    def initial_presentation_slide_count(self) -> int | None:
        for event in self.successful_action_events("presentation.inspect"):
            body = event.result
            hint = body.get("context_hint") if isinstance(body, dict) else None
            count = hint.get("slide_count") if isinstance(hint, dict) else None
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                return count
            result = body.get("result") if isinstance(body, dict) else None
            count = result.get("slide_count") if isinstance(result, dict) else None
            if isinstance(count, int) and not isinstance(count, bool) and count > 0:
                return count
            preview = body.get("preview") if isinstance(body, dict) else None
            if isinstance(preview, str):
                match = re.search(r'"slide_count"\s*:\s*(\d+)', preview)
                if match and int(match.group(1)) > 0:
                    return int(match.group(1))
        return None

    def all_slide_background_arguments(self) -> dict[str, Any] | None:
        color = requested_slide_background_color(self.instruction)
        if self.domain != "libreoffice_impress" or color is None:
            return None
        if not requests_all_slide_backgrounds(self.instruction):
            return None
        return {"all_slides": True, "color": color}

    def all_slide_background_readback_satisfied(self) -> bool:
        expected = self.all_slide_background_arguments()
        mutations = self.successful_action_events("slide.set_background")
        if expected is None or not mutations:
            return False
        mutation = next(
            (
                event
                for event in reversed(mutations)
                if event.proposed.get("arguments") == expected
            ),
            None,
        )
        if mutation is None:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        hint = readbacks[-1].result["context_hint"]
        slides = hint.get("slides")
        slide_count = hint.get("slide_count")
        if (
            not isinstance(slides, list)
            or not slides
            or not isinstance(slide_count, int)
            or len(slides) != slide_count
        ):
            return False
        expected_color = int(str(expected["color"]).lstrip("#"), 16)
        return all(
            isinstance(slide, dict)
            and isinstance(slide.get("background"), dict)
            and str(slide["background"].get("style", "")).casefold() == "solid"
            and slide["background"].get("color") == expected_color
            for slide in slides
        )

    def title_edge_position_plan(self) -> dict[str, Any] | None:
        request = requested_title_edge_position(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == request["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        title_shapes = [
            shape
            for shape in slide.get("all_shapes", [])
            if isinstance(shape, dict)
            and "titletextshape" in str(shape.get("kind", "")).casefold()
        ]
        if len(title_shapes) != 1:
            return None
        shape = title_shapes[0]
        geometry = {key: shape.get(key) for key in ("x", "y", "width", "height")}
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in geometry.values()
        ):
            return None
        slide_height = slide.get("height")
        if (
            isinstance(slide_height, bool)
            or not isinstance(slide_height, int)
            or slide_height <= 0
        ):
            return None
        target_y = (
            geometry["y"]
            if request["edge"] == "top"
            else slide_height - geometry["height"] - geometry["y"]
        )
        if target_y < 0:
            return None
        return {
            **request,
            "shape_name": shape.get("name"),
            "selector": {"path": shape.get("path")},
            "source_geometry": geometry,
            "target_geometry": {
                "x": geometry["x"],
                "y": target_y,
                "width": geometry["width"],
                "height": geometry["height"],
            },
            "arguments": {
                "slide": request["slide"],
                "selector": {"path": shape.get("path")},
                "x": geometry["x"],
                "y": target_y,
                "width": geometry["width"],
                "height": geometry["height"],
            },
        }

    def next_title_edge_position_action(self) -> dict[str, Any] | None:
        if requested_title_edge_position(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.title_edge_position_plan()
        if plan is None:
            return None
        if not any(
            slide_referenced_arguments_equal(
                event.proposed.get("arguments"), plan["arguments"]
            )
            for event in self.successful_action_events("shape.set_geometry")
        ):
            return {"action": "shape.set_geometry", "arguments": plan["arguments"]}
        return None

    def title_edge_position_readback_satisfied(self) -> bool:
        plan = self.title_edge_position_plan()
        mutations = self.successful_action_events("shape.set_geometry")
        if plan is None or not mutations:
            return False
        mutation = next(
            (
                event
                for event in reversed(mutations)
                if slide_referenced_arguments_equal(
                    event.proposed.get("arguments"), plan["arguments"]
                )
            ),
            None,
        )
        if mutation is None:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slides = readbacks[-1].result["context_hint"].get("slides", [])
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        shape = next(
            (
                item
                for item in slide.get("all_shapes", [])
                if isinstance(item, dict)
                and item.get("path") == plan["selector"]["path"]
            ),
            None,
        )
        return isinstance(shape, dict) and all(
            shape.get(key) == expected
            for key, expected in plan["target_geometry"].items()
        )

    def slide_title_update_plan(self) -> dict[str, Any] | None:
        request = requested_slide_title_update(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == request["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        titles = [
            shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".titletextshape")
        ]
        if len(titles) != 1:
            return None
        selector = {"path": titles[0]["path"]}
        return {
            **request,
            "shape_name": titles[0].get("name"),
            "selector": selector,
            "steps": [
                {
                    "action": "shape.write_text",
                    "arguments": {
                        "slide": request["slide"],
                        "selector": selector,
                        "text": request["text"],
                    },
                },
                {
                    "action": "shape.format_text",
                    "arguments": {
                        "slide": request["slide"],
                        "selector": selector,
                        "alignment": request["alignment"],
                    },
                },
            ],
        }

    def next_slide_title_update_action(self) -> dict[str, Any] | None:
        if requested_slide_title_update(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.slide_title_update_plan()
        if plan is None:
            return None
        for step in plan["steps"]:
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return step
        return None

    def slide_title_update_readback_satisfied(self) -> bool:
        plan = self.slide_title_update_plan()
        if plan is None or self.next_slide_title_update_action() is not None:
            return False
        mutation_events = [
            event
            for step in plan["steps"]
            for event in self.successful_action_events(step["action"])
            if event.proposed.get("arguments") == step["arguments"]
        ]
        if len(mutation_events) != len(plan["steps"]):
            return False
        last_mutation_step = max(event.step for event in mutation_events)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation_step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slide = next(
            (
                item
                for item in readbacks[-1].result["context_hint"].get("slides", [])
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        shape = next(
            (
                item
                for item in slide.get("text_shapes", [])
                if isinstance(item, dict)
                and item.get("path") == plan["selector"]["path"]
            ),
            None,
        )
        if not isinstance(shape, dict):
            return False
        observed_text = "\n".join(str(line) for line in shape.get("lines", []))
        style = shape.get("text_style")
        if observed_text != plan["text"] or not isinstance(style, dict):
            return False
        alignment_values = {
            "left": {"left", "0"},
            "right": {"right", "1"},
            "justify": {"justify", "block", "2"},
            "center": {"center", "3"},
        }
        observed_alignment = str(style.get("alignment", "")).casefold()
        return observed_alignment in alignment_values[plan["alignment"]]

    def slide_title_format_plan(self) -> dict[str, Any] | None:
        request = requested_slide_title_formatting(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        format_arguments = {
            key: value
            for key, value in request.items()
            if key in {"font_size", "bold", "underline", "color"}
        }
        resolved_targets = []
        steps = []
        for slide_index in request["slides"]:
            slide = next(
                (
                    item
                    for item in slides
                    if isinstance(item, dict) and item.get("slide") == slide_index
                ),
                None,
            )
            if not isinstance(slide, dict):
                return None
            candidates = [
                shape
                for shape in slide.get("recursive_text_shapes", [])
                if isinstance(shape, dict)
                and isinstance(shape.get("path"), list)
                and any(str(line).strip() for line in shape.get("lines", []))
            ]
            if not candidates:
                candidates = [
                    shape
                    for shape in slide.get("text_shapes", [])
                    if isinstance(shape, dict)
                    and isinstance(shape.get("path"), list)
                    and any(str(line).strip() for line in shape.get("lines", []))
                ]
            if not candidates:
                return None
            native_titles = [
                shape
                for shape in candidates
                if str(shape.get("kind", "")).casefold().endswith(".titletextshape")
            ]
            if len(native_titles) == 1:
                title = native_titles[0]
            else:

                def visual_order(shape: dict[str, Any]) -> tuple[Any, ...]:
                    def coordinate(value: Any) -> float:
                        if isinstance(value, bool) or not isinstance(
                            value, (int, float)
                        ):
                            return float("inf")
                        return float(value)

                    return (
                        coordinate(shape.get("y")),
                        coordinate(shape.get("x")),
                        tuple(shape["path"]),
                    )

                title = min(candidates, key=visual_order)
            arguments = {
                "slide": slide_index,
                "selector": {"path": title["path"]},
                **format_arguments,
            }
            resolved_targets.append(
                {
                    "slide": slide_index,
                    "selector": {"path": title["path"]},
                    "observed_name": title.get("name"),
                    "observed_text": "\n".join(
                        str(line) for line in title.get("lines", [])
                    ),
                }
            )
            steps.append({"action": "shape.format_text", "arguments": arguments})
        return {**request, "resolved_targets": resolved_targets, "steps": steps}

    def next_slide_title_format_action(self) -> dict[str, Any] | None:
        if requested_slide_title_formatting(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.slide_title_format_plan()
        if plan is None:
            return None
        for step in plan["steps"]:
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return step
        return None

    def slide_title_format_mutations_satisfied(self) -> bool:
        plan = self.slide_title_format_plan()
        return bool(
            plan and plan["steps"] and self.next_slide_title_format_action() is None
        )

    def slide_title_format_readback_satisfied(self) -> bool:
        plan = self.slide_title_format_plan()
        if plan is None or not self.slide_title_format_mutations_satisfied():
            return False
        mutation_events = [
            event
            for step in plan["steps"]
            for event in self.successful_action_events(step["action"])
            if event.proposed.get("arguments") == step["arguments"]
        ]
        if len(mutation_events) != len(plan["steps"]):
            return False
        last_mutation_step = max(event.step for event in mutation_events)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation_step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        readback_slides = readbacks[-1].result["context_hint"].get("slides", [])
        expected_color = (
            int(str(plan["color"]).lstrip("#"), 16) if "color" in plan else None
        )
        for target in plan["resolved_targets"]:
            slide = next(
                (
                    item
                    for item in readback_slides
                    if isinstance(item, dict) and item.get("slide") == target["slide"]
                ),
                None,
            )
            if not isinstance(slide, dict):
                return False
            shapes = slide.get("recursive_text_shapes", []) or slide.get(
                "text_shapes", []
            )
            shape = next(
                (
                    item
                    for item in shapes
                    if isinstance(item, dict)
                    and item.get("path") == target["selector"]["path"]
                ),
                None,
            )
            style = shape.get("text_style") if isinstance(shape, dict) else None
            if not isinstance(style, dict):
                return False
            if "font_size" in plan and float(style.get("font_size", -1)) != float(
                plan["font_size"]
            ):
                return False
            if "bold" in plan:
                try:
                    is_bold = float(style.get("bold_weight", 0)) >= 150
                except (TypeError, ValueError):
                    return False
                if is_bold is not plan["bold"]:
                    return False
            if "underline" in plan:
                observed = str(style.get("underline", "")).casefold()
                underlined = observed not in {"", "0", "none", "false"}
                if underlined is not plan["underline"]:
                    return False
            if expected_color is not None and style.get("color") != expected_color:
                return False
        return True

    def sized_slide_image_plan(self) -> dict[str, Any] | None:
        request = requested_sized_slide_image(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == request["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        initial_paths = [
            shape.get("path")
            for shape in slide.get("graphic_shapes", [])
            if isinstance(shape, dict) and isinstance(shape.get("path"), list)
        ]
        arguments = {
            **request,
            "x": 0,
            "y": 0,
        }
        return {**request, "initial_paths": initial_paths, "arguments": arguments}

    def next_sized_slide_image_action(self) -> dict[str, Any] | None:
        if requested_sized_slide_image(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.sized_slide_image_plan()
        if plan is None:
            return None
        if not any(
            event.proposed.get("arguments") == plan["arguments"]
            for event in self.successful_action_events("shape.insert_image")
        ):
            return {"action": "shape.insert_image", "arguments": plan["arguments"]}
        return None

    def sized_slide_image_readback_satisfied(self) -> bool:
        plan = self.sized_slide_image_plan()
        if plan is None or self.next_sized_slide_image_action() is not None:
            return False
        mutation = next(
            (
                event
                for event in reversed(
                    self.successful_action_events("shape.insert_image")
                )
                if event.proposed.get("arguments") == plan["arguments"]
            ),
            None,
        )
        if mutation is None:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slide = next(
            (
                item
                for item in readbacks[-1].result["context_hint"].get("slides", [])
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        initial_paths = {tuple(path) for path in plan["initial_paths"]}
        new_images = [
            shape
            for shape in slide.get("graphic_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and tuple(shape["path"]) not in initial_paths
        ]
        return len(new_images) == 1 and all(
            new_images[0].get(key) == plan[key] for key in ("width", "height")
        )

    def picture_heights_by_slide_plan(self) -> dict[str, Any] | None:
        return impress_semantics.picture_height_plan(self)

    def next_picture_heights_by_slide_action(self) -> dict[str, Any] | None:
        return impress_semantics.next_picture_height_action(self)

    def picture_heights_by_slide_readback_satisfied(self) -> bool:
        return impress_semantics.picture_height_readback_satisfied(self)

    def table_row_replacement_plan(self) -> dict[str, Any] | None:
        request = requested_table_row_replacement(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == request["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        tables = [
            shape
            for shape in slide.get("table_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and isinstance(shape.get("rows"), int)
            and isinstance(shape.get("columns"), int)
            and isinstance(shape.get("cells"), list)
        ]
        if len(tables) != 1:
            return None
        table = tables[0]
        if (
            request["row"] >= table["rows"]
            or len(request["values"]) != table["columns"]
        ):
            return None
        arguments = {
            "slide": request["slide"],
            "selector": {"path": table["path"]},
            "cells": [
                {"row": request["row"], "column": column, "text": value}
                for column, value in enumerate(request["values"])
            ],
        }
        return {
            **request,
            "selector": {"path": table["path"]},
            "observed_name": table.get("name"),
            "observed_rows": table["rows"],
            "observed_columns": table["columns"],
            "arguments": arguments,
        }

    def next_table_row_replacement_action(self) -> dict[str, Any] | None:
        if requested_table_row_replacement(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.table_row_replacement_plan()
        if plan is None:
            return None
        if not any(
            event.proposed.get("arguments") == plan["arguments"]
            for event in self.successful_action_events("table.write")
        ):
            return {"action": "table.write", "arguments": plan["arguments"]}
        return None

    def table_row_replacement_readback_satisfied(self) -> bool:
        plan = self.table_row_replacement_plan()
        if plan is None or self.next_table_row_replacement_action() is not None:
            return False
        mutation = next(
            (
                event
                for event in reversed(self.successful_action_events("table.write"))
                if event.proposed.get("arguments") == plan["arguments"]
            ),
            None,
        )
        if mutation is None:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slide = next(
            (
                item
                for item in readbacks[-1].result["context_hint"].get("slides", [])
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        table = next(
            (
                item
                for item in slide.get("table_shapes", [])
                if isinstance(item, dict)
                and item.get("path") == plan["selector"]["path"]
            ),
            None,
        )
        cells = table.get("cells") if isinstance(table, dict) else None
        return (
            isinstance(cells, list)
            and plan["row"] < len(cells)
            and cells[plan["row"]] == plan["values"]
        )

    def named_slide_table_plan(self) -> dict[str, Any] | None:
        request = requested_named_slide_table(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        matches: list[dict[str, Any]] = []
        for slide in slides:
            if not isinstance(slide, dict):
                continue
            titles = [
                shape
                for shape in slide.get("text_shapes", [])
                if isinstance(shape, dict)
                and str(shape.get("kind", "")).casefold().endswith(".titletextshape")
            ]
            if len(titles) != 1:
                continue
            title_text = "\n".join(
                str(line) for line in titles[0].get("lines", [])
            ).strip()
            if title_text.casefold() == request["slide_title"].casefold():
                matches.append(slide)
        if len(matches) != 1:
            return None
        slide = matches[0]
        empty_bodies = [
            shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".outlinershape")
            and not any(str(line).strip() for line in shape.get("lines", []))
        ]
        if len(empty_bodies) != 1:
            return None
        body_text = empty_bodies[0]
        body = next(
            (
                shape
                for shape in slide.get("all_shapes", [])
                if isinstance(shape, dict) and shape.get("path") == body_text["path"]
            ),
            None,
        )
        if not isinstance(body, dict):
            return None
        geometry = {key: body.get(key) for key in ("x", "y", "width")}
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in geometry.values()
        ):
            return None
        slide_index = slide.get("slide")
        if isinstance(slide_index, bool) or not isinstance(slide_index, int):
            return None
        initial_table_paths = [
            shape.get("path")
            for shape in slide.get("all_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".tableshape")
        ]
        steps = [
            {
                "action": "shape.delete",
                "arguments": {"slide": slide_index, "selector": {"path": body["path"]}},
            },
            {
                "action": "table.create",
                "arguments": {
                    "slide": slide_index,
                    "rows": request["rows"],
                    "columns": request["columns"],
                    **geometry,
                },
            },
        ]
        return {
            **request,
            "slide": slide_index,
            "body_selector": {"path": body["path"]},
            "geometry": geometry,
            "initial_table_paths": initial_table_paths,
            "steps": steps,
        }

    def next_named_slide_table_action(self) -> dict[str, Any] | None:
        if requested_named_slide_table(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.named_slide_table_plan()
        if plan is None:
            return None
        for step in plan["steps"]:
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return step
        return None

    def named_slide_table_readback_satisfied(self) -> bool:
        plan = self.named_slide_table_plan()
        if plan is None or self.next_named_slide_table_action() is not None:
            return False
        mutation_events = [
            event
            for step in plan["steps"]
            for event in self.successful_action_events(step["action"])
            if event.proposed.get("arguments") == step["arguments"]
        ]
        if len(mutation_events) != len(plan["steps"]):
            return False
        create_event = next(
            event
            for event in mutation_events
            if event.proposed.get("action") == "table.create"
        )
        create_result = (
            create_event.result.get("result")
            if isinstance(create_event.result, dict)
            else None
        )
        if not (
            isinstance(create_result, dict)
            and create_result.get("rows") == plan["rows"]
            and create_result.get("columns") == plan["columns"]
            and isinstance(create_result.get("height"), int)
            and create_result["height"] > 0
        ):
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > max(item.step for item in mutation_events)
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slide = next(
            (
                item
                for item in readbacks[-1].result["context_hint"].get("slides", [])
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        initial_paths = {tuple(path) for path in plan["initial_table_paths"]}
        new_tables = [
            shape
            for shape in slide.get("all_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".tableshape")
            and tuple(shape["path"]) not in initial_paths
        ]
        expected_geometry = {**plan["geometry"], "height": create_result["height"]}
        return len(new_tables) == 1 and all(
            new_tables[0].get(key) == value for key, value in expected_geometry.items()
        )

    def image_edge_position_plan(self) -> dict[str, Any] | None:
        request = requested_image_edge_position(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == request["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        images = [
            shape
            for shape in slide.get("graphic_shapes", [])
            if isinstance(shape, dict) and isinstance(shape.get("path"), list)
        ]
        if len(images) != 1:
            return None
        shape = images[0]
        geometry = {key: shape.get(key) for key in ("x", "y", "width", "height")}
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in geometry.values()
        ):
            return None
        slide_width = slide.get("width")
        if isinstance(slide_width, bool) or not isinstance(slide_width, int):
            return None
        mirrored_x = slide_width - geometry["width"] - geometry["x"]
        if mirrored_x < 0:
            return None
        center_x = geometry["x"] + geometry["width"] / 2
        target_x = geometry["x"]
        if request["edge"] == "right" and center_x < slide_width / 2:
            target_x = mirrored_x
        elif request["edge"] == "left" and center_x > slide_width / 2:
            target_x = mirrored_x
        target_geometry = {**geometry, "x": target_x}
        return {
            **request,
            "shape_name": shape.get("name"),
            "selector": {"path": shape["path"]},
            "source_geometry": geometry,
            "target_geometry": target_geometry,
            "arguments": {
                "slide": request["slide"],
                "selector": {"path": shape["path"]},
                **target_geometry,
            },
        }

    def next_image_edge_position_action(self) -> dict[str, Any] | None:
        if requested_image_edge_position(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.image_edge_position_plan()
        if plan is None:
            return None
        if not any(
            slide_referenced_arguments_equal(
                event.proposed.get("arguments"), plan["arguments"]
            )
            for event in self.successful_action_events("shape.set_geometry")
        ):
            return {"action": "shape.set_geometry", "arguments": plan["arguments"]}
        return None

    def image_edge_position_readback_satisfied(self) -> bool:
        plan = self.image_edge_position_plan()
        if plan is None:
            return False
        mutation = next(
            (
                event
                for event in reversed(
                    self.successful_action_events("shape.set_geometry")
                )
                if slide_referenced_arguments_equal(
                    event.proposed.get("arguments"), plan["arguments"]
                )
            ),
            None,
        )
        if mutation is None:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slide = next(
            (
                item
                for item in readbacks[-1].result["context_hint"].get("slides", [])
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        shape = next(
            (
                item
                for item in slide.get("graphic_shapes", [])
                if isinstance(item, dict)
                and item.get("path") == plan["selector"]["path"]
            ),
            None,
        )
        return isinstance(shape, dict) and all(
            shape.get(key) == value for key, value in plan["target_geometry"].items()
        )

    def table_edge_position_plan(self) -> dict[str, Any] | None:
        request = requested_table_edge_position(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == request["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        tables = [
            shape
            for shape in slide.get("all_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".tableshape")
        ]
        if len(tables) != 1:
            return None
        shape = tables[0]
        geometry = {key: shape.get(key) for key in ("x", "y", "width", "height")}
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in geometry.values()
        ):
            return None
        slide_height = slide.get("height")
        if (
            isinstance(slide_height, bool)
            or not isinstance(slide_height, int)
            or slide_height <= 0
        ):
            return None
        target_y = 0 if request["edge"] == "top" else slide_height - geometry["height"]
        if target_y < 0:
            return None
        target_geometry = {**geometry, "y": target_y}
        return {
            **request,
            "shape_name": shape.get("name"),
            "selector": {"path": shape["path"]},
            "source_geometry": geometry,
            "target_geometry": target_geometry,
            "arguments": {
                "slide": request["slide"],
                "selector": {"path": shape["path"]},
                **target_geometry,
            },
        }

    def next_table_edge_position_action(self) -> dict[str, Any] | None:
        if requested_table_edge_position(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.table_edge_position_plan()
        if plan is None:
            return None
        if not any(
            slide_referenced_arguments_equal(
                event.proposed.get("arguments"), plan["arguments"]
            )
            for event in self.successful_action_events("shape.set_geometry")
        ):
            return {"action": "shape.set_geometry", "arguments": plan["arguments"]}
        return None

    def table_edge_position_readback_satisfied(self) -> bool:
        plan = self.table_edge_position_plan()
        if plan is None:
            return False
        mutation = next(
            (
                event
                for event in reversed(
                    self.successful_action_events("shape.set_geometry")
                )
                if slide_referenced_arguments_equal(
                    event.proposed.get("arguments"), plan["arguments"]
                )
            ),
            None,
        )
        if mutation is None:
            return False
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > mutation.step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slide = next(
            (
                item
                for item in readbacks[-1].result["context_hint"].get("slides", [])
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        shape = next(
            (
                item
                for item in slide.get("all_shapes", [])
                if isinstance(item, dict)
                and item.get("path") == plan["selector"]["path"]
            ),
            None,
        )
        return isinstance(shape, dict) and all(
            shape.get(key) == value for key, value in plan["target_geometry"].items()
        )

    def title_range_personal_info_cleanup_plan(self) -> dict[str, Any] | None:
        request = requested_title_range_personal_info_cleanup(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None

        steps: list[dict[str, Any]] = []
        title_paths: list[dict[str, Any]] = []
        for slide_index in request["title_slides"]:
            slide = next(
                (
                    item
                    for item in slides
                    if isinstance(item, dict) and item.get("slide") == slide_index
                ),
                None,
            )
            if not isinstance(slide, dict):
                return None
            candidates = [
                shape
                for shape in slide.get("text_shapes", [])
                if isinstance(shape, dict)
                and isinstance(shape.get("path"), list)
                and isinstance(shape.get("y"), int)
                and any(str(line).strip() for line in shape.get("lines", []))
            ]
            if not candidates:
                return None
            title = min(candidates, key=lambda shape: (shape["y"], shape.get("x", 0)))
            selector = {"path": title["path"]}
            title_paths.append({"slide": slide_index, "path": title["path"]})
            steps.append(
                {
                    "action": "shape.format_text",
                    "arguments": {
                        "slide": slide_index,
                        "selector": selector,
                        "color": request["color"],
                        "bold": True,
                    },
                }
            )

        cleanup_slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict)
                and item.get("slide") == request["cleanup_slide"]
            ),
            None,
        )
        if not isinstance(cleanup_slide, dict):
            return None
        initial_cleanup_shape_count = cleanup_slide.get("shape_count")
        if not isinstance(initial_cleanup_shape_count, int):
            return None
        personal_shapes = []
        for shape in cleanup_slide.get("text_shapes", []):
            if not isinstance(shape, dict) or not isinstance(shape.get("path"), list):
                continue
            text = "\n".join(str(line) for line in shape.get("lines", [])).strip()
            if text and looks_like_personal_information(text):
                personal_shapes.append(shape)
        if not personal_shapes:
            return None
        delete_paths = {tuple(shape["path"]) for shape in personal_shapes}
        if request["include_icons"]:
            slide_width = cleanup_slide.get("width")
            slide_height = cleanup_slide.get("height")
            if isinstance(slide_width, int) and isinstance(slide_height, int):
                for shape in cleanup_slide.get("all_shapes", []):
                    if not isinstance(shape, dict) or not isinstance(
                        shape.get("path"), list
                    ):
                        continue
                    geometry = [shape.get(key) for key in ("x", "y", "width", "height")]
                    if not all(isinstance(value, int) for value in geometry):
                        continue
                    x, y, width, height = geometry
                    if width > slide_width * 0.08 or height > slide_height * 0.08:
                        continue
                    center_y = y + height / 2
                    if any(
                        isinstance(person.get("x"), int)
                        and isinstance(person.get("y"), int)
                        and isinstance(person.get("height"), int)
                        and x + width <= person["x"]
                        and abs(center_y - (person["y"] + person["height"] / 2))
                        <= slide_height * 0.08
                        for person in personal_shapes
                    ):
                        delete_paths.add(tuple(shape["path"]))
        for path in sorted(delete_paths, reverse=True):
            steps.append(
                {
                    "action": "shape.delete",
                    "arguments": {
                        "slide": request["cleanup_slide"],
                        "selector": {"path": list(path)},
                    },
                }
            )
        return {
            **request,
            "title_paths": title_paths,
            "deleted_paths": [list(path) for path in sorted(delete_paths)],
            "initial_cleanup_shape_count": initial_cleanup_shape_count,
            "steps": steps,
        }

    def next_title_range_personal_info_cleanup_action(self) -> dict[str, Any] | None:
        if requested_title_range_personal_info_cleanup(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.title_range_personal_info_cleanup_plan()
        if plan is None:
            return None
        for step in plan["steps"]:
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return step
        return None

    def title_range_personal_info_cleanup_readback_satisfied(self) -> bool:
        plan = self.title_range_personal_info_cleanup_plan()
        if (
            plan is None
            or self.next_title_range_personal_info_cleanup_action() is not None
        ):
            return False
        mutation_events = [
            event
            for step in plan["steps"]
            for event in self.successful_action_events(step["action"])
            if event.proposed.get("arguments") == step["arguments"]
        ]
        if len(mutation_events) != len(plan["steps"]):
            return False
        last_mutation = max(event.step for event in mutation_events)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slides = readbacks[-1].result["context_hint"].get("slides", [])
        for target in plan["title_paths"]:
            slide = next(
                (item for item in slides if item.get("slide") == target["slide"]), None
            )
            if not isinstance(slide, dict):
                return False
            shape = next(
                (
                    item
                    for item in slide.get("text_shapes", [])
                    if item.get("path") == target["path"]
                ),
                None,
            )
            style = shape.get("text_style") if isinstance(shape, dict) else None
            if not isinstance(style, dict):
                return False
            if str(style.get("color", "")).upper() not in {"#000000", "0"}:
                return False
            if float(style.get("bold_weight", 0)) < 150:
                return False
        cleanup = next(
            (item for item in slides if item.get("slide") == plan["cleanup_slide"]),
            None,
        )
        if not isinstance(cleanup, dict):
            return False
        expected_count = plan["initial_cleanup_shape_count"] - len(
            plan["deleted_paths"]
        )
        if cleanup.get("shape_count") != expected_count:
            return False
        return not any(
            looks_like_personal_information(
                "\n".join(str(line) for line in shape.get("lines", []))
            )
            for shape in cleanup.get("text_shapes", [])
            if isinstance(shape, dict)
        )

    def slide_role_text_format_plan(self) -> dict[str, Any] | None:
        request = requested_slide_role_text_formatting(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide_index = request["slide"]
        if slide_index is None:
            if initial.get("slide_count") != 1:
                return None
            slide_index = 0
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == slide_index
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None

        text_shapes = [
            shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict) and isinstance(shape.get("path"), list)
        ]
        body_shapes = [
            shape
            for shape in text_shapes
            if str(shape.get("kind", "")).casefold().endswith(".outlinershape")
        ]
        title_shapes = [
            shape
            for shape in text_shapes
            if str(shape.get("kind", "")).casefold().endswith(".titletextshape")
        ]
        other_shapes = [
            shape
            for shape in text_shapes
            if shape not in body_shapes and shape not in title_shapes
        ]
        table_shapes = [
            shape
            for shape in slide.get("all_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".tableshape")
        ]
        if not body_shapes or not title_shapes or not table_shapes:
            return None

        steps: list[dict[str, Any]] = []
        for role, shapes, underline in (
            ("body", body_shapes, request["body_underline"]),
            ("title", title_shapes, request["non_body_underline"]),
            ("other", other_shapes, request["non_body_underline"]),
        ):
            for shape in shapes:
                steps.append(
                    {
                        "role": role,
                        "action": "shape.format_text",
                        "arguments": {
                            "slide": slide_index,
                            "selector": {"path": shape["path"]},
                            "color": request["color"],
                            "underline": underline,
                        },
                        "shape_name": shape.get("name"),
                    }
                )
        for shape in table_shapes:
            steps.append(
                {
                    "role": "table",
                    "action": "table.format_text",
                    "arguments": {
                        "slide": slide_index,
                        "selector": {"path": shape["path"]},
                        "color": request["color"],
                        "underline": request["non_body_underline"],
                    },
                    "shape_name": shape.get("name"),
                }
            )
        return {**request, "slide": slide_index, "steps": steps}

    def next_slide_role_text_format_action(self) -> dict[str, Any] | None:
        if requested_slide_role_text_formatting(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.slide_role_text_format_plan()
        if plan is None:
            return None
        for step in plan["steps"]:
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return step
        return None

    def slide_role_text_format_mutations_satisfied(self) -> bool:
        plan = self.slide_role_text_format_plan()
        return bool(
            plan and plan["steps"] and self.next_slide_role_text_format_action() is None
        )

    def slide_role_text_format_readback_satisfied(self) -> bool:
        plan = self.slide_role_text_format_plan()
        if plan is None or not self.slide_role_text_format_mutations_satisfied():
            return False
        mutation_events = [
            event
            for step in plan["steps"]
            for event in self.successful_action_events(step["action"])
            if event.proposed.get("arguments") == step["arguments"]
        ]
        if len(mutation_events) != len(plan["steps"]):
            return False
        last_mutation_step = max(event.step for event in mutation_events)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation_step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slides = readbacks[-1].result["context_hint"].get("slides", [])
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        expected_color = int(str(plan["color"]).lstrip("#"), 16)
        observed_text = {
            tuple(shape.get("path", [])): shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict) and isinstance(shape.get("path"), list)
        }
        for step in plan["steps"]:
            if step["action"] != "shape.format_text":
                continue
            shape = observed_text.get(tuple(step["arguments"]["selector"]["path"]))
            style = shape.get("text_style") if isinstance(shape, dict) else None
            if not isinstance(style, dict):
                return False
            if style.get("color") != expected_color:
                return False
            expected_underline = 1 if step["arguments"]["underline"] else 0
            if style.get("underline") != expected_underline:
                return False

        for step in plan["steps"]:
            if step["action"] != "table.format_text":
                continue
            event = next(
                (
                    item
                    for item in mutation_events
                    if item.proposed.get("action") == "table.format_text"
                    and item.proposed.get("arguments") == step["arguments"]
                ),
                None,
            )
            hint = (
                event.result.get("context_hint")
                if event and isinstance(event.result, dict)
                else None
            )
            cells = hint.get("cells") if isinstance(hint, dict) else None
            rows = hint.get("rows") if isinstance(hint, dict) else None
            columns = hint.get("columns") if isinstance(hint, dict) else None
            if not isinstance(cells, list) or not cells:
                return False
            if (
                isinstance(rows, int)
                and isinstance(columns, int)
                and len(cells) != rows * columns
            ):
                return False
            for cell in cells:
                properties = cell.get("properties") if isinstance(cell, dict) else None
                if not isinstance(properties, dict):
                    return False
                if int(properties.get("CharColor", -1)) != expected_color:
                    return False
                expected = "1" if step["arguments"]["underline"] else "0"
                if str(properties.get("CharUnderline")) != expected:
                    return False
        return True

    def slide_content_format_plan(self) -> dict[str, Any] | None:
        request = requested_slide_content_formatting(self.instruction)
        initial = self.initial_presentation_context_hint()
        slides = initial.get("slides") if isinstance(initial, dict) else None
        if request is None or not isinstance(slides, list):
            return None
        slide_index = request["slide"]
        if slide_index is None:
            if initial.get("slide_count") != 1:
                return None
            slide_index = 0
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == slide_index
            ),
            None,
        )
        if not isinstance(slide, dict):
            return None
        content_shapes = [
            shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict)
            and isinstance(shape.get("path"), list)
            and str(shape.get("kind", "")).casefold().endswith(".outlinershape")
        ]
        if not content_shapes:
            return None
        steps = [
            {
                "role": "content",
                "action": "shape.format_text",
                "arguments": {
                    "slide": slide_index,
                    "selector": {"path": shape["path"]},
                    "font_size": request["font_size"],
                    "color": request["font_color"],
                },
                "shape_name": shape.get("name"),
            }
            for shape in content_shapes
        ]
        steps.append(
            {
                "role": "slide_background",
                "action": "slide.set_background",
                "arguments": {
                    "slide": slide_index,
                    "color": request["background_color"],
                },
            }
        )
        return {**request, "slide": slide_index, "steps": steps}

    def next_slide_content_format_action(self) -> dict[str, Any] | None:
        if requested_slide_content_formatting(self.instruction) is None:
            return None
        if not self.successful_action_events("presentation.inspect"):
            return {"action": "presentation.inspect", "arguments": {}}
        plan = self.slide_content_format_plan()
        if plan is None:
            return None
        for step in plan["steps"]:
            if not any(
                event.proposed.get("arguments") == step["arguments"]
                for event in self.successful_action_events(step["action"])
            ):
                return step
        return None

    def slide_content_format_mutations_satisfied(self) -> bool:
        plan = self.slide_content_format_plan()
        return bool(
            plan and plan["steps"] and self.next_slide_content_format_action() is None
        )

    def slide_content_format_readback_satisfied(self) -> bool:
        plan = self.slide_content_format_plan()
        if plan is None or not self.slide_content_format_mutations_satisfied():
            return False
        mutation_events = [
            event
            for step in plan["steps"]
            for event in self.successful_action_events(step["action"])
            if event.proposed.get("arguments") == step["arguments"]
        ]
        if len(mutation_events) != len(plan["steps"]):
            return False
        last_mutation_step = max(event.step for event in mutation_events)
        saves = [
            event
            for event in self.successful_adapter_events()
            if is_save(str(event.proposed.get("action", "")))
            and event.step > last_mutation_step
        ]
        if not saves:
            return False
        readbacks = [
            event
            for event in self.successful_action_events("presentation.inspect")
            if event.step > saves[-1].step
            and isinstance(event.result, dict)
            and isinstance(event.result.get("context_hint"), dict)
        ]
        if not readbacks:
            return False
        slides = readbacks[-1].result["context_hint"].get("slides", [])
        slide = next(
            (
                item
                for item in slides
                if isinstance(item, dict) and item.get("slide") == plan["slide"]
            ),
            None,
        )
        if not isinstance(slide, dict):
            return False
        background = slide.get("background")
        expected_background = int(str(plan["background_color"]).lstrip("#"), 16)
        if not (
            isinstance(background, dict)
            and str(background.get("style", "")).casefold() == "solid"
            and background.get("color") == expected_background
        ):
            return False
        expected_color = int(str(plan["font_color"]).lstrip("#"), 16)
        observed_text = {
            tuple(shape.get("path", [])): shape
            for shape in slide.get("text_shapes", [])
            if isinstance(shape, dict) and isinstance(shape.get("path"), list)
        }
        for step in plan["steps"]:
            if step["action"] != "shape.format_text":
                continue
            shape = observed_text.get(tuple(step["arguments"]["selector"]["path"]))
            style = shape.get("text_style") if isinstance(shape, dict) else None
            if not isinstance(style, dict):
                return False
            if style.get("color") != expected_color:
                return False
            if float(style.get("font_size", -1)) != float(plan["font_size"]):
                return False
        return True

    def next_slide_duplicate_spec(self) -> dict[str, int] | None:
        required = requested_last_slide_duplicate_count(self.instruction)
        initial_count = self.initial_presentation_slide_count()
        completed = len(self.successful_action_events("slide.duplicate"))
        if (
            required is None
            or initial_count is None
            or required > initial_count
            or completed >= required
        ):
            return None
        return {
            "sequence": completed + 1,
            "required": required,
            "slide": initial_count - required + completed,
            "index": initial_count + completed,
        }
