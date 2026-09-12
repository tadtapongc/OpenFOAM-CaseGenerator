"""Geometry-relative cell sizing — the default settings for any FSAE geometry.

Cell size is derived from the model itself (longest bounding-box dimension /
``cells_per_length``), so one fidelity preset means the same resolution per
model length on a full car, a front wing or a subassembly. These tests pin that
scaling, the 3.0 m calibration that reproduces the older absolute presets, the
explicit-metres escape hatch, and the trailing-edge refinement default.

Run with python -m unittest discover -s tests.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rapidfoam.cli import _do_generate
from rapidfoam.config import load_config, validate
from rapidfoam.meshers.presets import FIDELITY_PRESETS
from rapidfoam.meshers.sizing import (
    DEFAULT_CELLS_PER_LENGTH,
    resolve_base_cell_size,
    resolve_sizing,
)
from rapidfoam.stl_utils import write_stl

# One triangle per model; only the bounding box matters for cell sizing.
# Flow is -z and up is +y, so z is the model length and x the lateral (span).
CAR = [((0.0, 1.0, 0.0), (0.0, 0.0, 0.0), (0.0, 1.2, 0.0), (1.4, 0.0, 3.0))]
WING = [((0.0, 1.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.3, 0.0), (1.2, 0.0, 0.35))]


class ScalingScaffold(unittest.TestCase):
    """Temporary project with one STL, plus generate/read helpers."""

    triangles = CAR
    stl_name = "model.stl"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_stl(self.root / "stl" / self.stl_name, "model", self.triangles)

    def config(self, **extra) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps({"case_name": "scale_case", "stl_files": [self.stl_name], **extra}))
        return path

    def generate(self, case_name: str, mesher: str = "cfmesh", **extra) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps({"case_name": case_name, "stl_files": [self.stl_name], **extra}))
        with contextlib.redirect_stdout(io.StringIO()):
            _do_generate(path, self.root, mesher=mesher)
        return self.root / "cases" / case_name

    @staticmethod
    def mesh_dict(case: Path) -> str:
        return (case / "system" / "meshDict").read_text()

    @staticmethod
    def snappy_dict(case: Path) -> str:
        return (case / "system" / "snappyHexMeshDict").read_text()

    @staticmethod
    def case_config(case: Path) -> dict:
        return json.loads((case / "case_config.json").read_text())


class PresetDefaultsTest(unittest.TestCase):
    """The shipped presets state relative sizing and resolve it in metres."""

    def test_presets_size_from_the_geometry(self):
        for name, preset in FIDELITY_PRESETS.items():
            self.assertEqual(preset["base_cell_size"], "auto", name)
            self.assertGreater(float(preset["cells_per_length"]), 0, name)
            self.assertNotIn("distance_levels", preset, name)  # shells are relative now
            self.assertIs(preset["trailing_edge_refine"], True, name)

    def test_presets_reproduce_the_old_absolute_values_at_three_metres(self):
        expected = {"fast": 0.15, "standard": 0.10, "fine": 0.08}
        for name, preset in FIDELITY_PRESETS.items():
            self.assertAlmostEqual(
                resolve_base_cell_size({}, preset, 3.0)[0], expected[name], places=4, msg=name
            )

    def test_auto_base_is_length_over_cells_per_length(self):
        standard = FIDELITY_PRESETS["standard"]
        self.assertEqual(resolve_base_cell_size({}, standard, 3.0), (0.10, "auto"))
        self.assertEqual(resolve_base_cell_size({}, standard, 1.2)[0], 0.04)
        car = resolve_base_cell_size({}, standard, 3.0)[0]
        wing = resolve_base_cell_size({}, standard, 1.2)[0]
        self.assertAlmostEqual(car / wing, 2.5)   # a wing is meshed 2.5x finer

    def test_default_cells_per_length_applies_without_a_preset(self):
        self.assertEqual(
            resolve_base_cell_size({}, {}, 1.2),
            (1.2 / DEFAULT_CELLS_PER_LENGTH, "auto"),
        )

    def test_explicit_metres_win_over_auto(self):
        preset = FIDELITY_PRESETS["standard"]
        self.assertEqual(
            resolve_base_cell_size({"base_cell_size": 0.25}, preset, 1.2), (0.25, "absolute")
        )
        # The literal "auto" still means the preset's cells_per_length.
        self.assertEqual(
            resolve_base_cell_size({"base_cell_size": "auto"}, preset, 1.2), (0.04, "auto")
        )
        # cells_per_length retunes the scaling for one case.
        self.assertAlmostEqual(
            resolve_base_cell_size({"cells_per_length": 60}, preset, 1.2)[0], 0.02
        )

    def test_bad_sizing_is_rejected(self):
        preset = FIDELITY_PRESETS["standard"]
        for bad in (0, -0.1, "coarse"):
            with self.assertRaises(ValueError, msg=str(bad)):
                resolve_base_cell_size({"base_cell_size": bad}, preset, 1.2)
        for bad in (0, -5, "many"):
            with self.assertRaises(ValueError, msg=str(bad)):
                resolve_base_cell_size({"cells_per_length": bad}, preset, 1.2)
        with self.assertRaises(ValueError):
            resolve_base_cell_size({}, preset, 0.0)


class SizingValidationTest(unittest.TestCase):
    """``validate`` accepts the auto keywords and rejects malformed values."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_stl(self.root / "stl" / "model.stl", "model", CAR)

    def config(self, **mesh_params) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps({
            "case_name": "validate_case",
            "stl_files": ["model.stl"],
            "mesh_params": mesh_params,
        }))
        return path

    def validate(self, **mesh_params):
        cfg = load_config(self.config(**mesh_params), project_dir=self.root)
        errors, _ = validate(cfg, self.root)
        return errors

    def test_auto_and_cells_per_length_are_valid(self):
        self.assertEqual(self.validate(base_cell_size="auto", cells_per_length=40), [])
        self.assertEqual(self.validate(base_cell_size=0.10), [])

    def test_malformed_sizing_is_reported(self):
        for key, value in (("base_cell_size", 0), ("base_cell_size", "tiny"),
                           ("cells_per_length", 0), ("cells_per_length", "many")):
            errors = self.validate(**{key: value})
            self.assertTrue(any(key in e for e in errors), f"{key}={value!r} -> {errors}")


