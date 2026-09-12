"""Fidelity presets — the one place resolution policy is stated.

A preset is a *sizing policy*: ``cells_per_length`` background cells along the
longest bounding-box dimension of the model, the levels/shells/wake boxes derived
from it, and the per-mesh_params keys the writers read. Because the numbers are
relative, one preset means the same resolution per model length on a full car, a
front wing or a subassembly, and the cell count stays in the same ballpark on
either. The values are calibrated to reproduce the old absolute presets
(0.15 / 0.10 / 0.08 m base cell) at the 3.0 m reference length they were tuned on.

The wake boxes are relative in both senses: they are sized as fractions of the
model (``WAKE_*`` in :mod:`rapidfoam.meshers.refinement`) and their levels sit
``wake_levels_below_surface`` under ``surface_level[0]``, so a preset that refines
the surface refines the wake with it and a small model cannot ask for a wake box
that costs more than the model does.

Override per case with ``mesh_params.base_cell_size`` (metres) or
``mesh_params.cells_per_length``; ``docs/cfmesh.md`` explains the measurements
behind the defaults.
"""

from __future__ import annotations

from typing import Any

FIDELITY_PRESETS: dict[str, dict[str, Any]] = {
    "fast": {
        "desc": "Iterative design sweeps — coarse background, no layer optimisation",
        "cell_estimate": "~0.3-2 M cells (full car)",
        "n_cells_target": 1_000_000,
        "runtime_estimate": "~5-15 min on 32 cores",
        "base_cell_size": "auto",      # m — max_extent / cells_per_length
        "cells_per_length": 20,        # 0.15 m on a 3.0 m car; 0.06 m on a 1.2 m wing
        "surface_level": [3, 4],
        "edge_level": 5,
        "trailing_edge_refine": True,  # thin downstream edge: one local box
        "n_layers": 3,
        "expansion_ratio": 1.3,
        "first_layer_thickness": 0.4,
        "end_time": 800,
        "write_interval": 400,
        "maxGlobalCells": 8_000_000,
        "nCellsBetweenLevels": 2,
        "resolveFeatureAngle": 35,
        "nSolveIter": 100,
        "nFeatureSnapIter": 10,
        "nLayerIter": 30,
        "nRelaxIter_layers": 5,
        "slurm_time": "04:00:00",
        # Distance-based refinement shells, in units of the base cell
        "distance_shells": [
            (0.267, 3),   # 0.267 x base -> level 3
            (0.80, 2),    # 0.80 x base -> level 2
        ],
        # Wake boxes one level (near) and two levels (far) below the surface level.
        "wake_levels_below_surface": [1, 2],
    },
    "standard": {
        "desc": "Balanced — the default for FSAE design studies",
        "cell_estimate": "~1-5 M cells (full car)",
        "n_cells_target": 3_000_000,
        "runtime_estimate": "~15-60 min on 32 cores",
        "base_cell_size": "auto",      # m — max_extent / cells_per_length
        "cells_per_length": 30,        # 0.10 m on a 3.0 m car; 0.04 m on a 1.2 m wing
        "surface_level": [4, 5],       # 6.25 mm bodywork, 3.125 mm fine features
        "edge_level": 6,               # 1.56 mm at sharp aero edges (wings, gurneys)
        "trailing_edge_refine": True,
        "n_layers": 5,
        "expansion_ratio": 1.2,
        "first_layer_thickness": 0.3,
        "end_time": 1500,
        "write_interval": 500,
        "maxGlobalCells": 18_000_000,
        "nCellsBetweenLevels": 2,
        "resolveFeatureAngle": 35,     # keeps body curvature from ballooning to max level
        "nSolveIter": 200,
        "nFeatureSnapIter": 15,
        "nLayerIter": 50,
        "nRelaxIter_layers": 10,
        "slurm_time": "08:00:00",
        "distance_shells": [
            (0.25, 4),    # 25 mm shell = 6.25 mm cells on a 3.0 m car
            (0.80, 3),    # 80 mm -> 12.5 mm
        ],
        # One level below the surface for the rear-wing vortex / diffuser, three
        # below for downstream transport only.
        "wake_levels_below_surface": [1, 3],
    },
    "fine": {
        "desc": "Validation / report quality — finest surface and wake resolution",
        "cell_estimate": "~5-20 M cells (full car)",
        "n_cells_target": 12_000_000,
        "runtime_estimate": "~1-4 hours on 32 cores",
        "base_cell_size": "auto",      # m — max_extent / cells_per_length
        "cells_per_length": 37.5,      # 0.08 m on a 3.0 m car; 0.032 m on a 1.2 m wing
        "surface_level": [5, 6],       # 2.5 mm / 1.25 mm
        "edge_level": 7,               # 0.625 mm at edges
        "trailing_edge_refine": True,
        "n_layers": 6,
        "expansion_ratio": 1.15,
        "first_layer_thickness": 0.2,
        "end_time": 3000,
        "write_interval": 500,
        "maxGlobalCells": 30_000_000,
        "nCellsBetweenLevels": 2,
        "resolveFeatureAngle": 30,
        "nSolveIter": 300,
        "nFeatureSnapIter": 20,
        "nLayerIter": 50,
        "nRelaxIter_layers": 10,
        "slurm_time": "12:00:00",
        "distance_shells": [
            (0.25, 5),
            (0.75, 4),
            (1.875, 3),
        ],
        "wake_levels_below_surface": [1, 3],
    },
}


def preset_for(fidelity: str) -> dict[str, Any]:
    """The preset for ``fidelity``, falling back to ``standard``."""
    return FIDELITY_PRESETS.get(str(fidelity), FIDELITY_PRESETS["standard"])


__all__ = ["FIDELITY_PRESETS", "preset_for"]
