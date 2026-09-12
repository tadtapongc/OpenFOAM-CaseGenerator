"""Cell budget — where a mesh's cells go, priced before the mesher runs.

snappyHexMesh is the only engine with a cap (``maxGlobalCells``), and when the cap
is reached it stops refining: whatever did not make it stays coarse, the snap and
layer stages get squeezed, and the mesh comes out fine in one place and coarse in
another. That failure is invisible until the log is read, and it is caused by the
*distribution* of refinement, not by the surface size.

This module prices that distribution. Every refinement region and distance shell is
estimated as the octree cells snappy asks for, ``cells ~ volume / cell_size**3``
with ``cell_size = base_cell_size / 2**level``, so the CLI can print where the cells
go and say so *before* a run instead of after it.

Inputs are the resolved ``mesh_params`` and the domain box, i.e. the same numbers the
dictionaries are rendered from. The estimates are order-of-magnitude: the octree
mostly fills a region with full cells, and ``nCellsBetweenLevels`` adds buffer cells
that are not priced here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rapidfoam.meshers import get_mesher, resolve_mesher
from rapidfoam.meshers.presets import preset_for
from rapidfoam.meshers.sizing import Sizing, resolve_sizing

#: Warn when the estimate reaches this much of the cap (the last regions in are the
#: ones snappy drops first when it runs out of budget).
CAP_WARN_SHARE = 0.8

#: A region this share of the total is worth naming: making it one level coarser is
#: 8x cheaper.
DOMINANT_SHARE = 0.6


@dataclass(frozen=True)
class RegionBudget:
    """One priced refinement region (a box, a distance shell or the background)."""

    label: str
    level: int | None
    cell_size: float
    cells: int


@dataclass(frozen=True)
class CellBudget:
    """The estimated cell count, split by region, for one resolved case."""

    engine: str
    base_cell_size: float
    regions: tuple[RegionBudget, ...]
    total_cells: int
    #: ``maxGlobalCells`` for an engine that has one (snappy), otherwise ``None``.
    cap: int | None
    #: The preset's target cell count, used for engines without a cap.
    target: int | None = None

    @property
    def enforced_cap(self) -> int | None:
        """The cap that actually stops meshing, if the engine has one."""
        return self.cap if self.cap and self.cap > 0 else None

    @property
    def share_of_cap(self) -> float | None:
        cap = self.enforced_cap
        return None if cap is None else self.total_cells / cap

    @property
    def dominant(self) -> RegionBudget | None:
        """The region asking for the most cells."""
        return max(self.regions, key=lambda item: item.cells, default=None)

    def region(self, label: str) -> RegionBudget | None:
        """The priced region with this label, if it was priced."""
        for item in self.regions:
            if item.label == label:
                return item
        return None

    def warnings(self) -> list[str]:
        """What the estimate says about cell distribution, worst first."""
        messages: list[str] = []
        cap = self.enforced_cap
        dominant = self.dominant
        if cap is not None:
            share = self.share_of_cap or 0.0
            if share > 1.0:
                messages.append(
                    f"the regions ask for ~{self.total_cells:,} cells, "
                    f"{share * 100:.0f}% of mesh_params.maxGlobalCells ({cap:,}): snappy "
                    "stops refining once the cap is hit, so the last regions and the "
                    "snap/layer stages come out under-resolved"
                )
            elif share >= CAP_WARN_SHARE:
                messages.append(
                    f"the regions ask for ~{self.total_cells:,} cells, "
                    f"{share * 100:.0f}% of mesh_params.maxGlobalCells ({cap:,}); little "
                    "headroom is left for the snap and layer stages"
                )
        elif self.target and self.total_cells > 2 * self.target:
            messages.append(
                f"the regions ask for ~{self.total_cells:,} cells, about "
                f"{self.total_cells / self.target:.1f}x the preset's target "
                f"({self.target:,}); {self.engine} has no cell cap, so this is run time, "
                "disk and RAM rather than a hard stop"
            )
        if dominant is not None and dominant.cells > DOMINANT_SHARE * self.total_cells:
            share = dominant.cells / self.total_cells
            hint = ""
            if dominant.level is not None and dominant.level > 0:
                hint = (f"; level {dominant.level} -> {dominant.level - 1} makes that "
                        "region 8x cheaper")
            messages.append(
                f"'{dominant.label}' alone asks for {share * 100:.0f}% of the estimate "
                f"({dominant.cells:,} cells){hint}"
            )
        return messages

    def report_lines(self) -> list[str]:
        """Printable block: one line per region, then the total against the cap."""
        cap = self.enforced_cap
        header = "  Cell budget (estimate, cells = volume / cell size^3"
        header += f", cap {cap:,} cells):" if cap is not None else "):"
        lines = [header,
                 f"    {'region':<32}{'level':>6}{'cell size':>12}{'cells':>14}{'share':>8}"]
        for item in self.regions:
            level = "-" if item.level is None else str(item.level)
            share = 100.0 * item.cells / self.total_cells if self.total_cells else 0.0
            lines.append(
                f"    {item.label[:32]:<32}{level:>6}{_millimetres(item.cell_size):>12}"
                f"{item.cells:>14,}{share:>7.0f}%"
            )
        total = f"    {'estimated total':<32}{'':>6}{'':>12}{self.total_cells:>14,}"
        if cap is not None:
            total += f"{100.0 * self.total_cells / cap:>7.0f}%"
        lines.append(total)
        if cap is None and self.target:
            lines.append(f"    {'preset target':<32}{'':>6}{'':>12}{self.target:>14,}")
        return lines

    def as_dict(self) -> dict[str, Any]:
        """JSON-ready form for the web API."""
        return {
            "engine": self.engine,
            "base_cell_size": self.base_cell_size,
            "total_cells": self.total_cells,
            "cap": self.cap,
            "target": self.target,
            "regions": [
                {"label": item.label, "level": item.level,
                 "cell_size": item.cell_size, "cells": item.cells}
                for item in self.regions
            ],
            "warnings": self.warnings(),
        }


def _millimetres(metres: float) -> str:
    """A cell size in millimetres, with enough digits for a fine TE box."""
    for digits in (1, 2, 3, 4):
        if metres * 1000 >= 10 ** -(digits - 1):
            return f"{metres * 1000:.{digits}f} mm"
    return f"{metres * 1000:.2e} mm"


def _box_volume(region: dict[str, Any]) -> float:
    try:
        lo = [float(value) for value in region["min"]]
        hi = [float(value) for value in region["max"]]
    except (KeyError, TypeError, ValueError):
        return 0.0
    volume = 1.0
    for i in range(3):
        volume *= max(0.0, hi[i] - lo[i])
    return volume


def _background_cells(cfg: dict[str, Any], base_cell_size: float) -> int | None:
    """Cells in the domain box at the base cell size (blockMesh / cfMesh start)."""
    domain = cfg.get("domain_box")
    if not (isinstance(domain, dict) and "min" in domain and "max" in domain):
        return None
    cells = 1
    for i in range(3):
        try:
            extent = float(domain["max"][i]) - float(domain["min"][i])
        except (TypeError, ValueError):
            return None
        cells *= max(1, round(extent / base_cell_size))
    return cells


def _snappy_regions(
    mesh: dict[str, Any], sizing: Sizing, surface_area: float | None
) -> list[RegionBudget]:
    """snappy's surface refinement: the distance shells, one row per shell."""
    if not surface_area:
        return []
    base = float(sizing.base_cell_size)
    items: list[RegionBudget] = []
    previous = 0.0
    for distance, level in mesh.get("distance_levels", []) or []:
        band = max(0.0, float(distance) - previous)
        previous = float(distance)
        cell = base / (2 ** int(level))
        items.append(RegionBudget(
            f"surface shell {float(distance) * 1000:.0f} mm",
            int(level),
            cell,
            round(surface_area * band / cell ** 3),
        ))
    return items


