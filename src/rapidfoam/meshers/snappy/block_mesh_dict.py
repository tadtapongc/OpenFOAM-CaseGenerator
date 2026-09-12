"""system/blockMeshDict — settings in, text out.

The background hex block of the wind tunnel box. Every division came from
:func:`rapidfoam.meshers.snappy.settings.resolve_cells` and every patch from the
face assignment the domain writers use, so this module only formats.
"""

from __future__ import annotations

from pathlib import Path

from rapidfoam.meshers.snappy.settings import SnappySettings
from rapidfoam.writers.base import FOOTER, foam_header

#: Hex vertex ordering per box face.
FACE_MAP: dict[str, str] = {
    "+x": "(1 2 6 5)", "-x": "(0 4 7 3)",
    "+y": "(2 3 7 6)", "-y": "(0 1 5 4)",
    "+z": "(4 5 6 7)", "-z": "(0 3 2 1)",
}

#: Boundary role -> OpenFOAM patch type.
PATCH_TYPES: dict[str, str] = {
    "inlet": "patch",
    "outlet": "patch",
    "ground": "wall",
    "symmetry": "symmetry",
}


def render_block_mesh_dict(settings: SnappySettings) -> str:
    """The text of ``system/blockMeshDict``."""
    bmin, bmax = settings.minimum, settings.maximum
    nx, ny, nz = settings.cells

    # Group the box faces by the patch they were assigned to, in assignment order.
    patch_faces: dict[str, list[str]] = {}
    for direction, patch_name in settings.face_patches.items():
        patch_faces.setdefault(patch_name, []).append(FACE_MAP[direction])

    boundary_lines = []
    for patch_name, faces in patch_faces.items():
        patch_type = PATCH_TYPES.get(settings.patch_roles.get(patch_name, ""), "patch")
        boundary_lines.append(f"""\
    {patch_name}
    {{
        type {patch_type};
        faces ( {" ".join(faces)} );
    }}""")

    content = f"""\
scale   1;

vertices
(
    ({bmin[0]} {bmin[1]} {bmin[2]})
    ({bmax[0]} {bmin[1]} {bmin[2]})
    ({bmax[0]} {bmax[1]} {bmin[2]})
    ({bmin[0]} {bmax[1]} {bmin[2]})
    ({bmin[0]} {bmin[1]} {bmax[2]})
    ({bmax[0]} {bmin[1]} {bmax[2]})
    ({bmax[0]} {bmax[1]} {bmax[2]})
    ({bmin[0]} {bmax[1]} {bmax[2]})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);

edges ();

boundary
(
{chr(10).join(boundary_lines)}
);

mergePatchPairs ();

"""
    return foam_header("blockMeshDict") + content + FOOTER


def write_block_mesh_dict(settings: SnappySettings, case_dir: Path) -> None:
    """Write ``system/blockMeshDict``."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "blockMeshDict").write_text(render_block_mesh_dict(settings))


__all__ = ["FACE_MAP", "PATCH_TYPES", "render_block_mesh_dict", "write_block_mesh_dict"]
