"""Configuration loading, defaults, and validation.

The user config is minimal — just geometry + flow conditions.
Everything else is derived from universal defaults that work for any geometry.
"""

from __future__ import annotations

import copy
import json
import logging
import math
from pathlib import Path
from typing import Any

from rapidfoam.mesher_profiles import (
    SUPPORTED_MESHERS,
    load_mesher_profile,
    resolve_mesher,
)

log = logging.getLogger(__name__)

# ============================================================
# UNIVERSAL DEFAULTS — Settings that work for any geometry
# ============================================================

DEFAULT_CONFIG: dict[str, Any] = {
    "case_name": "my_case",
    "stl_files": [],
    "stl_dir": "stl",
    "case_dir": "cases",

    # Flow conditions
    "flow": {
        "velocity": 16.67,       # m/s
        "direction": "-z",       # freestream direction
        "ground": True,          # moving ground BC
    },

    # Output axes
    "outputs": {
        "drag_axis": "-z",
        "downforce_axis": "-y",
    },

    # Fluid properties (air at sea level, 20°C)
    "fluid": {
        "nu": 1.516e-5,
        "rho": 1.225,
    },

    # Turbulence (k-omega SST with wall functions — universal choice)
    "turbulence": {
        "model": "kOmegaSST",
        "intensity": 0.005,      # 0.5% — typical for external aero / FSAE
        "nut_ratio": 10,
    },

    # Domain patches
    "patches": {
        "inlet": "inlet",
        "outlet": "outlet",
        "ground": "ground",
        "walls": "farField",
        "symmetry": "symmetry",
    },

    # Force references
    "force_refs": {
        "lRef": 1.0,
        "Aref": 1.0,
        "CofR": [0, 0, 0],
    },

    # Parallel
    "parallel": {
        "n_procs": 10,
        "method": "scotch",
    },

    # SLURM
    "slurm": {
        "qos": "cu_hpc",
        "partition": "cpu",
        "nodes": 1,
        "time": "auto",
        "mem_per_cpu": "2G",
        "cpus_per_task": 1,
        "openfoam_module": None,
        "openfoam_source": "$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc",
    },

    # Solver settings (conservative, never-diverge)
    "solver": {
        "end_time": 800,
        "write_interval": 400,
        "purge_write": 2,
    },

    # Numerical schemes — stable second-order, no overshoot
    "schemes": {
        "div_U": "bounded Gauss limitedLinear 1",
        "div_k": "bounded Gauss upwind",
        "div_omega": "bounded Gauss upwind",
        "grad": "cellLimited Gauss linear 1",
        "laplacian": "Gauss linear limited corrected 0.5",
        "snGrad": "limited corrected 0.5",
        "wallDist": "meshWave",
    },

    # Linear solvers
    "linear_solvers": {
        "p": {
            "solver": "GAMG",
            "smoother": "DICGaussSeidel",
            "tolerance": 1e-7,
            "relTol": 0.01,
            "nPreSweeps": 0,
            "nPostSweeps": 2,
            "cacheAgglomeration": True,
            "agglomerator": "faceAreaPair",
            "nCellsInCoarsestLevel": 500,
            "mergeLevels": 2,
        },
        "U": {
            "solver": "PBiCGStab",
            "preconditioner": "DILU",
            "tolerance": 1e-8,
            "relTol": 0.01,
            "minIter": 1,
        },
    },

    # SIMPLE algorithm (SIMPLEC — more stable than classic SIMPLE)
    "simple": {
        "nNonOrthogonalCorrectors": 2,
        "consistent": True,
    },

    # Relaxation — SIMPLEC-optimized (consistent formulation enables U=0.7, p=0.7)
    "relaxation": {
        "fields": {"p": 0.7},
        "equations": {"U": 0.7, "k": 0.5, "omega": 0.5},
    },

    # Wall functions (Spalding bridges entire y+ range)
    "wall_functions": {
        "nut": "nutUSpaldingWallFunction",
        "k": "kqRWallFunction",
        "omega": "omegaWallFunction",
    },

    # Mesh — snappy settings (geometry-independent)
    "snap": {
        "nSmoothPatch": 5,
        "tolerance": 2.0,
        "nSolveIter": 200,
        "nRelaxIter": 8,
        "nFeatureSnapIter": 15,
        "implicitFeatureSnap": True,
        "explicitFeatureSnap": True,
        "multiRegionFeatureSnap": False,
    },

    # Boundary layers
    "layers": {
        "n_layers": 5,
        "expansion_ratio": 1.2,
        "first_layer_thickness": 0.3,   # relative
        "min_thickness": 0.05,
        "featureAngle": 170,
        "slipFeatureAngle": 30,
        "nGrow": 0,
        "maxFaceThicknessRatio": 0.5,
        "nSmoothSurfaceNormals": 3,
        "nSmoothThickness": 10,
        "nSmoothNormals": 3,
        "nRelaxIter": 10,
        "nBufferCellsNoExtrude": 0,
        "nLayerIter": 50,
        "maxAlignedCells": 200000,
        "minMedialAxisAngle": 90,
        "maxThicknessToMedialRatio": 0.3,
        "nMedialAxisIter": 10,
        "nSmoothDisplacement": 0,
        "detectExtrusionIsland": True,
        "nRelaxedIter": 20,
    },

    # Feature extraction (140° captures real aero edges without cosmetic CAD seams)
    "feature_extract": {
        "extractionMethod": "extractFromSurface",
        "includedAngle": 140,
    },

    # Mesh quality controls (relaxed — works with any geometry)
    "mesh_quality": {
        "maxNonOrtho": 65,
        "maxBoundarySkewness": 20,
        "maxInternalSkewness": 4,
        "maxConcave": 80,
        "minVol": 1e-13,
        "minTetQuality": 1e-15,
        "minArea": -1,
        "minTwist": 0.02,
        "minDeterminant": 0.001,
        "minFaceWeight": 0.05,
        "minVolRatio": 0.01,
        "minTriangleTwist": -1,
        "nSmoothScale": 4,
        "errorReduction": 0.75,
        "relaxed": {
            "maxNonOrtho": 75,
            "maxBoundarySkewness": 25,
            "maxInternalSkewness": 5,
            "maxConcave": 85,
            "minVol": 1e-13,
            "minTetQuality": 1e-30,
            "minArea": -1,
            "minTwist": 0.001,
            "minDeterminant": 0.0005,
            "minFaceWeight": 0.02,
            "minVolRatio": 0.005,
            "minTriangleTwist": -1,
        },
    },

    # potentialFoam
    "potential_flow": {
        "nNonOrthogonalCorrectors": 10,
    },

    # Mesher engine ("cfmesh" | "snappy")
    "mesher": "cfmesh",
    "cfmesh": {
        "workflow": "cartesianMesh",
        "feature_angle": 45,
    },
}


