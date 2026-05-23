# CFD_Remake — FSAE Front Wing Aerodynamics

Automated OpenFOAM v2512 CFD pipeline for Formula SAE front wing design iteration. This project provides a geometry-agnostic case generator (`cfd-gen`) that takes an STL file and a minimal JSON config, then produces a complete, ready-to-run OpenFOAM case with meshing, solving, and post-processing.

---

## Table of Contents

- [Project Overview](#project-overview)
- [Directory Structure](#directory-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Fidelity Levels](#fidelity-levels)
- [Simulation Details](#simulation-details)
  - [Solver & Physics](#solver--physics)
  - [Domain & Geometry](#domain--geometry)
  - [Mesh Strategy](#mesh-strategy)
  - [Boundary Conditions](#boundary-conditions)
  - [Numerical Schemes](#numerical-schemes)
  - [Linear Solvers & Relaxation](#linear-solvers--relaxation)
- [Execution](#execution)
- [Post-Processing](#post-processing)
- [Case Variants](#case-variants)
- [Python Package (cfd-gen)](#python-package-cfd-gen)
- [Dependencies](#dependencies)

---

## Project Overview

This project simulates the external aerodynamics of an FSAE front wing using steady-state RANS (Reynolds-Averaged Navier-Stokes) with the k-ω SST turbulence model. The workflow is fully automated:

1. **Input**: STL geometry file + minimal JSON configuration
2. **Generation**: Python tool derives all mesh parameters, boundary conditions, and solver settings
3. **Meshing**: blockMesh → snappyHexMesh (parallel, with boundary layers)
4. **Solving**: potentialFoam (initialization) → simpleFoam (SIMPLEC)
5. **Output**: Force/moment data, convergence monitoring, multi-case comparison

The design philosophy is **zero manual tuning** — mesh sizing, domain padding, turbulence values, and refinement regions are all computed from the STL bounding box and flow conditions.

---

## Directory Structure

```
CFD_Remake/
├── setup_case.py          # CLI entry: generate case (no install needed)
├── read_forces.py         # CLI entry: post-process forces (no install needed)
├── pyproject.toml         # Python package definition (cfd-gen)
├── configs/
│   └── example.json       # Minimal user config template
├── STL/                   # STL geometry files (symlink or directory)
├── CASES/                 # Generated OpenFOAM cases
│   ├── FW/                # Case variant 1
│   ├── FWV2/              # Case variant 2
│   ├── FWV3/              # Case variant 3
│   └── FWV4/              # Case variant 4
└── src/cfd_gen/           # Python package
    ├── __init__.py
    ├── __main__.py
    ├── cli.py             # CLI entry points (cfd-setup, cfd-forces)
    ├── config.py          # Config loading, defaults, validation
    ├── geometry.py        # Axis math, domain sizing, mesh derivation
    ├── stl_utils.py       # ASCII STL reader/writer, bounding box
    ├── writers/           # OpenFOAM dictionary generators
    │   ├── base.py        # Header template utilities
    │   ├── constants.py   # transportProperties, turbulenceProperties
    │   ├── fields.py      # 0/ directory (U, p, k, omega, nut, Phi)
    │   ├── mesh.py        # blockMeshDict, snappyHexMeshDict, surfaceFeatureExtractDict
    │   ├── scripts.py     # Allrun, Allrun.parallel, Allclean, run.sh (SLURM)
    │   └── solver.py      # controlDict, fvSchemes, fvSolution, decomposeParDict
    └── postproc/          # Post-processing tools
        ├── forces.py      # Force reading, convergence checking
        ├── compare.py     # Multi-case comparison table
        ├── plotting.py    # Matplotlib convergence plots
        └── residuals.py   # Residual monitoring
```

Each generated case has the standard OpenFOAM layout:

```
CASES/<case_name>/
├── 0/                     # Initial/boundary conditions (U, p, k, omega, nut, Phi)
├── 0.orig/                # Backup of initial conditions
├── constant/
│   ├── transportProperties
│   ├── turbulenceProperties
│   └── triSurface/        # STL geometry (copied & renamed)
├── system/
│   ├── blockMeshDict
│   ├── snappyHexMeshDict
│   ├── surfaceFeatureExtractDict
│   ├── controlDict
│   ├── fvSchemes
│   ├── fvSolution
│   └── decomposeParDict
├── Allrun                 # Serial execution script
├── Allrun.parallel        # Parallel execution script (recommended)
├── Allclean               # Clean case script
├── run.sh                 # SLURM HPC submission script
└── case_config.json       # Full resolved config snapshot
```

---

## Quick Start

### Without Installing

```bash
# 1. Place your STL in the STL/ directory
cp my_wing.STL STL/

# 2. Create a config (or copy the example)
cp configs/example.json configs/my_wing.json
# Edit: set case_name, stl_files, flow velocity, domain_box

# 3. Generate the case
python3 setup_case.py configs/my_wing.json

# 4. Run the simulation
cd CASES/my_wing
./Allrun.parallel        # Local (10 cores)
# OR
sbatch run.sh            # SLURM cluster

# 5. Post-process
cd CASES/my_wing
python3 ../../read_forces.py --plot
```

### With pip Install

```bash
pip install -e .

# Generate
cfd-setup configs/my_wing.json

# Post-process
cd CASES/my_wing
cfd-forces --plot
cfd-forces --live          # Real-time monitoring
cfd-forces --compare       # Compare all cases
cfd-forces --check         # Exit code 0 if converged
```

### Initialize a New Project

```bash
cfd-setup --init
# Creates: configs/example.json, STL/, CASES/
```

### Dry Run (Preview Without Generating)

```bash
python3 setup_case.py configs/my_wing.json -n
```

---

## Configuration

The user config is intentionally minimal. Only geometry and flow conditions are required — everything else uses universal defaults optimized for external aerodynamics.

### Minimal Config (`configs/example.json`)

```json
{
    "case_name": "FW",
    "stl_files": ["FW01V3.STL"],
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

    "domain_box": {
        "min": [0.0, 0.0, -7.5],
        "max": [2.5, 2.5, 2.0]
    },

    "domain_faces": {
        "-x": "symmetry",
        "+x": "farField",
        "-y": "ground",
        "+y": "farField",
        "+z": "inlet",
        "-z": "outlet"
    }
}
```

### Full Config Options

All fields below have sensible defaults and are optional:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `flow` | `velocity` | 16.67 | Freestream velocity (m/s) |
| `flow` | `direction` | `-z` | Flow direction axis |
| `flow` | `ground` | `true` | Moving ground boundary condition |
| `fluid` | `nu` | 1.516e-5 | Kinematic viscosity (m²/s) — air at 20°C |
| `fluid` | `rho` | 1.225 | Density (kg/m³) |
| `turbulence` | `model` | `kOmegaSST` | Turbulence model |
| `turbulence` | `intensity` | 0.005 | Turbulence intensity (0.5%) |
| `turbulence` | `nut_ratio` | 10 | νt/ν ratio |
| `parallel` | `n_procs` | 10 | Number of MPI processes |
| `parallel` | `method` | `scotch` | Decomposition method |
| `solver` | `end_time` | auto | Max iterations (from fidelity) |
| `solver` | `write_interval` | auto | Write frequency (from fidelity) |
| `solver` | `purge_write` | 2 | Keep only N latest time directories |
| `force_refs` | `lRef` | 1.0 | Reference length for coefficients |
| `force_refs` | `Aref` | 1.0 | Reference area for coefficients |
| `slurm` | `time` | auto | Wall time (from fidelity) |
| `slurm` | `openfoam_module` | `openfoam/v2512` | Module to load |

---

## Fidelity Levels

Three presets control mesh density, solver iterations, and layer resolution:

| Parameter | Fast | Standard | Fine |
|-----------|------|----------|------|
| Base cell size | 0.15 m | 0.10 m | 0.06 m |
| Surface refinement | levels 3–4 | levels 4–5 | levels 5–6 |
| Edge refinement | level 5 | level 6 | level 7 |
| Min surface cell | ~9.4 mm | ~3.1 mm | ~0.9 mm |
| Boundary layers | 3 | 5 | 8 |
| Expansion ratio | 1.3 | 1.2 | 1.15 |
| Max iterations | 800 | 1500 | 3000 |
| Max global cells | 8M | 20M | 40M |
| Typical runtime | 5–10 min | 30–60 min | 2–4 hours |
| SLURM wall time | 4 hours | 8 hours | 12 hours |
| Use case | Iterative design | Balanced accuracy | Final report |

Set via `"fidelity": "fast"` / `"standard"` / `"fine"` in the config.

---

## Simulation Details

### Solver & Physics

| Property | Value |
|----------|-------|
| Application | `simpleFoam` (steady-state, incompressible) |
| Algorithm | SIMPLEC (consistent SIMPLE) |
| Turbulence model | k-ω SST (`kOmegaSST`) |
| Fluid | Air at sea level, 20°C |
| Kinematic viscosity (ν) | 1.516 × 10⁻⁵ m²/s |
| Density (ρ) | 1.225 kg/m³ |
| Freestream velocity | 16.67 m/s (~60 km/h) |
| Turbulence intensity | 0.5% |
| νt/ν ratio | 10 |
| Derived k | 0.0104 m²/s² |
| Derived ω | 68.74 s⁻¹ |
| Derived νt | 1.516 × 10⁻⁴ m²/s |
| Initialization | potentialFoam → simpleFoam |

### Domain & Geometry

- **Half-model** with symmetry plane at x = 0 (multiply forces by 2 for full car)
- **Flow direction**: -z (inlet at +z face, outlet at -z face)
- **Downforce axis**: -y
- **Drag axis**: -z
- **Ground plane**: y = 0 (moving wall at freestream velocity)
- **Domain box** (standard fidelity): [0, 0, -7.5] to [2.5, 2.5, 2.0] meters

Domain padding is generous to avoid blockage effects:
- Upstream: 3–5× geometry length
- Downstream: 6–10× geometry length
- Lateral/top: 3–5× geometry height

### Mesh Strategy

The meshing pipeline:

1. **surfaceFeatureExtract** — Extract sharp edges (includedAngle = 150°)
2. **blockMesh** — Background hex mesh (uniform, base cell size from fidelity)
3. **snappyHexMesh** — Surface-conforming mesh with:
   - Castellated mesh (cell splitting near geometry)
   - Snap (project cells onto STL surface)
   - Add layers (boundary layer prism cells)
4. **checkMesh** — Validate mesh quality
5. **renumberMesh** — Optimize cell ordering for solver performance

Refinement regions (auto-computed from STL bounds):
- **nearBody**: Tight box around geometry (surface_level - 2)
- **wakeBox**: Extended downstream region (surface_level - 3)

Layer addition:
- Applied to wing surface and ground patch
- Spalding wall function bridges the entire y+ range (no strict y+ requirement)

### Boundary Conditions

| Patch | U | p | k | ω | νt |
|-------|---|---|---|---|-----|
| **inlet** | fixedValue (0 0 -16.67) | zeroGradient | fixedValue | fixedValue | calculated |
| **outlet** | zeroGradient | fixedValue 0 | zeroGradient | zeroGradient | calculated |
| **wing** | noSlip | zeroGradient | kqRWallFunction | omegaWallFunction | nutUSpaldingWallFunction |
| **ground** | fixedValue (0 0 -16.67) | zeroGradient | kqRWallFunction | omegaWallFunction | nutUSpaldingWallFunction |
| **farField** | slip | zeroGradient | zeroGradient | zeroGradient | calculated |
| **symmetry** | symmetry | symmetry | symmetry | symmetry | symmetry |

The ground uses a moving wall (same velocity as freestream) to simulate road-relative motion — critical for ground-effect aerodynamics.

### Numerical Schemes

| Category | Scheme |
|----------|--------|
| Time | steadyState |
| Gradient (U, k, ω) | cellLimited Gauss linear 1 |
| Divergence (U) | bounded Gauss limitedLinear 1 |
| Divergence (k, ω) | bounded Gauss upwind |
| Laplacian | Gauss linear limited corrected 0.5 |
| Interpolation | linear |
| snGrad | limited corrected 0.5 |
| Wall distance | meshWave |

The schemes are second-order accurate for velocity (limitedLinear) with first-order upwind for turbulence quantities — a stable combination that avoids oscillation while maintaining accuracy where it matters.

### Linear Solvers & Relaxation

**Pressure (p)**:
- Solver: GAMG (Geometric Algebraic Multi-Grid)
- Smoother: DICGaussSeidel
- Tolerance: 1 × 10⁻⁷, relTol: 0.001

**Velocity & Turbulence (U, k, ω)**:
- Solver: PBiCGStab (Preconditioned Bi-Conjugate Gradient Stabilized)
- Preconditioner: DILU
- Tolerance: 1 × 10⁻⁸, relTol: 0.01

**Under-relaxation factors**:
- p: 0.5
- U: 0.6
- k: 0.5
- ω: 0.5

**Bounded fields** (prevent negative values):
- k: min 1 × 10⁻⁶
- ω: min 1 × 10⁻⁴

---

## Execution

### Local Parallel (Recommended)

```bash
cd CASES/<case_name>
./Allrun.parallel
```

Pipeline:
1. `surfaceFeatureExtract` — Edge extraction
2. `blockMesh` — Background mesh
3. `decomposePar` — Split for parallel meshing
4. `snappyHexMesh -parallel` — Surface mesh (10 cores)
5. `reconstructParMesh` — Merge mesh
6. `checkMesh` — Quality validation
7. `renumberMesh` — Bandwidth optimization
8. `decomposePar` — Split for solving
9. `potentialFoam -parallel` — Velocity initialization
10. `simpleFoam -parallel` — Main solver (1500 iterations)
11. `reconstructPar` — Merge results

### SLURM HPC Submission

```bash
cd CASES/<case_name>
sbatch run.sh
```

The SLURM script requests 1 node, 10 tasks, and auto-loads the OpenFOAM module.

### Serial (Small Cases / Debugging)

```bash
cd CASES/<case_name>
./Allrun
```

### Clean & Re-run

```bash
cd CASES/<case_name>
./Allclean
./Allrun.parallel
```

---

## Post-Processing

### Force Summary

```bash
cd CASES/<case_name>
python3 ../../read_forces.py
```

Output:
```
=======================================================
  FORCE RESULTS (1500 iterations)
=======================================================
  Drag (-z):        12.345 N
  Downforce (-y):   45.678 N
  L/D:               3.700
-------------------------------------------------------
  Averaged (last 100):
    Drag:        12.340 N  (±0.123%)
    Downforce:   45.670 N  (±0.089%)
    L/D:          3.700
  Status: ✓ CONVERGED
=======================================================
  Note: If half-model (symmetry), multiply by 2.
```

### Convergence Plot

```bash
cfd-forces --plot          # Display plot
cfd-forces --plot --save   # Save as PNG
```

### Live Monitoring (During Simulation)

```bash
cfd-forces --live          # Updates every 3 seconds
cfd-forces --live -i 5     # Update interval: 5 seconds
```

### Multi-Case Comparison

```bash
cd <project_root>
cfd-forces --compare
```

Output:
```
===========================================================================
  Case              Drag [N]   Downforce [N]    L/D  Iters Status
  ---------------- ---------- -------------- ------ ------ ------------
  FW                   12.34          45.67   3.70   1500 ✓ converged
  FWV2                 11.89          47.23   3.97   1500 ✓ converged
  FWV3                 12.01          46.50   3.87   1500 ✓ converged
  FWV4                 10.56          42.10   3.99   1500 ✓ converged
===========================================================================
```

### Convergence Check (CI/Scripting)

```bash
cfd-forces --check
# Exit code 0 = converged, 1 = not converged
```

Convergence criterion: force variation < 0.5% (standard deviation / mean) over the last 100 iterations.

---

## Case Variants

| Case | STL | Description | Fidelity |
|------|-----|-------------|----------|
| **FW** | FW01V3.STL (6 MB) | Baseline front wing V1 | standard |
| **FWV2** | FW01V3.STL (6 MB) | Variant 2 (completed, 1500 iters) | standard |
| **FWV3** | FW01V3.STL (6 MB) | Variant 3 (completed, 1500 iters) | standard |
| **FWV4** | FrontWing.STL (439 KB) | Simplified/alternate geometry | standard |

All cases use the same flow conditions (16.67 m/s, -z direction) and turbulence model (k-ω SST).

---

## Python Package (cfd-gen)

### Architecture

The package follows a clean separation of concerns:

- **`config.py`** — Loads user JSON, deep-merges with universal defaults, validates
- **`geometry.py`** — Pure math: axis parsing, domain sizing, mesh parameter derivation
- **`stl_utils.py`** — STL I/O: read/write ASCII STL, bounding box, solid name rewriting
- **`writers/`** — Template-based OpenFOAM file generators (one module per category)
- **`postproc/`** — Force data parsing, convergence analysis, plotting

### Key Design Decisions

1. **Geometry-agnostic**: No hardcoded dimensions. Everything scales from STL bounds.
2. **Minimal user input**: Only case_name, stl_files, flow, and domain_box are required.
3. **Fidelity presets**: Three levels (fast/standard/fine) control all mesh/solver parameters.
4. **Universal defaults**: Wall functions, schemes, and relaxation factors that work for any external aero geometry.
5. **Config snapshot**: Each case saves its full resolved config as `case_config.json` for reproducibility.

### CLI Commands

| Command | Description |
|---------|-------------|
| `cfd-setup <config.json>` | Generate OpenFOAM case |
| `cfd-setup --init` | Create starter project structure |
| `cfd-setup <config.json> -n` | Dry run (preview only) |
| `cfd-forces` | Print force summary |
| `cfd-forces --plot` | Convergence plot |
| `cfd-forces --live` | Real-time force monitor |
| `cfd-forces --compare` | Multi-case comparison table |
| `cfd-forces --check` | Convergence check (exit code) |

---

## Dependencies

### Required

- **OpenFOAM v2512** (ESI/OpenCFD distribution)
- **Python ≥ 3.9** (no external packages needed for case generation)

### Optional

- **matplotlib ≥ 3.5** — For convergence plots (`pip install -e ".[plot]"`)
- **SLURM** — For HPC job submission

### OpenFOAM Utilities Used

| Utility | Purpose |
|---------|---------|
| `surfaceFeatureExtract` | Extract edge features from STL |
| `blockMesh` | Generate background hex mesh |
| `decomposePar` | Domain decomposition for parallel |
| `snappyHexMesh` | Surface-conforming mesh generation |
| `reconstructParMesh` | Merge parallel mesh |
| `checkMesh` | Mesh quality validation |
| `renumberMesh` | Cell renumbering for performance |
| `potentialFoam` | Potential flow initialization |
| `simpleFoam` | Steady-state RANS solver |
| `reconstructPar` | Merge parallel results |

---

## Notes

- **Half-model**: All cases use a symmetry plane at x = 0. Multiply reported forces by 2 for full-car values.
- **Wall functions**: The Spalding wall function (`nutUSpaldingWallFunction`) is used, which works across the entire y+ range — no strict y+ = 1 requirement.
- **Convergence**: The solver uses `writeAtEnd true` to always save the final state, even if interrupted.
- **Reproducibility**: The `case_config.json` saved in each case directory contains the complete resolved configuration (all defaults + user overrides + computed parameters).
- **STL format**: Only ASCII STL is supported. Convert binary STL in your CAD tool before use.
