"""cfMesh (cartesianMesh) dictionary and geometry writers.

Generates:
  - constant/triSurface/domain.stl (Combined wind tunnel bounding box + CAD geometry)
  - system/meshDict (cfMesh configuration for cartesianMesh)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rapidfoam.geometry import (
    face_assignments,
    resolve_cell_sizes,
    resolve_first_layer_height,
)
from rapidfoam.writers.base import FOOTER, foam_header


def write_box_stl_faces(box_min: list[float], box_max: list[float], face_map: dict[str, str]) -> str:
    """Generate ASCII STL representations of the 6 outer bounding box faces.

    Each face consists of 2 triangles with inward-facing surface normals
    (pointing into the fluid domain) and wrapped in a `solid <patch_name>` block.
    """
    x0, y0, z0 = box_min
    x1, y1, z1 = box_max

    # 8 box vertices
    v = [
        (x0, y0, z0),  # 0
        (x1, y0, z0),  # 1
        (x1, y1, z0),  # 2
        (x0, y1, z0),  # 3
        (x0, y0, z1),  # 4
        (x1, y0, z1),  # 5
        (x1, y1, z1),  # 6
        (x0, y1, z1),  # 7
    ]

    # Face definitions with inward-pointing normals: (normal, (v_a, v_b, v_c), (v_d, v_e, v_f))
    faces_spec = {
        "-x": ((1.0, 0.0, 0.0), (v[0], v[3], v[7]), (v[0], v[7], v[4])),
        "+x": ((-1.0, 0.0, 0.0), (v[1], v[5], v[6]), (v[1], v[6], v[2])),
        "-y": ((0.0, 1.0, 0.0), (v[0], v[4], v[5]), (v[0], v[5], v[1])),
        "+y": ((0.0, -1.0, 0.0), (v[2], v[6], v[7]), (v[2], v[7], v[3])),
        "-z": ((0.0, 0.0, 1.0), (v[0], v[1], v[2]), (v[0], v[2], v[3])),
        "+z": ((0.0, 0.0, -1.0), (v[4], v[7], v[6]), (v[4], v[6], v[5])),
    }

    blocks: list[str] = []
    for dir_key, (norm, tri1, tri2) in faces_spec.items():
        patch_name = face_map.get(dir_key, "farField")
        block = [f"solid {patch_name}"]
        for tri in (tri1, tri2):
            block.append(f"  facet normal {norm[0]:.6e} {norm[1]:.6e} {norm[2]:.6e}")
            block.append("    outer loop")
            block.append(f"      vertex {tri[0][0]:.6e} {tri[0][1]:.6e} {tri[0][2]:.6e}")
            block.append(f"      vertex {tri[1][0]:.6e} {tri[1][1]:.6e} {tri[1][2]:.6e}")
            block.append(f"      vertex {tri[2][0]:.6e} {tri[2][1]:.6e} {tri[2][2]:.6e}")
            block.append("    endloop")
            block.append("  endfacet")
        block.append(f"endsolid {patch_name}")
        blocks.append("\n".join(block))

    return "\n".join(blocks) + "\n"


def generate_domain_stl(
    cfg: dict[str, Any],
    case_dir: Path,
    stl_pairs: list[tuple[str, Path]],
) -> Path:
    """Generate combined domain.stl containing outer wind tunnel box and CAD surfaces.

    The outer wind tunnel box faces are written with inward-facing normals,
    while inner CAD geometry surfaces retain outward-facing normals.
    This concatenates surfaces; it does not clip CAD, repair intersections,
    or certify a closed manifold. Boundary intersections require CAD preparation
    and verification with the target cfMesh installation.
    """
    tri_dir = case_dir / "constant" / "triSurface"
    tri_dir.mkdir(parents=True, exist_ok=True)
    domain_stl_path = tri_dir / "domain.stl"

    box = cfg["domain_box"]
    faces = face_assignments(cfg)

    # 1. Write outer wind tunnel box faces
    box_stl_content = write_box_stl_faces(box["min"], box["max"], faces)

    with open(domain_stl_path, "w", encoding="utf-8", newline="\n") as fout:
        fout.write(box_stl_content)

        # 2. Append each CAD STL with solid <name> ... endsolid <name>
        for stem, path in stl_pairs:
            header_written = False
            with open(path, "r", encoding="utf-8", errors="replace") as fin:
                for line in fin:
                    stripped = line.strip()
                    if not header_written and stripped.startswith("solid"):
                        fout.write(f"solid {stem}\n")
                        header_written = True
                    elif stripped.startswith("endsolid"):
                        fout.write(f"endsolid {stem}\n")
                    else:
                        fout.write(line)

    return domain_stl_path


def _resolve_optimise_layer(cfmesh_cfg: dict[str, Any], fidelity: str) -> bool:
    """Whether cfMesh runs its layer optimisation pass.

    The optimisation pass (plus normal smoothing) is the most expensive cfMesh
    stage, so `optimise_layer: "auto"` keeps it for report-quality meshes
    (standard/fine) and skips it for fast/draft iteration.
    """
    value = cfmesh_cfg.get("optimise_layer", "auto")
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return str(fidelity).lower() not in ("fast", "draft", "iterate")


def write_mesh_dict(cfg: dict[str, Any], case_dir: Path) -> None:
    """Generate system/meshDict for cfMesh (cartesianMesh).

    Cell sizes come from `resolve_cell_sizes`, so the body refinement now means
    the same thing as in the snappy writer: body cells use ``surface_level[0]``
    (the finer level is only used for the feature-edge floor), ``minCellSize``
    is the feature-edge cell instead of a sub-millimetre sliver, and the ground
    plane is only refined when `cfmesh.ground_refine` asks for it.
    """
    mesh = cfg["mesh_params"]
    stl_names = cfg["stl_names"]
    patches = cfg["patches"]
    layers = cfg.get("layers", {})
    fidelity = str(cfg.get("fidelity", "standard")).lower()
    cfmesh_cfg = cfg.get("cfmesh", {}) if isinstance(cfg.get("cfmesh", {}), dict) else {}
    flow = cfg.get("flow", {})

    sizes = resolve_cell_sizes(mesh)
    base_cell = sizes["base"]
    body_cell = sizes["body"]
    min_cell = sizes["min"]
    refinement_thickness = mesh.get("refinement_thickness", cfmesh_cfg.get("refinement_thickness"))

    # Default outer boundary cell size: keep wind tunnel walls coarse at base_cell
    boundary_cell = float(mesh.get("boundary_cell_size", base_cell))

    def _local_ref(name: str, cell: float) -> str:
        lines = [f"        {name}", "        {"]
        lines.append(f"            cellSize {round(cell, 6)};")
        if refinement_thickness:
            lines.append(f"            refinementThickness {float(refinement_thickness):.6g};")
        lines.append("        }")
        return "\n".join(lines)

    # Local refinement for vehicle surfaces. cfMesh refines cells cut by feature
    # edges one level finer on its own (body/2), which is where edge_level lands.
    local_ref_lines = [_local_ref(name, body_cell) for name in stl_names]

    # Ground refinement is opt-in so cfMesh matches snappy, which never refines
    # the road plane (refining the whole road also forced a wide transition
    # volume under the car).
    ground_refine = bool(mesh.get("ground_refine", cfmesh_cfg.get("ground_refine", False)))
    if flow.get("ground", False) and ground_refine:
        ground_patch = patches.get("ground", "ground")
        ground_cell = float(mesh.get("ground_cell_size", round(base_cell / 2.0, 6)))
        local_ref_lines.append(_local_ref(ground_patch, ground_cell))

    # Refinement regions (wake boxes)
    regions = mesh.get("refinement_regions", [])
    object_ref_lines = []
    for r in regions:
        rmin = r["min"]
        rmax = r["max"]
        cx = round((rmin[0] + rmax[0]) / 2.0, 4)
        cy = round((rmin[1] + rmax[1]) / 2.0, 4)
        cz = round((rmin[2] + rmax[2]) / 2.0, 4)
        lx = round(abs(rmax[0] - rmin[0]), 4)
        ly = round(abs(rmax[1] - rmin[1]), 4)
        lz = round(abs(rmax[2] - rmin[2]), 4)
        reg_level = r.get("level", 2)
        reg_cell = round(base_cell / (2 ** reg_level), 6)

        object_ref_lines.append(f"""\
        {r["name"]}
        {{
            type box;
            centre ({cx} {cy} {cz});
            lengthX {lx};
            lengthY {ly};
            lengthZ {lz};
            cellSize {reg_cell};
        }}""")

    # Boundary layers ------------------------------------------------------
    n_layers = int(layers.get("n_layers", 5))
    expansion_ratio = layers.get("expansion_ratio", 1.2)
    # Absolute first-layer height: relative mode = first_layer_thickness x body
    # cell (snappy's convention), absolute mode = layers.first_layer_height.
    # cfMesh treats it as an upper bound, so a coarser body cell — not a bigger
    # number here — is what actually raises y+ into the wall-function range.
    first_layer_thickness = round(resolve_first_layer_height(layers, body_cell), 6)

    # 'patch_only' (default) writes nLayers 0 at the top level, so only the
    # patches listed in patchBoundaryLayers are layered: the road plane stays
    # unlayered unless layers.ground_layers is true. 'global' restores the
    # legacy behaviour that layered every patch, the ground included.
    layer_mode = str(cfmesh_cfg.get("layer_mode", "patch_only")).strip().lower()
    header_n_layers = n_layers if layer_mode == "global" else 0
    ground_patch_name = patches.get("ground", "ground")

    def _patch_layers(name: str) -> str:
        return f"""\
            {name}
            {{
                nLayers {n_layers};
                thicknessRatio {expansion_ratio};
                maxFirstLayerThickness {first_layer_thickness};
            }}"""

    patch_layer_lines = [_patch_layers(name) for name in stl_names]
    if layers.get("ground_layers", False):
        patch_layer_lines.append(_patch_layers(ground_patch_name))

    # Rename boundary block
    PATCH_TYPES = {
        "inlet": "patch",
        "outlet": "patch",
        "ground": "wall",
        "walls": "patch",
        "symmetry": "symmetry",
    }
    rename_lines = []
    for role, pname in patches.items():
        ptype = PATCH_TYPES.get(role, "patch")
        rename_lines.append(f"""\
        {pname}
        {{
            type {ptype};
            newName {pname};
        }}""")
    for name in stl_names:
        rename_lines.append(f"""\
        {name}
        {{
            type wall;
            newName {name};
        }}""")

    boundary_layers_block = ""
    if n_layers > 0:
        optimisation = cfmesh_cfg.get("optimisation", {})
        optimisation = optimisation if isinstance(optimisation, dict) else {}
        if _resolve_optimise_layer(cfmesh_cfg, fidelity):
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

        layer_comment = (
            "// nLayers 0 here => only the patches listed below are layered"
            if header_n_layers == 0
            else "// nLayers applies to every patch; entries below override it"
        )

        boundary_layers_block = f"""\
boundaryLayers
{{
    {layer_comment}
    nLayers             {header_n_layers};
    thicknessRatio      {expansion_ratio};
    maxFirstLayerThickness {first_layer_thickness};{optimise_block}

    patchBoundaryLayers
    {{
{chr(10).join(patch_layer_lines)}
    }}
}}
"""

    content = f"""\
surfaceFile "constant/triSurface/domain.fms";

maxCellSize         {base_cell:.6g};
minCellSize         {min_cell:.6g};
boundaryCellSize    {boundary_cell:.6g};

localRefinement
{{
{chr(10).join(local_ref_lines)}
}}

objectRefinements
{{
{chr(10).join(object_ref_lines)}
}}

{boundary_layers_block}
renameBoundary
{{
    defaultType wall;
    newPatchNames
    {{
{chr(10).join(rename_lines)}
    }}
}}
"""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "meshDict").write_text(foam_header("meshDict") + content + FOOTER)
