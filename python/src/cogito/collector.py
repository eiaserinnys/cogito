"""Automatic collectors for source locations, git info, env status, and runtime.

Each collector is a pure function (or thin class) that gathers data from
the process environment. No collector depends on Reflector internals —
they accept explicit parameters and return typed results.
"""

from __future__ import annotations

import inspect
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from cogito.types import ConfigEntry, RuntimeStatus, SourceEntry

logger = logging.getLogger(__name__)


def resolve_source(
    func: Callable,
    capability_name: str,
    source_root: str,
    git_head: str,
    git_remote_url: str | None,
) -> SourceEntry | None:
    """Resolve source location for a function via inspect.

    Args:
        func: The decorated function.
        capability_name: Name of the owning capability.
        source_root: Project-relative directory that serves as path base.
        git_head: Current git HEAD hash.
        git_remote_url: Remote origin URL (may be None).

    Returns:
        SourceEntry or None if source cannot be resolved.
    """
    try:
        source_file = inspect.getfile(func)
    except (TypeError, OSError):
        logger.warning("Cannot resolve source file for %s", func.__qualname__)
        return None

    try:
        source_lines, start_line = inspect.getsourcelines(func)
        end_line = start_line + len(source_lines) - 1
    except (OSError, TypeError):
        logger.warning("Cannot resolve source lines for %s", func.__qualname__)
        return None

    # Compute relative path from source_root
    source_path = Path(source_file).resolve()
    source_root_path = Path(source_root).resolve()

    try:
        relative = source_path.relative_to(source_root_path)
        path_str = str(relative).replace("\\", "/")
    except ValueError:
        # source_file is outside source_root — use absolute as fallback
        path_str = str(source_path).replace("\\", "/")

    module = getattr(func, "__module__", "") or ""

    return SourceEntry(
        capability=capability_name,
        module=module,
        path=path_str,
        entry_point=func.__qualname__,
        start_line=start_line,
        end_line=end_line,
        git_head=git_head,
        git_remote_url=git_remote_url,
    )


def get_git_head(cwd: str | None = None) -> str:
    """Get current git HEAD hash. Returns 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("Failed to get git HEAD: %s", e)
    return "unknown"


def get_git_remote_url(cwd: str | None = None) -> str | None:
    """Get git remote origin URL. Returns None on failure."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def resolve_config_status(key: str, sensitive: bool) -> tuple[str, str | None]:
    """Check environment variable status and return (status, display_value).

    Returns:
        Tuple of (status, current_value) where:
        - status: "valid", "missing", or "empty"
        - current_value: masked if sensitive, None if missing
    """
    raw = os.environ.get(key)

    if raw is None:
        return ("missing", None)
    if raw == "":
        return ("empty", "")

    if sensitive:
        display = raw[:2] + "***" if len(raw) >= 2 else "***"
    else:
        display = raw

    return ("valid", display)


def build_config_entry(
    key: str,
    capability: str | None,
    source: str,
    source_path: str | None,
    sensitive: bool,
    required: bool,
) -> ConfigEntry:
    """Build a ConfigEntry with live environment status."""
    status, current_value = resolve_config_status(key, sensitive)
    return ConfigEntry(
        key=key,
        capability=capability,
        source=source,
        source_path=source_path,
        sensitive=sensitive,
        required=required,
        status=status,
        current_value=current_value,
    )


def collect_runtime(
    start_time: float,
    health_status: str = "healthy",
    last_error: str | None = None,
) -> RuntimeStatus:
    """Collect runtime status using psutil if available, else os module.

    Args:
        start_time: ``time.monotonic()`` value captured at service start.
        health_status: Current health (``"healthy"``, ``"degraded"``, ``"unhealthy"``).
        last_error: Last error message, or None.
    """
    pid = os.getpid()
    uptime = time.monotonic() - start_time

    try:
        import psutil

        proc = psutil.Process(pid)
        mem = proc.memory_info()
        metrics = {
            "memory_rss_bytes": mem.rss,
            "memory_vms_bytes": mem.vms,
            "cpu_percent": proc.cpu_percent(interval=0),
            "num_threads": proc.num_threads(),
        }
        try:
            exe = proc.exe()
        except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
            exe = sys.executable
        try:
            cmdline = tuple(proc.cmdline())
        except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
            cmdline = tuple(sys.argv)
        try:
            cwd = proc.cwd()
        except (psutil.AccessDenied, psutil.ZombieProcess, OSError):
            cwd = os.getcwd()
    except ImportError:
        metrics = {}
        exe = sys.executable
        cmdline = tuple(sys.argv)
        cwd = os.getcwd()

    return RuntimeStatus(
        status=health_status,
        pid=pid,
        uptime_seconds=round(uptime, 2),
        metrics=metrics,
        last_error=last_error,
        exe=exe,
        cmdline=cmdline,
        cwd=cwd,
    )
