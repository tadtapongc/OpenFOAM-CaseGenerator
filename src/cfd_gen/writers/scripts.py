"""Shell script writers.

Generates: Allrun.parallel, Allrun, Allclean, run.sh (SLURM), convergence_monitor.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cfd_gen.geometry import parse_axis


def _write_script(path: Path, content: str) -> None:
    """Write script file with executable permission."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def _convergence_monitor_script(cfg: dict[str, Any]) -> str:
    """Generate a self-contained convergence monitor Python script.

    This script has zero external dependencies — it reads force.dat directly
    and modifies controlDict to trigger a clean solver stop.
    """
    drag_vec = parse_axis(cfg["outputs"]["drag_axis"])
    df_vec = parse_axis(cfg["outputs"]["downforce_axis"])

    # Determine axis indices and signs
    drag_idx = next(i for i, v in enumerate(drag_vec) if v != 0)
    drag_sign = int(drag_vec[drag_idx])
    df_idx = next(i for i, v in enumerate(df_vec) if v != 0)
    df_sign = int(df_vec[df_idx])

    return f'''\
#!/usr/bin/env python3
"""Auto-stop monitor: stops simpleFoam when forces converge.

Checks force.dat every INTERVAL seconds. When both drag and downforce
variation drop below THRESHOLD over the last WINDOW iterations,
modifies controlDict to set stopAt=writeNow for a clean exit.
"""

import os
import statistics
import sys
import time
from pathlib import Path

# === Configuration (from case_config) ===
DRAG_IDX = {drag_idx}
DRAG_SIGN = {drag_sign}
DF_IDX = {df_idx}
DF_SIGN = {df_sign}
THRESHOLD = 0.5     # percent
WINDOW = 200        # iterations to average
MIN_ITERS = 300     # minimum before checking
INTERVAL = 10       # seconds between checks


def find_force_files():
    """Find force.dat files."""
    files = []
    forces_dir = Path("postProcessing/forces")
    if forces_dir.exists():
        for d in sorted(forces_dir.iterdir()):
            f = d / "force.dat"
            if f.exists():
                files.append(f)
    # Parallel fallback
    if not files:
        for proc in sorted(Path(".").glob("processor*")):
            pf = proc / "postProcessing" / "forces"
            if pf.exists():
                for d in sorted(pf.iterdir()):
                    f = d / "force.dat"
                    if f.exists():
                        files.append(f)
                break
    return files


def read_forces(files):
    """Parse force.dat → (times, drags, downforces)."""
    times, drags, downforces = [], [], []
    seen = set()
    for path in files:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.replace("(", "").replace(")", "").split()
                    if len(parts) < 10:
                        continue
                    t = float(parts[0])
                    t_key = round(t, 8)
                    if t_key in seen:
                        continue
                    seen.add(t_key)
                    pressure = [float(parts[i]) for i in (1, 2, 3)]
                    viscous = [float(parts[i]) for i in (4, 5, 6)]
                    porous = [float(parts[i]) for i in (7, 8, 9)]
                    total = [pressure[j] + viscous[j] + porous[j] for j in range(3)]
                    times.append(t)
                    drags.append(total[DRAG_IDX] * DRAG_SIGN)
                    downforces.append(total[DF_IDX] * DF_SIGN)
        except (OSError, ValueError):
            pass
    if times:
        combined = sorted(zip(times, drags, downforces))
        times = [c[0] for c in combined]
        drags = [c[1] for c in combined]
        downforces = [c[2] for c in combined]
    return times, drags, downforces


def check_convergence(drags, downforces):
    """Check if forces are converged. Returns (converged, d_pct, f_pct, d_avg, f_avg)."""
    window = min(WINDOW, len(drags))
    if window < 20:
        return False, 100.0, 100.0, 0.0, 0.0
    d_win = drags[-window:]
    f_win = downforces[-window:]
    d_avg = statistics.mean(d_win)
    f_avg = statistics.mean(f_win)
    d_std = statistics.stdev(d_win)
    f_std = statistics.stdev(f_win)
    d_pct = (d_std / abs(d_avg) * 100) if d_avg != 0 else 100.0
    f_pct = (f_std / abs(f_avg) * 100) if f_avg != 0 else 100.0
    return (d_pct < THRESHOLD and f_pct < THRESHOLD), d_pct, f_pct, d_avg, f_avg


def trigger_stop():
    """Modify controlDict to stop solver cleanly."""
    cd = Path("system/controlDict")
    if not cd.exists():
        return
    text = cd.read_text()
    lines = text.split("\\n")
    new_lines = []
    for line in lines:
        if line.strip().startswith("stopAt"):
            new_lines.append("stopAt          writeNow;")
        else:
            new_lines.append(line)
    cd.write_text("\\n".join(new_lines))


def main():
    print(f"  Convergence monitor started (threshold: ±{{THRESHOLD}}%, window: {{WINDOW}}, min: {{MIN_ITERS}})")
    sys.stdout.flush()

    while True:
        time.sleep(INTERVAL)

        files = find_force_files()
        if not files:
            continue

        times, drags, downforces = read_forces(files)
        if len(times) < MIN_ITERS:
            continue

        converged, d_pct, f_pct, d_avg, f_avg = check_convergence(drags, downforces)

        n = len(times)
        status = "OK" if converged else ".."
        print(f"  [{{status}}] iter {{n:>5}} | drag: {{d_avg:>8.3f}} N (±{{d_pct:.3f}}%) | df: {{f_avg:>8.3f}} N (±{{f_pct:.3f}}%)")
        sys.stdout.flush()

        if converged:
            ld = abs(f_avg / d_avg) if d_avg != 0 else 0
            print(f"\\n  CONVERGED at iteration {{n}}")
            print(f"    Drag:      {{d_avg:.3f}} N (±{{d_pct:.3f}}%)")
            print(f"    Downforce: {{f_avg:.3f}} N (±{{f_pct:.3f}}%)")
            print(f"    L/D:       {{ld:.3f}}")
            print(f"  -> Triggering solver stop (writeNow)...")
            sys.stdout.flush()
            trigger_stop()
            print(f"  -> Done. Solver will write and exit.")
            sys.stdout.flush()
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
'''


