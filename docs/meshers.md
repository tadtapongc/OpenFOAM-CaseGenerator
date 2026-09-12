# Meshers: cfMesh and snappyHexMesh

RapidFOAM can mesh a case with either engine, and the mesher is selected per case
(`"mesher": "cfmesh"` or `"snappy"`, or `--mesher snappy` on the CLI). cfMesh
(`cartesianMesh`) is the default.

This page is the reference for *why* the two engines are configured differently,
what each key means in engine terms, and which settings were removed.

## Why one config cannot be fed to both engines

The two meshers do not mean the same thing by the same numbers:

| | snappyHexMesh | cfMesh |
|---|---|---|
| Refinement size | *relative* levels: `level 4` = `base_cell_size / 2**4` | *absolute* metres: `cellSize 0.00625;` |
| Feature edges | only the cells touching the extracted `.eMesh` edges (`edge_level`) | refines feature-edge cells one level finer than the surface cell on its own |
| Cell cap | `maxGlobalCells` / `maxLocalCells` | none |
| Distance refinement | `mode distance` shells around the surface | implicit in the octree; only explicit refinement boxes |
| Layers | `addLayersControls` | `boundaryLayers` + `patchBoundaryLayers` |

Feeding one dictionary to both writers is what once produced **449 k cells with
snappy and 4.4 M with cfMesh from the same config**. RapidFOAM therefore keeps the
physical intent in the case config (flow, domain, fidelity, `mesh_params`) and
lets each engine translate it:

```
DEFAULT_CONFIG -> mesher profile -> case config
-> case mesh_params_<mesher> -> case overrides
```

* Engine keys are declared once, in `src/rapidfoam/meshers/<engine>/keys.py`.
  `rapidfoam validate` and the Studio UI both read that declaration.
* Each engine is a package with the same shape: `settings.py` resolves every
  default and derived number, the `*dict.py` modules render from those settings
  and nothing else, and `plan.py` returns the meshing commands. `writers/` no
  longer holds any meshing dictionary.
* The shipped profiles (`src/rapidfoam/mesher_profiles/<engine>.json`) exist so a
  project can retune an engine once - drop `configs/meshers/<engine>.json` in your
  project to override them for every case.
* This page is where the tuning narratives live; the profiles contain only keys.

## Cell sizing (shared)

Every size is derived from the model:

| Key | Meaning |
|---|---|
| `mesh_params.base_cell_size` | `"auto"` (default) = `max_extent / cells_per_length`, where `max_extent` is the longest bounding-box dimension. A number pins it in metres and restores the absolute behaviour. |
| `mesh_params.cells_per_length` | Background cells across the longest dimension: `20` fast, `30` standard, `37.5` fine. Raise it to resolve a front wing or a subassembly at the same preset. |
| `mesh_params.body_cell_size` | Absolute surface cell size in metres; the levels are derived from it, so one statement drives both engines. |
| `mesh_params.surface_level` / `edge_level` | Levels (`[body, feature]` / feature edges) the shared sizing turns into the body and edge cells; snappy reads the levels directly, cfMesh the metres. |
| `mesh_params.edge_cell_size` | Absolute feature-edge cell size in metres. |

The presets are calibrated to the old car-scale absolutes (`0.15 / 0.10 / 0.08 m`)
at the 3.0 m reference length they were tuned on, so a 3.0 m car is unchanged
while a 1.2 m front wing is meshed 2.5x finer at the same relative cost:

| Model | `standard` base cell | Body cell | TE box cell |
|---|---|---|---|
| 3.0 m car | 0.100 m | 6.25 mm | 0.78 mm |
| 2.9 m car | 0.0967 m | 6.04 mm | 0.76 mm |
| 1.2 m front wing | 0.040 m | 2.50 mm | 0.31 mm |
| 1.0 m sample body | 0.0333 m | 2.08 mm | 0.26 mm |

The bundled 1.0 m sample therefore resolves *finer* than the documented car-scale
1.8 M-cell run; pin `base_cell_size` to `0.10` to reproduce that run's cells (the
wake boxes stay model fractions, so their extents follow the model even when the
cell size is pinned).

### Wake boxes and the cell budget

The wake boxes are the one part of a case that can quietly cost more than the model
itself, so both of their dimensions are relative:

