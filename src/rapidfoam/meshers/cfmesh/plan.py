"""cfMesh's meshing plan — the commands ``Allrun``/``run.sh`` render.

``surfaceFeatureEdges`` builds the ``.fms`` feature surface from ``domain.stl``,
``cartesianMesh`` creates the octree, ``reconstructParMesh`` stitches a parallel
mesh back together (cfMesh decomposes the octree itself using
``decomposeParDict``'s ``numberOfSubdomains``, so no ``decomposePar`` is needed),
then ``checkMesh`` and ``renumberMesh`` finish.

Parallel meshing is worth it and cheap to enable, but not every build ships the
parallel octree, so the MPI attempt carries a serial fallback and keeps the failed
attempt's log.

Both settings the plan reads — ``cfmesh.parallel_meshing`` and
``cfmesh.feature_angle`` — are plain engine keys, so
:func:`cfmesh_plan_from_config` builds the plan from a raw config, before any STL
bounds are measured.
"""

from __future__ import annotations

from typing import Any

from rapidfoam.meshers.cfmesh.settings import FEATURE_ANGLE_DEFAULT, CfMeshSettings
from rapidfoam.meshers.plan import MeshCommand, MeshPlan, resolve_parallel_meshing

SURFACE_STL = "constant/triSurface/domain.stl"
SURFACE_FMS = "constant/triSurface/domain.fms"

#: One OpenMP thread per rank: the octree passes are threaded, so MPI x threads
#: oversubscribes the node.
OMP_ONE_THREAD = ("OMP_NUM_THREADS=1",)


def _cfmesh_plan(parallel: bool, feature_angle: float) -> MeshPlan:
    """The command pipeline for a chosen MPI policy and crease angle."""
    commands = [
        MeshCommand(
            "surfaceFeatureEdges",
            args=("-angle", f"{feature_angle:g}", SURFACE_STL, SURFACE_FMS),
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


def cfmesh_mesh_plan(settings: CfMeshSettings) -> MeshPlan:
    """The meshing commands for resolved cfMesh settings."""
    return _cfmesh_plan(settings.parallel_meshing, settings.feature_angle)


def cfmesh_plan_from_config(cfg: dict[str, Any]) -> MeshPlan:
    """The meshing commands for a raw config, without resolving the geometry.

    ``cfmesh.parallel_meshing`` and ``cfmesh.feature_angle`` are the only settings
    the plan reads, and both are declared engine keys, so nothing here depends on
    the STL bounds — ``writers/scripts.py`` can render the scripts for a case whose
    geometry has not been measured yet.
    """
    engine = cfg.get("cfmesh", {})
    engine = engine if isinstance(engine, dict) else {}
    return _cfmesh_plan(
        resolve_parallel_meshing(
            engine.get("parallel_meshing", "auto"),
            cfg.get("parallel", {}).get("n_procs", 1),
        ),
        float(engine.get("feature_angle", FEATURE_ANGLE_DEFAULT)),
    )


__all__ = ["OMP_ONE_THREAD", "SURFACE_FMS", "SURFACE_STL", "cfmesh_mesh_plan",
           "cfmesh_plan_from_config"]
