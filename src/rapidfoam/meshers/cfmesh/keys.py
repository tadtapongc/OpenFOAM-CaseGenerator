"""cfMesh's configuration surface, declared once.

Every key cfMesh reads is listed here, with the replacement to use for keys that
were removed in the rewrite. ``config.py`` validates against this table, the web
UI renders its "Auto / preset" placeholders from it, and
``docs/cfmesh.md`` is generated from the same descriptions, so a key cannot be
read in one place and undocumented in another.
"""

from __future__ import annotations

from rapidfoam.meshers.keys import (
    BOOL,
    INT,
    METRES,
    NUMBER,
    TRISTATE,
    KeySpec,
)

#: Keys in the ``cfmesh`` block of a case config.
CFMESH_KEYS: dict[str, KeySpec] = {
    "feature_angle": KeySpec(
        NUMBER,
        doc="Feature angle handed to surfaceFeatureEdges when it builds the "
            ".fms surface (edges sharper than this become feature edges).",
        default=45,
    ),
    "optimise_layer": KeySpec(
        TRISTATE,
        doc="Layer optimisation plus normal smoothing: the most expensive cfMesh "
            "pass. 'auto' keeps it for standard/fine and skips it for fast.",
        default="auto",
    ),
    "optimisation": KeySpec(
        "mapping",
        doc="optimisationParameters values, used only when layer optimisation "
            "runs: nSmoothNormals, maxNumIterations, featureSizeFactor, "
            "reCalculateNormals, relThicknessTol.",
    ),
    "ground_refine": KeySpec(
        BOOL,
        doc="Refine the road patch to ground_cell_size. Off by default: snappy "
            "never refines the ground, and refining the whole road forces a wide "
            "transition volume under the car.",
        default=False,
    ),
    "ground_cell_size": KeySpec(
        METRES,
        doc="Cell size for the road patch when ground_refine is on "
            "(default: half the base cell).",
    ),
    "boundary_cell_size": KeySpec(
        METRES,
        doc="Cell size on the wind tunnel walls (default: the base cell).",
    ),
    "refinement_thickness": KeySpec(
        METRES,
        doc="Emit refinementThickness inside every localRefinement entry to grow "
            "a distance shell around the surfaces. cfMesh's own transition is "
            "what dominates cell count, so this is the main dial for matching "
            "snappy's distance_levels.",
    ),
    "parallel_meshing": KeySpec(
        TRISTATE,
        doc="Run cartesianMesh under mpirun. 'auto' (default) turns it on when "
            "parallel.n_procs > 1; the octree is split over the ranks given on "
            "the mpirun command line and stitched back with reconstructParMesh, "
            "so no decomposePar is needed for meshing. A build without the "
            "parallel octree falls back to a serial mesh.",
        default="auto",
    ),
}

#: Sub-keys of ``cfmesh.optimisation`` (validated so a typo cannot pass silently).
OPTIMISATION_KEYS: dict[str, KeySpec] = {
    "nSmoothNormals": KeySpec(INT, doc="Normal-smoothing iterations.", default=3),
    "maxNumIterations": KeySpec(INT, doc="Layer-optimisation iterations.", default=2),
    "featureSizeFactor": KeySpec(NUMBER, doc="Feature-size scaling factor.", default=0.4),
    "reCalculateNormals": KeySpec(INT, doc="Recompute normals (1/0).",
                                  default=1, allow_zero=True),
    "relThicknessTol": KeySpec(NUMBER, doc="Relative thickness tolerance.", default=0.1),
}

#: Keys deleted on purpose, with what to use instead. Reported as errors so an
#: old config fails loudly instead of silently ignoring the setting.
REMOVED_KEYS: dict[str, str] = {
    "cell_size_mode": "cell sizes are stated once (body_cell_size / edge_cell_size / "
                      "min_cell_size in mesh_params) and each mesher translates them",
    "cell_budget_enforced": "cfMesh has no cell cap; check the mesher's "
                            "enforces_cell_budget capability instead",
    "layer_mode": "layers are applied to the STL surfaces; use layers.ground_layers "
                  "to include the road",
    "workflow": "the mesher registry selects the executable",
    "ground_refine": "moved to cfmesh.ground_refine - it is an engine key, not a "
                     "sizing key (snappy never refines the ground)",
    "ground_cell_size": "moved to cfmesh.ground_cell_size",
    "boundary_cell_size": "moved to cfmesh.boundary_cell_size",
    "refinement_thickness": "moved to cfmesh.refinement_thickness (it was accepted "
                            "in two places, and the mesh_params copy silently won)",
}

#: Removed *inside* the cfmesh block.
REMOVED_ENGINE_KEYS: dict[str, str] = {
    "layer_mode": "layers are applied to the STL surfaces; use layers.ground_layers "
                  "to include the road",
    "workflow": "the mesher registry selects the executable",
}

__all__ = [
    "CFMESH_KEYS",
    "OPTIMISATION_KEYS",
    "REMOVED_ENGINE_KEYS",
    "REMOVED_KEYS",
]
