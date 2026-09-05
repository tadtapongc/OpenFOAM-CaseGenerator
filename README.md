# OpenFOAM Case Generator for External Aerodynamics

An automated OpenFOAM case generator designed for external aerodynamics and Formula Student / FSAE vehicle development. Give it an STL file and a minimal JSON config — it automatically generates a complete, ready-to-run OpenFOAM case with geometry-adaptive meshing, robust solver settings, boundary layer inflation, and force post-processing.

---

## Key Features

- **Optimized for FSAE Aerodynamics** — Mesh architecture tuned specifically for vehicle aerodynamics, delivering the optimal simulation sweet spot (~6–9 million cells on standard fidelity).
- **Two-Stage Wake Architecture** — Replaces massive uniform wake boxes with a high-resolution `nearWakeBox` (capturing rear wing vortices and diffuser separation) and an efficient `farWakeBox` (downstream transport without cell bloat).
- **Zero-Tweak Model Switching** — Automatic domain sizing (`"domain_box": "auto"`) fits the virtual wind tunnel to any CAD geometry, automatically aligning the road ground plane and vehicle centerline.
- **Non-Zero Centerline / Symmetry Plane Support** — Native support for CAD models exported with offsets (`"symmetry_plane": -0.1185` or `0.0`), automatically trimming half-car models cleanly.
- **Robust Incompressible Solver Setup** — `potentialFoam` initialization $\rightarrow$ `simpleFoam` (SIMPLEC) with cell-limited bounded TVD schemes and Spalding continuous wall functions ($k$-$\omega$ SST).
- **Auto-Stop Convergence Monitor** — Real-time monitor tracks forces and cleanly stops `simpleFoam` when variations drop below 0.5%, saving valuable cluster node hours.
- **HPC & SLURM Ready** — Pre-configured for cluster execution with fast node RAM/scratch (`$TMPDIR`) live synchronization, alongside local parallel execution scripts.

---

## Quick Start

### Prerequisites

