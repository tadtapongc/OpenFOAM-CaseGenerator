#!/bin/bash
#SBATCH --job-name=FW
#SBATCH --nodes=1
#SBATCH --ntasks=10
#SBATCH --time=08:00:00
#SBATCH --output=FW_%j.log

module load openfoam/v2512
source ${FOAM_INST_DIR:?}/etc/bashrc 2>/dev/null || true

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