* **Size** - `nearWakeBox` / `farWakeBox` are fractions of the model (the `WAKE_*`
  constants in `src/rapidfoam/meshers/refinement.py`): 1.2 model lengths behind the
  body for the near box, 3.5 for the far box, lateral/top pads of 15 % / 25 % of the
  model, floors of 3 % / 5 % of the model length. They used to be floored in metres
  (2.0 / 4.0 m long, 0.10-0.25 m thick), which the 3.0 m calibration turned into a
  small-model trap: a 1.0 m body asked for a 2.4 m wake box at level 3, i.e. 4.5 M
  cells, 55 % of a standard mesh and 27x the same box on the car those floors were
  written for (box volume ~ `L**3` while the cell size ~ `L`).
* **Level** - `mesh_params.wake_levels_below_surface` (`[near, far]`, default
  `[1, 3]`) says how many levels *below* `surface_level[0]` the boxes sit, so a case
  (or a `body_cell_size`) that refines the surface refines the wake with it. State
  `near_wake_level` / `far_wake_level` for an absolute level.

Every generation then prices the result - the background, each distance shell and
each region, as `cells ~ volume / cell_size**3` - and prints it:

```
  Cell budget (estimate, cells = volume / cell size^3, cap 18,000,000 cells):
    region                           level   cell size         cells   share
    background (blockMesh)               -     33.3 mm       216,300      5%
    surface shell 8 mm                   4      2.1 mm     1,035,048     23%
    nearWakeBox                          3      4.2 mm       933,638     21%
    trailingEdgeBox                      7     0.26 mm     1,964,461     44%
    estimated total                                        4,489,341     25%
```

