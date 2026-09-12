"""Mesh parameter derivation — geometry + preset -> the numbers writers read.

``resolve_mesh_params`` is the single entry point that turns a case config and the
geometry bounds into ``cfg["mesh_params"]``: the background cell, the levels, the
refinement regions (near/far wake boxes plus the trailing-edge box) and the
cells-per-length the case snapshot records. Cell sizes themselves are resolved by
:mod:`rapidfoam.meshers.sizing`.

Only declared keys are written through to the result, so a key that no writer
reads can no longer ride along into ``case_config.json``.
"""

from __future__ import annotations

import math
from typing import Any

from rapidfoam.geometry import (
    compute_domain_box,
    face_assignments,
    face_role,
    flow_axis_index_sign,
    up_axis_index,
)
from rapidfoam.meshers.keys import (
    AUTO,
    BOOL,
    INT,
    LEVELS,
    METRES,
    NUMBER,
    REGIONS,
    SHELLS,
    SIZE_OR_ALIAS,
    VECTOR,
    KeySpec,
)
from rapidfoam.meshers.presets import preset_for
from rapidfoam.meshers.sizing import (
    resolve_base_cell_size,
    resolve_trailing_edge_level,
    trailing_edge_box,
)

#: Every ``mesh_params`` key an engine reads, declared once. Validation and the
#: web UI are generated from this table instead of repeating the keys per engine.
MESH_PARAMS_KEYS: dict[str, KeySpec] = {
    "base_cell_size": KeySpec(
        AUTO,
        doc="Background cell size: 'auto' (default) = cells_per_length cells along "
            "the longest bounding-box dimension, or a number in metres to pin the "
            "absolute behaviour for both engines.",
        default="auto",
    ),
    "cells_per_length": KeySpec(
        NUMBER,
        doc="Cells across the longest bounding-box dimension used by 'auto' sizing "
            "(20 fast / 30 standard / 37.5 fine). Raise it to resolve a front wing "
            "or a subassembly at the same preset.",
        default=30,
    ),
    "surface_level": KeySpec(
        LEVELS,
        doc="Octree levels on the model surface, [body, feature]. snappy reads them "
            "directly; cfMesh derives its body cell from the body level and refines "
            "feature edges one level finer on its own.",
    ),
    "edge_level": KeySpec(
        INT,
        doc="Refinement level of the feature-edge cell (the shared sizing turns it "
            "into metres for cfMesh, snappy uses the level).",
        default=6,
        allow_zero=True,
    ),
    "body_cell_size": KeySpec(
        METRES,
        doc="Absolute cell size on the model surface (metres); the levels are "
            "derived from it so both engines agree.",
    ),
    "edge_cell_size": KeySpec(
        METRES,
        doc="Absolute cell size on feature edges (metres).",
    ),
    "min_cell_size": KeySpec(
        SIZE_OR_ALIAS,
        doc="cfMesh's global automatic-refinement floor: curvature and proximity "
            "refinement stops here on every surface. 'body' (default) is the "
            "surface cell, 'edge' the feature-edge cell, 'base' the background "
            "cell; or give metres. One wing A/B changing only this key: "
            "0.0015625 m = 3.95 M cells / 311 s mesh versus 0.00625 m = "
            "1.82 M cells / 130 s mesh.",
        aliases=("base", "body", "surface", "edge", "feature"),
        engines=("cfmesh",),
    ),
    "distance_levels": KeySpec(
        SHELLS,
        doc="Distance shells as (metres, level) pairs; takes precedence "
            "over distance_shells.",
        engines=("snappy",),
    ),
    "distance_shells": KeySpec(
        SHELLS,
        doc="Distance shells as (multiple of the base cell, level) pairs, so the "
            "shells follow the model scale instead of being car-scale absolutes. "
            "cfMesh reaches the same idea with cfmesh.refinement_thickness.",
        engines=("snappy",),
    ),
    "refinement_regions": KeySpec(
        REGIONS,
        doc="Refinement boxes {name, min, max, level} replacing the default near/far "
            "wake boxes; the trailing-edge box is appended unless one with that name "
            "is given.",
    ),
    "trailing_edge_refine": KeySpec(
        BOOL,
        doc="Add one thin refinement box on the downstream-most face (on in every "
            "preset) so a trailing edge thinner than the body cell is resolved "
            "locally instead of by lowering the global floor.",
    ),
    "te_level": KeySpec(
        AUTO,
        doc="Cell size of the trailing-edge box: base_cell_size / 2**te_level. "
            "'auto' (default) is edge_level + 1, roughly two cells across a thin "
            "blunt edge.",
        default="auto",
        allow_zero=True,
    ),
    "te_height_cells": KeySpec(
        NUMBER,
        doc="Half-height of the trailing-edge box in body cells, centred on the "
            "body's mid-height.",
        default=2.0,
    ),
    "te_depth_cells": KeySpec(
        NUMBER,
        doc="Box extent upstream of the trailing-edge plane, in body cells, plus "
            "one cell downstream.",
        default=3.0,
    ),
    "wake_levels_below_surface": KeySpec(
        LEVELS,
        doc="How much coarser the wake boxes are than the model surface, as "
            "[near, far] levels below surface_level[0]. Relative, so the wake "
            "boxes stay a fixed fraction of the mesh when the surface level or "
            "the model size changes; state near_wake_level / far_wake_level for "
            "an absolute level.",
        default=[1, 3],
    ),
    "near_wake_level": KeySpec(INT, doc="Absolute refinement level of the near "
                                        "wake box; overrides "
                                        "wake_levels_below_surface[0].",
                               allow_zero=True),
    "far_wake_level": KeySpec(INT, doc="Absolute refinement level of the far "
                                       "wake box; overrides "
                                       "wake_levels_below_surface[1].",
                              allow_zero=True),
    "wake_level": KeySpec(INT, doc="Legacy: sets both wake box levels.",
                          allow_zero=True),
    "nCellsBetweenLevels": KeySpec(INT, doc="Buffer cells between refinement levels.",
                                   default=2, engines=("snappy",)),
    "maxGlobalCells": KeySpec(INT, doc="Global cell cap (cfMesh has no equivalent).",
                              default=18_000_000, engines=("snappy",)),
    "maxLocalCells": KeySpec(INT, doc="Per-rank cell cap.", default=2_000_000,
                             engines=("snappy",)),
    "minRefinementCells": KeySpec(INT, doc="Minimum cells a refinement region must "
                                           "add.", default=10, allow_zero=True,
                                  engines=("snappy",)),
    "resolveFeatureAngle": KeySpec(NUMBER, doc="Feature angle handed to snappy's "
                                               "refinement.", default=35,
                                   engines=("snappy",)),
    "allowFreeStandingZoneFaces": KeySpec(BOOL, doc="Keep zone faces that are not "
                                                    "connected to a cell zone.",
                                          default=True, engines=("snappy",)),
    "locationInMesh": KeySpec(VECTOR, doc="Point inside the fluid region.",
                              engines=("snappy",)),
    "location_in_mesh": KeySpec(VECTOR, doc="Point inside the fluid region "
                                            "(snake_case spelling).",
                                engines=("snappy",)),
    "maxLoadUnbalance": KeySpec(NUMBER, doc="Load-balance tolerance.",
                                engines=("snappy",)),
}

