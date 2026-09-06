"""FastAPI web server providing REST API and serving the desktop UI."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import math
import os
import re
import shlex
import shutil
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cfd_gen.config import DEFAULT_CONFIG, deep_merge, find_stl, load_config, validate
from cfd_gen.geometry import (
    FIDELITY_PRESETS,
    compute_domain_box,
    compute_mesh_params,
    face_assignments,
    flow_axis_index_sign,
    parse_axis,
    up_axis_index,
)
from cfd_gen.postproc.forces import (
    check_convergence,
    find_force_files,
    is_symmetry_case,
    load_axis_config,
    read_forces,
)
from cfd_gen.stl_utils import stl_info
from cfd_gen.web.ssh_client import ClusterSSHClient

log = logging.getLogger("cfd_gen.web")

app = FastAPI(title="OpenFOAM Case Generator Studio", version="1.0.0")

# Restrict CORS to local origins only to protect credentials and SSH operations
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ssh_client = ClusterSSHClient()
CREDENTIALS_FILE = Path.home() / ".cfd_gen_cluster.json"
PROJECT_ROOT = Path.cwd()

CASE_NAME_REGEX = re.compile(r"^[A-Za-z0-9_-]+$")
JOB_ID_REGEX = re.compile(r"^[0-9]+$")
ALLOWED_LOG_TYPES = {
    "simpleFoam",
    "convergenceMonitor",
    "snappyHexMesh",
    "surfaceFeatureExtract",
    "blockMesh",
    "checkMesh",
    "renumberMesh",
    "potentialFoam",
}


def get_saved_cluster_config() -> dict[str, Any]:
    """Load cached cluster credentials if available."""
    if CREDENTIALS_FILE.exists():
        try:
            return json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "host": "",
        "port": 22,
        "username": "",
        "remote_repo_path": "",
        "save_password": True,
    }


def save_cluster_config(cfg: dict[str, Any]) -> None:
    """Save cluster credentials safely on user machine."""
    try:
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        to_save = dict(cfg)
        if not to_save.get("save_password"):
            to_save.pop("password", None)
        CREDENTIALS_FILE.write_text(json.dumps(to_save, indent=2), encoding="utf-8")
        try:
            CREDENTIALS_FILE.chmod(0o600)
        except Exception:
            pass
    except Exception as exc:
        log.warning("Could not persist cluster credentials: %s", exc)


# -------------------------------------------------------------
# Pydantic Request Models
# -------------------------------------------------------------

class SSHConnectRequest(BaseModel):
    host: str = ""
    port: int = 22
    username: str = ""
    password: Optional[str] = None
    key_path: Optional[str] = None
    remote_repo_path: str = ""
    save_password: bool = True


class JobSubmitRequest(BaseModel):
    case_name: str


class JobCancelRequest(BaseModel):
    job_id: str


class DomainBoxRequest(BaseModel):
    config: dict[str, Any]
    bounds: Optional[dict[str, list[float]]] = None


class GenerateCaseRequest(BaseModel):
    config: dict[str, Any]
    upload_to_cluster: bool = False
    generate_remotely: bool = False
    submit_slurm: bool = False
    generate_locally: bool = True


# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------

@app.post("/api/geometry/domain-box")
async def api_geometry_domain_box(req: DomainBoxRequest) -> dict[str, Any]:
    """Compute and preview the OpenFOAM wind tunnel domain box."""
    cfg = req.config
    merged = deep_merge(DEFAULT_CONFIG, {k: v for k, v in cfg.items() if not k.startswith("_")})

    bounds_tuple = None
    if req.bounds and "min" in req.bounds and "max" in req.bounds:
        bounds_tuple = (req.bounds["min"], req.bounds["max"])
    else:
        # Calculate from active STL files in stl/
        stl_files = cfg.get("stl_files", [])
        all_min = [float("inf")] * 3
        all_max = [float("-inf")] * 3
        for sname in stl_files:
            safe_sname = Path(sname).name
            p = find_stl(PROJECT_ROOT / "stl", safe_sname)
            if p and p.is_file():
                try:
                    _, _, b = stl_info(p)
                    for i in range(3):
                        all_min[i] = min(all_min[i], b[0][i])
                        all_max[i] = max(all_max[i], b[1][i])
                except Exception:
                    pass
        if all_min[0] != float("inf"):
            bounds_tuple = (all_min, all_max)
        else:
            # Default reference geometry bounds (half-model)
            bounds_tuple = ([-0.7, 0.035, -1.8], [0.7, 1.1, 1.2])

    try:
        # If explicit domain_box coordinates are configured, use them for domain
        if isinstance(cfg.get("domain_box"), dict) and "min" in cfg["domain_box"] and "max" in cfg["domain_box"]:
            domain = cfg["domain_box"]
        else:
            domain = compute_domain_box(merged, bounds_tuple)

        flow_idx, _ = flow_axis_index_sign(merged)
        up_idx = up_axis_index(merged)
        lateral_idx = next(i for i in range(3) if i != flow_idx and i != up_idx)
        center_lateral = (bounds_tuple[0][lateral_idx] + bounds_tuple[1][lateral_idx]) / 2.0
        return {
            "domain_box": domain,
            "bounds": {"min": bounds_tuple[0], "max": bounds_tuple[1]},
            "auto_symmetry_plane": round(center_lateral, 4),
            "lateral_axis": "xyz"[lateral_idx],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/cluster/saved-config")
async def api_get_saved_config() -> dict[str, Any]:
    """Get cached connection settings without exposing password in plaintext."""
    cfg = get_saved_cluster_config()
    return {
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 22),
        "username": cfg.get("username", ""),
        "remote_repo_path": cfg.get("remote_repo_path", ""),
        "has_saved_password": bool(cfg.get("password")),
        "key_path": cfg.get("key_path", ""),
    }


@app.post("/api/cluster/connect")
async def api_cluster_connect(req: SSHConnectRequest) -> dict[str, Any]:
    """Connect to the remote HPC cluster and test the environment."""
    saved_cfg = get_saved_cluster_config()
    password_to_use = req.password
    # If no password was provided but one is stored locally for this host/user, use it
    if not password_to_use and saved_cfg.get("password"):
        if (not req.host or req.host == saved_cfg.get("host")) and (not req.username or req.username == saved_cfg.get("username")):
            password_to_use = saved_cfg.get("password")

    try:
        res = await asyncio.to_thread(
            ssh_client.connect,
            host=req.host,
            username=req.username,
            password=password_to_use,
            key_path=req.key_path,
            port=req.port,
            remote_repo_path=req.remote_repo_path,
        )
        save_cluster_config({
            "host": req.host,
            "port": req.port,
            "username": req.username,
            "password": password_to_use if req.save_password else None,
            "key_path": req.key_path,
            "remote_repo_path": req.remote_repo_path,
            "save_password": req.save_password,
        })
        return res
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/cluster/status")
async def api_cluster_status() -> dict[str, Any]:
    """Get active SSH session and SLURM queue status."""
    connected = ssh_client.is_connected
    jobs = []
    if connected:
        try:
            jobs = await asyncio.to_thread(ssh_client.get_slurm_queue)
        except Exception:
            pass

    return {
        "connected": connected,
        "host": ssh_client.host,
        "username": ssh_client.username,
        "remote_repo_path": ssh_client.remote_repo_path,
        "active_jobs": jobs,
    }


@app.post("/api/cluster/disconnect")
async def api_cluster_disconnect() -> dict[str, Any]:
    """Disconnect SSH session."""
    await asyncio.to_thread(ssh_client.disconnect)
    return {"connected": False}


@app.get("/api/config/schema-defaults")
async def api_config_defaults() -> dict[str, Any]:
    """Return default config template and presets for the UI."""
    return {
        "default_config": DEFAULT_CONFIG,
        "fidelity_presets": {
            name: {
                "desc": p.get("desc", ""),
                "cell_estimate": p.get("cell_estimate", ""),
                "n_cells_target": p.get("n_cells_target", 0),
                "runtime_estimate": p.get("runtime_estimate", ""),
            }
            for name, p in FIDELITY_PRESETS.items()
        },
    }


@app.get("/api/config/templates")
async def api_config_templates() -> list[dict[str, Any]]:
    """List available config files in configs/ folder."""
    cfg_dir = PROJECT_ROOT / "configs"
    templates = []
    if cfg_dir.is_dir():
        for p in sorted(cfg_dir.glob("*.json")):
            try:
                content = json.loads(p.read_text(encoding="utf-8"))
                templates.append({
                    "filename": p.name,
                    "case_name": content.get("case_name", p.stem),
                    "stl_files": content.get("stl_files", []),
                    "fidelity": content.get("fidelity", "standard"),
                })
            except Exception:
                templates.append({"filename": p.name, "case_name": p.stem, "stl_files": []})
    return templates


@app.get("/api/config/load-file")
async def api_config_load_file(filename: str = "config.json") -> dict[str, Any]:
    """Load and return JSON content of a specific config file."""
    safe_filename = Path(filename).name
    cfg_dir = (PROJECT_ROOT / "configs").resolve()
    path = (cfg_dir / safe_filename).resolve()
    if not path.is_relative_to(cfg_dir) or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file {safe_filename} not found")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        merged = deep_merge(DEFAULT_CONFIG, {k: v for k, v in content.items() if not k.startswith("_")})
        return {
            "filename": safe_filename,
            "raw_config": content,
            "merged_config": merged,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Error reading config: {exc}")


@app.get("/api/stl/list")
async def api_stl_list() -> list[dict[str, Any]]:
    """List local STL files with geometric bounds and metadata."""
    stl_dir = PROJECT_ROOT / "stl"
    stls = []
    seen_paths = set()
    if stl_dir.is_dir():
        # Deduplicate paths (prevent duplicates on case-insensitive filesystems like Windows)
        all_candidates = sorted(stl_dir.glob("*.stl")) + sorted(stl_dir.glob("*.STL"))
        for p in all_candidates:
            resolved = p.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            try:
                fmt, n_facets, bounds = stl_info(p)
                (xmin, ymin, zmin), (xmax, ymax, zmax) = bounds
                dx = xmax - xmin
                dy = ymax - ymin
                dz = zmax - zmin
                is_likely_mm = max(dx, dy, dz) > 20.0
                stls.append({
                    "filename": p.name,
                    "size_bytes": p.stat().st_size,
                    "format": fmt,
                    "triangles": n_facets,
                    "bounds": {"min": [xmin, ymin, zmin], "max": [xmax, ymax, zmax]},
                    "dimensions": [dx, dy, dz],
                    "is_likely_mm": is_likely_mm,
                })
            except Exception as exc:
                stls.append({"filename": p.name, "size_bytes": p.stat().st_size, "error": str(exc)})
    return stls


@app.get("/api/stl/file/{filename}")
async def api_get_stl_file(filename: str):
    """Serve a local STL file by name."""
    safe_filename = Path(filename).name
    stl_dir = (PROJECT_ROOT / "stl").resolve()
    p = find_stl(stl_dir, safe_filename)
    if not p or not p.is_file() or not p.resolve().is_relative_to(stl_dir):
        raise HTTPException(status_code=404, detail=f"STL file '{safe_filename}' not found")
    return FileResponse(path=p, media_type="application/octet-stream", filename=p.name)


@app.post("/api/stl/upload")
async def api_stl_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload an STL file to local stl/ directory and inspect its bounds."""
    safe_name = Path(file.filename or "uploaded.stl").name
    if not safe_name.lower().endswith(".stl"):
        raise HTTPException(status_code=400, detail="Only .stl files are allowed")

    stl_dir = (PROJECT_ROOT / "stl").resolve()
    stl_dir.mkdir(exist_ok=True)

    dest = (stl_dir / safe_name).resolve()
    if not dest.is_relative_to(stl_dir):
        raise HTTPException(status_code=400, detail="Invalid destination path")

    content = await file.read()
    dest.write_bytes(content)

    try:
        fmt, n_facets, bounds = stl_info(dest)
        (xmin, ymin, zmin), (xmax, ymax, zmax) = bounds
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        return {
            "success": True,
            "filename": safe_name,
            "size_bytes": len(content),
            "format": fmt,
            "triangles": n_facets,
            "bounds": {"min": [xmin, ymin, zmin], "max": [xmax, ymax, zmax]},
            "dimensions": [dx, dy, dz],
            "is_likely_mm": max(dx, dy, dz) > 20.0,
        }
    except Exception as exc:
        return {
            "success": True,
            "filename": safe_name,
            "size_bytes": len(content),
            "warning": f"Uploaded, but geometry inspection failed: {exc}",
        }


