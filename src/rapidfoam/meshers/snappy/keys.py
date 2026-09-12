"""snappyHexMesh's configuration surface, declared once.

snappy has no ``snappy`` block today: every knob it reads lives in its own
section (``snap``, ``layers``, ``mesh_quality``, ``feature_extract`` and the
snappy-only ``mesh_params`` keys declared in
:mod:`rapidfoam.meshers.refinement`), so this table is empty and exists to keep
the registry interface identical to cfMesh's. A future snappy-only key gets one
``KeySpec`` here and is validated, documented and rendered in the Studio UI from
that single line.

``REMOVED_KEYS`` lists ``mesh_params`` keys deleted on purpose, so an old config
fails loudly instead of silently ignoring the setting.
"""

from __future__ import annotations

from rapidfoam.meshers.keys import KeySpec

#: Keys in the ``snappy`` block of a case config (none today).
SNAPPY_KEYS: dict[str, KeySpec] = {}

#: Keys deleted on purpose, with what to use instead.
REMOVED_KEYS: dict[str, str] = {
    "cell_size_mode": "cell sizes are stated once (body_cell_size / edge_cell_size / "
                      "min_cell_size in mesh_params) and levels derive from them",
    "cell_budget_enforced": "read the mesher's enforces_cell_budget capability",
    "ground_refine": "moved to cfmesh.ground_refine - snappy never refines the road plane "
                     "(layer it with layers.ground_layers instead)",
    "ground_cell_size": "moved to cfmesh.ground_cell_size",
    "boundary_cell_size": "moved to cfmesh.boundary_cell_size",
    "refinement_thickness": "moved to cfmesh.refinement_thickness",
}

__all__ = ["REMOVED_KEYS", "SNAPPY_KEYS"]
