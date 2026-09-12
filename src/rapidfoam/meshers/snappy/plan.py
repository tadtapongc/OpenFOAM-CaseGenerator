"""snappyHexMesh's meshing plan — the commands ``Allrun``/``run.sh`` render.

``surfaceFeatureExtract`` builds the ``.eMesh`` feature edges from each STL,
``blockMesh`` lays down the background hex, then snappy runs ``-overwrite``. The
parallel path splits first with ``decomposePar``, checks with a *parallel*
``checkMesh`` and stitches the mesh back with ``reconstructParMesh`` (snappy
writes a real decomposed mesh, unlike cfMesh's octree). ``renumberMesh``
reduces the matrix bandwidth for the solve.

Parallel meshing follows ``parallel.n_procs``: snappy splits the mesh itself, so
there is no engine key to gate it on.
"""

from __future__ import annotations

from typing import Any

from rapidfoam.meshers.plan import MeshCommand, MeshPlan
from rapidfoam.meshers.snappy.settings import SnappySettings

#: Rewrites the mesh in place and skips function objects during meshing.
OVERWRITE = ("-overwrite", "-noFunctionObjects")
CHECK_ARGS = ("-allGeometry", "-allTopology", "-noFunctionObjects")


def snappy_mesh_plan(settings: SnappySettings) -> MeshPlan:
    """The meshing commands for resolved snappy settings."""
    parallel = settings.parallel_meshing
    commands = [MeshCommand("surfaceFeatureExtract"), MeshCommand("blockMesh")]
    if parallel:
        commands += [
            MeshCommand("decomposePar"),
            MeshCommand("snappyHexMesh", args=OVERWRITE, mpi=True, mpi_args=("-parallel",)),
            MeshCommand(
                "checkMesh",
                args=CHECK_ARGS,
                mpi=True,
                mpi_args=("-parallel",),
                reconstruct_after=True,
            ),
        ]
    else:
        commands += [
            MeshCommand("snappyHexMesh", args=OVERWRITE),
            MeshCommand("checkMesh", args=CHECK_ARGS),
        ]
    commands.append(MeshCommand("renumberMesh", args=OVERWRITE))
    return MeshPlan(
        commands=tuple(commands),
        label="snappyHexMesh",
        parallel_meshing=parallel,
    )


def snappy_plan_from_config(cfg: dict[str, Any]) -> MeshPlan:
    """Convenience wrapper for callers that only have the raw config."""
    from rapidfoam.meshers.snappy.settings import resolve_snappy_settings

    return snappy_mesh_plan(resolve_snappy_settings(cfg))


__all__ = ["snappy_mesh_plan", "snappy_plan_from_config"]
