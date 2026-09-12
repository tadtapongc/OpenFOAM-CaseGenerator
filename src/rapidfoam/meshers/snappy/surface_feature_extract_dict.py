"""system/surfaceFeatureExtractDict — settings in, text out.

One entry per input STL: snappy meshes the extracted ``.eMesh`` feature edges, so
the included angle here decides which CAD edges survive as features.
"""

from __future__ import annotations

from pathlib import Path

from rapidfoam.meshers.snappy.settings import SnappySettings
from rapidfoam.writers.base import FOOTER, foam_header


def render_surface_feature_extract_dict(settings: SnappySettings) -> str:
    """The text of ``system/surfaceFeatureExtractDict``."""
    feature = settings.feature_extract
    method = feature["extractionMethod"]
    angle = feature["includedAngle"]

    entries = [
        f"""\
    {name}.stl
    {{
        extractionMethod    {method};
        {method}Coeffs
        {{
            includedAngle   {angle};
        }}
        subsetFeatures
        {{
            nonManifoldEdges    yes;
            openEdges           yes;
        }}
        writeObj            no;
    }}"""
        for name in settings.stl_names
    ]

    content = "\n".join(entries) + "\n\n"
    return foam_header("surfaceFeatureExtractDict") + content + FOOTER


def write_surface_feature_extract_dict(settings: SnappySettings, case_dir: Path) -> None:
    """Write ``system/surfaceFeatureExtractDict``."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "surfaceFeatureExtractDict").write_text(
        render_surface_feature_extract_dict(settings)
    )


__all__ = ["render_surface_feature_extract_dict", "write_surface_feature_extract_dict"]
