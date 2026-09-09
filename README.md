# RapidFOAM 🏎️💨

> **Rapid External Aerodynamics & OpenFOAM Automation Suite**  
> Developed for **Rapidamente Formula Student** (Chulalongkorn University).

RapidFOAM automates the entire OpenFOAM workflow for external vehicle aerodynamics. Give it an STL file and a simple config, and it automatically builds the wind tunnel domain, sets up `snappyHexMesh`, configures the `simpleFoam` solver, sets boundary conditions, and provides real-time force telemetry ($C_D$, $C_L$).

---

## Quick Start: Which way do you want to use it?

You can use RapidFOAM in two ways:
1. **[RapidFOAM Studio (Web GUI)](#1-rapidfoam-studio-interactive-web-gui---recommended)**: Visual 3D viewport, real-time domain sizing, live convergence graphs, and 1-click HPC cluster dispatching. *(Recommended)*
2. **[Command-Line Interface (CLI)](#2-command-line-interface-cli)**: Fast, scriptable, zero-GUI workflow using simple terminal commands.

---

## 1. RapidFOAM Studio (Interactive Web GUI) — *Recommended*

The Web Studio gives you a full visual environment in your browser without having to edit JSON or OpenFOAM dictionary files by hand.

### Step 1: Launch the Studio

- **Windows**: Double-click `run_app.bat` (or run `run_app.bat` in PowerShell/CMD).
- **Linux / macOS**: Run `./run_app.sh` in your terminal.
- **Direct Python**:
  ```bash
  pip install -e ".[web]"
  rapidfoam-studio
  # or: python -m rapidfoam.web.server
  ```
The Studio will automatically open in your browser at `http://127.0.0.1:8000`.

---

### Step 2: Set Up Your Simulation

1. **Upload or Select STL**:
   - In the **3D Viewer** panel, upload your CAD export (`.stl`).
   - You can upload multiple STL files (e.g., chassis, front wing, rear wing) to inspect multi-element assemblies together.
2. **Inspect the 3D Wind Tunnel**:
   - Rotate, pan, and zoom in the 3D viewport.
   - The yellow wireframe box is the **computational domain** (wind tunnel). It automatically resizes whenever you change padding or car dimensions.
3. **Configure Flow & Physics**:
   - **Velocity**: Set freestream speed in m/s (e.g. `20 m/s` for FSAE, `16.67 m/s` = 60 km/h).
   - **Fidelity Preset**: Choose mesh quality preset:
     - `fast` (~2–4M cells, ~10 min): Quick design sanity check.
     - `standard` (~6–9M cells, ~30–60 min): Balanced sweet spot for Formula Student aero package iteration. *(Recommended)*
     - `fine` (~12–16M cells, ~2–4 hrs): High-resolution final aerodynamic validation.
   - **Ground & Ride Height**: Set moving ground plane (`true`/`false`) and road clearance/elevation.
   - **Symmetry Plane**: Enable half-car simulation along $X=0$ (or offset) to cut cell count and solve time by 50%.

---

### Step 3: Run & Monitor

- **Local Run**: Click **"Generate Case"** to create a complete OpenFOAM case in `cases/<case_name>/`.
- **Remote Cluster Run (HPC / SLURM)**:
  1. Open the **Cluster SSH** dialog (top right).
  2. Enter your cluster credentials (host, user, password/key).
  3. Click **"Run on Cluster"** — RapidFOAM transfers the files, queues the SLURM job, and streams progress.
- **Telemetry Tab**: Watch force convergence (Drag and Downforce) and residual plots update in real time as the solver runs.

---

## 2. Command-Line Interface (CLI)

For headless clusters, automated sweeps, or command-line purists.

### Step 1: Place Your CAD Geometry
Export your geometry as an **ASCII STL** in **meters**, and place it in the `stl/` folder:
```bash
stl/my_wing.stl
```

---

### Step 2: Configure Your Case
Copy or edit `configs/config.json`. A clean, minimal working example:
```json
{
  "case_name": "front_wing_iter1",
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
    "n_procs": 8
  }
}
```

---

### Step 3: Preview (Dry Run)
Before generating files, preview domain dimensions, mesh sizing, and boundary conditions:
```bash
python setup_case.py configs/config.json --dry-run
# or:
rapidfoam-setup configs/config.json -n
```

---

### Step 4: Generate Case
Generate the full OpenFOAM case directory structure:
```bash
python setup_case.py configs/config.json
```
This generates a ready-to-run case inside `cases/front_wing_iter1/` with all dictionaries (`0/`, `constant/`, `system/`) and execution scripts (`Allrun`, `Allrun.parallel`, `Allclean`).

---

### Step 5: Run the Simulation
Navigate to the generated case directory and start the solver:

```bash
cd cases/front_wing_iter1

# Run in parallel using MPI (uses n_procs specified in config):
./Allrun.parallel

# Or run on a single core:
./Allrun
```

The script automatically executes:
1. `surfaceFeatureExtract` (extracts sharp aerodynamic feature lines)
2. `blockMesh` (generates hexahedral background domain mesh)
3. `decomposePar` (distributes domain across MPI ranks)
4. `snappyHexMesh -overwrite` (conforming body snapping, distance shells, wake boxes & boundary layers in parallel)
5. `checkMesh` (checks mesh quality & orthogonality in parallel)
6. `reconstructParMesh` & `renumberMesh` (unifies and renumbers mesh bandwidth)
7. `decomposePar` (redistributes final mesh for solver)
8. `potentialFoam` (initializes divergence-free potential velocity field)
9. `convergence_monitor.py` (background process tracking force convergence)
10. `simpleFoam` (incompressible turbulent Navier-Stokes with SIMPLEC and $k$-$\omega$ SST)
11. `reconstructPar` (collates parallel time steps back to reconstructed case)

---

### Step 6: Post-Process Aerodynamic Forces

Check convergence, calculate drag and downforce, or plot charts:

```bash
# Print force summary table (Drag, Downforce, Lift-to-Drag ratio):
python read_forces.py

# Show live real-time convergence graph during solve:
python read_forces.py --live

# Save convergence plot as PNG image:
python read_forces.py --save

# Compare multiple cases side-by-side in a summary table:
python read_forces.py --compare
```

---

## Must-Know Rules for Formula Student Aerodynamics 💡

1. **Units Must Be Meters ($m$)**:
   - OpenFOAM assumes STL coordinates are in **meters**.
   - *Common mistake*: If your CAD is exported in millimeters ($mm$), a 1.5-meter wing becomes 1,500 meters long! Scale your STL by $0.001$ before running.
2. **Coordinate Orientation Convention**:
   - **$+Z$ / $-Z$ (Blue)**: Longitudinal flow direction (freestream air flows along $-Z$).
   - **$+Y$ (Green)**: Upward vertical axis (height above ground).
   - **$+X$ (Red)**: Spanwise lateral axis.
3. **Use Symmetry Planes ($X=0$)**:
   - If your car or wing is symmetric and running straight (zero yaw angle), simulate half the car along $X=0$.
   - This cuts mesh cell count in half and doubles your simulation turnaround speed. RapidFOAM automatically doubles forces back to full-car values in summaries.
4. **Auto-Stop Convergence**:
   - RapidFOAM runs `convergence_monitor.py` in the background. Once drag and downforce variation drops below $\pm 0.5\%$ over a rolling window of 200 iterations (after a minimum of 300 iterations), it sets `stopAt writeNow;` to cleanly finish the solver, saving precious HPC compute hours.

---

## Project Structure Overview

```text
RapidFOAM/
├── configs/            # Case configuration JSON files
├── stl/                # Place CAD STL files here
├── cases/              # Generated OpenFOAM case directories
├── src/rapidfoam/      # Core RapidFOAM automation engine & Web Studio
├── tests/              # Automated test suite (74 unit tests)
├── run_app.bat         # 1-Click launcher for Windows
├── run_app.sh          # 1-Click launcher for Linux / Mac
├── setup_case.py       # CLI case generator entry point
└── read_forces.py      # CLI force analysis & plotting tool
```

---

## Authors & Acknowledgements

Developed for **Rapidamente Formula Student** (Chulalongkorn University).  
Maintained by Tadtapong C. ([@tadtapongc](https://github.com/tadtapongc)) & Rapidamente Aerodynamics Division.

---

## OpenFOAM® Trademark Notice

OPENFOAM® is a registered trade mark of OpenCFD Limited. RapidFOAM is an independent project by Rapidamente Formula Student and is not approved or endorsed by OpenCFD Limited.
