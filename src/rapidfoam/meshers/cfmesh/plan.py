"""cfMesh's meshing plan — the commands ``Allrun``/``run.sh`` render.

``surfaceFeatureEdges`` builds the ``.fms`` feature surface from ``domain.stl``,
``cartesianMesh`` creates the octree, ``reconstructParMesh`` stitches a parallel
mesh back together (cfMesh decomposes the octree itself using
``decomposeParDict``'s ``numberOfSubdomains``, so no ``decomposePar`` is needed),
then ``checkMesh`` and ``renumberMesh`` finish.

Parallel meshing is worth it and cheap to enable, but not every build ships the
parallel octree, so the MPI attempt carries a serial fallback and keeps the failed
attempt's log.
"""

from __future__ import annotations

from typing import Any

from rapidfoam.meshers.cfmesh.settings import CfMeshSettings
from rapidfoam.meshers.plan import MeshCommand, MeshPlan

SURFACE_STL = "constant/triSurface/domain.stl"
SURFACE_FMS = "constant/triSurface/domain.fms"

#: One OpenMP thread per rank: the octree passes are threaded, so MPI x threads
#: oversubscribes the node.
OMP_ONE_THREAD = ("OMP_NUM_THREADS=1",)


def cfmesh_mesh_plan(settings: CfMeshSettings) -> MeshPlan:
    """The meshing commands for resolved cfMesh settings."""
    parallel = settings.parallel_meshing
    commands = [
        MeshCommand(
            "surfaceFeatureEdges",
            args=("-angle", f"{settings.feature_angle:g}", SURFACE_STL, SURFACE_FMS),
        ),
        MeshCommand(
            "cartesianMesh",
            mpi=parallel,
            mpi_args=("-parallel",),
            serial_retry=parallel,
            reconstruct_after=parallel,
            env=("OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-$SLURM_NTASKS}",) if not parallel else (),
            env_mpi=OMP_ONE_THREAD,
            env_allrun=OMP_ONE_THREAD if parallel else (),
        ),
        MeshCommand("checkMesh", args=("-noFunctionObjects",)),
        MeshCommand("renumberMesh", args=("-overwrite", "-noFunctionObjects")),
    ]
    return MeshPlan(
        commands=tuple(commands),
        label="cfMesh cartesianMesh",
        deploy_user_appbin=True,
        parallel_meshing=parallel,
    )


def cfmesh_plan_from_config(cfg: dict[str, Any]) -> MeshPlan:
    """Convenience wrapper for callers that only have the raw config."""
    from rapidfoam.meshers.cfmesh.settings import resolve_cfmesh_settings

    return cfmesh_mesh_plan(resolve_cfmesh_settings(cfg))


__all__ = ["OMP_ONE_THREAD", "SURFACE_FMS", "SURFACE_STL", "cfmesh_mesh_plan",
           "cfmesh_plan_from_config"]
