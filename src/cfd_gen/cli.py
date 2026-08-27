"""CLI entry points for case generation and post-processing."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def setup_main() -> None:
    """Entry point for cfd-setup command."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="Generate OpenFOAM case from STL + JSON config.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    cfd-setup --init                    Create starter project structure
    cfd-setup configs/example.json      Generate case
    cfd-setup configs/example.json -n   Preview only (dry run)
""",
    )
    parser.add_argument("config", nargs="?", help="JSON config file")
    parser.add_argument("--dry-run", "-n", action="store_true",
                        help="Preview settings without generating files")
    parser.add_argument("--init", action="store_true",
                        help="Create starter project structure")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="  %(message)s",
    )

    project_dir = Path.cwd()

    if args.init:
        _do_init(project_dir)
        return

    if not args.config:
        parser.print_help()
        sys.exit(1)

    _do_generate(Path(args.config), project_dir, dry_run=args.dry_run)


def _do_init(project_dir: Path) -> None:
    """Create starter project structure."""
    from cfd_gen.config import DEFAULT_CONFIG

    cfg_dir = project_dir / "configs"
    cfg_dir.mkdir(exist_ok=True)

    # Write minimal example config
    example = {
        "case_name": "my_wing",
        "stl_files": ["my_geometry.STL"],
        "flow": {
            "velocity": 16.67,
            "direction": "-z",
            "ground": True,
        },
        "outputs": {
            "drag_axis": "-z",
            "downforce_axis": "-y",
        },
    }
    out_path = cfg_dir / "example.json"
    out_path.write_text(json.dumps(example, indent=4) + "\n")

    (project_dir / "stl").mkdir(exist_ok=True)
    (project_dir / "cases").mkdir(exist_ok=True)

    print(f"\n  ✓ Created: {out_path}")
    print(f"  ✓ Created: stl/ and cases/")
    print(f"\n  Next steps:")
    print(f"    1. Place STL files in stl/")
    print(f"    2. Edit configs/example.json")
    print(f"    3. cfd-setup configs/example.json")


def _do_generate(cfg_path: Path, project_dir: Path, dry_run: bool = False) -> None:
    """Generate a complete OpenFOAM case."""
    from cfd_gen.config import find_stl, load_config, validate
    from cfd_gen.geometry import (
        compute_mesh_params,
        turbulence_values,
        vec_str,
        velocity_vector,
    )
    from cfd_gen.stl_utils import copy_stl, stl_bounds

    if not cfg_path.exists():
        sys.exit(f"ERROR: {cfg_path} not found")

    # Load and validate config
    cfg = load_config(cfg_path)
    
    # Load raw config to correctly handle user overrides
    with open(cfg_path) as f:
        raw_user = json.load(f)
    raw_overrides = raw_user.get("overrides", {})
    
    def _is_set(section: str, key: str) -> bool:
        """Check if user explicitly set a value in their config."""
        if section in raw_overrides and key in raw_overrides[section]: return True
        if section in raw_user and key in raw_user[section]: return True
        return False

    print(f"  Config: {cfg_path}")

    errors, warnings = validate(cfg, project_dir)
    for w in warnings:
        print(f"  ⚠  {w}")
    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    ✗ {e}")
        sys.exit(1)

    # Resolve STL names (strip extensions for OpenFOAM patch names)
    stl_dir = project_dir / cfg["stl_dir"]
    stl_names: list[str] = []
    stl_paths: list[Path] = []
    for name in cfg["stl_files"]:
        stem = name.rsplit(".", 1)[0] if "." in name else name
        stl_names.append(stem)
        path = find_stl(stl_dir, name)
        if path:
            stl_paths.append(path)

    cfg["stl_names"] = stl_names

    # Compute combined STL bounds
    all_min = [float("inf")] * 3
    all_max = [float("-inf")] * 3
    for path in stl_paths:
        smin, smax = stl_bounds(path)
        for i in range(3):
            all_min[i] = min(all_min[i], smin[i])
            all_max[i] = max(all_max[i], smax[i])

    if all_min[0] == float("inf"):
        sys.exit("ERROR: No valid STL files found — cannot compute domain")

    combined_bounds = (tuple(all_min), tuple(all_max))

    # Warn if STL is too close to domain boundary
    box = cfg["domain_box"]
    axis_labels = ["x", "y", "z"]
    for i in range(3):
        clearance_min = all_min[i] - box["min"][i]
        clearance_max = box["max"][i] - all_max[i]
        stl_extent = all_max[i] - all_min[i]
        min_clearance = max(0.1, stl_extent * 0.1)  # at least 10% of geometry size
        if clearance_min < min_clearance:
            print(f"  ⚠  STL very close to domain boundary: "
                  f"{axis_labels[i]}_min (clearance: {clearance_min:.3f} m)")
        if clearance_max < min_clearance:
            print(f"  ⚠  STL very close to domain boundary: "
                  f"{axis_labels[i]}_max (clearance: {clearance_max:.3f} m)")

    # Derive mesh parameters from geometry
    cfg["domain_box"] = cfg["domain_box"]  # required in config
    cfg["mesh_params"] = compute_mesh_params(cfg, combined_bounds)
    # Apply fidelity presets conditionally
    from cfd_gen.geometry import FIDELITY_PRESETS
    fidelity = cfg.get("fidelity", "fast")
    preset = FIDELITY_PRESETS.get(fidelity, FIDELITY_PRESETS["fast"])
    
    if not _is_set("solver", "end_time"):
        cfg["solver"]["end_time"] = preset["end_time"]
    if not _is_set("layers", "n_layers"):
        cfg["layers"]["n_layers"] = preset["n_layers"]
    if not _is_set("layers", "expansion_ratio"):
        cfg["layers"]["expansion_ratio"] = preset["expansion_ratio"]
    if not _is_set("layers", "first_layer_thickness"):
        cfg["layers"]["first_layer_thickness"] = preset["first_layer_thickness"]
    if not _is_set("layers", "nLayerIter"):
        cfg["layers"]["nLayerIter"] = preset.get("nLayerIter", 50)
    if not _is_set("layers", "nRelaxIter"):
        cfg["layers"]["nRelaxIter"] = preset.get("nRelaxIter_layers", 10)
    if not _is_set("solver", "write_interval"):
        cfg["solver"]["write_interval"] = preset["write_interval"]
    if not _is_set("snap", "nSolveIter"):
        cfg["snap"]["nSolveIter"] = preset.get("nSolveIter", 200)
    if not _is_set("snap", "nFeatureSnapIter"):
        cfg["snap"]["nFeatureSnapIter"] = preset.get("nFeatureSnapIter", 15)
        
    # Only apply preset SLURM time if user left it as default 'auto'
    if cfg["slurm"]["time"] in ("auto", "04:00:00"):
        cfg["slurm"]["time"] = preset.get("slurm_time", "04:00:00")

    # Derived values for display
    k, omega, nut = turbulence_values(cfg)
    vel = velocity_vector(cfg)
    mesh = cfg["mesh_params"]
    end_time = cfg["solver"]["end_time"]

    print(f"\n  Geometry bounds:")
    print(f"    min: ({all_min[0]:.3f}, {all_min[1]:.3f}, {all_min[2]:.3f})")
    print(f"    max: ({all_max[0]:.3f}, {all_max[1]:.3f}, {all_max[2]:.3f})")
    print(f"  Domain box:")
    box = cfg["domain_box"]
    print(f"    min: ({box['min'][0]:.3f}, {box['min'][1]:.3f}, {box['min'][2]:.3f})")
    print(f"    max: ({box['max'][0]:.3f}, {box['max'][1]:.3f}, {box['max'][2]:.3f})")
    print(f"  Mesh:")
    print(f"    Base cell:      {mesh['base_cell_size']} m")
    print(f"    Surface level:  {mesh['surface_level']}")
    print(f"    Edge level:     {mesh['edge_level']}")
    dist_levels = mesh.get('distance_levels', [])
    if dist_levels:
        shells = ", ".join(f"{d*1000:.0f}mm→L{l}" for d, l in dist_levels)
        print(f"    Distance shells: {shells}")
    print(f"    Wake regions:   {len(mesh['refinement_regions'])}")

    # Dry run — stop here
    if dry_run:
        print(f"\n  DRY RUN — would generate: cases/{cfg['case_name']}/")
        print(f"    Velocity:   {cfg['flow']['velocity']:.2f} m/s  U={vec_str(vel)}")
        print(f"    k={k:.5g}  ω={omega:.5g}  νt={nut:.5g}")
        print(f"    Surfaces:   {', '.join(stl_names)}")
        print(f"    Pipeline:   potentialFoam → simpleFoam ({end_time} iters, linearUpwind)")
        return

    # Generate case
    case_dir = project_dir / "cases" / cfg["case_name"]
    print(f"\n{'='*60}")
    print(f"  Generating: cases/{cfg['case_name']}/")
    print(f"  Velocity: {cfg['flow']['velocity']:.2f} m/s | Cell: {mesh['base_cell_size']} m")
    print(f"  Surfaces: {', '.join(stl_names)}")
    print(f"  Pipeline: potentialFoam → simpleFoam ({end_time} iters, linearUpwind)")
    print(f"{'='*60}")

    # Create directories
    for d in ("0", "constant/triSurface", "system"):
        (case_dir / d).mkdir(parents=True, exist_ok=True)

    # Copy STL files
    print(f"\n  STL files:")
    tri_dir = case_dir / "constant" / "triSurface"
    for stem, path in zip(stl_names, stl_paths):
        try:
            n_tri = copy_stl(path, tri_dir / f"{stem}.stl", stem)
            print(f"    ✓ {stem} ({n_tri:,} triangles)")
        except ValueError as e:
            print(f"    ✗ {stem} ERROR: {e}")
            sys.exit(1)

    # Write all OpenFOAM files
    from cfd_gen.writers.constants import write_constant
    from cfd_gen.writers.fields import write_fields
    from cfd_gen.writers.mesh import (
        write_block_mesh_dict,
        write_snappy_hex_mesh_dict,
        write_surface_feature_extract_dict,
    )
    from cfd_gen.writers.scripts import write_scripts
    from cfd_gen.writers.solver import (
        write_control_dict,
        write_decompose_par_dict,
        write_fv_schemes,
        write_fv_solution,
    )

    write_block_mesh_dict(cfg, case_dir)
    write_surface_feature_extract_dict(cfg, case_dir)
    write_snappy_hex_mesh_dict(cfg, case_dir)
    write_control_dict(cfg, case_dir)
    write_fv_schemes(cfg, case_dir)
    write_fv_solution(cfg, case_dir)
    write_decompose_par_dict(cfg, case_dir)
    write_constant(cfg, case_dir)
    write_fields(cfg, case_dir)
    write_scripts(cfg, case_dir)

    # Backup 0/ as 0.orig
    orig_dir = case_dir / "0.orig"
    if orig_dir.exists():
        shutil.rmtree(orig_dir)
    shutil.copytree(case_dir / "0", orig_dir)

    # Save config snapshot (for post-processing)
    (case_dir / "case_config.json").write_text(json.dumps(cfg, indent=2) + "\n")

    print(f"\n  ✓ Case: cases/{cfg['case_name']}/")
    print(f"    cd cases/{cfg['case_name']} && ./Allrun.parallel")
    print()


# ============================================================
# FORCES CLI
# ============================================================

def forces_main() -> None:
    """Entry point for cfd-forces command."""
    parser = argparse.ArgumentParser(
        description="OpenFOAM force post-processing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", "-c", default=None, help="Config JSON for axis info")
    parser.add_argument("--plot", "-p", action="store_true", help="Convergence plot")
    parser.add_argument("--save", "-s", action="store_true", help="Save plot as PNG")
    parser.add_argument("--live", "-l", action="store_true", help="Real-time monitor")
    parser.add_argument("--compare", action="store_true", help="Multi-case comparison")
    parser.add_argument("--check", action="store_true", help="Exit 0 if converged, 1 if not")
    parser.add_argument("--interval", "-i", type=float, default=3, help="Live update interval (s)")
    args = parser.parse_args()

    from cfd_gen.postproc.compare import compare_cases
    from cfd_gen.postproc.forces import (
        check_convergence,
        find_force_files,
        load_axis_config,
        print_summary,
        read_forces,
    )
    from cfd_gen.postproc.plotting import live_monitor, plot_forces

    # Compare mode
    if args.compare:
        compare_cases()
        return

    # Live mode
    if args.live:
        live_monitor(args.config, args.interval)
        return

    # Standard modes
    drag_idx, drag_sign, df_idx, df_sign, drag_axis, df_axis = load_axis_config(args.config)

    files = find_force_files()
    if not files:
        sys.exit("ERROR: No force.dat found. Run from inside the case directory.")

    times, drags, downforces = read_forces(files, drag_idx, drag_sign, df_idx, df_sign)

    # Check mode
    if args.check:
        conv, dp, fp, da, fa = check_convergence(drags, downforces)
        if conv:
            print(f"CONVERGED: drag={da:.3f}N df={fa:.3f}N")
            sys.exit(0)
        else:
            print(f"NOT CONVERGED: drag ±{dp:.3f}% df ±{fp:.3f}%")
            sys.exit(1)

    # Summary
    print_summary(times, drags, downforces, drag_axis, df_axis)

    # Plot
    if args.plot or args.save:
        plot_forces(times, drags, downforces, drag_axis, df_axis, save=args.save)
