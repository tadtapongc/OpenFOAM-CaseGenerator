"""Configuration loading, defaults, and validation.

The user config is minimal — just geometry + flow conditions.
Everything else is derived from universal defaults that work for any geometry.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

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
        "mem_per_cpu": "3G",
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
            "mergeLevels": 1,
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

    # Relaxation — SIMPLEC-optimized, damps oscillation
    "relaxation": {
        "fields": {"p": 0.5},
        "equations": {"U": 0.6, "k": 0.5, "omega": 0.5},
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

    # Feature extraction
    "feature_extract": {
        "extractionMethod": "extractFromSurface",
        "includedAngle": 150,
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
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def load_config(config_path: str | Path) -> dict[str, Any]:
    """Load user config JSON and merge with universal defaults.

    User only needs to specify:
      - case_name
      - stl_files
      - flow (velocity, direction, ground)
      - outputs (drag_axis, downforce_axis)

    Everything else uses universal defaults.
    """
    config_path = Path(config_path)
    with open(config_path) as f:
        user_cfg = json.load(f)

    # Strip comment keys
    user_cfg = {k: v for k, v in user_cfg.items() if not k.startswith("_")}

    # Apply overrides section into top-level (power user feature)
    overrides = user_cfg.pop("overrides", {})

    cfg = deep_merge(DEFAULT_CONFIG, user_cfg)
    if overrides:
        cfg = deep_merge(cfg, overrides)

    return cfg


# ============================================================
# VALIDATION
# ============================================================

def validate(cfg: dict[str, Any], project_dir: Path) -> tuple[list[str], list[str]]:
    """Validate config. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    # Required fields
    if not cfg.get("stl_files"):
        errors.append("'stl_files' is required (list of STL filenames)")

    if not cfg.get("case_name"):
        errors.append("'case_name' is required")

    # Flow
    flow = cfg.get("flow", {})
    if flow.get("velocity", 0) <= 0:
        errors.append("flow.velocity must be > 0")

    try:
        from cfd_gen.geometry import parse_axis
        parse_axis(flow.get("direction", ""))
    except ValueError as e:
        errors.append(f"flow.direction: {e}")

    # Output axes
    outputs = cfg.get("outputs", {})
    for key in ("drag_axis", "downforce_axis"):
        try:
            from cfd_gen.geometry import parse_axis
            parse_axis(outputs.get(key, ""))
        except ValueError as e:
            errors.append(f"outputs.{key}: {e}")

    # STL files
    stl_dir = project_dir / cfg.get("stl_dir", "STL")
    if not stl_dir.exists():
        errors.append(f"STL directory not found: {stl_dir}")
    else:
        for name in cfg.get("stl_files", []):
            found = _find_stl(stl_dir, name)
            if not found:
                warnings.append(f"STL not found: '{name}' in {stl_dir}")

    # Patches
    required_patches = {"inlet", "outlet", "ground", "walls", "symmetry"}
    missing = required_patches - set(cfg.get("patches", {}).keys())
    if missing:
        errors.append(f"Missing patch keys: {missing}")

    # Domain box (required)
    box = cfg.get("domain_box")
    if not box:
        errors.append("'domain_box' is required: {\"min\": [x,y,z], \"max\": [x,y,z]}")
    elif "min" not in box or "max" not in box:
        errors.append("domain_box must have 'min' and 'max' keys")
    else:
        for i in range(3):
            if box["min"][i] >= box["max"][i]:
                errors.append(f"domain_box min[{i}] >= max[{i}]")

    return errors, warnings


def _find_stl(stl_dir: Path, name: str) -> Path | None:
    """Search for STL file with flexible naming."""
    # Strip extension if user included it
    stem = name.rsplit(".", 1)[0] if "." in name else name

    for pattern in (name, f"{stem}.stl", f"{stem}.STL",
                    f"{stem.lower()}.stl", f"{stem.lower()}.STL"):
        p = stl_dir / pattern
        if p.exists():
            return p
    return None


def find_stl(stl_dir: Path, name: str) -> Path | None:
    """Public interface for STL file search."""
    return _find_stl(stl_dir, name)