class CarScaleGenerationTest(ScalingScaffold):
    """A 3.0 m car keeps the documented car-scale cells, TE box included."""

    def test_car_scale_matches_the_absolute_presets(self):
        case = self.generate("car")
        mesh = self.mesh_dict(case)
        self.assertIn("cellSize 0.00625;", mesh)          # 0.10 / 2**4
        self.assertIn("minCellSize         0.00625;", mesh)
        self.assertIn("trailingEdgeBox", mesh)            # on by default
        snapshot = self.case_config(case)
        self.assertEqual(snapshot["mesh_params"]["base_cell_size"], 0.1)
        self.assertEqual(snapshot["mesh_params"]["base_cell_size_mode"], "auto")
        self.assertEqual(snapshot["mesh_params"]["cells_per_length"], 30.0)

    def test_distance_shells_scale_with_the_model(self):
        car = self.generate("car", mesher="snappy")
        self.assertIn("(0.025 4) (0.08 3)", self.snappy_dict(car))
        self.assertIn("trailingEdgeBox", self.snappy_dict(car))


class WingScaleGenerationTest(ScalingScaffold):
    """A 1.2 m wing is meshed 2.5x finer than the car, without extra keys."""

    triangles = WING

    def test_wing_gets_finer_cells_automatically(self):
        case = self.generate("wing")
        mesh = self.mesh_dict(case)
        self.assertIn("cellSize 0.0025;", mesh)           # 0.04 / 2**4
        self.assertIn("minCellSize         0.0025;", mesh)
        self.assertIn("trailingEdgeBox", mesh)
        snapshot = self.case_config(case)
        self.assertEqual(snapshot["mesh_params"]["base_cell_size"], 0.04)
        self.assertEqual(snapshot["mesh_params"]["base_cell_size_mode"], "auto")

    def test_wing_shells_follow_the_scale(self):
        wing = self.generate("wing_snappy", mesher="snappy")
        self.assertIn("(0.01 4) (0.032 3)", self.snappy_dict(wing))

    def test_explicit_metres_restore_car_scale_cells(self):
        case = self.generate("wing_absolute", mesh_params={"base_cell_size": 0.10})
        self.assertIn("cellSize 0.00625;", self.mesh_dict(case))
        snapshot = self.case_config(case)
        self.assertEqual(snapshot["mesh_params"]["base_cell_size_mode"], "absolute")

    def test_cells_per_length_overrides_the_preset(self):
        case = self.generate("wing_dense", mesh_params={"cells_per_length": 60})
        sizing = resolve_sizing(self.case_config(case)["mesh_params"])
        self.assertAlmostEqual(sizing.base_cell_size, 0.02)
        self.assertAlmostEqual(sizing.body_cell_size, 0.00125)

    def test_trailing_edge_refine_can_be_switched_off(self):
        case = self.generate("wing_no_te", mesh_params={"trailing_edge_refine": False})
        self.assertNotIn("trailingEdgeBox", self.mesh_dict(case))