It warns when the estimate passes 80 % of `maxGlobalCells` - snappy **stops
refining** once the cap is reached, which is what leaves a mesh very fine in one
place and too coarse in another - and names the region that dominates the total,
because one level coarser is 8x cheaper. `rapidfoam` prices it for both engines
(cfMesh has no cap, so its line is a cost estimate against the preset's target) and
the Studio returns the same numbers from `POST /api/case/validate`
(`cell_budget`). The numbers are order-of-magnitude: the octree fills a region with
full cells but leaves partial cells at its boundary, and `nCellsBetweenLevels` adds
buffer cells that are not priced. `grep -m1 cells: log.checkMesh` remains the
measurement.

## cfMesh

### How RapidFOAM runs it

```
surfaceFeatureEdges -angle <cfmesh.feature_angle> domain.stl domain.fms
cartesianMesh
reconstructParMesh -constant      # only when meshing in parallel
checkMesh -noFunctionObjects
renumberMesh -overwrite -noFunctionObjects
```

`domain.stl` is written by RapidFOAM: the six wind-tunnel box faces (inward
normals, so the box is the fluid) concatenated with your CAD solids (outward
normals, so the model is a hole). It **concatenates** surfaces - it does not clip
CAD, repair intersections or certify a closed manifold - and `rapidfoam generate`
warns when CAD touches or crosses the domain boundary.

cfMesh ships as a user app, so the generated scripts add `$FOAM_USER_APPBIN` to
`PATH` when it is set.

### Cell sizes in `system/meshDict`

| Key | Meaning |
|---|---|
| `mesh_params.base_cell_size` -> `maxCellSize` | Background cell of the wind-tunnel box. |
| `mesh_params.min_cell_size` -> `minCellSize` | **Global floor** for cfMesh's automatic refinement: curvature and proximity refinement stops here on *every* surface. `"body"` (default), `"edge"`, `"base"`, or metres. |
| `cfmesh.boundary_cell_size` -> `boundaryCellSize` | Cell size on the tunnel walls (default: the base cell). |
| `mesh_params.body_cell_size` / `edge_cell_size` | Cells on the model surface and, one level finer, on feature edges. |

`minCellSize` is the most expensive knob, because it is global. On the bundled
wing, with an identical STL and config and only this key changed:

| `min_cell_size` | Cells | Mesh time | Job time |
|---|---|---|---|
| 0.0015625 m (`"edge"`) | 3.95 M | 311 s | 79m49s |
| 0.00625 m (`"body"`, default) | 1.82 M | 130 s | 12m58s |

That is why the default is `"body"`: snappy's `edge_level` only refines the cells
touching extracted feature edges, so using it as cfMesh's global floor refined the
whole car two levels deeper than intended.

### Trailing-edge refinement (`mesh_params.trailing_edge_refine`)

A trailing edge can be thinner than the body cell - the bundled test body ends in
a 1.4 mm blunt strip against a 6.25 mm cell - and cfMesh cannot create a cell that
small because `minCellSize` stops it. The remaining slivers are removed by one
thin refinement box (`objectRefinements/trailingEdgeBox`) on the downstream-most
face of the geometry, on by default in every preset:

| Key | Meaning |
|---|---|
| `trailing_edge_refine` | `true` (preset default) adds the box; `false` drops it. |
| `te_level` | Box cell = `base_cell_size / 2**te_level`. `"auto"` = `edge_level + 1`, roughly two cells across a thin blunt edge (level 7 = 0.78 mm on a 3.0 m car). Level 6 only halves the slivers; level 8 resolves the gap cleanly at 8x the box cost. |
| `te_height_cells` | Half-height band in body cells, centred on the body's mid-height. |
| `te_depth_cells` | Extent upstream of the trailing-edge plane in body cells, plus one cell downstream. |

Lowering `minCellSize` instead refines every curved surface it touches: one octree
level on the recorded A/B marked 29 229 + 116 543 curvature-refined boxes. snappy
reads the same region, so the setting works with either engine.

Verify with:

```bash
grep -A6 trailingEdgeBox system/meshDict
grep -m1 cells: log.checkMesh
```

### Layers

`boundaryLayers` lists one entry per STL surface, with `nLayers` taken from
`layers.n_layers` and the thickness from `layers.expansion_ratio` /
`layers.first_layer_thickness` (or `layers.first_layer_height` when
`layers.first_layer_mode` is `"absolute"`). cfMesh treats the first-layer height as
an upper bound and compresses the stack to fit the local cell, so the way to raise
y+ into the wall-function range is a coarser *body* cell, not a larger number here.

The top-level `nLayers` is `0` and each patch is listed explicitly, so the road
plane is unlayered unless `layers.ground_layers` is `true`. (The old
`cfmesh.layer_mode: "global"` switch, which layered every patch including the road,
is gone: `ground_layers` says the same thing in one place.)

`cfmesh.optimise_layer` runs cfMesh's layer optimisation plus normal smoothing -
the most expensive pass - and `"auto"` (the default) keeps it for `standard`/`fine`
and skips it for `fast`, where the smoothness does not matter. The
`cfmesh.optimisation` sub-keys (`nSmoothNormals`, `maxNumIterations`,
`featureSizeFactor`, `reCalculateNormals`, `relThicknessTol`) are written only when
it runs.

### Parallel meshing (`cfmesh.parallel_meshing`)

`"auto"` (the default) runs `cartesianMesh` under `mpirun` when
`parallel.n_procs > 1`. cfMesh decomposes the octree itself using
`numberOfSubdomains` from `system/decomposeParDict`, so **no `decomposePar` is
needed for meshing** - only for the solver afterwards. The stitched mesh comes back
with `reconstructParMesh -constant` before `checkMesh`, and OpenMP is pinned to one
thread per rank to avoid oversubscription.

Not every build ships the parallel octree, so the MPI attempt keeps its own log:

* `Allrun.parallel` retries serially and moves the failed log aside as
  `log.cartesianMesh.parallel`, tailing its last 20 lines to the job output.
* `run.sh` runs `mpirun --oversubscribe -np $SLURM_NTASKS cartesianMesh -parallel`
  into `log.cartesianMesh.parallel`, falls back to a serial run if that fails, and
  reconstructs only when the parallel attempt succeeded.

`parallel_meshing: false` forces the serial path; a single-rank case always meshes
serially.

> **Still to verify on the cluster:** whether the installed cfMesh build accepts
> `-parallel` (`grep -i parallel log.cartesianMesh.parallel`) and how the
> trailing-edge box interacts with `minCellSize` in the parallel octree split.

## snappyHexMesh

```
surfaceFeatureExtract
blockMesh
decomposePar                       # when parallel
snappyHexMesh -overwrite -noFunctionObjects
checkMesh -allGeometry -allTopology -noFunctionObjects
reconstructParMesh -constant       # when parallel
renumberMesh -overwrite -noFunctionObjects
```

snappy's dictionaries live in their own sections (`snap`, `layers`, `mesh_quality`,
`feature_extract`, `potential_flow`); the `mesh_params` keys it reads are
`surface_level`, `edge_level`, `distance_levels`, `refinement_regions`,
`wake_levels_below_surface` (plus an absolute `near_wake_level` / `far_wake_level`),
`nCellsBetweenLevels`, `maxGlobalCells`, `maxLocalCells`, `minRefinementCells`,
`resolveFeatureAngle`, `allowFreeStandingZoneFaces` and `locationInMesh`, plus the
sizing keys both engines share. `distance_shells` are multiples of the base cell, so
they follow the model scale; `distance_levels` are absolutes in metres and take
precedence. `meshers/budget.py` prices whatever those keys produce; the CLI prints
it and warns against `maxGlobalCells`.

