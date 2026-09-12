"""system/snappyHexMeshDict — settings in, text out.

The castellated, snap, layer and quality blocks, the geometry from the STLs and
the refinement regions, the feature files to snap to and the point that must end
up inside the fluid. Levels stay snappy-native (``surface_level = [body,
feature]``, ``edge_level`` for the extracted feature edges); the shared sizing
already turned the same intent into metres for cfMesh.
"""

from __future__ import annotations

from pathlib import Path

from rapidfoam.meshers.snappy.settings import SnappySettings
from rapidfoam.writers.base import FOOTER, bool_str, foam_header


def render_snappy_hex_mesh_dict(settings: SnappySettings) -> str:
    """The text of ``system/snappyHexMeshDict``."""
    castellated = settings.castellated
    snap = settings.snap
    layers = settings.layers
    quality = settings.quality
    relaxed = settings.relaxed

    # Geometry: the STLs to mesh, plus one searchableBox per refinement region.
    geo_lines = [
        f"    {name}.stl {{ type triSurfaceMesh; name {name}; }}" for name in settings.stl_names
    ]
    geo_lines += [
        f"    {region.name} {{ type searchableBox;"
        f" min ({region.minimum[0]} {region.minimum[1]} {region.minimum[2]});"
        f" max ({region.maximum[0]} {region.maximum[1]} {region.maximum[2]}); }}"
        for region in settings.regions
    ]

    # Features: one extracted edge mesh per STL, snapped to the edge level.
    feat_lines = [
        f'        {{ file "{name}.eMesh"; level {settings.edge_level}; }}'
        for name in settings.stl_names
    ]

    ref_surf_lines = [
        f"        {name} {{ level ({settings.surface_level[0]} {settings.surface_level[1]});"
        f" patchInfo {{ type wall; }} }}"
        for name in settings.stl_names
    ]

    # Distance-based refinement on the STL surfaces conforms to the shape, where a
    # box would not; the wake boxes are plain inside-refinements.
    ref_region_lines: list[str] = []
    if settings.distance_levels:
        distance_levels = " ".join(
            f"({distance} {level})" for distance, level in settings.distance_levels
        )
        ref_region_lines += [
            f"        {name} {{ mode distance; levels ({distance_levels}); }}"
            for name in settings.stl_names
        ]
    ref_region_lines += [
        f"        {region.name} {{ mode inside; levels ((1e15 {region.level})); }}"
        for region in settings.regions
    ]

    # Layer surfaces: the model, plus the road when the case asks for it.
    layer_lines = [
        f'        "{name}" {{ nSurfaceLayers {settings.n_layers}; }}'
        for name in settings.stl_names
    ]
    if settings.ground_layers and settings.ground_patch in set(settings.face_patches.values()):
        layer_lines.append(
            f'        "{settings.ground_patch}" {{ nSurfaceLayers {settings.n_layers}; }}'
        )

    location = settings.location_in_mesh
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
    maxLocalCells       {castellated["maxLocalCells"]};
    maxGlobalCells      {castellated["maxGlobalCells"]};
    minRefinementCells  {castellated["minRefinementCells"]};
    maxLoadUnbalance    {castellated["maxLoadUnbalance"]};
    nCellsBetweenLevels {castellated["nCellsBetweenLevels"]};

    features
    (
{chr(10).join(feat_lines)}
    );

    refinementSurfaces
    {{
{chr(10).join(ref_surf_lines)}
    }}

    resolveFeatureAngle {castellated["resolveFeatureAngle"]};

    refinementRegions
    {{
{chr(10).join(ref_region_lines)}
    }}

    locationInMesh ({location[0]:.4f} {location[1]:.4f} {location[2]:.4f});
    allowFreeStandingZoneFaces {bool_str(castellated["allowFreeStandingZoneFaces"])};
}}

