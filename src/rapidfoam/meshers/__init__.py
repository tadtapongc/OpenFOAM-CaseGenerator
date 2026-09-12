"""Mesher registry — one entry per engine, one place that knows their names.

A mesher owns everything engine-specific about meshing:

    name                     "cfmesh" | "snappy"
    enforces_cell_budget     whether it has a maxGlobalCells-style cap
    mesh_params_keys()       the ``mesh_params`` keys it reads (validated)
    engine_keys()            the keys of its own config block (e.g. ``cfmesh``)
    write_case()             the files it needs (system/*, constant/triSurface/*)
    mesh_plan()              the meshing commands, engine-neutral (see plan.py)
    validate()               cross-key checks only this engine can make

Adding an engine means adding one module and one entry here; the CLI, the script
writer, validation and the web UI all go through the registry.
"""

from __future__ import annotations

from typing import Any

MESHERS: tuple[str, ...] = ("cfmesh", "snappy")

#: Historical name kept for callers that imported it from here.
SUPPORTED_MESHERS = MESHERS


def resolve_mesher(cfg: dict[str, Any]) -> str:
    """Return the mesher key for a config.

    Accepts ``"mesher": "snappy"`` and the legacy ``{"type": "snappy"}`` form.
    """
    mesher = cfg.get("mesher", "cfmesh")
    if isinstance(mesher, dict):
        mesher = mesher.get("type", "cfmesh")
    return str(mesher).strip().lower()


def get_mesher(name: str) -> Any:
    """The mesher implementation for ``name`` (imported lazily, no cycles)."""
    key = str(name).strip().lower()
    if key == "cfmesh":
        from rapidfoam.meshers.cfmesh import CFMESH

        return CFMESH
    if key == "snappy":
        from rapidfoam.meshers.snappy import SNAPPY

        return SNAPPY
    raise ValueError(f"Unknown mesher '{name}' (expected one of {', '.join(MESHERS)})")


def mesher_for(cfg: dict[str, Any]) -> Any:
    """The mesher implementation selected by a resolved config."""
    return get_mesher(resolve_mesher(cfg))


__all__ = [
    "MESHERS",
    "SUPPORTED_MESHERS",
    "get_mesher",
    "mesher_for",
    "resolve_mesher",
]
