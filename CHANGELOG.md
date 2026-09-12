# Changelog

All notable changes to RapidFOAM will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Geometry-relative cell sizing** (`mesh_params.base_cell_size: "auto"`, `mesh_params.cells_per_length`): the fidelity presets now size the background cell from the model itself — `longest bounding-box dimension / cells_per_length` (20 / 30 / 37.5 for `fast` / `standard` / `fine`) — so the same preset means the same resolution per model length, and roughly the same cell count, on a full FSAE car, a front wing, a rear wing or a subassembly. A 1.2 m front wing gets 2.5x finer cells than a 3.0 m car at `standard` (0.04 m base, 2.5 mm body, 0.6 mm edge) instead of the car-scale 6.25 mm body cell. The presets reproduce the previous absolute values at the 3.0 m length they were tuned on; an explicit `base_cell_size` in metres pins the old behaviour. Distance shells moved from metres to multiples of the base cell (`distance_shells`), and `case_config.json` records `base_cell_size_mode` plus the resolved `cells_per_length`.
- **Trailing-edge refinement is on by default** in every fidelity preset (`mesh_params.trailing_edge_refine`, still `false`-able): thin downstream edges are now resolved without a case-by-case opt-in. The default moved from the cfMesh profile to the fidelity presets so snappy and cfMesh share it.
- **Self-describing fidelity presets**: `desc`, `cell_estimate`, `n_cells_target` and `runtime_estimate` are populated for `fast`/`standard`/`fine` (the keys `GET /api/config/schema-defaults` already returned, previously empty).
- **The Studio's Overrides tab follows the selected mesher.** Every "Auto (…)" label in the Expert > Overrides tab is now rendered from the schema payload for the selected *engine and fidelity* instead of from static HTML and a JavaScript copy of the presets: mesh-parameter hints are tagged with the engine (`Auto (snappy: 6)`), the wake levels show the offset the preset resolves to (`Auto (cfmesh: level 3 = surface L4 - 1)`), the model-relative base cell shows the divisor (`Auto (cfmesh: model length / 30 = 0.10 m on a 3.0 m car)`), and a `mesh_params` key the engine does not read is disabled with the reason named (`mesh_params.min_cell_size` on snappy). `GET /api/config/schema-defaults` now returns the fidelity presets in full (levels, wake offsets, layer settings, solver cadence) rather than only `cells_per_length`, so the UI keeps no second copy of them; the static HTML placeholders remain the pre-fetch fallback.
- **Parallel cfMesh meshing** (`cfmesh.parallel_meshing`, default `"auto"`): `cartesianMesh` runs under MPI whenever `parallel.n_procs > 1`, decomposes the octree using `system/decomposeParDict`, and is stitched back with `reconstructParMesh -constant` before `checkMesh`. OpenMP is pinned to one thread per rank, the serial `Allrun` is untouched, and both parallel scripts fall back to a serial mesh if the build rejects the parallel run, keeping the failed attempt's log in `log.cartesianMesh.parallel` and echoing its last lines to the job output.
- **Trailing-edge refinement** (`mesh_params.trailing_edge_refine` with `te_level`, `te_height_cells`, `te_depth_cells`): one thin refinement region on the downstream-most face of the geometry, for trailing edges thinner than the body cell. Both engines read the region.
- The shipped `configs/config.json` template now documents the trailing-edge knobs and `cfmesh.parallel_meshing` next to the other cfMesh-native keys, so a case config copied from it cannot silently drop them; the generated summary lists `Region trailingEdgeBox: Level <n>` as the pre-submit check.

### Changed