def keys_for(engine: str) -> dict[str, KeySpec]:
    """The ``mesh_params`` keys one engine reads.

    A view of :data:`MESH_PARAMS_KEYS` filtered by each key's declared ``engines``,
    so the per-engine key lists (the CLI, ``/api/config`` and the validation
    warning below) come from the table instead of being restated per engine.
    """
    return {key: spec for key, spec in MESH_PARAMS_KEYS.items() if spec.reads(engine)}


def unread_keys(mesh: dict[str, Any], engine: str) -> list[str]:
    """Sorted keys a case sets that the selected engine never reads."""
    return sorted(
        key for key in mesh
        if key in MESH_PARAMS_KEYS and not MESH_PARAMS_KEYS[key].reads(engine)
    )


#: Keys that only ever appear in a *resolved* ``mesh_params`` snapshot (written by
#: :func:`resolve_mesh_params` into ``case_config.json``), never as case input, so
#: re-validating a resolved config does not flag them as unknown.
RESOLVED_ONLY_KEYS: tuple[str, ...] = (
    "base_cell_size_mode",
)

#: ``mesh_params`` keys a preset or case may set that writers read verbatim.
MESH_PARAMS_PASSTHROUGH: tuple[str, ...] = (
    "body_cell_size",
    "edge_cell_size",
    "min_cell_size",
    "near_wake_level",
    "far_wake_level",
    "wake_level",
    "location_in_mesh",
    "locationInMesh",
    "maxLoadUnbalance",
    "trailing_edge_refine",
    "te_level",
    "te_height_cells",
    "te_depth_cells",
)


