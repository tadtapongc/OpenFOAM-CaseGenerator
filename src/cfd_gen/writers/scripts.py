"""Shell script writers.

Generates: Allrun.parallel, Allrun, Allclean, run.sh (SLURM)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _write_script(path: Path, content: str) -> None:
    """Write script file with executable permission."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o755)


def write_scripts(cfg: dict[str, Any], case_dir: Path) -> None:
    """Write all execution scripts."""
    n = cfg["parallel"]["n_procs"]
    case_name = cfg["case_name"]
    slurm = cfg["slurm"]
    end_time = cfg["solver"]["end_time"]

    # ---- Allrun.parallel ----
    _write_script(case_dir / "Allrun.parallel", f"""\
#!/bin/bash
set -e
cd "${{0%/*}}" || exit
. ${{WM_PROJECT_DIR:?}}/bin/tools/RunFunctions

echo "Case: $(basename $(pwd)) | Cores: {n} | Iters: {end_time}"

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
runParallel simpleFoam || true

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

runApplication surfaceFeatureExtract
runApplication blockMesh
runApplication snappyHexMesh -overwrite -noFunctionObjects
runApplication checkMesh -allGeometry -allTopology -noFunctionObjects
runApplication renumberMesh -overwrite -noFunctionObjects
runApplication potentialFoam -noFunctionObjects || true
runApplication simpleFoam || true

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
[ -d 0.orig ] && rm -rf 0 && cp -r 0.orig 0
""")

    # ---- run.sh (SLURM) ----
    _write_script(case_dir / "run.sh", f"""\
#!/bin/bash
#SBATCH --job-name={case_name}
#SBATCH --nodes=1
#SBATCH --ntasks={n}
#SBATCH --time={slurm["time"]}
#SBATCH --output={case_name}_%j.log

module load {slurm["openfoam_module"]}
source ${{FOAM_INST_DIR:?}}/etc/bashrc 2>/dev/null || true

set -e
echo "Job $SLURM_JOB_ID | $(hostname) | $(date)"

# Mesh
surfaceFeatureExtract > log.surfaceFeatureExtract 2>&1
blockMesh > log.blockMesh 2>&1
decomposePar > log.decomposePar 2>&1
mpirun -np $SLURM_NTASKS snappyHexMesh -overwrite -noFunctionObjects -parallel > log.snappyHexMesh 2>&1
reconstructParMesh -constant > log.reconstructParMesh 2>&1
rm -rf processor*
checkMesh -allGeometry -allTopology -noFunctionObjects > log.checkMesh 2>&1
renumberMesh -overwrite -noFunctionObjects > log.renumberMesh 2>&1

# Solve
decomposePar > log.decomposePar.solver 2>&1
mpirun -np $SLURM_NTASKS potentialFoam -noFunctionObjects -parallel > log.potentialFoam 2>&1 || true
mpirun -np $SLURM_NTASKS simpleFoam -parallel > log.simpleFoam 2>&1 || true

# Always reconstruct
reconstructPar > log.reconstructPar 2>&1
rm -rf processor*

echo "Done at $(date)"
""")
