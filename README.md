# OpenFOAM Case Generator for External Aerodynamics

An automated, geometry-adaptive OpenFOAM case generator engineered for external vehicle aerodynamics, Formula Student / FSAE racecar development, and aerodynamic bodywork.

Given an ASCII STL geometry and a concise JSON configuration, the generator automatically derives wind tunnel domain bounds, feature edge extraction, two-stage wake refinement boxes, boundary layer inflation, robust SIMPLEC numerical schemes, boundary field conditions, SLURM cluster submission scripts, and real-time post-processing monitors.

Requires **zero package installation** and runs entirely using standard Python and OpenFOAM commands.

---

## Table of Contents

1. [Key Features](#key-features)
2. [Quick Start & Requirements](#quick-start--requirements)
3. [Case Anatomy & Directory Structure](#case-anatomy--directory-structure)
4. [Standard Command Workflow](#standard-command-workflow)
   - [Step 1: Place STL Geometry](#step-1-place-stl-geometry)
   - [Step 2: Configure Case (`configs/config.json`)](#step-2-configure-case-configsconfigjson)
   - [Step 3: Preview Case (Dry Run)](#step-3-preview-case-dry-run)
   - [Step 4: Generate OpenFOAM Case](#step-4-generate-openfoam-case)
   - [Step 5: Run Simulation (Standard OpenFOAM Commands)](#step-5-run-simulation-standard-openfoam-commands)
   - [Step 6: Post-Process Aerodynamic Forces](#step-6-post-process-aerodynamic-forces)
5. [Configuration Guide (`config.json`)](#configuration-guide-configjson)
   - [Essential Settings](#essential-settings)
   - [Ground Plane & Ride Height Styles](#ground-plane--ride-height-styles)
   - [Symmetry Plane & Half-Car Simulation](#symmetry-plane--half-car-simulation)
   - [Aircraft & Free-Air Simulation](#aircraft--free-air-simulation)
   - [Fluid & Atmospheric Properties](#fluid--atmospheric-properties)
   - [Turbulence Specification](#turbulence-specification)
   - [Parallel & SLURM Cluster Settings](#parallel--slurm-cluster-settings)
   - [Expert Overrides](#expert-overrides)
6. [Fidelity Presets & Mesh Sizing](#fidelity-presets--mesh-sizing)
7. [Geometry, Domain & Boundary Physics Deep Dive](#geometry-domain--boundary-physics-deep-dive)
   - [Automatic Domain Sizing Mathematics](#automatic-domain-sizing-mathematics)
   - [Coordinate Transformations & Orientation](#coordinate-transformations--orientation)
   - [Road & Moving Ground Boundary Condition](#road--moving-ground-boundary-condition)
   - [Symmetry Clipping & Force Projection](#symmetry-clipping--force-projection)
8. [Meshing Pipeline & `snappyHexMesh` Architecture](#meshing-pipeline--snappyhexmesh-architecture)
   - [Step 1: Feature Extraction (`surfaceFeatureExtract`)](#step-1-feature-extraction-surfacefeatureextract)
   - [Step 2: Background Hexahedral Grid (`blockMesh`)](#step-2-background-hexahedral-grid-blockmesh)
   - [Step 3: Conforming Distance-Based Refinement Shells](#step-3-conforming-distance-based-refinement-shells)
   - [Step 4: Two-Stage Wake Refinement Architecture](#step-4-two-stage-wake-refinement-architecture)
   - [Step 5: Surface Snapping Controls](#step-5-surface-snapping-controls)
   - [Step 6: Boundary Layer Inflation (`addLayersControls`)](#step-6-boundary-layer-inflation-addlayerscontrols)
   - [Step 7: Parallel Quality Verification (`checkMesh`)](#step-7-parallel-quality-verification-checkmesh)
   - [Step 8: Cuthill-McKee Bandwidth Reduction (`renumberMesh`)](#step-8-cuthill-mckee-bandwidth-reduction-renumbermesh)
9. [Numerical Physics, Schemes & Solver Coupling](#numerical-physics-schemes--solver-coupling)
   - [Pre-Initialization with `potentialFoam`](#pre-initialization-with-potentialfoam)
   - [SIMPLEC Pressure-Velocity Coupling](#simplec-pressure-velocity-coupling)
   - [Spatial Discretization Schemes (`fvSchemes`)](#spatial-discretization-schemes-fvschemes)
   - [Linear Solvers & Multigrid Acceleration (`fvSolution`)](#linear-solvers--multigrid-acceleration-fvsolution)
   - [Turbulence Closure & Wall Functions ($k$-$\omega$ SST)](#turbulence-closure--wall-functions-k-omega-sst)
10. [Post-Processing, Force Analysis & Live Monitoring](#post-processing-force-analysis--live-monitoring)
    - [Force Extraction & Decomposition](#force-extraction--decomposition)
    - [Multi-Part Force Accounting](#multi-part-force-accounting)
    - [Automated Convergence Monitor & Clean Auto-Stop](#automated-convergence-monitor--clean-auto-stop)
    - [Real-Time Animated Live Dashboard](#real-time-animated-live-dashboard)
    - [Multi-Case Tabular Comparison](#multi-case-tabular-comparison)
11. [HPC Cluster Execution & Fault Recovery](#hpc-cluster-execution--fault-recovery)
12. [Performance Optimization Architecture](#performance-optimization-architecture)
13. [FSAE & Aerodynamics Engineering Best Practices](#fsae--aerodynamics-engineering-best-practices)
14. [Troubleshooting & FAQ](#troubleshooting--faq)
15. [Automated Regression Tests](#automated-regression-tests)

---

## Key Features

- **Standard Commands Only**: No custom CLI binary installation needed. Run directly with standard `python setup_case.py`, standard OpenFOAM commands (`blockMesh`, `snappyHexMesh`, `simpleFoam`), and standard `python read_forces.py`.
- **Optimized for FSAE & Vehicle Aerodynamics**: Domain dimensions, refinement shells, boundary layers, and wake regions are tailored specifically for ground vehicles, targeting the optimal simulation sweet spot (~6–9 million cells on standard fidelity).
- **Two-Stage Wake Architecture**: Replaces massive uniform wake boxes with a high-resolution `nearWakeBox` (capturing rear wing vortices, undertray diffuser recovery, and tire separation) paired with an efficient `farWakeBox` (preserving wake transport to the outlet without cell bloat), saving 8–10 million redundant cells.
- **Conforming Distance Refinement Shells**: Uses proximity-based distance shells (e.g. 25 mm $\rightarrow$ Level 4, 80 mm $\rightarrow$ Level 3) that drape smoothly over complex bodywork curves instead of crude axis-aligned boxes.
- **Zero-Tweak Geometry Adaptation**: Automatic domain sizing (`"domain_box": "auto"`) fits the virtual wind tunnel around any CAD assembly, automatically determining upstream, downstream, top, and ground offsets.
- **Offset Centerline & Non-Zero Symmetry Planes**: Native support for CAD models exported with lateral offsets (e.g. `"symmetry_plane": -0.1185` or `0.0`), automatically clipping half-car models cleanly along the symmetry boundary.
- **Robust Incompressible Solver Setup**: Divergence-free `potentialFoam` initialization $\rightarrow$ `simpleFoam` (SIMPLEC) with cell-limited bounded TVD schemes and Spalding continuous wall functions ($k$-$\omega$ SST).
- **Auto-Stop Convergence Monitor**: A background monitor analyzes live aerodynamic forces, calculates variance over a rolling 200-iteration window, and cleanly triggers solver termination (`stopAt writeNow;`) once variation drops below 0.5%, preventing wasted compute hours.
- **HPC & SLURM Cluster Pipeline**: Production-grade cluster script with node-local fast scratch (`$TMPDIR` / `/dev/shm`) execution, background status sync, signal trapping (`SIGTERM`/`SIGINT`), emergency reconstruction, and processor backup.
- **$O(1)$-Memory Streaming STL Engine**: Streams large CAD assemblies (100–500+ MB STLs) line-by-line for bounding box extraction and verbatim coordinate copying, eliminating memory bloat and preserving 100% CAD precision.
- **Zero External Python Dependencies for Generation**: Uses only Python's built-in standard library for all case generation and force parsing (`matplotlib` is only optional if you want graphical plots).

---

## Quick Start & Requirements

### System Requirements

- **Operating System**: Linux (Ubuntu, RHEL, Rocky, Debian), macOS, or Windows (WSL2 / native Python).
- **OpenFOAM**: OpenFOAM v2006 through v2606 (ESI/OpenCFD) or OpenFOAM 9/10/11 (Foundation).
- **Python**: Python $\ge$ 3.9 (standard library only for case generation; `matplotlib` optional for GUI plots).

### Getting Started (No Installation Required)

Simply clone the repository and run:

```bash
git clone https://github.com/tadtapongc/OpenFOAM-CaseGenerator.git
cd OpenFOAM-CaseGenerator
```

You do not need to install anything. All commands use standard Python scripts:
- `python setup_case.py configs/config.json`: Generates the OpenFOAM case.
- `python setup_case.py configs/config.json --dry-run`: Previews domain and mesh sizing without generating files.
- `python setup_case.py --init`: Generates starter template directories (`configs/`, `stl/`, `cases/`).
- `python read_forces.py`: Analyzes forces, plots convergence, and compares cases.

*(Optional)* If you want real-time animated GUI plots:
```bash
pip install matplotlib
```

---

## Case Anatomy & Directory Structure

When a case is generated, it creates a fully self-contained OpenFOAM case directory structured as follows:

```text
cases/<case_name>/
├── 0/                                  # Boundary condition field definitions
│   ├── U                               # Velocity vector field (inlet, moving road, noSlip car)
│   ├── p                               # Kinematic pressure field (p/rho, [m²/s²])
│   ├── k                               # Turbulent kinetic energy [m²/s²]
│   ├── omega                           # Specific dissipation rate [1/s]
│   └── nut                             # Turbulent kinematic eddy viscosity [m²/s]
├── 0.orig/                             # Pristine initial field backup (restored by ./Allclean)
├── constant/
│   ├── transportProperties             # Kinematic viscosity (nu = 1.516e-5 m²/s)
│   ├── turbulenceProperties            # Turbulence model selection (kOmegaSST)
│   └── triSurface/                     # Geometry surface files
│       ├── <model>.stl                 # CAD geometry (exact ASCII STL)
│       └── <model>.eMesh               # Extracted sharp feature edges (140° threshold)
├── system/
│   ├── blockMeshDict                   # Background hex grid sizing & outer tunnel boundaries
│   ├── snappyHexMeshDict               # Conformal refinement, snapping, and prism layers
│   ├── surfaceFeatureExtractDict       # Edge feature extraction rules
│   ├── controlDict                     # Solver runtime, force function objects, residuals, y+
│   ├── fvSchemes                       # TVD divergence, gradient, and laplacian schemes
│   ├── fvSolution                      # SIMPLEC relaxation, GAMG multigrid & PBiCGStab solvers
│   └── decomposeParDict                # MPI domain decomposition (Scotch method)
├── Allrun.parallel                     # Local parallel execution bash script (MPI)
├── Allrun                              # Local serial execution bash script
├── Allclean                            # Case cleanup script (resets mesh and solver outputs)
├── run.sh                              # Production SLURM cluster submission batch script
├── convergence_monitor.py              # Background auto-stop monitor script (reads force.dat & updates controlDict)
└── case_config.json                    # Frozen snapshot of the configuration used to generate this case
```

### Runtime Outputs Generated During Simulation

```text
cases/<case_name>/
├── log.blockMesh                       # Background meshing log
├── log.surfaceFeatureExtract           # Edge extraction log
├── log.snappyHexMesh                   # Volume mesh generation log
├── log.checkMesh                       # Parallel mesh quality diagnostics log
├── log.renumberMesh                    # Cuthill-McKee matrix bandwidth reduction log
├── log.potentialFoam                   # Divergence-free initialization log
├── log.simpleFoam                      # Steady-state RANS solver log
├── log.reconstructPar                  # Parallel field reconstruction log
├── postProcessing/
│   ├── forces/0/force.dat              # Raw drag, downforce, and pitching moment per time step
│   ├── forceCoeffs/0/forceCoeffs.dat   # Force coefficients (Cd, Cl, Cs, Cm)
│   └── residuals/0/solverInfo.dat      # Solver convergence residuals for p, U, k, omega
└── VTK/                                # (Optional) Converted ParaView visualization files
```

---

## Standard Command Workflow

```text
[ CAD Export (.STL) ]
         │
         ▼
[ 1. Place STL in stl/ ] ──────► [ 2. Edit configs/config.json ]
                                                 │
                                                 ▼
[ 5. Solve: ./Allrun.parallel ] ◄────── [ 4. Generate: python setup_case.py ]
     or standard OpenFOAM cmds                  (Dry-run: --dry-run)
     or sbatch run.sh
         │
         ▼
[ 6. Post-Process: python read_forces.py ]
     (--plot, --live, --compare)
```

### Step 1: Place STL Geometry

1. Export your CAD model as an **ASCII STL** file in **meters** ($1.0 = 1\text{ meter}$).
2. Ensure the geometry is closed/watertight.
3. Place it in the `stl/` folder:
   ```bash
   cp my_car.STL stl/
   ```

### Step 2: Configure Case (`configs/config.json`)

Edit `configs/config.json` with standard JSON:

```json
{
    "case_name": "RP14_FSAE",            // Case output folder created under cases/<case_name>/
    "stl_files": ["RP14.STL"],           // ASCII STL geometry filename(s) in stl/ directory
    "fidelity": "standard",              // Quality preset: "fast" (~2-4M cells), "standard" (~6-9M, FSAE sweet spot), "fine" (~12-16M)

    "flow": {
        "velocity": 16.67,               // Freestream air velocity in m/s (16.67 m/s ≈ 60 km/h)
        "direction": "-z",               // Freestream flow direction vector (air travels from +z toward -z)
        "ground": true                   // true = moving road wall at freestream velocity; false = slip wall
    },

    "outputs": {
        "drag_axis": "-z",               // Axis along which aerodynamic drag is reported
        "downforce_axis": "-y"           // Axis along which downforce (-lift) is reported (-y = toward ground)
    },

    "domain_box": "auto",                // "auto" derives 4L upstream, 8L downstream, 4H top virtual wind tunnel
    "symmetry_plane": -0.1185,           // Lateral centerline coordinate if car is offset from origin (omit or 0.0 if centered)

    "domain_faces": {
        "-x": "symmetry",                // Inner car centerline: symmetry boundary condition
        "+x": "farField",                // Outer lateral side wall: slip wall boundary (no boundary layer)
        "-y": "ground",                  // Road floor: fixedValue uniform matching freestream speed (moving road)
        "+y": "farField",                // Wind tunnel ceiling: slip wall boundary
        "+z": "inlet",                   // Virtual wind tunnel air intake: uniform fixed velocity
        "-z": "outlet"                   // Downstream exhaust: uniform 0 gauge pressure (p = 0)
    },

    "parallel": {
        "n_procs": 32                    // Number of CPU cores for MPI decomposition, meshing, and solving
    }
}
```

### Step 3: Preview Case (Dry Run)

Check derived wind tunnel bounds, bounding box dimensions, and mesh parameters before writing any files:

```bash
python setup_case.py configs/config.json --dry-run
```

Output:
```text
  Config: configs/config.json
  ℹ  STL crosses symmetry plane: x_min (-0.118 m) — geometry will be cut at symmetry boundary
  ℹ  Ground plane: y = 0.000 m (ground clearance: 35.0 mm)

  Geometry bounds:
    min: (-0.118, 0.035, -1.450)
    max: (0.720, 1.180, 1.550)
  Domain box:
    min: (-0.118, 0.000, -25.450)
    max: (4.076, 5.760, 13.550)
  Mesh:
    Base cell:      0.1 m
    Surface level:  [4, 5]
    Edge level:     6
    Distance shells: 25mm→L4, 80mm→L3
    Region nearWakeBox: Level 3
    Region farWakeBox: Level 1

  DRY RUN — would generate: cases/RP14_FSAE
    Velocity:   16.67 m/s  U=(0 0 -16.67)
    k=0.01042  ω=68.733  νt=0.0001516
    Surfaces:   RP14
    Pipeline:   potentialFoam → simpleFoam (1500 iters, bounded Gauss limitedLinear 1)
```

### Step 4: Generate OpenFOAM Case

Generate the complete OpenFOAM case directory structure under `cases/<case_name>/`:

```bash
python setup_case.py configs/config.json
```

*(Re-running this command safely refreshes all case dictionaries and `0/` boundary conditions while preserving your previous run history.)*

### Step 5: Run Simulation (Standard OpenFOAM Commands)

Navigate into the generated case directory:

```bash
cd cases/RP14_FSAE
```

You can run the simulation using **Method A (Automated Script)**, **Method B (Direct Standard OpenFOAM Commands)**, or **Method C (SLURM Cluster)**:

#### Method A: Run via Automated Bash Script
```bash
./Allrun.parallel
```

#### Method B: Run Step-by-Step with Standard OpenFOAM Commands
If you prefer executing standard OpenFOAM commands manually in your terminal:

```bash
# 1. Extract sharp feature edges (140° threshold) into constant/triSurface/*.eMesh
surfaceFeatureExtract

# 2. Build the outer background hexahedral grid sized to the virtual wind tunnel
blockMesh

# 3. Decompose domain across 32 MPI cores using Scotch graph partitioning
decomposePar

# 4. Generate parallel volume mesh (distance shells, wake boxes, snapping, and boundary layers)
mpirun -np 32 snappyHexMesh -parallel -overwrite

# 5. Verify parallel mesh quality metrics (non-orthogonality < 70°, skewness < 4) across all MPI ranks
mpirun -np 32 checkMesh -allGeometry -allTopology -noFunctionObjects -parallel

# 6. Reconstruct the volume mesh from processor* directories back to constant/polyMesh
reconstructParMesh -constant
rm -rf processor*

# 7. Renumber cell labels using Cuthill-McKee algorithm to minimize sparse matrix bandwidth
renumberMesh -overwrite

# 8. Re-decompose fields with the finalized volume mesh ready for solving
decomposePar

# 9. Solve Laplace potential equation (∇²Φ = 0) to compute a divergence-free initial velocity
mpirun -np 32 potentialFoam -parallel -writephi -noFunctionObjects

# 10. Run steady-state incompressible RANS solver using SIMPLEC pressure-velocity coupling
mpirun -np 32 simpleFoam -parallel

# 11. Reconstruct parallel time-step solution fields into serial format for ParaView visualization
reconstructPar -latestTime
```

#### Method C: Submit to SLURM Cluster
```bash
sbatch run.sh
```

#### Reset / Clean Case
To wipe mesh and solver output files back to initial state:
```bash
./Allclean
```

### Step 6: Post-Process Aerodynamic Forces

Run the standard post-processing script from the project root:

```bash
# 1. Print formatted aerodynamic force summary table:
python read_forces.py

# 2. Open interactive real-time convergence dashboard:
python read_forces.py --live

# 3. Plot force convergence history to an image/figure:
python read_forces.py --plot

# 4. Compare aerodynamic forces across all cases in cases/:
python read_forces.py --compare
```

---

## Configuration Guide (`config.json`)

### Essential Settings

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `case_name` | `string` | *required* | Folder name created under `cases/<case_name>/` |
| `stl_files` | `list[str]` | *required* | List of STL files in `stl/` (e.g. `["car.STL"]` or `["wing.stl", "body.stl"]`) |
| `fidelity` | `string` | `"standard"` | Quality preset: `"fast"`, `"standard"`, or `"fine"` |
| `flow.velocity` | `float` | `16.67` | Freestream velocity in m/s (16.67 m/s $\approx$ 60 km/h) |
| `flow.direction` | `string` | `"-z"` | Freestream direction vector (`"-z"`, `"+z"`, `"-x"`, etc.) |
| `flow.ground` | `bool` | `true` | `true` sets moving road wall at freestream velocity; `false` sets slip wall |
| `outputs.drag_axis` | `string` | `"-z"` | Direction along which drag is calculated |
| `outputs.downforce_axis`| `string` | `"-y"` | Direction along which downforce (negative lift) is calculated |
| `domain_box` | `string / dict` | `"auto"` | `"auto"` derives bounds from STL; or supply `{"min": [...], "max": [...]}` |
| `domain_faces` | `dict[str, str]`| *auto* | Mapping of 6 box faces (`"-x"`, `"+x"`, etc.) to boundary types |
| `parallel.n_procs` | `int` | `32` | Number of CPU cores for MPI parallel meshing and solving |

### Ground Plane & Ride Height Styles

Adjust ground positioning relative to the CAD geometry:

- **Style 1 — Relative Ride Height (`ground_clearance`)**:
  Specifies the distance in meters below the lowest CAD vertex. Ideal for ride-height sensitivity sweeps:
  ```json
  "ground_clearance": 0.035   // Ground placed exactly 35 mm below lowest point of STL
  ```
- **Style 2 — Absolute Coordinate (`ground_plane`)**:
  Fixes the road coordinate at an exact CAD assembly elevation:
  ```json
  "ground_plane": 0.0         // Ground plane placed at y = 0.0
  ```
- **Style 3 — Auto-Snap (Default)**:
  If omitted, the ground plane automatically snaps to the lowest point of the geometry (`y = smin`).

### Symmetry Plane & Half-Car Simulation

Simulating a symmetric half-car cuts cell count and compute time in half:

```json
"symmetry_plane": 0.0,                   // Lateral coordinate of the vehicle centerline (e.g. 0.0 or -0.1185)
"domain_faces": {
    "-x": "symmetry",                    // Inner symmetry cut plane (mirrored in force analysis)
    "+x": "farField",                    // Outer side boundary: slip wall padded 4x vehicle width
    "-y": "ground",                      // Road surface: moving road boundary condition
    "+y": "farField",                    // Wind tunnel ceiling: slip wall padded 4x vehicle height
    "+z": "inlet",                       // Virtual wind tunnel air intake: uniform fixed velocity
    "-z": "outlet"                       // Downstream exhaust: static pressure outlet (p = 0)
}
```

- **Offset Centerlines**: If the CAD model has an origin offset (e.g. car centerline at $x = -0.1185$), specify `"symmetry_plane": -0.1185`. The generator clips the wind tunnel at this exact coordinate and offsets wake boxes accordingly.
- **Automatic Force Doubling**: `python read_forces.py` automatically detects half-car setups and reports both simulated half-model forces and projected full-car ($\times 2$) forces side-by-side.

### Aircraft & Free-Air Simulation

To simulate an aircraft, drone, or hydrofoil outside of ground effect:

```json
"flow": {
    "velocity": 45.0,                    // Flight airspeed in m/s (45.0 m/s ≈ 162 km/h)
    "direction": "-z",                   // Flight direction vector (air flows from +z to -z)
    "ground": false                      // false = disable moving ground (open atmosphere all around)
},
"outputs": {
    "drag_axis": "-z",                   // Streamwise direction for aerodynamic drag
    "downforce_axis": "+y"               // +y reports positive aerodynamic Lift (upward direction)
},
"domain_faces": {
    "-x": "symmetry",                    // Inner symmetry plane (or "farField" for full aircraft)
    "+x": "farField",                    // Outer wingtip boundary: slip wall padded 4x span
    "-y": "farField",                    // Atmosphere below aircraft: slip wall padded 4x height
    "+y": "farField",                    // Atmosphere above aircraft: slip wall padded 4x height
    "+z": "inlet",                       // Upstream air entry: fixed velocity inlet
    "-z": "outlet"                       // Downstream exhaust: static pressure outlet (p = 0)
}
```

### Fluid & Atmospheric Properties

```json
"fluid": {
    "rho": 1.225,                        // Air density in kg/m³ (Standard air at 20°C: 1.225; hot 35°C track: ~1.145)
    "nu": 1.516e-5                       // Kinematic viscosity in m²/s (Standard air at 20°C: 1.516e-5; 35°C: ~1.66e-5)
}
```

### Turbulence Specification

```json
"turbulence": {
    "model": "kOmegaSST",                // Menter's Shear Stress Transport (industry standard for external aero)
    "intensity": 0.005,                  // Freestream turbulence intensity: 0.5% (wind tunnel freestream)
    "nut_ratio": 10                      // Ratio of turbulent to laminar viscosity (nut / nu = 10)
}
```

Turbulent kinetic energy ($k$) and specific dissipation rate ($\omega$) are automatically initialized via:
$$k = \frac{3}{2} (U_\infty \cdot I)^2, \quad \omega = \frac{k}{(\nu_t / \nu) \cdot \nu}, \quad \nu_t = 10 \cdot \nu$$

### Parallel & SLURM Cluster Settings

```json
"parallel": {
    "n_procs": 32,                       // Total number of MPI ranks / CPU cores
    "method": "scotch"                   // Decomposition method: "scotch" (automatic graph partitioning)
},
"slurm": {
    "qos": "cu_hpc",                     // Quality of Service queue name on SLURM cluster
    "partition": "cpu",                  // Cluster hardware partition (e.g. cpu, compute, standard)
    "nodes": 1,                          // Node count (1 node minimizes MPI cross-switch latency)
    "time": "08:00:00",                  // Maximum walltime allocation (hh:mm:ss)
    "mem_per_cpu": "2G",                 // RAM requested per core (2GB * 32 cores = 64GB total)
    "openfoam_module": [                 // Cluster module environment packages to load
        "GCC/11.3.0",
        "OpenMPI/4.1.4-GCC-11.3.0"
    ],
    "openfoam_source": "$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc",  // OpenFOAM environment activation script
    "use_tmpdir": true,                  // true = run inside fast node RAM/NVMe scratch ($TMPDIR)
    "sync_interval": 15                  // Periodic sync interval in seconds for forces and logs
}
```

### Expert Overrides

Every default can be overridden by adding an `"overrides"` block or direct parameter mappings in `config.json`:

```json
"overrides": {
    "relaxation": {
        "fields": {
            "p": 0.7                     // SIMPLEC pressure under-relaxation factor (0.7 enables fast convergence)
        },
        "equations": {
            "U": 0.7,                    // Velocity momentum equation relaxation factor
            "k": 0.5,                    // Turbulent kinetic energy equation relaxation factor
            "omega": 0.5                 // Specific dissipation rate equation relaxation factor
        }
    },
    "mesh_params": {
        "base_cell_size": 0.08,          // Custom background hexahedral cell dimension in meters
        "surface_level": [4, 6],         // Min and max surface refinement levels on vehicle STL
        "edge_level": 7                  // Feature edge refinement level on wing trailing edges / flaps
    }
}
```

---

## Fidelity Presets & Mesh Sizing

Three carefully calibrated fidelity presets are provided:

| Metric / Parameter | Fast | Standard (FSAE Sweet Spot) | Fine (Validation) |
| :--- | :--- | :--- | :--- |
| **Base Cell Size ($h_0$)** | 0.15 m (150 mm) | 0.10 m (100 mm) | 0.08 m (80 mm) |
| **Surface Level** | Level [3, 4] (18.8 – 9.4 mm) | Level [4, 5] (6.25 – 3.12 mm) | Level [5, 6] (2.50 – 1.25 mm) |
| **Edge Level** | Level 5 (4.69 mm) | Level 6 (1.56 mm) | Level 7 (0.62 mm) |
| **Distance Refinement** | 40mm $\rightarrow$ L3, 120mm $\rightarrow$ L2 | 25mm $\rightarrow$ L4, 80mm $\rightarrow$ L3 | 20mm $\rightarrow$ L5, 60mm $\rightarrow$ L4, 150mm $\rightarrow$ L3 |
| **Near Wake Box** | Level 2 (37.5 mm) | Level 3 (12.5 mm) | Level 4 (5.0 mm) |
| **Far Wake Box** | Level 1 (75.0 mm) | Level 1 (50.0 mm) | Level 2 (20.0 mm) |
| **Boundary Layers** | 3 layers ($ER = 1.30$) | 5 layers ($ER = 1.20$) | 6 layers ($ER = 1.15$) |
| **First Layer Relative Size** | 0.40 | 0.30 | 0.20 |
| **Buffer Cells (`nCellsBetweenLevels`)** | 2 | 2 | 2 |
| **Feature Angle (`resolveFeatureAngle`)**| 35° | 35° | 30° |
| **Typical Cell Count** | **~2 – 4 Million** | **~6 – 9 Million** | **~12 – 16 Million** |
| **Solve Time (32 cores)** | ~10 – 15 min | ~35 – 45 min | ~2 – 4 hours |
| **Primary Application** | Rapid concept screening | Aero package iteration & design | Final validation & wind tunnel correlation |

---

## Geometry, Domain & Boundary Physics Deep Dive

### Automatic Domain Sizing Mathematics

To prevent artificial boundary blockage and pressure reflection while minimizing cell count, the generator sizes the virtual wind tunnel based on aerodynamic blockage criteria:

Let geometry extents along length, height, and lateral width be $L_x, L_y, L_z$. The domain bounding box $[D_{min}, D_{max}]$ is derived as follows:

- **Upstream Distance**: $4 \times L_{geometry}$ ahead of leading edge. Guarantees uniform stagnation flow without inlet pressure influence.
- **Downstream Distance**: $8 \times L_{geometry}$ behind trailing edge. Prevents outlet boundary condition backpressure on diffuser and wake recovery.
- **Top / Ceiling Distance**: $4 \times H_{geometry}$ above car roof. Ensures aerodynamic blockage ratio:
  $$\text{Blockage Ratio} = \frac{A_{\text{frontal}}}{A_{\text{wind tunnel}}} < 1.5\%$$
  eliminating the need for wind tunnel blockage corrections.
- **Lateral Far Wall**: $4 \times W_{geometry}$ from outer edge.

### Coordinate Transformations & Orientation

Arbitrary vehicle CAD export orientations are supported through an internal vector transformation matrix:

```text
Flow Direction (-z):
  - Streamwise (Length): Z-axis (Inlet at +z, Outlet at -z)
  - Vertical (Height):   Y-axis (Road at -y, Ceiling at +y)
  - Lateral (Width):     X-axis (Symmetry at -x, Far Wall at +x)
```

If your CAD was exported with flow along `-x` and up along `+z`, set `"direction": "-x"` and `"downforce_axis": "-z"`. The generator automatically swaps indexing, aspect ratios, wake bounding boxes, and velocity vectors.

### Road & Moving Ground Boundary Condition

In real-world racing, the track moves beneath the vehicle at vehicle speed, eliminating the ground boundary layer found in static wind tunnels:

- When `"ground": true`:
  - Patch type: `wall`.
  - Velocity ($U$): `fixedValue uniform (x y z)` matching the freestream velocity vector.
  - Turbulence ($k, \omega, \nu_t$): Continuous wall functions applied to moving road.
- When `"ground": false` (static slip road or high altitude aircraft):
  - Patch type: `patch` with `slip` velocity and `zeroGradient` pressure.

### Symmetry Clipping & Force Projection

When simulating a half-model:
1. CAD geometry crossing the symmetry plane is trimmed by `snappyHexMesh` at the boundary.
2. The `locationInMesh` seed point is projected away from the symmetry plane toward the outer far-wall ceiling corner to guarantee it sits strictly within the fluid volume.
3. Wake boxes (`nearWakeBox` and `farWakeBox`) are automatically clipped so their inner lateral face aligns exactly with the symmetry plane coordinate.
4. `python read_forces.py` queries `system/blockMeshDict` for symmetry boundaries. If detected, it computes both simulated half-forces and full-car projected forces:
   $$F_{\text{full car}} = 2 \times F_{\text{half car}}$$

---

## Meshing Pipeline & `snappyHexMesh` Architecture

The meshing workflow transforms an STL surface into an analysis-ready hexahedral-dominant volume mesh:

```text
[ blockMesh ] ──► [ surfaceFeatureExtract ] ──► [ snappyHexMesh (Parallel) ]
                                                        │
[ renumberMesh ] ◄── [ reconstructParMesh ] ◄── [ checkMesh (Parallel) ]
```

### Step 1: Feature Extraction (`surfaceFeatureExtract`)

Sharp aerodynamic edges (wing trailing edges, endplate perimeters, diffuser strakes, gurney flaps) are extracted into OpenFOAM `.eMesh` format using an included angle of `140°`:

$$\theta_{\text{included}} = 140^\circ$$

- **Why 140°?** Angles sharper than 140° (such as $90^\circ$ endplates or $15^\circ$ trailing edges) are preserved for explicit vertex snapping. Flatter cosmetic CAD facets (such as cylindrical roll hoops or curved sidepods) are ignored, avoiding false geometric ridges.

### Step 2: Background Hexahedral Grid (`blockMesh`)

`blockMesh` creates the outer bounding box with uniform hexahedral cells having an aspect ratio close to $1:1:1$:

$$n_x = \text{round}\left(\frac{\Delta X}{h_0}\right), \quad n_y = \text{round}\left(\frac{\Delta Y}{h_0}\right), \quad n_z = \text{round}\left(\frac{\Delta Z}{h_0}\right)$$

### Step 3: Conforming Distance-Based Refinement Shells

Rather than generating millions of cells inside an oversized rectangular box around the chassis, the generator uses **distance-based surface shells**:
- Within **25 mm** of geometry $\rightarrow$ **Level 4** refinement (6.25 mm cell size).
- Within **80 mm** of geometry $\rightarrow$ **Level 3** refinement (12.5 mm cell size).

These shells hug the curvature of wings, suspension arms, and sidepods, providing smooth resolution transitions while eliminating empty-air cell bloat.

### Step 4: Two-Stage Wake Refinement Architecture

Wake vortex shedding and flow separation require high resolution behind the car, but uniform wake boxes waste massive compute resources. The generator uses a **two-stage wake architecture**:

```text
                ┌──────────────────┐
                │   nearWakeBox    │──────┐
┌───────────┐   │ (High-Resolution)│      │     farWakeBox
│  Vehicle  │──►│  Rear Wing & Diff│      ├──────────────────────────────► [ Outlet ]
│    CAD    │   │  Level 3 (12.5mm)│      │  Wake Transport to Outlet
└───────────┘   └──────────────────┘      │  Level 1 (50.0mm)
 ◄── 1.0L ──►    ◄────── 1.2L ─────►      └──────────────────────────────►
                                           ◄──────────── 3.5L ───────────►
```

1. **`nearWakeBox` (Level 3, 12.5 mm)**:
   - Extends $1.2 \times L_{geometry}$ behind the car.
   - Encompasses rear wing tip vortices, diffuser pressure recovery, and tire wake separation.
2. **`farWakeBox` (Level 1, 50.0 mm)**:
   - Extends $3.5 \times L_{geometry}$ downstream toward the outlet.
   - Prevents artificial numerical dissipation of the wake while saving ~8 million cells compared to a single uniform wake box.

### Step 5: Surface Snapping Controls

`snapControls` morph cell vertices onto the CAD triangles:
- `explicitFeatureSnap true;` pulls cell vertices directly onto `.eMesh` sharp lines.
- `implicitFeatureSnap true;` snaps vertices to surface curvature.
- `nSolveIter 200;` and `tolerance 2.0;` guarantee high surface conformity on multi-element wings.

### Step 6: Boundary Layer Inflation (`addLayersControls`)

Boundary layers are inflated from vehicle surfaces to resolve viscous shear stresses:
- **5 prism layers** with an expansion ratio of $1.20$.
- **Spalding Wall Function Targeting**: Sized such that $y^+$ values fall naturally into the buffer and log-law region ($20 < y^+ < 100$), seamlessly captured by continuous wall functions without requiring millions of sub-viscous cells ($y^+ < 1$).
- `featureAngle 170;` prevents layer collapse over sharp wing edges.
- `maxFaceThicknessRatio 0.5;` prevents layer distortion on highly curved leading edges.

### Step 7: Parallel Quality Verification (`checkMesh`)

Immediately following `snappyHexMesh`, `checkMesh` runs across all MPI ranks in parallel:
- **Non-Orthogonality**: Maximum $< 70^\circ$, average $< 12^\circ$.
- **Skewness**: Internal $< 4.0$, Boundary $< 20.0$.
- **Negative / Inverted Cells**: Exactly 0.

### Step 8: Cuthill-McKee Bandwidth Reduction (`renumberMesh`)

`renumberMesh -overwrite` reorders cell indices using the Reverse Cuthill-McKee (RCM) algorithm. This reduces sparse matrix bandwidth, improving CPU cache locality and speeding up linear solver operations by 15–30%.

---

## Numerical Physics, Schemes & Solver Coupling

### Pre-Initialization with `potentialFoam`

Before `simpleFoam` starts, `potentialFoam` solves Laplace's equation for velocity potential:

$$\nabla^2 \Phi = 0, \quad \vec{U}_{\text{init}} = \nabla \Phi$$

This produces a divergence-free, physically plausible initial velocity field around wings and bodywork. It eliminates the initial pressure shockwave that frequently crashes RANS solvers on iteration 1.

### SIMPLEC Pressure-Velocity Coupling

The generator uses **SIMPLEC** (`consistent true;`) rather than standard SIMPLE:

In standard SIMPLE, the velocity correction neglects neighbor velocity corrections ($\sum A_{nb} u'_{nb}$), requiring aggressive under-relaxation ($U \approx 0.3, p \approx 0.3$) to prevent divergent oscillations.

SIMPLEC includes the dominant neighbor velocity terms, enabling significantly more aggressive relaxation without numerical instability:

```openfoam
SIMPLE
{
    nNonOrthogonalCorrectors 2;                          // 2 corrector loops for non-orthogonal mesh faces (up to 70°)
    consistent               true;                       // Enables SIMPLE-Consistent (SIMPLEC) coupling
}

relaxationFactors
{
    fields
    {
        p           0.7;                                 // Kinematic pressure relaxation (SIMPLEC enables 0.7 vs standard 0.3)
    }
    equations
    {
        U           0.7;                                 // Momentum equation relaxation factor (accelerates convergence)
        k           0.5;                                 // Turbulent kinetic energy relaxation factor
        omega       0.5;                                 // Specific dissipation rate relaxation factor
    }
}
```

**Result**: SIMPLEC achieves convergence in **20–30% fewer iterations** (~300–500 iterations faster), saving substantial compute time on large clusters.

### Spatial Discretization Schemes (`fvSchemes`)

Numerical schemes are chosen to guarantee second-order spatial accuracy while strictly preventing unphysical oscillations:

```openfoam
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss limitedLinear 1;        // 2nd-order TVD with Sweby limiter (sharp wing wake resolution)
    div(phi,k)      bounded Gauss upwind;                 // 1st-order bounded upwind (guarantees positive turbulent kinetic energy)
    div(phi,omega)  bounded Gauss upwind;                 // 1st-order bounded upwind (guarantees positive specific dissipation rate)
}

gradSchemes
{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;           // Cell-limited gradient (prevents overshoots at boundary layer interfaces)
}

laplacianSchemes
{
    default         Gauss linear limited corrected 0.5;   // Non-orthogonal corrected laplacian (stable up to 75° non-orthogonality)
}
```

### Linear Solvers & Multigrid Acceleration (`fvSolution`)

The linear solvers balance fast convergence with parallel scaling across 32+ MPI ranks:

```openfoam
solvers
{
    p
    {
        solver                  GAMG;                    // Geometric-Algebraic Multigrid solver for elliptic pressure equation
        smoother                DICGaussSeidel;          // Diagonal incomplete-Cholesky Gauss-Seidel smoother
        tolerance               1e-7;                    // Absolute convergence target for pressure residual
        relTol                  0.01;                    // Relative residual reduction per SIMPLE outer loop (1%)
        nPreSweeps              0;                       // Multigrid pre-smoothing sweeps
        nPostSweeps             2;                       // Multigrid post-smoothing sweeps
        cacheAgglomeration      true;                    // Reuses coarse grid hierarchy across iterations
        agglomerator            faceAreaPair;            // Coarsening algorithm based on face area pairing
        nCellsInCoarsestLevel   500;                     // Minimum cell count on the coarsest multigrid level
        mergeLevels             2;                       // Merges coarse grid levels across MPI processor boundaries (high-core scaling)
    }

    "(U|k|omega)"
    {
        solver                  PBiCGStab;               // Preconditioned Bi-Conjugate Gradient Stabilized linear solver
        preconditioner          DILU;                    // Diagonal Incomplete LU decomposition preconditioner
        tolerance               1e-8;                    // Absolute convergence tolerance for momentum/turbulence
        relTol                  0.01;                    // Relative residual reduction per iteration (1%)
        minIter                 1;                       // Minimum number of linear iterations per time step
    }
}
```

### Turbulence Closure & Wall Functions ($k$-$\omega$ SST)

The $k$-$\omega$ SST (Shear Stress Transport) model combines:
1. Standard $k$-$\omega$ formulation in the inner boundary layer (robust against adverse pressure gradients and flow separation).
2. Standard $k$-$\epsilon$ formulation in the freestream (eliminating sensitivity to inlet freestream turbulence values).

#### Continuous Spalding Wall Function (`nutUSpaldingWallFunction`)

In full-car simulations, $y^+$ varies dramatically from $y^+ \approx 5$ on small wing flaps to $y^+ \approx 120$ on large undertray panels.

Traditional wall functions require $y^+ > 30$ and fail catastrophically in the buffer layer ($5 < y^+ < 30$). The generator uses **Spalding's continuous law of the wall**:

$$y^+ = u^+ + \frac{1}{E} \left[ e^{\kappa u^+} - 1 - \kappa u^+ - \frac{(\kappa u^+)^2}{2} - \frac{(\kappa u^+)^3}{6} \right]$$

Spalding's law smoothly bridges the viscous sublayer, buffer layer, and logarithmic layer, providing accurate skin friction across any local $y^+$ value ($1 < y^+ < 150$).

---

## Post-Processing, Force Analysis & Live Monitoring

### Force Extraction & Decomposition

OpenFOAM's `forces` function object calculates total aerodynamic loads by integrating pressure and viscous shear stress over vehicle surface patches:

$$\vec{F}_{\text{total}} = \vec{F}_{\text{pressure}} + \vec{F}_{\text{viscous}} = \sum_{f} p_f \vec{A}_f + \sum_{f} \vec{\tau}_{w,f} \cdot \vec{A}_f$$

Forces are projected along configured axes:
- **Drag**: Along flow direction ($\vec{F} \cdot \vec{d}_{\text{drag}}$)
- **Downforce**: Toward ground ($\vec{F} \cdot \vec{d}_{\text{downforce}}$)
- **Efficiency ($L/D$)**: $\frac{\text{Downforce}}{\text{Drag}}$

Run `python read_forces.py`:

```text
=================================================================
  FORCE RESULTS (989 iterations)
  ℹ  SYMMETRY DETECTED: Showing Half-Model and Full-Car (x2)
=================================================================
  [Half-Model Simulated]
    Drag (-z):           123.940 N
    Downforce (-y):       293.160 N
    L/D:                     2.365

  [Full-Car Projected (x2)]
    Drag (-z):           247.880 N
    Downforce (-y):       586.320 N
    L/D:                     2.365
-----------------------------------------------------------------
  Averaged (last 200 iterations):
    Half-Model:  Drag =   123.249 N (±0.21%) | DF =   291.884 N (±0.38%)
    Full-Car:    Drag =   246.498 N (±0.21%) | DF =   583.768 N (±0.38%)
    L/D:             2.368
  Status: ✓ CONVERGED
=================================================================
```

### Multi-Part Force Accounting

If multiple STL files are supplied (e.g. `["front_wing.stl", "rear_wing.stl", "undertray.stl"]`), dedicated function objects are generated for each component:
- `postProcessing/forces_front_wing/0/force.dat`
- `postProcessing/forces_rear_wing/0/force.dat`
- `postProcessing/forces_undertray/0/force.dat`

This allows instant isolation of component downforce contributions and aerodynamic balance (Center of Pressure).

### Automated Convergence Monitor & Clean Auto-Stop

The convergence monitor evaluates stability over a rolling window of 200 iterations using the coefficient of variation (relative standard deviation):

$$\text{Variation} = \frac{\sigma_F}{|\mu_F|} \times 100\% \le 0.5\%$$

where $\sigma_F$ is the standard deviation and $\mu_F$ is the mean of force $F$ over the last 200 iterations.

When both Drag and Downforce vary by less than **0.5%** over the last 200 iterations (after a minimum of 300 iterations):
1. The monitor dynamically rewrites `system/controlDict`:
   ```openfoam
   stopAt writeNow;
   ```
2. `simpleFoam` detects the change at the next time step, writes full volume fields to disk, and exits cleanly with exit code 0.
3. Compute resources are immediately freed.

### Real-Time Animated Live Dashboard

Launch the animated real-time GUI during simulation:

```bash
python read_forces.py --live
```

Features:
- **Page 0 (Residuals)**: Real-time semi-log convergence plots for $p, U_x, U_y, U_z, k, \omega$.
- **Page 1 (Drag)**: Raw drag history, rolling 100-iteration average, and variance band.
- **Page 2 (Downforce)**: Raw downforce history, rolling average, and $L/D$ ratio.
- **Page 3 (Summary Table)**: Latest forces, rolling averages, percentage variations, and convergence status.
- **Interactive Navigation**: Cycle pages using GUI buttons or **Left / Right arrow keys**.
- **$O(N)$ Prefix-Sum Algorithm**: Cumulative sum rolling average ensures 60 FPS UI responsiveness even beyond 5,000 iterations.

### Multi-Case Tabular Comparison

Compare aerodynamic numbers across design iterations in your `cases/` directory:

```bash
python read_forces.py --compare
```

Output:
```text
===========================================================================
  Case               Drag [N]  Downforce [N]    L/D  Iters Status      
  ---------------- ---------- -------------- ------ ------ ------------
  FW_Config_A (x2)     185.20         420.10   2.27   1200 ✓ converged 
  FW_Config_B (x2)     178.40         445.60   2.50    950 ✓ converged 
  FW_Config_C (x2)     192.10         460.80   2.40    700 running     
===========================================================================
```

---

## HPC Cluster Execution & Fault Recovery

The generated `run.sh` script is engineered for high-performance computing clusters running SLURM:

```bash
sbatch run.sh
```

### Key Cluster Resilience Features

1. **Fast Local Scratch (`$TMPDIR` / `/dev/shm`)**:
   - The entire mesh generation and solver execution run on node-local NVMe or RAM scratch.
   - Bypasses shared parallel filesystems (NFS, Lustre, GPFS), eliminating file lock latency and metadata server bottlenecks across multi-million cell runs.
2. **Pruned Background Sync Loop**:
   - A background sync loop copies `postProcessing/` force logs and solver logs back to the submit directory every 15 seconds.
   - Internal `processor*` trees are explicitly excluded from the periodic sync, saving cluster I/O bandwidth.
3. **Signal Trapping & Clean Emergency Reconstruction**:
   - If the job hits the SLURM walltime limit or is cancelled (`scancel`), Linux signals (`SIGTERM`, `SIGINT`) are intercepted by a bash trap.
   - The trap immediately halts background monitors, triggers emergency parallel reconstruction (`reconstructPar -latestTime`), and copies final results back to the persistent storage directory.
4. **Crash State Preservation (`.running_location`)**:
   - If a crash occurs or copy-back fails, the script records the exact scratch node and directory in `.running_location`, ensuring simulation data is never lost.

---

## Performance Optimization Architecture

Eight targeted performance optimizations are implemented across every layer of the CFD pipeline:

| Layer | Optimization | Mechanism | Measured Impact |
| :--- | :--- | :--- | :--- |
| **STL Ingestion** | Streaming $O(1)$-Memory Parser | Line-by-line streaming in `stl_utils.py` | Memory drops from ~55 MB to < 1 MB on 50k-triangle STLs; preserves verbatim CAD precision |
| **CLI Pipeline** | Single-Pass Metadata Caching | Cached `stl_info` reuse in `cli.py` | Eliminates redundant 200 MB disk reads during domain sizing pass |
| **Solver Physics** | SIMPLEC Consistent Relaxation | $U = 0.7, p = 0.7$ with `consistent true;` | 20–30% fewer iterations to convergence (~300–500 fewer iterations) |
| **Linear Algebra** | Multigrid Agglomeration | GAMG with `mergeLevels 2;` in `fvSolution` | Eliminates inter-processor communication bottlenecks on 32+ cores |
| **Meshing Engine**| Load Balancing Tuning | `maxLoadUnbalance 0.25;` in `snappy` | Prevents continuous cell migration between MPI ranks during mesh snapping |
| **Mesh Quality** | Parallel `checkMesh` | Parallel MPI execution before reconstruction | Validates multi-million cell meshes ~10–20× faster |
| **HPC Cluster I/O**| Pruned `rsync` Transfer | Excludes `processor*` subtree crawls | Eliminates heavy NFS/Lustre filesystem strain during periodic sync |
| **Monitor GUI** | $O(N)$ Prefix-Sum Rolling Average | Cumulative sum accumulator in `plotting.py` | Replaces quadratic $O(N \cdot W)$ list slicing, eliminating GUI lag |

---

## FSAE & Aerodynamics Engineering Best Practices

### CAD Export Guidelines

- **Watertight Solids**: Ensure wings, endplates, and chassis are closed 3D solids. Zero-thickness surfaces (sheets) will fail during snappyHexMesh layer extrusion.
- **Fillet Sharp Trailing Edges**: If wing trailing edges are razor-thin (< 0.5 mm), consider adding a tiny 0.5 mm blunt flat face. This gives `snappyHexMesh` space to build high-quality prism layers.
- **Multi-Element Slats & Flaps**: Maintain at least a 5–10 mm gap between the main wing element and secondary flaps to prevent cell bridge pinching.

### Determining Aerodynamic Balance (Center of Pressure)

To find the longitudinal Center of Pressure ($x_{\text{CoP}}$):

$$x_{\text{CoP}} = \frac{M_{\text{pitch}}}{F_{\text{downforce}}}$$

Configure the center of rotation (`CofR`) at the front axle in `config.json`:
```json
"force_refs": {
    "CofR": [0.0, 0.0, 0.0],             // Center of Rotation (x, y, z) for pitch moment calculation (front axle)
    "lRef": 1.530,                       // Reference length in meters (wheelbase for pitch moment)
    "Aref": 1.000                        // Reference frontal area in m² for force coefficients (Cd, Cl)
}
```
The percentage of front downforce is then calculated directly from the pitch moment.

---

## Troubleshooting & FAQ

### 1. `snappyHexMesh` crashes with "Point is not inside mesh"
- **Cause**: The `locationInMesh` coordinate falls inside the CAD body or outside the domain box.
- **Solution**: The generator automatically places `locationInMesh` in the upstream-ceiling-farwall corner. If using custom overrides, ensure `locationInMesh` coordinates sit in open air.

### 2. Solution diverges on iteration 1 with `Floating point exception`
- **Cause**: Divergence caused by zero initial velocity around sharp trailing edges.
- **Solution**: `potentialFoam` is automatically run prior to `simpleFoam` in `Allrun.parallel`. Ensure `potentialFoam` runs successfully to initialize a smooth velocity field before `simpleFoam` begins.

### 3. Boundary layers fail to inflate on wings
- **Cause**: Surface triangulation is too coarse or `featureAngle` is too acute.
- **Solution**: Ensure `fidelity` is set to `"standard"` or `"fine"`. The generator uses `featureAngle 170;` and `resolveFeatureAngle 35;` to ensure layers wrap around sharp edges.

### 4. My CAD model is in millimeters instead of meters
- **Cause**: OpenFOAM treats STL coordinates as meters. A 1500 mm car will be meshed as a 1.5-kilometer-long vehicle.
- **Solution**: Scale your STL by $0.001$ in your CAD software or use OpenFOAM's `surfaceTransformPoints -scale '(0.001 0.001 0.001)' input.stl output.stl`.

---

## Automated Regression Tests

The test suite runs with standard Python:

```bash
python -m unittest discover -s tests -v
```

The test suite validates:
- Configuration validation and error catching for invalid geometries, axes, and types.
- Automatic virtual wind tunnel domain derivation and symmetry clipping mathematics.
- Exact coordinate preservation and $O(1)$-memory streaming STL processing.
- Restart-tolerant force and residual log parsing.
- Shell script syntax, background monitor daemons, and SLURM trap lifecycle harnesses.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
