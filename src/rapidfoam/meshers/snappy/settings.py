"""snappyHexMesh settings — the only place its defaults and derived numbers live.

The dictionary writers used to carry their own ``.get(key, default)`` fallbacks,
so the same number had two homes (``maxGlobalCells`` said 30M in the writer and
18M in the preset table, ``includedAngle`` said 150 in the writer and 140 in
``config.py``) and the automatic ``locationInMesh`` corner was computed while
rendering. All of that resolves here, once, into a frozen
:class:`SnappySettings`, which leaves :mod:`.block_mesh_dict`,
:mod:`.snappy_hex_mesh_dict` and :mod:`.surface_feature_extract_dict` as pure
renderers: settings in, text out.

Precedence: whatever the resolved config says wins (``config.py``'s
``DEFAULT_CONFIG`` sections, the ``snap``/``layers``/``mesh_quality``/
``feature_extract`` blocks of the case, and ``mesh_params`` already run through
:func:`rapidfoam.meshers.refinement.resolve_mesh_params`). The tables below are
what a *bare* config handed straight to the writer falls back to; they carry the
same numbers as the case defaults so the two cannot drift apart again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rapidfoam.geometry import (
    face_assignments,
    face_role,
    flow_axis_index_sign,
    up_axis_index,
)
from rapidfoam.meshers.plan import resolve_parallel_meshing
from rapidfoam.meshers.refinement import keys_for
from rapidfoam.meshers.sizing import Sizing, resolve_first_layer_fraction, resolve_sizing

#: ``snapControls`` (the same numbers as ``config.py``'s ``snap`` section).
SNAP_DEFAULTS: dict[str, Any] = {
    "nSmoothPatch": 5,
    "tolerance": 2.0,
    "nSolveIter": 200,
    "nRelaxIter": 8,
    "nFeatureSnapIter": 15,
    "implicitFeatureSnap": True,
    "explicitFeatureSnap": True,
    "multiRegionFeatureSnap": False,
}

#: ``addLayersControls`` keys that are not surface layer counts (``layers``).
LAYER_DEFAULTS: dict[str, Any] = {
    "expansion_ratio": 1.2,
    "min_thickness": 0.05,
    "nGrow": 0,
    "featureAngle": 170,
    "slipFeatureAngle": 30,
    "maxFaceThicknessRatio": 0.5,
    "nSmoothSurfaceNormals": 3,
    "nSmoothThickness": 10,
    "nSmoothNormals": 3,
    "nRelaxIter": 10,
    "nBufferCellsNoExtrude": 0,
    "nLayerIter": 50,
    "maxAlignedCells": 200_000,
    "minMedialAxisAngle": 90,
    "maxThicknessToMedialRatio": 0.3,
    "nMedialAxisIter": 10,
    "nSmoothDisplacement": 0,
    "detectExtrusionIsland": True,
    "nRelaxedIter": 20,
}

#: ``meshQualityControls``.
QUALITY_DEFAULTS: dict[str, Any] = {
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
}

#: The ``relaxed`` sub-dictionary snappy falls back to when a cell fails.
RELAXED_DEFAULTS: dict[str, Any] = {
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
}

#: ``surfaceFeatureExtractDict`` (140 degrees: real aero edges, no CAD seams).
FEATURE_DEFAULTS: dict[str, Any] = {
    "extractionMethod": "extractFromSurface",
    "includedAngle": 140,
}

#: ``castellatedMeshControls`` keys taken straight from the resolved
#: ``mesh_params``. Their defaults are declared once, in the shared
#: :data:`rapidfoam.meshers.refinement.MESH_PARAMS_KEYS` table, so they are read
#: from there instead of being restated here.
CASTELLATED_KEYS: tuple[str, ...] = (
    "maxLocalCells",
    "maxGlobalCells",
    "minRefinementCells",
    "nCellsBetweenLevels",
    "resolveFeatureAngle",
    "allowFreeStandingZoneFaces",
)

#: Knobs of the same block with no shared default: snappy's own value.
CASTELLATED_DEFAULTS: dict[str, Any] = {"maxLoadUnbalance": 0.25}

#: Layer count, and the key that adds the road patch to the layered surfaces.
LAYER_COUNT_DEFAULT = 5
GROUND_LAYER_KEY = "ground_layers"


@dataclass(frozen=True)
class RefinementBox:
    """One refinement region: a searchableBox refined to a snappy level."""

    name: str
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    level: int


@dataclass(frozen=True)
class SnappySettings:
    """Everything the three snappy dictionaries are rendered from."""

    sizing: Sizing
    stl_names: tuple[str, ...]
    #: ``"+x" -> patch name``, plus the role each patch plays.
    face_patches: dict[str, str]
    patch_roles: dict[str, str]
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    #: ``blockMesh`` divisions ``(nx ny nz)`` of the wind tunnel box.
    cells: tuple[int, int, int]
    surface_level: tuple[int, int]
    edge_level: int
    regions: tuple[RefinementBox, ...]
    distance_levels: tuple[tuple[float, int], ...]
    location_in_mesh: tuple[float, float, float]
    n_layers: int
    first_layer_fraction: float
    ground_patch: str
    ground_layers: bool
    parallel_meshing: bool
    castellated: dict[str, Any] = field(default_factory=dict)
    snap: dict[str, Any] = field(default_factory=dict)
    layers: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    relaxed: dict[str, Any] = field(default_factory=dict)
    feature_extract: dict[str, Any] = field(default_factory=dict)


def _merged(defaults: dict[str, Any], block: Any) -> dict[str, Any]:
    """``defaults`` overlaid with a config block (a non-object block is ignored)."""
    return {**defaults, **block} if isinstance(block, dict) else dict(defaults)


def resolve_cells(
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    cell_size: float,
) -> tuple[int, int, int]:
    """``blockMesh`` divisions for the box: one per base cell, at least one."""
    return tuple(
        max(1, round((maximum[i] - minimum[i]) / cell_size)) for i in range(3)
    )


def resolve_location_in_mesh(
    cfg: dict[str, Any],
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    face_patches: dict[str, str],
    patch_roles: dict[str, str],
) -> tuple[float, float, float]:
    """A point that is inside the fluid region.

    ``mesh_params.location_in_mesh`` (or ``locationInMesh``) wins. Otherwise the
    domain corner maximally far from the geometry: the model sits downstream, near
    the road and near the symmetry plane, so snappy gets the inlet side, the roof,
    and the wall opposite a symmetry plane (the lateral centre otherwise).
    """
    mesh = cfg.get("mesh_params", {})
    explicit = mesh.get("location_in_mesh", mesh.get("locationInMesh"))
    if explicit:
        return tuple(float(v) for v in explicit)

    loc = [0.0, 0.0, 0.0]
    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i not in (flow_idx, up_idx))
    extent = [maximum[i] - minimum[i] for i in range(3)]

    if flow_sign > 0:
        loc[flow_idx] = minimum[flow_idx] + extent[flow_idx] * 0.05
    else:
        loc[flow_idx] = maximum[flow_idx] - extent[flow_idx] * 0.05

    loc[up_idx] = maximum[up_idx] - extent[up_idx] * 0.05
    if patch_roles.get(face_patches.get(f"+{'xyz'[up_idx]}", "")) == "ground":
        loc[up_idx] = minimum[up_idx] + extent[up_idx] * 0.05

    sym_dir = next(
        (direction for direction, patch in face_patches.items()
         if patch_roles.get(patch) == "symmetry"),
        None,
    )
    if sym_dir and sym_dir.endswith("xyz"[lateral_idx]):
        if sym_dir.startswith("-"):
            loc[lateral_idx] = maximum[lateral_idx] - extent[lateral_idx] * 0.05
        else:
            loc[lateral_idx] = minimum[lateral_idx] + extent[lateral_idx] * 0.05
    else:
        loc[lateral_idx] = (minimum[lateral_idx] + maximum[lateral_idx]) / 2

    return (loc[0], loc[1], loc[2])


def resolve_snappy_settings(cfg: dict[str, Any]) -> SnappySettings:
    """Resolve a case config into concrete snappyHexMesh settings.

    Reads ``domain_box``, ``mesh_params`` (via :func:`resolve_sizing`), the
    ``snap``/``layers``/``mesh_quality``/``feature_extract`` blocks, ``patches``
    and ``parallel``. Every default, the block divisions, the ``locationInMesh``
    point and the relative first-layer thickness are decided here; nothing
    downstream needs the raw config.
    """
    mesh = cfg.get("mesh_params", {})
    box = cfg.get("domain_box", {})
    patches = cfg.get("patches", {})
    patches = patches if isinstance(patches, dict) else {}

    minimum = tuple(float(v) for v in box["min"])
    maximum = tuple(float(v) for v in box["max"])

    sizing = resolve_sizing(mesh)
    face_patches = dict(face_assignments(cfg))
    patch_roles = {
        name: face_role(cfg, name) for name in dict.fromkeys(face_patches.values())
    }

    layers = _merged(LAYER_DEFAULTS, cfg.get("layers"))
    quality = _merged(QUALITY_DEFAULTS, cfg.get("mesh_quality"))
    relaxed = _merged(
        RELAXED_DEFAULTS,
        quality.get("relaxed") if isinstance(quality.get("relaxed"), dict) else None,
    )

    # The caps and angles are declared once in the shared `mesh_params` table;
    # read the defaults from there, then let the case override them.
    castellated = dict(CASTELLATED_DEFAULTS)
    specs = keys_for("snappy")
    for key in CASTELLATED_KEYS:
        spec = specs.get(key)
        if spec is not None and spec.default is not None:
            castellated[key] = spec.default
    for key in (*CASTELLATED_KEYS, "maxLoadUnbalance"):
        if key in mesh:
            castellated[key] = mesh[key]

    return SnappySettings(
        sizing=sizing,
        stl_names=tuple(cfg.get("stl_names", ())),
        face_patches=face_patches,
        patch_roles=patch_roles,
        minimum=minimum,
        maximum=maximum,
        cells=resolve_cells(minimum, maximum, sizing.base_cell_size),
        surface_level=tuple(int(v) for v in mesh["surface_level"]),
        edge_level=int(mesh["edge_level"]),
        regions=tuple(
            RefinementBox(
                name=str(region["name"]),
                minimum=tuple(float(v) for v in region["min"]),
                maximum=tuple(float(v) for v in region["max"]),
                level=int(region.get("level", 2)),
            )
            for region in mesh.get("refinement_regions", [])
        ),
        distance_levels=tuple(
            (float(distance), int(level))
            for distance, level in mesh.get("distance_levels", [])
        ),
        location_in_mesh=resolve_location_in_mesh(
            cfg, minimum, maximum, face_patches, patch_roles
        ),
        n_layers=int(layers.get("n_layers", LAYER_COUNT_DEFAULT)),
        first_layer_fraction=round(
            resolve_first_layer_fraction(layers, sizing.body_cell_size), 4
        ),
        ground_patch=str(patches.get("ground", "ground")),
        ground_layers=bool(layers.get(GROUND_LAYER_KEY, False)),
        parallel_meshing=resolve_parallel_meshing(
            "auto", cfg.get("parallel", {}).get("n_procs", 1)
        ),
        castellated=castellated,
        snap=_merged(SNAP_DEFAULTS, cfg.get("snap")),
        layers=layers,
        quality=quality,
        relaxed=relaxed,
        feature_extract=_merged(FEATURE_DEFAULTS, cfg.get("feature_extract")),
    )


__all__ = [
    "CASTELLATED_DEFAULTS",
    "CASTELLATED_KEYS",
    "FEATURE_DEFAULTS",
    "GROUND_LAYER_KEY",
    "LAYER_COUNT_DEFAULT",
    "LAYER_DEFAULTS",
    "QUALITY_DEFAULTS",
    "RELAXED_DEFAULTS",
    "SNAP_DEFAULTS",
    "RefinementBox",
    "SnappySettings",
    "resolve_cells",
    "resolve_location_in_mesh",
    "resolve_snappy_settings",
]