`mesh_params.min_cell_size` is cfMesh's dial and snappy has no equivalent, so
`rapidfoam validate` warns on either engine when a case sets a key the selected
engine never reads. Which keys belong to whom is declared once, as `engines=` on
each key in `rapidfoam/meshers/refinement.py`; the warning, the per-engine key
lists and the Studio UI all read that declaration instead of restating it.

## Removed keys

These were accepted before the mesher split and are now rejected with the
replacement named in the error:

| Key | Use instead |
|---|---|
| `mesh_params.cell_size_mode` | Nothing: `body_cell_size` / `edge_cell_size` / `min_cell_size` state the sizes once and each engine translates them. |
| `mesh_params.cell_budget_enforced` | Nothing: ask the mesher. cfMesh has no cap; snappy always does. |
| `mesh_params.ground_refine` | `cfmesh.ground_refine` (an engine key: snappy never refines the road). |
| `mesh_params.ground_cell_size` | `cfmesh.ground_cell_size`. |
| `mesh_params.boundary_cell_size` | `cfmesh.boundary_cell_size`. |
| `mesh_params.refinement_thickness` | `cfmesh.refinement_thickness`. |
| `cfmesh.layer_mode` | `layers.ground_layers`. |
| `cfmesh.workflow` | Nothing: the mesher registry selects the executable. |

## Key reference

The authoritative list is the code:

* `src/rapidfoam/meshers/refinement.py` - `MESH_PARAMS_KEYS` (every shared sizing
  and refinement key, with its kind, default and the engines that read it) plus
  `keys_for(engine)` / `unread_keys(mesh, engine)`
* `src/rapidfoam/meshers/cfmesh/keys.py` - `CFMESH_KEYS`, `OPTIMISATION_KEYS`,
  `REMOVED_ENGINE_KEYS`, `REMOVED_KEYS`
* `src/rapidfoam/meshers/snappy/keys.py` - `SNAPPY_KEYS` (empty today), `REMOVED_KEYS`

Both engines are laid out the same way - one module per responsibility:

| Module | Holds |
|---|---|
| `<engine>/keys.py` | the config surface it reads, declared once |
| `<engine>/settings.py` | every default, `"auto"` and derived value, resolved once into a frozen settings object |
| `<engine>/mesh_dict.py` (snappy: `block_mesh_dict.py`, `surface_feature_extract_dict.py`, `snappy_hex_mesh_dict.py`) | the dictionaries, rendered from settings only |
| `<engine>/plan.py` | the meshing commands as data (`mesh_plan`) |

snappy's defaults live in `meshers/snappy/settings.py` (`SNAP_DEFAULTS`,
`LAYER_DEFAULTS`, `QUALITY_DEFAULTS`, `RELAXED_DEFAULTS`, `FEATURE_DEFAULTS`) and
are the same numbers as the `snap` / `layers` / `mesh_quality` /
`feature_extract` sections of `DEFAULT_CONFIG`; the caps and angles that belong to
`mesh_params` (`maxGlobalCells`, `nCellsBetweenLevels`, `resolveFeatureAngle`, ...)
are read from the shared declaration in `meshers/refinement.py` instead of being
restated, and `meshers/plan.py` owns the MPI policy both engines share.

The Studio UI reads the same tables from `GET /api/config/schema-defaults`
(`mesher_keys`, `mesh_params_keys`, `fidelity_presets`, `mesher_defaults`), so its
placeholders and descriptions cannot drift from the code. Every "Auto (…)" label
in the Overrides tab is rendered for the **selected engine and fidelity** — the
mesh-parameter controls are tagged with that engine (`Auto (snappy: 6)`), the wake
levels are shown as the offset the preset resolves to (`Auto (cfmesh: level 3 =
surface L4 - 1)`), and a `mesh_params` key the engine does not read
(`min_cell_size` on snappy) is disabled with the reason named, using each key's
declared `engines` list rather than a second list in JavaScript. The static HTML
placeholders are only the pre-fetch fallback.
