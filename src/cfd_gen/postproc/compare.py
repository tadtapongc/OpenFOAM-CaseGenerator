"""Multi-case comparison."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from cfd_gen.postproc.forces import (
    axis_index_sign,
    check_convergence,
    find_force_files,
    read_forces,
)


def compare_cases(cases_dir: Path | None = None) -> None:
    """Compare forces across all cases in CASES/ directory."""
    if cases_dir is None:
        # Try script parent, then cwd
        candidates = [Path.cwd() / "CASES", Path(__file__).resolve().parent.parent.parent.parent / "CASES"]
        cases_dir = next((d for d in candidates if d.exists()), None)

    if not cases_dir or not cases_dir.exists():
        sys.exit("ERROR: CASES/ directory not found")

    case_dirs = sorted(
        [d for d in cases_dir.iterdir() if d.is_dir() and (d / "case_config.json").exists()],
        key=lambda d: d.name,
    )
    if not case_dirs:
        sys.exit("ERROR: No cases found in CASES/")

    results = []
    for d in case_dirs:
        with open(d / "case_config.json") as f:
            cfg = json.load(f)

        # Support both config formats
        outputs = cfg.get("outputs", {})
        drag_axis = outputs.get("drag_axis") or cfg.get("drag_axis", "-z")
        df_axis = outputs.get("downforce_axis") or cfg.get("downforce_axis", "-y")
        di, ds = axis_index_sign(drag_axis)
        fi, fs = axis_index_sign(df_axis)

        files = find_force_files(d)
        if not files:
            results.append({
                "name": cfg.get("case_name", d.name),
                "drag": None, "df": None, "ld": None, "iters": 0, "conv": False,
            })
            continue

        times, drags, dfs = read_forces(files, di, ds, fi, fs)
        if not times:
            results.append({
                "name": cfg.get("case_name", d.name),
                "drag": None, "df": None, "ld": None, "iters": 0, "conv": False,
            })
            continue

        conv, dp, fp, da, fa = check_convergence(drags, dfs)
        ld = abs(fa / da) if da != 0 else 0

        results.append({
            "name": cfg.get("case_name", d.name),
            "drag": da, "df": fa, "ld": ld,
            "iters": len(times), "conv": conv, "dp": dp, "fp": fp,
        })

    # Print table
    print(f"\n{'='*75}")
    print(f"  {'Case':<16} {'Drag [N]':>10} {'Downforce [N]':>14} {'L/D':>6} {'Iters':>6} {'Status':<12}")
    print(f"  {'-'*16} {'-'*10} {'-'*14} {'-'*6} {'-'*6} {'-'*12}")
    for r in results:
        d_str = f"{r['drag']:.2f}" if r["drag"] is not None else "—"
        f_str = f"{r['df']:.2f}" if r["df"] is not None else "—"
        ld_str = f"{r['ld']:.2f}" if r["ld"] is not None else "—"
        status = "✓ converged" if r["conv"] else ("running" if r["iters"] > 0 else "no data")
        print(f"  {r['name']:<16} {d_str:>10} {f_str:>14} {ld_str:>6} {r['iters']:>6} {status:<12}")
    print(f"{'='*75}\n")