def write_scripts(cfg: dict[str, Any], case_dir: Path) -> None:
    """Write all execution scripts."""
    n = cfg["parallel"]["n_procs"]
    case_name = cfg["case_name"]
    slurm = cfg.get("slurm", {})
    end_time = cfg["solver"]["end_time"]

    # ----- SLURM settings with good defaults for CU e-Science -----
    qos = slurm.get("qos", "cu_long")
    partition = slurm.get("partition", "cpu")
    nodes = slurm.get("nodes", 1)
    time_limit = slurm.get("time", "04:00:00")
    mem_per_cpu = slurm.get("mem_per_cpu", "3G")
    cpus_per_task = slurm.get("cpus_per_task", 1)
    openfoam_module = slurm.get("openfoam_module", None)
    openfoam_source = slurm.get(
        "openfoam_source",
        "$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc"
    )

    # ---- convergence_monitor.py (self-contained) ----
    _write_script(
        case_dir / "convergence_monitor.py",
        _convergence_monitor_script(cfg),
    )

    # ---- Allrun.parallel ----
    _write_script(case_dir / "Allrun.parallel", f"""\
#!/bin/bash
set -e
cd "${{0%/*}}" || exit
. ${{WM_PROJECT_DIR:?}}/bin/tools/RunFunctions

echo "Case: $(basename $(pwd)) | Cores: {n} | Iters: {end_time}"

# Restore stopAt in case convergence monitor changed it on a previous run
if [ -f system/controlDict ]; then
    sed -i 's/stopAt.*writeNow/stopAt          endTime/' system/controlDict
fi

# Mesh
runApplication surfaceFeatureExtract
runApplication blockMesh
runApplication decomposePar
runParallel snappyHexMesh -overwrite -noFunctionObjects
runApplication reconstructParMesh -constant
rm -rf processor*
runApplication checkMesh -allGeometry -allTopology -noFunctionObjects
runApplication renumberMesh -overwrite -noFunctionObjects

# Solve
runApplication -s solver decomposePar
runParallel -s potential potentialFoam -noFunctionObjects || true

# Start convergence monitor in background (auto-stops solver when converged)
python3 ./convergence_monitor.py > log.convergenceMonitor 2>&1 &
MONITOR_PID=$!

runParallel simpleFoam || true

# Stop monitor if still running
kill $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

# Always reconstruct (even if solver was interrupted)
runApplication reconstructPar
rm -rf processor*

echo "Done. Results in $(pwd)"
""")

    # ---- Allrun (serial) ----
    _write_script(case_dir / "Allrun", f"""\
#!/bin/bash
set -e
cd "${{0%/*}}" || exit
. ${{WM_PROJECT_DIR:?}}/bin/tools/RunFunctions

# Restore stopAt in case convergence monitor changed it on a previous run
if [ -f system/controlDict ]; then
    sed -i 's/stopAt.*writeNow/stopAt          endTime/' system/controlDict
fi

runApplication surfaceFeatureExtract
runApplication blockMesh
runApplication snappyHexMesh -overwrite -noFunctionObjects
runApplication checkMesh -allGeometry -allTopology -noFunctionObjects
runApplication renumberMesh -overwrite -noFunctionObjects
runApplication potentialFoam -noFunctionObjects || true

# Start convergence monitor in background
python3 ./convergence_monitor.py > log.convergenceMonitor 2>&1 &
MONITOR_PID=$!

runApplication simpleFoam || true

kill $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

echo "Done."
""")

    # ---- Allclean ----
    _write_script(case_dir / "Allclean", """\
#!/bin/bash
cd "${0%/*}" || exit
. ${WM_PROJECT_DIR:?}/bin/tools/CleanFunctions

cleanCase
rm -rf constant/polyMesh constant/extendedFeatureEdgeMesh
rm -f constant/triSurface/*.eMesh
rm -f log.*
rm -rf postProcessing
# Restore stopAt in controlDict if it was changed by convergence monitor
if [ -f system/controlDict ]; then
    sed -i 's/stopAt.*writeNow/stopAt          endTime/' system/controlDict
fi
[ -d 0.orig ] && rm -rf 0 && cp -r 0.orig 0
""")

    # ---- run.sh (SLURM) - Full improved version ----
    load_lines = []
    if openfoam_module:
        if isinstance(openfoam_module, list):
            for mod in openfoam_module:
                load_lines.append(f"module load {mod}")
        else:
            load_lines.append(f"module load {openfoam_module}")
    if openfoam_source:
        load_lines.append(f"source {openfoam_source}")
    
    openfoam_load = "\n".join(load_lines) if load_lines else ""

    _write_script(case_dir / "run.sh", f"""\
#!/bin/bash
#SBATCH --job-name={case_name}
#SBATCH --qos={qos}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={n}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --mem-per-cpu={mem_per_cpu}
#SBATCH --time={time_limit}
#SBATCH --output={case_name}_%j.log

echo "=============================================="
echo "Job ID   : $SLURM_JOB_ID"
echo "Node     : $(hostname)"
echo "Cores    : $SLURM_NTASKS"
echo "QoS      : {qos}"
echo "Started  : $(date)"
echo "=============================================="

# Load environment
module purge
{openfoam_load}

# Extra safety (if a module defines FOAM_INST_DIR but doesn't source bashrc)
if [ -n "${{FOAM_INST_DIR:-}}" ]; then
    source ${{FOAM_INST_DIR}}/etc/bashrc 2>/dev/null || true
fi

set -e

ORIG_DIR=$PWD

# Robustly create a temporary directory in RAM (/dev/shm) or fallback to /tmp
if [ -d "/dev/shm" ] && [ -w "/dev/shm" ]; then
    RAM_DIR=$(mktemp -d -p /dev/shm cfd_${SLURM_JOB_ID:-local}_XXXXXX)
else
    RAM_DIR=$(mktemp -d -t cfd_${SLURM_JOB_ID:-local}_XXXXXX)
fi

echo ">>> Setting up local execution in $RAM_DIR"
echo ">>> Copying case to $RAM_DIR"
rsync -a $ORIG_DIR/ $RAM_DIR/
cd $RAM_DIR

# Ensure results are copied back when script exits or is interrupted
cleanup() {{
    echo ">>> Copying results back to network filesystem"
    rsync -a $RAM_DIR/ $ORIG_DIR/
    echo ">>> Cleaning up RAM disk"
    cd $ORIG_DIR
    rm -rf $RAM_DIR
    echo "=============================================="
    echo "Job finished at $(date)"
    echo "=============================================="
}}
trap cleanup EXIT

# Restore stopAt (in case previous run was stopped by monitor)
if [ -f system/controlDict ]; then
    sed -i 's/stopAt.*writeNow/stopAt          endTime/' system/controlDict
fi

# ======================== MESH ========================
echo ">>> Running surfaceFeatureExtract"
surfaceFeatureExtract > log.surfaceFeatureExtract 2>&1

echo ">>> Running blockMesh"
blockMesh > log.blockMesh 2>&1

echo ">>> Decomposing for meshing"
decomposePar > log.decomposePar 2>&1

echo ">>> Running snappyHexMesh (parallel)"
mpirun -np $SLURM_NTASKS snappyHexMesh -overwrite -noFunctionObjects -parallel > log.snappyHexMesh 2>&1

echo ">>> Reconstructing mesh"
reconstructParMesh -constant > log.reconstructParMesh 2>&1
rm -rf processor*

echo ">>> Checking mesh"
checkMesh -allGeometry -allTopology -noFunctionObjects > log.checkMesh 2>&1

echo ">>> Renumbering mesh"
renumberMesh -overwrite -noFunctionObjects > log.renumberMesh 2>&1

# ======================== SOLVE ========================
echo ">>> Decomposing for solver"
decomposePar > log.decomposePar.solver 2>&1

echo ">>> Running potentialFoam"
mpirun -np $SLURM_NTASKS potentialFoam -noFunctionObjects -parallel > log.potentialFoam 2>&1 || true

echo ">>> Starting convergence monitor"
python3 ./convergence_monitor.py > log.convergenceMonitor 2>&1 &
MONITOR_PID=$!

echo ">>> Running simpleFoam"
mpirun -np $SLURM_NTASKS simpleFoam -parallel > log.simpleFoam 2>&1 || true

# Stop monitor
kill $MONITOR_PID 2>/dev/null || true
wait $MONITOR_PID 2>/dev/null || true

echo ">>> Reconstructing results"
reconstructPar > log.reconstructPar 2>&1
rm -rf processor*
""")
