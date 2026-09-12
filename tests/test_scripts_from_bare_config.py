"""Writing scripts must not need the geometry to be resolved first.

``cli.py`` resolves ``domain_box`` and ``mesh_params`` from the STL bounds before
it calls :func:`rapidfoam.writers.scripts.write_scripts`, but ``write_scripts`` is
also usable on its own with a case config and nothing else — that is exactly what
``tests/test_shell_scripts.py`` does with a bare ``DEFAULT_CONFIG``. That test is
``skipUnless(posix and bash)``, so the two ways an unresolved config used to break
script writing only ever showed up on the Linux CI jobs:

    KeyError: 'min'                          # snappy settings wanted a domain box
    ValueError: base_cell_size 'auto' ...    # cfMesh sizing wanted metres

The meshing plan is deliberately derived from the config alone (see
``meshers/*/plan.py``), so the commands for ``Allrun``/``run.sh`` no longer depend
on the resolved domain box. These tests pin that, and pin that the config-only plan
still equals the one built from resolved settings (so the scripts and the
dictionaries cannot drift apart).

Run with python -m unittest discover -s tests.
"""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rapidfoam.config import DEFAULT_CONFIG
from rapidfoam.geometry import compute_domain_box
from rapidfoam.meshers import get_mesher
from rapidfoam.meshers.cfmesh import (
    cfmesh_mesh_plan,
    cfmesh_plan_from_config,
    resolve_cfmesh_settings,
)
from rapidfoam.meshers.refinement import resolve_mesh_params
from rapidfoam.meshers.snappy import (
    resolve_snappy_settings,
    snappy_mesh_plan,
    snappy_plan_from_config,
)
from rapidfoam.writers.scripts import write_scripts

#: The scripts ``write_scripts`` is documented to generate.
SCRIPTS = ("Allrun", "Allrun.parallel", "Allclean", "run.sh", "convergence_monitor.py")

#: A stand-in for the STL bounds ``cli.py`` measures before resolving the mesh.
BOUNDS = ((0.0, 0.0, 0.0), (1.0, 0.8, 0.4))


class ScriptsFromBareConfigTest(unittest.TestCase):
    """A case config on its own is enough to render the scripts."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="rapidfoam_scripts_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def bare_config(self, mesher: str) -> dict:
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["mesher"] = mesher
        return cfg

    def resolved_config(self, mesher: str, n_procs: int = 1, **engine) -> dict:
        cfg = self.bare_config(mesher)
        cfg["parallel"]["n_procs"] = n_procs
        if engine:
            cfg[mesher] = {**cfg.get(mesher, {}), **engine}
        cfg["mesh_params"] = resolve_mesh_params(cfg, BOUNDS)
        cfg["domain_box"] = compute_domain_box(cfg, BOUNDS)
        return cfg

    def case_dir(self, name: str) -> Path:
        case = self.root / name
        (case / "system").mkdir(parents=True)
        (case / "system" / "controlDict").write_text("stopAt endTime;\n")
        return case

    def test_default_config_ships_an_unresolved_case(self):
        """The template is what the tests above rely on: no box, sizing still "auto"."""
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        self.assertNotIn("domain_box", cfg)
        self.assertEqual(cfg["mesh_params"]["base_cell_size"], "auto")

    def test_write_scripts_accepts_a_bare_config(self):
        for mesher in ("snappy", "cfmesh"):
            with self.subTest(mesher=mesher):
                case = self.case_dir(mesher)
                write_scripts(self.bare_config(mesher), case)
                for name in SCRIPTS:
                    self.assertTrue((case / name).exists(), f"{mesher}: {name}")

    def test_registry_plan_needs_no_geometry(self):
        for mesher in ("snappy", "cfmesh"):
            with self.subTest(mesher=mesher):
                plan = get_mesher(mesher).mesh_plan(self.bare_config(mesher))
                self.assertEqual(plan.label.split()[0], "snappyHexMesh" if mesher == "snappy"
                                 else "cfMesh")

    def test_snappy_plan_matches_the_resolved_settings(self):
        for n_procs in (1, 4):
            with self.subTest(n_procs=n_procs):
                cfg = self.resolved_config("snappy", n_procs=n_procs)
                self.assertEqual(
                    snappy_plan_from_config(cfg),
                    snappy_mesh_plan(resolve_snappy_settings(cfg)),
                )

    def test_cfmesh_plan_matches_the_resolved_settings(self):
        for engine in ({}, {"feature_angle": 60.0}):
            for n_procs in (1, 4):
                with self.subTest(engine=engine, n_procs=n_procs):
                    cfg = self.resolved_config("cfmesh", n_procs=n_procs, **engine)
                    self.assertEqual(
                        cfmesh_plan_from_config(cfg),
                        cfmesh_mesh_plan(resolve_cfmesh_settings(cfg)),
                    )

    def test_cfmesh_plan_carries_the_declared_crease_angle(self):
        plan = cfmesh_plan_from_config(self.bare_config("cfmesh"))
        surface = next(c for c in plan.commands if c.tool == "surfaceFeatureEdges")
        self.assertIn("45", surface.args)

        declared = self.bare_config("cfmesh")
        declared["cfmesh"] = {**declared.get("cfmesh", {}), "feature_angle": 60}
        plan = cfmesh_plan_from_config(declared)
        surface = next(c for c in plan.commands if c.tool == "surfaceFeatureEdges")
        self.assertIn("60", surface.args)

    def test_mpi_plan_follows_the_rank_count_without_geometry(self):
        serial = self.bare_config("snappy")
        serial["parallel"] = {**serial["parallel"], "n_procs": 1}
        parallel = self.bare_config("snappy")
        parallel["parallel"] = {**parallel["parallel"], "n_procs": 4}
        self.assertFalse(snappy_plan_from_config(serial).parallel_meshing)
        self.assertTrue(snappy_plan_from_config(parallel).parallel_meshing)


if __name__ == "__main__":
    unittest.main()
