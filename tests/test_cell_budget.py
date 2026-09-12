"""Cell-budget estimates — the per-region pricing the CLI prints and the API returns.

The estimate is what turns "the mesh is too fine here and too coarse there" into a
number before a run: every refinement region and distance shell is priced as
``volume / cell_size**3``, and the total is checked against ``maxGlobalCells``,
because snappy stops refining once the cap is reached.

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
from rapidfoam.config import resolve_config_dict
from rapidfoam.meshers.budget import budget_from_case, estimate_cell_budget
from rapidfoam.stl_utils import stl_surface_area, write_stl

#: A 1.0 x 1.0 m square in the z = 0 plane: two triangles, 1 m2 of surface.
SQUARE = [((0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
          ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0))]

#: Domain box + one 1 m3 box at level 3 keep every number in these tests exact.
EXACT = {
    "base_cell_size": 0.10,
    "surface_level": [4, 5],
    "trailing_edge_refine": False,
    "refinement_regions": [
        {"name": "wakeBox", "min": [0.0, 0.0, -1.0], "max": [1.0, 1.0, 0.0], "level": 3},
    ],
}


class BudgetScaffold(unittest.TestCase):
    """Temporary project with one STL, plus generate/estimate helpers."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stl_dir = self.root / "stl"
        write_stl(self.stl_dir / "body.stl", "body", SQUARE)

    def config(self, **extra) -> dict:
        return {"case_name": "budget_case", "stl_files": ["body.stl"],
                "domain_box": {"min": [0.0, 0.0, -2.0], "max": [1.0, 1.0, 2.0]}, **extra}

    def generate(self, **extra) -> tuple[dict, str]:
        """Generate a case; returns its ``case_config.json`` and the console text."""
        path = self.root / "config.json"
        path.write_text(json.dumps(self.config(**extra)))
        echo = io.StringIO()
        with contextlib.redirect_stdout(echo):
            _do_generate(path, self.root)
        snapshot = json.loads((self.root / "cases/budget_case/case_config.json").read_text())
        return snapshot, echo.getvalue()

    def budget(self, **extra):
        snapshot, _text = self.generate(**extra)
        area = stl_surface_area(self.stl_dir / "body.stl")
        return estimate_cell_budget(snapshot, surface_area=area)


class CellBudgetTest(BudgetScaffold):
    def test_prices_every_region_and_totals_them(self):
        budget = self.budget(mesher="snappy", mesh_params=dict(EXACT))
        # 10 x 10 x 40 background cells at 0.10 m.
        self.assertEqual(budget.region("background (blockMesh)").cells, 4_000)
        # 1 m3 box at level 3 -> (0.10 / 8) = 12.5 mm cells.
        self.assertEqual(budget.region("wakeBox").cells, 512_000)
        # The preset's shells: a 25 mm band at level 4, then 25-80 mm at level 3.
        self.assertEqual(budget.region("surface shell 25 mm").cells, 102_400)
        self.assertEqual(budget.region("surface shell 80 mm").cells, 28_160)
        self.assertEqual(budget.total_cells, sum(item.cells for item in budget.regions))
        self.assertEqual(budget.total_cells, 646_560)
        self.assertEqual(budget.engine, "snappy")
        self.assertEqual(budget.cap, 18_000_000)

    def test_the_cli_prints_the_report(self):
        _snapshot, text = self.generate(mesher="snappy", mesh_params=dict(EXACT))
        self.assertIn("Cell budget (estimate", text)
        self.assertIn("background (blockMesh)", text)
        self.assertIn("wakeBox", text)
        self.assertIn("estimated total", text)

    def test_warns_when_the_regions_exceed_the_cap(self):
        budget = self.budget(mesher="snappy",
                             mesh_params={**EXACT, "maxGlobalCells": 100_000})
        self.assertEqual(budget.cap, 100_000)
        messages = budget.warnings()
        self.assertTrue(any("maxGlobalCells" in m and "stops refining" in m for m in messages),
                        messages)
        self.assertGreater(budget.share_of_cap, 1.0)

    def test_names_the_region_that_dominates_the_total(self):
        budget = self.budget(mesher="snappy", mesh_params=dict(EXACT))
        self.assertEqual(budget.dominant.label, "wakeBox")
        self.assertTrue(any("'wakeBox' alone asks for" in m and "8x cheaper" in m
                            for m in budget.warnings()), budget.warnings())

    def test_a_balanced_case_has_nothing_to_report(self):
        balanced = {**EXACT,
                    "distance_shells": [],
                    "refinement_regions": [
                        {"name": "boxA", "min": [0.0, 0.0, -1.0], "max": [1.0, 1.0, 0.0],
                         "level": 3},
                        {"name": "boxB", "min": [0.0, 0.0, -2.0], "max": [1.0, 1.0, -1.0],
                         "level": 3},
                    ]}
        budget = self.budget(mesher="snappy", mesh_params=balanced)
        self.assertEqual(budget.warnings(), [])

    def test_cfmesh_is_priced_without_a_cap(self):
        budget = self.budget(mesher="cfmesh", mesh_params=dict(EXACT))
        self.assertEqual(budget.engine, "cfmesh")
        self.assertIsNone(budget.cap)
        self.assertIsNotNone(budget.region("surface (localRefinement)"))
        self.assertIsNotNone(budget.region("background (maxCellSize)"))
        self.assertFalse(any("maxGlobalCells" in m for m in budget.warnings()))

    def test_report_and_dict_agree(self):
        budget = self.budget(mesher="snappy", mesh_params=dict(EXACT))
        payload = budget.as_dict()
        self.assertEqual(payload["total_cells"], budget.total_cells)
        self.assertEqual(len(payload["regions"]), len(budget.regions))
        self.assertEqual(payload["warnings"], budget.warnings())


class BudgetFromCaseTest(BudgetScaffold):
    def test_prices_a_config_without_geometry(self):
        merged = resolve_config_dict(self.config(mesher="snappy"))
        budget = budget_from_case(merged, self.stl_dir)
        self.assertIsNotNone(budget)
        self.assertIsNotNone(budget.region("background (blockMesh)"))
        self.assertIsNotNone(budget.region("trailingEdgeBox"))

    def test_missing_stls_price_nothing(self):
        merged = resolve_config_dict(self.config(mesher="snappy", stl_files=["absent.stl"]))
        self.assertIsNone(budget_from_case(merged, self.stl_dir))


class SurfaceAreaTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_area_of_a_known_square(self):
        write_stl(self.root / "square.stl", "square", SQUARE)
        self.assertAlmostEqual(stl_surface_area(self.root / "square.stl"), 1.0)

    def test_area_of_one_triangle(self):
        write_stl(self.root / "triangle.stl", "triangle", [SQUARE[0]])
        self.assertAlmostEqual(stl_surface_area(self.root / "triangle.stl"), 0.5)

    def test_missing_file_is_reported(self):
        with self.assertRaises(FileNotFoundError):
            stl_surface_area(self.root / "absent.stl")


if __name__ == "__main__":
    unittest.main()
