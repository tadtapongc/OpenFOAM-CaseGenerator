# OpenFOAM Case Generator for External Aerodynamics

An OpenFOAM case generator for external aerodynamics, with defaults intended for vehicle and Formula Student / FSAE studies.

Given ASCII STL geometry and a JSON configuration, the generator writes domain bounds, meshing settings, SIMPLEC solver settings, boundary conditions, execution scripts, and force-monitoring tools.

Case generation and force parsing use the Python standard library. Running simulations requires a compatible OpenFOAM environment; plotting requires `matplotlib`.

The repository includes regression tests for generation, parsing, and script behavior. It does not include an OpenFOAM compatibility matrix, an end-to-end simulation benchmark, or aerodynamic validation results. Generated settings are starting points that need mesh, domain, and solution checks for each study.

---

## Table of Contents

1. [Key Features](#key-features)
2. [Quick Start & Requirements](#quick-start--requirements)
   - [System Requirements](#system-requirements)
   - [Workflow A: OpenFOAM Studio (Interactive Web GUI)](#workflow-a-openfoam-studio-interactive-web-gui)
   - [Workflow B: Standard Command-Line Interface (CLI)](#workflow-b-standard-command-line-interface-cli)
3. [OpenFOAM Studio (Interactive Web GUI)](#openfoam-studio-interactive-web-gui)
   - [Launching the Studio](#launching-the-studio)
   - [Interactive 3D WebGL Viewport & Coordinate System](#interactive-3d-webgl-viewport--coordinate-system)
   - [Multi-STL Assembly Visualization & Component Management](#multi-stl-assembly-visualization--component-management)
   - [Visual Configuration Builder](#visual-configuration-builder)
   - [Live Telemetry & Convergence Dashboard (Tab 3)](#live-telemetry--convergence-dashboard-tab-3)
   - [Simulation Cases Archive & Lifecycle Manager (Tab 4)](#simulation-cases-archive--lifecycle-manager-tab-4)
   - [Remote HPC Cluster & SLURM Integration](#remote-hpc-cluster--slurm-integration)
   - [Credential Security & Local Persistence](#credential-security--local-persistence)
4. [Case Anatomy & Directory Structure](#case-anatomy--directory-structure)
5. [Standard Command Workflow](#standard-command-workflow)
   - [Step 1: Place STL Geometry](#step-1-place-stl-geometry)
   - [Step 2: Configure Case (`configs/config.json`)](#step-2-configure-case-configsconfigjson)
   - [Step 3: Preview Case (Dry Run)](#step-3-preview-case-dry-run)
   - [Step 4: Generate OpenFOAM Case](#step-4-generate-openfoam-case)
   - [Step 5: Run Simulation (Standard OpenFOAM Commands)](#step-5-run-simulation-standard-openfoam-commands)
   - [Step 6: Post-Process Aerodynamic Forces](#step-6-post-process-aerodynamic-forces)
6. [Configuration Guide (`config.json`)](#configuration-guide-configjson)
   - [Essential Settings](#essential-settings)
   - [Ground Plane & Ride Height Styles](#ground-plane--ride-height-styles)
   - [Symmetry Plane & Half-Car Simulation](#symmetry-plane--half-car-simulation)
   - [Aircraft & Free-Air Simulation](#aircraft--free-air-simulation)
   - [Fluid & Atmospheric Properties](#fluid--atmospheric-properties)
   - [Turbulence Specification](#turbulence-specification)
   - [Parallel & SLURM Cluster Settings](#parallel--slurm-cluster-settings)
   - [Expert Overrides](#expert-overrides)
7. [Fidelity Presets & Mesh Sizing](#fidelity-presets--mesh-sizing)
8. [Geometry, Domain & Boundary Physics Deep Dive](#geometry-domain--boundary-physics-deep-dive)
   - [Automatic Domain Sizing Mathematics](#automatic-domain-sizing-mathematics)
   - [Coordinate Transformations & Orientation](#coordinate-transformations--orientation)
   - [Road & Moving Ground Boundary Condition](#road--moving-ground-boundary-condition)
   - [Symmetry Clipping & Force Projection](#symmetry-clipping--force-projection)
9. [Meshing Pipeline & `snappyHexMesh` Architecture](#meshing-pipeline--snappyhexmesh-architecture)
   - [Step 1: Feature Extraction (`surfaceFeatureExtract`)](#step-1-feature-extraction-surfacefeatureextract)
   - [Step 2: Background Hexahedral Grid (`blockMesh`)](#step-2-background-hexahedral-grid-blockmesh)
   - [Step 3: Conforming Distance-Based Refinement Shells](#step-3-conforming-distance-based-refinement-shells)
   - [Step 4: Two-Stage Wake Refinement Architecture](#step-4-two-stage-wake-refinement-architecture)
   - [Step 5: Surface Snapping Controls](#step-5-surface-snapping-controls)
   - [Step 6: Boundary Layer Inflation (`addLayersControls`)](#step-6-boundary-layer-inflation-addlayerscontrols)
   - [Step 7: Parallel Quality Verification (`checkMesh`)](#step-7-parallel-quality-verification-checkmesh)
   - [Step 8: Cell Renumbering (`renumberMesh`)](#step-8-cell-renumbering-renumbermesh)
10. [Numerical Physics, Schemes & Solver Coupling](#numerical-physics-schemes--solver-coupling)
    - [Pre-Initialization with `potentialFoam`](#pre-initialization-with-potentialfoam)
    - [SIMPLEC Pressure-Velocity Coupling](#simplec-pressure-velocity-coupling)
    - [Spatial Discretization Schemes (`fvSchemes`)](#spatial-discretization-schemes-fvschemes)
    - [Linear Solvers & Multigrid Acceleration (`fvSolution`)](#linear-solvers--multigrid-acceleration-fvsolution)
    - [Turbulence Closure & Wall Functions ($k$-$\omega$ SST)](#turbulence-closure--wall-functions-k-omega-sst)
11. [Post-Processing, Force Analysis & Live Monitoring](#post-processing-force-analysis--live-monitoring)
    - [Force Extraction & Decomposition](#force-extraction--decomposition)
    - [Multi-Part Force Accounting](#multi-part-force-accounting)
    - [Automated Convergence Monitor & Clean Auto-Stop](#automated-convergence-monitor--clean-auto-stop)
    - [Real-Time Animated Live Dashboard](#real-time-animated-live-dashboard)
    - [Multi-Case Tabular Comparison](#multi-case-tabular-comparison)
12. [HPC Cluster Execution & Fault Recovery](#hpc-cluster-execution--fault-recovery)
13. [Performance-Related Implementation Choices](#performance-related-implementation-choices)
14. [FSAE & Aerodynamics Study Considerations](#fsae--aerodynamics-study-considerations)
15. [Troubleshooting & FAQ](#troubleshooting--faq)
16. [Automated Regression Tests](#automated-regression-tests)

---

## Key Features

- **Standard Commands Only**: No custom CLI binary installation needed. Run directly with standard `python setup_case.py`, standard OpenFOAM commands (`blockMesh`, `snappyHexMesh`, `simpleFoam`), and standard `python read_forces.py`.
- **OpenFOAM Studio Web Application**: Includes an interactive browser-based UI (`run_app.sh` / `run_app.bat`) featuring a 3D geometry viewer, real-time 3D coordinate axes trihedron, live wind tunnel domain box visualization, bidirectional visual config synchronization, and direct remote SSH/SLURM cluster dispatching with local credential security.
- **Vehicle-Oriented Defaults**: Configurable domain padding, refinement levels, boundary layers, and wake regions.
- **Two Wake Refinement Boxes**: A `nearWakeBox` and a coarser `farWakeBox`, with dimensions derived from geometry bounds.
- **Distance Refinement Shells**: Refinement based on distance from the STL surface (e.g. 25 mm $\rightarrow$ Level 4, 80 mm $\rightarrow$ Level 3 for the standard preset).
- **Automatic Domain Sizing**: `"domain_box": "auto"` derives domain bounds from STL extents and configurable padding factors.
- **Offset Symmetry Planes**: Configurable symmetry coordinates (e.g. `"symmetry_plane": -0.1185` or `0.0`) set the domain boundary and wake-box alignment.
- **Incompressible Solver Settings**: Scripts invoke `potentialFoam` before `simpleFoam`, with SIMPLEC, limited velocity convection, upwind turbulence convection, and $k$-$\omega$ SST wall-function settings.
- **Force-Based Auto-Stop**: A background monitor requests solver termination (`stopAt writeNow;`) when drag and downforce meet a rolling variation threshold. This measures force stability, not overall solution accuracy.
- **SLURM Script Generation**: Optional scratch execution, periodic log sync, signal handlers, and attempts to reconstruct and retain results on failure.
- **Streaming STL Processing**: Bounding-box extraction and geometry copying process ASCII STL files line by line. Copying retains vertex text while rewriting solid names.
- **Zero External Python Dependencies for Generation**: Uses only Python's built-in standard library for all case generation and force parsing (`matplotlib` is only optional if you want graphical plots).

---

## Quick Start & Requirements

### System Requirements

- **Operating System**: Case generation uses Python. Generated execution scripts target a Linux/Bash environment with OpenFOAM; parallel runs also require MPI. Native Windows Python can generate files, but cannot run these scripts by itself.
- **OpenFOAM**: The templates use OpenCFD-style dictionaries and the `simpleFoam` workflow. Compatibility across releases and with Foundation editions has not been established by the repository's tests. Check generated dictionaries and commands against your installation.
- **Python**: Python $\ge$ 3.9 (standard library only for case generation; `matplotlib` optional for CLI plots; `fastapi`, `uvicorn`, `paramiko` for Web Studio).

### Getting Started

Clone the repository; the scripts run directly without installing this project as a package:

```bash
git clone https://github.com/tadtapongc/OpenFOAM-CaseGenerator.git
cd OpenFOAM-CaseGenerator
```

#### Workflow A: OpenFOAM Studio (Interactive Web GUI)

For a visual, interactive experience with 3D CAD visualization, wind tunnel cage inspection, real-time config editing, and remote cluster submission, run the 1-click launcher:

- **Linux / macOS**:
  ```bash
  chmod +x run_app.sh
  ./run_app.sh
  ```
- **Windows**:
  Double-click `run_app.bat` or run in Command Prompt / PowerShell:
  ```cmd
  run_app.bat
  ```
- **Cross-Platform / Manual**:
  ```bash
  pip install -e ".[web]"
  python -m cfd_gen.web.server
  ```
The studio will automatically open your default web browser to `http://127.0.0.1:8000`.

#### Workflow B: Standard Command-Line Interface (CLI)

For headless, automated, or scripted workflows, you only need Python standard library:

Place your ASCII STL in `stl/`, then edit `configs/config.json` to set its filename, a new case name, flow settings, and an appropriate MPI rank count. Preview and generate from the repository root:

```bash
python setup_case.py configs/config.json --dry-run
python setup_case.py configs/config.json
```

With OpenFOAM loaded in your shell, follow [Step 5](#step-5-run-simulation-standard-openfoam-commands) to run the generated case and [Step 6](#step-6-post-process-aerodynamic-forces) to inspect its forces. Plotting additionally requires `python -m pip install matplotlib`.

`python setup_case.py --init` creates starter directories and an example configuration; it does not supply geometry or overwrite an existing example.

---

## OpenFOAM Studio (Interactive Web GUI)

OpenFOAM Studio is a local web application providing an intuitive visual environment for setting up CFD cases, inspecting 3D geometries, validating domain bounds, and dispatching simulations to remote HPC clusters.

### Launching the Studio

You can launch OpenFOAM Studio via the automated runner scripts or standard Python:

```bash
# Linux / macOS (creates .venv, installs dependencies, launches server)
./run_app.sh

# Windows (creates .venv, installs dependencies, launches server)
run_app.bat

# Or direct Python invocation:
python -m cfd_gen.web.server --port 8000
```

Key CLI arguments for `cfd_gen.web.server`:
- `--host <ip>`: Bind address (default: `127.0.0.1`).
- `--port <port>`: Port to listen on (default: `8000`).
- `--restart`: Automatically terminate an existing CFD Studio instance on the port and restart.
- `--no-browser`: Do not automatically open the default web browser on launch.

> [!TIP]
> **Intelligent Port Supervisor**: If port `8000` is already occupied by a previously running CFD Studio process, the launcher automatically detects the process, cleans up the old process tree, and restarts immediately. If occupied by an unrelated application, it automatically advances to the next available open port.

---

### Interactive 3D WebGL Viewport & Coordinate System

The studio features a high-performance 3D viewport powered by Three.js with full OrbitControls support (left-click to rotate, right-click to pan, scroll to zoom).

#### Coordinate System & Color Conventions
The 3D scene adheres strictly to OpenFOAM and SAE vehicle aerodynamics coordinate standards:
- **+X Axis (Red)**: Lateral / symmetry spanwise direction (points toward driver's right).
- **+Y Axis (Green)**: Elevation / vertical height direction (points upwards from the ground plane).
- **+Z Axis (Blue)**: Longitudinal / freestream flow direction (freestream air flows along $-Z$ towards the outlet).

#### Viewport Elements & Diagnostic Overlays
1. **Interactive 3D Trihedron (Bottom-Right)**:
   A dedicated screen-fixed 3D orientation indicator with labeled axes ($X$, $Y$, $Z$) in the lower-right corner. It mirrors scene camera rotations dynamically in real time, ensuring you never lose spatial orientation.
2. **In-Scene CAD Origin Triad**:
   A visible coordinate triad located at the absolute origin `(0, 0, 0)` with labeled directional arrows to verify where your CAD coordinates and symmetry plane lie relative to OpenFOAM space.
3. **Live Virtual Wind Tunnel Bounding Cage**:
   A dynamic wireframe bounding box that renders the exact computational domain ($x_{min} \dots x_{max}, y_{min} \dots y_{max}, z_{min} \dots z_{max}$) computed from geometry bounds and padding settings. Any change in the configuration (e.g., domain padding, ground height, or symmetry plane offset) recalculates and updates the cage geometry in real time.
4. **Boundary Face Identification Labels**:
   World-space badges (`INLET ➔`, `➔ OUTLET`, `SYMMETRY`) positioned at the domain extremities with depth-tested materials, occluding behind geometry in foreground angles while remaining visible when panning around boundaries.
5. **Ground Plane Grid**:
   A reference ground grid positioned exactly at the active ground plane coordinate (`y = ground_plane`), providing visual feedback for ride height and ground clearance.
6. **Studio Aero Lighting & Double-Sided Rendering**:
   Balanced ambient and directional lighting with double-sided metallic materials, ensuring thin aerodynamic surfaces (splitters, endplates, multi-element wing profiles) never disappear or invert.
7. **Low-Profile Viewport HUD & Angle Presets**:
   A streamlined floating HUD provides instant controls for:
   - **Camera Presets**: One-click alignment to `Iso`, `Top` (gimbal-lock-free), `Side`, and `Front` orthographic-style perspectives.
   - **Fit Framing**: Toggle camera framing between **Fit Domain** (encompassing the full 40-50m wind tunnel) and **Fit Model** (tight zoom on vehicle geometry).
   - **Diagnostic Overlays**: Independent checkboxes for Origin Axes, Domain Wireframe, Geometry Bounding Box, Ground Plane, and Freestream Flow Vector.
   - **Maximize Viewport**: Expand the 3D canvas to a full-window view (or restore the split layout).

---

### Multi-STL Assembly Visualization & Component Management

Real-world aerodynamic packages (especially in FSAE, GT, and sports car racing) consist of multiple discrete CAD solid files—such as chassis, front wing assembly, rear wing multi-elements, suspension links, and underbody diffusers.

OpenFOAM Studio provides native multi-STL assembly inspection and management:

- **Simultaneous Multi-Component Rendering**:
  Load and view multiple independent STL files simultaneously in the virtual wind tunnel without geometry overwriting or ghosting.
- **Harmonious 8-Color Component Palette**:
  Each added STL component is assigned a distinct, high-contrast metallic color from a curated aerodynamic palette (`Sky Cyan`, `Mint Emerald`, `Rose Pink`, `Lavender`, `Amber Gold`, `Marine Teal`, `Coral Red`, `Electric Blue`), allowing instant visual identification of different wings, flaps, and body panels.
- **Interactive Component Chip Bar**:
  - **Color Dot Indicators**: Every component in the active setup list displays a color dot matching its 3D mesh in the viewport.
  - **Click to Highlight**: Clicking any component chip flashes an emissive cyan highlight on that part in the 3D scene.
  - **One-Click Part Removal (`×`)**: Removing an STL chip instantly deletes the corresponding mesh from the 3D scene, removes it from the configuration, and recalculates the domain bounds.
- **Union Bounding Box & Domain Integration**:
  The bounding box helper and automatic wind tunnel domain generator compute the **union bounding box** across all active components, ensuring adequate upstream/downstream domain sizing and ground clearance for the full assembly.
- **Batch Uploading**:
  Select or drag-and-drop multiple `.stl` files at once. The studio previews all parts locally in Three.js and uploads them concurrently to the server's `stl/` repository.

---

### Visual Configuration Builder

The web interface eliminates manual JSON editing errors with form-based parameter management and bidirectional synchronization:

- **Template Selection**: One-click configuration templates for:
  - *Standard Vehicle Half-Car* (symmetry plane at $x=0$, moving ground, auto-sized tunnel).
  - *Full-Car Moving Ground* (full vehicle with road velocity matching freestream).
  - *Airfoil / Aircraft Free-Air* (six-sided far-field boundaries without road interaction).
  - *Coarse Fast Test* (low mesh resolution for quick pipeline verification).
- **Fidelity Presets**:
  Select between `fast` (~2-4M cells), `standard` (~6-9M cells), or `fine` (~12-16M cells), with real-time estimates of cell count, runtime, and background cell size.
- **Physical & Boundary Setup**:
  - Dual-sync velocity control (interactive slider synchronized between km/h and m/s).
  - Ground clearance adjustment with options for absolute coordinates or relative offsets.
  - Interactive face boundary assignment (`inlet`, `outlet`, `symmetry`, `ground`, `farField`).
  - Automatic symmetry plane centering button based on the lateral geometry mid-plane.
- **SLURM Cluster & MPI Controls**:
  Configure parallel decomposition core count (8, 16, 32, 48, 64 cores), partition, walltime limit, memory per core, and OpenFOAM environment module source scripts.
- **Dictionary Overrides**:
  Optional expert overrides for base cell size, surface min/max levels, edge refinement, and two-stage wake boxes (`nearWakeBox`, `farWakeBox`).
- **Bidirectional JSON Drawer**:
  A slide-out Monaco/code editor allows inspecting and directly editing the active `config.json`. Form changes update JSON in real time, and JSON edits instantly refresh the visual controls and 3D visualizer.

---

### Live Telemetry & Convergence Dashboard (Tab 3)

The Telemetry Dashboard provides live aerodynamic tracking, convergence verification, and solver log monitoring:

- **Monitored Case Picker**:
  Select any generated case from the dropdown to monitor its solution progress.
- **Live Polling Toggle**:
  Toggle automatic 5-second polling on and off with the `● Live Sync (5s)` / `⏸ Paused` button, featuring a pulsing green live indicator.
- **Aerodynamic KPI Cards**:
  - **Downforce ($-F_y$)**: Average downforce in Newtons ($N$) with rolling variation percentage ($\pm\%$).
  - **Drag ($-F_z$)**: Average drag force in Newtons ($N$) with rolling variation percentage ($\pm\%$).
  - **Aero Efficiency ($L/D$)**: Real-time lift-to-drag ratio ($-F_y / -F_z$).
  - **Solver Iteration & Status**: Active iteration count and convergence state.
- **Dual Real-Time Convergence Charts**:
  - **Force History Chart**: Displays raw iteration forces alongside a **35-iteration smoothed moving average** trend line, making it easy to distinguish physical oscillations from numerical noise.
  - **Residuals Chart**: Plots equation residuals ($p$, $U$, $k$, $\omega$) on a logarithmic scale with clean scientific notation formatting.
- **Smart Standby & Empty State Handling**:
  When monitoring cases that are newly generated or meshed, clean overlays indicate the current stage (`Generated`, `Meshing`, `Meshed`) and present the exact command to execute (`./Allrun.parallel`), avoiding frozen or ghosted curves.
- **Solver & Meshing Log Console**:
  - Switch between `log.simpleFoam`, `log.snappyHexMesh`, `log.potentialFoam`, and `log.blockMesh`.
  - Auto-scroll toggle for tracking real-time solver output.
  - Displays current log file name and byte size.
  - **One-Click Copy**: Copy complete terminal log outputs to the clipboard.

---

### Simulation Cases Archive & Lifecycle Manager (Tab 4)

The Cases Archive provides a centralized view of all simulation cases residing on local storage and connected HPC clusters:

- **Summary Stat Cards**:
  At-a-glance KPI metrics showing:
  - **Total Cases**: Total count across local storage and remote clusters.
  - **Converged & Solved**: Simulations that satisfied the $\pm 0.5\%$ force convergence stability threshold.
  - **Active / Solving**: Simulations currently running or meshing.
  - **Ready / Meshed**: Cases generated and awaiting execution.
- **Real-Time Search & Status Filter Pills**:
  Filter cases instantly by name, geometry filename, fidelity preset, or status using the search bar and filter pills (`All`, `Converged`, `Completed`, `Solving`, `Generated`).
- **Comprehensive Case Data Table**:
  - **Case & Setup**: Case name, fidelity badge (`standard`, `fast`, `fine`), MPI core count (`32p`), and geometry tags.
  - **Status Badges**: Color-coded badges (`● CONVERGED`, `⚡ SOLVING`, `✓ COMPLETED`, `⬡ MESHED`, `○ GENERATED`, `⏳ QUEUED`, `✗ FAILED`).
  - **Flow Conditions**: Freestream velocity in km/h and m/s, along with flow direction vector.
  - **Aerodynamic Results**: Color-coded badges displaying final $F_y$ (downforce), $F_z$ (drag), and $L/D$ (aero efficiency).
  - **Progress**: Current solver iteration count.
  - **Location & Modified**: `Local`, `Cluster`, or `Local & Cluster` indicator with formatted timestamp (`YYYY-MM-DD HH:MM`).
- **Actions**:
  - **📊 Live Telemetry**: One-click jump to the Telemetry dashboard with the selected case loaded for real-time convergence and log monitoring.
  - **🗑️ Delete Case**: Synchronously removes case directories across local storage and the remote cluster via SSH.

---

### Remote HPC Cluster & SLURM Integration

OpenFOAM Studio includes an integrated SSH and SLURM manager to bridge local CAD preparation with remote cluster computation:

- **Secure SSH Connection**: Connects to remote compute clusters using SSH key pairs or password authentication via Paramiko.
- **One-Click Case Deployment**: Generates and transfers case files to the remote cluster scratch filesystem.
- **Job Dispatching**: Submits the generated `run.sh` SLURM batch script (`sbatch run.sh`) configured with your specified partition, node count, and default QoS (`cu_hpc` or custom).
- **Live Job Queue Monitoring**: Real-time table display of running, pending, and completed SLURM jobs (`squeue -u <user>`).
- **Job Cancellation**: One-click job termination directly from the queue table (`scancel <job_id>`).

---

### Credential Security & Local Persistence

To ensure zero risk of committing sensitive cluster credentials to Git:
- **No Hardcoded Defaults**: Target cluster hostname, SSH username, and remote paths are never hardcoded in repository files.
- **Browser LocalStorage**: Form fields automatically persist connection settings in your browser's private `localStorage` (`cfd_cluster_config`), so your host, user, and remote paths are remembered across sessions without touching the codebase.
- **User-Home Configuration**: Backend caching stores credentials strictly in `~/.cfd_gen_cluster.json` located in your user profile home directory, completely isolated from git repositories and shared environments.

---

## Case Anatomy & Directory Structure

Generation creates the following case files and scripts. The `.eMesh` files are produced later by feature extraction:

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
│       ├── <model>.stl                 # ASCII STL with rewritten solid names
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
├── run.sh                              # SLURM cluster submission script; adapt to your cluster
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
├── log.renumberMesh                    # Cell renumbering log
├── log.potentialFoam                   # Potential-flow initialization log
├── log.simpleFoam                      # Steady-state RANS solver log
├── log.reconstructPar                  # Parallel field reconstruction log
├── postProcessing/
│   ├── forces/0/force.dat              # Force vectors; CLI projects onto drag/downforce axes
│   ├── forces/0/moment.dat             # Moment vectors about CofR
│   ├── forceCoeffs/0/coefficient.dat   # Integrated force and moment coefficients (OpenCFD)
│   └── residuals/0/solverInfo.dat      # Solver convergence residuals for p, U, k, omega
└── VTK/                                # (Optional) Converted ParaView visualization files
```

The coefficient filename shown follows the [OpenCFD output specification](https://api.openfoam.com/2606/classFoam_1_1functionObjects_1_1forceCoeffs.html). Check filenames and column headers for your installed release.

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

Edit `configs/config.json` with standard JSON. The annotated examples below and in the configuration guide use `//` comments for explanation; remove those comments when copying into a JSON file. Later examples show fragments to merge into the top-level object.

```jsonc
{
    "case_name": "my_case",              // Case output folder created under cases/<case_name>/
    "stl_files": ["geometry.stl"],       // ASCII STL geometry filename(s) in stl/ directory
    "fidelity": "standard",              // Mesh and solver preset: "fast", "standard", or "fine"

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
    "symmetry_plane": 0.0,               // Lateral centerline coordinate if geometry uses symmetry (omit or 0.0 if centered)

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

Example output reproduced using the preceding configuration and geometry with the bounds shown below (paths shortened). The geometry is not bundled with the repository:
```text
  Config: configs/config.json
  ℹ  Ground plane: y = 0.035 m (ground clearance: 0.0 mm)

  Geometry bounds:
    min: (-0.118, 0.035, -1.450)
    max: (0.720, 1.180, 1.550)
  Domain box:
    min: (-0.118, 0.035, -25.450)
    max: (4.074, 5.760, 13.550)
  Mesh:
    Base cell:      0.1 m
    Surface level:  [4, 5]
    Edge level:     6
    Distance shells: 25mm→L4, 80mm→L3
    Region nearWakeBox: Level 3
    Region farWakeBox: Level 1

  DRY RUN — would generate: cases/my_case
    Velocity:   16.67 m/s  U=(0 0 -16.67)
    k=0.010421  ω=68.739  νt=0.0001516
    Surfaces:   geometry
    Pipeline:   potentialFoam → simpleFoam (1500 iters, bounded Gauss limitedLinear 1)
```

### Step 4: Generate OpenFOAM Case

Generate the complete OpenFOAM case directory structure under `cases/<case_name>/`:

```bash
python setup_case.py configs/config.json
```

Re-running generation with the same case name overwrites dictionaries, `0/`, `0.orig/`, scripts, and the configuration snapshot, while leaving previous results and logs in place. Use a new case name for a changed study: the generated `controlDict` starts from `latestTime`, so retained results can affect a subsequent run.

### Step 5: Run Simulation (Standard OpenFOAM Commands)

Navigate into the generated case directory:

```bash
cd cases/my_case
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

# 5. Report mesh quality metrics across all MPI ranks; inspect the log before solving
mpirun -np 32 checkMesh -allGeometry -allTopology -noFunctionObjects -parallel

# 6. Reconstruct the volume mesh from processor* directories back to constant/polyMesh
reconstructParMesh -constant
rm -rf processor*

# 7. Renumber cell labels
renumberMesh -overwrite

# 8. Re-decompose fields with the finalized volume mesh ready for solving
decomposePar

# 9. Run potential-flow initialization
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

Run the post-processing script from the project root. Replace `cases/my_case` with the case you want to inspect:

```bash
# Print the force summary for a specific case:
python read_forces.py cases/my_case

# Open the live dashboard:
python read_forces.py cases/my_case --live

# Display a force-history plot:
python read_forces.py cases/my_case --plot

# Save force_convergence.png in the current working directory:
python read_forces.py cases/my_case --save

# Check force stability (exit 0 if the criterion passes, 1 otherwise):
python read_forces.py cases/my_case --check

# Compare cases under cases/:
python read_forces.py --compare
```

Plotting requires `matplotlib`. With no case argument, single-case commands use the current directory if it looks like a case; otherwise they select the most recently modified case directory under `cases/`. Use an explicit path to track a particular study. `--compare` scans `cases/` independently of the case argument. `--check` uses the [CLI stability criterion](#automated-convergence-monitor--clean-auto-stop), which has a shorter minimum history than auto-stop.

---

## Configuration Guide (`config.json`)

### Essential Settings

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `case_name` | `string` | `"my_case"` | Folder name created under `cases/<case_name>/`; choose a new name for each study |
| `stl_files` | `list[str]` | *required* | List of STL files in `stl/` (e.g. `["car.STL"]` or `["wing.stl", "body.stl"]`) |
| `fidelity` | `string` | `"standard"` | Quality preset: `"fast"`, `"standard"`, or `"fine"` |
| `flow.velocity` | `float` | `16.67` | Freestream velocity in m/s (16.67 m/s $\approx$ 60 km/h) |
| `flow.direction` | `string` | `"-z"` | Freestream direction vector (`"-z"`, `"+z"`, `"-x"`, etc.) |
| `flow.ground` | `bool` | `true` | `true` sets moving road wall at freestream velocity; `false` sets slip wall |
| `outputs.drag_axis` | `string` | `"-z"` | Direction along which drag is calculated |
| `outputs.downforce_axis`| `string` | `"-y"` | Direction along which downforce (negative lift) is calculated |
| `domain_box` | `string / dict` | `"auto"` | `"auto"` derives bounds from STL; or supply `{"min": [...], "max": [...]}` |
| `domain_faces` | `dict[str, str]`| *auto* | Mapping of 6 box faces (`"-x"`, `"+x"`, etc.) to boundary types |
| `parallel.n_procs` | `int` | `10` | Number of MPI ranks; `configs/config.json` explicitly selects `32` |

### Ground Plane & Ride Height Styles

Adjust ground positioning relative to the CAD geometry:

- **Style 1 — Relative Ride Height (`ground_clearance`)**:
  Specifies the distance in meters below the lowest CAD vertex:
  ```jsonc
  "ground_clearance": 0.035   // Ground placed exactly 35 mm below lowest point of STL
  ```
- **Style 2 — Absolute Coordinate (`ground_plane`)**:
  Fixes the road coordinate at an exact CAD assembly elevation:
  ```jsonc
  "ground_plane": 0.0         // Ground plane placed at y = 0.0
  ```
- **Style 3 — Auto-Snap (Default)**:
  If omitted, the ground plane automatically snaps to the lowest point of the geometry (`y = smin`).

### Symmetry Plane & Half-Car Simulation

For a study that assumes symmetric geometry and flow, a half-model reduces the simulated domain. The change in cell count and runtime depends on the mesh and execution settings:

```jsonc
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

To configure a domain without a moving ground, use far-field faces above and below the geometry. This still uses the same steady incompressible solver setup:

```jsonc
"flow": {
    "velocity": 45.0,                    // Flight airspeed in m/s (45.0 m/s ≈ 162 km/h)
    "direction": "-z",                   // Flight direction vector (air flows from +z to -z)
    "ground": false                      // Disable the moving-ground condition; set domain faces below
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

```jsonc
"fluid": {
    "rho": 1.225,                        // Density in kg/m³; set for your fluid and conditions
    "nu": 1.516e-5                       // Kinematic viscosity in m²/s; set for your fluid and conditions
}
```

### Turbulence Specification

```jsonc
"turbulence": {
    "model": "kOmegaSST",                // Default turbulence model
    "intensity": 0.005,                  // Example freestream turbulence intensity: 0.5%
    "nut_ratio": 10                      // Initial turbulent-to-laminar viscosity ratio
}
```

Let $r$ be the configured `nut_ratio`, $I$ the turbulence intensity as a fraction, and $U_\infty$ the freestream speed. The generator initializes the turbulence fields using:

$$k_0 = \frac{3}{2}(U_\infty I)^2, \qquad \nu_{t,0} = r\nu, \qquad \omega_0 = \frac{k_0}{r\nu}.$$

The estimate for $k_0$ assumes isotropic turbulence. The viscosity-ratio relation is an initialization estimate, not the general SST eddy-viscosity law: the model recalculates $\nu_t$ using a strain-dependent limiter. The default $r=10$ can be changed in the configuration. See the [OpenFOAM SST model equations](https://doc.openfoam.com/2606/tools/processing/models/turbulence/ras/linear-evm/rtm/kOmegaSST/).

### Parallel & SLURM Cluster Settings

```jsonc
"parallel": {
    "n_procs": 32,                       // Total number of MPI ranks / CPU cores
    "method": "scotch"                   // Decomposition method: "scotch" (automatic graph partitioning)
},
"slurm": {
    "qos": "cu_hpc",                     // Quality of Service queue name on SLURM cluster
    "partition": "cpu",                  // Cluster hardware partition (e.g. cpu, compute, standard)
    "nodes": 1,                          // Requested node count
    "time": "08:00:00",                  // Maximum walltime allocation (hh:mm:ss)
    "mem_per_cpu": "2G",                 // RAM requested per core (2GB * 32 cores = 64GB total)
    "openfoam_module": [                 // Cluster module environment packages to load
        "GCC/11.3.0",
        "OpenMPI/4.1.4-GCC-11.3.0"
    ],
    "openfoam_source": "$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc",  // OpenFOAM environment activation script
    "use_tmpdir": false,                 // Standard HPC practice: false = run in-place on parallel scratch; true = node-local scratch ($TMPDIR)
    "sync_interval": 15                  // Periodic sync interval in seconds (only used if use_tmpdir: true)
}
```

### Expert Overrides

Configuration values can be customized either via an explicit `"overrides"` block or directly inside section keys.

> [!IMPORTANT]
> **Preset Precedence**: Any value explicitly specified by the user in `overrides` or directly inside a section (e.g. `solver.end_time`, `layers.n_layers`, `mesh_params.base_cell_size`) **strictly overrides** the fidelity preset defaults (`fast`, `standard`, `fine`). You can select `fidelity: "standard"` while overriding only specific parameters.

#### Style A — Explicit `"overrides"` Block (Recommended for Modular Sweeps)
```jsonc
{
    "case_name": "wing_study_high_res",
    "stl_files": ["wing.stl"],
    "fidelity": "standard",
    "overrides": {
        "solver": {
            "end_time": 600              // Run for 600 iterations instead of default 1500
        },
        "layers": {
            "n_layers": 7,               // Inflate 7 prism layers instead of standard 5
            "expansion_ratio": 1.25      // Custom layer geometric growth ratio
        },
        "fluid": {
            "rho": 1.15                  // High-altitude or heated air density in kg/m³
        }
    }
}
```

#### Style B — Direct Section Overrides
```jsonc
{
    "case_name": "chassis_overrides",
    "stl_files": ["chassis.stl"],
    "fidelity": "standard",
    "solver": {
        "end_time": 800,
        "write_interval": 200
    },
    "mesh_params": {
        "base_cell_size": 0.08,          // Finer background mesh (80 mm instead of 100 mm)
        "surface_level": [4, 6],         // Refine surface to level 6 (1.25 mm)
        "edge_level": 7                  // Feature edge refinement at 0.625 mm
    }
}
```

---

## Fidelity Presets & Mesh Sizing

Three presets supply mesh and solver settings. The table shows nominal refinement sizes for the listed base cells; actual cell shapes and layer coverage must be checked after meshing. Preset names do not establish accuracy, cell count, or runtime for a particular geometry.

| Metric / Parameter | Fast | Standard | Fine |
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

---

## Geometry, Domain & Boundary Physics Deep Dive

### Automatic Domain Sizing Mathematics

The generator pads the STL bounding box using configurable multiples of the geometry extents. These are sizing heuristics; the code does not calculate frontal area or verify a blockage ratio.

For the standard preset, the default padding is:

- **Upstream Distance**: $4 \times L_{geometry}$ ahead of the geometry.
- **Downstream Distance**: $8 \times L_{geometry}$ behind the geometry.
- **Top / Ceiling Distance**: $4 \times H_{geometry}$ above the geometry.
- **Lateral Far Wall**: $4 \times W_{geometry}$ from the outer edge, with width adjusted for an explicitly supplied symmetry plane.

Extents used for padding have a 0.1 m minimum. The fast and fine presets use different factors. Check domain sensitivity for your geometry and flow conditions.

### Coordinate Transformations & Orientation

Flow and force directions can be assigned to signed Cartesian axes. The generator uses those axes to choose domain dimensions and velocity components; it does not rotate the STL or accept arbitrary direction vectors:

```text
Flow Direction (-z):
  - Streamwise (Length): Z-axis (Inlet at +z, Outlet at -z)
  - Vertical (Height):   Y-axis (Road at -y, Ceiling at +y)
  - Lateral (Width):     X-axis (Symmetry at -x, Far Wall at +x)
```

If your CAD was exported with flow along `-x` and up along `+z`, set `"direction": "-x"` and `"downforce_axis": "-z"`. The generator automatically swaps indexing, aspect ratios, wake bounding boxes, and velocity vectors.

### Road & Moving Ground Boundary Condition

For faces assigned the `ground` role, the mesh patch type is `wall` regardless of `flow.ground`. The flag selects the field boundary conditions:

- When `"ground": true`:
  - Velocity ($U$): `fixedValue uniform (x y z)` matching the freestream velocity vector.
  - Turbulence: `kqRWallFunction` for $k$, `omegaWallFunction` for $\omega$, and `nutUSpaldingWallFunction` for $\nu_t$ by default.
- When `"ground": false`:
  - Velocity: `slip`; pressure, $k$, and $\omega$: `zeroGradient`; $\nu_t$: `calculated`.

Pressure uses `zeroGradient` in both cases. To remove the ground role from a free-air domain, assign that face to `farField` as in the aircraft example; setting `flow.ground=false` alone does not change its mesh patch type or domain placement.

### Symmetry Clipping & Force Projection

When simulating a half-model:
1. The domain boundary limits the modeled region; the copied STL is not geometrically trimmed by the generator. Inspect how `snappyHexMesh` handles surfaces crossing that boundary.
2. The `locationInMesh` seed point is placed near an upstream outer corner. Verify that it lies in the intended fluid region, especially for unusual geometry or manual domain bounds.
3. Wake boxes (`nearWakeBox` and `farWakeBox`) are automatically clipped so their inner lateral face aligns exactly with the symmetry plane coordinate.
4. `python read_forces.py` checks `domain_faces` in the selected configuration or `case_config.json`, then falls back to symmetry patch types in `constant/polyMesh/boundary`. If detected, it computes both simulated half-forces and full-car projected forces:
   $$F_{\text{full car}} = 2 \times F_{\text{half car}}$$

This projection assumes the configured symmetry represents a physical half-model. It does not verify that the geometry or flow is symmetric.

---

## Meshing Pipeline & `snappyHexMesh` Architecture

The scripts invoke the following tools to construct a hexahedral-dominant volume mesh. Inspect meshing logs, surface conformity, and layer coverage before using the mesh:

```text
[ surfaceFeatureExtract ] ──► [ blockMesh ] ──► [ snappyHexMesh (Parallel) ]
                                                        │
[ renumberMesh ] ◄── [ reconstructParMesh ] ◄── [ checkMesh (Parallel) ]
```

### Step 1: Feature Extraction (`surfaceFeatureExtract`)

Sharp aerodynamic edges (wing trailing edges, endplate perimeters, diffuser strakes, gurney flaps) are extracted into OpenFOAM `.eMesh` format using an included angle of `140°`:

$$\theta_{\text{included}} = 140^\circ$$

- `140°` is the default extraction threshold. Inspect the extracted edges and adjust the threshold if required by your surface triangulation.

### Step 2: Background Hexahedral Grid (`blockMesh`)

`blockMesh` creates the outer bounding box with uniform hexahedral cells having an aspect ratio close to $1:1:1$:

$$n_x = \text{round}\left(\frac{\Delta X}{h_0}\right), \quad n_y = \text{round}\left(\frac{\Delta Y}{h_0}\right), \quad n_z = \text{round}\left(\frac{\Delta Z}{h_0}\right)$$

### Step 3: Conforming Distance-Based Refinement Shells

The standard preset requests **distance-based surface shells**:
- Within **25 mm** of geometry $\rightarrow$ **Level 4** refinement (6.25 mm cell size).
- Within **80 mm** of geometry $\rightarrow$ **Level 3** refinement (12.5 mm cell size).

These settings define refinement distances from the surface. Their effect on total cell count and resolved flow features depends on the geometry and other refinement controls.

### Step 4: Two-Stage Wake Refinement Architecture

The generator defines two refinement boxes using the streamwise geometry extent $L$. The standard preset requests the following nominal refinement sizes:

1. **`nearWakeBox` (Level 3, 12.5 mm)**:
   - Extends $\max(2\,\mathrm{m},\,1.2L)$ downstream of the geometry's trailing bound.
   - Also overlaps the rearmost $0.4L$ of the geometry's bounding box.
2. **`farWakeBox` (Level 1, 50.0 mm)**:
   - Starts at the trailing bound and extends $\max(4\,\mathrm{m},\,3.5L)$ downstream.
   - Requests coarser refinement farther downstream. Wake resolution needs to be assessed from the resulting solution.

These minimum lengths can make a wake box reach or extend beyond the outlet for small geometries or shortened domains; the generated boxes are not clipped to the outlet. Only their overlap with the meshed domain is relevant. For example, with $L=0.5\,\mathrm{m}$ and standard domain padding, the far box and outlet are both 4 m downstream of the geometry's trailing bound.

### Step 5: Surface Snapping Controls

`snapControls` morph cell vertices onto the CAD triangles:
- `explicitFeatureSnap true;` pulls cell vertices directly onto `.eMesh` sharp lines.
- `implicitFeatureSnap true;` detects geometric features by sampling the surface. This is feature detection, distinct from the general surface-snapping step; see the [OpenFOAM snappyHexMesh guide](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.4-mesh-generation-with-the-snappyhexmesh-utility).
- `nSolveIter 200;` and `tolerance 2.0;` are the standard preset's snapping controls. Inspect the resulting surface conformity.

### Step 6: Boundary Layer Inflation (`addLayersControls`)

The standard preset requests prism layers on vehicle surfaces:
- **5 prism layers** with an expansion ratio of $1.20$; actual coverage can be lower.
- **Relative Thickness**: Layer thickness is specified relative to local cell size. The generator does not predict the resulting $y^+$; inspect the generated `yPlus` output and assess suitability for the wall treatment.
- `featureAngle 170;` controls the feature-angle limit for layer growth.
- `maxFaceThicknessRatio 0.5;` sets a layer-thickness constraint.

### Step 7: Parallel Quality Verification (`checkMesh`)

Immediately following `snappyHexMesh`, the parallel script runs `checkMesh` across MPI ranks. Inspect reported non-orthogonality, skewness, topology, and invalid cells. Invoking the check does not establish that the generated mesh meets the needs of the simulation.

### Step 8: Cell Renumbering (`renumberMesh`)

`renumberMesh -overwrite` reorders cell indices. Its effect on solver runtime depends on the mesh, ordering method, and hardware; this repository provides no measured speedup.

---

## Numerical Physics, Schemes & Solver Coupling

### Pre-Initialization with `potentialFoam`

The generated scripts invoke `potentialFoam` before `simpleFoam` to attempt potential-flow initialization. They continue even if this step fails, so inspect its log. Initialization alone does not establish solver stability.

### SIMPLEC Pressure-Velocity Coupling

The default configuration enables **SIMPLEC** with `consistent true;` and supplies the following relaxation factors. Suitable relaxation settings depend on the case:

```openfoam
SIMPLE
{
    nNonOrthogonalCorrectors 2;                          // Non-orthogonal correction setting
    consistent               true;                       // Enables SIMPLE-Consistent (SIMPLEC) coupling
}

relaxationFactors
{
    fields
    {
        p           0.7;                                 // Kinematic pressure relaxation
    }
    equations
    {
        U           0.7;                                 // Momentum equation relaxation factor
        k           0.5;                                 // Turbulent kinetic energy relaxation factor
        omega       0.5;                                 // Specific dissipation rate relaxation factor
    }
}
```

No comparative SIMPLE/SIMPLEC iteration-count benchmark is included in this repository.

### Spatial Discretization Schemes (`fvSchemes`)

The defaults use limited velocity convection and first-order upwind turbulence convection. These choices do not establish overall spatial accuracy or rule out oscillations; assess mesh and scheme sensitivity for your study:

```openfoam
divSchemes
{
    default         none;
    div(phi,U)      bounded Gauss limitedLinear 1;        // Limited convection for velocity
    div(phi,k)      bounded Gauss upwind;                 // Upwind convection for turbulent kinetic energy
    div(phi,omega)  bounded Gauss upwind;                 // Upwind convection for specific dissipation rate
}

gradSchemes
{
    default         Gauss linear;
    grad(U)         cellLimited Gauss linear 1;           // Cell-limited gradient
}

laplacianSchemes
{
    default         Gauss linear limited corrected 0.5;   // Limited non-orthogonal correction
}
```

### Linear Solvers & Multigrid Acceleration (`fvSolution`)

The default linear solver settings are:

```openfoam
solvers
{
    p
    {
        solver                  GAMG;                    // Geometric-Algebraic Multigrid solver for elliptic pressure equation
        smoother                DICGaussSeidel;          // Diagonal incomplete-Cholesky Gauss-Seidel smoother
        tolerance               1e-7;                    // Absolute convergence target for pressure residual
        relTol                  0.01;                    // Current/initial linear residual ratio threshold (1%)
        nPreSweeps              0;                       // Multigrid pre-smoothing sweeps
        nPostSweeps             2;                       // Multigrid post-smoothing sweeps
        cacheAgglomeration      true;                    // Reuses coarse grid hierarchy across iterations
        agglomerator            faceAreaPair;            // Coarsening algorithm based on face area pairing
        nCellsInCoarsestLevel   500;                     // Minimum cell count on the coarsest multigrid level
        mergeLevels             2;                       // Agglomeration level-merging setting
    }

    "(U|k|omega)"
    {
        solver                  PBiCGStab;               // Preconditioned Bi-Conjugate Gradient Stabilized linear solver
        preconditioner          DILU;                    // Diagonal Incomplete LU decomposition preconditioner
        tolerance               1e-8;                    // Absolute convergence tolerance for momentum/turbulence
        relTol                  0.01;                    // Current/initial linear residual ratio threshold (1%)
        minIter                 1;                       // Minimum number of linear iterations per time step
    }
}
```

`relTol 0.01` permits a linear solve to stop when its current residual falls below 1% of that solve's initial residual. The absolute `tolerance` and iteration limits also affect termination; this is not a requirement for a 1% reduction between successive SIMPLE iterations. See [OpenFOAM solution control](https://www.openfoam.com/documentation/user-guide/6-solving/6.3-solution-and-algorithm-control).

### Turbulence Closure & Wall Functions ($k$-$\omega$ SST)

The default is `kOmegaSST`. The generator writes `k`, `omega`, and `nut` fields and their boundary conditions. Turbulence-model suitability and sensitivity to inlet turbulence values must be assessed for the study.

#### Continuous Spalding Wall Function (`nutUSpaldingWallFunction`)

The generated `nut` wall boundary uses `nutUSpaldingWallFunction`. This selection does not establish skin-friction accuracy across all $y^+$ values. Check wall-function requirements for your OpenFOAM version, actual $y^+$, prism-layer coverage, and mesh sensitivity.

---

## Post-Processing, Force Analysis & Live Monitoring

### Force Extraction & Decomposition

OpenFOAM's `forces` function object integrates pressure and viscous contributions over the selected body patches:

$$\vec{F}_{\text{total}} = \vec{F}_{\text{pressure}} + \vec{F}_{\text{viscous}}.$$

The generated incompressible case stores kinematic pressure $p_k=p_{\mathrm{physical}}/\rho_\infty$ in units of $\mathrm{m^2/s^2}$. Using OpenFOAM's boundary face-area vectors $\vec{S}_f$, which point out of the fluid domain, the pressure force on the body is:

$$\vec{F}_{\text{pressure}} = \rho_\infty \sum_f (p_{k,f}-p_{k,\mathrm{ref}})\vec{S}_f.$$

Here $p_{k,\mathrm{ref}}$ is the reference pressure expressed in the same kinematic units. The `rho rhoInf;` and `rhoInf` entries supply `fluid.rho` for conversion to force in newtons. The viscous contribution comes from the model's effective stress at the body patches. See the [OpenFOAM forces documentation](https://doc.openfoam.com/2606/tools/post-processing/function-objects/forces/forces/).

Forces are projected along configured axes:

- **Drag**: $F_D=\vec{F}\cdot\vec{d}_{\text{drag}}$, along `outputs.drag_axis` (normally the flow direction).
- **Downforce**: $F_{DF}=\vec{F}\cdot\vec{d}_{\text{downforce}}$, along `outputs.downforce_axis`. The default `-y` makes downward force positive; setting `+y` reports upward lift under the same CLI label.
- **Displayed Ratio (`L/D`)**: $|F_{DF}/F_D|$. The CLI takes the absolute value, so inspect the signed force components to distinguish lift from downforce. A zero drag denominator makes this ratio undefined; the CLI's zero or omitted display in that case is not a physical efficiency value.

The generated `forceCoeffs` object also uses `outputs.downforce_axis` as `liftDir`. With the default `-y` direction, positive `Cl` therefore denotes downforce. Its `pitchAxis` is `dragDir` crossed with `liftDir` (default `-x`), and moments are referenced to `force_refs.CofR`. Match directions, reference area, reference length, and moment origin before comparing coefficients with another study.

`force.dat` contains force vectors; `moment.dat` contains moment vectors about `CofR`. The CLI projects the force vectors onto the configured axes and does not read pitching moments. These separate files are described in the [OpenFOAM forces output specification](https://api.openfoam.com/2512/forces_8H_source.html).

Run `python read_forces.py`. The following numbers illustrate the output format; they are not validation results:

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

Each component also has a `moment.dat` file alongside `force.dat`, containing moments about `CofR`. Center-of-pressure or aerodynamic-balance calculations require separate interpretation of those forces, moments, axes, and reference points.

### Automated Convergence Monitor & Clean Auto-Stop

The force-stability checks use relative sample standard deviation:

$$\text{Variation} = \frac{s_F}{|\bar F|} \times 100\% < 0.5\%.$$

Here $s_F$ is the sample standard deviation and $\bar F$ is the mean over the selected force-history window. Both drag and downforce must pass; a zero mean does not pass. The minimum history differs by tool:

- **Auto-stop monitor**: Waits for at least 300 samples, then checks the latest 200 samples with the default settings.
- **CLI summary, `--check`, comparison, and dashboard summary**: Can report convergence after 20 samples, using all available samples up to a 200-sample window. These reports do not impose the monitor's 300-sample minimum.

The counts refer to parsed force samples; with the generated one-sample-per-iteration output they correspond to solver iterations. A CLI `CONVERGED` result can therefore appear before auto-stop is eligible.

When the auto-stop criterion passes:
1. The monitor dynamically rewrites `system/controlDict`:
   ```openfoam
   stopAt writeNow;
   ```
2. The monitor requests that the solver write its state and stop through OpenFOAM's runtime-modifiable control dictionary.
3. The execution script proceeds to reconstruction and cleanup after the solver exits. Check the solver and reconstruction logs to confirm completion.

The monitor checks force variation only. A `CONVERGED` label means this criterion passed; it does not check residuals, conservation, mesh independence, or agreement with physical measurements. A steady force history alone does not establish a validated solution.

### Real-Time Animated Live Dashboard

Launch the animated real-time GUI during simulation:

```bash
python read_forces.py --live
```

Features:
- **Page 0 (Residuals)**: Real-time semi-log convergence plots for $p, U_x, U_y, U_z, k, \omega$.
- **Page 1 (Drag)**: Raw drag history, rolling 100-sample average, and a band showing the recent force range.
- **Page 2 (Downforce)**: Raw downforce history, rolling average, and $L/D$ ratio.
- **Page 3 (Summary Table)**: Latest forces, rolling averages, percentage variations, and convergence status.
- **Interactive Navigation**: Cycle pages using GUI buttons or **Left / Right arrow keys**.
- **Rolling Average Calculation**: Uses a cumulative sum to compute rolling averages in linear time in the number of samples. GUI refresh speed also depends on data loading, plotting, and hardware.

### Multi-Case Tabular Comparison

Compare aerodynamic numbers across design iterations in your `cases/` directory:

```bash
python read_forces.py --compare
```

Illustrative output (not benchmark results):
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

The generated `run.sh` script targets SLURM. Adjust its queue, modules, OpenFOAM source path, resource requests, and scratch settings for your cluster:

```bash
sbatch run.sh
```

### Scratch, Sync, and Recovery Behavior

1. **Optional Scratch Execution**:
   - With `use_tmpdir` enabled, the script copies the case into a temporary directory, preferring writable `$TMPDIR`, then `/dev/shm`, then the system temporary directory.
   - Storage type, capacity, persistence, and accessibility depend on the cluster. The script does not establish multi-node access to node-local scratch.
2. **Pruned Background Sync Loop**:
   - A background sync loop copies `postProcessing/` force logs and solver logs back to the submit directory every 15 seconds.
   - Internal `processor*` trees are excluded from the periodic sync. Full results are copied back during cleanup.
3. **Signal Handling and Recovery Attempts**:
   - Handlers for `SIGTERM`, `SIGINT`, and script exit attempt to stop background tasks, reconstruct the latest solver results when applicable, and copy scratch results back.
   - Recovery depends on available time and functioning storage. `SIGKILL` and node failure cannot be handled by these traps.
4. **Scratch Location Record (`.running_location`)**:
   - Before scratch execution, the script records the host and directory. It retains this record and scratch data when reconstruction or copy-back fails.
   - The record helps locate retained files; it is not a backup and cannot preserve data if the scratch storage is lost or removed by the cluster.

---

## Performance-Related Implementation Choices

The implementation includes the following choices. Their effects on memory use and runtime have not been established by reproducible benchmarks in this repository.

| Area | Implemented behavior |
| :--- | :--- |
| **STL Ingestion** | Bounding-box and copy operations process ASCII STL lines without retaining a full triangle list. |
| **CLI Pipeline** | Reuses `stl_info` metadata when copying geometry. |
| **Solver Settings** | Enables SIMPLEC and supplies pressure and velocity relaxation factors of 0.7. |
| **Linear Solvers** | Uses GAMG with `mergeLevels 2;` for pressure. |
| **Meshing** | Sets `maxLoadUnbalance 0.25;`. |
| **Mesh Checks** | Runs `checkMesh` in parallel before reconstruction in the parallel workflow. |
| **Cluster I/O** | Periodic `rsync` includes logs and `postProcessing/`, excluding processor trees. |
| **Monitor GUI** | Computes rolling averages with a cumulative sum. |

---

## FSAE & Aerodynamics Study Considerations

### CAD Export Guidelines

- **Surface Preparation**: Check closed surfaces, normals, intersections, and unintended gaps. The generator's STL parsing checks do not establish watertightness or meshability.
- **Sharp Trailing Edges**: Inspect whether the surface and volume meshes represent thin edges adequately. Geometry changes alter the modeled shape and require assessment.
- **Multi-Element Slats & Flaps**: Choose refinement that resolves the actual gaps and inspect the resulting cells and layers. No fixed gap size ensures successful meshing.

### Determining Aerodynamic Balance (Center of Pressure)

Center-of-pressure calculations require a consistent force/moment sign convention, reference point, and assumptions about the force line of action. A pitch-moment/downforce ratio is not a general formula when other force components contribute to the moment.

Set the moment reference point (`CofR`) explicitly, for example at the front axle:
```jsonc
"force_refs": {
    "CofR": [0.0, 0.0, 0.0],             // Center of Rotation (x, y, z) for pitch moment calculation (front axle)
    "lRef": 1.530,                       // Reference length in meters (wheelbase for pitch moment)
    "Aref": 1.000                        // Reference frontal area in m² for force coefficients (Cd, Cl)
}
```
The force CLI does not calculate front-axle load percentage. Derive aerodynamic balance separately using your reference point, wheelbase, force components, and moment convention.

---

## Troubleshooting & FAQ

### 1. `snappyHexMesh` crashes with "Point is not inside mesh"
- **Check**: Confirm that `locationInMesh` lies within the intended fluid region and the domain. The generated corner-based position is a heuristic; inspect it against the actual geometry.

### 2. Solution diverges on iteration 1 with `Floating point exception`
- **Check**: Inspect the solver log, mesh quality, boundary conditions, initial fields, and numerical settings. A floating-point exception does not identify a unique cause. Check the `potentialFoam` log too: the generated scripts continue if initialization fails.

### 3. Boundary layers fail to inflate on wings
- **Check**: Inspect layer-addition logs, surface triangulation, local gaps, refinement, thickness, and quality controls. Changing presets or feature angles alone does not ensure layer coverage.

### 4. My CAD model is in millimeters instead of meters
- **Cause**: OpenFOAM treats STL coordinates as meters. A 1500 mm car will be meshed as a 1.5-kilometer-long vehicle.
- **Solution**: Scale your STL by $0.001$ in your CAD software or use OpenFOAM's `surfaceTransformPoints -scale '(0.001 0.001 0.001)' input.stl output.stl`.

---

## Automated Regression Tests

The repository includes a comprehensive automated test suite consisting of **70 tests** implemented via Python's standard `unittest` framework:

```bash
# Run all automated tests:
python -m unittest discover -s tests -v
```

The test suite is organized into three specialized test modules:
1. **[tests/test_regressions.py](file:///c:/Users/tadta/OneDrive/Documents/projects/OpenFOAM-CaseGenerator/tests/test_regressions.py) (30 Tests)**:
   - Verifies configuration ingestion, default merging, and input validation.
   - Tests geometric domain box derivation, symmetry clipping, and ground elevation alignment.
   - Tests streaming STL inspection, facet counting, bounding boxes, and verbatim vertex copying.
   - Tests multi-stage trajectory stitching across solver restarts and rolling average calculation.
   - Validates that `convergence_monitor.py` has all Python type annotations dynamically stripped via AST for cluster portability on Python 3.6+.
2. **[tests/test_shell_scripts.py](file:///c:/Users/tadta/OneDrive/Documents/projects/OpenFOAM-CaseGenerator/tests/test_shell_scripts.py) (11 Tests, POSIX Bash)**:
   - Uses an isolated dummy OpenFOAM binary harness to test `Allrun`, `Allrun.parallel`, `Allclean`, and `run.sh` under real bash shells.
   - Validates background monitor sub-process cleanup on exit/SIGINT/SIGTERM.
   - Tests SLURM scratch RAM disk (`$TMPDIR`) execution, periodic `rsync` logging, and partial solution recovery on interruption (`reconstructPar -latestTime`).
   *(Skipped automatically on native Windows systems).*
3. **[tests/test_web_api.py](file:///c:/Users/tadta/OneDrive/Documents/projects/OpenFOAM-CaseGenerator/tests/test_web_api.py) (29 Tests)**:
   - Verifies FastAPI REST endpoints, schema templates, and default config responses.
   - Tests directory traversal attack defenses on configuration and STL file paths.
   - Validates credential security (ensuring cluster passwords are never exposed in API responses).
   - Tests mock SSH and SFTP cluster operations (SLURM queue parsing, remote job dispatching, cancellation).
   - Validates force telemetry extraction, symmetry doubling, and logarithmic residual parsing.

These tests do not execute OpenFOAM, measure large-file memory consumption, establish solver compatibility, or validate aerodynamic predictions.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
