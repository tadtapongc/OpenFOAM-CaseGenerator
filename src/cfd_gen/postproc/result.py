"""Structured case results — stable machine-readable aggregation.

Aggregates the information available for a completed (or partially
completed) OpenFOAM case into one typed object with a fixed JSON schema:

* case config snapshot (case_config.json) — flow conditions, fluid
  properties, force reference values, output axes
* force post-processing output (postProcessing/forces/*/force.dat) —
  parsed with the existing cfd_gen.postproc.forces utilities

Only values that can be derived reliably from the case config and output
are populated; unknown values remain None (JSON null).  Nothing is
invented — e.g. yaw/AoA are not part of the current config schema, so
they stay null.

The JSON output is deterministic (fixed key order, no timestamps) and is
intended for automation, dashboards, and external integrations.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cfd_gen.postproc.forces import (
    axis_index_sign,
    check_convergence,
    find_force_files,
    read_forces,
)

SCHEMA_VERSION = "1.0"

# Minimum iterations before force averages are considered reliable —
# matches the minimum window of check_convergence().
MIN_RELIABLE_ITERS = 20

# Status values
STATUS_COMPLETED = "completed"    # force data present and converged
STATUS_INCOMPLETE = "incomplete"  # force data present but not converged / too few iterations
STATUS_NO_DATA = "no_data"        # no force data found


# ============================================================
# DATA MODEL
# ============================================================

@dataclass
class Conditions:
    """Flow conditions for the case (from the config snapshot)."""

    velocity_ms: float | None = None
    yaw_deg: float | None = None
    aoa_deg: float | None = None


@dataclass
class Forces:
    """Aerodynamic forces in Newtons (averaged over the last 200 iterations)."""

    drag_N: float | None = None
    downforce_N: float | None = None
    lift_N: float | None = None


@dataclass
class Coefficients:
    """Force coefficients (drag, lift) and lift-to-drag ratio."""

    Cd: float | None = None
    Cl: float | None = None
    L_over_D: float | None = None


@dataclass
class Convergence:
    """Force convergence state (±0.5% over the last 200 iterations)."""

    converged: bool | None = None
    force_variation_percent: float | None = None


@dataclass
class CaseResult:
    """Structured result for one OpenFOAM case (schema 1.0)."""

    case: str
    status: str
    conditions: Conditions = field(default_factory=Conditions)
    forces: Forces = field(default_factory=Forces)
    coefficients: Coefficients = field(default_factory=Coefficients)
    convergence: Convergence = field(default_factory=Convergence)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the stable schema (fixed key order)."""
        return {
            "schema_version": self.schema_version,
            "case": self.case,
            "status": self.status,
            "conditions": asdict(self.conditions),
            "forces": asdict(self.forces),
            "coefficients": asdict(self.coefficients),
            "convergence": asdict(self.convergence),
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON (deterministic key order, trailing newline)."""
        return json.dumps(self.to_dict(), indent=indent) + "\n"


# ============================================================
# EXTRACTION
# ============================================================

def _as_float(value: Any) -> float | None:
    """Return value as float if it is a finite real number, else None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _round(value: float | None, ndigits: int) -> float | None:
    """Round for stable output; None passes through."""
    return None if value is None else round(value, ndigits)


def _load_case_config(case_dir: Path) -> dict[str, Any]:
    """Load the case's resolved config snapshot ({} if missing/invalid)."""
    path = case_dir / "case_config.json"
    try:
        with open(path) as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def _output_axes(cfg: dict[str, Any]) -> tuple[str, str, int, int, int, int]:
    """Resolve drag/downforce axes from the config (defaults: -z / -y).

    Mirrors the axis resolution used by compare.py; falls back to the
    defaults if the config holds an invalid axis string.
    """
    outputs = cfg.get("outputs") or {}
    drag_axis = outputs.get("drag_axis") or cfg.get("drag_axis", "-z")
    df_axis = outputs.get("downforce_axis") or cfg.get("downforce_axis", "-y")
    try:
        drag_idx, drag_sign = axis_index_sign(drag_axis)
        df_idx, df_sign = axis_index_sign(df_axis)
    except (KeyError, AttributeError):
        drag_axis, df_axis = "-z", "-y"
        drag_idx, drag_sign = axis_index_sign(drag_axis)
        df_idx, df_sign = axis_index_sign(df_axis)
    return drag_axis, df_axis, drag_idx, drag_sign, df_idx, df_sign


def _read_force_series(
    case_dir: Path,
    drag_idx: int,
    drag_sign: int,
    df_idx: int,
    df_sign: int,
) -> tuple[list[float], list[float], list[float]]:
    """Read force data via the existing parsers; empty on any failure."""
    try:
        files = find_force_files(case_dir)
        times, drags, downforces = read_forces(
            files, drag_idx, drag_sign, df_idx, df_sign
        )
        return times, drags, downforces
    except Exception:
        return [], [], []


def _lift_from_downforce(downforce: float | None, df_axis: str) -> float | None:
    """Lift is the +y force.

    Derivable exactly when the downforce axis lies on the y axis
    (sign flip for -y).  Returns None otherwise — no data is invented.
    """
    if downforce is None:
        return None
    axis = str(df_axis).strip().lower()
    if axis in ("+y", "y"):
        return downforce
    if axis == "-y":
        return -downforce
    return None


def _compute_coefficients(
    rho: float | None,
    velocity: float | None,
    a_ref: float | None,
    drag: float | None,
    downforce: float | None,
    lift: float | None,
) -> Coefficients:
    """Compute Cd / Cl / L/D from forces + case config (None if not derivable)."""
    coeffs = Coefficients()

    q_dyn_a_ref: float | None = None
    if (
        rho is not None and rho > 0
        and velocity is not None and velocity > 0
        and a_ref is not None and a_ref > 0
    ):
        q_dyn_a_ref = 0.5 * rho * velocity * velocity * a_ref

    if q_dyn_a_ref is not None:
        if drag is not None:
            coeffs.Cd = _round(drag / q_dyn_a_ref, 4)
        if lift is not None:
            coeffs.Cl = _round(lift / q_dyn_a_ref, 4)

    if drag is not None and downforce is not None and drag != 0:
        coeffs.L_over_D = _round(abs(downforce / drag), 4)

    return coeffs


def build_result(case_dir: str | Path) -> CaseResult:
    """Aggregate a case's config + force output into a CaseResult.

    Never raises for missing or invalid post-processing output — unknown
    values stay None.  Force values are the averages over the last 200
    iterations (same criterion as cfd-forces --check); with fewer than
    20 iterations the averages are not reliable and stay None.
    """
    case_dir = Path(case_dir)
    cfg = _load_case_config(case_dir)

    case_name = cfg.get("case_name") or case_dir.resolve().name

    # --- conditions (from the config snapshot) ---
    flow = cfg.get("flow") or {}
    conditions = Conditions(velocity_ms=_as_float(flow.get("velocity")))
    # yaw_deg / aoa_deg: not part of the current config schema -> remain None

    # --- forces (reuses the existing force parsers) ---
    drag_axis, df_axis, drag_idx, drag_sign, df_idx, df_sign = _output_axes(cfg)
    times, drags, downforces = _read_force_series(
        case_dir, drag_idx, drag_sign, df_idx, df_sign
    )

    forces = Forces()
    convergence = Convergence()
    status = STATUS_NO_DATA
    raw_drag: float | None = None
    raw_downforce: float | None = None

    if times:
        try:
            converged, d_pct, f_pct, d_avg, f_avg = check_convergence(
                drags, downforces
            )
        except Exception:
            converged, d_pct, f_pct, d_avg, f_avg = False, None, None, None, None

        convergence.converged = bool(converged)
        if (
            d_avg is not None and f_avg is not None
            and len(times) >= MIN_RELIABLE_ITERS
        ):
            raw_drag, raw_downforce = d_avg, f_avg
            forces.drag_N = _round(d_avg, 4)
            forces.downforce_N = _round(f_avg, 4)
            forces.lift_N = _round(_lift_from_downforce(f_avg, df_axis), 4)
            if d_pct is not None and f_pct is not None:
                convergence.force_variation_percent = _round(
                    max(d_pct, f_pct), 3
                )
            status = STATUS_COMPLETED if converged else STATUS_INCOMPLETE
        else:
            status = STATUS_INCOMPLETE

    # --- coefficients (forces + case config) ---
    fluid = cfg.get("fluid") or {}
    refs = cfg.get("force_refs") or {}
    coefficients = _compute_coefficients(
        rho=_as_float(fluid.get("rho")),
        velocity=conditions.velocity_ms,
        a_ref=_as_float(refs.get("Aref")),
        drag=raw_drag,
        downforce=raw_downforce,
        lift=_lift_from_downforce(raw_downforce, df_axis),
    )

    return CaseResult(
        case=str(case_name),
        status=status,
        conditions=conditions,
        forces=forces,
        coefficients=coefficients,
        convergence=convergence,
    )
