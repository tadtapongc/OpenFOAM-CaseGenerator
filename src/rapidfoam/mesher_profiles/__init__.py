"""Mesher-native profile files (split configuration).

RapidFOAM keeps the *physical* intent in the case config (flow, domain, outputs,
force references, fidelity, optional ``mesh_params``) and the *engine-specific*
knobs in one tracked profile per mesher:

    src/rapidfoam/mesher_profiles/cfmesh.json    shipped with the package
    src/rapidfoam/mesher_profiles/snappy.json    shipped with the package
    configs/meshers/cfmesh.json                  optional project-local override
    configs/meshers/snappy.json

Merge order (later wins):

    DEFAULT_CONFIG -> mesher profile -> case config
    -> case ``mesh_params_<mesher>`` block -> case ``overrides`` block

Why split: the two meshers do not mean the same thing by the same key.
snappy counts *relative* levels (``level 4`` == ``base_cell_size / 2**4``),
cfMesh takes *absolute* cell sizes in metres and refines feature edges one
level finer on its own. Feeding one dictionary to both writers is what made the
same config produce 449 k cells with snappy and 4.4 M cells with cfMesh; the
profile is where each engine's real semantics are declared, while the case
config keeps stating intent once.

The same trap hides inside a single key name: cfMesh's ``minCellSize`` is a
*global* refinement floor (curvature and proximity refinement stops there on
every surface), while snappy's ``edge_level`` only refines the cells touching
the extracted feature edges. The cfMesh profile therefore floors it at the body
cell (``min_cell_size: "body"``); the edge cell over-refined every surface and
was worth ~8x the cells.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MESHER_PROFILES_DIR = Path(__file__).resolve().parent
PROJECT_PROFILES_REL = Path("configs") / "meshers"
SUPPORTED_MESHERS: tuple[str, ...] = ("cfmesh", "snappy")


def resolve_mesher(cfg: dict[str, Any]) -> str:
    """Return the mesher key for a config as a lowercase string.

    Accepts both ``"mesher": "snappy"`` and the legacy
    ``"mesher": {"type": "snappy"}`` form.
    """
    mesher = cfg.get("mesher", "cfmesh")
    if isinstance(mesher, dict):
        mesher = mesher.get("type", "cfmesh")
    return str(mesher).strip().lower()


def project_profile_path(mesher: str, project_dir: Path | str | None = None) -> Path:
    """Path of the optional project-local override for ``mesher``."""
    root = Path(project_dir) if project_dir is not None else Path.cwd()
    return root / PROJECT_PROFILES_REL / f"{str(mesher).lower()}.json"


def load_mesher_profile(mesher: str, project_dir: Path | str | None = None) -> dict[str, Any]:
    """Load the shipped profile for ``mesher``, overlaid with any project copy.

    Returns an empty dict for unsupported mesher names so that config loading
    stays tolerant and validation can report the error.
    """
    from rapidfoam.config import deep_merge  # local import — config imports this module

    key = str(mesher).lower()
    if key not in SUPPORTED_MESHERS:
        return {}

    merged: dict[str, Any] = {}
    for path in (MESHER_PROFILES_DIR / f"{key}.json", project_profile_path(key, project_dir)):
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid mesher profile '{path}': {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Mesher profile must be a JSON object: {path}")
        merged = deep_merge(merged, data)
    return merged


__all__ = [
    "MESHER_PROFILES_DIR",
    "PROJECT_PROFILES_REL",
    "SUPPORTED_MESHERS",
    "load_mesher_profile",
    "project_profile_path",
    "resolve_mesher",
]
