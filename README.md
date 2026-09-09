# RapidFOAM

OpenFOAM external aerodynamics automation suite and Web Studio developed for **Rapidamente Formula Student** (Chulalongkorn University).

RapidFOAM automates the end-to-end OpenFOAM workflow for vehicle aerodynamics: CAD STL geometry ingestion, automatic wind tunnel domain sizing, `snappyHexMesh` refinement (surfaces, feature edges, distance shells, two-stage wake boxes, and boundary layer inflation), `simpleFoam` case configuration (SIMPLEC, k-omega SST), parallel execution, and real-time aerodynamic force telemetry (Drag, Downforce, L/D, Cd, Cl).

---

## Features

- **Automated Case Generation**: Generates complete, ready-to-run OpenFOAM cases (`0/`, `constant/`, `system/`, and shell scripts) from a single JSON configuration.
- **Smart Domain & Mesh Sizing**: Automatically bounds the virtual wind tunnel around input STL geometries, configures wake refinement boxes, and sets up boundary layer inflation.
- **Fidelity Presets**: Built-in mesh templates (`fast`, `standard`, `fine`) calibrated for rapid concept screening versus high-resolution validation.
- **Symmetry Plane Support**: Half-car simulations along `x = 0` cut mesh count and compute time in half, with automatic force scaling back to full-car values in summaries and plots.
- **Interactive Web Studio**: Three.js 3D domain visualizer, interactive config editor, live convergence telemetry, and 1-click remote HPC cluster dispatching via SSH/SLURM.
- **Live Telemetry & Auto-Stop**: Convergence monitor tracks rolling force variation and signals `stopAt writeNow;` once drag and downforce stabilize within +/- 0.5%, saving compute hours.
- **Post-Processing CLI**: Tabulate aerodynamic forces, plot live convergence curves, and compare multiple case iterations side-by-side.

---

## Installation

### Prerequisites

- **Python**: 3.9 or higher
- **OpenFOAM**: OpenFOAM v2006+ (e.g. v2006, v2206, v2306, v2406) or OpenFOAM 8/9/10/11 installed on the execution machine or cluster.

### Setup

Clone the repository and install RapidFOAM in editable mode:

```bash
git clone https://github.com/tadtapongc/RapidFOAM.git
cd RapidFOAM

# Core CLI tools only:
pip install -e .

# With Web Studio and plotting dependencies:
pip install -e ".[web,plot]"
```

Installed console scripts:
- `rapidfoam-setup` (or `rapidfoam`): Case generator CLI
- `rapidfoam-forces`: Force analysis and post-processing CLI
- `rapidfoam-monitor`: Standalone convergence auto-stop monitor
- `rapidfoam-studio` (or `rapidfoam-web`): Interactive Web Studio server

---

## Usage

RapidFOAM can be run through the interactive browser-based Studio or directly via the command line.

### Web Studio

The Web Studio provides a 3D visual viewport to inspect wind tunnel dimensions, edit flow conditions, generate cases, and manage remote HPC runs.

- **Windows**: Double-click `run_app.bat` (or execute `run_app.bat` in CMD / PowerShell).
- **Linux / macOS**: Run `./run_app.sh` in terminal.
- **Direct Command**:
  ```bash
  rapidfoam-studio
  # or:
  python -m rapidfoam.web.server
  ```

Open `http://127.0.0.1:8000` in your browser.

1. **Upload Geometry**: Drag and drop ASCII STL files into the 3D viewer. Multiple components (e.g. chassis, front wing, rear wing) can be viewed together.
2. **Set Parameters**: Adjust velocity, fidelity preset, ground clearance, and symmetry plane. The yellow wireframe domain updates dynamically in the 3D viewport.
3. **Run Locally or on HPC**:
   - Click **Generate Case** to build the case directory under `cases/<case_name>/`.
   - Use the **Cluster SSH** dialog to connect to your remote SLURM cluster, transfer the case, and monitor the queue.
4. **Monitor Telemetry**: Watch residual histories and force curves stream in real time.

---

### Command-Line Interface (CLI)

For headless servers, batch sweeps, or automated pipelines:

#### 1. Initialize Workspace (Optional)
To create a clean starter directory structure with sample configs:
```bash
python setup_case.py --init
```
This sets up `stl/`, `cases/`, and `configs/config.json`.

#### 2. Add Geometry
Export your geometry as an **ASCII STL** in **meters** and place it in the `stl/` folder:
```bash
stl/my_wing.stl
```

#### 3. Configure Case
Edit `configs/config.json` or create a new JSON config:

