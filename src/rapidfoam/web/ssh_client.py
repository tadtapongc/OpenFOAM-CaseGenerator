"""SSH and SFTP client manager for interacting with remote HPC clusters."""

from __future__ import annotations

import ast
import inspect
import time
import base64
import io
import json
import logging
import os
import re
import shlex
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    paramiko = None  # type: ignore


def force_helper_source() -> str:
    """Ship the maintained parser to clusters, independent of their installed version."""
    from rapidfoam import geometry
    from rapidfoam.postproc import forces
    from rapidfoam.writers.scripts import _AnnotationStripper, _clean_force_helpers
    source = "\n\n".join(inspect.getsource(f) for f in (
        geometry.parse_axis, geometry.axis_index_sign,
        forces.load_axis_config, forces.is_symmetry_case,
    ))
    tree = _AnnotationStripper().visit(ast.parse(source))
    ast.fix_missing_locations(tree)
    return ("import json, math, re, statistics\nfrom pathlib import Path\n"
            + "AXIS_MAP = " + repr(geometry.AXIS_MAP) + "\n"
            + ast.unparse(tree) + "\n" + _clean_force_helpers() + "\n")


class ClusterSSHClient:
    """Manages an SSH/SFTP session to the OpenFOAM compute cluster."""

    def __init__(self) -> None:
        self._client: Optional[Any] = None
        self._sftp: Optional[Any] = None
        self.host: str = ""
        self.port: int = 22
        self.username: str = ""
        self.remote_repo_path: str = ""

    @property
    def is_connected(self) -> bool:
        """Check if active SSH transport exists and is active."""
        if not self._client:
            return False
        transport = self._client.get_transport()
        return transport is not None and transport.is_active()

    def connect(
        self,
        host: str,
        username: str,
        password: Optional[str] = None,
        key_path: Optional[str] = None,
        key_data: Optional[str] = None,
        port: int = 22,
        remote_repo_path: str = "",
        timeout: float = 15.0,
    ) -> dict[str, Any]:
        """Connect to the remote cluster via SSH."""
        if not PARAMIKO_AVAILABLE:
            raise RuntimeError(
                "Paramiko is not installed. Please install it using: pip install paramiko"
            )

        self.disconnect()

        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())

        pkey = None
        if key_data:
            pkey_file = io.StringIO(key_data.strip())
            for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                try:
                    pkey_file.seek(0)
                    pkey = key_cls.from_private_key(pkey_file, password=password)
                    break
                except Exception:
                    continue
        elif key_path:
            expanded = os.path.expanduser(key_path)
            if os.path.isfile(expanded):
                for key_cls in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey):
                    try:
                        pkey = key_cls.from_private_key_file(expanded, password=password)
                        break
                    except Exception:
                        continue

        connect_kwargs: dict[str, Any] = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": timeout,
            "banner_timeout": timeout,
        }
        if pkey is not None:
            connect_kwargs["pkey"] = pkey
        elif password:
            connect_kwargs["password"] = password
        else:
            # Fall back to default user SSH keys
            connect_kwargs["look_for_keys"] = True

        try:
            client.connect(**connect_kwargs)
        except Exception as exc:
            log.error("SSH connection failed to %s@%s: %s", username, host, exc)
            raise ConnectionError(f"Failed to connect to {username}@{host}: {exc}") from exc

        self._client = client
        self.host = host
        self.port = port
        self.username = username
        self.remote_repo_path = remote_repo_path or f"/work/home/{username}/Rapidamente/cfd/RapidFOAM"

        return self.test_connection()

    def disconnect(self) -> None:
        """Close SFTP and SSH connections."""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None

        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def get_sftp(self) -> Any:
        """Get or create SFTP client."""
        if not self.is_connected:
            raise ConnectionError("Not connected to cluster SSH server.")
        if self._sftp is None:
            self._sftp = self._client.open_sftp()
        return self._sftp

    def run_command(self, command: str, timeout: Optional[float] = 60.0) -> tuple[int, str, str]:
        """Execute command on the remote cluster."""
        if not self.is_connected:
            raise ConnectionError("Not connected to cluster SSH server.")

        _stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        channel = stdout.channel
        out, err = bytearray(), bytearray()
        deadline = time.monotonic() + timeout if timeout is not None else None
        try:
            while True:
                # Drain both streams while the remote process is running.
                if channel.recv_ready():
                    out.extend(channel.recv(65536))
                if channel.recv_stderr_ready():
                    err.extend(channel.recv_stderr(65536))
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    break
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("SSH command timed out")
                time.sleep(0.01)
            return channel.recv_exit_status(), out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
        finally:
            channel.close()

    def read_case_forces(self, case_name: str) -> dict[str, Any]:
        """Read remote case metadata and forces together using the shared parser."""
        script = force_helper_source() + """
import sys
repo = Path(sys.argv[1])
case = repo / "cases" / sys.argv[2]
config = case / "case_config.json"
if not config.is_file():
    config = repo / "configs" / (sys.argv[2] + ".json")
di, ds, fi, fs, da, fa = load_axis_config(str(config), case)
sym = is_symmetry_case(str(config), case)
times, drag, downforce = read_forces(find_force_files(case), di, ds, fi, fs)
scale = 2 if sym else 1
print(json.dumps({"times": times, "drag": [v * scale for v in drag],
                  "downforce": [v * scale for v in downforce],
                  "is_symmetry": sym, "drag_axis": da, "downforce_axis": fa}))
"""
        b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
        code = "import base64; exec(base64.b64decode(" + repr(b64) + "))"
        command = "python3 -c " + shlex.quote(code) + " " + shlex.quote(self.remote_repo_path) + " " + shlex.quote(case_name)
        status, out, err = self.run_command(command, timeout=30)
        if status:
            raise RuntimeError(err or "Remote force reader failed")
        return json.loads(out)

    def test_connection(self) -> dict[str, Any]:
        """Test SSH connection and check environment on cluster."""
        if not self.is_connected:
            return {"connected": False, "error": "Not connected"}

        # Run environment checks with safely quoted paths
        quoted_repo = shlex.quote(self.remote_repo_path)
        cmd = (
            f"echo 'HOSTNAME='$(hostname) && "
            f"which sbatch >/dev/null 2>&1 && echo 'SLURM=available' || echo 'SLURM=missing' && "
            f"which python3 >/dev/null 2>&1 && echo 'PYTHON='$(which python3) || echo 'PYTHON=missing' && "
            f"[ -d {quoted_repo} ] && echo 'REPO=exists' || echo 'REPO=missing'"
        )
        _, out, _ = self.run_command(cmd, timeout=15)
        lines = dict(item.split("=", 1) for item in out.strip().splitlines() if "=" in item)

        repo_exists = lines.get("REPO") == "exists"
        slurm_ok = lines.get("SLURM") == "available"

        return {
            "connected": True,
            "host": self.host,
            "username": self.username,
            "remote_host": lines.get("HOSTNAME", self.host),
            "remote_repo_path": self.remote_repo_path,
            "repo_exists": repo_exists,
            "slurm_available": slurm_ok,
            "remote_python": lines.get("PYTHON", "missing"),
            "raw_test_output": out.strip(),
        }

    def ensure_remote_dir(self, remote_dir: str) -> None:
        """Recursively create remote directory if it doesn't exist."""
        sftp = self.get_sftp()
        parts = remote_dir.replace("\\", "/").split("/")
        curr = ""
        for part in parts:
            if not part:
                curr = "/"
                continue
            curr = f"{curr}/{part}" if curr != "/" else f"/{part}"
            try:
                sftp.stat(curr)
            except IOError:
                try:
                    sftp.mkdir(curr)
                except IOError:
                    pass

    def upload_file(self, local_path: str | Path, remote_path: str) -> None:
        """Upload a local file to remote cluster via SFTP."""
        local_p = Path(local_path)
        if not local_p.is_file():
            raise FileNotFoundError(f"Local file not found: {local_path}")

        remote_dir = os.path.dirname(remote_path.replace("\\", "/"))
        self.ensure_remote_dir(remote_dir)

        sftp = self.get_sftp()
        sftp.put(str(local_p), remote_path.replace("\\", "/"))

    def upload_text(self, text_content: str, remote_path: str) -> None:
        """Upload a string content directly as a remote file."""
        remote_dir = os.path.dirname(remote_path.replace("\\", "/"))
        self.ensure_remote_dir(remote_dir)

        sftp = self.get_sftp()
        bio = io.BytesIO(text_content.encode("utf-8"))
        sftp.putfo(bio, remote_path.replace("\\", "/"))

    def read_remote_text(self, remote_path: str, max_lines: Optional[int] = None) -> str:
        """Read a remote text file via SFTP or tail command."""
        if max_lines is not None:
            safe_lines = max(1, min(int(max_lines), 2000))
            quoted_path = shlex.quote(remote_path)
            cmd = f"tail -n {safe_lines} {quoted_path}"
            code, out, _ = self.run_command(cmd, timeout=10)
            if code == 0:
                return out
            return ""

        sftp = self.get_sftp()
        try:
            with sftp.open(remote_path.replace("\\", "/"), "r") as f:
                content = f.read().decode("utf-8", errors="replace")
                return content
        except Exception as exc:
            log.warning("Could not read remote file %s: %s", remote_path, exc)
            return ""

    def get_slurm_queue(self, username: Optional[str] = None) -> list[dict[str, str]]:
        """Query SLURM squeue for user jobs."""
        user = username or self.username
        if not user or not re.match(r"^[A-Za-z0-9_.-]+$", user):
            return []

        quoted_user = shlex.quote(user)
        cmd = f"squeue -u {quoted_user} --format='%i|%j|%P|%T|%M|%l|%D|%R' --noheader"
        code, out, _ = self.run_command(cmd, timeout=15)
        if code != 0:
            return []

        jobs: list[dict[str, str]] = []
        for line in out.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 7:
                jobs.append({
                    "job_id": parts[0],
                    "name": parts[1],
                    "partition": parts[2],
                    "state": parts[3],
                    "time_used": parts[4],
                    "time_limit": parts[5],
                    "nodes": parts[6],
                    "reason": parts[7] if len(parts) > 7 else "",
                })
        return jobs

    def remote_file_exists(self, remote_path: str) -> bool:
        """Check if a remote file or directory exists via SFTP."""
        if not self.is_connected:
            return False
        try:
            sftp = self.get_sftp()
            sftp.stat(remote_path.replace("\\", "/"))
            return True
        except (IOError, OSError):
            return False

    def is_case_running(self, case_name: str) -> bool:
        """Check if a case currently has an active (RUNNING or PENDING) SLURM job."""
        if not self.is_connected:
            return False
        try:
            jobs = self.get_slurm_queue()
            for job in jobs:
                # Job name or case_name matching
                jname = job.get("name", "")
                if jname == case_name or jname == f"cfd_{case_name}" or case_name in jname:
                    state = job.get("state", "").upper()
                    if state in ("R", "RUNNING", "PD", "PENDING", "CF", "CONFIGURING"):
                        return True
        except Exception:
            pass
        return False

    def submit_job(self, case_name: str) -> dict[str, Any]:
        """Submit sbatch run.sh for a case on the cluster."""
        if not re.match(r"^[A-Za-z0-9_-]+$", case_name):
            return {"success": False, "error": f"Invalid case name: {case_name}"}

        remote_case_dir = f"{self.remote_repo_path}/cases/{case_name}"
        quoted_case_dir = shlex.quote(remote_case_dir)
        cmd = f"cd {quoted_case_dir} && sbatch run.sh"
        code, out, err = self.run_command(cmd, timeout=20)
        if code != 0:
            return {"success": False, "error": err or out or "Failed to execute sbatch"}

        # Typical output: 'Submitted batch job 1234567'
        job_id = None
        for token in out.split():
            if token.isdigit():
                job_id = token
                break

        return {
            "success": True,
            "job_id": job_id,
            "raw_output": out.strip(),
            "case_dir": remote_case_dir,
        }

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a SLURM job."""
        job_id_str = str(job_id).strip()
        if not re.match(r"^[0-9]+$", job_id_str):
            return {"success": False, "job_id": job_id_str, "error": "Job ID must be numeric"}

        cmd = f"scancel {shlex.quote(job_id_str)}"
        code, _, err = self.run_command(cmd, timeout=15)
        return {
            "success": code == 0,
            "job_id": job_id_str,
            "error": err if code != 0 else None,
        }

    def list_remote_cases(self) -> list[dict[str, Any]]:
        """List cases in cases/ folder on the cluster."""
        cases_dir = f"{self.remote_repo_path}/cases"
        quoted_dir = shlex.quote(cases_dir)
        cmd = (
            f"[ -d {quoted_dir} ] && "
            f"ls -l --time-style=+%Y-%m-%d\\ %H:%M:%S {quoted_dir} || echo ''"
        )
        code, out, _ = self.run_command(cmd, timeout=15)
        cases: list[dict[str, Any]] = []
        if code != 0 or not out.strip():
            return cases

        for line in out.strip().splitlines():
            line = line.strip()
            if not line.startswith("d"):
                continue
            tokens = line.split()
            if len(tokens) >= 8:
                cname = tokens[-1]
                mtime = f"{tokens[5]} {tokens[6]}"
                cases.append({
                    "name": cname,
                    "modified": mtime,
                })
        return cases

    def list_remote_cases_detailed(self) -> list[dict[str, Any]]:
        """Extract detailed metadata, simulation status, and aerodynamic forces for all remote cases."""
        if not self.is_connected:
            return []

        remote_script = """
