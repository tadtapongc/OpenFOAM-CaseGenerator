"""Mesher profile split: per-mesher config merge and writer equivalence.

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
from rapidfoam.geometry import (
    MIN_CELL_SIZE_ALIASES,
    resolve_cell_sizes,
    resolve_first_layer_height,
    resolve_min_cell_size,
)
from rapidfoam.mesher_profiles import load_mesher_profile, resolve_mesher
from rapidfoam.stl_utils import write_stl

# A single triangle long in x, wide in y, thin in z: enough for domain + mesh
# derivation without needing an actual mesher.
TRIANGLES = [((0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.5, 0.0, 0.0), (0.0, 0.8, 0.4))]


class ProjectScaffold(unittest.TestCase):
    """Temporary project with one STL, plus config/generate helpers."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        write_stl(self.root / "stl" / "body.stl", "body", TRIANGLES)

    def config(self, **extra) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps({"case_name": "profile_case", "stl_files": ["body.stl"], **extra}))
        return path

    def generate(self, mesher: str, case_name: str, **extra) -> Path:
        path = self.root / "config.json"
        path.write_text(json.dumps({"case_name": case_name, "stl_files": ["body.stl"], **extra}))
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
    def layers_block(mesh_dict: str) -> str:
        block = mesh_dict.split("patchBoundaryLayers", 1)[1]
        return block.split("renameBoundary", 1)[0]

    @staticmethod
    def local_refinement(mesh_dict: str) -> str:
        return mesh_dict.split("localRefinement", 1)[1].split("objectRefinements", 1)[0]


class ProfileMergeTest(ProjectScaffold):
    """One case config, two engines, engine-native keys per profile."""

    def test_cfmesh_profile_supplies_native_defaults(self):
        cfg = load_config(self.config(), project_dir=self.root)
        self.assertEqual(cfg["mesher"], "cfmesh")
        self.assertEqual(cfg["mesh_params"]["cell_size_mode"], "absolute")
        self.assertIs(cfg["mesh_params"]["cell_budget_enforced"], False)
        self.assertEqual(cfg["cfmesh"]["layer_mode"], "patch_only")
        self.assertIs(cfg["cfmesh"]["ground_refine"], False)
        self.assertEqual(cfg["cfmesh"]["optimise_layer"], "auto")
        self.assertEqual(cfg["layers"]["first_layer_mode"], "relative")

    def test_snappy_profile_is_selected_by_config(self):
        cfg = load_config(self.config(mesher="snappy"), project_dir=self.root)
        self.assertEqual(cfg["mesher"], "snappy")
        self.assertEqual(cfg["mesh_params"]["cell_size_mode"], "relative_levels")
        self.assertIs(cfg["mesh_params"]["cell_budget_enforced"], True)
        # cfMesh-only policy keys must not leak into a snappy case
        self.assertNotIn("layer_mode", cfg["cfmesh"])

    def test_mesher_argument_overrides_the_config(self):
        path = self.config(mesher="cfmesh")
        as_snappy = load_config(path, mesher="snappy", project_dir=self.root)
        self.assertEqual(as_snappy["mesher"], "snappy")
        self.assertNotIn("layer_mode", as_snappy["cfmesh"])
        as_cfmesh = load_config(path, mesher="cfmesh", project_dir=self.root)
        self.assertEqual(as_cfmesh["cfmesh"]["layer_mode"], "patch_only")

    def test_case_values_beat_profile_values(self):
        cfg = load_config(self.config(cfmesh={"ground_refine": True, "optimise_layer": False}),
                          project_dir=self.root)
        self.assertIs(cfg["cfmesh"]["ground_refine"], True)
        self.assertIs(cfg["cfmesh"]["optimise_layer"], False)
        self.assertEqual(cfg["cfmesh"]["layer_mode"], "patch_only")  # untouched profile key survives

    def test_inline_mesh_params_block_applies_only_to_its_mesher(self):
        path = self.config(mesh_params_cfmesh={"body_cell_size": 0.02},
                           mesh_params_snappy={"surface_level": [2, 3]})
        as_cfmesh = load_config(path, project_dir=self.root)
        self.assertEqual(as_cfmesh["mesh_params"]["body_cell_size"], 0.02)
        self.assertNotIn("mesh_params_cfmesh", as_cfmesh)
        self.assertNotIn("mesh_params_snappy", as_cfmesh)

        as_snappy = load_config(path, mesher="snappy", project_dir=self.root)
        self.assertEqual(as_snappy["mesh_params"]["surface_level"], [2, 3])
        self.assertNotIn("body_cell_size", as_snappy["mesh_params"])

    def test_project_local_profile_overrides_shipped_profile(self):
        override = self.root / "configs" / "meshers"
        override.mkdir(parents=True)
        (override / "cfmesh.json").write_text(json.dumps({"cfmesh": {"optimise_layer": False}}))
        cfg = load_config(self.config(), project_dir=self.root)
        self.assertIs(cfg["cfmesh"]["optimise_layer"], False)
        self.assertEqual(cfg["cfmesh"]["layer_mode"], "patch_only")
        self.assertIs(load_mesher_profile("cfmesh", self.root)["cfmesh"]["optimise_layer"], False)

    def test_resolve_mesher_handles_the_legacy_dict_form(self):
        self.assertEqual(resolve_mesher({"mesher": {"type": "snappy"}}), "snappy")
        self.assertEqual(resolve_mesher({"mesher": "cfmesh"}), "cfmesh")
        self.assertEqual(resolve_mesher({}), "cfmesh")