class WakeBoxScalingTest(ScalingScaffold):
    """Wake boxes are model fractions with relative levels, not absolutes.

    They used to be floored in metres (2.0 / 4.0 m long, 0.10-0.25 m thick), which
    the 3.0 m calibration turned into a small-model trap: the box stayed large while
    the cell size shrank with the model, so the box cost grew as 1/L**3 (a 1 m body
    asked for 4.5 M cells in nearWakeBox alone, 55 % of a standard mesh).
    """

    #: The scaffold car at half size: same shape, max_extent 1.5 m instead of 3.0.
    HALF_CAR = (((0.0, 1.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.6, 0.0), (0.7, 0.0, 1.5)),)

    def boxes(self, case_name: str, **extra) -> dict[str, dict]:
        """The two wake boxes of a generated case, keyed by name."""
        snapshot = self.case_config(self.generate(case_name, mesher="snappy", **extra))
        return {region["name"]: region
                for region in snapshot["mesh_params"]["refinement_regions"]}

    @staticmethod
    def length(box: dict) -> float:
        """Extent along the flow axis (the scaffold's flow is -z)."""
        return box["max"][2] - box["min"][2]

    def generate_small(self, case_name: str) -> dict[str, dict]:
        write_stl(self.root / "stl" / "small.stl", "small", self.HALF_CAR)
        path = self.root / "config.json"
        path.write_text(json.dumps({"case_name": case_name, "stl_files": ["small.stl"],
                                    "mesher": "snappy"}))
        with contextlib.redirect_stdout(io.StringIO()):
            _do_generate(path, self.root)
        snapshot = self.case_config(self.root / "cases" / case_name)
        return {region["name"]: region
                for region in snapshot["mesh_params"]["refinement_regions"]}

    def test_wake_boxes_scale_with_the_model(self):
        car = self.boxes("wake_car")
        small = self.generate_small("wake_small")
        self.assertAlmostEqual(self.length(car["nearWakeBox"]) / self.length(small["nearWakeBox"]),
                               2.0, places=3)
        self.assertAlmostEqual(self.length(car["farWakeBox"]) / self.length(small["farWakeBox"]),
                               2.0, places=3)

    def test_small_models_are_not_floored_in_metres(self):
        small = self.generate_small("wake_small_floor")
        # 1.2 model lengths (1.5 m) behind the body plus the 0.4 it covers = 2.4 m.
        # The old absolute 2.0 m floor would have made this 2.6 m; the box is a
        # fraction of the model now, so a half-size car gets a half-size wake box.
        self.assertAlmostEqual(self.length(small["nearWakeBox"]), 1.2 * 1.5 + 0.4 * 1.5, places=3)
        self.assertLess(self.length(small["nearWakeBox"]), 2.0 + 0.4 * 1.5)

    def test_wake_levels_follow_the_surface_level(self):
        default = self.boxes("wake_levels_default")
        self.assertEqual(default["nearWakeBox"]["level"], 3)   # standard: 4 - 1
        self.assertEqual(default["farWakeBox"]["level"], 1)    # 4 - 3

        deeper = self.boxes("wake_levels_deep", mesh_params={"surface_level": [6, 7]})
        self.assertEqual(deeper["nearWakeBox"]["level"], 5)
        self.assertEqual(deeper["farWakeBox"]["level"], 3)

        relative = self.boxes("wake_levels_relative",
                              mesh_params={"surface_level": [5, 6],
                                           "wake_levels_below_surface": [0, 2]})
        self.assertEqual(relative["nearWakeBox"]["level"], 5)
        self.assertEqual(relative["farWakeBox"]["level"], 3)

    def test_an_absolute_level_still_wins(self):
        absolute = self.boxes("wake_levels_absolute",
                              mesh_params={"surface_level": [6, 7], "near_wake_level": 2})
        self.assertEqual(absolute["nearWakeBox"]["level"], 2)
        self.assertEqual(absolute["farWakeBox"]["level"], 3)   # still 6 - 3

    def test_levels_cannot_go_negative(self):
        shallow = self.boxes("wake_levels_shallow",
                             mesh_params={"surface_level": [1, 2],
                                          "wake_levels_below_surface": [0, 5]})
        self.assertEqual(shallow["nearWakeBox"]["level"], 1)
        self.assertEqual(shallow["farWakeBox"]["level"], 0)


class WakeGapValidationTest(ScalingScaffold):
    """``wake_levels_below_surface`` is validated like every other mesh_params key."""

    def validate(self, value):
        cfg = load_config(self.config(mesh_params={"wake_levels_below_surface": value}),
                          project_dir=self.root)
        return validate(cfg, self.root)[0]

    def test_valid_gaps(self):
        for value in ([0, 0], [1, 3], [2, 2]):
            with self.subTest(value=value):
                self.assertEqual(self.validate(value), [])

    def test_malformed_gaps_are_rejected(self):
        for value in ([3, 1], [1], [1, 2, 3], [-1, 2], "near"):
            with self.subTest(value=value):
                errors = self.validate(value)
                self.assertTrue(any("wake_levels_below_surface" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