@app.post("/api/case/generate-and-submit")
async def api_case_generate_and_submit(req: GenerateCaseRequest) -> dict[str, Any]:
    """Generate OpenFOAM case locally and/or on cluster, and optionally submit SLURM job."""
    cfg = req.config
    case_name = cfg.get("case_name", "").strip()
    if not case_name:
        raise HTTPException(status_code=400, detail="case_name is required")
    if not CASE_NAME_REGEX.match(case_name):
        raise HTTPException(status_code=400, detail="case_name must contain only alphanumeric characters, underscores, and hyphens")

    # 1. Validate config
    merged = deep_merge(DEFAULT_CONFIG, {k: v for k, v in cfg.items() if not k.startswith("_")})
    errors, warnings = validate(merged, PROJECT_ROOT)
    if errors:
        raise HTTPException(status_code=400, detail=f"Config validation errors: {', '.join(errors)}")

    # 2. Save config locally
    cfg_dir = PROJECT_ROOT / "configs"
    cfg_dir.mkdir(exist_ok=True)
    local_cfg_path = cfg_dir / f"{case_name}.json"
    local_cfg_path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")

    local_actions: dict[str, Any] = {}
    cluster_actions: dict[str, Any] = {}

    # 3. Generate locally if requested
    if req.generate_locally:
        from cfd_gen.cli import _do_generate
        try:
            await asyncio.to_thread(_do_generate, local_cfg_path, PROJECT_ROOT, dry_run=False)
            local_actions["generated_locally"] = True
            local_actions["case_path"] = str(PROJECT_ROOT / "cases" / case_name)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Local case generation failed: {exc}")

    # 4. Cluster synchronization and remote execution
    if req.upload_to_cluster:
        if not ssh_client.is_connected:
            raise HTTPException(status_code=400, detail="Not connected to cluster. Please connect via SSH first.")

        remote_repo = ssh_client.remote_repo_path

        # Upload STLs used in this config
        stl_files = cfg.get("stl_files", [])
        uploaded_stls = []
        for sname in stl_files:
            safe_sname = Path(sname).name
            local_stl = find_stl(PROJECT_ROOT / "stl", safe_sname)
            if local_stl and local_stl.is_file():
                remote_stl = f"{remote_repo}/stl/{local_stl.name}"
                await asyncio.to_thread(ssh_client.upload_file, local_stl, remote_stl)
                uploaded_stls.append(sname)

        cluster_actions["uploaded_stls"] = uploaded_stls

        # Upload config JSON
        remote_cfg = f"{remote_repo}/configs/{case_name}.json"
        await asyncio.to_thread(ssh_client.upload_text, json.dumps(cfg, indent=4) + "\n", remote_cfg)
        cluster_actions["uploaded_config"] = remote_cfg

        # Execute setup_case.py remotely
        if req.generate_remotely:
            gen_cmd = f"cd {shlex.quote(remote_repo)} && python3 setup_case.py {shlex.quote(f'configs/{case_name}.json')}"
            code, out, err = await asyncio.to_thread(ssh_client.run_command, gen_cmd, timeout=45)
            cluster_actions["setup_exit_code"] = code
            cluster_actions["setup_output"] = out.strip()
            cluster_actions["setup_error"] = err.strip()

            if code != 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"Remote setup_case.py failed with exit code {code}: {err or out}",
                )

        # Submit SLURM job
        if req.submit_slurm:
            submit_res = await asyncio.to_thread(ssh_client.submit_job, case_name)
            cluster_actions["slurm_submit"] = submit_res

    return {
        "success": True,
        "case_name": case_name,
        "warnings": warnings,
        "local_actions": local_actions,
        "cluster_actions": cluster_actions,
    }


