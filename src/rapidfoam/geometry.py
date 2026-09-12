"""Geometry utilities — axis math, domain sizing, boundary-role resolution.

Cell sizing and mesh refinement live in :mod:`rapidfoam.meshers` (sizing.py for
the cell sizes, refinement.py for the wake/trailing-edge regions), because they
are what the meshers translate into engine units. This module stays pure
geometry so ``meshers`` can import it without a cycle.
"""

from __future__ import annotations

import math
from typing import Any

from rapidfoam.stl_utils import BBox

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
    if not isinstance(s, str):
        raise ValueError("Axis must be a string: +x, -x, +y, -y, +z, -z")
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


def face_role(cfg: dict[str, Any], patch_name: str) -> str:
    """Resolve a patch name to its configured boundary role."""
    for role, name in cfg["patches"].items():
        if patch_name == name:
            return role
    return {"farField": "walls"}.get(patch_name, patch_name)


def face_assignments(cfg: dict[str, Any]) -> dict[str, str]:
    """Resolve the six faces once for domain sizing and every writer."""
    patches = cfg["patches"]
    if "domain_faces" in cfg:
        return {direction: patches.get(face_role(cfg, name), name)
                for direction, name in cfg["domain_faces"].items()}
    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i not in (flow_idx, up_idx))
    faces = {sign + axis: patches["walls"] for axis in "xyz" for sign in "-+"}
    faces[("-" if flow_sign > 0 else "+") + "xyz"[flow_idx]] = patches["inlet"]
    faces[("+" if flow_sign > 0 else "-") + "xyz"[flow_idx]] = patches["outlet"]
    faces["-" + "xyz"[up_idx]] = patches["ground"]
    faces["-" + "xyz"[lateral_idx]] = patches["symmetry"]
    return faces


# ============================================================
# DOMAIN SIZING — Geometry-derived, generous padding
# ============================================================

def compute_domain_box(cfg: dict[str, Any], combined_bounds: BBox) -> dict[str, list[float]]:
    """Compute domain bounding box from STL bounds.

    Uses generous padding to avoid blockage effects:
      - Upstream: 4× geometry length
      - Downstream: 8× geometry length
      - Lateral/top: 4× geometry height
      - Ground at smin[up_idx] (for ground vehicles)
      - Symmetry at lateral=smin[lateral_idx] if symmetry face, else padded

    Returns:
        {"min": [x,y,z], "max": [x,y,z]}
    """
    smin, smax = combined_bounds
    extents = [smax[i] - smin[i] for i in range(3)]

    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i != flow_idx and i != up_idx)

    # Padding factors (reduced for fast fidelity)
    fidelity = cfg.get("fidelity", "standard")
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

    # Up axis: ground plane for vehicles, or open air padding for airplanes/free-flight
    up_extent = max(extents[up_idx], 0.1)
    domain_faces = {d: face_role(cfg, name) for d, name in face_assignments(cfg).items()}
    up_min_key = f"-{'xyz'[up_idx]}"
    is_ground = "ground" in domain_faces.get(up_min_key, "").lower()

    ground_coord = cfg.get("ground_plane")
    if ground_coord is not None:
        dmin[up_idx] = float(ground_coord)
    elif "ground_clearance" in cfg and cfg["ground_clearance"] is not None and is_ground:
        dmin[up_idx] = smin[up_idx] - float(cfg["ground_clearance"])
    elif is_ground:
        dmin[up_idx] = smin[up_idx]  # ground plane touches bottom of car
    else:
        # Airborne / airplane: open atmosphere below aircraft
        bottom_factor = cfg.get("domain", {}).get("bottom_factor", top)
        dmin[up_idx] = smin[up_idx] - up_extent * bottom_factor

    dmax[up_idx] = smax[up_idx] + up_extent * top

    # Lateral axis
    lat_extent = max(extents[lateral_idx], 0.1)
    lateral_min_key = f"-{'xyz'[lateral_idx]}"
    is_symmetry = "symmetry" in domain_faces.get(lateral_min_key, "").lower()

    # Centerline / symmetry plane coordinate (supports planes not at 0)
    sym_coord = cfg.get("symmetry_plane", cfg.get("centerline"))

    if is_symmetry:
        if sym_coord is not None:
            dmin[lateral_idx] = float(sym_coord)
            car_half_width = max(0.1, smax[lateral_idx] - float(sym_coord))
            dmax[lateral_idx] = smax[lateral_idx] + car_half_width * lateral
        elif abs(smin[lateral_idx]) < 0.05:
            dmin[lateral_idx] = 0.0
            dmax[lateral_idx] = smax[lateral_idx] + lat_extent * lateral
        else:
            dmin[lateral_idx] = smin[lateral_idx]
            dmax[lateral_idx] = smax[lateral_idx] + lat_extent * lateral
    else:
        dmin[lateral_idx] = smin[lateral_idx] - lat_extent * lateral
        dmax[lateral_idx] = smax[lateral_idx] + lat_extent * lateral

    # The positive-face variants retain the half-model on the opposite side.
    if domain_faces.get(f"+{'xyz'[up_idx]}") == "ground":
        dmin[up_idx] = smin[up_idx] - up_extent * top
        dmax[up_idx] = (float(ground_coord) if ground_coord is not None else
                       smax[up_idx] + float(cfg.get("ground_clearance") or 0))
    if domain_faces.get(f"+{'xyz'[lateral_idx]}") == "symmetry":
        edge = smax[lateral_idx]
        plane = (float(sym_coord) if sym_coord is not None else
                 0.0 if abs(edge) < 0.05 else edge)
        width = max(0.1, plane - smin[lateral_idx]) if sym_coord is not None else lat_extent
        dmax[lateral_idx] = plane
        dmin[lateral_idx] = smin[lateral_idx] - width * lateral

    return {
        "min": [round(v, 4) for v in dmin],
        "max": [round(v, 4) for v in dmax],
    }


__all__ = [
    "AXIS_MAP",
    "axis_index_sign",
    "compute_domain_box",
    "face_assignments",
    "face_role",
    "flow_axis_index_sign",
    "parse_axis",
    "turbulence_values",
    "up_axis_index",
    "vec_str",
    "velocity_vector",
]
