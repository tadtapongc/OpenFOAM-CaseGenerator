# cfd-gen — OpenFOAM Case Generator for External Aerodynamics

A geometry-agnostic OpenFOAM case generator for external aerodynamics simulations. Give it an STL file and a minimal JSON config — it produces a complete, ready-to-run OpenFOAM case with meshing, solving, and post-processing.

Built for FSAE/Formula Student front wing development, but works with any external aero geometry.

---

## Features

- **Zero manual tuning** — mesh sizing, domain padding, turbulence values, and refinement regions are all derived from the STL bounding box
- **Three fidelity presets** — `fast` (5–10 min), `standard` (30–60 min), `fine` (2–4 hours)
- **Minimal config** — only geometry file, flow speed, and domain box required
- **Full pipeline** — from STL to force coefficients in one command
- **Post-processing CLI** — convergence plots, live monitoring, multi-case comparison
- **HPC ready** — generates SLURM scripts alongside local parallel scripts

---

## Quick Start

### Prerequisites

- [OpenFOAM v2512](https://www.openfoam.com/download) (ESI/OpenCFD distribution)
- Python ≥ 3.9

### Installation

```bash
git clone https://github.com/<your-username>/cfd-gen.git
cd cfd-gen
pip install -e .
```

Or use without installing:

```bash
python3 setup_case.py <config.json>
```

### Usage

```bash
# 1. Initialize project structure
cfd-setup --init

# 2. Place your STL geometry in STL/
cp my_wing.STL STL/

# 3. Edit the config
vim configs/example.json

# 4. Generate the OpenFOAM case
cfd-setup configs/my_config.json

# 5. Run the simulation
cd CASES/my_case
./Allrun.parallel          # Local parallel (default: 10 cores)
# OR
sbatch run.sh              # SLURM cluster submission

# 6. Check results
cfd-forces                 # Force summary
cfd-forces --plot          # Convergence plot
cfd-forces --live          # Real-time monitoring during solve
```

### Dry Run (Preview Without Generating)

```bash
cfd-setup configs/my_config.json -n
```

---

## Configuration

Only 4 fields are required — everything else uses universal defaults optimized for external aerodynamics.

### Minimal Config

```json
{
    "case_name": "my_wing",
    "stl_files": ["my_geometry.STL"],
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

### Optional Overrides

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
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
| Typical runtime (10 cores) | 5–10 min | 30–60 min | 2–4 hours |
| Use case | Iterative design | Balanced accuracy | Final report |

---

## Project Structure

```
cfd-gen/
├── setup_case.py          # Run without installing
├── read_forces.py         # Run without installing
├── pyproject.toml         # Package definition
├── configs/
│   └── example.json       # Config template
├── STL/                   # Place your geometry here (gitignored)
├── CASES/                 # Generated cases go here (gitignored)
└── src/cfd_gen/
    ├── cli.py             # CLI entry points
    ├── config.py          # Config loading, defaults, validation
    ├── geometry.py        # Domain sizing, mesh parameter derivation
    ├── stl_utils.py       # ASCII STL reader/writer
    ├── writers/
    │   ├── base.py        # OpenFOAM header templates
    │   ├── constants.py   # transportProperties, turbulenceProperties
    │   ├── fields.py      # Boundary condition files (0/)
    │   ├── mesh.py        # blockMeshDict, snappyHexMeshDict
    │   ├── scripts.py     # Allrun, Allclean, SLURM scripts
    │   └── solver.py      # controlDict, fvSchemes, fvSolution
    └── postproc/
        ├── forces.py      # Force reading, convergence check
        ├── compare.py     # Multi-case comparison
        ├── plotting.py    # Matplotlib plots
        └── residuals.py   # Residual monitoring
```

### Generated Case Layout

```
CASES/<case_name>/
├── 0/                     # Boundary conditions (U, p, k, omega, nut, Phi)
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
├── Allrun                 # Serial execution
├── Allrun.parallel        # Parallel execution (recommended)
├── Allclean               # Reset case
├── run.sh                 # SLURM submission script
└── case_config.json       # Full resolved config (for reproducibility)
```

---

## Simulation Setup

### Solver & Turbulence

| Property | Value |
|----------|-------|
| Solver | `simpleFoam` (steady-state, incompressible RANS) |
| Algorithm | SIMPLEC (consistent SIMPLE) |
| Turbulence | k-ω SST |
| Wall treatment | Spalding wall function (all y+ compatible) |
| Initialization | potentialFoam → simpleFoam |

### Mesh Pipeline

1. `surfaceFeatureExtract` — Sharp edge extraction (includedAngle = 150°)
2. `blockMesh` — Uniform background hex mesh
3. `snappyHexMesh` — Castellated mesh + snap + boundary layers
4. `checkMesh` — Quality validation
5. `renumberMesh` — Cell ordering optimization

Auto-computed refinement regions:
- **nearBody** — Tight box around geometry
- **wakeBox** — Extended downstream region

### Boundary Conditions

| Patch | U | p | Turbulence |
|-------|---|---|------------|
| **inlet** | fixedValue | zeroGradient | fixedValue |
| **outlet** | zeroGradient | fixedValue 0 | zeroGradient |
| **geometry** | noSlip | zeroGradient | wall functions |
| **ground** | moving wall | zeroGradient | wall functions |
| **farField** | slip | zeroGradient | zeroGradient |
| **symmetry** | symmetry | symmetry | symmetry |

The ground patch uses a moving wall at freestream velocity to simulate road-relative motion — critical for ground-effect aerodynamics.

### Numerical Schemes

- **Velocity divergence**: bounded Gauss limitedLinear 1 (second-order, bounded)
- **Turbulence divergence**: bounded Gauss upwind (first-order, stable)
- **Gradient**: cellLimited Gauss linear 1
- **Laplacian**: Gauss linear limited corrected 0.5

### Relaxation

| Field | Factor |
|-------|--------|
| p | 0.5 |
| U | 0.6 |
| k | 0.5 |
| ω | 0.5 |

---

## Post-Processing

### CLI Commands

| Command | Description |
|---------|-------------|
| `cfd-forces` | Print force summary (drag, downforce, L/D) |
| `cfd-forces --plot` | Convergence history plot |
| `cfd-forces --plot --save` | Save plot as PNG |
| `cfd-forces --live` | Real-time force monitor (updates every 3s) |
| `cfd-forces --compare` | Compare all cases in CASES/ directory |
| `cfd-forces --check` | Exit code 0 if converged, 1 if not |

### Example Output

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

### Convergence Criterion

Forces are considered converged when the standard deviation / mean < 0.5% over the last 100 iterations.

---

## Execution Options

| Method | Command | Use Case |
|--------|---------|----------|
| Local parallel | `./Allrun.parallel` | Development (10 cores) |
| SLURM | `sbatch run.sh` | HPC cluster |
| Serial | `./Allrun` | Debugging / small cases |
| Clean & re-run | `./Allclean && ./Allrun.parallel` | Reset and restart |

---

## Design Decisions

1. **Geometry-agnostic** — No hardcoded dimensions. Mesh parameters scale from STL bounding box.
2. **Minimal user input** — Only case_name, stl_files, flow conditions, and domain_box required.
3. **Universal defaults** — Wall functions, schemes, and relaxation that work for any external aero geometry without divergence.
4. **Reproducibility** — Each case saves its full resolved config as `case_config.json`.
5. **Spalding wall function** — Works across the entire y+ range, no strict mesh requirements at the wall.

---

## Dependencies

### Required

- [OpenFOAM v2512](https://www.openfoam.com/download) (ESI/OpenCFD distribution)
- Python ≥ 3.9 (standard library only for case generation)

### Optional

- [matplotlib](https://matplotlib.org/) ≥ 3.5 — for convergence plots (`pip install -e ".[plot]"`)
- SLURM — for HPC job submission

---

## Notes

- **Half-model**: Uses a symmetry plane. Multiply reported forces by 2 for full-vehicle values.
- **STL format**: Only ASCII STL is supported. Convert binary STL in your CAD tool (e.g., SolidWorks: Save As → STL → ASCII).
- **STL and CASES directories** are gitignored. Place your geometry in `STL/` and generated cases appear in `CASES/`.
- **Convergence safety**: The solver uses `writeAtEnd true` to always save the final state, even if interrupted.

---

## License

This project is provided as-is for educational and research purposes.
