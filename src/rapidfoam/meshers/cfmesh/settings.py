"""cfMesh settings — the only place ``auto``/``'body'``/two-home defaults resolve.

The writer used to decide policy while rendering (it resolved ``optimise_layer:
"auto"``, looked ``ground_refine`` up in two dictionaries, and fell back from
``mesh_params.refinement_thickness`` to ``cfmesh.refinement_thickness``). All of
that now happens here, once, into a frozen :class:`CfMeshSettings`, so
:mod:`rapidfoam.meshers.cfmesh.mesh_dict` is a pure renderer and the CLI, the plan
and the docs all read the same resolved values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfoam.meshers.plan import resolve_parallel_meshing
from rapidfoam.meshers.sizing import Sizing, resolve_first_layer_height, resolve_sizing

#: Fidelities for which the layer-optimisation pass is skipped under "auto".
DRAFT_FIDELITIES = ("fast", "draft", "iterate")


@dataclass(frozen=True)
class Region:
    """One refinement box, with the cell size cfMesh needs (not the level)."""

    name: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    cell_size: float


@dataclass(frozen=True)
class CfMeshSettings:
    """Everything ``meshDict`` is rendered from."""

    sizing: Sizing
    stl_names: tuple[str, ...]
    patches: dict[str, str]
    regions: tuple[Region, ...]
    feature_angle: float
    boundary_cell_size: float
    ground_refine: bool
    ground_cell_size: float
    ground_patch: str
    ground_layers: bool
    refinement_thickness: float | None
    n_layers: int
    expansion_ratio: float
    first_layer_height: float
    optimise_layer: bool
    optimisation: dict[str, Any] = field(default_factory=dict)
    parallel_meshing: bool = False

    @property
    def surface_file(self) -> str:
        return "constant/triSurface/domain.fms"

    def local_refinements(self) -> list[tuple[str, float]]:
        """``(patch, cellSize)`` pairs for the localRefinement block."""
        surface = [(name, self.sizing.body_cell_size) for name in self.stl_names]
        if self.ground_refine:
            surface.append((self.ground_patch, self.ground_cell_size))
        return surface


def resolve_optimise_layer(value: Any, fidelity: str) -> bool:
    """Whether cfMesh runs its layer-optimisation pass.

    ``"auto"`` keeps it for report-quality meshes and skips it for fast/draft
    iteration, because optimisation plus normal smoothing is the costliest stage.
    """
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "1", "on"):
        return True
    if text in ("false", "no", "0", "off"):
        return False
    return str(fidelity).lower() not in DRAFT_FIDELITIES


def _positive(value: Any, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if number > 0 else fallback


def resolve_cfmesh_settings(cfg: dict[str, Any]) -> CfMeshSettings:
    """Resolve a case config into concrete cfMesh settings.

    Reads ``mesh_params`` (via :func:`resolve_sizing`), the ``cfmesh`` block, and
    ``layers``/``fidelity`` for the boundary-layer policy. Every ``"auto"``,
    alias and default is resolved here; nothing downstream needs the raw config.
    """
    mesh = cfg.get("mesh_params", {})
    engine = cfg.get("cfmesh", {})
    engine = engine if isinstance(engine, dict) else {}
    layers = cfg.get("layers", {})
    fidelity = str(cfg.get("fidelity", "standard"))

    sizing = resolve_sizing(mesh)

    regions = tuple(
        Region(
            name=str(region["name"]),
            minimum=tuple(float(v) for v in region["min"]),
            maximum=tuple(float(v) for v in region["max"]),
            cell_size=round(sizing.base_cell_size / (2 ** int(region.get("level", 2))), 6),
        )
        for region in mesh.get("refinement_regions", [])
    )

    patches = dict(cfg.get("patches", {}))
    ground_refine = bool(engine.get("ground_refine", False))
    if not cfg.get("flow", {}).get("ground", False):
        # No road patch in the mesh: nothing to refine or layer.
        ground_refine = False

    return CfMeshSettings(
        sizing=sizing,
        stl_names=tuple(cfg.get("stl_names", ())),
        patches=patches,
        regions=regions,
        feature_angle=float(engine.get("feature_angle", 45)),
        boundary_cell_size=_positive(
            engine.get("boundary_cell_size"), float(sizing.base_cell_size)
        ),
        ground_refine=ground_refine,
        ground_cell_size=_positive(
            engine.get("ground_cell_size"), round(sizing.base_cell_size / 2.0, 6)
        ),
        ground_patch=patches.get("ground", "ground"),
        ground_layers=bool(layers.get("ground_layers", False)) and cfg.get(
            "flow", {}).get("ground", False
        ),
        refinement_thickness=engine.get("refinement_thickness"),
        n_layers=int(layers.get("n_layers", 5)),
        expansion_ratio=float(layers.get("expansion_ratio", 1.2)),
        first_layer_height=round(
            resolve_first_layer_height(layers, float(sizing.body_cell_size)), 6
        ),
        optimise_layer=resolve_optimise_layer(engine.get("optimise_layer", "auto"), fidelity),
        optimisation=engine.get("optimisation", {}) if isinstance(
            engine.get("optimisation", {}), dict
        ) else {},
        parallel_meshing=resolve_parallel_meshing(
            engine.get("parallel_meshing", "auto"),
            cfg.get("parallel", {}).get("n_procs", 1),
        ),
    )


__all__ = [
    "DRAFT_FIDELITIES",
    "CfMeshSettings",
    "Region",
    "resolve_cfmesh_settings",
    "resolve_optimise_layer",
    # Re-exported from rapidfoam.meshers.plan: the MPI policy is shared.
    "resolve_parallel_meshing",
]
