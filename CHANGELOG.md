# Changelog

All notable changes to RapidFOAM will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Parallel cfMesh meshing** (`cfmesh.parallel_meshing`, default `"auto"`): `cartesianMesh` runs under MPI whenever `parallel.n_procs > 1`, decomposes the octree using `system/decomposeParDict`, and is stitched back with `reconstructParMesh -constant` before `checkMesh`. OpenMP is pinned to one thread per rank, the serial `Allrun` is untouched, and both parallel scripts fall back to a serial mesh if the build rejects the parallel run.
- **Trailing-edge refinement** (`mesh_params.trailing_edge_refine` with `te_level`, `te_height_cells`, `te_depth_cells`): one thin refinement region on the downstream-most face of the geometry, for trailing edges thinner than the body cell. Both engines read the region.

### Fixed
- Separate read-only validation, configuration saving, and case generation in Studio.
- Preserve advanced visual-form configuration and cfMesh boundary/ground cell sizes.
- Load the bundled STL and align boundary previews with configured axes and faces.
- Share force parsing between local processing, remote telemetry, and archive summaries.
- Report generation/submission errors and use solver-log timestamps for local activity.
- Escape dynamic HTML, verify SSH host keys, and drain both SSH output streams before waiting for completion.
- Make password storage opt-in and accurately label its on-disk plaintext format.
- Restore shadowed API tests, isolate web test files, and test the actual restart launcher behavior.
- Correct displayed defaults, reporting labels, package versions, queue refresh, navigation accessibility, and responsive layout.
- Restrict turbulence models to the supported kOmegaSST writer and clarify surface-geometry limitations.
- **Thin trailing edges no longer mesh into slivers with cfMesh.** Its automatic curvature and proximity refinement stops at `minCellSize` (`meshOctreeAutomaticRefinement::setMaxRefLevel`), so a body ending in a 1.4 mm blunt strip against a 6.25 mm body cell could not be resolved there. `trailing_edge_refine` resolves it with a local box instead of lowering the global floor, which refines every curved surface it touches.
- Correct the cfMesh profile notes: `minCellSize` caps the automatic refinement, and `localRefinement` does not refine feature-edge cells to `body/2` on its own (`patchRefinement` only reads `cellSize`). The measured cost of the finer floor is now recorded in the profile and README.

## [1.1.0] - 2026-09-10

### Added
- **cfMesh (`cartesianMesh`) Engine**: Integrated cfMesh as an alternative mesher engine for external vehicle and aerospace aerodynamics.
- **Combined Flow Domain Surface Builder**: Generates wind-tunnel faces with inward-facing normals and appends CAD surfaces. It does not repair intersections or certify a closed manifold.
- **Automated `system/meshDict` Synthesis**: Multi-fidelity cell budgeting, surface/edge refinement, and wake refinement boxes for cfMesh.
- **cfMesh-First Ecosystem**: Set `cfMesh` as the primary default mesher across Web Studio UI, CLI, and configuration templates with `snappyHexMesh` preserved as an optional alternative.
- **Boundary Layer Normal Optimization**: Enabled `optimiseLayer 1` and normal smoothing heuristics for uncompromised boundary layer extrusion on multi-element wings and trailing edges.
- **Lean Boundary Cell Budgeting**: Restricting `boundaryCellSize` to base cell size while refining CAD surfaces and ground plane, reducing domain cell count from 10.6M to ~4M cells.

### Fixed
- Fixed OpenMPI SLURM slot starvation on cluster compute nodes by adding `--oversubscribe` to parallel launcher invocations.
- Added automatic `$FOAM_USER_APPBIN` PATH propagation in shell execution scripts.

## [1.0.0] - 2026-09-10

### Initial Public Release

#### Core CFD Automation Engine
- **Automated Case Generation**: Complete OpenFOAM case scaffolding (`0/`, `constant/`, `system/`) from a single JSON configuration.
- **Dynamic Wind Tunnel Derivation**: Computes virtual wind tunnel bounding boxes automatically from ASCII STL CAD bounds with upstream, downstream, roof, and lateral buffer ratios.
- **snappyHexMesh Refinement Heuristics**: Automated generation of surface refinements, explicit feature edge meshes (`surfaceFeatureExtract`), distance refinement shells, and two-stage wake refinement regions (`nearWakeBox`, `farWakeBox`).
- **Boundary Layer Inflation**: Automated prism layer extrusion settings targeting $y^+$ guidelines.
- **Mesh Fidelity Presets**: Built-in presets (`fast`, `standard`, `fine`) with predefined cell count budgets and refinement levels.
- **Symmetry Plane Support**: Half-car simulation support (e.g. `x = 0`) with automatic 2x force scaling across reports and comparisons.
- **Execution Pipeline Scripts**: Generates hardened POSIX execution scripts (`Allrun`, `Allrun.parallel`, `Allclean`, `run.sh`) with signal handling, background monitor termination, and interrupted parallel run reconstruction.
- **OpenFOAM Compatibility**: Supports ESI-OpenCFD releases (`v2006` through `v2606`) and OpenFOAM Foundation (`v8`–`v11`).

#### Real-Time Telemetry & Convergence Monitoring
- **Convergence Auto-Stop**: Live background monitor analyzing rolling window force variation ($\pm 0.5\%$) and gracefully signaling OpenFOAM solvers to stop via `stopAt writeNow;`.
- **Force Analysis CLI**: `rapidfoam-forces` tool for tabulating Drag, Downforce, and L/D ratios, live polling, and multi-case comparisons.

#### Interactive Web Studio
- **3D Viewport**: Real-time CAD and domain wireframe inspection using Three.js and OrbitControls.
- **Live Telemetry Charts**: Streaming force and residual curves powered by Chart.js.
- **Parameter & Preset Editor**: In-browser configuration manager with template presets.
- **Remote Cluster Execution**: SLURM cluster management over SSH/SFTP with job submission (`sbatch`), queue monitoring (`squeue`), and remote log inspection.

#### Packaging & Testing
- Pure zero-dependency core running on Python 3.9+ standard library.
- Comprehensive test suite covering regression checks, script synthesis, API security, and cluster telemetry.
