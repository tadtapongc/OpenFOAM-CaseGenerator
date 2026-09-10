"""Backward compatibility alias for snappyHexMesh writers.

Deprecated: Import directly from `rapidfoam.writers.snappy` instead.
"""

from __future__ import annotations

from rapidfoam.writers.snappy import (
    FACE_MAP,
    write_block_mesh_dict,
    write_snappy_hex_mesh_dict,
    write_surface_feature_extract_dict,
)

__all__ = [
    "FACE_MAP",
    "write_block_mesh_dict",
    "write_snappy_hex_mesh_dict",
    "write_surface_feature_extract_dict",
]
