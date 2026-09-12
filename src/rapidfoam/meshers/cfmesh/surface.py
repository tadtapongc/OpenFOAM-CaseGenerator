"""domain.stl — the wind tunnel box plus the CAD, as cfMesh's one surface.

cfMesh meshes a single closed surface, so the outer box faces (inward normals, so
the box is the fluid) are concatenated with the CAD solids (outward normals, so
the model is a hole). snappy grows its blockMesh box instead, which is why this
lives with the cfMesh mesher and not in the shared writers.

This concatenates surfaces; it does not clip CAD, repair intersections, or
certify a closed manifold. Verify the resulting mesh when CAD crosses the domain
boundary - ``rapidfoam generate`` warns when it does.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rapidfoam.geometry import face_assignments


def write_box_stl_faces(box_min: list[float], box_max: list[float],
                        face_map: dict[str, str]) -> str:
    """ASCII STL for the six bounding-box faces, normals pointing inwards."""
    x0, y0, z0 = box_min
    x1, y1, z1 = box_max
    v = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    faces_spec = {
        "-x": ((1.0, 0.0, 0.0), (v[0], v[3], v[7]), (v[0], v[7], v[4])),
        "+x": ((-1.0, 0.0, 0.0), (v[1], v[5], v[6]), (v[1], v[6], v[2])),
        "-y": ((0.0, 1.0, 0.0), (v[0], v[4], v[5]), (v[0], v[5], v[1])),
        "+y": ((0.0, -1.0, 0.0), (v[2], v[6], v[7]), (v[2], v[7], v[3])),
        "-z": ((0.0, 0.0, 1.0), (v[0], v[1], v[2]), (v[0], v[2], v[3])),
        "+z": ((0.0, 0.0, -1.0), (v[4], v[7], v[6]), (v[4], v[6], v[5])),
    }

    blocks: list[str] = []
    for direction, (normal, tri1, tri2) in faces_spec.items():
        patch_name = face_map.get(direction, face_map.get("walls", "farField"))
        block = [f"solid {patch_name}"]
        for tri in (tri1, tri2):
            block.append(f"  facet normal {normal[0]:.6e} {normal[1]:.6e} {normal[2]:.6e}")
            block.append("    outer loop")
            for vertex in tri:
                block.append(f"      vertex {vertex[0]:.6e} {vertex[1]:.6e} {vertex[2]:.6e}")
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
    """Write ``constant/triSurface/domain.stl`` (box faces + CAD solids)."""
    tri_dir = case_dir / "constant" / "triSurface"
    tri_dir.mkdir(parents=True, exist_ok=True)
    domain_stl_path = tri_dir / "domain.stl"

    box = cfg["domain_box"]
    box_stl_content = write_box_stl_faces(box["min"], box["max"], face_assignments(cfg))

    with open(domain_stl_path, "w", encoding="utf-8", newline="\n") as fout:
        fout.write(box_stl_content)
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


__all__ = ["generate_domain_stl", "write_box_stl_faces"]