- [OpenFOAM v2512 / v2606](https://www.openfoam.com/download) (ESI/OpenCFD distribution)
- Python ≥ 3.9 (standard library only for case generation)
- (Optional) `matplotlib` for generating convergence history plots

### Setup

```bash
git clone https://github.com/tadtapongc/OpenFOAM-CaseGenerator
cd OpenFOAM-CaseGenerator
```

---

## Usage Workflow

### 1. Place STL Geometry
Place your ASCII STL geometry file into the `stl/` folder:
```bash
cp my_car.STL stl/
```

### 2. Configure Case (`configs/config.json`)
Edit `configs/config.json` to specify your case name and STL file:
```json
{
    "case_name": "RP14_FSAE",
    "stl_files": ["RP14.STL"],
    "fidelity": "standard",

    "flow": {
        "velocity": 16.67,
        "direction": "-z",
        "ground": true
    },

    "outputs": {
        "drag_axis": "-z",
        "downforce_axis": "-y"
    },

    "domain_box": "auto",
    "symmetry_plane": -0.1185,

    "domain_faces": {
        "-x": "symmetry",
        "+x": "farField",
        "-y": "ground",
        "+y": "farField",
        "+z": "inlet",
        "-z": "outlet"
    },

    "parallel": {
        "n_procs": 32
    }
}
```

### 3. Preview Case (Dry Run)
Check geometry bounds, auto-domain dimensions, and mesh parameters before generating:
```bash
python setup_case.py configs/config.json --dry-run
```

### 4. Generate Case Files
Generate the complete OpenFOAM directory structure under `cases/<case_name>/`:
```bash
python setup_case.py configs/config.json
```

### 5. Run Simulation
Navigate into the generated case directory:
```bash
cd cases/RP14_FSAE

# Option A: Run locally in parallel (e.g. 32 cores)
./Allrun.parallel

# Option B: Submit to SLURM cluster
sbatch run.sh

# Option C: Clean / reset case
./Allclean
```

### 6. Post-Processing & Force Analysis
Analyze convergence and aerodynamic forces using `read_forces.py`:
```bash
# Print force summary (Drag, Downforce, L/D, convergence status)
python read_forces.py

# Plot force convergence history (requires matplotlib)
python read_forces.py --plot

# Live monitoring during simulation solve (refreshes automatically)
python read_forces.py --live

# Compare forces across all generated cases
python read_forces.py --compare
```

Example force report with automatic symmetry detection:
```text
=================================================================
  FORCE RESULTS (1210 iterations)
  ℹ  SYMMETRY DETECTED: Showing Half-Model and Full-Car (x2)
=================================================================
  [Half-Model Simulated]
    Drag (-z):           123.229 N
    Downforce (-y):       300.943 N
    L/D:                     2.442

  [Full-Car Projected (x2)]
    Drag (-z):           246.459 N
    Downforce (-y):       601.887 N
    L/D:                     2.442
-----------------------------------------------------------------
  Averaged (last 200 iterations):
    Half-Model:  Drag =   122.549 N (±0.23%) | DF =   298.384 N (±0.49%)
    Full-Car:    Drag =   245.099 N (±0.23%) | DF =   596.769 N (±0.49%)
    L/D:             2.435
  Status: ✓ CONVERGED
=================================================================
```

---

## Configuration Reference

### Essential Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `case_name` | string | *required* | Output directory created under `cases/<case_name>/` |
| `stl_files` | list | *required* | List of STL filenames in `stl/` |
| `fidelity` | string | `"standard"` | Quality preset: `"fast"`, `"standard"`, or `"fine"` |
| `flow.velocity` | float | `16.67` | Freestream velocity in m/s (16.67 m/s ≈ 60 km/h) |
| `flow.direction` | string | `"-z"` | Freestream flow direction (`"-z"`, `"+z"`, `"-x"`, etc.) |
| `flow.ground` | boolean | `true` | `true` enables moving ground wall at freestream velocity |
| `domain_box` | string / dict | `"auto"` | `"auto"` derives wind tunnel bounds from STL; or supply `{"min": [...], "max": [...]}` |
| `symmetry_plane` | float | *optional* | Centerline coordinate if vehicle symmetry is not at 0.0 (e.g. `-0.1185`) |
| `ground_clearance` | float | *optional* | Gap in meters below lowest STL point (e.g. `0.035` for 35 mm front wing ride height) |
| `ground_plane` | float | *optional* | Fixed absolute coordinate of ground plane (e.g. `0.0` or `-0.050`) |
| `parallel.n_procs` | integer | `10` | Number of CPU cores for MPI decomposition; the supplied main config selects 32 |

### Ground Level & Ride Height Sweeps (Optional)

Adjust the road position relative to the geometry for full-car simulations, front wing studies, or ride height sweeps:

- **Style 1 — Relative Clearance (`ground_clearance`)**: Gap in meters below the lowest point of the STL. Ideal for front wing ride-height sensitivity studies ($h = 25\text{ mm}, 35\text{ mm}, 50\text{ mm}$):
  ```json
  "ground_clearance": 0.035   // 35 mm ride height below lowest wing feature
  ```
- **Style 2 — Absolute Coordinate (`ground_plane`)**: Fixed coordinate of the road in CAD space. Ideal when geometry is exported in full-vehicle assembly coordinates:
  ```json
  "ground_plane": 0.0         // Road plane fixed at y = 0.0
  ```
*(If omitted, the ground plane snaps to the lowest point of the vehicle unless `ground_clearance` is supplied. An explicit `ground_plane: 0.0` places the road at absolute zero.)*

### Aircraft & Free-Flight Simulation (Optional)

To simulate an airplane, UAV, or wing outside of ground effect in open air:
```json
"flow": {
    "velocity": 30.0,
    "direction": "-z",
    "ground": false            // Disable moving road
},
"outputs": {
    "drag_axis": "-z",
    "downforce_axis": "+y"     // +y reports positive Lift (instead of downforce)
},
"domain_faces": {
    "-x": "symmetry",          // or "farField" for full aircraft
    "+x": "farField",
    "-y": "farField",          // Open atmosphere below aircraft (auto-pads 4x height)
    "+y": "farField",          // Open atmosphere above aircraft
    "+z": "inlet",
    "-z": "outlet"
}
```

### Fluid & Ambient Properties (Optional)

```json
"fluid": {
    "rho": 1.225,       // Air density in kg/m³ (Standard air: 1.225; hot 35°C track: ~1.145)
    "nu": 1.516e-5      // Kinematic viscosity in m²/s (Standard air: 1.516e-5; 35°C: ~1.66e-5)
}
```

---

## Fidelity Presets (FSAE Optimized)

| Parameter | Fast | Standard (FSAE Default) | Fine |
| :--- | :--- | :--- | :--- |
| **Base cell size** | 0.15 m (150 mm) | 0.10 m (100 mm) | 0.08 m (80 mm) |
| **Surface refinement** | Level [3, 4] (18.8–9.4 mm) | Level [4, 5] (6.25–3.12 mm) | Level [5, 6] (2.5–1.25 mm) |
| **Edge refinement** | Level 5 (4.7 mm) | Level 6 (1.56 mm) | Level 7 (0.62 mm) |
| **Near Wake Box** | Level 2 (37.5 mm) | Level 3 (12.5 mm) | Level 4 (5.0 mm) |
| **Far Wake Box** | Level 1 (75.0 mm) | Level 1 (50.0 mm) | Level 2 (20.0 mm) |
| **Boundary layers** | 3 layers | 5 layers | 6 layers |
| **Expansion ratio** | 1.30 | 1.20 | 1.15 |
| **nCellsBetweenLevels** | 2 | 2 | 2 |
| **resolveFeatureAngle** | 35° | 35° | 30° |
| **Approximate Cell Count** | **~2–4 Million** | **~6–9 Million** | **~12–16 Million** |
| **Solving Time (32 cores)** | ~10–15 min | ~30–60 min | ~2–4 hours |
| **Primary Use Case** | Rapid concept iteration | Standard FSAE aerodynamic design | Final aerodynamic report validation |

---

## Simulation Architecture

### Mesh Pipeline
1. `surfaceFeatureExtract` — Extracts sharp aerodynamic edges (wing trailing edges, endplate perimeters, gurneys) with `includedAngle = 140°`.
2. `blockMesh` — Hex background mesh sized to domain box with ground alignment.
3. `snappyHexMesh`:
   - **Castellated mesh**: Distance shells (`25mm→L4`, `80mm→L3`) + Two-stage wake (`nearWakeBox` L3 + `farWakeBox` L1).
   - **Snap phase**: Surface snapping with implicit/explicit feature edge capture.
   - **Layer phase**: 5 prism layers inflated from wall faces with Spalding wall function sizing.
4. `checkMesh` — Topology and non-orthogonality quality validation.
5. `renumberMesh` — Bandwidth reduction for maximum linear solver throughput.

### Solver & Numerical Schemes
- **Solver**: `simpleFoam` (Steady-state incompressible RANS).
- **Initialization**: `potentialFoam` computes an initial divergence-free velocity field before `simpleFoam` starts.
- **Algorithm**: **SIMPLEC** (`consistent true`), enabling robust velocity relaxation ($U = 0.6, p = 0.5$).
- **Turbulence Model**: $k$-$\omega$ SST (Menter's Shear Stress Transport) with continuous `nutUSpaldingWallFunction`.
- **Convection Schemes**:
  - Velocity: `bounded Gauss limitedLinear 1` (2nd-order TVD with Sweby limiter).
  - Turbulence ($k, \omega$): `bounded Gauss upwind` (1st-order bounded, preventing negative $k$).
- **Linear Solvers**:
  - Pressure: `GAMG` (Geometric-Algebraic Multigrid) with `DICGaussSeidel`.
  - Velocity & Turbulence: `PBiCGStab` with `DILU` preconditioner.

---

## Project Structure

```
OpenFOAM-CaseGenerator/
├── setup_case.py              # CLI entry point for case generation
├── read_forces.py             # CLI entry point for force analysis
├── configs/
│   ├── config.json            # Main user configuration
│   └── example.json           # Minimal template
├── stl/                       # Place geometry STL files here (gitignored)
├── cases/                     # Generated OpenFOAM cases appear here (gitignored)
└── src/cfd_gen/
    ├── cli.py                 # Core CLI handling and orchestration
    ├── config.py              # Configuration loading, validation, and defaults
    ├── geometry.py            # Domain sizing, presets, and wake derivation
    ├── stl_utils.py           # STL ASCII reader/writer and bounding box math
    ├── writers/               # OpenFOAM dictionary generators
    │   ├── constants.py       # transportProperties, turbulenceProperties
    │   ├── fields.py          # Boundary conditions in 0/
    │   ├── mesh.py            # blockMeshDict, snappyHexMeshDict, surfaceFeatureExtractDict
    │   ├── scripts.py         # Allrun, Allclean, and SLURM submission scripts
    │   └── solver.py          # controlDict, fvSchemes, fvSolution, decomposeParDict
    └── postproc/              # Force parsing, plotting, and convergence monitoring
```

---

## Notes & Best Practices

- **Symmetry (Half-Car & Force Scaling)**:
  - `snappyHexMesh` automatically trims away any CAD geometry crossing beyond the symmetry boundary.
  - `read_forces.py` and `read_forces.py --compare` automatically detect symmetry cases and report both the **simulated half-model forces** and the **full-car projected forces ($\times 2$)** side-by-side, eliminating manual conversion.
- **ASCII STL Format**:
  - OpenFOAM `surfaceFeatureExtract` and `snappyHexMesh` require ASCII STL format. If your CAD exports binary STL, save or export as ASCII (e.g. in SolidWorks: *Save As $\rightarrow$ STL $\rightarrow$ Options $\rightarrow$ ASCII*).
- **Cluster Scratch Directory (`$TMPDIR`)**:
  - The generated `run.sh` runs inside node local scratch (`$TMPDIR`) on HPC clusters, syncing forces and logs back to the case folder every 15 seconds. This eliminates network filesystem (NFS/Lustre) bottlenecks. Set `"use_tmpdir": false` in `config.json` if running directly in-place.
  - Solver failures return a nonzero exit status after recovery. If reconstruction or copying results fails, the script preserves recovery data and reports its location; scratch runs retain `.running_location` for recovery.

Regenerating an existing case updates its input files and `0.orig`, while retaining previous results. Run `./Allclean` before a fresh simulation, or use a new `case_name` to retain the previous run separately. `--init` preserves an existing `configs/example.json`.

Regression checks use only Python's standard library:
```bash
python -m unittest discover -s tests -v
```
On Linux, this also executes the generated scripts with fake solver commands in temporary directories, testing failure recovery without running CFD. Those shell checks are skipped on Windows.
