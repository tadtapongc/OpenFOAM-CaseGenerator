"""Execute generated scripts with fake OpenFOAM commands in isolated Linux cases."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cfd_gen.config import DEFAULT_CONFIG
from cfd_gen.writers.scripts import write_scripts


@unittest.skipUnless(os.name == "posix" and shutil.which("bash"), "Requires Linux bash")
class ShellScriptsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cfd_gen_scripts_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.case = self.root / "case with spaces"
        (self.case / "system").mkdir(parents=True)
        (self.case / "system/controlDict").write_text("stopAt endTime;\n")
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        runfunctions = self.root / "foam/bin/tools/RunFunctions"
        runfunctions.parent.mkdir(parents=True)
        runfunctions.write_text('''runApplication() {
    if [ "$1" = "-s" ]; then shift 2; fi
    "$@"
}
runParallel() {
    if [ "$1" = "-s" ]; then shift 2; fi
    "$@"
}
''')
        tool = self.bin / "fake-tool"
        tool.write_text('''#!/bin/bash
name=$(basename "$0")
if [ "$name" = "$FAIL_STAGE" ]; then exit 31; fi
case "$name" in
    decomposePar)
        mkdir -p processor0
        echo recoverable > processor0/state
        ;;
    simpleFoam)
        touch "$HARNESS_ROOT/solver.started"
        if [ "$WAIT_SOLVER" = 1 ]; then
            while true; do sleep 0.1; done
        fi
        exit "${FAKE_SOLVER_STATUS:-0}"
        ;;
    reconstructPar)
        if [ "${RECONSTRUCT_STATUS:-0}" -ne 0 ]; then exit "$RECONSTRUCT_STATUS"; fi
        cp processor0/state reconstructed
        ;;
    mpirun)
        shift 2
        exec "$@"
        ;;
    python3)
        echo $$ > "$HARNESS_ROOT/monitor.pid"
        trap 'exit 0' TERM INT
        while true; do sleep 0.1; done
        ;;
    rsync)
        args=("$@")
        count=${#args[@]}
        src=${args[$((count-2))]}
        dst=${args[$((count-1))]}
        if [ "$COPYBACK_FAIL" = 1 ] && [ "$dst" = "$ORIG_CASE/" ]; then exit 42; fi
        cp -a "$src/." "$dst/"
        ;;
esac
''')
        tool.chmod(0o755)
        for name in ("surfaceFeatureExtract", "blockMesh", "decomposePar", "snappyHexMesh",
                     "reconstructParMesh", "checkMesh", "renumberMesh", "potentialFoam",
                     "simpleFoam", "reconstructPar", "mpirun", "python3", "rsync", "module"):
            (self.bin / name).symlink_to(tool)
        self.env = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                    "WM_PROJECT_DIR": str(self.root / "foam"), "SLURM_JOB_ID": "test",
                    "SLURM_NTASKS": "2", "TMPDIR": str(self.scratch),
                    "HARNESS_ROOT": str(self.root), "ORIG_CASE": str(self.case),
                    "FOAM_INST_DIR": "", "FAIL_STAGE": "", "COPYBACK_FAIL": "0",
                    "WAIT_SOLVER": "0", "SOLVER_STATUS": "0", "RECONSTRUCT_STATUS": "0"}

    def generate(self, scratch=False):
        cfg = copy.deepcopy(DEFAULT_CONFIG)
        cfg["parallel"]["n_procs"] = 2
        cfg["slurm"].update(use_tmpdir=scratch, openfoam_source=None, openfoam_module=None)
        write_scripts(cfg, self.case)

    def run_script(self, name, **env):
        if "SOLVER_STATUS" in env:
            env["FAKE_SOLVER_STATUS"] = env.pop("SOLVER_STATUS")
        return subprocess.run(["bash", str(self.case/name)], cwd=self.case,
                              env={**self.env, **env}, text=True, capture_output=True, timeout=15)

    def assert_monitor_stopped(self):
        path = self.root/"monitor.pid"
        if path.exists():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(path.read_text()), 0)

    def test_all_generated_shell_syntax(self):
        for scratch in (False, True):
            self.generate(scratch)
            for name in ("Allrun", "Allrun.parallel", "Allclean", "run.sh"):
                result = subprocess.run(["bash", "-n", str(self.case/name)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_serial_solver_failure_is_reported(self):
        self.generate()
        result = self.run_script("Allrun", SOLVER_STATUS="17")
        self.assertEqual(result.returncode, 17, result.stdout+result.stderr)
        self.assertNotIn("Done.", result.stdout)
        self.assert_monitor_stopped()

    def test_parallel_solver_failure_recovers_results_and_reports_failure(self):
        self.generate()
        result = self.run_script("Allrun.parallel", SOLVER_STATUS="17")
        self.assertEqual(result.returncode, 17, result.stdout+result.stderr)
        self.assertEqual((self.case/"reconstructed").read_text().strip(), "recoverable")
        self.assertFalse((self.case/"processor0").exists())
        self.assert_monitor_stopped()

    def test_parallel_reconstruction_failure_keeps_processors(self):
        self.generate()
        result = self.run_script("Allrun.parallel", RECONSTRUCT_STATUS="23")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.case/"processor0/state").read_text().strip(), "recoverable")

    def test_slurm_in_place_reconstruction_failure_keeps_processors(self):
        self.generate()
        result = self.run_script("run.sh", RECONSTRUCT_STATUS="23")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.case/"processor0/state").exists())
        self.assert_monitor_stopped()

    def test_slurm_scratch_reconstruction_failure_keeps_both_copies(self):
        self.generate(True)
        result = self.run_script("run.sh", RECONSTRUCT_STATUS="23")
        self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue((self.case/"processor0/state").exists())
        self.assertTrue((self.case/".running_location").exists())
        self.assertEqual(len(list(self.scratch.glob("*/processor0/state"))), 1)
        self.assert_monitor_stopped()

    def test_slurm_copyback_failure_retains_scratch_and_location(self):
        self.generate(True)
        result = self.run_script("run.sh", COPYBACK_FAIL="1")
        self.assertNotEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue((self.case/".running_location").exists())
        self.assertEqual(len(list(self.scratch.glob("*/reconstructed"))), 1)

    def test_slurm_solver_failure_survives_successful_cleanup(self):
        self.generate(True)
        result = self.run_script("run.sh", SOLVER_STATUS="17")
        self.assertEqual(result.returncode, 17, result.stdout+result.stderr)
        self.assertTrue((self.case/"reconstructed").exists())
        self.assertFalse(list(self.scratch.iterdir()))

    def test_slurm_scratch_success_syncs_and_cleans(self):
        self.generate(True)
        result = self.run_script("run.sh")
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertTrue((self.case/"reconstructed").exists())
        self.assertFalse(list(self.scratch.iterdir()))
        self.assertFalse((self.case/".running_location").exists())
        self.assert_monitor_stopped()

    def test_failed_meshing_preserves_mesh_processors(self):
        self.generate(True)
        result = self.run_script("run.sh", FAIL_STAGE="snappyHexMesh")
        self.assertEqual(result.returncode, 31, result.stdout+result.stderr)
        self.assertTrue((self.case/"processor0/state").exists())
        self.assertFalse((self.case/"reconstructed").exists())

    def test_sigterm_attempts_recovery_without_losing_failed_results(self):
        self.generate(True)
        proc = subprocess.Popen(["bash", str(self.case/"run.sh")], cwd=self.case,
                                env={**self.env, "WAIT_SOLVER": "1", "RECONSTRUCT_STATUS": "23"},
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
        try:
            deadline = time.monotonic()+5
            while not (self.root/"solver.started").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((self.root/"solver.started").exists())
            os.killpg(proc.pid, signal.SIGTERM)
            stdout, stderr = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 143, stdout+stderr)
            self.assertTrue((self.case/"processor0/state").exists())
            self.assertEqual(len(list(self.scratch.glob("*/processor0/state"))), 1)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.communicate()


if __name__ == "__main__":
    unittest.main()
