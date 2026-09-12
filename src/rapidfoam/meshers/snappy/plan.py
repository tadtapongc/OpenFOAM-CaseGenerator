"""snappyHexMesh's meshing plan — the commands ``Allrun``/``run.sh`` render.

``surfaceFeatureExtract`` builds the ``.eMesh`` feature edges from each STL,
``blockMesh`` lays down the background hex, then snappy runs ``-overwrite``. The
parallel path splits first with ``decomposePar``, checks with a *parallel*
``checkMesh`` and stitches the mesh back with ``reconstructParMesh`` (snappy
writes a real decomposed mesh, unlike cfMesh's octree). ``renumberMesh``
reduces the matrix bandwidth for the solve.

Parallel meshing follows ``parallel.n_procs``: snappy splits the mesh itself, so
there is no engine key to gate it on — which is why
:func:`snappy_plan_from_config` can build the plan from a raw config, before any
STL bounds are measured.
"""

from __future__ import annotations

from typing import Any

from rapidfoam.meshers.plan import MeshCommand, MeshPlan, resolve_parallel_meshing
from rapidfoam.meshers.snappy.settings import SnappySettings

#: Rewrites the mesh in place and skips function objects during meshing.
OVERWRITE = ("-overwrite", "-noFunctionObjects")
CHECK_ARGS = ("-allGeometry", "-allTopology", "-noFunctionObjects")


def _snappy_plan(parallel: bool) -> MeshPlan:
    """The command pipeline for a chosen MPI policy."""
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


def snappy_mesh_plan(settings: SnappySettings) -> MeshPlan:
    """The meshing commands for resolved snappy settings."""
    return _snappy_plan(settings.parallel_meshing)


def snappy_plan_from_config(cfg: dict[str, Any]) -> MeshPlan:
    """The meshing commands for a raw config, without resolving the geometry.

    The only setting the plan reads is the MPI policy, and snappy always derives
    that from ``parallel.n_procs`` (see
    :func:`rapidfoam.meshers.snappy.settings.resolve_snappy_settings`), so nothing
    here depends on the STL bounds — ``writers/scripts.py`` can render the scripts
    for a case whose geometry has not been measured yet.
    """
    return _snappy_plan(
        resolve_parallel_meshing("auto", cfg.get("parallel", {}).get("n_procs", 1))
    )


__all__ = ["snappy_mesh_plan", "snappy_plan_from_config"]
