"""Tests for the structured result exporter (postproc/result.py).

Uses minimal fake case fixtures (case_config.json + postProcessing/forces)
— no OpenFOAM installation or simulation required.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

from cfd_gen.postproc import result as R
from cfd_gen.postproc.result import build_result

CONFIG = {
    "case_name": "rearwing_v12",
    "flow": {"velocity": 16.67, "direction": "-z", "ground": True},
    "outputs": {"drag_axis": "-z", "downforce_axis": "-y"},
    "fluid": {"nu": 1.516e-5, "rho": 1.225},
    "force_refs": {"lRef": 1.0, "Aref": 1.0, "CofR": [0, 0, 0]},
}

DYNAMIC_PRESSURE_REF = 0.5 * 1.225 * 16.67 ** 2  # Aref = 1.0


def _force_line(t: int, fy: float, fz: float) -> str:
    """One force.dat line: Time, pressure (x y z), viscous (x y z), porous (x y z).

    With drag_axis=-z and downforce_axis=-y: total_z=-12.34 -> drag=+12.34 N,
    total_y=-45.678 -> downforce=+45.678 N.
    """
    return f"{t}  (0.0 {fy} {fz})  (0 0 0)  (0 0 0)\n"


def _make_case(
    case_dir: Path,
    config: dict | None = CONFIG,
    n_iters: int = 0,
    fy_fn=None,
    fz_fn=None,
) -> Path:
    """Build a minimal fake case directory."""
    case_dir.mkdir(parents=True, exist_ok=True)
    if config is not None:
        (case_dir / "case_config.json").write_text(json.dumps(config, indent=2))
    root = case_dir / "postProcessing" / "forces"
    for i in range(n_iters):
        d = root / str(i)
        d.mkdir(parents=True, exist_ok=True)
        fy = fy_fn(i) if fy_fn else 0.0
        fz = fz_fn(i) if fz_fn else 0.0
        (d / "force.dat").write_text(_force_line(i, fy, fz))
    return case_dir


@pytest.fixture
def converged_case(tmp_path) -> Path:
    """250 iterations with small oscillation -> converged."""
    return _make_case(
        tmp_path / "cases" / "rearwing_v12",
        n_iters=250,
        fy_fn=lambda i: -(45.678 + 0.05 * math.sin(i * 0.3)),
        fz_fn=lambda i: -(12.34 + 0.01 * math.sin(i * 0.7)),
    )


@pytest.fixture
def nonconverged_case(tmp_path) -> Path:
    """250 iterations with 5% oscillation -> not converged."""
    return _make_case(
        tmp_path / "cases" / "osc_case",
        config={**CONFIG, "case_name": "osc_case"},
        n_iters=250,
        fy_fn=lambda i: -(45.678 * (1 + 0.05 * math.sin(i * 0.5))),
        fz_fn=lambda i: -(12.34 * (1 + 0.05 * math.sin(i * 0.9))),
    )


@pytest.fixture
def short_case(tmp_path) -> Path:
    """10 iterations -> too few for a reliable average."""
    return _make_case(
        tmp_path / "cases" / "short_case",
        config={**CONFIG, "case_name": "short_case"},
        n_iters=10,
        fy_fn=lambda i: -45.678,
        fz_fn=lambda i: -12.34,
    )


@pytest.fixture
def empty_case(tmp_path) -> Path:
    """Config only, no force data."""
    return _make_case(tmp_path / "cases" / "empty_case", n_iters=0)


# ============================================================
# 1. Completed case with force data
# ============================================================

class TestCompletedCase:
    def test_status_and_case_name(self, converged_case):
        res = build_result(converged_case)
        assert res.schema_version == "1.0"
        assert res.case == "rearwing_v12"
        assert res.status == R.STATUS_COMPLETED

    def test_conditions(self, converged_case):
        res = build_result(converged_case)
        assert res.conditions.velocity_ms == 16.67
        assert res.conditions.yaw_deg is None
        assert res.conditions.aoa_deg is None

    def test_forces(self, converged_case):
        res = build_result(converged_case)
        assert res.forces.drag_N == pytest.approx(12.34, abs=0.02)
        assert res.forces.downforce_N == pytest.approx(45.678, abs=0.06)
        # lift is the +y force: sign flip of downforce for a -y downforce axis
        assert res.forces.lift_N == pytest.approx(-45.678, abs=0.06)

    def test_coefficients(self, converged_case):
        res = build_result(converged_case)
        assert res.coefficients.Cd == pytest.approx(12.34 / DYNAMIC_PRESSURE_REF, rel=3e-3)
        assert res.coefficients.Cl == pytest.approx(-45.678 / DYNAMIC_PRESSURE_REF, rel=3e-3)
        assert res.coefficients.L_over_D == pytest.approx(45.678 / 12.34, rel=3e-3)

    def test_convergence(self, converged_case):
        res = build_result(converged_case)
        assert res.convergence.converged is True
        assert res.convergence.force_variation_percent is not None
        assert res.convergence.force_variation_percent < 0.5


# ============================================================
# 2. Missing force data
# ============================================================

class TestMissingForceData:
    def test_status_and_nulls(self, empty_case):
        res = build_result(empty_case)
        assert res.status == R.STATUS_NO_DATA
        assert res.forces.drag_N is None
        assert res.forces.downforce_N is None
        assert res.forces.lift_N is None
        assert res.coefficients.Cd is None
        assert res.coefficients.Cl is None
        assert res.coefficients.L_over_D is None
        assert res.convergence.converged is None
        assert res.convergence.force_variation_percent is None
        # config-derived values are still available
        assert res.conditions.velocity_ms == 16.67
        assert res.case == "rearwing_v12"


# ============================================================
# 3. Incomplete / non-converged case
# ============================================================

class TestIncompleteCase:
    def test_not_converged(self, nonconverged_case):
        res = build_result(nonconverged_case)
        assert res.status == R.STATUS_INCOMPLETE
        assert res.convergence.converged is False
        assert res.convergence.force_variation_percent > 0.5
        # averages are still reported when enough iterations exist
        assert res.forces.drag_N == pytest.approx(12.34, abs=0.2)
        assert res.forces.downforce_N == pytest.approx(45.678, abs=1.0)

    def test_too_few_iterations(self, short_case):
        res = build_result(short_case)
        assert res.status == R.STATUS_INCOMPLETE
        assert res.convergence.converged is False
        assert res.forces.drag_N is None
        assert res.forces.downforce_N is None
        assert res.convergence.force_variation_percent is None
        assert res.coefficients.Cd is None
        assert res.coefficients.L_over_D is None


def test_case_without_config(tmp_path):
    """Force data without case_config.json: no invented conditions."""
    case = _make_case(
        tmp_path / "cases" / "bare_case",
        config=None,
        n_iters=250,
        fy_fn=lambda i: -(45.678 + 0.05 * math.sin(i * 0.3)),
        fz_fn=lambda i: -(12.34 + 0.01 * math.sin(i * 0.7)),
    )
    res = build_result(case)
    assert res.case == "bare_case"
    assert res.status == R.STATUS_COMPLETED
    assert res.conditions.velocity_ms is None
    assert res.coefficients.Cd is None
    # L/D needs only the forces
    assert res.coefficients.L_over_D == pytest.approx(45.678 / 12.34, rel=3e-3)


# ============================================================
# 4. JSON serialization
# ============================================================

class TestJsonSerialization:
    def test_roundtrip_and_schema_keys(self, converged_case):
        res = build_result(converged_case)
        data = json.loads(res.to_json())
        assert data["schema_version"] == "1.0"
        assert set(data) == {
            "schema_version", "case", "status",
            "conditions", "forces", "coefficients", "convergence",
        }
        assert set(data["conditions"]) == {"velocity_ms", "yaw_deg", "aoa_deg"}
        assert set(data["forces"]) == {"drag_N", "downforce_N", "lift_N"}
        assert set(data["coefficients"]) == {"Cd", "Cl", "L_over_D"}
        assert set(data["convergence"]) == {"converged", "force_variation_percent"}
        assert data == res.to_dict()

    def test_deterministic(self, converged_case):
        a = build_result(converged_case).to_json()
        b = build_result(converged_case).to_json()
        assert a == b

    def test_nulls_serialized_as_json_null(self, empty_case):
        data = json.loads(build_result(empty_case).to_json())
        assert data["forces"] == {"drag_N": None, "downforce_N": None, "lift_N": None}
        assert data["conditions"]["yaw_deg"] is None
        assert data["conditions"]["aoa_deg"] is None
        assert data["convergence"]["converged"] is None


# ============================================================
# 5. Backward compatibility with existing post-processing code
# ============================================================

class TestBackwardCompatibility:
    def test_reuses_existing_parsers(self, converged_case):
        from cfd_gen.postproc.forces import (
            axis_index_sign,
            check_convergence,
            find_force_files,
            read_forces,
        )

        files = find_force_files(converged_case)
        assert files
        di, ds = axis_index_sign("-z")
        fi, fs = axis_index_sign("-y")
        times, drags, dfs = read_forces(files, di, ds, fi, fs)
        conv, dp, fp, d_avg, f_avg = check_convergence(drags, dfs)

        res = build_result(converged_case)
        assert res.forces.drag_N == pytest.approx(d_avg, abs=1e-3)
        assert res.forces.downforce_N == pytest.approx(f_avg, abs=1e-3)
        assert res.convergence.converged is conv
        assert res.convergence.force_variation_percent == pytest.approx(
            max(dp, fp), abs=1e-3
        )

    def test_existing_apis_still_work(self, converged_case, capsys):
        from cfd_gen.postproc.forces import (
            find_force_files,
            load_axis_config,
            print_summary,
            read_forces,
        )

        drag_idx, drag_sign, df_idx, df_sign, drag_axis, df_axis = load_axis_config(
            str(converged_case / "case_config.json")
        )
        assert (drag_axis, df_axis) == ("-z", "-y")
        files = find_force_files(converged_case)
        times, drags, dfs = read_forces(files, drag_idx, drag_sign, df_idx, df_sign)
        assert print_summary(times, drags, dfs, drag_axis, df_axis) is True
        assert "CONVERGED" in capsys.readouterr().out


# ============================================================
# CLI
# ============================================================

class TestCli:
    @staticmethod
    def _run(monkeypatch, *argv):
        from cfd_gen.cli import result_main

        monkeypatch.setattr(sys, "argv", ["cfd-result", *argv])
        result_main()

    def test_human_readable(self, converged_case, monkeypatch, capsys):
        self._run(monkeypatch, str(converged_case))
        out = capsys.readouterr().out
        assert "rearwing_v12" in out
        assert "completed" in out
        assert "Drag:" in out and "12.3" in out

    def test_json_flag(self, converged_case, monkeypatch, capsys):
        self._run(monkeypatch, str(converged_case), "--json")
        data = json.loads(capsys.readouterr().out)
        assert data["case"] == "rearwing_v12"
        assert data["status"] == "completed"

    def test_output_file(self, converged_case, tmp_path, monkeypatch, capsys):
        out_file = tmp_path / "out" / "result.json"
        self._run(monkeypatch, str(converged_case), "--output", str(out_file))
        cap = capsys.readouterr()
        assert out_file.exists()
        assert json.loads(out_file.read_text())["case"] == "rearwing_v12"
        # confirmation goes to stderr; human summary stays on stdout
        assert "result.json" in cap.err
        assert "rearwing_v12" in cap.out

    def test_json_and_output_together(self, converged_case, tmp_path, monkeypatch, capsys):
        out_file = tmp_path / "result.json"
        self._run(monkeypatch, str(converged_case), "--json", "-o", str(out_file))
        cap = capsys.readouterr()
        assert json.loads(cap.out)["status"] == "completed"
        assert json.loads(out_file.read_text())["status"] == "completed"

    def test_missing_case_dir(self, tmp_path, monkeypatch):
        from cfd_gen.cli import result_main

        monkeypatch.setattr(sys, "argv", ["cfd-result", str(tmp_path / "nope")])
        with pytest.raises(SystemExit) as ei:
            result_main()
        assert "not found" in str(ei.value.code)

    def test_default_case_dir_is_cwd(self, converged_case, monkeypatch, capsys):
        monkeypatch.chdir(converged_case)
        self._run(monkeypatch, "--json")
        data = json.loads(capsys.readouterr().out)
        assert data["case"] == "rearwing_v12"