@app.post("/api/case/submit")
async def api_case_submit(req: JobSubmitRequest) -> dict[str, Any]:
    """Submit sbatch for an existing case on the cluster."""
    if not CASE_NAME_REGEX.match(req.case_name):
        raise HTTPException(status_code=400, detail="Invalid case_name")
    if not ssh_client.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to cluster")
    res = await asyncio.to_thread(ssh_client.submit_job, req.case_name)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Failed to submit job"))
    return res


@app.post("/api/case/cancel")
async def api_case_cancel(req: JobCancelRequest) -> dict[str, Any]:
    """Cancel a SLURM job."""
    job_id = str(req.job_id).strip()
    if not JOB_ID_REGEX.match(job_id):
        raise HTTPException(status_code=400, detail="job_id must be numeric")
    if not ssh_client.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to cluster")
    res = await asyncio.to_thread(ssh_client.cancel_job, job_id)
    return res


@app.get("/api/telemetry/forces")
async def api_telemetry_forces(case_name: str) -> dict[str, Any]:
    """Fetch force convergence telemetry with correct axes and symmetry doubling."""
    if not CASE_NAME_REGEX.match(case_name):
        raise HTTPException(status_code=400, detail="Invalid case_name")

    # 1. Resolve axis and symmetry configuration
    local_case = PROJECT_ROOT / "cases" / case_name
    local_cfg = PROJECT_ROOT / "configs" / f"{case_name}.json"
    cfg_to_use = str(local_cfg) if local_cfg.is_file() else None

    drag_idx, drag_sign, df_idx, df_sign, _, _ = load_axis_config(
        config_path=cfg_to_use,
        case_dir=local_case if local_case.is_dir() else None,
    )
    is_sym = is_symmetry_case(
        config_path=cfg_to_use,
        case_dir=local_case if local_case.is_dir() else None,
    )
    sym_scale = 2.0 if is_sym else 1.0

    times: list[float] = []
    drags: list[float] = []
    downforces: list[float] = []

    # 2. Check remote cluster first if connected
    if ssh_client.is_connected:
        remote_forces_dir = f"{ssh_client.remote_repo_path}/cases/{case_name}/postProcessing/forces"
        quoted_dir = shlex.quote(remote_forces_dir)
        cmd = f"ls -1 {quoted_dir} 2>/dev/null | sort -n"
        code, out, _ = await asyncio.to_thread(ssh_client.run_command, cmd, timeout=5)
        if code == 0 and out.strip():
            subdirs = [d.strip() for d in out.strip().splitlines() if d.strip()]
            all_content = []
            for subdir in subdirs:
                if re.match(r"^[0-9\.]+$", subdir):
                    fpath = f"{remote_forces_dir}/{subdir}/force.dat"
                    c = await asyncio.to_thread(ssh_client.read_remote_text, fpath)
                    if c:
                        all_content.append(c)
            if all_content:
                samples: dict[float, tuple[float, float, float]] = {}
                for fc in all_content:
                    segment_started = False
                    for line in fc.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.replace("(", " ").replace(")", " ").split()
                        if len(parts) >= 10:
                            try:
                                vals = [float(v) for v in parts[:10]]
                                if not all(math.isfinite(v) for v in vals):
                                    continue
                                t = vals[0]
                                t_key = round(t, 8)
                                if not segment_started:
                                    samples = {k: s for k, s in samples.items() if k < t_key}
                                    segment_started = True
                                samples[t_key] = (
                                    t,
                                    vals[1 + drag_idx] * drag_sign * sym_scale,
                                    vals[1 + df_idx] * df_sign * sym_scale,
                                )
                            except ValueError:
                                continue
                if samples:
                    sorted_samples = sorted(samples.values())
                    times = [s[0] for s in sorted_samples]
                    drags = [s[1] for s in sorted_samples]
                    downforces = [s[2] for s in sorted_samples]

    # 3. Fall back to local case directory
    if not times and local_case.is_dir():
        files = find_force_files(local_case)
        if files:
            try:
                times, drags, downforces = read_forces(
                    files, drag_idx, drag_sign, df_idx, df_sign
                )
                if is_sym:
                    drags = [d * 2.0 for d in drags]
                    downforces = [df * 2.0 for df in downforces]
            except Exception as exc:
                log.warning("Could not read local forces: %s", exc)

    if not times:
        case_stage = "Generated"
        has_mesh = False
        if local_case.is_dir():
            if (local_case / "constant" / "polyMesh" / "points").is_file():
                has_mesh = True
                case_stage = "Meshed"
            if (local_case / "log.simpleFoam").is_file():
                case_stage = "Solving"
            elif (local_case / "log.snappyHexMesh").is_file():
                case_stage = "Meshing"

        return {
            "has_data": False,
            "case_name": case_name,
            "stage": case_stage,
            "has_mesh": has_mesh,
            "run_command": "./Allrun.parallel",
            "message": f"No force.dat found yet for case '{case_name}'. Current stage: {case_stage}.",
        }

    converged, d_pct, f_pct, d_avg, f_avg = check_convergence(drags, downforces)
    ld_ratio = (f_avg / d_avg) if abs(d_avg) > 1e-3 else 0.0

    # Downsample points if there are thousands, to keep browser rendering butter-smooth
    max_pts = 400
    if len(times) > max_pts:
        step = math.ceil(len(times) / max_pts)
        times_sub = times[::step]
        drags_sub = drags[::step]
        downforces_sub = downforces[::step]
    else:
        times_sub = times
        drags_sub = drags
        downforces_sub = downforces

    return {
        "has_data": True,
        "case_name": case_name,
        "is_symmetry": is_sym,
        "total_iterations": len(times),
        "latest_iteration": times[-1] if times else 0,
        "converged": converged,
        "drag_avg": round(d_avg, 3),
        "downforce_avg": round(f_avg, 3),
        "drag_pct": round(d_pct, 3),
        "downforce_pct": round(f_pct, 3),
        "ld_ratio": round(ld_ratio, 3),
        "series": {
            "iterations": times_sub,
            "drag": [round(v, 3) for v in drags_sub],
            "downforce": [round(v, 3) for v in downforces_sub],
        },
    }