def _cfmesh_surface_regions(sizing: Sizing, surface_area: float | None) -> list[RegionBudget]:
    """cfMesh's surface refinement: a two-cell-thick band at the body cell.

    cfMesh refines the octree by curvature and proximity down to ``minCellSize``
    rather than with distance shells, so the band width is an approximation of what
    ``localRefinement`` costs.
    """
    if not surface_area:
        return []
    body = float(sizing.body_cell_size)
    return [RegionBudget("surface (localRefinement)", sizing.body_level, body,
                         round(2.0 * surface_area / body ** 2))]


def estimate_cell_budget(cfg: dict[str, Any], *, surface_area: float | None = None,
                         cap: int | None = None) -> CellBudget:
    """Price a resolved case config's refinement into an estimated cell budget.

    Args:
        cfg: A config whose ``mesh_params`` came from
            :func:`rapidfoam.meshers.refinement.resolve_mesh_params` (and whose
            ``domain_box`` is resolved).
        surface_area: Total STL area in m2, from
            :func:`rapidfoam.stl_utils.stl_surface_area`; the distance shells need
            it. Omitted, only the boxes and the background are priced.
        cap: Override the engine's cap (mainly for tests).

    Returns:
        A :class:`CellBudget` with one entry per priced region.
    """
    mesh = cfg.get("mesh_params", {}) or {}
    engine = resolve_mesher(cfg)
    mesher = get_mesher(engine)
    sizing = resolve_sizing(mesh)
    base = float(sizing.base_cell_size)

    items: list[RegionBudget] = []
    background = _background_cells(cfg, base)
    if background:
        label = ("background (maxCellSize)" if engine == "cfmesh"
                 else "background (blockMesh)")
        items.append(RegionBudget(label, None, base, background))

    if engine == "snappy":
        items += _snappy_regions(mesh, sizing, surface_area)
    else:
        items += _cfmesh_surface_regions(sizing, surface_area)

    for region in mesh.get("refinement_regions", []) or []:
        level = int(region.get("level", 2))
        cell = base / (2 ** level)
        items.append(RegionBudget(str(region.get("name", "region")), level, cell,
                                  round(_box_volume(region) / cell ** 3)))

    if cap is None and mesher.enforces_cell_budget:
        cap = int(mesh.get("maxGlobalCells", 0) or 0) or None
    target = preset_for(cfg.get("fidelity", "standard")).get("n_cells_target")
    return CellBudget(
        engine=engine,
        base_cell_size=base,
        regions=tuple(items),
        total_cells=sum(item.cells for item in items),
        cap=cap,
        target=int(target) if target else None,
    )


