"""Residual reading utilities."""

from __future__ import annotations

from pathlib import Path


def _dir_time(p: Path) -> float:
    try:
        return float(p.name)
    except ValueError:
        return 0.0


def find_residual_files(base_dir: str | Path | None = None) -> list[Path]:
    """Find solverInfo.dat files."""
    base = Path(base_dir) if base_dir else Path(".")
    all_files: list[Path] = []

    res_dir = base / "postProcessing" / "residuals"
    if res_dir.exists():
        for d in sorted(res_dir.glob("*/"), key=_dir_time):
            f = d / "solverInfo.dat"
            if f.exists():
                all_files.append(f)

    if not all_files:
        for proc_dir in sorted(base.glob("processor*")):
            pr = proc_dir / "postProcessing" / "residuals"
            if pr.exists():
                for d in sorted(pr.glob("*/"), key=_dir_time):
                    f = d / "solverInfo.dat"
                    if f.exists():
                        all_files.append(f)
                break

    return all_files


def read_residuals(files: list[Path]) -> tuple[dict[str, list[float | None]], list[str]]:
    """Read solverInfo.dat files.

    Returns:
        (data_dict, headers)
    """
    data: dict[str, list[float | None]] = {}
    headers: list[str] = []
    seen: set[float] = set()

    for path in files:
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("#"):
                        if "Time" in line:
                            headers = line.strip("# \n").split()
                        continue
                    if not line.strip() or not headers:
                        continue
                    parts = line.split()
                    try:
                        t = float(parts[0])
                    except (ValueError, IndexError):
                        continue
                    t_key = round(t, 8)
                    if t_key in seen:
                        continue
                    seen.add(t_key)
                    for i, h in enumerate(headers):
                        if i < len(parts):
                            try:
                                val: float | None = float(parts[i])
                            except ValueError:
                                val = None
                        else:
                            val = None
                        data.setdefault(h, []).append(val)
        except (OSError, ValueError):
            pass

    if "Time" in data and data["Time"]:
        sort_idx = sorted(range(len(data["Time"])), key=lambda i: data["Time"][i] or 0)
        for key in data:
            data[key] = [data[key][i] for i in sort_idx]

    return data, headers