- **cfMesh is a module now, not a writer with policy inside it.** Everything cfMesh-specific lives under `src/rapidfoam/meshers/`: `cfmesh/keys.py` declares the engine's config surface, `cfmesh/settings.py` resolves every `"auto"`, alias and default into one frozen `CfMeshSettings`, `cfmesh/mesh_dict.py` renders `system/meshDict` from those settings, `cfmesh/surface.py` writes `domain.stl`, and `cfmesh/plan.py` returns the meshing commands as data. Cell sizing (`meshers/sizing.py`), the fidelity presets (`meshers/presets.py`) and the wake/trailing-edge regions (`meshers/refinement.py`) are engine-neutral and shared with snappy, and `config.validate` is driven by the same key tables. See [docs/meshers.md](docs/meshers.md).
- **One meshing plan, three spellings.** `writers/scripts.py` used to carry seven hand-written pipelines (cfMesh and snappy x `Allrun`, `Allrun.parallel`, `run.sh`); it now renders the plan the selected mesher returns, so the serial/MPI policy and the parallel-fallback idiom exist once per renderer instead of once per mesher.
- **snappyHexMesh is a package too, and its defaults have one home.** `meshers/snappy.py` and `writers/snappy.py` became `src/rapidfoam/meshers/snappy/`: `keys.py` declares the config surface, `settings.py` resolves every default and derived value into a frozen `SnappySettings` (the `blockMesh` divisions, the auto `locationInMesh` corner, the relative first-layer thickness, the castellated/snap/layer/quality blocks), `block_mesh_dict.py` / `surface_feature_extract_dict.py` / `snappy_hex_mesh_dict.py` render from those settings only, and `plan.py` returns the meshing commands. That removes the last duplicate defaults in the writer: `maxGlobalCells` said 30M in the renderer against 18M in the shared `mesh_params` table, and `feature_extract.includedAngle` said 150 against `DEFAULT_CONFIG`'s 140 — both now read the declared default, so what the dictionaries fall back to and what a case starts from cannot drift apart. `resolve_parallel_meshing` moved into `meshers/plan.py`, which both engines share, and the generated dictionaries are byte-for-byte unchanged.
- **The cfMesh/snappy key split is declared once, not repeated.** Every `mesh_params` key in `meshers/refinement.py` now names the engines that read it (`KeySpec.engines`), and the per-engine key lists (`CfMesh.mesh_params_keys()` / `Snappy.mesh_params_keys()`), the Studio schema and the validation warning are derived from that declaration. `rapidfoam validate` therefore warns for either engine — a snappy case that sets `min_cell_size`, or a cfMesh case that sets `maxGlobalCells` — instead of the cfMesh-only hard-coded list it used before, and the warning now covers `allowFreeStandingZoneFaces`, `locationInMesh`, `maxLoadUnbalance` and `distance_shells`, which the old list missed.
- **The mesher profiles contain keys, not essays.** The tuning narratives that filled `mesher_profiles/*.json` (measured A/B cell counts, cluster timings) moved to `docs/meshers.md`; the profiles keep only what a project can override, and engine defaults now come from the profile rather than `DEFAULT_CONFIG`, so a project-local `configs/meshers/<engine>.json` can no longer be shadowed by the built-in defaults.

### Removed

- **cfMesh keys that nothing read, or that said the same thing in two places** - each is now rejected with the replacement named in the error: `mesh_params.cell_size_mode` (a label for whichever resolution branch had won), `mesh_params.cell_budget_enforced` (cfMesh has no cell cap - read the mesher's `enforces_cell_budget`), `cfmesh.workflow` (the mesher registry selects the executable) and `cfmesh.layer_mode` (use `layers.ground_layers`, which does the same thing in one place).
- **`writers/snappy.py` and `writers/mesh.py`** - the snappy dictionaries are rendered from resolved settings under `meshers/snappy/`, next to the engine that reads them, so `writers/` holds fields, solver files and scripts only. The deprecated alias module had nothing left to alias.
- **`ground_refine`, `ground_cell_size`, `boundary_cell_size` and `refinement_thickness` moved into the `cfmesh` block.** Each was previously accepted in `mesh_params` *and* `cfmesh`, with the `mesh_params` copy silently winning; they are engine keys (snappy never refines the road plane), and a config that still uses the `mesh_params` spelling is now told where they went.


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
- Validate snappy's own config surface: a `snappy` block that is not an object is an error, and a key in it that nothing reads (a typo such as `octree_leves`) is reported instead of being ignored silently.
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
