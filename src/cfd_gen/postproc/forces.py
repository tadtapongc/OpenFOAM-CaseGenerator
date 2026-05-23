"""Force reading and convergence checking."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

# ============================================================
# AXIS UTILITIES
# ============================================================

AXIS_MAP = {
    "+x": (1, 0, 0), "x": (1, 0, 0), "-x": (-1, 0, 0),
    "+y": (0, 1, 0), "y": (0, 1, 0), "-y": (0, -1, 0),
    "+z": (0, 0, 1), "z": (0, 0, 1), "-z": (0, 0, -1),
}


def axis_index_sign(axis_str: str) -> tuple[int, int]:
    """Return (index, sign) for axis string."""
    vec = AXIS_MAP[axis_str.strip().lower()]
    for i, v in enumerate(vec):
        if v != 0:
            return i, int(v)
    return 0, 1


def load_axis_config(config_path: str | None = None) -> tuple[int, int, int, int, str, str]:
    """Load drag/downforce axis from config or case_config.json.

    Returns:
        (drag_idx, drag_sign, df_idx, df_sign, drag_axis_str, df_axis_str)
    """
    cfg = None
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            cfg = json.load(f)
    elif Path("case_config.json").exists():
        with open("case_config.json") as f:
            cfg = json.load(f)

    # Support both old and new config formats
    if cfg:
        outputs = cfg.get("outputs", {})
        drag_axis = outputs.get("drag_axis") or cfg.get("drag_axis", "-z")
        df_axis = outputs.get("downforce_axis") or cfg.get("downforce_axis", "-y")
    else:
        drag_axis = "-z"
        df_axis = "-y"

    drag_idx, drag_sign = axis_index_sign(drag_axis)
    df_idx, df_sign = axis_index_sign(df_axis)
    return drag_idx, drag_sign, df_idx, df_sign, drag_axis, df_axis


# ============================================================
# FILE DISCOVERY
# ============================================================

def _dir_time(p: Path) -> float:
    try:
        return float(p.name)
    except ValueError:
        return 0.0


def find_force_files(base_dir: str | Path | None = None) -> list[Path]:
    """Find force.dat files across time directories."""
    base = Path(base_dir) if base_dir else Path(".")
    all_files: list[Path] = []

    forces_dir = base / "postProcessing" / "forces"
    if forces_dir.exists():
        for d in sorted(forces_dir.glob("*/"), key=_dir_time):
            f = d / "force.dat"
            if f.exists():
                all_files.append(f)

    # Processor fallback (parallel live data)
    if not all_files:
        for proc_dir in sorted(base.glob("processor*")):
            pf = proc_dir / "postProcessing" / "forces"
            if pf.exists():
                for d in sorted(pf.glob("*/"), key=_dir_time):
                    f = d / "force.dat"
                    if f.exists():
                        all_files.append(f)
                break

    return all_files


# ============================================================
# DATA READING
# ============================================================

def read_forces(
    files: list[Path] | Path,
    drag_idx: int,
    drag_sign: int,
    df_idx: int,
    df_sign: int,
) -> tuple[list[float], list[float], list[float]]:
    """Parse force.dat files.

    Returns:
        (times, drags, downforces)
    """
    times, drags, downforces = [], [], []
    seen: set[float] = set()

    if not isinstance(files, (list, tuple)):
        files = [files]

    for path in files:
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.replace("(", "").replace(")", "").split()
                    if len(parts) < 10:
                        continue
                    t = float(parts[0])
                    t_key = round(t, 8)
                    if t_key in seen:
                        continue
                    seen.add(t_key)
                    pressure = [float(parts[i]) for i in (1, 2, 3)]
                    viscous = [float(parts[i]) for i in (4, 5, 6)]
                    porous = [float(parts[i]) for i in (7, 8, 9)]
                    total = [pressure[j] + viscous[j] + porous[j] for j in range(3)]
                    times.append(t)
                    drags.append(total[drag_idx] * drag_sign)
                    downforces.append(total[df_idx] * df_sign)
        except (OSError, ValueError):
            pass

    if times:
        combined = sorted(zip(times, drags, downforces))
        times = [c[0] for c in combined]
        drags = [c[1] for c in combined]
        downforces = [c[2] for c in combined]

    return times, drags, downforces


# ============================================================
# CONVERGENCE CHECK
# ============================================================

def check_convergence(
    drags: list[float],
    downforces: list[float],
    window: int = 100,
    threshold: float = 0.5,
) -> tuple[bool, float, float, float, float]:
    """Check force convergence.

    Returns:
        (converged, drag_pct, df_pct, drag_avg, df_avg)

    Threshold is 0.5% — slightly relaxed for robustness.
    """
    if len(drags) < window:
        window = len(drags)
    if window < 20:
        return False, 100.0, 100.0, 0.0, 0.0

    d_win = drags[-window:]
    f_win = downforces[-window:]
    d_avg = statistics.mean(d_win)
    f_avg = statistics.mean(f_win)
    d_std = statistics.stdev(d_win)
    f_std = statistics.stdev(f_win)

    d_pct = (d_std / abs(d_avg) * 100) if d_avg != 0 else 100.0
    f_pct = (f_std / abs(f_avg) * 100) if f_avg != 0 else 100.0

    return (d_pct < threshold and f_pct < threshold), d_pct, f_pct, d_avg, f_avg


# ============================================================
# SUMMARY
# ============================================================

def print_summary(
    times: list[float],
    drags: list[float],
    downforces: list[float],
    drag_axis: str,
    df_axis: str,
) -> bool:
    """Print force summary with convergence info. Returns True if converged."""
    if not times:
        print("  No force data found.")
        return False

    converged, d_pct, f_pct, d_avg, f_avg = check_convergence(drags, downforces)
    ld = abs(f_avg / d_avg) if d_avg != 0 else 0

    print(f"\n{'='*55}")
    print(f"  FORCE RESULTS ({len(times)} iterations)")
    print(f"{'='*55}")
    print(f"  Drag ({drag_axis}):      {drags[-1]:>10.3f} N")
    print(f"  Downforce ({df_axis}):  {downforces[-1]:>10.3f} N")
    if drags[-1] != 0:
        print(f"  L/D:              {abs(downforces[-1]/drags[-1]):>10.3f}")
    print(f"{'-'*55}")
    print(f"  Averaged (last 100):")
    print(f"    Drag:       {d_avg:>10.3f} N  (±{d_pct:.3f}%)")
    print(f"    Downforce:  {f_avg:>10.3f} N  (±{f_pct:.3f}%)")
    print(f"    L/D:        {ld:>10.3f}")
    print(f"  Status: {'✓ CONVERGED' if converged else '✗ NOT CONVERGED'}")
    print(f"{'='*55}")
    print(f"  Note: If half-model (symmetry), multiply by 2.\n")

    return converged
