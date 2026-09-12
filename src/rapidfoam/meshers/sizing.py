"""Cell sizing — the numbers both meshers derive from the model.

Every cell size RapidFOAM writes is relative to the *model*: ``base_cell_size``
is ``max_extent / cells_per_length`` by default, so one fidelity preset means the
same resolution per model length on a full car, a front wing or a subassembly,
and the trailing-edge box and distance shells follow the same scale. An explicit
``mesh_params.base_cell_size`` in metres pins the absolute behaviour instead.

The meshers read :class:`Sizing` and translate it into their own units (snappy
levels, cfMesh metres); nothing engine-specific lives here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

DEFAULT_CELLS_PER_LENGTH = 30


@dataclass(frozen=True)
class Sizing:
    """Resolved cell sizes in metres plus the levels they came from."""

    base_cell_size: float       # background cell of the wind tunnel box
    body_cell_size: float       # cells on the model surface
    edge_cell_size: float       # cells on extracted feature edges
    min_cell_size: float        # cfMesh's global refinement floor
    body_level: int
    feature_level: int
    edge_level: int
    body_from_metres: bool      # body came from body_cell_size, not the levels

    @property
    def mode(self) -> str:
        """Informational label: which intent stated the body cell."""
        return "absolute" if self.body_from_metres else "relative_levels"


def resolve_base_cell_size(
    mesh: dict[str, Any],
    preset: dict[str, Any],
    max_extent: float,
) -> tuple[float, str]:
    """Background cell size in metres, and whether it was explicit.

    An explicit ``mesh_params.base_cell_size`` in metres wins. ``"auto"`` (the
    preset default) is ``max_extent / cells_per_length``, where ``max_extent`` is
    the longest bounding-box dimension; ``mesh_params.cells_per_length``
    overrides the preset's value for one case.
    """
    value = mesh.get("base_cell_size")
    if value is not None and str(value).strip().lower() != "auto":
        try:
            metres = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "mesh_params.base_cell_size must be a number in metres or 'auto' "
                f"(got {value!r})"
            ) from exc
        if not math.isfinite(metres) or metres <= 0:
            raise ValueError(f"mesh_params.base_cell_size must be > 0 metres (got {value!r})")
        return metres, "absolute"

    per_length = mesh.get(
        "cells_per_length",
        preset.get("cells_per_length", DEFAULT_CELLS_PER_LENGTH),
    )
    try:
        per_length = float(per_length)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"mesh_params.cells_per_length must be a number > 0 (got {per_length!r})"
        ) from exc
    if not math.isfinite(per_length) or per_length <= 0:
        raise ValueError(f"mesh_params.cells_per_length must be > 0 (got {per_length!r})")
    if not math.isfinite(max_extent) or max_extent <= 0:
        raise ValueError("STL has zero extent — check your geometry")
    return float(max_extent) / per_length, "auto"


def resolve_min_cell_size(value: Any, *, base: float, body: float, edge: float) -> float:
    """cfMesh's ``minCellSize``: the floor every automatic refinement stops at.

    It is not snappy's ``edge_level``. cfMesh refines by curvature and proximity
    on *every* surface down to this floor, so flooring it at the edge cell
    resolved the whole car two levels finer than snappy intended (4.4 M cells
    where snappy needed 449 k). It therefore defaults to the body cell; cfMesh
    still refines feature-edge cells to ``body / 2`` on its own.
    """
    if value is None:
        return float(body)
    if isinstance(value, str):
        key = MIN_CELL_SIZE_ALIASES.get(value.strip().lower())
        if key is None:
            raise ValueError(
                "mesh_params.min_cell_size must be a number in metres or one of "
                f"{', '.join(sorted(MIN_CELL_SIZE_ALIASES))} (got {value!r})"
            )
        return float({"base": base, "body": body, "edge": edge}[key])
    try:
        resolved = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"mesh_params.min_cell_size must be a number in metres or an alias (got {value!r})"
        ) from exc
    if resolved <= 0:
        raise ValueError("mesh_params.min_cell_size must be > 0 metres")
    return resolved


MIN_CELL_SIZE_ALIASES: dict[str, str] = {
    "base": "base",
    "body": "body",
    "surface": "body",
    "edge": "edge",
    "feature": "edge",
}


def resolve_sizing(mesh: dict[str, Any]) -> Sizing:
    """Resolve ``mesh_params`` into concrete cell sizes in metres.

    ``base_cell_size`` must already be a number: ``"auto"`` is resolved from the
    geometry by :func:`rapidfoam.meshers.refinement.resolve_mesh_params` first.
    """
    base = mesh.get("base_cell_size", 0.10)
    if isinstance(base, str):
        raise ValueError(
            "mesh_params.base_cell_size 'auto' must be resolved from the geometry first "
            "(resolve_mesh_params(cfg, combined_bounds)); resolve_sizing needs metres"
        )
    base = float(base)
    levels = mesh.get("surface_level", [4, 5])
    body_level = int(levels[0])
    feature_level = int(levels[1])
    edge_level = int(mesh.get("edge_level", feature_level + 1))

    body_override = mesh.get("body_cell_size")
    body_from_metres = body_override is not None
    body = float(body_override) if body_from_metres else base / (2 ** body_level)

    edge_override = mesh.get("edge_cell_size")
    edge = base / (2 ** edge_level) if edge_override is None else float(edge_override)

    return Sizing(
        base_cell_size=base,
        body_cell_size=float(body),
        edge_cell_size=float(edge),
        min_cell_size=resolve_min_cell_size(
            mesh.get("min_cell_size"), base=base, body=float(body), edge=float(edge)
        ),
        body_level=body_level,
        feature_level=feature_level,
        edge_level=edge_level,
        body_from_metres=body_from_metres,
    )


def resolve_first_layer_height(layers: dict[str, Any], body_cell: float) -> float:
    """First boundary-layer cell height in metres.

    ``first_layer_mode: "relative"`` (default) is ``first_layer_thickness`` x the
    body cell, which keeps both meshers in the same wall-function range;
    ``"absolute"`` reads ``first_layer_height`` in metres. cfMesh treats the value
    as an upper bound and still compresses the stack to fit the local cell.
    """
    mode = str(layers.get("first_layer_mode", "relative")).lower()
    if mode == "absolute" and layers.get("first_layer_height"):
        return float(layers["first_layer_height"])
    return float(body_cell) * float(layers.get("first_layer_thickness", 0.3))


def resolve_first_layer_fraction(layers: dict[str, Any], body_cell: float) -> float:
    """snappy's relative ``firstLayerThickness`` matching the resolved height.

    snappy clamps the real layer stack, so treat the result as nominal.
    """
    if body_cell <= 0:
        return float(layers.get("first_layer_thickness", 0.3))
    return min(0.6, max(0.05, resolve_first_layer_height(layers, body_cell) / float(body_cell)))


def resolve_trailing_edge_level(value: Any, edge_level: int) -> int:
    """Refinement level for the trailing-edge box.

    ``"auto"`` (default) is ``edge_level + 1``: one level finer than snappy's
    feature-edge cell, which puts roughly two cells across a thin blunt trailing
    edge.
    """
    text = "" if value is None else str(value).strip().lower()
    if text in ("auto", ""):
        return int(edge_level) + 1
    try:
        level = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"mesh_params.te_level must be a nonnegative integer or 'auto' (got {value!r})"
        ) from exc
    if level < 0:
        raise ValueError(f"mesh_params.te_level must be a nonnegative integer (got {level})")
    return level


def trailing_edge_box(
    cfg: dict[str, Any],
    combined_bounds: Any,
    *,
    level: int,
    body_cell: float,
    height_cells: float = 2.0,
    depth_cells: float = 3.0,
) -> dict[str, Any] | None:
    """Thin refinement box hugging the downstream-most face of the geometry.

    A wing trailing edge is often thinner than the body cell (the bundled test
    body ends in a 1.4 mm strip against a 6.25 mm cell), and cfMesh's automatic
    refinement stops at ``minCellSize``, so the extruder would leave slivers.
    Refining a *volume* is what costs cells, so the box only spans the wedge that
    is still thinner than a couple of body cells: ``depth_cells`` upstream of the
    trailing-edge plane, one cell downstream, and a ``height_cells`` band either
    side of the body's mid-height.

    Returns ``None`` for a degenerate box so callers can skip it silently.
    """
    from rapidfoam.geometry import flow_axis_index_sign, up_axis_index

    smin = [float(v) for v in combined_bounds[0]]
    smax = [float(v) for v in combined_bounds[1]]
    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i not in (flow_idx, up_idx))

    te_plane = smax[flow_idx] if flow_sign > 0 else smin[flow_idx]

    lo = list(smin)
    hi = list(smax)
    for axis in (up_idx, lateral_idx):
        lo[axis] = smin[axis] - body_cell
        hi[axis] = smax[axis] + body_cell

    mid = 0.5 * (smin[up_idx] + smax[up_idx])
    band = float(height_cells) * body_cell
    lo[up_idx] = max(lo[up_idx], mid - band)
    hi[up_idx] = min(hi[up_idx], mid + band)

    upstream = te_plane - flow_sign * float(depth_cells) * body_cell
    downstream = te_plane + flow_sign * body_cell
    lo[flow_idx], hi[flow_idx] = min(upstream, downstream), max(upstream, downstream)

    domain_box = cfg.get("domain_box")
    if isinstance(domain_box, dict) and "min" in domain_box and "max" in domain_box:
        for i in range(3):
            lo[i] = max(lo[i], float(domain_box["min"][i]))
            hi[i] = min(hi[i], float(domain_box["max"][i]))

    if any(hi[i] - lo[i] <= body_cell * 1e-6 for i in range(3)):
        return None

    return {
        "name": "trailingEdgeBox",
        "min": [round(v, 4) for v in lo],
        "max": [round(v, 4) for v in hi],
        "level": int(level),
    }


__all__ = [
    "DEFAULT_CELLS_PER_LENGTH",
    "MIN_CELL_SIZE_ALIASES",
    "Sizing",
    "resolve_base_cell_size",
    "resolve_first_layer_fraction",
    "resolve_first_layer_height",
    "resolve_min_cell_size",
    "resolve_sizing",
    "resolve_trailing_edge_level",
    "trailing_edge_box",
]