snapControls
{{
    nSmoothPatch        {snap["nSmoothPatch"]};
    tolerance           {snap["tolerance"]};
    nSolveIter          {snap["nSolveIter"]};
    nRelaxIter          {snap["nRelaxIter"]};
    nFeatureSnapIter    {snap["nFeatureSnapIter"]};
    implicitFeatureSnap {bool_str(snap["implicitFeatureSnap"])};
    explicitFeatureSnap {bool_str(snap["explicitFeatureSnap"])};
    multiRegionFeatureSnap {bool_str(snap["multiRegionFeatureSnap"])};
}}

addLayersControls
{{
    relativeSizes       true;
    layers
    {{
{chr(10).join(layer_lines)}
    }}
    expansionRatio          {layers["expansion_ratio"]};
    firstLayerThickness     {settings.first_layer_fraction};
    minThickness            {layers["min_thickness"]};
    nGrow                   {layers["nGrow"]};
    featureAngle            {layers["featureAngle"]};
    slipFeatureAngle        {layers["slipFeatureAngle"]};
    maxFaceThicknessRatio   {layers["maxFaceThicknessRatio"]};
    nSmoothSurfaceNormals   {layers["nSmoothSurfaceNormals"]};
    nSmoothThickness        {layers["nSmoothThickness"]};
    nSmoothNormals          {layers["nSmoothNormals"]};
    nRelaxIter              {layers["nRelaxIter"]};
    nBufferCellsNoExtrude   {layers["nBufferCellsNoExtrude"]};
    nLayerIter              {layers["nLayerIter"]};
    maxAlignedCells         {layers["maxAlignedCells"]};
    minMedialAxisAngle      {layers["minMedialAxisAngle"]};
    maxThicknessToMedialRatio {layers["maxThicknessToMedialRatio"]};
    nMedialAxisIter         {layers["nMedialAxisIter"]};
    nSmoothDisplacement     {layers["nSmoothDisplacement"]};
    detectExtrusionIsland   {bool_str(layers["detectExtrusionIsland"])};
    nRelaxedIter            {layers["nRelaxedIter"]};
}}

meshQualityControls
{{
    maxNonOrtho         {quality["maxNonOrtho"]};
    maxBoundarySkewness {quality["maxBoundarySkewness"]};
    maxInternalSkewness {quality["maxInternalSkewness"]};
    maxConcave          {quality["maxConcave"]};
    minVol              {quality["minVol"]};
    minTetQuality       {quality["minTetQuality"]};
    minArea             {quality["minArea"]};
    minTwist            {quality["minTwist"]};
    minDeterminant      {quality["minDeterminant"]};
    minFaceWeight       {quality["minFaceWeight"]};
    minVolRatio         {quality["minVolRatio"]};
    minTriangleTwist    {quality["minTriangleTwist"]};
    nSmoothScale        {quality["nSmoothScale"]};
    errorReduction      {quality["errorReduction"]};

    relaxed
    {{
        maxNonOrtho     {relaxed["maxNonOrtho"]};
        maxBoundarySkewness {relaxed["maxBoundarySkewness"]};
        maxInternalSkewness {relaxed["maxInternalSkewness"]};
        maxConcave      {relaxed["maxConcave"]};
        minVol          {relaxed["minVol"]};
        minTetQuality   {relaxed["minTetQuality"]};
        minArea         {relaxed["minArea"]};
        minTwist        {relaxed["minTwist"]};
        minDeterminant  {relaxed["minDeterminant"]};
        minFaceWeight   {relaxed["minFaceWeight"]};
        minVolRatio     {relaxed["minVolRatio"]};
        minTriangleTwist {relaxed["minTriangleTwist"]};
    }}
}}

writeFlags ( scalarLevels layerSets layerFields );
mergeTolerance 1e-6;

"""
    return foam_header("snappyHexMeshDict") + content + FOOTER


def write_snappy_hex_mesh_dict(settings: SnappySettings, case_dir: Path) -> None:
    """Write ``system/snappyHexMeshDict``."""
    system_dir = case_dir / "system"
    system_dir.mkdir(parents=True, exist_ok=True)
    (system_dir / "snappyHexMeshDict").write_text(render_snappy_hex_mesh_dict(settings))


__all__ = ["render_snappy_hex_mesh_dict", "write_snappy_hex_mesh_dict"]
