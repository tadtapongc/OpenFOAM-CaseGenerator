"""snappyHexMesh as a package: settings resolve once, the writers only render.

The dictionaries used to carry their own ``.get(key, default)`` fallbacks and to
compute the ``locationInMesh`` corner while rendering, so a number could live in
two places (``maxGlobalCells`` said 30M in the writer and 18M in the preset) and
``includedAngle`` disagreed with ``config.py``. These tests pin the split:
``meshers/snappy/settings.py`` owns every default and derived value, the
``*_dict.py`` modules take settings and produce text, and the old flat modules
are gone.

Run with python -m unittest discover -s tests.
"""
from __future__ import annotations

import contextlib
import importlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rapidfoam.cli import _do_generate
from rapidfoam.config import DEFAULT_CONFIG
from rapidfoam.meshers import get_mesher
from rapidfoam.meshers.snappy import (
    SnappySettings,
    render_block_mesh_dict,
    render_snappy_hex_mesh_dict,
    render_surface_feature_extract_dict,
    resolve_cells,
    resolve_location_in_mesh,
    resolve_snappy_settings,
    snappy_mesh_plan,
)
from rapidfoam.meshers.snappy.settings import (
    FEATURE_DEFAULTS,
    LAYER_DEFAULTS,
    QUALITY_DEFAULTS,
    RELAXED_DEFAULTS,
    SNAP_DEFAULTS,
)
from rapidfoam.stl_utils import write_stl