@app.get("/api/telemetry/residuals")
async def api_telemetry_residuals(case_name: str) -> dict[str, Any]:
    """Parse solver residuals from log.simpleFoam or solverInfo.dat with aligned iterations."""
    if not CASE_NAME_REGEX.match(case_name):
        raise HTTPException(status_code=400, detail="Invalid case_name")

    log_content = ""
    if ssh_client.is_connected:
        remote_log = f"{ssh_client.remote_repo_path}/cases/{case_name}/log.simpleFoam"
        log_content = await asyncio.to_thread(ssh_client.read_remote_text, remote_log, max_lines=1200)

    if not log_content:
        local_log = PROJECT_ROOT / "cases" / case_name / "log.simpleFoam"
        if local_log.is_file():
            try:
                with open(local_log, encoding="utf-8", errors="replace") as f:
                    raw_lines = f.readlines()
                    log_content = "".join(raw_lines[-1200:])
            except Exception:
                pass

    if not log_content:
        return {"has_data": False, "message": "No log.simpleFoam found."}

    # Extract initial residuals using regex and store strictly aligned by iteration
    pattern = re.compile(
        r"Solving for (p|Ux|Uy|Uz|k|omega),\s+Initial residual\s+=\s+([0-9\.eE\+\-]+)",
        re.IGNORECASE,
    )
    iter_data: dict[int, dict[str, float]] = {}
    current_iter = 0

    for line in log_content.splitlines():
        if "Time = " in line:
            try:
                current_iter = int(line.split("Time = ")[-1].strip())
            except ValueError:
                pass
        match = pattern.search(line)
        if match and current_iter > 0:
            var = match.group(1)
            if current_iter not in iter_data:
                iter_data[current_iter] = {}
            # Keep the FIRST residual for each variable in this time-step (initial residual)
            if var not in iter_data[current_iter]:
                try:
                    iter_data[current_iter][var] = float(match.group(2))
                except ValueError:
                    pass

    sorted_iters = sorted(iter_data.keys())[-150:]
    all_vars = ["p", "Ux", "Uy", "Uz", "k", "omega"]
    residuals_aligned: dict[str, list[Optional[float]]] = {v: [] for v in all_vars}
    for it in sorted_iters:
        d = iter_data[it]
        for v in all_vars:
            residuals_aligned[v].append(d.get(v))

    return {
        "has_data": len(sorted_iters) > 0,
        "iterations": sorted_iters,
        "residuals": residuals_aligned,
    }


