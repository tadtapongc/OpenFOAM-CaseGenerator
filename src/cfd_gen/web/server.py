"""FastAPI web server providing REST API and serving the desktop UI."""

from __future__ import annotations

import argparse
import io
import json
import logging
import math
import os
import re
import sys
import webbrowser
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
from cfd_gen.postproc.forces import check_convergence, find_force_files, read_forces
from cfd_gen.stl_utils import stl_info
from cfd_gen.web.ssh_client import ClusterSSHClient

log = logging.getLogger("cfd_gen.web")

app = FastAPI(title="OpenFOAM Case Generator Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ssh_client = ClusterSSHClient()
CREDENTIALS_FILE = Path.home() / ".cfd_gen_cluster.json"
PROJECT_ROOT = Path.cwd()


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
        # Never store password if user opted out
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
    upload_to_cluster: bool = True
    generate_remotely: bool = True
    submit_slurm: bool = False


# -------------------------------------------------------------
# REST API Endpoints
# -------------------------------------------------------------

@app.post("/api/geometry/domain-box")
async def api_geometry_domain_box(req: DomainBoxRequest) -> dict[str, Any]:
    """Compute and preview the OpenFOAM wind tunnel domain box."""
    cfg = req.config
    merged = deep_merge(DEFAULT_CONFIG, {k: v for k, v in cfg.items() if not k.startswith("_")})

    # If explicit domain_box coordinates are configured
    if isinstance(cfg.get("domain_box"), dict) and "min" in cfg["domain_box"] and "max" in cfg["domain_box"]:
        return {"domain_box": cfg["domain_box"]}

    bounds_tuple = None
    if req.bounds and "min" in req.bounds and "max" in req.bounds:
        bounds_tuple = (req.bounds["min"], req.bounds["max"])
    else:
        # Calculate from active STL files in stl/
        stl_files = cfg.get("stl_files", [])
        all_min = [float("inf")] * 3
        all_max = [float("-inf")] * 3
        for sname in stl_files:
            p = find_stl(PROJECT_ROOT / "stl", sname)
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
    """Get cached connection settings (without exposing plain password unnecessarily)."""
    cfg = get_saved_cluster_config()
    return {
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 22),
        "username": cfg.get("username", ""),
        "remote_repo_path": cfg.get("remote_repo_path", ""),
        "has_saved_password": bool(cfg.get("password")),
        "saved_password": cfg.get("password", ""),
        "key_path": cfg.get("key_path", ""),
    }