#: Fallback wake gaps for a bare config: the presets state their own.
DEFAULT_WAKE_GAPS: tuple[int, int] = (1, 3)

# Wake-box geometry as fractions of the *model*, not metres. The boxes used to be
# floored at absolute sizes (2.0 / 4.0 m long, 0.10 / 0.15 / 0.20 / 0.25 m thick),
# which the presets' 3.0 m calibration silently turned into a small-model problem:
# a 1 m body asked for a 2.4 m wake box at level 3 — 4.5 M cells, 55 % of a
# standard mesh, and 27x the same box on the car the floors were written for
# (volume ~ L**3 while the cell size ~ L). The floors are now the same fractions
# of the model length: a normal car is unchanged (the fractions dominate there),
# a wing or a subassembly gets a box in proportion to itself, and the wake stays a
# bounded fraction of the mesh at every `cells_per_length`.
WAKE_PAD_LATERAL = 0.15          # of the model width, each side
WAKE_PAD_TOP = 0.25              # of the model height
WAKE_PAD_LATERAL_MIN = 0.03      # of the model length (floor of the width pad)
WAKE_PAD_TOP_MIN = 0.05          # of the model length (floor of the height pad)
WAKE_NEAR_LENGTH = 1.2           # of the model length in the flow direction
WAKE_FAR_LENGTH = 3.5
WAKE_NEAR_LENGTH_MIN = 0.4       # of the model length (floor of the near length)
WAKE_FAR_LENGTH_MIN = 1.2
WAKE_FAR_PAD_LATERAL = 0.30
WAKE_FAR_PAD_TOP = 0.40
WAKE_FAR_PAD_LATERAL_MIN = 0.06
WAKE_FAR_PAD_TOP_MIN = 0.10