class ProfileValidationTest(ProjectScaffold):
    """The split must not silently ignore keys or accept dead configurations."""

    def test_snappy_only_keys_are_flagged_for_cfmesh(self):
        cfg = load_config(self.config(mesh_params={"maxGlobalCells": 1000}), project_dir=self.root)
        _errors, warnings = validate(cfg, self.root)
        self.assertTrue(any("maxGlobalCells" in w for w in warnings), warnings)

    def test_absolute_first_layer_mode_requires_a_height(self):
        cfg = load_config(self.config(layers={"first_layer_mode": "absolute"}), project_dir=self.root)
        errors, _warnings = validate(cfg, self.root)
        self.assertTrue(any("first_layer_height" in e for e in errors), errors)

    def test_unknown_layer_mode_is_rejected(self):
        cfg = load_config(self.config(cfmesh={"layer_mode": "everywhere"}), project_dir=self.root)
        errors, _warnings = validate(cfg, self.root)
        self.assertTrue(any("layer_mode" in e for e in errors), errors)

    def test_unknown_optimise_layer_value_is_rejected(self):
        cfg = load_config(self.config(cfmesh={"optimise_layer": "maybe"}), project_dir=self.root)
        errors, _warnings = validate(cfg, self.root)
        self.assertTrue(any("optimise_layer" in e for e in errors), errors)

    def test_bad_trailing_edge_settings_are_rejected(self):
        cases = {
            "params": {"trailing_edge_refine": "yes"},
            "te_level": {"te_level": -1},
            "te_height_cells": {"te_height_cells": 0},
            "te_depth_cells": {"te_depth_cells": "deep"},
        }
        for expected, mesh_params in cases.items():
            with self.subTest(key=expected):
                cfg = load_config(self.config(mesh_params=mesh_params), project_dir=self.root)
                errors, _warnings = validate(cfg, self.root)
                self.assertTrue(any(expected in e for e in errors), errors)

    def test_auto_trailing_edge_level_is_accepted(self):
        cfg = load_config(self.config(mesh_params={"te_level": "auto"}), project_dir=self.root)
        errors, _warnings = validate(cfg, self.root)
        self.assertEqual(errors, [])


