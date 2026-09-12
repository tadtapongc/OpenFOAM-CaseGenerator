"""Per-mesher profile files - the engine defaults a project can override.

RapidFOAM keeps the *physical* intent in the case config (flow, domain, outputs,
fidelity, mesh_params) and lets each engine ship a profile that a project can
override without editing the package:

    src/rapidfoam/mesher_profiles/cfmesh.json    shipped with the package
    src/rapidfoam/mesher_profiles/snappy.json    shipped with the package
    configs/meshers/cfmesh.json                  optional project-local override
    configs/meshers/snappy.json

Merge order (later wins):

    DEFAULT_CONFIG -> mesher profile -> case config
    -> case ``mesh_params_<mesher>`` block -> case ``overrides`` block

The profiles exist so a project can retune an engine once (a cluster with a slow
filesystem, a build without parallel meshing) instead of per case. Engine keys
themselves are declared in ``rapidfoam/meshers/<engine>/keys.py``; see
``docs/meshers.md`` for why the two engines must not share one dictionary.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rapidfoam.meshers import MESHERS, SUPPORTED_MESHERS

MESHER_PROFILES_DIR = Path(__file__).resolve().parent
PROJECT_PROFILES_REL = Path("configs") / "meshers"


def project_profile_path(mesher: str, project_dir: Path | str | None = None) -> Path:
    """Path of the optional project-local override for ``mesher``."""
    root = Path(project_dir) if project_dir is not None else Path.cwd()
    return root / PROJECT_PROFILES_REL / f"{str(mesher).lower()}.json"


def load_mesher_profile(mesher: str, project_dir: Path | str | None = None) -> dict[str, Any]:
    """Load the shipped profile for ``mesher``, overlaid with any project copy.

    Returns an empty dict for unsupported mesher names so that config loading
    stays tolerant and validation can report the error.
    """
    from rapidfoam.config import deep_merge  # local import - config imports this module

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
    "MESHERS",
    "MESHER_PROFILES_DIR",
    "PROJECT_PROFILES_REL",
    "SUPPORTED_MESHERS",
    "load_mesher_profile",
    "project_profile_path",
]