def resolve_wake_gaps(value: Any) -> tuple[int, int]:
    """``(near, far)`` levels below the surface the wake boxes sit at.

    Accepts the ``[near, far]`` list a preset or case states; a missing or
    malformed value (which ``validate`` reports separately) falls back to
    :data:`DEFAULT_WAKE_GAPS`.
    """
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(_is_nonnegative_int(v) for v in value) and value[0] <= value[1]):
        return int(value[0]), int(value[1])
    return DEFAULT_WAKE_GAPS


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def resolve_mesh_params(cfg: dict[str, Any], combined_bounds: Any) -> dict[str, Any]:
    """Derive every mesh parameter from the geometry bounds.

    Cell sizes are geometry-relative unless ``mesh_params.base_cell_size`` pins
    them in metres, and the distance shells scale with the base cell so one preset
    holds across model scales. The wake boxes are model fractions too, and their
    levels sit ``wake_levels_below_surface`` under ``surface_level[0]``, so the
    wake keeps its share of the mesh when the surface level or the model size
    changes instead of growing cubically. ``trailing_edge_refine`` (on in every
    preset) adds one thin region on the downstream-most face, because cfMesh's
    automatic refinement stops at ``minCellSize`` and a trailing edge thinner than
    the body cell can only be resolved locally.
    """
    smin, smax = combined_bounds
    extents = [smax[i] - smin[i] for i in range(3)]
    max_extent = max(extents)
    if max_extent <= 0:
        raise ValueError("STL has zero extent — check your geometry")

    preset = preset_for(cfg.get("fidelity", "standard"))
    user_mesh = cfg.get("mesh_params", {})

    base_cell, base_cell_mode = resolve_base_cell_size(user_mesh, preset, max_extent)
    base_cell = round(base_cell, 4)

    surface_level = user_mesh.get("surface_level", preset["surface_level"])
    edge_level = user_mesh.get("edge_level", preset["edge_level"])

    # An absolute body-cell intent re-derives the levels, so a config that states
    # "body cells are 6.25 mm" drives snappy and cfMesh identically.
    body_cell_override = user_mesh.get("body_cell_size")
    if body_cell_override:
        level = max(0, round(math.log2(base_cell / float(body_cell_override))))
        surface_level = user_mesh.get("surface_level", [level, level + 1])
        edge_level = user_mesh.get("edge_level", level + 2)

    # Distance-based refinement shells: explicit metres win, then explicit
    # base-cell multiples, otherwise the preset's shells (which follow the scale).
    if "distance_levels" in user_mesh:
        distance_levels = user_mesh["distance_levels"]
        if distance_levels and isinstance(distance_levels[0], list):
            distance_levels = [tuple(x) for x in distance_levels]
    elif "distance_shells" in user_mesh:
        distance_levels = [
            (round(float(multiple) * base_cell, 6), int(level))
            for multiple, level in user_mesh["distance_shells"]
        ]
    else:
        distance_levels = [
            (round(float(multiple) * base_cell, 6), int(level))
            for multiple, level in preset.get("distance_shells", [])
        ]

    resolve_feature_angle = user_mesh.get(
        "resolveFeatureAngle", preset.get("resolveFeatureAngle", 35)
    )
    near_gap, far_gap = resolve_wake_gaps(
        user_mesh.get("wake_levels_below_surface", preset.get("wake_levels_below_surface"))
    )
    body_level = int(surface_level[0])
    near_wake_level = user_mesh.get("near_wake_level", max(0, body_level - near_gap))
    far_wake_level = user_mesh.get("far_wake_level", max(0, body_level - far_gap))
    if "wake_level" in user_mesh:  # legacy single wake level
        near_wake_level = user_mesh["wake_level"]

    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i != flow_idx and i != up_idx)

    domain_faces = {d: face_role(cfg, name) for d, name in face_assignments(cfg).items()}
    is_ground = "ground" in domain_faces.get(f"-{'xyz'[up_idx]}", "").lower()
    is_symmetry = "symmetry" in domain_faces.get(f"-{'xyz'[lateral_idx]}", "").lower()

    sym_coord = cfg.get("symmetry_plane", cfg.get("centerline"))
    if sym_coord is not None:
        sym_x = float(sym_coord)
    elif isinstance(cfg.get("domain_box"), dict) and "min" in cfg["domain_box"]:
        sym_x = cfg["domain_box"]["min"][lateral_idx]
    elif abs(smin[lateral_idx]) < 0.05:
        sym_x = 0.0
    else:
        sym_x = smin[lateral_idx]

    ground_z: float | None = None
    if is_ground:
        if cfg.get("ground_plane") is not None:
            ground_z = float(cfg["ground_plane"]) - 0.01
        elif cfg.get("ground_clearance") is not None:
            ground_z = smin[up_idx] - float(cfg["ground_clearance"]) - 0.01
        elif isinstance(cfg.get("domain_box"), dict) and "min" in cfg["domain_box"]:
            ground_z = cfg["domain_box"]["min"][up_idx] - 0.01
        else:
            ground_z = smin[up_idx] - 0.01

    # --- 1. Near wake box: high resolution behind the vehicle ---------------
    # Fractions of the model (see the WAKE_* constants), not absolute metres.
    near_pad_lat = max(extents[lateral_idx] * WAKE_PAD_LATERAL, max_extent * WAKE_PAD_LATERAL_MIN)
    near_pad_top = max(extents[up_idx] * WAKE_PAD_TOP, max_extent * WAKE_PAD_TOP_MIN)
    near_length = max(extents[flow_idx] * WAKE_NEAR_LENGTH, max_extent * WAKE_NEAR_LENGTH_MIN)

    near_min = list(smin)
    near_max = list(smax)
    near_min[up_idx] = ground_z if is_ground else smin[up_idx] - near_pad_top
    near_max[up_idx] = smax[up_idx] + near_pad_top
    near_min[lateral_idx] = smin[lateral_idx] - near_pad_lat
    near_max[lateral_idx] = smax[lateral_idx] + near_pad_lat
    if is_symmetry:
        near_min[lateral_idx] = sym_x
    if flow_sign > 0:
        near_min[flow_idx] = smin[flow_idx] + extents[flow_idx] * 0.6
        near_max[flow_idx] = smax[flow_idx] + near_length
    else:
        near_min[flow_idx] = smin[flow_idx] - near_length
        near_max[flow_idx] = smin[flow_idx] + extents[flow_idx] * 0.4

    # --- 2. Far wake box: cheap downstream transport to the outlet ----------
    far_pad_lat = max(extents[lateral_idx] * WAKE_FAR_PAD_LATERAL,
                      max_extent * WAKE_FAR_PAD_LATERAL_MIN)
    far_pad_top = max(extents[up_idx] * WAKE_FAR_PAD_TOP, max_extent * WAKE_FAR_PAD_TOP_MIN)
    far_length = max(extents[flow_idx] * WAKE_FAR_LENGTH, max_extent * WAKE_FAR_LENGTH_MIN)

    far_min = list(smin)
    far_max = list(smax)
    far_min[up_idx] = ground_z if is_ground else smin[up_idx] - far_pad_top
    far_max[up_idx] = smax[up_idx] + far_pad_top
    far_min[lateral_idx] = smin[lateral_idx] - far_pad_lat
    far_max[lateral_idx] = smax[lateral_idx] + far_pad_lat
    if is_symmetry:
        far_min[lateral_idx] = sym_x
    if flow_sign > 0:
        far_min[flow_idx] = smax[flow_idx]
        far_max[flow_idx] = smax[flow_idx] + far_length
    else:
        far_min[flow_idx] = smin[flow_idx] - far_length
        far_max[flow_idx] = smin[flow_idx]

    domain_box = cfg.get("domain_box")
    if not isinstance(domain_box, dict):
        domain_box = compute_domain_box(cfg, combined_bounds)
    if domain_faces.get(f"+{'xyz'[up_idx]}") == "ground":
        for upper in (near_max, far_max):
            upper[up_idx] = domain_box["max"][up_idx] + 0.01
    if domain_faces.get(f"+{'xyz'[lateral_idx]}") == "symmetry":
        for upper in (near_max, far_max):
            upper[lateral_idx] = domain_box["max"][lateral_idx]

    default_regions = [
        {"name": "nearWakeBox", "min": [round(v, 4) for v in near_min],
         "max": [round(v, 4) for v in near_max], "level": near_wake_level},
        {"name": "farWakeBox", "min": [round(v, 4) for v in far_min],
         "max": [round(v, 4) for v in far_max], "level": far_wake_level},
    ]
    refinement_regions = list(user_mesh.get("refinement_regions", default_regions))

    if user_mesh.get("trailing_edge_refine", preset.get("trailing_edge_refine", False)):
        body_cell = float(base_cell) / (2 ** int(surface_level[0]))
        te_box = trailing_edge_box(
            cfg,
            combined_bounds,
            level=resolve_trailing_edge_level(user_mesh.get("te_level"), int(edge_level)),
            body_cell=body_cell,
            height_cells=user_mesh.get("te_height_cells", 2.0),
            depth_cells=user_mesh.get("te_depth_cells", 3.0),
        )
        if te_box is not None and not any(
            str(r.get("name")) == te_box["name"] for r in refinement_regions
        ):
            refinement_regions.append(te_box)

    result: dict[str, Any] = {
        "base_cell_size": base_cell,
        "base_cell_size_mode": base_cell_mode,
        "cells_per_length": round(max_extent / base_cell, 3),
        "surface_level": surface_level,
        "edge_level": edge_level,
        "distance_levels": distance_levels,
        "refinement_regions": refinement_regions,
        "wake_levels_below_surface": [near_gap, far_gap],
        "near_wake_level": near_wake_level,
        "far_wake_level": far_wake_level,
        "nCellsBetweenLevels": user_mesh.get(
            "nCellsBetweenLevels", preset.get("nCellsBetweenLevels", 2)
        ),
        "maxGlobalCells": user_mesh.get(
            "maxGlobalCells", preset.get("maxGlobalCells", 18_000_000)
        ),
        "maxLocalCells": user_mesh.get("maxLocalCells", 2_000_000),
        "minRefinementCells": user_mesh.get("minRefinementCells", 10),
        "resolveFeatureAngle": resolve_feature_angle,
        "allowFreeStandingZoneFaces": user_mesh.get("allowFreeStandingZoneFaces", True),
    }
    for key in MESH_PARAMS_PASSTHROUGH:
        if key in user_mesh:
            result[key] = user_mesh[key]
    return result


__all__ = [
    "DEFAULT_WAKE_GAPS",
    "MESH_PARAMS_KEYS",
    "MESH_PARAMS_PASSTHROUGH",
    "RESOLVED_ONLY_KEYS",
    "compute_mesh_params",
    "keys_for",
    "resolve_mesh_params",
    "resolve_wake_gaps",
    "unread_keys",
]

# Historical name (the CLI and older tests imported this spelling).
compute_mesh_params = resolve_mesh_params
