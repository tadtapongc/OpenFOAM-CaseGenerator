"""Meshing plans — what each engine needs to happen, as data.

A mesher returns a :class:`MeshPlan` (an ordered list of :class:`MeshCommand`s
plus the MPI policy) and ``writers/scripts.py`` renders it. Before this split the
four mesh pipelines (cfMesh and snappy x serial and MPI) were hand-written twice
more in ``scripts.py`` - once for ``Allrun.parallel`` with RunFunctions and once
for ``run.sh`` with explicit redirection - so a change to the meshing order had to
be made in three places and the two spellings could drift.

The plan records *intent*; the two renderers differ only in idiom:

    runApplication <cmd>              # Allrun, logs via RunFunctions
    <cmd> > log.<cmd> 2>&1            # run.sh, explicit per-stage logs

``MeshCommand.mpi`` marks the command that runs under MPI, and
``serial_retry`` the fallback when a build rejects the parallel run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def resolve_parallel_meshing(value: Any, n_procs: Any) -> bool:
    """Whether an engine runs its mesh under MPI.

    A declared ``parallel_meshing`` wins (``"auto"`` is the engine default);
    otherwise more than one rank means the mesh is split. Lives next to
    :class:`MeshPlan` because it is the MPI policy both engines read - cfMesh
    declares the key in its own block, snappy always derives it from
    ``parallel.n_procs``.
    """
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "yes", "1", "on"):
        return True
    if text in ("false", "no", "0", "off"):
        return False
    try:
        return int(n_procs) > 1
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True)
class MeshCommand:
    """One meshing command in a pipeline."""

    tool: str
    args: tuple[str, ...] = ()
    #: Extra arguments appended only by the explicit-mpirun renderer (run.sh),
    #: because ``runParallel`` in RunFunctions adds ``-parallel`` itself.
    mpi_args: tuple[str, ...] = ()
    #: Run under MPI (mpirun in run.sh, runParallel in Allrun).
    mpi: bool = False
    #: Fall back to a serial run if the MPI attempt fails (cfMesh builds without
    #: the parallel octree passes).
    serial_retry: bool = False
    #: After this command succeeds, ``reconstructParMesh -constant`` and
    #: ``rm -rf processor*``: set on the command that ends the MPI mesh phase.
    reconstruct_after: bool = False
    #: Environment exported by run.sh immediately before the serial run.
    env: tuple[str, ...] = ()
    #: Environment exported by run.sh immediately before the MPI attempt.
    env_mpi: tuple[str, ...] = ()
    #: Environment exported by Allrun.parallel immediately before the MPI attempt.
    env_allrun: tuple[str, ...] = ()

    @property
    def log(self) -> str:
        return f"log.{self.tool}"


@dataclass(frozen=True)
class MeshPlan:
    """Everything the script writers need to emit a meshing section."""

    commands: tuple[MeshCommand, ...]
    #: Human label for the mesh section header, e.g. "cfMesh cartesianMesh".
    label: str = "Mesh"
    #: cfMesh ships as a user app: make $FOAM_USER_APPBIN visible when present.
    deploy_user_appbin: bool = False
    #: Whether ``parallel_meshing`` selected the MPI path (used for messaging).
    parallel_meshing: bool = False

__all__ = ["MeshCommand", "MeshPlan", "resolve_parallel_meshing"]
