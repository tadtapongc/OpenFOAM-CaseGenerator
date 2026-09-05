"""STL file utilities — ASCII STL reader/writer for OpenFOAM.

Supports:
  - Reading ASCII STL files
  - Writing ASCII STL (required by snappyHexMesh)
  - Solid name rewriting for OpenFOAM patch matching
  - Bounding box computation
"""

from __future__ import annotations

import re
import shutil
import struct
from pathlib import Path
from typing import Sequence

Triangle = tuple[
    tuple[float, float, float],  # normal
    tuple[float, float, float],  # v1
    tuple[float, float, float],  # v2
    tuple[float, float, float],  # v3
]

BBox = tuple[tuple[float, float, float], tuple[float, float, float]]


def is_binary_stl(filepath: Path) -> bool:
    """Detect whether an STL file is binary or ASCII."""
    filepath = Path(filepath)
    size = filepath.stat().st_size

    if size < 84:
        return False

    # Check text content first to avoid false positives
    try:
        with open(filepath, "r", errors="ignore") as f:
            first_line = f.readline().strip()
            if first_line.startswith("solid"):
                for _ in range(5):
                    line = f.readline().strip()
                    if "facet" in line or "vertex" in line or "endsolid" in line:
                        return False
    except Exception:
        pass

    with open(filepath, "rb") as f:
        f.read(80)
        n_triangles = struct.unpack("<I", f.read(4))[0]

    expected_size = 84 + 50 * n_triangles
    return size == expected_size


def read_stl(filepath: str | Path) -> tuple[str, list[Triangle]]:
    """Read an ASCII STL file.

    Returns:
        (solid_name, list_of_triangles)
        Each triangle is (normal, v1, v2, v3) where each is a 3-tuple of floats.

    Raises:
        FileNotFoundError: If file doesn't exist.
        ValueError: If file is binary or malformed.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"STL file not found: {filepath}")

    if is_binary_stl(filepath):
        raise ValueError(
            f"Binary STL not supported: {filepath}\n"
            f"  Convert to ASCII in your CAD tool (SolidWorks: Save As → STL → ASCII)."
        )

    text = filepath.read_text(encoding="utf-8", errors="replace")

    match = re.match(r"^\s*solid\s+(.*)", text, re.MULTILINE)
    if not match:
        raise ValueError(f"Not a valid ASCII STL: {filepath}")
    name = match.group(1).strip() or filepath.stem

    facet_pattern = re.compile(
        r"facet\s+normal\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s*\n"
        r"\s*outer\s+loop\s*\n"
        r"\s*vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s*\n"
        r"\s*vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s*\n"
        r"\s*vertex\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s+([\d.eE+\-]+)\s*\n"
        r"\s*endloop\s*\n"
        r"\s*endfacet",
        re.MULTILINE,
    )

    triangles: list[Triangle] = []
    for m in facet_pattern.finditer(text):
        vals = [float(m.group(i)) for i in range(1, 13)]
        triangles.append((
            (vals[0], vals[1], vals[2]),
            (vals[3], vals[4], vals[5]),
            (vals[6], vals[7], vals[8]),
            (vals[9], vals[10], vals[11]),
        ))

    if not triangles:
        raise ValueError(f"No triangles found in {filepath}")

    return name, triangles


def write_stl(filepath: str | Path, name: str, triangles: Sequence[Triangle]) -> None:
    """Write triangles to an ASCII STL file."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"solid {name}"]
    for normal, v1, v2, v3 in triangles:
        lines.append(f"  facet normal {normal[0]:.6e} {normal[1]:.6e} {normal[2]:.6e}")
        lines.append("    outer loop")
        lines.append(f"      vertex {v1[0]:.6e} {v1[1]:.6e} {v1[2]:.6e}")
        lines.append(f"      vertex {v2[0]:.6e} {v2[1]:.6e} {v2[2]:.6e}")
        lines.append(f"      vertex {v3[0]:.6e} {v3[1]:.6e} {v3[2]:.6e}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {name}")
    lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")


def stl_bounds(filepath: str | Path) -> BBox:
    """Compute axis-aligned bounding box.

    Returns:
        ((xmin, ymin, zmin), (xmax, ymax, zmax))
    """
    _, triangles = read_stl(filepath)
    xs, ys, zs = [], [], []
    for _, v1, v2, v3 in triangles:
        for v in (v1, v2, v3):
            xs.append(v[0])
            ys.append(v[1])
            zs.append(v[2])
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def copy_stl(src: str | Path, dst: str | Path, name: str | None = None) -> int:
    """Copy STL to destination, optionally rewriting solid name.

    Returns:
        Number of triangles.
    """
    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    original_name, triangles = read_stl(src)
    n_triangles = len(triangles)

    if name is None or name == original_name:
        shutil.copy2(src, dst)
    else:
        write_stl(dst, name, triangles)

    return n_triangles