class TrailingEdgeRefinementTest(ProjectScaffold):
    """A thin trailing edge is resolved by a local box, not by a global floor.

    cfMesh's automatic curvature/proximity refinement stops at minCellSize, so
    the only local lever is an explicit refinement region. The scaffold STL is
    x 0..1.5, y 0..0.8, z 0..0.4 with the default -z flow, so the trailing-edge
    plane sits at z = 0.
    """

    def regions(self, mesh_dict: str) -> str:
        return mesh_dict.split("objectRefinements", 1)[1].split("boundaryLayers", 1)[0]

    def test_off_by_default(self):
        mesh_dict = self.mesh_dict(self.generate("cfmesh", "te_off"))
        self.assertNotIn("trailingEdgeBox", mesh_dict)

    def test_auto_level_is_one_finer_than_the_edge_cell(self):
        # 0.10 / 2**7 = 0.00078125 m, one level below snappy's edge cell.
        case = self.generate("cfmesh", "te_auto", mesh_params={"trailing_edge_refine": True})
        block = self.regions(self.mesh_dict(case))
        self.assertIn("trailingEdgeBox", block)
        self.assertIn("cellSize 0.000781;", block)

    def test_explicit_level_reaches_the_writer(self):
        case = self.generate("cfmesh", "te_level", mesh_params={"trailing_edge_refine": True,
                                                               "te_level": 6})
        expected = f"cellSize {round(0.10 / 2 ** 6, 6)};"
        self.assertIn(expected, self.regions(self.mesh_dict(case)))

    def test_box_hugs_the_downstream_face(self):
        case = self.generate("cfmesh", "te_box", mesh_params={"trailing_edge_refine": True})
        cfg = json.loads((case / "case_config.json").read_text())
        region = next(r for r in cfg["mesh_params"]["refinement_regions"]
                      if r["name"] == "trailingEdgeBox")
        # Three body cells upstream, one downstream; body cell = 0.10 / 2**4.
        # The writer rounds region extents to 0.1 mm.
        self.assertAlmostEqual(region["min"][2], -0.00625, delta=1e-4)
        self.assertAlmostEqual(region["max"][2], 0.01875, delta=1e-4)
        # Half-height band of two body cells around the body's mid-height (y = 0.4)
        self.assertAlmostEqual(region["min"][1], 0.3875, delta=1e-4)
        self.assertAlmostEqual(region["max"][1], 0.4125, delta=1e-4)
        self.assertEqual(region["level"], 7)

    def test_region_also_applies_to_snappy(self):
        case = self.generate("snappy", "te_snappy", mesh_params={"trailing_edge_refine": True})
        snappy_dict = self.snappy_dict(case)
        self.assertIn("trailingEdgeBox", snappy_dict)
        self.assertIn("mode inside", snappy_dict)
        self.assertNotIn("trailingEdgeBox", self.snappy_dict(self.generate("snappy", "te_snappy_off")))

    def test_user_region_with_the_same_name_wins(self):
        custom = [{"name": "trailingEdgeBox", "min": [0.0, 0.3, -0.02],
                   "max": [1.0, 0.5, 0.02], "level": 5}]
        case = self.generate("cfmesh", "te_custom", mesh_params={
            "trailing_edge_refine": True, "refinement_regions": custom})
        cfg = json.loads((case / "case_config.json").read_text())
        regions = [r for r in cfg["mesh_params"]["refinement_regions"]
                   if r["name"] == "trailingEdgeBox"]
        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["level"], 5)


class ParallelMeshingProfileTest(ProjectScaffold):
    """cfmesh.parallel_meshing selects the MPI mesh path."""

    def test_profile_defaults_to_auto(self):
        cfg = load_config(self.config(), project_dir=self.root)
        self.assertEqual(cfg["cfmesh"]["parallel_meshing"], "auto")

    def test_explicit_values_are_accepted(self):
        for value in (True, False, "auto"):
            with self.subTest(value=value):
                cfg = load_config(self.config(cfmesh={"parallel_meshing": value}),
                                  project_dir=self.root)
                errors, _warnings = validate(cfg, self.root)
                self.assertEqual(errors, [])


