"""Fail-closed host resource guard for autonomous project work.

This module only observes host state and launches explicitly bounded child commands.
It never restarts or kills Hermes, deployed bots, databases, or unrelated services.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceSnapshot:
    available_memory_bytes: int
    total_memory_bytes: int
    swap_used_bytes: int
    swap_total_bytes: int
    disk_free_bytes: int
    disk_total_bytes: int
    disk_used_percent: float
    inode_free_percent: float

    @property
    def swap_used_percent(self) -> float:
        return (self.swap_used_bytes / self.swap_total_bytes * 100) if self.swap_total_bytes else 0.0


@dataclass(frozen=True)
class GuardPolicy:
    min_available_memory_mb: int = 768
    max_swap_used_percent: float = 90.0
    max_disk_used_percent: float = 85.0
    min_disk_free_gb: float = 8.0
    min_inode_free_percent: float = 10.0


def _meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, raw = line.partition(":")
        parts = raw.strip().split()
        if parts:
            values[key] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    return values


def snapshot(path: Path = Path("/")) -> ResourceSnapshot:
    mem = _meminfo()
    usage = shutil.disk_usage(path)
    stat = os.statvfs(path)
    inode_free = stat.f_bavail / stat.f_blocks * 100 if stat.f_blocks else 0.0
    return ResourceSnapshot(
        available_memory_bytes=mem.get("MemAvailable", 0),
        total_memory_bytes=mem.get("MemTotal", 0),
        swap_used_bytes=max(0, mem.get("SwapTotal", 0) - mem.get("SwapFree", 0)),
        swap_total_bytes=mem.get("SwapTotal", 0),
        disk_free_bytes=usage.free,
        disk_total_bytes=usage.total,
        disk_used_percent=(usage.used / usage.total * 100) if usage.total else 100.0,
        inode_free_percent=inode_free,
    )


def violations(current: ResourceSnapshot, policy: GuardPolicy = GuardPolicy()) -> list[str]:
    problems = []
    if current.available_memory_bytes < policy.min_available_memory_mb * 1024**2:
        problems.append("LOW_AVAILABLE_MEMORY")
    if current.swap_used_percent > policy.max_swap_used_percent:
        problems.append("SWAP_PRESSURE")
    if current.disk_used_percent > policy.max_disk_used_percent:
        problems.append("DISK_PRESSURE")
    if current.disk_free_bytes < policy.min_disk_free_gb * 1024**3:
        problems.append("LOW_DISK_FREE")
    if current.inode_free_percent < policy.min_inode_free_percent:
        problems.append("INODE_PRESSURE")
    return problems


def status(policy: GuardPolicy = GuardPolicy()) -> dict:
    current = snapshot()
    return {"ok": not violations(current, policy), "violations": violations(current, policy),
            "policy": asdict(policy), "snapshot": asdict(current),
            "swap_used_percent": current.swap_used_percent}


def run_bounded(command: list[str], *, timeout_seconds: int = 300, memory_mb: int = 1024,
                cwd: Path | None = None) -> int:
    """Run one child process with a preflight guard and process-group timeout."""
    blocked = violations(snapshot())
    if blocked:
        print(json.dumps({"status": "BLOCKED_RESOURCE_PRESSURE", "violations": blocked}, sort_keys=True))
        return 75
    if timeout_seconds < 1 or memory_mb < 128:
        raise ValueError("unsafe bound")

    def limits() -> None:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024**2, memory_mb * 1024**2))
        resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds, timeout_seconds + 2))
        resource.setrlimit(resource.RLIMIT_FSIZE, (256 * 1024**2, 256 * 1024**2))

    proc = subprocess.Popen(command, cwd=cwd, start_new_session=True, preexec_fn=limits)
    try:
        return proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
        return 124


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fail-closed resource guard")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--run", nargs=argparse.REMAINDER)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--memory-mb", type=int, default=1024)
    args = parser.parse_args(argv)
    if args.run:
        return run_bounded(args.run, timeout_seconds=args.timeout_seconds, memory_mb=args.memory_mb)
    result = status()
    print(json.dumps(result, indent=2 if args.json else None, sort_keys=True))
    return 0 if result["ok"] else 75


if __name__ == "__main__":
    raise SystemExit(main())