```json
{
  "case_name": "front_wing_v1",
  "stl_files": ["my_wing.stl"],
  "fidelity": "standard",
  "flow": {
    "velocity": 20.0,
    "direction": "-z",
    "ground": true
  },
  "outputs": {
    "drag_axis": "-z",
    "downforce_axis": "-y"
  },
  "domain_box": "auto",
  "symmetry_plane": 0.0,
  "parallel": {
    "n_procs": 16
  }
}
```

#### 4. Preview (Dry Run)
Inspect domain bounds, estimated cell sizing, and boundary assignments without writing files:
```bash
python setup_case.py configs/config.json --dry-run
# or using the CLI shortcut:
rapidfoam-setup configs/config.json -n
```

#### 5. Generate Case
Create the complete OpenFOAM case directory structure:
```bash
python setup_case.py configs/config.json
```
This generates `cases/<case_name>/` containing `0/`, `constant/`, `system/`, and execution scripts:
- `Allrun.parallel`: Full parallel pipeline (MPI)
- `Allrun`: Serial pipeline
- `Allclean`: Resets the case directory and restores initial fields
- `run.sh`: Ready-to-submit SLURM cluster batch script (`sbatch run.sh`)
- `convergence_monitor.py`: Standalone monitor script embedded in the case

#### 6. Run the Simulation
Navigate to the generated case directory and start the solver:

```bash
cd cases/front_wing_v1

# Parallel execution using MPI:
./Allrun.parallel

# Or single-core:
./Allrun

# Or submit to a SLURM cluster:
sbatch run.sh
```

The run script executes the standard OpenFOAM external aero pipeline:
1. `surfaceFeatureExtract` (extracts sharp feature edges to `.eMesh`)
2. `blockMesh` (creates background hexahedral mesh)
3. `decomposePar` (splits domain across MPI ranks)
4. `snappyHexMesh -overwrite` (surface snapping, refinement regions, boundary layers in parallel)
5. `checkMesh` (verifies mesh orthogonality and aspect ratio)
6. `reconstructParMesh` & `renumberMesh` (assembles and renumbers mesh)
7. `decomposePar` (redistributes mesh for solver ranks)
8. `potentialFoam` (initializes divergence-free flow field)
9. `convergence_monitor.py` (background process tracking force convergence)
10. `simpleFoam` (incompressible SIMPLEC solver with k-omega SST)
11. `reconstructPar` (collates parallel results back to root time directories)

#### 7. Read Aerodynamic Forces
Extract forces, check convergence, or generate plots:

```bash
# Print force summary table (Drag, Downforce, L/D):
python read_forces.py

# Specify a particular case directory:
python read_forces.py cases/front_wing_v1

# Live convergence plot during solve (requires matplotlib):
python read_forces.py --live

# Save convergence plot to PNG (saves force_convergence.png):
python read_forces.py --save

# Compare all cases in cases/ directory:
python read_forces.py --compare

# Check convergence status (exit code 0 if converged, 1 if not):
python read_forces.py --check
```

---

## Configuration Reference

Key settings available in `configs/config.json`:

| Parameter | Type | Description | Default |
| :--- | :--- | :--- | :--- |
| `case_name` | `string` | Target folder name under `cases/` | Required |
| `stl_files` | `list` | List of STL filenames in `stl/` | Required |
| `fidelity` | `string` | Mesh preset: `"fast"`, `"standard"`, or `"fine"` | `"standard"` |
| `flow.velocity` | `float` | Freestream velocity in m/s | `16.67` (~60 km/h) |
| `flow.direction` | `string` | Flow direction vector (`"-z"`, `"+x"`, etc.) | `"-z"` |
| `flow.ground` | `bool` | Enable moving ground wall at freestream speed | `true` |
| `domain_box` | `string` / `dict` | `"auto"` or explicit `{"min": [x,y,z], "max": [x,y,z]}` | `"auto"` |
| `symmetry_plane` | `float` / `null` | Coordinate for symmetry split (e.g. `0.0`), or omit for full 3D | `null` |
| `ground_clearance` | `float` | Relative road gap in meters below lowest STL point | Lowest vertex |
| `ground_plane` | `float` | Fixed CAD elevation coordinate of ground (takes precedence over clearance) | `null` |
| `parallel.n_procs` | `int` | Number of CPU cores for MPI decomposition | `10` |

### Fidelity Presets

