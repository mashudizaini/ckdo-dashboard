"""
SSH Executor — Paramiko wrapper. Ported from the standalone
ebs-backup-dashboard app almost unchanged.

Backup execution pattern:
  1. upload script to /tmp via SFTP
  2. submit via `nohup script > log 2>&1 & echo $!`
  3. return PID
  4. dashboard polling: kill -0 $PID + tail log + parse manifest.json
  5. browser can close, backup continues on server
"""
import io
from typing import Optional
import paramiko
from app.services.ebs_backup.vault_shim import vault

SSH_CONNECT_TIMEOUT = 15
SSH_COMMAND_TIMEOUT = 300


class SSHResult:
    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.ok = exit_code == 0

    def __repr__(self):
        return f"<SSHResult ok={self.ok} exit={self.exit_code}>"


class SSHExecutor:
    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "oracle",
        password: Optional[str] = None,
        private_key_pem: Optional[str] = None,
        key_passphrase: Optional[str] = None,
        connect_timeout: Optional[int] = None,
    ):
        self.host = host
        self.port = port
        self.username = username
        self._password = password
        self._private_key_pem = private_key_pem
        self._key_passphrase = key_passphrase
        self.connect_timeout = connect_timeout or SSH_CONNECT_TIMEOUT
        self._client: Optional[paramiko.SSHClient] = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def connect(self):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs = dict(
            hostname=self.host, port=self.port, username=self.username,
            timeout=self.connect_timeout, banner_timeout=self.connect_timeout,
            auth_timeout=self.connect_timeout,
            look_for_keys=False, allow_agent=False,
        )
        if self._private_key_pem:
            kwargs["pkey"] = self._load_private_key(self._private_key_pem,
                                                      self._key_passphrase)
        elif self._password:
            kwargs["password"] = self._password
        else:
            raise ValueError("SSH needs password or private_key_pem")
        client.connect(**kwargs)
        self._client = client

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    @staticmethod
    def _load_private_key(pem: str, passphrase: Optional[str]):
        for KeyClass in (paramiko.Ed25519Key, paramiko.RSAKey,
                         paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                return KeyClass.from_private_key(io.StringIO(pem), password=passphrase)
            except (paramiko.SSHException, ValueError):
                continue
        raise ValueError("Private key not recognized (RSA/Ed25519/ECDSA/DSS)")

    # ----- Sync command -----
    def run(self, cmd: str, timeout: Optional[int] = None) -> SSHResult:
        timeout = timeout or SSH_COMMAND_TIMEOUT
        if not self._client:
            self.connect()
        stdin, stdout, stderr = self._client.exec_command(cmd, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        return SSHResult(
            exit_code,
            stdout.read().decode(errors="replace"),
            stderr.read().decode(errors="replace"),
        )

    # ----- Async submit (background) -----
    def submit_background(self, script_path_remote: str,
                           log_path_remote: str,
                           pidfile_remote: str) -> int:
        cmd = (
            f"nohup bash {script_path_remote} > {log_path_remote} 2>&1 & "
            f"echo $! > {pidfile_remote}; cat {pidfile_remote}"
        )
        r = self.run(cmd, timeout=10)
        if not r.ok:
            raise RuntimeError(f"Submit background failed: {r.stderr}")
        return int(r.stdout.strip())

    def is_pid_alive(self, pid: int) -> bool:
        r = self.run(f"kill -0 {pid} 2>/dev/null && echo ALIVE || echo DEAD",
                      timeout=5)
        return "ALIVE" in r.stdout

    def tail_log(self, log_path: str, lines: int = 100) -> str:
        r = self.run(f"tail -n {lines} {log_path} 2>/dev/null || true", timeout=10)
        return r.stdout

    def _process_group(self, pid: int) -> int:
        """Resolve the real process group id for pid. nohup'd background jobs
        started from a non-interactive SSH shell do NOT become their own group
        leader (job control is off), so the pgid is some other, unrelated pid
        (often the now-exited exec_command shell) — never assume pgid == pid."""
        r = self.run(f"ps -o pgid= -p {pid} 2>/dev/null", timeout=5)
        try:
            return int(r.stdout.strip())
        except ValueError:
            return pid

    def kill_pid(self, pid: int, sig: int = 15, group: bool = True) -> bool:
        # nohup'd backup scripts pipe through tar|gzip|ssh — those child
        # processes share a process group with the tracked pid, so signal the
        # whole group by default or the pipeline stages survive as orphans.
        target = f"-{self._process_group(pid)}" if group else str(pid)
        r = self.run(f"kill -{sig} {target} 2>/dev/null && echo OK || echo FAIL",
                      timeout=5)
        return "OK" in r.stdout

    def pause_pid(self, pid: int) -> bool:
        """SIGSTOP the whole process group — suspends tar/gzip/ssh in place,
        resumable later with resume_pid(). Does not lose any progress."""
        pgid = self._process_group(pid)
        r = self.run(f"kill -STOP -{pgid} 2>/dev/null && echo OK || echo FAIL",
                      timeout=5)
        return "OK" in r.stdout

    def resume_pid(self, pid: int) -> bool:
        pgid = self._process_group(pid)
        r = self.run(f"kill -CONT -{pgid} 2>/dev/null && echo OK || echo FAIL",
                      timeout=5)
        return "OK" in r.stdout

    def upload_text(self, content: str, remote_path: str, mode: int = 0o755):
        parent = "/".join(remote_path.split("/")[:-1])
        if parent:
            self.run(f"mkdir -p {parent}")
        sftp = self._client.open_sftp()
        try:
            with sftp.file(remote_path, "w") as f:
                f.write(content)
            sftp.chmod(remote_path, mode)
        finally:
            sftp.close()

    def download_text(self, remote_path: str) -> str:
        sftp = self._client.open_sftp()
        try:
            with sftp.file(remote_path, "r") as f:
                return f.read().decode(errors="replace")
        finally:
            sftp.close()


# ============================================================
def ssh_from_server(server, credential) -> SSHExecutor:
    """Factory from EbsServer + EbsCredential record in DB."""
    if credential.cred_type == "ssh_password":
        return SSHExecutor(
            host=server.host, port=server.port or 22,
            username=credential.username,
            password=vault.decrypt(credential.secret_encrypted),
        )
    elif credential.cred_type == "ssh_key":
        return SSHExecutor(
            host=server.host, port=server.port or 22,
            username=credential.username,
            private_key_pem=vault.decrypt(credential.secret_encrypted),
            key_passphrase=(
                vault.decrypt(credential.key_passphrase_encrypted)
                if credential.key_passphrase_encrypted else None
            ),
        )
    else:
        raise ValueError(f"cred_type {credential.cred_type} is not SSH")
