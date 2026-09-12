"""snappyHexMesh as a mesher: state, files, plan and validation.

The module mirrors :mod:`rapidfoam.meshers.cfmesh`, one file per responsibility:

    settings.py                     cfg -> SnappySettings (defaults, levels, caps)
    block_mesh_dict.py              SnappySettings -> system/blockMeshDict
    surface_feature_extract_dict.py SnappySettings -> system/surfaceFeatureExtractDict
    snappy_hex_mesh_dict.py         SnappySettings -> system/snappyHexMeshDict
    plan.py                         the meshing commands (rendered by writers/scripts.py)
    keys.py                         the config surface it reads, declared once

The dictionaries are rendered from resolved settings only, so the CLI, the plan
and the verification scripts all read the same numbers.

``surfaceFeatureExtract``, ``blockMesh``, ``snappyHexMesh``, ``checkMesh`` and
``renumberMesh`` are stock OpenFOAM apps and must be on ``$PATH`` (or ``$WM_PROJECT_DIR``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rapidfoam.meshers.keys import removed, unknown_keys
from rapidfoam.meshers.plan import MeshPlan
from rapidfoam.meshers.refinement import keys_for, unread_keys
from rapidfoam.meshers.snappy.block_mesh_dict import (
    FACE_MAP,
    render_block_mesh_dict,
    write_block_mesh_dict,
)
from rapidfoam.meshers.snappy.keys import REMOVED_KEYS, SNAPPY_KEYS
from rapidfoam.meshers.snappy.plan import snappy_mesh_plan, snappy_plan_from_config
from rapidfoam.meshers.snappy.settings import (
    RefinementBox,
    SnappySettings,
    resolve_cells,
    resolve_location_in_mesh,
    resolve_snappy_settings,
)
from rapidfoam.meshers.snappy.snappy_hex_mesh_dict import (
    render_snappy_hex_mesh_dict,
    write_snappy_hex_mesh_dict,
)
from rapidfoam.meshers.snappy.surface_feature_extract_dict import (
    render_surface_feature_extract_dict,
    write_surface_feature_extract_dict,
)


class Snappy:
    """snappyHexMesh's entry in the mesher registry."""

    name = "snappy"
    label = "snappyHexMesh"
    #: snappy splits the mesh itself, but it caps the result with maxGlobalCells.
    enforces_cell_budget = True

    # ---- config surface -------------------------------------------------
    def engine_keys(self) -> dict[str, Any]:
        return SNAPPY_KEYS

    def mesh_params_keys(self) -> dict[str, Any]:
        return keys_for(self.name)

    def removed_keys(self) -> dict[str, str]:
        return REMOVED_KEYS

    def settings(self, cfg: dict[str, Any]) -> SnappySettings:
        return resolve_snappy_settings(cfg)

    # ---- files ----------------------------------------------------------
    def write_case(self, cfg: dict[str, Any], case_dir: Path,
                   stl_pairs: list[tuple[str, Path]]) -> list[str]:
        """Write the three dictionaries; returns what was written."""
        settings = self.settings(cfg)
        write_block_mesh_dict(settings, case_dir)
        write_surface_feature_extract_dict(settings, case_dir)
        write_snappy_hex_mesh_dict(settings, case_dir)
        return ["system/blockMeshDict", "system/surfaceFeatureExtractDict",
                "system/snappyHexMeshDict"]

    # ---- execution ------------------------------------------------------
    def mesh_plan(self, cfg: dict[str, Any]) -> MeshPlan:
        # Deliberately the config-only plan: snappy's commands follow
        # parallel.n_procs, never the resolved domain box, so scripts can be written
        # before (or without) measuring the geometry.
        return snappy_plan_from_config(cfg)

    # ---- validation -----------------------------------------------------
    def validate(self, cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Errors and warnings only snappy can raise."""
        warnings: list[str] = []
        mesh = cfg.get("mesh_params", {})
        errors = removed(mesh, REMOVED_KEYS, "mesh_params")

        # Keys that belong to the other engine: flag them instead of silently
        # ignoring them. Which keys those are comes from the shared table.
        ignored = unread_keys(mesh, self.name)
        if ignored:
            warnings.append(
                f"snappyHexMesh ignores {', '.join(ignored)} (cfMesh-only keys). "
                "snappy's floor is mesh_params.surface_level / edge_level; min_cell_size "
                "has no snappy equivalent."
            )

        # A "snappy" block is accepted but nothing reads it yet, so a typo there
        # would otherwise pass silently.
        engine = cfg.get("snappy", {})
        if isinstance(engine, dict):
            warnings += unknown_keys(engine, SNAPPY_KEYS, "snappy")
        else:
            errors.append("'snappy' must be an object")
        return errors, warnings


SNAPPY = Snappy()

__all__ = [
    "FACE_MAP",
    "REMOVED_KEYS",
    "SNAPPY",
    "SNAPPY_KEYS",
    "RefinementBox",
    "Snappy",
    "SnappySettings",
    "render_block_mesh_dict",
    "render_snappy_hex_mesh_dict",
    "render_surface_feature_extract_dict",
    "resolve_cells",
    "resolve_location_in_mesh",
    "resolve_snappy_settings",
    "snappy_mesh_plan",
    "snappy_plan_from_config",
    "write_block_mesh_dict",
    "write_snappy_hex_mesh_dict",
    "write_surface_feature_extract_dict",
]