@app.get("/api/telemetry/logs")
async def api_telemetry_logs(case_name: str, log_type: str = "simpleFoam", lines: int = 100) -> dict[str, Any]:
    """Tail log files with strict type whitelisting and length limits."""
    if not CASE_NAME_REGEX.match(case_name):
        raise HTTPException(status_code=400, detail="Invalid case_name")
    if log_type not in ALLOWED_LOG_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported log_type: {log_type}")

    safe_lines = max(1, min(int(lines), 2000))
    filename = f"log.{log_type}"
    content = ""

    if ssh_client.is_connected:
        remote_path = f"{ssh_client.remote_repo_path}/cases/{case_name}/{filename}"
        content = await asyncio.to_thread(ssh_client.read_remote_text, remote_path, max_lines=safe_lines)

    if not content:
        local_file = PROJECT_ROOT / "cases" / case_name / filename
        if local_file.is_file():
            try:
                with open(local_file, encoding="utf-8", errors="replace") as f:
                    raw_lines = f.readlines()
                    content = "".join(raw_lines[-safe_lines:])
            except Exception:
                pass

    return {
        "case_name": case_name,
        "log_type": log_type,
        "content": content or f"No entries in {filename} yet.",
    }


@app.get("/api/cases")
async def api_list_cases() -> list[dict[str, Any]]:
    """List simulation cases from local directory and cluster with comprehensive metadata."""
    cases_dict: dict[str, dict[str, Any]] = {}

    # 1. Local cases
    local_cases_dir = PROJECT_ROOT / "cases"
    if local_cases_dir.is_dir():
        for d in local_cases_dir.iterdir():
            if not d.is_dir() or d.name.startswith("."):
                continue

            case_name = d.name
            st = d.stat()
            mtime_dt = datetime.fromtimestamp(st.st_mtime)
            mtime_str = mtime_dt.strftime("%Y-%m-%d %H:%M")

            # Check case configuration
            cfg_file = d / "case_config.json"
            if not cfg_file.is_file():
                cfg_file = PROJECT_ROOT / "configs" / f"{case_name}.json"

            fidelity = "standard"
            velocity = "16.67"
            flow_dir = "-z"
            n_procs = 32
            stl_name = "--"
            if cfg_file.is_file():
                try:
                    with open(cfg_file, encoding="utf-8") as cf:
                        cd = json.load(cf)
                        fidelity = cd.get("fidelity", "standard")
                        v_val = cd.get("flow", {}).get("velocity", 16.67)
                        velocity = f"{v_val:.1f}" if isinstance(v_val, (int, float)) else str(v_val)
                        flow_dir = cd.get("flow", {}).get("direction", "-z")
                        n_procs = cd.get("parallel", {}).get("n_procs", 32)
                        stls = cd.get("stl_files", [])
                        if stls:
                            stl_name = Path(stls[0]).name
                except Exception:
                    pass

            status = "Generated"
            converged = False
            has_forces = False
            has_residuals = False
            has_mesh = (d / "constant" / "polyMesh" / "points").is_file()
            latest_iter: Optional[int] = None
            downforce_val: Optional[float] = None
            drag_val: Optional[float] = None
            ld_val: Optional[float] = None

            # Check forces
            force_files = find_force_files(d)
            if force_files:
                has_forces = True
                try:
                    drag_idx, drag_sign, df_idx, df_sign, _, _ = load_axis_config(
                        config_path=str(cfg_file) if cfg_file.is_file() else None,
                        case_dir=d,
                    )
                    is_sym = is_symmetry_case(
                        config_path=str(cfg_file) if cfg_file.is_file() else None,
                        case_dir=d,
                    )
                    times, drags, downforces = read_forces(
                        force_files, drag_idx, drag_sign, df_idx, df_sign
                    )
                    if is_sym:
                        drags = [drv * 2.0 for drv in drags]
                        downforces = [dfv * 2.0 for dfv in downforces]
                    if times:
                        latest_iter = int(times[-1])
                        c_conv, _, _, d_avg, f_avg = check_convergence(drags, downforces)
                        converged = c_conv
                        downforce_val = round(f_avg, 2)
                        drag_val = round(d_avg, 2)
                        ld_val = round(f_avg / d_avg, 2) if abs(d_avg) > 1e-3 else None
                        status = "Converged" if converged else "Solving"
                except Exception:
                    pass

            # Check log.simpleFoam
            log_simple = d / "log.simpleFoam"
            if log_simple.is_file():
                has_residuals = True
                try:
                    with open(log_simple, encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                        tail = "".join(lines[-15:])
                        if "End" in tail or "Finalising parallel run" in tail:
                            status = "Completed" if not converged else "Converged"
                        elif status != "Converged":
                            status = "Solving"
                except Exception:
                    pass

            # Check mesher stage if still generated
            if status == "Generated":
                log_snappy = d / "log.snappyHexMesh"
                if log_snappy.is_file():
                    try:
                        with open(log_snappy, encoding="utf-8", errors="replace") as f:
                            lines = f.readlines()
                            tail = "".join(lines[-15:])
                            if "End" in tail or "Finalising parallel run" in tail:
                                status = "Meshed"
                            else:
                                status = "Meshing"
                    except Exception:
                        status = "Meshed"
                elif has_mesh:
                    status = "Meshed"

            cases_dict[case_name] = {
                "name": case_name,
                "location": "Local",
                "path": f"cases/{case_name}",
                "modified": mtime_str,
                "modified_ts": st.st_mtime,
                "status": status,
                "fidelity": fidelity,
                "velocity": velocity,
                "direction": flow_dir,
                "n_procs": n_procs,
                "stl_name": stl_name,
                "has_forces": has_forces,
                "has_residuals": has_residuals,
                "has_mesh": has_mesh,
                "latest_iter": latest_iter,
                "converged": converged,
                "downforce": downforce_val,
                "drag": drag_val,
                "ld_ratio": ld_val,
            }

    # 2. Remote cases if cluster connected
    if ssh_client.is_connected:
        try:
            remote_cases = await asyncio.to_thread(ssh_client.list_remote_cases)
            for rc in remote_cases:
                cname = rc["name"]
                if cname in cases_dict:
                    cases_dict[cname]["location"] = "Local & Cluster"
                else:
                    cases_dict[cname] = {
                        "name": cname,
                        "location": "Cluster",
                        "path": f"{ssh_client.remote_repo_path}/cases/{cname}",
                        "modified": rc.get("modified", "--"),
                        "modified_ts": 0.0,
                        "status": "Cluster Job",
                        "fidelity": "--",
                        "velocity": "--",
                        "direction": "--",
                        "n_procs": "--",
                        "stl_name": "--",
                        "has_forces": True,
                        "has_residuals": True,
                        "has_mesh": True,
                        "latest_iter": None,
                        "converged": False,
                        "downforce": None,
                        "drag": None,
                        "ld_ratio": None,
                    }
        except Exception as exc:
            log.warning("Could not list remote cases: %s", exc)

    return sorted(cases_dict.values(), key=lambda x: x.get("modified_ts", 0.0), reverse=True)


@app.delete("/api/cases/{case_name}")
async def api_case_delete(case_name: str) -> dict[str, Any]:
    """Delete a simulation case directory."""
    if not CASE_NAME_REGEX.match(case_name):
        raise HTTPException(status_code=400, detail="Invalid case_name")

    target_dir = PROJECT_ROOT / "cases" / case_name
    deleted = False
    if target_dir.is_dir() and target_dir.resolve().is_relative_to(PROJECT_ROOT / "cases"):
        shutil.rmtree(target_dir)
        deleted = True

    if ssh_client.is_connected:
        quoted_remote = shlex.quote(f"{ssh_client.remote_repo_path}/cases/{case_name}")
        code, _, _ = await asyncio.to_thread(ssh_client.run_command, f"rm -rf {quoted_remote}")
        if code == 0:
            deleted = True

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Case '{case_name}' not found")

    return {"success": True, "case_name": case_name}


# -------------------------------------------------------------
# Mount Static Frontend
# -------------------------------------------------------------

STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main() -> None:
    """CLI launcher for the web server."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Launch OpenFOAM Case Generator Studio.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()

    import socket
    import urllib.request

    def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0

    target_port = args.port
    if is_port_in_use(target_port, args.host):
        try:
            req = urllib.request.urlopen(f"http://{args.host}:{target_port}/api/config/schema-defaults", timeout=1)
            if req.status == 200:
                url = f"http://{args.host}:{target_port}"
                print("\n" + "=" * 60)
                print("  [RapidAero] CFD Studio is already running!")
                print(f"  Access dashboard at: {url}")
                print("=" * 60 + "\n")
                if not args.no_browser:
                    webbrowser.open(url)
                return
        except Exception:
            pass

        while is_port_in_use(target_port, args.host):
            target_port += 1
        print(f"[*] Port {args.port} was busy. Switched to next available port: {target_port}")
        args.port = target_port

    import uvicorn

    url = f"http://{args.host}:{args.port}"
    print("\n" + "=" * 60)
    cfg = get_saved_cluster_config()
    target = cfg.get("host") or "Not configured (set in Web UI)"
    print(f"  Cluster target: {target}")
    print(f"  Listening on:   {url}")
    print("=" * 60 + "\n")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
