"""Geometry utilities — axis math, domain sizing, mesh parameter derivation.

All mesh/domain parameters are derived from STL bounding box.
No geometry-specific tuning required.
"""

from __future__ import annotations

import math
from typing import Any

from cfd_gen.stl_utils import BBox

# ============================================================
# AXIS UTILITIES
# ============================================================

AXIS_MAP: dict[str, tuple[int, int, int]] = {
    "+x": (1, 0, 0), "x": (1, 0, 0), "-x": (-1, 0, 0),
    "+y": (0, 1, 0), "y": (0, 1, 0), "-y": (0, -1, 0),
    "+z": (0, 0, 1), "z": (0, 0, 1), "-z": (0, 0, -1),
}


def parse_axis(s: str) -> tuple[int, int, int]:
    """Parse axis string to unit vector tuple."""
    s = s.strip().lower()
    if s not in AXIS_MAP:
        raise ValueError(f"Invalid axis '{s}'. Use: +x, -x, +y, -y, +z, -z")
    return AXIS_MAP[s]


def axis_index_sign(axis_str: str) -> tuple[int, int]:
    """Return (column_index, sign_multiplier) for axis string."""
    vec = parse_axis(axis_str)
    for i, v in enumerate(vec):
        if v != 0:
            return i, int(v)
    return 0, 1


def up_axis_index(cfg: dict[str, Any]) -> int:
    """Determine the 'up' axis index from downforce direction.

    Convention: downforce_axis='-y' means downforce points -y, so up is +y, index=1.
    """
    df_vec = parse_axis(cfg["outputs"]["downforce_axis"])
    for i, v in enumerate(df_vec):
        if v != 0:
            return i
    return 1


def flow_axis_index_sign(cfg: dict[str, Any]) -> tuple[int, int]:
    """Return (index, sign) of the flow direction."""
    vec = parse_axis(cfg["flow"]["direction"])
    for i, v in enumerate(vec):
        if v != 0:
            return i, int(v)
    return 2, -1


def vec_str(v: tuple[float, ...]) -> str:
    """Format 3-tuple as OpenFOAM vector: (x y z)."""
    return f"({v[0]:.6g} {v[1]:.6g} {v[2]:.6g})"


def velocity_vector(cfg: dict[str, Any]) -> tuple[float, float, float]:
    """Compute velocity vector from flow direction and speed."""
    d = parse_axis(cfg["flow"]["direction"])
    U = cfg["flow"]["velocity"]
    return (d[0] * U, d[1] * U, d[2] * U)


def turbulence_values(cfg: dict[str, Any]) -> tuple[float, float, float]:
    """Compute k, omega, nut from config.

    Returns:
        (k, omega, nut)
    """
    U = cfg["flow"]["velocity"]
    I = cfg["turbulence"]["intensity"]
    nu = cfg["fluid"]["nu"]
    nut_ratio = cfg["turbulence"]["nut_ratio"]
    k = 1.5 * (U * I) ** 2
    omega = k / (nut_ratio * nu)
    nut = nut_ratio * nu
    return k, omega, nut


# ============================================================
# DOMAIN SIZING — Geometry-derived, generous padding
# ============================================================