class CellSizeResolutionTest(unittest.TestCase):
    """Levels and absolute sizes must resolve to the same metres."""

    def test_levels_and_absolute_modes_agree(self):
        levels = resolve_cell_sizes({"base_cell_size": 0.10, "surface_level": [4, 5], "edge_level": 6})
        absolute = resolve_cell_sizes({"base_cell_size": 0.10, "body_cell_size": 0.00625})
        self.assertEqual(levels["mode"], "relative_levels")
        self.assertEqual(absolute["mode"], "absolute")
        self.assertAlmostEqual(levels["body"], absolute["body"])
        self.assertAlmostEqual(levels["edge"], 0.0015625)
        # cfMesh's floor is a *global* one, so it follows the body cell rather
        # than the edge cell snappy only uses on feature-edge cells.
        self.assertAlmostEqual(levels["min"], levels["body"])

    def test_first_layer_relative_and_absolute_agree(self):
        relative = resolve_first_layer_height({"first_layer_thickness": 0.3}, 0.00625)
        absolute = resolve_first_layer_height(
            {"first_layer_mode": "absolute", "first_layer_height": 0.001875}, 0.00625)
        self.assertAlmostEqual(relative, absolute)


class WriterEquivalenceTest(ProjectScaffold):
    """What the two writers emit for the same physical intent."""

    def test_body_cell_size_means_the_same_to_both_writers(self):
        extra = {"mesh_params": {"base_cell_size": 0.10, "body_cell_size": 0.00625}}
        cfmesh_dict = self.mesh_dict(self.generate("cfmesh", "eq_cfmesh", **extra))
        self.assertIn("cellSize 0.00625;", cfmesh_dict)
        self.assertNotIn("cellSize 0.003125;", cfmesh_dict)  # level[1] no longer drives the body

        snappy_dict = self.snappy_dict(self.generate("snappy", "eq_snappy", **extra))
        self.assertIn("level (4 5)", snappy_dict)  # 0.10 / 2**4 = 0.00625

    def test_cfmesh_surface_refinement_uses_the_body_level(self):
        case = self.generate("cfmesh", "cf_body_level",
                             mesh_params={"base_cell_size": 0.10, "surface_level": [4, 5]})
        cfmesh_dict = self.mesh_dict(case)
        self.assertIn("cellSize 0.00625;", cfmesh_dict)
        self.assertIn("minCellSize         0.00625;", cfmesh_dict)  # floor = body cell

    def test_cfmesh_layers_only_the_stl_surfaces_by_default(self):
        cfmesh_dict = self.mesh_dict(self.generate("cfmesh", "cf_default_layers"))
        self.assertIn("nLayers             0;", cfmesh_dict)
        block = self.layers_block(cfmesh_dict)
        self.assertIn("body", block)
        self.assertNotIn("ground", block)

    def test_ground_layers_flag_layers_the_road(self):
        case = self.generate("cfmesh", "cf_ground_layers", layers={"ground_layers": True})
        self.assertIn("ground", self.layers_block(self.mesh_dict(case)))

    def test_ground_refinement_is_opt_in(self):
        off = self.mesh_dict(self.generate("cfmesh", "cf_no_ground"))
        self.assertNotIn("ground", self.local_refinement(off))
        on = self.mesh_dict(self.generate("cfmesh", "cf_ground", cfmesh={"ground_refine": True}))
        self.assertIn("ground", self.local_refinement(on))

    def test_optimise_layer_auto_follows_fidelity(self):
        fast = self.mesh_dict(self.generate("cfmesh", "cf_fast", fidelity="fast"))
        self.assertIn("optimiseLayer 0;", fast)
        self.assertNotIn("optimisationParameters", fast)

        standard = self.mesh_dict(self.generate("cfmesh", "cf_standard"))
        self.assertIn("optimiseLayer 1;", standard)
        self.assertIn("optimisationParameters", standard)

    def test_absolute_first_layer_height_is_written_to_cfmesh(self):
        case = self.generate("cfmesh", "cf_abs_layer",
                             layers={"first_layer_mode": "absolute", "first_layer_height": 0.002})
        self.assertIn("maxFirstLayerThickness 0.002;", self.mesh_dict(case))

    def test_snappy_first_layer_fraction_matches_the_absolute_intent(self):
        case = self.generate("snappy", "sn_abs_layer",
                             mesh_params={"base_cell_size": 0.10, "body_cell_size": 0.00625},
                             layers={"first_layer_mode": "absolute", "first_layer_height": 0.001875})
        self.assertIn("firstLayerThickness     0.3;", self.snappy_dict(case))

    def test_refinement_thickness_is_emitted_when_requested(self):
        case = self.generate("cfmesh", "cf_thickness", cfmesh={"refinement_thickness": 0.04})
        self.assertIn("refinementThickness 0.04;", self.mesh_dict(case))

    def test_case_config_snapshot_records_the_resolved_profile(self):
        case = self.generate("cfmesh", "cf_snapshot")
        snapshot = json.loads((case / "case_config.json").read_text())
        self.assertEqual(snapshot["mesher"], "cfmesh")
        self.assertEqual(snapshot["cfmesh"]["layer_mode"], "patch_only")
        self.assertIs(snapshot["mesh_params"]["cell_budget_enforced"], False)


