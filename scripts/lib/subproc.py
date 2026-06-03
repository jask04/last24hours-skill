"""Subprocess helpers for process-group timeout cleanup."""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional, Sequence


class SubprocTimeout(Exception):
    """Raised when a subprocess exceeds its timeout and is killed."""


@dataclass
class SubprocResult:
    returncode: int
    stdout: str
    stderr: str


def run_with_timeout(
    cmd: Sequence[str],
    *,
    timeout: int,
    env: Optional[dict] = None,
    on_pid: Optional[Callable[[int], None]] = None,
) -> SubprocResult:
    """Run a subprocess and clean up its process group on timeout."""
    preexec = os.setsid if hasattr(os, "setsid") else None
    proc = subprocess.Popen(
        list(cmd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        preexec_fn=preexec,
        env=env,
    )
    if on_pid is not None:
        try:
            on_pid(proc.pid)
        except Exception:
            pass
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        raise SubprocTimeout(str(exc)) from exc
    return SubprocResult(proc.returncode, stdout or "", stderr or "")