def budget_from_case(cfg: dict[str, Any], stl_dir: Any) -> CellBudget | None:
    """Resolve a case's STLs and mesh params, then estimate its budget.

    For callers that hold a config but no geometry (the web UI's validation step).
    Returns ``None`` when no STL can be read, so callers skip silently.

    Args:
        cfg: A resolved case config (``stl_files``, flow, fidelity, mesh_params).
        stl_dir: Directory the ``stl_files`` entries live in.
    """
    from rapidfoam.config import find_stl
    from rapidfoam.geometry import compute_domain_box
    from rapidfoam.meshers.refinement import resolve_mesh_params
    from rapidfoam.stl_utils import stl_info, stl_surface_area

    paths = []
    for name in cfg.get("stl_files", []) or []:
        path = find_stl(stl_dir, str(name))
        if path is not None:
            paths.append(path)
    if not paths:
        return None

    combined = cfg.get("combined_bounds")
    if combined is None:
        all_min = [float("inf")] * 3
        all_max = [float("-inf")] * 3
        for path in paths:
            _name, _triangles, bounds = stl_info(path)
            for i in range(3):
                all_min[i] = min(all_min[i], bounds[0][i])
                all_max[i] = max(all_max[i], bounds[1][i])
        if all_min[0] == float("inf"):
            return None
        combined = (tuple(all_min), tuple(all_max))

    case = dict(cfg)
    case["stl_names"] = [path.stem for path in paths]
    if not isinstance(case.get("domain_box"), dict):
        case["domain_box"] = compute_domain_box(case, combined)
    case["mesh_params"] = resolve_mesh_params(case, combined)

    try:
        area = sum(stl_surface_area(path) for path in paths)
    except (OSError, ValueError):
        area = None
    return estimate_cell_budget(case, surface_area=area)


__all__ = [
    "CAP_WARN_SHARE",
    "DOMINANT_SHARE",
    "CellBudget",
    "RegionBudget",
    "budget_from_case",
    "estimate_cell_budget",
]

