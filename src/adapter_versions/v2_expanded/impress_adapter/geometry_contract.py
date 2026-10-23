from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from .errors import AdapterError


GEOMETRY_FIELDS = ("x", "y", "width", "height")
MEASUREMENT_FIELDS = ("width_measurement", "height_measurement")
MEASUREMENT_UNITS = ("mm", "cm", "in")
SHAPE_EDGES = ("top", "bottom", "left", "right")
ATOMIC_GEOMETRY_FIELDS = {
    "shape.align_to_slide": ("edge",),
    "shape.move": ("x", "y"),
    "shape.resize": ("width", "height", "width_measurement", "height_measurement"),
}

_HUNDREDTH_MM_PER_UNIT = {
    "mm": Decimal("100"),
    "cm": Decimal("1000"),
    "in": Decimal("2540"),
}


def order_shapes_by_position(
    shapes: list[dict[str, Any]], order: str
) -> list[dict[str, Any]] | None:
    """Sort observed geometry without changing native identifiers or shape records."""
    if any(
        not isinstance(shape, dict)
        or any(
            isinstance(shape.get(axis), bool) or not isinstance(shape.get(axis), int)
            for axis in ("x", "y")
        )
        for shape in shapes
    ):
        return None
    key_functions = {
        "top_to_bottom": lambda shape: (shape["y"], shape["x"]),
        "bottom_to_top": lambda shape: (-shape["y"], shape["x"]),
        "left_to_right": lambda shape: (shape["x"], shape["y"]),
        "right_to_left": lambda shape: (-shape["x"], shape["y"]),
    }
    key_function = key_functions.get(order)
    return sorted(shapes, key=key_function) if key_function is not None else None


def measurement_to_hundredth_mm(measurement: Mapping[str, Any]) -> int:
    if set(measurement) != {"value", "unit"}:
        raise AdapterError(
            "INVALID_REQUEST",
            "measurement requires exactly value and unit",
        )
    value = measurement.get("value")
    unit = measurement.get("unit")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterError("INVALID_REQUEST", "measurement.value must be a number")
    if not isinstance(unit, str) or unit not in MEASUREMENT_UNITS:
        raise AdapterError(
            "INVALID_REQUEST",
            f"measurement.unit must be one of {', '.join(MEASUREMENT_UNITS)}",
        )
    try:
        decimal_value = Decimal(str(value))
    except InvalidOperation as exc:
        raise AdapterError(
            "INVALID_REQUEST", "measurement.value must be a finite number"
        ) from exc
    if not decimal_value.is_finite() or decimal_value <= 0:
        raise AdapterError(
            "INVALID_REQUEST", "measurement.value must be finite and positive"
        )
    resolved = (decimal_value * _HUNDREDTH_MM_PER_UNIT[unit]).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )
    if resolved <= 0:
        raise AdapterError("INVALID_REQUEST", "measurement resolves to zero size")
    return int(resolved)


def validate_shape_geometry_params(params: Mapping[str, Any]) -> None:
    edge = params.get("edge")
    supplied_geometry = [field for field in GEOMETRY_FIELDS if field in params]
    supplied_measurements = [field for field in MEASUREMENT_FIELDS if field in params]
    if edge is not None:
        if not isinstance(edge, str) or edge not in SHAPE_EDGES:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.edge must be one of {', '.join(SHAPE_EDGES)}",
            )
        if supplied_geometry or supplied_measurements:
            raise AdapterError(
                "INVALID_REQUEST",
                "params.edge cannot be combined with numeric or measured geometry",
            )
        return
    if not supplied_geometry and not supplied_measurements:
        raise AdapterError(
            "INVALID_REQUEST",
            "shape.set_geometry requires edge or a geometry field",
        )
    for axis in ("width", "height"):
        if axis in params and f"{axis}_measurement" in params:
            raise AdapterError(
                "INVALID_REQUEST",
                f"params.{axis} and params.{axis}_measurement are mutually exclusive",
            )
    for field in supplied_geometry:
        value = params[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be an integer")
        if field in {"width", "height"} and value <= 0:
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be positive")
    for field in supplied_measurements:
        measurement = params[field]
        if not isinstance(measurement, Mapping):
            raise AdapterError("INVALID_REQUEST", f"params.{field} must be an object")
        measurement_to_hundredth_mm(measurement)


def validate_atomic_geometry_params(action: str, params: Mapping[str, Any]) -> None:
    fields = ATOMIC_GEOMETRY_FIELDS[action]
    unexpected = set(params).difference({"slide", "slide_number", "selector", *fields})
    if unexpected:
        raise AdapterError(
            "INVALID_REQUEST", f"{action} has unsupported params: {sorted(unexpected)}"
        )
    if not any(field in params for field in fields):
        raise AdapterError("INVALID_REQUEST", f"{action} requires one of {', '.join(fields)}")
    validate_shape_geometry_params(params)


def resolve_shape_geometry(params: Mapping[str, Any]) -> dict[str, int]:
    validate_shape_geometry_params(params)
    resolved = {
        field: int(params[field]) for field in GEOMETRY_FIELDS if field in params
    }
    for axis in ("width", "height"):
        field = f"{axis}_measurement"
        if field in params:
            resolved[axis] = measurement_to_hundredth_mm(params[field])
    return resolved


def validate_optional_shape_geometry_params(params: Mapping[str, Any]) -> None:
    """Validate geometry when supplied while preserving insert defaults when omitted."""
    if any(field in params for field in (*GEOMETRY_FIELDS, *MEASUREMENT_FIELDS)):
        validate_shape_geometry_params(params)


def resolve_optional_shape_geometry(params: Mapping[str, Any]) -> dict[str, int]:
    """Resolve only explicitly selected geometry fields."""
    validate_optional_shape_geometry_params(params)
    if not any(field in params for field in (*GEOMETRY_FIELDS, *MEASUREMENT_FIELDS)):
        return {}
    return resolve_shape_geometry(params)


def edge_aligned_position(
    *,
    edge: str,
    slide_width: int,
    slide_height: int,
    x: int,
    y: int,
    width: int,
    height: int,
) -> dict[str, int]:
    if edge not in SHAPE_EDGES:
        raise AdapterError("INVALID_REQUEST", f"unsupported slide edge: {edge}")
    if slide_width <= 0 or slide_height <= 0 or width <= 0 or height <= 0:
        raise AdapterError("CONFLICT", "slide and shape dimensions must be positive")
    if width > slide_width or height > slide_height:
        raise AdapterError(
            "CONFLICT",
            "shape does not fit within the slide bounds",
            {
                "slide_width": slide_width,
                "slide_height": slide_height,
                "shape_width": width,
                "shape_height": height,
            },
            422,
        )
    if edge == "top":
        return {"x": x, "y": 0}
    if edge == "bottom":
        return {"x": x, "y": slide_height - height}
    if edge == "left":
        return {"x": 0, "y": y}
    return {"x": slide_width - width, "y": y}
