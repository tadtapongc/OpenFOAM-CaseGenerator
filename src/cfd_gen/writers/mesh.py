"""Mesh-related OpenFOAM dict writers.

Generates: blockMeshDict, snappyHexMeshDict, surfaceFeatureExtractDict
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cfd_gen.geometry import (
    flow_axis_index_sign,
    parse_axis,
    up_axis_index,
)
from cfd_gen.writers.base import FOOTER, bool_str, foam_header

# ============================================================
# FACE MAP — hex vertex ordering to face string
# ============================================================

FACE_MAP: dict[str, str] = {
    "+x": "(1 2 6 5)", "-x": "(0 4 7 3)",
    "+y": "(2 3 7 6)", "-y": "(0 1 5 4)",
    "+z": "(4 5 6 7)", "-z": "(0 3 2 1)",
}


def _get_face_assignments(cfg: dict[str, Any]) -> dict[str, str]:
    """Get face-to-patch mapping.

    If 'domain_faces' is in config, use it directly.
    Otherwise, auto-assign from flow/up axes (legacy behavior).

    Returns:
        dict mapping direction ("+x", "-x", etc.) to patch name
    """
    patches = cfg["patches"]

    # Explicit assignment — user specifies each face
    if "domain_faces" in cfg:
        return cfg["domain_faces"]

    # Auto-assign from flow direction (fallback)
    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)

    if flow_sign > 0:
        inlet_dir = "-" + "xyz"[flow_idx]
        outlet_dir = "+" + "xyz"[flow_idx]
    else:
        inlet_dir = "+" + "xyz"[flow_idx]
        outlet_dir = "-" + "xyz"[flow_idx]

    ground_dir = "-" + "xyz"[up_idx]
    lateral_axes = [i for i in range(3) if i != flow_idx and i != up_idx]
    symmetry_dir = "-" + "xyz"[lateral_axes[0]] if lateral_axes else "-x"

    all_dirs = ["+x", "-x", "+y", "-y", "+z", "-z"]
    assigned = {inlet_dir, outlet_dir, ground_dir, symmetry_dir}
    wall_dirs = [d for d in all_dirs if d not in assigned]

    face_map = {
        inlet_dir: patches["inlet"],
        outlet_dir: patches["outlet"],
        ground_dir: patches["ground"],
        symmetry_dir: patches["symmetry"],
    }
    for d in wall_dirs:
        face_map[d] = patches["walls"]

    return face_map


# ============================================================
# BLOCKMESH
# ============================================================

def write_block_mesh_dict(cfg: dict[str, Any], case_dir: Path) -> None:
    """Generate blockMeshDict from domain box and base cell size."""
    box = cfg["domain_box"]
    bmin, bmax = box["min"], box["max"]
    cell_size = cfg["mesh_params"]["base_cell_size"]

    nx = max(1, round((bmax[0] - bmin[0]) / cell_size))
    ny = max(1, round((bmax[1] - bmin[1]) / cell_size))
    nz = max(1, round((bmax[2] - bmin[2]) / cell_size))

    face_assignments = _get_face_assignments(cfg)

    # Group faces by patch name
    patch_faces: dict[str, list[str]] = {}
    for direction, patch_name in face_assignments.items():
        patch_faces.setdefault(patch_name, []).append(FACE_MAP[direction])

    # Determine patch types
    PATCH_TYPES = {
        "inlet": "patch",
        "outlet": "patch",
        "ground": "wall",
        "symmetry": "symmetry",
    }

    # Build boundary block
    boundary_lines = []
    for patch_name, faces in patch_faces.items():
        # Determine type: check if patch_name matches a known type
        patch_type = "patch"  # default
        for key, ptype in PATCH_TYPES.items():
            if key in patch_name.lower():
                patch_type = ptype
                break
        faces_str = " ".join(faces)
        boundary_lines.append(f"""\
    {patch_name}
    {{
        type {patch_type};
        faces ( {faces_str} );
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
    (case_dir / "system" / "blockMeshDict").write_text(
        foam_header("blockMeshDict") + content + FOOTER
    )


# ============================================================
# SNAPPYHEXMESH
# ============================================================

def write_snappy_hex_mesh_dict(cfg: dict[str, Any], case_dir: Path) -> None:
    """Generate snappyHexMeshDict — universal settings."""
    mesh = cfg["mesh_params"]
    stl_names = cfg["stl_names"]
    patches = cfg["patches"]
    snap = cfg["snap"]
    layers = cfg["layers"]
    quality = cfg["mesh_quality"]
    relaxed = quality.get("relaxed", {})
    feat = cfg["feature_extract"]

    surface_level = mesh["surface_level"]
    edge_level = mesh["edge_level"]
    regions = mesh["refinement_regions"]

    # Geometry block
    geo_lines = []
    for name in stl_names:
        geo_lines.append(f"    {name}.stl {{ type triSurfaceMesh; name {name}; }}")
    for r in regions:
        geo_lines.append(
            f"    {r['name']} {{ type searchableBox;"
            f" min ({r['min'][0]} {r['min'][1]} {r['min'][2]});"
            f" max ({r['max'][0]} {r['max'][1]} {r['max'][2]}); }}")

    # Features block
    feat_lines = []
    for name in stl_names:
        feat_lines.append(f"        {{ file \"{name}.eMesh\"; level {edge_level}; }}")

    # Refinement surfaces
    ref_surf_lines = []
    for name in stl_names:
        ref_surf_lines.append(
            f"        {name} {{ level ({surface_level[0]} {surface_level[1]});"
            f" patchInfo {{ type wall; }} }}")

    # Refinement regions
    ref_region_lines = []
    for r in regions:
        ref_region_lines.append(
            f"        {r['name']} {{ mode inside; levels ((1e15 {r['level']})); }}")

    # Layer surfaces
    layer_lines = []
    n_layers = layers["n_layers"]
    for name in stl_names:
        layer_lines.append(f'        "{name}" {{ nSurfaceLayers {n_layers}; }}')
    if cfg["flow"]["ground"]:
        layer_lines.append(f'        "{patches["ground"]}" {{ nSurfaceLayers {n_layers}; }}')

    # Location in mesh — inlet-ceiling-farwall corner (always outside geometry)
    #
    # Strategy: place the point at the domain corner that is maximally far
    # from where geometry lives (geometry is downstream, near ground, near
    # symmetry plane). This is robust for all external aero configurations.
    box = cfg["domain_box"]
    flow_idx, flow_sign = flow_axis_index_sign(cfg)
    up_idx = up_axis_index(cfg)
    lateral_idx = next(i for i in range(3) if i != flow_idx and i != up_idx)
    extent = [box["max"][i] - box["min"][i] for i in range(3)]

    loc = [0.0, 0.0, 0.0]

    # Flow axis: near inlet (upstream side)
    if flow_sign > 0:
        loc[flow_idx] = box["min"][flow_idx] + extent[flow_idx] * 0.05
    else:
        loc[flow_idx] = box["max"][flow_idx] - extent[flow_idx] * 0.05

    # Up axis: near ceiling (top of domain, far from ground)
    loc[up_idx] = box["max"][up_idx] - extent[up_idx] * 0.05

    # Lateral axis: away from symmetry plane (toward far wall)
    domain_faces = cfg.get("domain_faces", {})
    sym_dir = None
    for face_dir, patch_name in domain_faces.items():
        if "symmetry" in patch_name.lower():
            sym_dir = face_dir
            break

    if sym_dir and sym_dir.endswith("xyz"[lateral_idx]):
        # Symmetry is on the lateral axis — move to the opposite side
        if sym_dir.startswith("-"):
            loc[lateral_idx] = box["max"][lateral_idx] - extent[lateral_idx] * 0.05
        else:
            loc[lateral_idx] = box["min"][lateral_idx] + extent[lateral_idx] * 0.05
    else:
        # No symmetry on lateral axis — center is safe
        loc[lateral_idx] = (box["min"][lateral_idx] + box["max"][lateral_idx]) / 2

    content = f"""\
castellatedMesh true;
snap            true;
addLayers       true;

geometry
{{
{chr(10).join(geo_lines)}
}}

castellatedMeshControls
{{
    maxLocalCells       {mesh.get("maxLocalCells", 2000000)};
    maxGlobalCells      {mesh.get("maxGlobalCells", 30000000)};
    minRefinementCells  {mesh.get("minRefinementCells", 10)};
    maxLoadUnbalance    0.10;
    nCellsBetweenLevels {mesh.get("nCellsBetweenLevels", 3)};

    features
    (
{chr(10).join(feat_lines)}
    );

    refinementSurfaces
    {{
{chr(10).join(ref_surf_lines)}
    }}

    resolveFeatureAngle {mesh.get("resolveFeatureAngle", 15)};

    refinementRegions
    {{
{chr(10).join(ref_region_lines)}
    }}

    locationInMesh ({loc[0]:.4f} {loc[1]:.4f} {loc[2]:.4f});
    allowFreeStandingZoneFaces {bool_str(mesh.get("allowFreeStandingZoneFaces", True))};
}}

snapControls
{{
    nSmoothPatch        {snap.get("nSmoothPatch", 5)};
    tolerance           {snap.get("tolerance", 2.0)};
    nSolveIter          {snap.get("nSolveIter", 200)};
    nRelaxIter          {snap.get("nRelaxIter", 8)};
    nFeatureSnapIter    {snap.get("nFeatureSnapIter", 15)};
    implicitFeatureSnap {bool_str(snap.get("implicitFeatureSnap", True))};
    explicitFeatureSnap {bool_str(snap.get("explicitFeatureSnap", True))};
    multiRegionFeatureSnap {bool_str(snap.get("multiRegionFeatureSnap", False))};
}}

addLayersControls
{{
    relativeSizes       true;
    layers
    {{
{chr(10).join(layer_lines)}
    }}
    expansionRatio          {layers.get("expansion_ratio", 1.2)};
    firstLayerThickness     {layers.get("first_layer_thickness", 0.3)};
    minThickness            {layers.get("min_thickness", 0.05)};
    nGrow                   {layers.get("nGrow", 0)};
    featureAngle            {layers.get("featureAngle", 170)};
    slipFeatureAngle        {layers.get("slipFeatureAngle", 30)};
    maxFaceThicknessRatio   {layers.get("maxFaceThicknessRatio", 0.5)};
    nSmoothSurfaceNormals   {layers.get("nSmoothSurfaceNormals", 3)};
    nSmoothThickness        {layers.get("nSmoothThickness", 10)};
    nSmoothNormals          {layers.get("nSmoothNormals", 3)};
    nRelaxIter              {layers.get("nRelaxIter", 10)};
    nBufferCellsNoExtrude   {layers.get("nBufferCellsNoExtrude", 0)};
    nLayerIter              {layers.get("nLayerIter", 50)};
    maxAlignedCells         {layers.get("maxAlignedCells", 200000)};
    minMedialAxisAngle      {layers.get("minMedialAxisAngle", 90)};
    maxThicknessToMedialRatio {layers.get("maxThicknessToMedialRatio", 0.3)};
    nMedialAxisIter         {layers.get("nMedialAxisIter", 10)};
    nSmoothDisplacement     {layers.get("nSmoothDisplacement", 0)};
    detectExtrusionIsland   {bool_str(layers.get("detectExtrusionIsland", True))};
    nRelaxedIter            {layers.get("nRelaxedIter", 20)};
}}

meshQualityControls
{{
    maxNonOrtho         {quality.get("maxNonOrtho", 65)};
    maxBoundarySkewness {quality.get("maxBoundarySkewness", 20)};
    maxInternalSkewness {quality.get("maxInternalSkewness", 4)};
    maxConcave          {quality.get("maxConcave", 80)};
    minVol              {quality.get("minVol", 1e-13)};
    minTetQuality       {quality.get("minTetQuality", 1e-15)};
    minArea             {quality.get("minArea", -1)};
    minTwist            {quality.get("minTwist", 0.02)};
    minDeterminant      {quality.get("minDeterminant", 0.001)};
    minFaceWeight       {quality.get("minFaceWeight", 0.05)};
    minVolRatio         {quality.get("minVolRatio", 0.01)};
    minTriangleTwist    {quality.get("minTriangleTwist", -1)};
    nSmoothScale        {quality.get("nSmoothScale", 4)};
    errorReduction      {quality.get("errorReduction", 0.75)};

    relaxed
    {{
        maxNonOrtho     {relaxed.get("maxNonOrtho", 75)};
        maxBoundarySkewness {relaxed.get("maxBoundarySkewness", 25)};
        maxInternalSkewness {relaxed.get("maxInternalSkewness", 5)};
        maxConcave      {relaxed.get("maxConcave", 85)};
        minVol          {relaxed.get("minVol", 1e-13)};
        minTetQuality   {relaxed.get("minTetQuality", 1e-30)};
        minArea         {relaxed.get("minArea", -1)};
        minTwist        {relaxed.get("minTwist", 0.001)};
        minDeterminant  {relaxed.get("minDeterminant", 0.0005)};
        minFaceWeight   {relaxed.get("minFaceWeight", 0.02)};
        minVolRatio     {relaxed.get("minVolRatio", 0.005)};
        minTriangleTwist {relaxed.get("minTriangleTwist", -1)};
    }}
}}

writeFlags ( scalarLevels layerSets layerFields );
mergeTolerance 1e-6;

"""
    (case_dir / "system" / "snappyHexMeshDict").write_text(
        foam_header("snappyHexMeshDict") + content + FOOTER
    )


# ============================================================
# SURFACE FEATURE EXTRACT
# ============================================================

def write_surface_feature_extract_dict(cfg: dict[str, Any], case_dir: Path) -> None:
    """Generate surfaceFeatureExtractDict."""
    feat = cfg["feature_extract"]
    method = feat.get("extractionMethod", "extractFromSurface")
    angle = feat.get("includedAngle", 150)

    entries = []
    for name in cfg["stl_names"]:
        entries.append(f"""\
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
    }}""")

    content = "\n".join(entries) + "\n\n"
    (case_dir / "system" / "surfaceFeatureExtractDict").write_text(
        foam_header("surfaceFeatureExtractDict") + content + FOOTER
    )