def compute_domain_box(cfg: dict[str, Any], combined_bounds: BBox) -> dict[str, list[float]]:
    """Compute domain bounding box from STL bounds.

    Uses generous padding to avoid blockage effects:
      - Upstream: 5× geometry length
      - Downstream: 10× geometry length
      - Lateral/top: 5× geometry height
      - Ground at 0 (for ground vehicles)
      - Symmetry at lateral=0

    Returns:
        {"min": [x,y,z], "max": [x,y,z]}
    """
    smin, smax = combined_bounds
    extents = [smax[i] - smin[i] for i in range(3)]

    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i != flow_idx and i != up_idx)

    # Padding factors (reduced for fast fidelity)
    fidelity = cfg.get("fidelity", "fast")
    if fidelity == "fast":
        default_up, default_down, default_lat, default_top = 3, 6, 3, 3
    elif fidelity == "fine":
        default_up, default_down, default_lat, default_top = 5, 10, 5, 5
    else:
        default_up, default_down, default_lat, default_top = 4, 8, 4, 4

    upstream = cfg.get("domain", {}).get("upstream_factor", default_up)
    downstream = cfg.get("domain", {}).get("downstream_factor", default_down)
    lateral = cfg.get("domain", {}).get("lateral_factor", default_lat)
    top = cfg.get("domain", {}).get("top_factor", default_top)

    dmin = [0.0] * 3
    dmax = [0.0] * 3

    # Flow axis
    flow_extent = max(extents[flow_idx], 0.1)
    if flow_sign > 0:
        dmin[flow_idx] = smin[flow_idx] - flow_extent * upstream
        dmax[flow_idx] = smax[flow_idx] + flow_extent * downstream
    else:
        dmin[flow_idx] = smin[flow_idx] - flow_extent * downstream
        dmax[flow_idx] = smax[flow_idx] + flow_extent * upstream

    # Up axis (ground at 0, top padded)
    up_extent = max(extents[up_idx], 0.1)
    dmin[up_idx] = 0.0  # ground plane
    dmax[up_idx] = smax[up_idx] + up_extent * top

    # Lateral axis (symmetry at 0, far side padded)
    lat_extent = max(extents[lateral_idx], 0.1)
    dmin[lateral_idx] = 0.0  # symmetry plane
    dmax[lateral_idx] = smax[lateral_idx] + lat_extent * lateral

    return {
        "min": [round(v, 3) for v in dmin],
        "max": [round(v, 3) for v in dmax],
    }


# ============================================================
# FIDELITY PRESETS
# ============================================================

FIDELITY_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        # Quick turnaround for iterative design (~5-10 min on 10 cores)
        # Coarse background, moderate surface, minimal layers
        "base_cell_size": 0.15,        # m — coarse background
        "surface_level": [3, 4],       # 0.15/2^4 = 9.4mm surface cells
        "edge_level": 5,               # 0.15/2^5 = 4.7mm at edges
        "n_layers": 3,
        "expansion_ratio": 1.3,
        "first_layer_thickness": 0.4,
        "end_time": 800,
        "write_interval": 400,
        "maxGlobalCells": 8_000_000,
        "nCellsBetweenLevels": 2,
        "resolveFeatureAngle": 25,
        "nSolveIter": 100,             # snap iterations
        "nFeatureSnapIter": 10,
        "nLayerIter": 30,
        "nRelaxIter_layers": 5,
        "slurm_time": "04:00:00",
        # Distance-based refinement shells (distance, level)
        # Shells conform to geometry shape — replaces nearBody box
        "distance_levels": [
            (0.015, 4),   # 15mm → level 4
            (0.060, 3),   # 60mm → level 3
            (0.200, 2),   # 200mm → level 2
        ],
    },
    "standard": {
        # Balanced — good accuracy, reasonable time (~30-60 min)
        "base_cell_size": 0.10,
        "surface_level": [4, 5],       # 0.10/2^5 = 3.1mm surface cells
        "edge_level": 6,               # 0.10/2^6 = 1.6mm at edges
        "n_layers": 5,
        "expansion_ratio": 1.2,
        "first_layer_thickness": 0.3,
        "end_time": 1500,
        "write_interval": 500,
        "maxGlobalCells": 20_000_000,
        "nCellsBetweenLevels": 3,
        "resolveFeatureAngle": 20,
        "nSolveIter": 200,
        "nFeatureSnapIter": 15,
        "nLayerIter": 50,
        "nRelaxIter_layers": 10,
        "slurm_time": "08:00:00",
        # Distance-based refinement shells
        "distance_levels": [
            (0.010, 5),   # 10mm → level 5
            (0.040, 4),   # 40mm → level 4
            (0.150, 3),   # 150mm → level 3
        ],
    },
    "fine": {
        # Final report quality — accurate numbers (~2-4 hours)
        "base_cell_size": 0.06,
        "surface_level": [5, 6],       # 0.06/2^6 = 0.9mm surface cells
        "edge_level": 7,               # 0.06/2^7 = 0.5mm at edges
        "n_layers": 8,
        "expansion_ratio": 1.15,
        "first_layer_thickness": 0.2,
        "end_time": 3000,
        "write_interval": 500,
        "maxGlobalCells": 40_000_000,
        "nCellsBetweenLevels": 3,
        "resolveFeatureAngle": 15,
        "nSolveIter": 300,
        "nFeatureSnapIter": 20,
        "nLayerIter": 50,
        "nRelaxIter_layers": 10,
        "slurm_time": "12:00:00",
        # Distance-based refinement shells
        "distance_levels": [
            (0.005, 6),   # 5mm → level 6
            (0.020, 5),   # 20mm → level 5
            (0.080, 4),   # 80mm → level 4
        ],
    },
}