# ============================================================
# CONFIG LOADING
# ============================================================

def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override dict into base dict."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key.startswith("_"):
            continue
        if isinstance(val, dict):
            result[key] = deep_merge(result.get(key, {}) if isinstance(result.get(key), dict) else {}, val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def resolve_config_dict(
    user_cfg: dict[str, Any],
    mesher: str | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Resolve an in-memory case config dict into a complete configuration.

    This is the single source of truth for config resolution: the CLI funnels a
    JSON file through it (via :func:`load_config`), and the web UI funnels the
    browser payload through it, so validation, domain previews and generated
    case files can never disagree about what a case contains.

    Merge order (later wins): DEFAULT_CONFIG -> mesher profile -> case config ->
    case ``mesh_params_<mesher>`` block -> case ``overrides`` block.

    Args:
        user_cfg: Raw case config. Comment keys (leading ``_``) are stripped and
            the ``overrides`` block is applied last.
        mesher: Optional override ("cfmesh" | "snappy"); it selects the profile
            and beats the config's own ``mesher`` key.
        project_dir: Project root used to find ``configs/meshers/<mesher>.json``.

    Raises:
        ValueError: If ``user_cfg`` is not an object or ``overrides`` is not an
            object.
    """
    if not isinstance(user_cfg, dict):
        raise ValueError("Config must be a JSON object")

    # Strip comment keys
    user_cfg = {k: v for k, v in user_cfg.items() if not k.startswith("_")}

    # Apply overrides section into top-level (power user feature)
    overrides = user_cfg.pop("overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("'overrides' must be an object")

    cfg = deep_merge(DEFAULT_CONFIG, user_cfg)

    # Mesher profile sits directly under the case config: it supplies the
    # engine-native defaults for every key the case file did not state.
    mesher_key = str(mesher).strip().lower() if mesher else resolve_mesher(cfg)
    if mesher:
        cfg["mesher"] = mesher_key
    cfg = deep_merge(load_mesher_profile(mesher_key, project_dir), cfg)

    # Inline per-mesher tuning blocks, e.g. "mesh_params_cfmesh": { ... }
    inline: dict[str, Any] = {}
    for key in [k for k in cfg if k.startswith("mesh_params_")]:
        block = cfg.pop(key)
        if key == f"mesh_params_{mesher_key}" and isinstance(block, dict):
            inline = deep_merge(inline, block)
    if inline:
        cfg = deep_merge(cfg, {"mesh_params": inline})

    if overrides:
        cfg = deep_merge(cfg, overrides)

    return cfg


def load_config(
    config_path: str | Path,
    mesher: str | None = None,
    project_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load user config JSON and merge with defaults and the mesher profile.

    User only needs to specify:
      - case_name
      - stl_files
      - flow (velocity, direction, ground)
      - outputs (drag_axis, downforce_axis)

    Everything else uses universal defaults plus the mesher-native profile
    (`src/rapidfoam/mesher_profiles/<mesher>.json`, overlaid by an optional
    `configs/meshers/<mesher>.json`), so one case config can drive either
    engine while each writer still gets its own native settings.

    Merge order (later wins): DEFAULT_CONFIG -> mesher profile -> case config ->
    case `mesh_params_<mesher>` block -> case `overrides` block. The merge itself
    lives in :func:`resolve_config_dict`, which the web UI also calls so both
    entry points resolve a case identically.

    Args:
        config_path: Case config JSON.
        mesher: Optional CLI override ("cfmesh" | "snappy"); it selects the
            profile and beats the config's own "mesher" key.
        project_dir: Project root used to find `configs/meshers/<mesher>.json`.
    """
    config_path = Path(config_path)
    with open(config_path, encoding="utf-8") as f:
        user_cfg = json.load(f)
    return resolve_config_dict(user_cfg, mesher=mesher, project_dir=project_dir)


# ============================================================
# VALIDATION
# ============================================================

def validate(cfg: dict[str, Any], project_dir: Path) -> tuple[list[str], list[str]]:
    """Validate config. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    from rapidfoam.geometry import (
        FIDELITY_PRESETS,
        MIN_CELL_SIZE_ALIASES,
        face_assignments,
        face_role,
        parse_axis,
    )

    # Check containers before dereferencing nested values.
    sections = [key for key, value in DEFAULT_CONFIG.items() if isinstance(value, dict)]
    for section in sections + ["mesh_params", "domain"]:
        if not isinstance(cfg.get(section, {}), dict):
            errors.append(f"'{section}' must be an object")
    if errors:
        return errors, warnings

    def finite(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

    def vector(value: Any, label: str) -> bool:
        valid = isinstance(value, (list, tuple)) and len(value) == 3 and all(finite(v) for v in value)
        if not valid:
            errors.append(f"{label} must contain three finite numbers")
        return valid

    def positive(section: str, key: str, integer: bool = False, allow_zero: bool = False) -> None:
        value = cfg.get(section, {}).get(key)
        if key not in cfg.get(section, {}):
            return
        if (not finite(value) or (value < 0 if allow_zero else value <= 0)
                or (integer and not isinstance(value, int))):
            errors.append(f"{section}.{key} must be a finite {'integer' if integer else 'number'} "
                          f"{'≥ 0' if allow_zero else '> 0'}")

    # Required fields
    stl_files = cfg.get("stl_files")
    if not isinstance(stl_files, list) or not stl_files or not all(isinstance(n, str) and n for n in stl_files):
        errors.append("'stl_files' is required (list of STL filenames)")
        stl_files = []

    name = cfg.get("case_name")
    if not isinstance(name, str) or not name or name in (".", "..") or any(c in name for c in '/\\\r\n'):
        errors.append("'case_name' must be a nonempty folder name without path separators")
    for key in ("stl_dir", "case_dir"):
        if not isinstance(cfg.get(key), str) or not cfg[key]:
            errors.append(f"'{key}' must be a nonempty path string")
    if not isinstance(cfg.get("fidelity", "standard"), str) or cfg.get("fidelity", "standard") not in FIDELITY_PRESETS:
        errors.append("fidelity must be fast, standard, or fine")

    # Mesher engine
    mesher = cfg.get("mesher", "cfmesh")
    mesher_type = resolve_mesher(cfg)
    if not isinstance(mesher, (str, dict)):
        mesher_type = None
    if mesher_type not in SUPPORTED_MESHERS:
        errors.append("mesher must be 'snappy' or 'cfmesh'")

    if cfg.get("turbulence", {}).get("model", "kOmegaSST") != "kOmegaSST":
        errors.append("turbulence.model must be kOmegaSST; other models are not supported by the case writers")

    # Flow
    flow = cfg.get("flow", {})
    positive("flow", "velocity")
    if not isinstance(flow.get("ground"), bool):
        errors.append("flow.ground must be true or false")

    try:
        parse_axis(flow.get("direction", ""))
    except ValueError as e:
        errors.append(f"flow.direction: {e}")

    # Output axes
    outputs = cfg.get("outputs", {})
    for key in ("drag_axis", "downforce_axis"):
        try:
            parse_axis(outputs.get(key, ""))
        except ValueError as e:
            errors.append(f"outputs.{key}: {e}")

    # STL files
    stl_dir = project_dir / (cfg.get("stl_dir") if isinstance(cfg.get("stl_dir"), str) else "stl")
    if not stl_dir.is_dir():
        errors.append(f"STL directory not found: {stl_dir}")
    else:
        stems = set()
        for name in stl_files:
            stem = name.rsplit(".", 1)[0] if "." in name else name
            if not stem or stem in stems or any(c in name for c in '/\\\r\n'):
                errors.append(f"STL names must be filenames with unique nonempty stems: {name!r}")
                continue
            stems.add(stem)
            found = _find_stl(stl_dir, name)
            if not found:
                errors.append(f"STL not found: '{name}' in {stl_dir}")

    # Patches
    required_patches = {"inlet", "outlet", "ground", "walls", "symmetry"}
    missing = required_patches - set(cfg.get("patches", {}).keys())
    if missing:
        errors.append(f"Missing patch keys: {missing}")
    patch_names = list(cfg.get("patches", {}).values())
    if not all(isinstance(n, str) and n and not any(c.isspace() for c in n) for n in patch_names):
        errors.append("patch names must be nonempty strings without whitespace")
    elif len(set(patch_names)) != len(patch_names):
        errors.append("patch names must be unique")

    for section, keys in {
        "fluid": ("nu", "rho"), "turbulence": ("intensity", "nut_ratio"),
        "mesh_params": ("base_cell_size", "boundary_cell_size", "ground_cell_size"), "solver": ("end_time", "write_interval"),
        "layers": ("expansion_ratio", "first_layer_thickness", "min_thickness"),
        "force_refs": ("lRef", "Aref"),
    }.items():
        for key in keys:
            positive(section, key)
    for section, keys in {
        "parallel": ("n_procs",), "slurm": ("nodes", "cpus_per_task"),
        "mesh_params": ("maxGlobalCells", "maxLocalCells", "nCellsBetweenLevels"),
    }.items():
        for key in keys:
            positive(section, key, integer=True)
    for key in ("edge_level", "near_wake_level", "far_wake_level", "wake_level", "minRefinementCells"):
        positive("mesh_params", key, integer=True, allow_zero=True)
    positive("layers", "n_layers", integer=True, allow_zero=True)
    positive("solver", "purge_write", integer=True, allow_zero=True)
    for key in cfg.get("domain", {}):
        if key.endswith("_factor"):
            positive("domain", key)
    for key in ("ground_plane", "ground_clearance", "symmetry_plane", "centerline"):
        value = cfg.get(key)
        if value is not None and (not finite(value) or (key == "ground_clearance" and value < 0)):
            errors.append(f"{key} must be finite" + (" and ≥ 0" if key == "ground_clearance" else ""))
    vector(cfg["force_refs"].get("CofR"), "force_refs.CofR")
    mesh = cfg.get("mesh_params", {})
    for key in ("locationInMesh", "location_in_mesh"):
        if key in mesh:
            vector(mesh[key], f"mesh_params.{key}")
    level = mesh.get("surface_level")
    if level is not None and (not isinstance(level, (list, tuple)) or len(level) != 2
                             or not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in level)
                             or level[0] > level[1]):
        errors.append("mesh_params.surface_level must be two ordered nonnegative integers")
    for key in ("body_cell_size", "edge_cell_size", "min_cell_size", "refinement_thickness"):
        if key == "min_cell_size" and isinstance(mesh.get(key), str):
            # cfMesh's global refinement floor also takes aliases, e.g. "body"
            # (= snappy's surface_level[0]) or "edge" (= snappy's edge_level).
            if mesh[key].strip().lower() not in MIN_CELL_SIZE_ALIASES:
                errors.append(
                    "mesh_params.min_cell_size must be a number in metres or one of "
                    f"{', '.join(sorted(MIN_CELL_SIZE_ALIASES))}"
                )
            continue
        positive("mesh_params", key)

    # ---- Mesher-profile keys (src/rapidfoam/mesher_profiles/<mesher>.json) ----
    mode = mesh.get("cell_size_mode")
    if mode is not None and str(mode).lower() not in ("absolute", "relative_levels"):
        errors.append("mesh_params.cell_size_mode must be 'absolute' or 'relative_levels'")
    if "ground_refine" in mesh and not isinstance(mesh["ground_refine"], bool):
        errors.append("mesh_params.ground_refine must be true or false")

    cfmesh_cfg = cfg.get("cfmesh", {})
    if not isinstance(cfmesh_cfg, dict):
        errors.append("'cfmesh' must be an object")
    else:
        optimise = cfmesh_cfg.get("optimise_layer", "auto")
        valid_optimise = isinstance(optimise, bool) or (
            isinstance(optimise, str) and optimise.strip().lower() in ("auto", "true", "false")
        )
        if not valid_optimise:
            errors.append("cfmesh.optimise_layer must be true, false or 'auto'")
        enum_keys = {
            "layer_mode": ("patch_only", "global"),
        }
        for key, allowed in enum_keys.items():
            if key in cfmesh_cfg and str(cfmesh_cfg[key]).lower() not in allowed:
                errors.append(f"cfmesh.{key} must be one of {', '.join(repr(a) for a in allowed)}")
        if "ground_refine" in cfmesh_cfg and not isinstance(cfmesh_cfg["ground_refine"], bool):
            errors.append("cfmesh.ground_refine must be true or false")
        positive("cfmesh", "refinement_thickness")
        positive("cfmesh", "feature_angle")

    layers_cfg = cfg.get("layers", {})
    first_layer_mode = str(layers_cfg.get("first_layer_mode", "relative")).lower()
    if first_layer_mode not in ("relative", "absolute"):
        errors.append("layers.first_layer_mode must be 'relative' or 'absolute'")
    elif first_layer_mode == "absolute" and not layers_cfg.get("first_layer_height"):
        errors.append("layers.first_layer_height (metres) is required when layers.first_layer_mode is 'absolute'")
    positive("layers", "first_layer_height")

    # Keys that only one engine reads — flag them instead of silently ignoring
    if mesher_type == "cfmesh":
        ignored = sorted(
            key for key in ("maxGlobalCells", "maxLocalCells", "nCellsBetweenLevels",
                            "minRefinementCells", "distance_levels", "resolveFeatureAngle")
            if key in mesh
        )
        if ignored:
            warnings.append(
                f"cfMesh ignores {', '.join(ignored)} (snappy-only keys). Control cfMesh cost with "
                "mesh_params.body_cell_size / edge_cell_size / min_cell_size, cfmesh.ground_refine, "
                "cfmesh.optimise_layer and the wake box levels instead."
            )

    # Ground settings precedence warning
    if cfg.get("ground_plane") is not None and cfg.get("ground_clearance") is not None:
        warnings.append(
            f"Both 'ground_plane' ({cfg['ground_plane']}) and 'ground_clearance' "
            f"({cfg['ground_clearance']}) are defined; 'ground_plane' takes precedence."
        )

    # Domain box (can be "auto" or {"min": [x,y,z], "max": [x,y,z]})
    box = cfg.get("domain_box")
    if box not in ("auto", None) and not isinstance(box, dict):
        errors.append("'domain_box' must be 'auto' or a dict: {\"min\": [x,y,z], \"max\": [x,y,z]}")
    elif isinstance(box, dict):
        min_valid = vector(box.get("min"), "domain_box.min")
        max_valid = vector(box.get("max"), "domain_box.max")
        if min_valid and max_valid:
            for i in range(3):
                if box["min"][i] >= box["max"][i]:
                    errors.append(f"domain_box min[{i}] >= max[{i}]")

    # Geometry and field writers require independent flow and vertical axes.
    try:
        flow_vec = parse_axis(flow.get("direction", ""))
        up_vec = parse_axis(outputs.get("downforce_axis", ""))
        drag_vec = parse_axis(outputs.get("drag_axis", ""))
        if any(a and b for a, b in zip(flow_vec, up_vec)):
            errors.append("flow.direction and outputs.downforce_axis must use different axes")
        if any(a and b for a, b in zip(drag_vec, up_vec)):
            errors.append("drag_axis and downforce_axis must use different axes")
    except ValueError:
        pass
    faces = cfg.get("domain_faces")
    if "domain_faces" in cfg:
        if not isinstance(faces, dict) or set(faces) != {s+a for a in "xyz" for s in "-+"}:
            errors.append("domain_faces must assign all six faces: -x, +x, -y, +y, -z, +z")
        elif any(not isinstance(v, str) or face_role(cfg, v) not in required_patches for v in faces.values()):
            errors.append("domain_faces values must be boundary roles or configured patch names")
    if not errors:
        resolved = face_assignments(cfg)
        roles = {d: face_role(cfg, p) for d, p in resolved.items()}
        if "inlet" not in roles.values() or "outlet" not in roles.values():
            errors.append("domain_faces must include inlet and outlet")
        up_idx = next(i for i, v in enumerate(up_vec) if v)
        flow_idx = next(i for i, v in enumerate(flow_vec) if v)
        lateral_idx = next(i for i in range(3) if i not in (up_idx, flow_idx))
        for role, axis in (("ground", up_idx), ("symmetry", lateral_idx)):
            assigned = [d for d, r in roles.items() if r == role]
            if len(assigned) > 1 or any(d[-1] != "xyz"[axis] for d in assigned):
                errors.append(f"{role} must occupy at most one face on the {'xyz'[axis]} axis")
    return errors, warnings


def _find_stl(stl_dir: Path, name: str) -> Path | None:
    """Search for STL file with flexible naming."""
    # Strip extension if user included it
    stem = name.rsplit(".", 1)[0] if "." in name else name

    for pattern in (name, f"{stem}.stl", f"{stem}.STL",
                    f"{stem.lower()}.stl", f"{stem.lower()}.STL"):
        p = stl_dir / pattern
        if p.is_file():
            return p
    return None


def find_stl(stl_dir: Path, name: str) -> Path | None:
    """Public interface for STL file search."""
    return _find_stl(stl_dir, name)
