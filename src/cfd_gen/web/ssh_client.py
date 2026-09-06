"""SSH and SFTP client manager for interacting with remote HPC clusters."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    paramiko = None  # type: ignore


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
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

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
        self.remote_repo_path = remote_repo_path or f"/work/home/{username}/Rapidamente/cfd/OpenFOAM-CaseGenerator"

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

        stdin, stdout, stderr = self._client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        out_str = stdout.read().decode("utf-8", errors="replace")
        err_str = stderr.read().decode("utf-8", errors="replace")
        return exit_code, out_str, err_str

    def test_connection(self) -> dict[str, Any]:
        """Test SSH connection and check environment on cluster."""
        if not self.is_connected:
            return {"connected": False, "error": "Not connected"}

        # Run environment checks
        cmd = (
            f"echo 'HOSTNAME='$(hostname) && "
            f"which sbatch >/dev/null 2>&1 && echo 'SLURM=available' || echo 'SLURM=missing' && "
            f"which python3 >/dev/null 2>&1 && echo 'PYTHON='$(which python3) || echo 'PYTHON=missing' && "
            f"[ -d '{self.remote_repo_path}' ] && echo 'REPO=exists' || echo 'REPO=missing'"
        )
        code, out, err = self.run_command(cmd, timeout=15)
        lines = dict(item.split("=", 1) for item in out.strip().splitlines() if "=" in item)

        repo_exists = lines.get("REPO") == "exists"
        slurm_ok = lines.get("SLURM") == "available"
        python_ok = lines.get("PYTHON") != "missing"

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
        if max_lines:
            cmd = f"tail -n {max_lines} '{remote_path}'"
            code, out, err = self.run_command(cmd, timeout=10)
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
        cmd = f"squeue -u {user} --format='%i|%j|%P|%T|%M|%l|%D|%R' --noheader"
        code, out, err = self.run_command(cmd, timeout=15)
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

    def submit_job(self, case_name: str) -> dict[str, Any]:
        """Submit sbatch run.sh for a case on the cluster."""
        remote_case_dir = f"{self.remote_repo_path}/cases/{case_name}"
        cmd = f"cd '{remote_case_dir}' && sbatch run.sh"
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
        cmd = f"scancel {job_id}"
        code, out, err = self.run_command(cmd, timeout=15)
        return {
            "success": code == 0,
            "job_id": job_id,
            "error": err if code != 0 else None,
        }

    def list_remote_cases(self) -> list[dict[str, Any]]:
        """List cases in cases/ folder on the cluster."""
        cmd = (
            f"[ -d '{self.remote_repo_path}/cases' ] && "
            f"ls -l --time-style=+%Y-%m-%d\\ %H:%M:%S '{self.remote_repo_path}/cases' || echo ''"
        )
        code, out, err = self.run_command(cmd, timeout=15)
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