| Preset | Base Cell | Surface Levels | Edge Level | Boundary Layers | Max Iterations | Target Cells | Typical Runtime |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fast` | 0.15 m | [3, 4] | 5 | 3 | 800 | ~2–4 M | ~5–10 min (16–32 cores) |
| `standard` | 0.10 m | [4, 5] | 6 | 5 | 1500 | ~6–9 M | ~30–60 min (32 cores) |
| `fine` | 0.08 m | [5, 6] | 7 | 6 | 3000 | ~12–16 M | ~2–4 hrs |

---

## Technical Notes & Conventions

### STL Format & Units
- **Format**: Geometry files must be in **ASCII STL** format. Binary STLs should be converted in CAD before running (e.g. SolidWorks: *Save As → STL → Options → Output: ASCII*).
- **Units**: OpenFOAM assumes geometry coordinates are in **meters**. If CAD is exported in millimeters (mm), scale geometry by `0.001` before running, or use:
  ```bash
  surfaceTransformPoints -scale '(0.001 0.001 0.001)' input.stl output.stl
  ```

### Coordinate Orientation
- **X axis**: Lateral / spanwise.
- **Y axis**: Vertical / height above ground.
- **Z axis**: Streamwise / longitudinal (freestream air travels along `-Z`).
- Drag axis: `-Z`. Downforce axis: `-Y` (negative lift).

### Symmetry Planes
For straight-line running conditions (zero yaw), a half-car model with a symmetry plane at `x = 0` cuts cell count by roughly 50%. RapidFOAM automatically detects symmetry and outputs both half-model values and full-car projected values (multiplied by 2) in summary tables and comparisons.

### Convergence Auto-Stop
The background monitor (`convergence_monitor.py`) inspects force outputs every 10 seconds. Once drag and downforce variation remains within +/- 0.5% over a 200-iteration rolling window (after at least 300 iterations), the monitor writes `stopAt writeNow;` to `system/controlDict` to gracefully terminate the solve.

---

## Repository Structure

```text
RapidFOAM/
├── configs/            # Case configuration JSON files
├── stl/                # CAD geometry files (ASCII STL in meters)
├── cases/              # Generated OpenFOAM case directories
├── src/rapidfoam/      # Core RapidFOAM package
│   ├── config.py       # Config loading, defaults, and input validation
│   ├── geometry.py     # Domain sizing, fidelity presets, mesh parameters
│   ├── stl_utils.py    # Streaming ASCII STL inspection and validation
│   ├── cli.py          # Command-line entry points (setup, forces)
│   ├── writers/        # OpenFOAM dictionary and execution script generators
│   │   ├── base.py     # FoamFile headers and formatting helpers
│   │   ├── constants.py# transportProperties, turbulenceProperties
│   │   ├── fields.py   # 0/ initial & boundary fields (U, p, k, omega, nut)
│   │   ├── mesh.py     # blockMeshDict, snappyHexMeshDict, surfaceFeatureExtractDict
│   │   ├── solver.py   # fvSchemes, fvSolution, controlDict, decomposeParDict
│   │   └── scripts.py  # Allrun, Allrun.parallel, Allclean, run.sh, convergence_monitor.py
│   ├── postproc/       # Aerodynamic force analysis & plotting
│   │   ├── forces.py   # force.dat parser, symmetry scaling, convergence checks
│   │   ├── plotting.py # Matplotlib static & live convergence plots
│   │   ├── compare.py  # Multi-case comparison table
│   │   ├── residuals.py# Residual parser
│   │   └── convergence_monitor.py # Standalone convergence auto-stop monitor
│   └── web/            # RapidFOAM Web Studio
│       ├── server.py   # FastAPI backend & static file server
│       ├── ssh_client.py # Paramiko SSH/SFTP client for remote SLURM clusters
│       └── static/     # Web Studio UI (Three.js 3D viewport, telemetry graphs)
├── tests/              # Automated test suite (74 unit & regression tests)
├── run_app.bat         # 1-click launcher for Windows
├── run_app.sh          # 1-click launcher for Linux / macOS
├── setup_case.py       # Case generator CLI script
└── read_forces.py      # Force analysis and plotting CLI script
```

---

## Testing

Run the automated test suite with Python's standard `unittest`:

```bash
python -m unittest discover -s tests -v
```

---

## Authors

- **Tadtapong C.** ([@tadtapongc](https://github.com/tadtapongc)) — Lead Developer & Maintainer
- **Rapidamente Formula Student** (Chulalongkorn University) — Aerodynamics Division

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

### Trademark Notice
OPENFOAM® is a registered trademark of OpenCFD Limited. RapidFOAM is an independent project and is not affiliated with, sponsored, or endorsed by OpenCFD Limited.
