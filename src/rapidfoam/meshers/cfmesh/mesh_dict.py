"""meshDict rendering — settings in, text out.

No policy here: every ``auto``, alias, default and fallback was resolved by
:func:`rapidfoam.meshers.cfmesh.settings.resolve_cfmesh_settings`, so this module
can be read as the cfMesh dictionary documentation it produces.
"""

from __future__ import annotations

from pathlib import Path

from rapidfoam.meshers.cfmesh.settings import CfMeshSettings
from rapidfoam.writers.base import FOOTER, foam_header

#: Boundary-role -> OpenFOAM patch type for the renameBoundary block.
PATCH_TYPES: dict[str, str] = {
    "inlet": "patch",
    "outlet": "patch",
    "ground": "wall",
    "walls": "patch",
    "symmetry": "symmetry",
}


def _local_refinement(name: str, cell: float, thickness: float | None) -> str:
    lines = [f"        {name}", "        {"]
    lines.append(f"            cellSize {round(cell, 6)};")
    if thickness:
        lines.append(f"            refinementThickness {float(thickness):.6g};")
    lines.append("        }")
    return "\n".join(lines)


def _object_refinement(region) -> str:
    cx = round((region.minimum[0] + region.maximum[0]) / 2.0, 4)
    cy = round((region.minimum[1] + region.maximum[1]) / 2.0, 4)
    cz = round((region.minimum[2] + region.maximum[2]) / 2.0, 4)
    lx = round(abs(region.maximum[0] - region.minimum[0]), 4)
    ly = round(abs(region.maximum[1] - region.minimum[1]), 4)
    lz = round(abs(region.maximum[2] - region.minimum[2]), 4)
    return f"""\
        {region.name}
        {{
            type box;
            centre ({cx} {cy} {cz});
            lengthX {lx};
            lengthY {ly};
            lengthZ {lz};
            cellSize {round(region.cell_size, 6)};
        }}"""


def _patch_layers(name: str, n_layers: int, expansion_ratio: float, first_layer: float) -> str:
    return f"""\
            {name}
            {{
                nLayers {n_layers};
                thicknessRatio {expansion_ratio};
                maxFirstLayerThickness {first_layer};
            }}"""


def _boundary_layers_block(settings: CfMeshSettings) -> str:
    if settings.n_layers <= 0:
        return ""

    optimisation = settings.optimisation
    if settings.optimise_layer:
        optimise_block = f"""
    optimiseLayer 1;

    optimisationParameters
    {{
        nSmoothNormals      {optimisation.get("nSmoothNormals", 3)};
        maxNumIterations    {optimisation.get("maxNumIterations", 2)};
        featureSizeFactor   {optimisation.get("featureSizeFactor", 0.4)};
        reCalculateNormals  {optimisation.get("reCalculateNormals", 1)};
        relThicknessTol     {optimisation.get("relThicknessTol", 0.1)};
    }}"""
    else:
        optimise_block = "\n    optimiseLayer 0;"

    patch_layer_lines = [
        _patch_layers(name, settings.n_layers, settings.expansion_ratio,
                      settings.first_layer_height)
        for name in settings.stl_names
    ]
    if settings.ground_layers:
        patch_layer_lines.append(
            _patch_layers(settings.ground_patch, settings.n_layers,
                          settings.expansion_ratio, settings.first_layer_height)
        )

    return f"""\
boundaryLayers
{{
    // nLayers 0 here => only the patches listed below are layered
    nLayers             0;
    thicknessRatio      {settings.expansion_ratio};
    maxFirstLayerThickness {settings.first_layer_height};{optimise_block}

    patchBoundaryLayers
    {{
{chr(10).join(patch_layer_lines)}
    }}
}}
"""


def _rename_boundary_lines(settings: CfMeshSettings) -> list[str]:
    lines: list[str] = []
    for role, patch_name in settings.patches.items():
        patch_type = PATCH_TYPES.get(role, "patch")
        lines.append(f"""\
        {patch_name}
        {{
            type {patch_type};
            newName {patch_name};
        }}""")
    for name in settings.stl_names:
        lines.append(f"""\
        {name}
        {{
            type wall;
            newName {name};
        }}""")
    return lines


def render_mesh_dict(settings: CfMeshSettings) -> str:
    """The ``system/meshDict`` text for resolved cfMesh settings."""
    sizing = settings.sizing
    local_ref_lines = [
        _local_refinement(name, cell, settings.refinement_thickness)
        for name, cell in settings.local_refinements()
    ]
    object_ref_lines = [_object_refinement(region) for region in settings.regions]

    content = f"""\
surfaceFile "{settings.surface_file}";

maxCellSize         {sizing.base_cell_size:.6g};
minCellSize         {sizing.min_cell_size:.6g};
boundaryCellSize    {settings.boundary_cell_size:.6g};

localRefinement
{{
{chr(10).join(local_ref_lines)}
}}

objectRefinements
{{
{chr(10).join(object_ref_lines)}
}}

{_boundary_layers_block(settings)}
renameBoundary
{{
    defaultType wall;
    newPatchNames
    {{
{chr(10).join(_rename_boundary_lines(settings))}
    }}
}}
"""
    return foam_header("meshDict") + content + FOOTER


def write_mesh_dict(settings: CfMeshSettings, case_dir: Path) -> None:
    """Write ``system/meshDict``."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "meshDict").write_text(render_mesh_dict(settings))


__all__ = ["PATCH_TYPES", "render_mesh_dict", "write_mesh_dict"]
