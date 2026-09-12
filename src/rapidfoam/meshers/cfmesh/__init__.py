"""cfMesh (cartesianMesh) as a mesher: state, files, plan and validation.

The module splits cfMesh knowledge the way the rest of the code needs it:

    settings.py   cfg -> CfMeshSettings (all "auto"/alias/default resolution)
    mesh_dict.py  CfMeshSettings -> system/meshDict (pure rendering)
    surface.py    constant/triSurface/domain.stl (box faces + CAD)
    plan.py       the meshing commands (rendered by writers/scripts.py)
    keys.py       the config surface it reads, declared once

RapidFOAM runs the stock cfMesh apps (``cartesianMesh``, plus
``surfaceFeatureEdges`` to build the feature surface it meshes), so they must be
available on ``$FOAM_USER_APPBIN`` or ``$PATH``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rapidfoam.meshers.cfmesh.keys import (
    CFMESH_KEYS,
    OPTIMISATION_KEYS,
    REMOVED_ENGINE_KEYS,
    REMOVED_KEYS,
)
from rapidfoam.meshers.cfmesh.mesh_dict import render_mesh_dict, write_mesh_dict
from rapidfoam.meshers.cfmesh.plan import cfmesh_mesh_plan, cfmesh_plan_from_config
from rapidfoam.meshers.cfmesh.settings import (
    CfMeshSettings,
    Region,
    resolve_cfmesh_settings,
)
from rapidfoam.meshers.cfmesh.surface import generate_domain_stl, write_box_stl_faces
from rapidfoam.meshers.keys import removed, unknown_keys, validate_keys
from rapidfoam.meshers.plan import MeshPlan
from rapidfoam.meshers.refinement import keys_for, unread_keys


class CfMesh:
    """cfMesh's entry in the mesher registry."""

    name = "cfmesh"
    label = "cfMesh (cartesianMesh)"
    #: cfMesh has no maxGlobalCells-style cap: cost follows the cell sizes.
    enforces_cell_budget = False

    # ---- config surface -------------------------------------------------
    def engine_keys(self) -> dict[str, Any]:
        return CFMESH_KEYS

    def mesh_params_keys(self) -> dict[str, Any]:
        return keys_for(self.name)

    def removed_keys(self) -> dict[str, str]:
        return REMOVED_KEYS

    def settings(self, cfg: dict[str, Any]) -> CfMeshSettings:
        return resolve_cfmesh_settings(cfg)

    # ---- files ----------------------------------------------------------
    def write_case(self, cfg: dict[str, Any], case_dir: Path,
                   stl_pairs: list[tuple[str, Path]]) -> list[str]:
        """Write domain.stl and system/meshDict; returns what was written."""
        generate_domain_stl(cfg, case_dir, stl_pairs)
        write_mesh_dict(self.settings(cfg), case_dir)
        return ["constant/triSurface/domain.stl", "system/meshDict"]

    # ---- execution ------------------------------------------------------
    def mesh_plan(self, cfg: dict[str, Any]) -> MeshPlan:
        # Deliberately the config-only plan: the commands depend on the MPI policy
        # and the crease angle, never on the resolved domain box, so scripts can be
        # written before (or without) measuring the geometry.
        return cfmesh_plan_from_config(cfg)

    # ---- validation -----------------------------------------------------
    def validate(self, cfg: dict[str, Any]) -> tuple[list[str], list[str]]:
        """Errors and warnings only cfMesh can raise."""
        errors: list[str] = []
        warnings: list[str] = []
        engine = cfg.get("cfmesh", {})
        if not isinstance(engine, dict):
            return ["'cfmesh' must be an object"], warnings

        errors += removed(engine, REMOVED_ENGINE_KEYS, "cfmesh")
        errors += validate_keys(engine, CFMESH_KEYS, "cfmesh")

        optimisation = engine.get("optimisation")
        if isinstance(optimisation, dict):
            errors += validate_keys(optimisation, OPTIMISATION_KEYS, "cfmesh.optimisation")
        elif optimisation is not None:
            errors.append("cfmesh.optimisation must be an object")

        mesh = cfg.get("mesh_params", {})
        errors += removed(mesh, REMOVED_KEYS, "mesh_params")
        # Unknown engine keys are a warning, not an error: a project profile may
        # carry a key a newer/older build understands.
        warnings += unknown_keys(engine, CFMESH_KEYS, "cfmesh")

        # Keys that belong to the other engine: flag them instead of silently
        # ignoring them. Which keys those are comes from the shared table.
        ignored = unread_keys(mesh, self.name)
        if ignored:
            warnings.append(
                f"cfMesh ignores {', '.join(ignored)} (snappy-only keys). Control cfMesh "
                "cost with mesh_params.min_cell_size, cfmesh.ground_refine, "
                "cfmesh.optimise_layer and the wake box levels instead."
            )
        return errors, warnings


CFMESH = CfMesh()

__all__ = [
    "CFMESH",
    "CFMESH_KEYS",
    "CfMesh",
    "CfMeshSettings",
    "OPTIMISATION_KEYS",
    "Region",
    "cfmesh_mesh_plan",
    "cfmesh_plan_from_config",
    "generate_domain_stl",
    "render_mesh_dict",
    "resolve_cfmesh_settings",
    "write_box_stl_faces",
    "write_mesh_dict",
]
