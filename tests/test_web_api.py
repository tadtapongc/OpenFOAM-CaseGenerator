"""Automated tests for Web API endpoints and Cluster SSH client using standard unittest."""

import asyncio
import shutil
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi import HTTPException

from cfd_gen.web.server import (
    DomainBoxRequest,
    GenerateCaseRequest,
    JobCancelRequest,
    api_get_saved_config,
    api_config_defaults,
    api_config_load_file,
    api_config_templates,
    api_stl_list,
    api_get_stl_file,
    api_case_generate_and_submit,
    api_case_cancel,
    api_geometry_domain_box,
    api_telemetry_forces,
    api_telemetry_residuals,
    api_telemetry_logs,
    api_list_cases,
    api_case_delete,
)
from cfd_gen.web.ssh_client import ClusterSSHClient


class TestWebAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_stl = Path("stl/sample_wing.stl")
        if not cls.sample_stl.exists():
            cls.sample_stl.parent.mkdir(parents=True, exist_ok=True)
            cls.sample_stl.write_text(
                "solid sample_wing\n"
                "  facet normal 0 0 1\n"
                "    outer loop\n"
                "      vertex 0 0 0\n"
                "      vertex 1 0 0\n"
                "      vertex 0 1 0\n"
                "    endloop\n"
                "  endfacet\n"
                "endsolid sample_wing\n"
            )
            cls.created_stl = True
        else:
            cls.created_stl = False

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "created_stl", False) and cls.sample_stl.exists():
            cls.sample_stl.unlink(missing_ok=True)

    def test_saved_cluster_config(self):
        """Test retrieving cached cluster config with password redacted."""
        res = asyncio.run(api_get_saved_config())
        self.assertIn("host", res)
        self.assertIn("username", res)
        self.assertIn("remote_repo_path", res)
        self.assertIn("has_saved_password", res)
        self.assertNotIn("saved_password", res)

    def test_config_schema_defaults(self):
        """Test schema defaults endpoint."""
        res = asyncio.run(api_config_defaults())
        self.assertIn("default_config", res)
        self.assertIn("fidelity_presets", res)
        self.assertIn("fast", res["fidelity_presets"])
        self.assertIn("standard", res["fidelity_presets"])

    def test_config_templates(self):
        """Test templates list endpoint."""
        templates = asyncio.run(api_config_templates())
        self.assertIsInstance(templates, list)
        self.assertTrue(any(t["filename"] == "config.json" for t in templates))

    def test_config_load_file(self):
        """Test loading config.json."""
        res = asyncio.run(api_config_load_file("config.json"))
        self.assertEqual(res["filename"], "config.json")
        self.assertIn("raw_config", res)
        self.assertEqual(res["raw_config"]["case_name"], "my_case")

    def test_config_load_file_traversal_blocked(self):
        """Test that directory traversal in load-file is blocked."""
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(api_config_load_file("../secret.json"))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_stl_list(self):
        """Test listing STLs in stl/ directory without duplicate paths."""
        stls = asyncio.run(api_stl_list())
        self.assertIsInstance(stls, list)
        filenames = [s["filename"] for s in stls]
        self.assertEqual(len(filenames), len(set(filenames)))

    def test_stl_file_serving(self):
        """Test serving raw STL file."""
        res = asyncio.run(api_get_stl_file("sample_wing.stl"))
        self.assertEqual(res.status_code, 200)
        self.assertTrue(Path(res.path).exists())

    def test_validation_endpoint(self):
        """Test generating/validating a config."""
        test_cfg_path = Path("configs/test_case_web.json")
        self.addCleanup(lambda: test_cfg_path.unlink(missing_ok=True))

        valid_cfg = {
            "case_name": "test_case_web",
            "stl_files": ["sample_wing.stl"],
            "flow": {"velocity": 20.0, "direction": "-z", "ground": True},
            "outputs": {"drag_axis": "-z", "downforce_axis": "-y"},
            "parallel": {"n_procs": 16},
        }

        req = GenerateCaseRequest(
            config=valid_cfg,
            upload_to_cluster=False,
            generate_remotely=False,
            submit_slurm=False,
            generate_locally=False,
        )
        res = asyncio.run(api_case_generate_and_submit(req))
        self.assertTrue(res["success"])
        self.assertEqual(res["case_name"], "test_case_web")

    def test_case_name_validation_injection(self):
        """Test that malicious case names are rejected."""
        invalid_cfgs = [
            {"case_name": "bad;name", "stl_files": ["sample_wing.stl"]},
            {"case_name": "bad'name", "stl_files": ["sample_wing.stl"]},
            {"case_name": "bad name", "stl_files": ["sample_wing.stl"]},
        ]
        for cfg in invalid_cfgs:
            req = GenerateCaseRequest(
                config=cfg,
                upload_to_cluster=False,
                generate_remotely=False,
                submit_slurm=False,
                generate_locally=False,
            )
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(api_case_generate_and_submit(req))
            self.assertEqual(ctx.exception.status_code, 400)

    def test_job_id_validation_injection(self):
        """Test that non-numeric job IDs are rejected in job cancel."""
        req = JobCancelRequest(job_id="123; rm -rf /")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(api_case_cancel(req))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_local_case_generation(self):
        """Test local case generation through the API endpoint."""
        case_name = "test_case_local_gen"
        test_cfg_path = Path(f"configs/{case_name}.json")
        test_case_dir = Path(f"cases/{case_name}")
        self.addCleanup(lambda: test_cfg_path.unlink(missing_ok=True))
        self.addCleanup(lambda: shutil.rmtree(test_case_dir, ignore_errors=True))

        valid_cfg = {
            "case_name": case_name,
            "stl_files": ["sample_wing.stl"],
            "flow": {"velocity": 20.0, "direction": "-z", "ground": True},
            "outputs": {"drag_axis": "-z", "downforce_axis": "-y"},
            "parallel": {"n_procs": 8},
        }

        req = GenerateCaseRequest(
            config=valid_cfg,
            upload_to_cluster=False,
            generate_remotely=False,
            submit_slurm=False,
            generate_locally=True,
        )
        res = asyncio.run(api_case_generate_and_submit(req))
        self.assertTrue(res["success"])
        self.assertTrue(res["local_actions"].get("generated_locally"))
        self.assertTrue((test_case_dir / "system" / "controlDict").is_file())

    def test_telemetry_logs_whitelist(self):
        """Test that arbitrary log_types are rejected."""
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(api_telemetry_logs("my_case", log_type="malicious_type"))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_telemetry_forces_and_convergence(self):
        """Test telemetry forces calculation and symmetry scaling."""
        case_name = "test_case_telemetry"
        case_dir = Path(f"cases/{case_name}")
        forces_dir = case_dir / "postProcessing" / "forces" / "0"
        forces_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(case_dir, ignore_errors=True))

        # Write force.dat with total(fx fy fz)
        force_lines = ["# Time total(fx fy fz) pressure(fx fy fz) viscous(fx fy fz)\n"]
        for i in range(1, 60):
            # t, total(0.0 -200.0 -50.0) -> fy=-200, fz=-50
            force_lines.append(f"{i} (0.0 -200.0 -50.0) (0 0 0) (0 0 0)\n")
        (forces_dir / "force.dat").write_text("".join(force_lines))

        res = asyncio.run(api_telemetry_forces(case_name))
        self.assertTrue(res["has_data"])
        self.assertEqual(res["case_name"], case_name)
        self.assertEqual(res["total_iterations"], 59)
        # Default axes: drag = -fz = 50.0, df = -fy = 200.0
        self.assertAlmostEqual(res["drag_avg"], 50.0, places=1)
        self.assertAlmostEqual(res["downforce_avg"], 200.0, places=1)

    def test_telemetry_residuals_alignment(self):
        """Test telemetry residuals alignment where variable arrays have equal length."""
        case_name = "test_case_residuals"
        case_dir = Path(f"cases/{case_name}")
        case_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(case_dir, ignore_errors=True))

        log_lines = []
        for it in range(1, 15):
            log_lines.append(f"Time = {it}\n")
            log_lines.append("Solving for Ux, Initial residual = 0.05, Final residual = 0.001, No Iterations 5\n")
            log_lines.append("Solving for Uy, Initial residual = 0.04, Final residual = 0.001, No Iterations 5\n")
            log_lines.append("Solving for Uz, Initial residual = 0.03, Final residual = 0.001, No Iterations 5\n")
            # Multiple p correctors
            log_lines.append("Solving for p, Initial residual = 0.02, Final residual = 0.001, No Iterations 10\n")
            log_lines.append("Solving for p, Initial residual = 0.005, Final residual = 0.0001, No Iterations 10\n")
            log_lines.append("Solving for k, Initial residual = 0.01, Final residual = 0.0005, No Iterations 3\n")
            log_lines.append("Solving for omega, Initial residual = 0.008, Final residual = 0.0002, No Iterations 3\n")
        (case_dir / "log.simpleFoam").write_text("".join(log_lines))

        res = asyncio.run(api_telemetry_residuals(case_name))
        self.assertTrue(res["has_data"])
        n_iters = len(res["iterations"])
        self.assertEqual(n_iters, 14)
        for var, series in res["residuals"].items():
            self.assertEqual(len(series), n_iters, f"Residuals for {var} must match iteration count")
        # Ensure initial residual for p was captured (0.02), not the second corrector (0.005)
        self.assertAlmostEqual(res["residuals"]["p"][0], 0.02)

    def test_ssh_client_parse_squeue(self):
        """Test SLURM squeue parsing logic."""
        c = ClusterSSHClient()
        mock_squeue_output = (
            "1234567|aero_sim|cpu|RUNNING|00:15:22|08:00:00|1|None\n"
            "1234568|Wing_V2|cpu|PENDING|00:00:00|04:00:00|1|Priority\n"
        )
        with patch.object(c, "run_command", return_value=(0, mock_squeue_output, "")):
            jobs = c.get_slurm_queue("testuser")
            self.assertEqual(len(jobs), 2)
            self.assertEqual(jobs[0]["job_id"], "1234567")
            self.assertEqual(jobs[0]["name"], "aero_sim")
            self.assertEqual(jobs[0]["state"], "RUNNING")
            self.assertEqual(jobs[1]["state"], "PENDING")

    def test_ssh_client_submit_job(self):
        """Test SLURM sbatch submission parsing."""
        c = ClusterSSHClient()
        c.remote_repo_path = "/work/home/testuser/repo"
        mock_sbatch_out = "Submitted batch job 987654\n"
        with patch.object(c, "run_command", return_value=(0, mock_sbatch_out, "")):
            res = c.submit_job("case_test")
            self.assertTrue(res["success"])
            self.assertEqual(res["job_id"], "987654")

    def test_geometry_domain_box(self):
        """Test computing wind tunnel domain box from geometry bounds."""
        req = DomainBoxRequest(
            config={
                "flow": {"velocity": 16.67, "direction": "-z", "ground": True},
                "fidelity": "standard",
                "symmetry_plane": -0.1185,
                "ground_clearance": 0.035,
            },
            bounds={"min": [-0.7, 0.035, -1.8], "max": [0.7, 1.1, 1.2]},
        )
        res = asyncio.run(api_geometry_domain_box(req))
        self.assertIn("domain_box", res)
        self.assertIn("min", res["domain_box"])
        self.assertIn("max", res["domain_box"])
        self.assertEqual(len(res["domain_box"]["min"]), 3)
        self.assertEqual(len(res["domain_box"]["max"]), 3)

    def test_ground_clearance_styles(self):
        """Test 2 + 1 ground clearance styles: None (touching CAD bottom), Relative, and Absolute."""
        bounds = {"min": [-0.7, 0.035, -1.8], "max": [0.7, 1.1, 1.2]}
        base_cfg = {
            "flow": {"velocity": 16.67, "direction": "-z", "ground": True},
            "fidelity": "standard",
            "symmetry_plane": -0.1185,
        }

        # Style 0 / None (Default): road touches lowest CAD vertex smin[1] = 0.035
        res_none = asyncio.run(api_geometry_domain_box(DomainBoxRequest(config=base_cfg, bounds=bounds)))
        self.assertAlmostEqual(res_none["domain_box"]["min"][1], 0.035)

        # Style 1: Relative ride height gap (0.020m below smin[1] -> 0.035 - 0.020 = 0.015)
        cfg_rel = dict(base_cfg, ground_clearance=0.020)
        res_rel = asyncio.run(api_geometry_domain_box(DomainBoxRequest(config=cfg_rel, bounds=bounds)))
        self.assertAlmostEqual(res_rel["domain_box"]["min"][1], 0.015)

        # Style 2: Absolute CAD ground plane (fixed at 0.0)
        cfg_abs = dict(base_cfg, ground_plane=0.0)
        res_abs = asyncio.run(api_geometry_domain_box(DomainBoxRequest(config=cfg_abs, bounds=bounds)))
        self.assertAlmostEqual(res_abs["domain_box"]["min"][1], 0.0)

    def test_auto_symmetry_plane_calculation(self):
        """Test calculation of auto symmetry plane from geometry bounds."""
        # bounds with asymmetric X min = -0.8639691, max = 0.6265309
        bounds = {"min": [-0.8640, 0.0, -1.71], "max": [0.6266, 1.0, 1.44]}
        cfg = {
            "flow": {"velocity": 16.67, "direction": "-z", "ground": True},
            "outputs": {"drag_axis": "-z", "downforce_axis": "-y"},
        }
        res = asyncio.run(api_geometry_domain_box(DomainBoxRequest(config=cfg, bounds=bounds)))
        self.assertIn("auto_symmetry_plane", res)
        self.assertEqual(res["lateral_axis"], "x")
        # (-0.8640 + 0.6266) / 2 = -0.2374 / 2 = -0.1187
        self.assertAlmostEqual(res["auto_symmetry_plane"], -0.1187, places=4)

    def test_list_cases_and_delete(self):
        """Test listing cases archive and deleting a case."""
        # Create a dummy case in cases/
        dummy_case = Path("cases/test_case_archive_dummy")
        dummy_case.mkdir(parents=True, exist_ok=True)
        (dummy_case / "case_config.json").write_text('{"case_name": "test_case_archive_dummy", "fidelity": "standard"}')

        try:
            cases = asyncio.run(api_list_cases())
            self.assertTrue(any(c["name"] == "test_case_archive_dummy" for c in cases))
            matching = next(c for c in cases if c["name"] == "test_case_archive_dummy")
            self.assertEqual(matching["location"], "Local")
            self.assertEqual(matching["status"], "Generated")
            self.assertIn("modified", matching)
        finally:
            del_res = asyncio.run(api_case_delete("test_case_archive_dummy"))
            self.assertTrue(del_res["success"])
            self.assertFalse(dummy_case.exists())


if __name__ == "__main__":
    unittest.main()