@app.post("/api/cluster/connect")
async def api_cluster_connect(req: SSHConnectRequest) -> dict[str, Any]:
    """Connect to the remote HPC cluster and test the environment."""
    try:
        res = ssh_client.connect(
            host=req.host,
            username=req.username,
            password=req.password,
            key_path=req.key_path,
            port=req.port,
            remote_repo_path=req.remote_repo_path,
        )
        save_cluster_config({
            "host": req.host,
            "port": req.port,
            "username": req.username,
            "password": req.password if req.save_password else None,
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
            jobs = ssh_client.get_slurm_queue()
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
    ssh_client.disconnect()
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
    path = PROJECT_ROOT / "configs" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Config file {filename} not found")
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
        # Also compute merged config with defaults
        merged = deep_merge(DEFAULT_CONFIG, {k: v for k, v in content.items() if not k.startswith("_")})
        return {
            "filename": filename,
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
    if stl_dir.is_dir():
        for p in sorted(stl_dir.glob("*.stl")) + sorted(stl_dir.glob("*.STL")):
            try:
                fmt, n_facets, bounds = stl_info(p)
                (xmin, ymin, zmin), (xmax, ymax, zmax) = bounds
                dx = xmax - xmin
                dy = ymax - ymin
                dz = zmax - zmin
                # Detect millimeter scale: FSAE car/wing is typically 0.2m - 3.5m.
                # If bounding box is > 10m or > 200, it's almost certainly in millimeters!
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
    stl_dir = PROJECT_ROOT / "stl"
    p = find_stl(stl_dir, filename)
    if not p or not p.is_file():
        raise HTTPException(status_code=404, detail=f"STL file '{filename}' not found")
    return FileResponse(path=p, media_type="application/octet-stream", filename=p.name)


@app.post("/api/stl/upload")
async def api_stl_upload(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload an STL file to local stl/ directory and inspect its bounds."""
    stl_dir = PROJECT_ROOT / "stl"
    stl_dir.mkdir(exist_ok=True)

    dest = stl_dir / file.filename
    content = await file.read()
    dest.write_bytes(content)

    try:
        fmt, n_facets, bounds = stl_info(dest)
        (xmin, ymin, zmin), (xmax, ymax, zmax) = bounds
        dx, dy, dz = xmax - xmin, ymax - ymin, zmax - zmin
        return {
            "success": True,
            "filename": file.filename,
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
            "filename": file.filename,
            "size_bytes": len(content),
            "warning": f"Uploaded, but geometry inspection failed: {exc}",
        }


@app.post("/api/case/generate-and-submit")
async def api_case_generate_and_submit(req: GenerateCaseRequest) -> dict[str, Any]:
    """Generate OpenFOAM case and optionally transfer to cluster and submit SLURM job."""
    cfg = req.config
    case_name = cfg.get("case_name", "").strip()
    if not case_name:
        raise HTTPException(status_code=400, detail="case_name is required")

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

    cluster_actions: dict[str, Any] = {}

    # 3. Cluster synchronization and execution
    if req.upload_to_cluster:
        if not ssh_client.is_connected:
            raise HTTPException(status_code=400, detail="Not connected to cluster. Please connect via SSH first.")

        remote_repo = ssh_client.remote_repo_path

        # Upload STLs used in this config
        stl_files = cfg.get("stl_files", [])
        uploaded_stls = []
        for sname in stl_files:
            local_stl = find_stl(PROJECT_ROOT / "stl", sname)
            if local_stl and local_stl.is_file():
                remote_stl = f"{remote_repo}/stl/{local_stl.name}"
                ssh_client.upload_file(local_stl, remote_stl)
                uploaded_stls.append(sname)

        cluster_actions["uploaded_stls"] = uploaded_stls

        # Upload config JSON
        remote_cfg = f"{remote_repo}/configs/{case_name}.json"
        ssh_client.upload_text(json.dumps(cfg, indent=4) + "\n", remote_cfg)
        cluster_actions["uploaded_config"] = remote_cfg

        # Execute setup_case.py remotely
        if req.generate_remotely:
            gen_cmd = f"cd '{remote_repo}' && python3 setup_case.py 'configs/{case_name}.json'"
            code, out, err = ssh_client.run_command(gen_cmd, timeout=45)
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
            submit_res = ssh_client.submit_job(case_name)
            cluster_actions["slurm_submit"] = submit_res

    return {
        "success": True,
        "case_name": case_name,
        "warnings": warnings,
        "cluster_actions": cluster_actions,
    }


@app.post("/api/case/submit")
async def api_case_submit(req: JobSubmitRequest) -> dict[str, Any]:
    """Submit sbatch for an existing case on the cluster."""
    if not ssh_client.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to cluster")
    res = ssh_client.submit_job(req.case_name)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Failed to submit job"))
    return res


@app.post("/api/case/cancel")
async def api_case_cancel(req: JobCancelRequest) -> dict[str, Any]:
    """Cancel a SLURM job."""
    if not ssh_client.is_connected:
        raise HTTPException(status_code=400, detail="Not connected to cluster")
    res = ssh_client.cancel_job(req.job_id)
    return res


@app.get("/api/telemetry/forces")
async def api_telemetry_forces(case_name: str) -> dict[str, Any]:
    """Fetch force convergence telemetry for a given case."""
    force_content = ""

    # Check remote cluster first if connected
    if ssh_client.is_connected:
        remote_force_path = f"{ssh_client.remote_repo_path}/cases/{case_name}/postProcessing/forces/0/force.dat"
        force_content = ssh_client.read_remote_text(remote_force_path)
        if not force_content:
            # Check other time subdirectories in postProcessing/forces/
            cmd = f"ls '{ssh_client.remote_repo_path}/cases/{case_name}/postProcessing/forces/' 2>/dev/null | sort -n | tail -n 1"
            code, out, _ = ssh_client.run_command(cmd, timeout=5)
            last_dir = out.strip()
            if last_dir:
                remote_force_path = f"{ssh_client.remote_repo_path}/cases/{case_name}/postProcessing/forces/{last_dir}/force.dat"
                force_content = ssh_client.read_remote_text(remote_force_path)

    # Fall back to local case directory
    if not force_content:
        local_case = PROJECT_ROOT / "cases" / case_name
        files = find_force_files(local_case)
        if files:
            try:
                force_content = files[-1].read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

    if not force_content:
        return {
            "has_data": False,
            "message": f"No force.dat found yet for case '{case_name}'. (Solver may still be meshing or initializing).",
        }

    # Parse forces directly
    lines = force_content.splitlines()
    times: list[float] = []
    drags: list[float] = []
    downforces: list[float] = []

    # Default axis orientations for FSAE: flow along -z (drag), downforce along -y
    # In OpenFOAM forces output:
    # forces: total(x y z) pressure(x y z) viscous(x y z)
    # Total drag is typically z component (-z), downforce is -y
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line_clean = line.replace("(", " ").replace(")", " ")
        parts = line_clean.split()
        if len(parts) >= 4:
            try:
                t = float(parts[0])
                fx = float(parts[1])
                fy = float(parts[2])
                fz = float(parts[3])
                # Downforce (-fy) and Drag (-fz)
                drag = -fz
                df = -fy
                times.append(t)
                drags.append(drag)
                downforces.append(df)
            except ValueError:
                continue

    if not times:
        return {"has_data": False, "message": "force.dat found but has no numeric rows yet."}

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
    """Parse solver residuals from log.simpleFoam or solverInfo.dat."""
    log_content = ""
    if ssh_client.is_connected:
        remote_log = f"{ssh_client.remote_repo_path}/cases/{case_name}/log.simpleFoam"
        log_content = ssh_client.read_remote_text(remote_log, max_lines=600)

    if not log_content:
        local_log = PROJECT_ROOT / "cases" / case_name / "log.simpleFoam"
        if local_log.is_file():
            try:
                with open(local_log, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    log_content = "".join(lines[-600:])
            except Exception:
                pass

    if not log_content:
        return {"has_data": False, "message": "No log.simpleFoam found."}

    # Extract initial residuals using regex
    # Pattern: Solving for Ux, Initial residual = 0.04523, ...
    pattern = re.compile(
        r"Solving for (p|Ux|Uy|Uz|k|omega),\s+Initial residual\s+=\s+([0-9\.eE\+\-]+)",
        re.IGNORECASE,
    )
    residuals_map: dict[str, list[float]] = {"p": [], "Ux": [], "Uy": [], "Uz": [], "k": [], "omega": []}
    current_iter = 0
    iter_list: list[int] = []

    for line in log_content.splitlines():
        if "Time = " in line:
            try:
                current_iter = int(line.split("Time = ")[-1].strip())
            except ValueError:
                pass
        match = pattern.search(line)
        if match:
            var, val_str = match.groups()
            try:
                val = float(val_str)
                residuals_map[var].append(val)
                if var == "p":
                    iter_list.append(current_iter)
            except ValueError:
                pass

    return {
        "has_data": len(iter_list) > 0,
        "iterations": iter_list[-150:],
        "residuals": {k: v[-150:] for k, v in residuals_map.items()},
    }


@app.get("/api/telemetry/logs")
async def api_telemetry_logs(case_name: str, log_type: str = "simpleFoam", lines: int = 100) -> dict[str, Any]:
    """Tail log files (e.g. simpleFoam, snappyHexMesh, convergenceMonitor)."""
    filename = f"log.{log_type}"
    content = ""

    if ssh_client.is_connected:
        remote_path = f"{ssh_client.remote_repo_path}/cases/{case_name}/{filename}"
        content = ssh_client.read_remote_text(remote_path, max_lines=lines)

    if not content:
        local_file = PROJECT_ROOT / "cases" / case_name / filename
        if local_file.is_file():
            try:
                with open(local_file, encoding="utf-8", errors="replace") as f:
                    raw_lines = f.readlines()
                    content = "".join(raw_lines[-lines:])
            except Exception:
                pass

    return {
        "case_name": case_name,
        "log_type": log_type,
        "content": content or f"No entries in {filename} yet.",
    }


@app.get("/api/cases")
async def api_list_cases() -> list[dict[str, Any]]:
    """List simulation cases from cluster and local directory."""
    cases_dict: dict[str, dict[str, Any]] = {}

    # Local cases
    local_cases_dir = PROJECT_ROOT / "cases"
    if local_cases_dir.is_dir():
        for d in local_cases_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                cases_dict[d.name] = {
                    "name": d.name,
                    "location": "local",
                    "modified": d.stat().st_mtime,
                    "has_forces": (d / "postProcessing" / "forces").is_dir(),
                }

    # Remote cases if connected
    if ssh_client.is_connected:
        try:
            remote_cases = ssh_client.list_remote_cases()
            for rc in remote_cases:
                cname = rc["name"]
                if cname in cases_dict:
                    cases_dict[cname]["location"] = "both"
                else:
                    cases_dict[cname] = {
                        "name": cname,
                        "location": "cluster",
                        "modified": rc.get("modified", ""),
                        "has_forces": True,
                    }
        except Exception:
            pass

    return sorted(cases_dict.values(), key=lambda x: str(x.get("modified", "")), reverse=True)


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
        # Check if an existing instance of CFD Studio is already running on this port
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

        # If port is occupied by another application, switch to the next available port
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