# A single triangle long in x, wide in y, thin in z: enough for domain + mesh
# derivation without needing an actual mesher.
TRIANGLES = [((0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (0.0, 0.8, 0.4))]

#: A config with nothing but what the settings module reads, to prove the
#: fallbacks still render when no DEFAULT_CONFIG was merged in.
BARE = {
    "flow": {"velocity": 16.67, "direction": "-z", "ground": True},
    "outputs": {"downforce_axis": "-y"},
    "patches": {"inlet": "inlet", "outlet": "outlet", "ground": "ground",
                "symmetry": "symmetry", "walls": "farField"},
    "stl_names": ["body"],
    "domain_box": {"min": [0.0, 0.0, -3.2], "max": [7.5, 4.0, 2.0]},
    "mesh_params": {
        "base_cell_size": 0.05,
        "surface_level": [4, 5],
        "edge_level": 6,
        "refinement_regions": [],
        "distance_levels": [],
    },
}


def bare_config(**extra) -> dict:
    """A raw (unresolved) config, so the writer defaults are exercised."""
    cfg = {key: (dict(value) if isinstance(value, dict) else value) for key, value in BARE.items()}
    cfg.update(extra)
    return cfg


class SnappyScaffold(unittest.TestCase):
    """Temporary project with one STL, plus a generate helper."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_stl(self.root / "stl" / "body.stl", "body", TRIANGLES)

    def generate(self, case_name: str, mesher: str = "snappy", **extra) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps({"case_name": case_name, "stl_files": ["body.stl"], **extra}))
        with contextlib.redirect_stdout(io.StringIO()):
            _do_generate(path, self.root, mesher=mesher)
        return self.root / "cases" / case_name

    @staticmethod
    def settings(case: Path) -> SnappySettings:
        cfg = json.loads((case / "case_config.json").read_text(encoding="utf-8"))
        return resolve_snappy_settings(cfg)

    @staticmethod
    def dict_text(case: Path, name: str) -> str:
        return (case / "system" / name).read_text(encoding="utf-8")


class DefaultsTest(unittest.TestCase):
    """The fallback tables are the case defaults, not a second opinion."""

    def test_snappy_tables_match_the_case_defaults(self):
        self.assertEqual(SNAP_DEFAULTS, DEFAULT_CONFIG["snap"])
        self.assertEqual(QUALITY_DEFAULTS, {
            key: value for key, value in DEFAULT_CONFIG["mesh_quality"].items()
            if key != "relaxed"
        })
        self.assertEqual(RELAXED_DEFAULTS, DEFAULT_CONFIG["mesh_quality"]["relaxed"])
        self.assertEqual(FEATURE_DEFAULTS, DEFAULT_CONFIG["feature_extract"])
        # n_layers has its own home (SnappySettings.n_layers) and the first-layer
        # thickness belongs to the shared sizing module.
        shared = {key: value for key, value in DEFAULT_CONFIG["layers"].items()
                  if key in LAYER_DEFAULTS}
        self.assertEqual(shared, LAYER_DEFAULTS)

    def test_bare_config_renders_with_snappy_own_defaults(self):
        settings = resolve_snappy_settings(bare_config())
        self.assertEqual(settings.snap, SNAP_DEFAULTS)
        self.assertEqual(settings.quality["maxNonOrtho"], 65)
        self.assertEqual(settings.relaxed["maxNonOrtho"], 75)
        self.assertEqual(settings.feature_extract["includedAngle"], 140)
        # Declared in rapidfoam.meshers.refinement, not restated in the writer.
        self.assertEqual(settings.castellated["maxGlobalCells"], 18_000_000)
        self.assertEqual(settings.castellated["nCellsBetweenLevels"], 2)
        self.assertEqual(settings.castellated["maxLoadUnbalance"], 0.25)
        text = render_snappy_hex_mesh_dict(settings)
        self.assertIn("maxGlobalCells      18000000;", text)
        self.assertIn("nSmoothPatch        5;", text)
        self.assertIn("firstLayerThickness     0.3;", text)
        self.assertIn("includedAngle   140;", render_surface_feature_extract_dict(settings))

    def test_case_values_win_over_the_tables(self):
        settings = resolve_snappy_settings(bare_config(
            snap={"nSmoothPatch": 21, "multiRegionFeatureSnap": True},
            layers={"n_layers": 8, "expansion_ratio": 1.35},
            mesh_quality={"maxNonOrtho": 71, "relaxed": {"maxNonOrtho": 78}},
            feature_extract={"includedAngle": 150},
            mesh_params={**BARE["mesh_params"], "maxGlobalCells": 1_234_567},
        ))
        self.assertEqual(settings.snap["nSmoothPatch"], 21)
        self.assertEqual(settings.snap["tolerance"], SNAP_DEFAULTS["tolerance"])
        self.assertTrue(settings.snap["multiRegionFeatureSnap"])
        self.assertEqual(settings.n_layers, 8)
        self.assertEqual(settings.layers["expansion_ratio"], 1.35)
        self.assertEqual(settings.quality["maxNonOrtho"], 71)
        self.assertEqual(settings.quality["maxConcave"], QUALITY_DEFAULTS["maxConcave"])
        self.assertEqual(settings.relaxed["maxNonOrtho"], 78)
        self.assertEqual(settings.feature_extract["includedAngle"], 150)
        self.assertEqual(settings.castellated["maxGlobalCells"], 1_234_567)


class DerivedValueTest(unittest.TestCase):
    """Numbers snappy derives from the box, the geometry and the layers."""

    def test_cells_follow_the_box_and_the_base_cell(self):
        self.assertEqual(resolve_cells((0.0, 0.0, 0.0), (10.0, 4.0, 2.0), 0.5), (20, 8, 4))
        # A box thinner than one cell still gets a cell in that direction.
        self.assertEqual(resolve_cells((0.0, 0.0, 0.0), (10.0, 4.0, 0.01), 0.5), (20, 8, 1))

    def test_auto_location_sits_away_from_the_geometry(self):
        faces = {"+x": "farField", "-x": "symmetry", "+y": "farField", "-y": "ground",
                 "+z": "inlet", "-z": "outlet"}
        roles = {"farField": "walls", "symmetry": "symmetry", "ground": "ground",
                 "inlet": "inlet", "outlet": "outlet"}
        # Flow is -z (so upstream is +z), the roof is +y, symmetry is -x.
        loc = resolve_location_in_mesh(
            bare_config(), (0.0, 0.0, -3.2), (7.5, 4.0, 2.0), faces, roles
        )
        for got, want in zip(loc, (7.125, 3.8, 1.74)):
            self.assertAlmostEqual(got, want, places=4)

    def test_auto_location_drops_to_the_floor_when_the_roof_is_ground(self):
        faces = {"+x": "symmetry", "-x": "farField", "+y": "ground", "-y": "farField",
                 "+z": "inlet", "-z": "outlet"}
        roles = {"symmetry": "symmetry", "farField": "walls", "ground": "ground",
                 "inlet": "inlet", "outlet": "outlet"}
        loc = resolve_location_in_mesh(
            bare_config(), (0.0, 0.0, -3.2), (7.5, 4.0, 2.0), faces, roles
        )
        self.assertAlmostEqual(loc[1], 0.2, places=4)  # floor the ground patch owns
        self.assertAlmostEqual(loc[0], 0.375, places=4)  # opposite the +x symmetry

    def test_explicit_location_wins(self):
        settings = resolve_snappy_settings(bare_config(
            mesh_params={**BARE["mesh_params"], "location_in_mesh": [1.0, 2.0, 3.0]},
        ))
        self.assertEqual(settings.location_in_mesh, (1.0, 2.0, 3.0))
        self.assertIn(
            "locationInMesh (1.0000 2.0000 3.0000);",
            render_snappy_hex_mesh_dict(settings),
        )

    def test_first_layer_fraction_tracks_the_absolute_intent(self):
        relative = resolve_snappy_settings(bare_config())
        body_cell = relative.sizing.body_cell_size
        absolute = resolve_snappy_settings(bare_config(layers={
            "n_layers": 5, "first_layer_mode": "absolute",
            "first_layer_height": body_cell * 0.4,
        }))
        self.assertEqual(relative.first_layer_fraction, 0.3)
        self.assertEqual(absolute.first_layer_fraction, 0.4)

    def test_parallel_meshing_follows_the_rank_count(self):
        serial = snappy_mesh_plan(resolve_snappy_settings(bare_config()))
        parallel = snappy_mesh_plan(resolve_snappy_settings(bare_config(parallel={"n_procs": 4})))
        self.assertFalse(serial.parallel_meshing)
        self.assertEqual(
            [command.tool for command in serial.commands],
            ["surfaceFeatureExtract", "blockMesh", "snappyHexMesh", "checkMesh", "renumberMesh"],
        )
        self.assertTrue(parallel.parallel_meshing)
        self.assertEqual(
            [command.tool for command in parallel.commands],
            ["surfaceFeatureExtract", "blockMesh", "decomposePar", "snappyHexMesh",
             "checkMesh", "renumberMesh"],
        )
        self.assertEqual(len([command for command in parallel.commands if command.mpi]), 2)


class PackageLayoutTest(SnappyScaffold):
    """The registry surface still works, from the new package."""

    def test_registry_still_reports_its_identity(self):
        mesher = get_mesher("snappy")
        self.assertEqual((mesher.name, mesher.label), ("snappy", "snappyHexMesh"))
        self.assertTrue(mesher.enforces_cell_budget)
        self.assertEqual(mesher.engine_keys(), {})
        self.assertIn("maxGlobalCells", mesher.mesh_params_keys())

    def test_dictionaries_are_rendered_from_the_resolved_settings(self):
        case = self.generate("snappy_render")
        settings = self.settings(case)
        self.assertIsInstance(settings, SnappySettings)
        self.assertEqual(render_block_mesh_dict(settings), self.dict_text(case, "blockMeshDict"))
        self.assertEqual(
            render_surface_feature_extract_dict(settings),
            self.dict_text(case, "surfaceFeatureExtractDict"),
        )
        self.assertEqual(
            render_snappy_hex_mesh_dict(settings), self.dict_text(case, "snappyHexMeshDict")
        )

    def test_road_layers_only_when_the_case_asks_for_them(self):
        plain = self.settings(self.generate("snappy_no_road"))
        road = self.settings(self.generate(
            "snappy_road",
            layers={"ground_layers": True},
        ))
        self.assertFalse(plain.ground_layers)
        self.assertNotIn('"ground" { nSurfaceLayers', render_snappy_hex_mesh_dict(plain))
        self.assertTrue(road.ground_layers)
        self.assertIn('"ground" { nSurfaceLayers 5; }', render_snappy_hex_mesh_dict(road))

    def test_the_old_flat_modules_are_gone(self):
        for name in ("rapidfoam.writers.snappy", "rapidfoam.writers.mesh"):
            with self.subTest(name=name), self.assertRaises(ModuleNotFoundError):
                importlib.import_module(name)

    def test_the_package_is_one_module_per_responsibility(self):
        expected = {
            "rapidfoam.meshers.snappy",
            "rapidfoam.meshers.snappy.block_mesh_dict",
            "rapidfoam.meshers.snappy.keys",
            "rapidfoam.meshers.snappy.plan",
            "rapidfoam.meshers.snappy.settings",
            "rapidfoam.meshers.snappy.snappy_hex_mesh_dict",
            "rapidfoam.meshers.snappy.surface_feature_extract_dict",
        }
        package = Path(importlib.import_module("rapidfoam.meshers.snappy").__file__).parent
        modules = {f"rapidfoam.meshers.snappy.{path.stem}" for path in package.glob("*.py")}
        modules.discard("rapidfoam.meshers.snappy.__init__")
        modules.add("rapidfoam.meshers.snappy")
        self.assertEqual(modules, expected)