import os, sys, json, glob, re, math, statistics, datetime
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
cases_dir = repo / "cases"

def read_tail(fpath, max_bytes=8192):
    try:
        sz = fpath.stat().st_size
        with open(str(fpath), "rb") as f:
            if sz > max_bytes:
                f.seek(sz - max_bytes)
            return f.read().decode("utf-8", errors="replace")
    except Exception:
        return ""

results = []
if cases_dir.is_dir():
    for d in sorted(cases_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("."):
            continue
        cname = d.name
        st = d.stat()
        mtime = st.st_mtime
        mtime_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        # Config
        cfg_file = d / "case_config.json"
        if not cfg_file.is_file():
            cfg_file = repo / "configs" / (cname + ".json")

        fidelity = "standard"
        velocity = "16.67"
        direction = "-z"
        n_procs = 32
        stl_name = "--"
        drag_idx, drag_sign = 2, -1.0
        df_idx, df_sign = 1, -1.0
        is_sym = False

        if cfg_file.is_file():
            try:
                with open(str(cfg_file), encoding="utf-8") as f:
                    cd = json.load(f)
                    fidelity = cd.get("fidelity", "standard")
                    v_val = cd.get("flow", {}).get("velocity", 16.67)
                    velocity = f"{v_val:.1f}" if isinstance(v_val, (int, float)) else str(v_val)
                    direction = cd.get("flow", {}).get("direction", "-z")
                    n_procs = cd.get("parallel", {}).get("n_procs", 32)
                    stls = cd.get("stl_files", [])
                    if stls:
                        stl_name = Path(stls[0]).name
            except Exception:
                pass

        drag_idx, drag_sign, df_idx, df_sign, _, _ = load_axis_config(str(cfg_file), d)
        is_sym = is_symmetry_case(str(cfg_file), d)
        sym_scale = 2.0 if is_sym else 1.0
        force_files = find_force_files(d)
        has_forces = bool(force_files)
        latest_iter = None
        converged = False
        downforce_val = drag_val = ld_val = None
        times, drags, downforces = read_forces(force_files, drag_idx, drag_sign, df_idx, df_sign)
        if times:
            drags = [v * sym_scale for v in drags]
            downforces = [v * sym_scale for v in downforces]
            latest_iter = int(times[-1])
            converged, _, _, d_avg, f_avg = check_convergence(drags, downforces)
            downforce_val = round(f_avg, 2)
            drag_val = round(d_avg, 2)
            ld_val = round(f_avg / d_avg, 2) if abs(d_avg) > 1e-3 else None

        # Check logs and status
        status = "Generated"
        log_simple = d / "log.simpleFoam"
        has_residuals = log_simple.is_file()
        has_mesh = (d / "constant" / "polyMesh" / "points").is_file()

        if log_simple.is_file():
            tail = read_tail(log_simple)
            if "End" in tail or "Finalising parallel run" in tail:
                status = "Converged" if converged else "Completed"
            elif any(err in tail for err in ["FOAM FATAL", "Fatal error", "FOAM aborting", "sigFpe", "SIGFPE", "Floating point exception"]):
                status = "Failed"
            else:
                status = "Solving"
        elif (d / "log.cartesianMesh").is_file():
            tail = read_tail(d / "log.cartesianMesh")
            if "End" in tail or "Finalising parallel run" in tail:
                status = "Meshed"
            elif any(err in tail for err in ["FOAM FATAL", "Fatal error", "FOAM aborting", "sigFpe", "SIGFPE"]):
                status = "Failed"
            else:
                status = "Meshing"
        elif (d / "log.snappyHexMesh").is_file():
            tail = read_tail(d / "log.snappyHexMesh")
            if "End" in tail or "Finalising parallel run" in tail:
                status = "Meshed"
            elif any(err in tail for err in ["FOAM FATAL", "Fatal error", "FOAM aborting", "sigFpe", "SIGFPE"]):
                status = "Failed"
            else:
                status = "Meshing"
        elif has_mesh:
            status = "Meshed"

        is_running_loc = (d / ".running_location").is_file()

        results.append({
            "name": cname,
            "modified": mtime_str,
            "modified_ts": mtime,
            "status": status,
            "fidelity": fidelity,
            "velocity": velocity,
            "direction": direction,
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
            "is_running_loc": is_running_loc,
        })

print("__CASE_JSON_START__" + json.dumps(results) + "__CASE_JSON_END__")
"""
        try:
            b64 = base64.b64encode((force_helper_source() + remote_script).encode("utf-8")).decode("ascii")
            quoted_repo = shlex.quote(self.remote_repo_path or ".")
            py_code = f"import base64; exec(base64.b64decode('{b64}').decode('utf-8'))"
            cmd = f"python3 -c {shlex.quote(py_code)} {quoted_repo}"
            code, out, err = self.run_command(cmd, timeout=15)
            if code == 0 and "__CASE_JSON_START__" in out:
                payload = out.split("__CASE_JSON_START__")[1].split("__CASE_JSON_END__")[0]
                return json.loads(payload)
            log.warning("list_remote_cases_detailed remote script returned code %s: %s", code, err or out[:200])
        except Exception as exc:
            log.warning("list_remote_cases_detailed failed: %s", exc)

        # Fallback to basic list_remote_cases
        basic = self.list_remote_cases()
        return [
            {
                "name": c["name"],
                "modified": c.get("modified", ""),
                "modified_ts": 0,
                "status": "Cluster Job",
                "fidelity": "--",
                "velocity": "--",
                "direction": "--",
                "n_procs": 0,
                "stl_name": "--",
                "has_forces": False,
                "has_residuals": False,
                "has_mesh": False,
                "latest_iter": None,
                "converged": False,
                "downforce": None,
                "drag": None,
                "ld_ratio": None,
                "is_running_loc": False,
            }
            for c in basic
        ]