class CfMeshRefinementFloorTest(ProjectScaffold):
    """cfMesh's minCellSize is a *global* floor, so it follows the body cell.

    Flooring it at snappy's ``edge_level`` cell refined every surface cell two
    levels deeper than snappy and produced 4.4M cells where snappy needed 449k
    (the mesher itself was only 5 min of that run — the cell count drove the
    solve).
    """

    def test_profile_floors_cfmesh_at_the_body_cell(self):
        cfg = load_config(self.config(), project_dir=self.root)
        self.assertEqual(cfg["mesh_params"]["min_cell_size"], "body")
        sizes = resolve_cell_sizes(cfg["mesh_params"])
        self.assertAlmostEqual(sizes["body"], 0.00625)     # 0.10 / 2**4
        self.assertAlmostEqual(sizes["min"], sizes["body"])
        self.assertAlmostEqual(sizes["edge"], 0.0015625)   # 0.10 / 2**6, snappy-only

    def test_cfmesh_mesh_dict_floors_at_the_body_cell(self):
        cfmesh_dict = self.mesh_dict(self.generate("cfmesh", "cf_floor"))
        self.assertIn("minCellSize         0.00625;", cfmesh_dict)
        self.assertIn("cellSize 0.00625;", cfmesh_dict)  # same cell as the surface

    def test_aliases_resolve_to_the_matching_cell_size(self):
        sizes = resolve_cell_sizes({"base_cell_size": 0.10, "surface_level": [4, 5], "edge_level": 6})
        cases = {"base": sizes["base"], "body": sizes["body"], "surface": sizes["body"],
                 "edge": sizes["edge"], "feature": sizes["edge"]}
        self.assertEqual(set(cases), set(MIN_CELL_SIZE_ALIASES))
        for alias, expected in cases.items():
            self.assertAlmostEqual(
                resolve_min_cell_size(alias, base=sizes["base"], body=sizes["body"], edge=sizes["edge"]),
                expected, msg=alias)

    def test_unset_floor_defaults_to_the_body_cell(self):
        sizes = resolve_cell_sizes({"base_cell_size": 0.10, "surface_level": [4, 5]})
        self.assertAlmostEqual(sizes["min"], sizes["body"])

    def test_numeric_floor_and_edge_alias_still_reach_the_writer(self):
        numeric = self.generate("cfmesh", "cf_floor_numeric", mesh_params={"min_cell_size": 0.003})
        self.assertIn("minCellSize         0.003;", self.mesh_dict(numeric))
        alias = self.generate("cfmesh", "cf_floor_edge", mesh_params={"min_cell_size": "edge"})
        self.assertIn("minCellSize         0.0015625;", self.mesh_dict(alias))

    def test_bad_floor_is_reported(self):
        for bad in ("tiny", 0.0, -1.0):
            with self.assertRaises(ValueError):
                resolve_min_cell_size(bad, base=0.1, body=0.00625, edge=0.0015625)
        cfg = load_config(self.config(mesh_params={"min_cell_size": "tiny"}), project_dir=self.root)
        errors, _warnings = validate(cfg, self.root)
        self.assertTrue(any("min_cell_size" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
