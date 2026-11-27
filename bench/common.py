"""Tiện ích chung của harness: file nền, thông tin môi trường, RSS."""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from spike_build import MB, gen_file, peak_rss_mb  # noqa: F401  (dùng lại từ spike tuần 1)

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
DATA_DIR = ROOT.parent / "data"         # data/ ở gốc repo (không commit)
TRACES = ROOT / "traces"
RESULTS = ROOT / "results"


def base_file(size_mb: int) -> Path:
    """File nền giống log, sinh một lần với seed cố định (data/ ở gốc repo, không commit)."""
    path = DATA_DIR / f"log_{size_mb}mb.txt"
    if not path.exists():
        print(f"sinh {path} ...", file=sys.stderr, flush=True)
        gen_file(path, size_mb)
    return path


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def commit() -> str:
    c = _run(["git", "rev-parse", "--short", "HEAD"])
    return c + ("+dirty" if c and _run(["git", "status", "--porcelain", "--untracked-files=no"]) else "")


def machine() -> str:
    cpu = _run(["sysctl", "-n", "machdep.cpu.brand_string"]) if sys.platform == "darwin" else ""
    if not cpu and os.path.exists("/proc/cpuinfo"):
        with open("/proc/cpuinfo") as f:
            cpu = next((l.split(":", 1)[1].strip() for l in f if l.startswith("model name")), "")
    return f"{cpu or platform.processor() or platform.machine()} / {platform.system()} {platform.release()}"


def environment() -> dict:
    """Mọi thứ cần để tái lập một lần chạy benchmark (Flow 5.5)."""
    ram = ""
    if sys.platform == "darwin":
        ram = _run(["sysctl", "-n", "hw.memsize"])
    elif hasattr(os, "sysconf"):
        ram = str(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
    return {
        "commit": commit(), "machine": machine(), "cpus": os.cpu_count(),
        "ram_gb": round(int(ram) / 2**30, 1) if ram else None,
        "os": platform.platform(), "python": platform.python_version(),
        "implementation": platform.python_implementation(), "optimize": sys.flags.optimize,
        "pip_freeze": _run([sys.executable, "-m", "pip", "freeze", "--exclude-editable"]).splitlines(),
    }


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
