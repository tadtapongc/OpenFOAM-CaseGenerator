"""cfMesh (cartesianMesh) dictionary and geometry writers.

Generates:
  - constant/triSurface/domain.stl (Combined wind tunnel bounding box + CAD geometry)
  - system/meshDict (cfMesh configuration for cartesianMesh)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rapidfoam.geometry import face_assignments, face_role
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


def write_mesh_dict(cfg: dict[str, Any], case_dir: Path) -> None:
    """Generate system/meshDict for cfMesh (cartesianMesh)."""
    mesh = cfg["mesh_params"]
    stl_names = cfg["stl_names"]
    patches = cfg["patches"]
    layers = cfg.get("layers", {})
    fidelity = cfg.get("fidelity", "standard")

    base_cell = float(mesh.get("base_cell_size", 0.10))
    surface_level = mesh.get("surface_level", [4, 5])
    edge_level = mesh.get("edge_level", 6)

    # Calculate absolute cell sizes from levels
    surf_cell_coarse = round(base_cell / (2 ** surface_level[0]), 6)
    surf_cell_fine = round(base_cell / (2 ** surface_level[1]), 6)
    edge_cell = round(base_cell / (2 ** edge_level), 6)

    min_cell = min(edge_cell, surf_cell_fine)
    # Default outer boundary cell size: keep wind tunnel walls coarse at base_cell
    boundary_cell = float(mesh.get("boundary_cell_size", base_cell))

    # Local refinement for vehicle surfaces
    local_ref_lines = []
    for name in stl_names:
        local_ref_lines.append(f"""\
        {name}
        {{
            cellSize {surf_cell_fine};
        }}""")

    # Ground refinement: if ground vehicle (FSAE / auto), refine road underneath
    flow = cfg.get("flow", {})
    if flow.get("ground", False):
        ground_patch = patches.get("ground", "ground")
        ground_cell = float(mesh.get("ground_cell_size", round(base_cell / 2.0, 6)))
        local_ref_lines.append(f"""\
        {ground_patch}
        {{
            cellSize {ground_cell};
        }}""")

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

    # Boundary layers
    n_layers = layers.get("n_layers", 5)
    expansion_ratio = layers.get("expansion_ratio", 1.2)
    first_layer_ratio = layers.get("first_layer_thickness", 0.3)
    # Estimate first layer thickness in meters from surface fine cell
    first_layer_thickness = round(surf_cell_fine * first_layer_ratio, 6)

    patch_layer_lines = []
    for name in stl_names:
        patch_layer_lines.append(f"""\
            {name}
            {{
                nLayers {n_layers};
                thicknessRatio {expansion_ratio};
                maxFirstLayerThickness {first_layer_thickness};
            }}""")

    if layers.get("ground_layers", False):
        ground_patch = patches.get("ground", "ground")
        patch_layer_lines.append(f"""\
            {ground_patch}
            {{
                nLayers {n_layers};
                thicknessRatio {expansion_ratio};
                maxFirstLayerThickness {first_layer_thickness};
            }}""")

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
        boundary_layers_block = f"""\
boundaryLayers
{{
    nLayers             {n_layers};
    thicknessRatio      {expansion_ratio};
    maxFirstLayerThickness {first_layer_thickness};

    patchBoundaryLayers
    {{
{chr(10).join(patch_layer_lines)}
    }}

    optimiseLayer 1;

    optimisationParameters
    {{
        nSmoothNormals      3;
        maxNumIterations    2;
        featureSizeFactor   0.4;
        reCalculateNormals  1;
        relThicknessTol     0.1;
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