# ============================================================
# MESH PARAMETER DERIVATION — Universal, geometry-adaptive
# ============================================================

def compute_mesh_params(cfg: dict[str, Any], combined_bounds: BBox) -> dict[str, Any]:
    """Derive all mesh parameters from geometry bounds.

    Philosophy: relative sizing for everything. No absolute cell sizes.
    The mesh adapts to whatever geometry you throw at it.

    Refinement strategy:
        - Distance-based shells around the STL surface (replaces nearBody box).
          Cells are refined based on proximity to the geometry, giving smooth
          transitions that conform to the actual shape.
        - Box-based wake region downstream (distance mode can't reach the far wake).

    Fidelity levels:
        "fast"     — iterative design, quick turnaround
        "standard" — balanced accuracy/speed (default)
        "fine"     — final report quality

    Returns dict with:
        base_cell_size, surface_level, edge_level, distance_levels,
        refinement_regions (wake only), n_layers, etc.
    """
    smin, smax = combined_bounds
    extents = [smax[i] - smin[i] for i in range(3)]
    max_extent = max(extents)

    if max_extent <= 0:
        raise ValueError("STL has zero extent — check your geometry")

    # Get fidelity preset
    fidelity = cfg.get("fidelity", "fast")
    preset = FIDELITY_PRESETS.get(fidelity, FIDELITY_PRESETS["fast"])

    user_mesh = cfg.get("mesh_params", {})

    # Base cell: respect user override or use fidelity preset
    base_cell = user_mesh.get("base_cell_size", preset["base_cell_size"])

    # Surface and edge levels: respect user override or use fidelity preset
    surface_level = user_mesh.get("surface_level", preset["surface_level"])
    edge_level = user_mesh.get("edge_level", preset["edge_level"])

    # Distance-based refinement shells
    distance_levels = user_mesh.get("distance_levels", preset["distance_levels"])
    if distance_levels and isinstance(distance_levels[0], list):
        distance_levels = [tuple(x) for x in distance_levels]

    resolve_feature_angle = user_mesh.get("resolveFeatureAngle", preset.get("resolveFeatureAngle", 20))

    # Wake box (kept as box-based — distance mode can't reach far wake)
    wake_level = max(1, surface_level[1] - 3)

    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)

    pad = [max(0.05, d * 0.2) for d in extents]

    wake_min = [smin[i] - pad[i] for i in range(3)]
    wake_max = [smax[i] + pad[i] for i in range(3)]
    # Extend wake box down to ground level (with 10mm margin to guarantee boundary overlap)
    if "domain_box" in cfg and "min" in cfg["domain_box"] and len(cfg["domain_box"]["min"]) > up_idx:
        wake_min[up_idx] = cfg["domain_box"]["min"][up_idx] - 0.01
    else:
        wake_min[up_idx] = min(0.0, smin[up_idx]) - 0.01
    wake_length = max(2.0, extents[flow_idx] * 4.0)

    if flow_sign > 0:
        wake_min[flow_idx] = smax[flow_idx]
        wake_max[flow_idx] = smax[flow_idx] + wake_length
    else:
        wake_max[flow_idx] = smin[flow_idx]
        wake_min[flow_idx] = smin[flow_idx] - wake_length

    refinement_regions = user_mesh.get("refinement_regions", [
        {"name": "wakeBox", "min": [round(v, 3) for v in wake_min],
         "max": [round(v, 3) for v in wake_max], "level": wake_level},
    ])

    return {
        "base_cell_size": round(base_cell, 4),
        "surface_level": surface_level,
        "edge_level": edge_level,
        "distance_levels": distance_levels,
        "refinement_regions": refinement_regions,
        "nCellsBetweenLevels": user_mesh.get("nCellsBetweenLevels", preset.get("nCellsBetweenLevels", 3)),
        "maxGlobalCells": user_mesh.get("maxGlobalCells", preset.get("maxGlobalCells", 20_000_000)),
        "maxLocalCells": user_mesh.get("maxLocalCells", 2_000_000),
        "minRefinementCells": user_mesh.get("minRefinementCells", 10),
        "resolveFeatureAngle": resolve_feature_angle,
        "allowFreeStandingZoneFaces": user_mesh.get("allowFreeStandingZoneFaces", True),
    }


