# RapidFOAM

OpenFOAM® external aerodynamics automation suite and Web Studio developed for **Rapidamente Formula Student** (Chulalongkorn University).

<img width="1292" height="586" alt="RapidFOAM" src="https://github.com/user-attachments/assets/db91bb4b-5261-4cea-a793-a40dfc756ddc" />

https://github.com/user-attachments/assets/caced105-394c-4c8f-b6f1-86d14df9ae85

> **Trademark Notice**  
> OPENFOAM® is a registered trade mark of OpenCFD Limited, producer and distributor of the OpenFOAM software via [www.openfoam.com](https://www.openfoam.com).  
> This offering is not approved or endorsed by OpenCFD Limited, producer and distributor of the OpenFOAM software via [www.openfoam.com](https://www.openfoam.com), and owner of the OPENFOAM® and OpenCFD® trade marks.

RapidFOAM streamlines the OpenFOAM workflow for external vehicle aerodynamics: CAD STL ingestion, domain sizing, cfMesh dictionary generation (default) or optional `snappyHexMesh`, `simpleFoam` steady-state case setup (SIMPLEC, k-omega SST), execution scripts, and force convergence monitoring (Drag, Downforce, L/D). The case writers support `kOmegaSST`; other turbulence models are rejected.

---

## Features

- **Case Directory Generation**: Generates complete OpenFOAM case structures (`0/`, `constant/`, `system/`) and execution scripts from a single JSON configuration.
- **Domain & Mesh Parameter Derivation**: Derives wind tunnel dimensions from STL bounding boxes, creates two-stage wake refinement regions (`nearWakeBox`, `farWakeBox`), distance shells, and boundary layer controls.
- **Mesh Fidelity Presets**: Predefined configuration presets (`fast`, `standard`, `fine`) targeting different resolution levels and turnaround times.
- **Mesher-Native Profiles**: One case config drives either engine; cfMesh and snappy keep their own native settings in `src/rapidfoam/mesher_profiles/`, selectable with `--mesher`.
- **Symmetry Plane Support**: Half-car simulations (e.g. `x = 0`) cut mesh cell count roughly in half, with automatic 2x force scaling in summaries and comparison tables.
- **Web Studio Interface**: Browser-based UI with Three.js 3D domain visualization, interactive parameter editor, real-time convergence charts, and remote SLURM cluster job submission over SSH.
- **Convergence Auto-Stop**: Background monitor tracks rolling force variation and signals `stopAt writeNow;` once drag and downforce stabilize within a user-defined threshold (default +/- 0.5%).
- **Post-Processing CLI**: Tabulates aerodynamic forces (Drag, Downforce, L/D), plots live convergence curves, and compares multiple case iterations side-by-side.

---

## OpenFOAM Compatibility & Environment

### Supported OpenFOAM Versions

- **Primary Target**: **ESI-OpenCFD releases (OpenFOAM v2006, v2106, v2206, v2306, v2406, v2606)**
  - The generated dictionaries utilize OpenCFD syntax conventions (such as `libs (forces);` function objects and modern Open MPI process binding options).
- **OpenFOAM Foundation (v8, v9, v10, v11)**:
  - The core solvers (`simpleFoam`, `snappyHexMesh`, `blockMesh`, `surfaceFeatureExtract`) and boundary condition structures are largely compatible. Note that minor syntax differences (such as function object library naming like `"libforces.so"`) may apply depending on the specific release.

### Environment Configuration
The path to your OpenFOAM installation is configured in `configs/config.json` under `"slurm"`:
- `openfoam_source`: Path to your OpenFOAM environment script (e.g. `"$HOME/OpenFOAM/OpenFOAM-v2606/etc/bashrc"` or `"/opt/openfoam2606/etc/bashrc"`).
- `openfoam_module`: List of environment modules to load on HPC clusters (e.g. `["GCC/11.3.0", "OpenMPI/4.1.4-GCC-11.3.0"]` or `["OpenFOAM/v2206-foss-2022a"]`), or `null` if sourcing directly.

---

## Installation

### Prerequisites

- **Python**: 3.9 or higher
- **OpenFOAM**: Installed locally or on the remote cluster (see compatibility above).

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

RapidFOAM can be run through the interactive Web Studio or via the command line.

### Web Studio

The Web Studio provides a 3D viewport to inspect domain sizing, edit flow conditions, generate cases, and manage remote HPC jobs.

- **Windows**: Run `run_app.bat` (or double-click it in Windows Explorer).
- **Linux / macOS**: Run `./run_app.sh` in terminal.
- **Direct Command**:
  ```bash
  rapidfoam-studio
  # or:
  python -m rapidfoam.web.server
  ```

Open `http://127.0.0.1:8000` in your browser.

1. **Upload Geometry**: Drop ASCII STL files into the 3D viewer. Multiple components (e.g. chassis, front wing, rear wing) can be viewed together.
2. **Configure Parameters**: Adjust velocity, fidelity preset, ground clearance, and symmetry planes. The yellow wireframe domain updates dynamically in the 3D viewport.
3. **Run Locally or on HPC**:
   - Click **Generate Case** to build the case directory under `cases/<case_name>/`.
   - Use the **Cluster SSH** dialog to connect to a remote SLURM cluster, transfer the case files, and submit the batch job.
4. **Monitor Telemetry**: Watch force histories (Drag, Downforce) and residuals update as the case solves.

**Engine switches change the profile, not your case config.** The *Mesher Engine* selector writes `mesher` into the saved case config, and the Expert tab exposes the profile knobs directly: *First Layer Specification* (`layers.first_layer_mode`) and *7. Mesher Engine Policy* (`cfmesh.ground_refine`, `cfmesh.layer_mode`, `cfmesh.optimise_layer`). Anything left on **Auto** follows `src/rapidfoam/mesher_profiles/<mesher>.json`, and the Auto labels show that resolved value (fetched from `/api/config/schema-defaults`). Validation, the domain preview and the generated case all run through the same config resolver, so the UI can never disagree with the case it writes.

---

### Command-Line Interface (CLI)

For headless servers, batch sweeps, or automated pipelines:

#### 1. Initialize Workspace (Optional)
To create a starter directory structure with a sample configuration:
```bash
python setup_case.py --init
```
This creates `stl/`, `cases/`, and `configs/config.json`.

#### 2. Place CAD Geometry
Export your geometry as an **ASCII STL** in **meters** and place it in the `stl/` folder:
```bash
stl/my_wing.stl
```

> **Geometry Note**: `snappyHexMesh` requires clean, watertight surface geometry without open holes or self-intersecting triangles. Check and repair CAD exports before meshing.

#### 3. Configure Case
Edit `configs/config.json` or create a case-specific JSON config:

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

#### 4. Preview Settings (Dry Run)
Inspect domain extents, estimated base cell sizes, and boundary assignments without writing files:
```bash
python setup_case.py configs/config.json --dry-run
# or:
rapidfoam-setup configs/config.json -n
```

#### 5. Generate Case
Generate the complete OpenFOAM case directory:
```bash
python setup_case.py configs/config.json
```
This generates `cases/<case_name>/` containing `0/`, `constant/`, `system/`, and execution scripts:
- `Allrun.parallel`: MPI parallel execution script
- `Allrun`: Single-core execution script
- `Allclean`: Resets the case directory and restores initial condition fields
- `run.sh`: SLURM batch submission script (`sbatch run.sh`)
- `convergence_monitor.py`: Embedded auto-stop monitor script

#### 6. Run the Simulation
Navigate to the case directory and execute the run script:

```bash
cd cases/front_wing_v1

# Run in parallel using MPI:
./Allrun.parallel

# Or submit to a SLURM cluster:
sbatch run.sh
```

With the default `cfmesh` engine, the script runs `cartesianMesh`, checks the mesh, then initializes with `potentialFoam` and solves with `simpleFoam`. Meshing runs directly; solver parallelism uses MPI. The `snappy` alternative executes:
1. `surfaceFeatureExtract` (extracts feature edges to `.eMesh`)
2. `blockMesh` (creates background hexahedral mesh)
3. `decomposePar` (splits domain across MPI ranks)
4. `snappyHexMesh -overwrite` (surface snapping, refinement regions, boundary layers in parallel)
5. `checkMesh` (verifies mesh orthogonality and quality metrics)
6. `reconstructParMesh` & `renumberMesh` (assembles and renumbers mesh)
7. `decomposePar` (redistributes mesh for solver ranks)
8. `potentialFoam` (initializes divergence-free flow field)
9. `convergence_monitor.py` (background process tracking force convergence)
10. `simpleFoam` (incompressible SIMPLEC solver with k-omega SST)
11. `reconstructPar` (collates parallel results back to root time directories)

#### 7. Post-Process Aerodynamic Forces
Extract forces, verify convergence, or generate plots:

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
| `flow.direction` | `string` | Flow direction vector (`"-z"`, `"+x"`, `"-x"`, etc.) | `"-z"` |
| `flow.ground` | `bool` | Enable moving ground wall at freestream speed | `true` |
| `outputs.drag_axis` | `string` | Axis along which drag force is reported | `"-z"` |
| `outputs.downforce_axis` | `string` | Axis along which downforce (-lift) is reported | `"-y"` |
| `domain_box` | `string` / `dict` | `"auto"` or explicit `{"min": [x,y,z], "max": [x,y,z]}` | `"auto"` |
| `symmetry_plane` | `float` / `null` | Coordinate for symmetry split (e.g. `0.0`), or omit for full 3D | `null` |
| `ground_clearance` | `float` | Relative road gap in meters below lowest STL point | Lowest vertex |
| `ground_plane` | `float` | Fixed CAD elevation coordinate of ground (takes precedence over clearance) | `null` |
| `parallel.n_procs` | `int` | Number of CPU cores for MPI decomposition | `10` |

### Mesh Fidelity Presets

| Preset | Base Cell | Surface Levels | Edge Level | Boundary Layers | Max Iterations | Target Cells† | Estimated Runtime* |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `fast` | 0.15 m | [3, 4] | 5 | 3 | 800 | ~0.2–4 M | ~5–10 min |
| `standard` | 0.10 m | [4, 5] | 6 | 5 | 1500 | ~0.5–2 M | ~6–45 min |
| `fine` | 0.08 m | [5, 6] | 7 | 6 | 3000 | ~2–16 M | ~2–4 hrs |

*\* Runtime estimates for typical Formula Student half-car models on a 32-core cluster node. Solver time scales with cell count, so the mesher dominates the spread.*<br>*† Cell counts depend strongly on the mesher. On one A/B (identical config, STL and 32-core node) a `standard` run produced **449 k cells / 6 min** with snappy and **1.3 hrs** with cfMesh, with the mesher itself taking only 5 min of that: cfMesh's `minCellSize` floor defaulted to the *edge* cell, which is a **global** refinement floor and resolved the whole body two levels finer than snappy's surface level. `mesh_params.min_cell_size` now defaults to `"body"` (= snappy's `surface_level[0]`), so both engines resolve the same cells; set it to `"edge"`, `"base"` or a value in metres to bias that trade-off. Read `cells:` from `log.checkMesh` after the first run and tune `mesh_params.body_cell_size` next.*

### Mesher Engines & Profiles

Both engines are driven from the **same case config**; the engine-specific settings live in one tracked profile per mesher:

```text
src/rapidfoam/mesher_profiles/cfmesh.json    # cfMesh-native defaults (shipped)
src/rapidfoam/mesher_profiles/snappy.json    # snappy-native defaults (shipped)
configs/meshers/<mesher>.json                # optional project-local override
```

Merge order is `DEFAULT_CONFIG -> mesher profile -> case config -> mesh_params_<mesher> -> overrides`, so a case file always wins over a profile. Anything the engines read differently has a home there:

| Intent | snappy-native | cfMesh-native |
| :--- | :--- | :--- |
| Surface resolution | `surface_level: [body, feature]` levels | `body_cell_size` / `edge_cell_size` in metres |
| Smallest cell | `edge_level` (feature-edge cells only) | `min_cell_size` — a **global** floor, defaults to `"body"` (the edge cell over-refines the whole surface ~8x) |
| Ground plane | never refined (layered only if `layers.ground_layers`) | `cfmesh.ground_refine` (default `false`) |
| Boundary layers | `layers` block, `first_layer_mode: "relative"` | `cfmesh.layer_mode: "patch_only"`, `optimise_layer: "auto"` |
| Cell budget | `maxGlobalCells` (enforced) | none — cost follows cell size, `ground_refine`, `optimise_layer` |

Run the same config through either engine to A/B them:

```bash
rapidfoam -c configs/config.json                  # mesher from the config
rapidfoam -c configs/config.json --mesher snappy  # one config, both engines
```

For fast design iteration use `fidelity: "fast"`: `cfmesh.optimise_layer: "auto"` skips cfMesh's layer-optimisation pass, the ground is not refined, and only the STL surfaces receive boundary layers. Validate a shortlisted design at `standard`/`fine` (or cross-check with `--mesher snappy`).

The same knobs live in the Web Studio: *Mesher Engine* plus *7. Mesher Engine Policy* and *First Layer Specification* in the Expert tab. `GET /api/config/schema-defaults` returns the profile-resolved defaults per engine (`mesher_defaults`), so the UI can show what **Auto** means instead of guessing.


---

## Technical Notes & Conventions

### STL Format & Units
- **Format**: Geometry files must be in **ASCII STL** format. Binary STLs should be converted in CAD before running (e.g. SolidWorks: *Save As → STL → Options → Output: ASCII*).
- **Units**: OpenFOAM assumes geometry coordinates are in **meters**. If CAD is exported in millimeters (mm), scale geometry by `0.001` before running:
  ```bash
  surfaceTransformPoints -scale '(0.001 0.001 0.001)' input.stl output.stl
  ```

### Coordinate System & Axis Flexibility
RapidFOAM supports arbitrary coordinate systems by configuring flow and force directions to match your CAD orientation:

- **Default Formula Student Convention**:
  - Longitudinal flow: along `-Z` (`"flow.direction": "-z"`, `"outputs.drag_axis": "-z"`)
  - Vertical / height: `+Y` (`"outputs.downforce_axis": "-y"`)
  - Lateral / spanwise: `X` (symmetry plane at `x = 0`)
- **Alternative Orientations**: If your CAD model is oriented differently (for example, flow along `+X` and height along `+Z` in aerospace conventions), update `flow.direction`, `drag_axis`, and `downforce_axis` in `configs/config.json`:
  ```json
  "flow": {
    "direction": "+x"
  },
  "outputs": {
    "drag_axis": "+x",
    "downforce_axis": "-z"
  }
  ```
  The generator automatically maps inlet, outlet, ground, and lateral boundaries, and aligns upstream/downstream domain padding with the active flow axis.

### Symmetry Planes
For straight-line running conditions (zero yaw), a half-car model with a symmetry plane at `x = 0` cuts cell count by roughly 50%. When a symmetry boundary is present, RapidFOAM reports both the simulated half-model values and the projected full-car values (multiplied by 2) in summaries and comparison tables.

### Convergence Auto-Stop
The background monitor (`convergence_monitor.py`) inspects force outputs every 10 seconds. Once drag and downforce variation remains within +/- 0.5% over a 200-iteration rolling window (after at least 300 iterations), the monitor writes `stopAt writeNow;` to `system/controlDict` to terminate the solve gracefully and write final results.

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
│   ├── mesher_profiles/ # Engine-native meshing profiles (cfmesh.json, snappy.json)
│   └── web/            # RapidFOAM Web Studio
│       ├── server.py   # FastAPI backend & static file server
│       ├── ssh_client.py # Paramiko SSH/SFTP client for remote SLURM clusters
│       └── static/     # Web Studio UI (Three.js 3D viewport, telemetry graphs)
├── tests/              # Python and Node regression tests
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
node --test tests/test_frontend.cjs
```

Install `.[web,plot]` for the full Python suite. Shell integration tests require Linux/POSIX and are skipped on Windows. Web tests run in temporary workspaces.

Studio's **Validate** action performs read-only validation. **Save Config** writes the input JSON only; **Generate Locally** writes case dictionaries. Editing visual controls preserves advanced settings that have no corresponding control. `--restart` is required for the launcher to terminate an existing Studio instance.

SSH connections verify host keys against the user's SSH known-hosts file. Before first use, connect with your normal SSH client and verify the server fingerprint through your cluster administrator. Studio rejects unknown or changed keys. Password persistence is off by default; explicitly enabling it stores the password as plaintext on local disk. SSH keys are preferable when available.

The cfMesh surface writer concatenates the wind-tunnel box and CAD surfaces. It does **not** perform CAD clipping, intersection repair, boolean subtraction, or manifold certification. CAD crossing symmetry or touching ground requires preparation and a mesh check on the target cfMesh version. The bundled sample crosses its configured symmetry plane; successful dictionary generation alone does not certify a valid mesh. Force stability likewise does not establish mesh independence or aerodynamic accuracy.

---

## Authors

- **Tadtapong C.** ([@tadtapongc](https://github.com/tadtapongc)) — Lead Developer & Maintainer
- **Rapidamente Formula Student** (Chulalongkorn University) — Aerodynamics Division

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

### Trademark Notice
OPENFOAM® is a registered trade mark of OpenCFD Limited, producer and distributor of the OpenFOAM software via [www.openfoam.com](https://www.openfoam.com).

This offering is not approved or endorsed by OpenCFD Limited, producer and distributor of the OpenFOAM software via [www.openfoam.com](https://www.openfoam.com), and owner of the OPENFOAM® and OpenCFD® trade marks.
