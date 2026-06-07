#!/usr/bin/env python3
"""
Forkmark — Universal Launcher
================================
Detects your OS and hardware, then starts Forkmark using the best
available method:

  1. Docker (recommended) — same experience on every OS
  2. Python direct         — fallback when Docker is unavailable

Usage
-----
  Windows :  double-click start.bat  (or: python start.py)
  macOS   :  ./start.sh              (or: python3 start.py)
  Linux   :  ./start.sh              (or: python3 start.py)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

# ── Configuration ──────────────────────────────────────────────────────────────

VERSION   = "0.1.1"
PORT      = int(os.getenv("FM_PORT", "7700"))
COMPOSE_F = "docker-compose.simple.yml"
URL       = f"http://localhost:{PORT}"
HERE      = os.path.dirname(os.path.abspath(__file__))

# ── Helpers ───────────────────────────────────────────────────────────────────

def _os_name() -> str:
    return platform.system()   # 'Windows' | 'Darwin' | 'Linux'

def _arch() -> str:
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64"):
        return "x86_64"
    return m

def banner() -> None:
    w = 46
    title = f"Forkmark v{VERSION}  —  AI Workflow QA"
    pad   = (w - len(title)) * " "
    print()
    print(f"  ╔{'═' * w}╗")
    print(f"  ║  {title}{pad}║")
    print(f"  ╚{'═' * w}╝")
    print(f"  OS   : {_os_name()} ({_arch()})")
    print(f"  URL  : {URL}")
    print()

def die(msg: str) -> None:
    print(f"\n  ✗  {msg}\n")
    if _os_name() == "Windows":
        input("  Press Enter to exit...")
    sys.exit(1)

def ask(prompt: str, default: str = "y") -> str:
    try:
        return input(prompt).strip().lower() or default
    except (EOFError, KeyboardInterrupt):
        return default

# ── Docker helpers ─────────────────────────────────────────────────────────────

def _find_docker_compose() -> list[str] | None:
    """Return the compose command (v2 preferred, v1 fallback)."""
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, check=True, timeout=10,
        )
        return ["docker", "compose"]
    except Exception:
        pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    return None

def _docker_running() -> bool:
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True, check=True, timeout=10,
        )
        return True
    except Exception:
        return False

def _docker_available() -> bool:
    return bool(shutil.which("docker"))

# ── .env first-run setup ──────────────────────────────────────────────────────

def _ensure_env_file() -> None:
    env_path = os.path.join(HERE, ".env")
    if os.path.exists(env_path):
        return  # already configured

    print("  First-run setup")
    print("  " + "─" * 44)
    print("  Forkmark can use an OpenAI-compatible key for")
    print("  LLM-as-judge divergence scoring (optional).")
    print()
    key = ask("  API key — OpenAI / OpenRouter (Enter to skip): ", "").strip()
    print()

    lines = []
    if key:
        lines += [
            f"OPENAI_API_KEY={key}",
            f"FM_OPENAI_API_KEY={key}",
        ]
    else:
        lines += [
            "# Add your API key here to enable LLM judge scoring:",
            "# OPENAI_API_KEY=sk-...",
        ]
    with open(env_path, "w") as f:
        f.write("\n".join(lines) + "\n")

# ── Health polling ────────────────────────────────────────────────────────────

def _wait_for_health(timeout: int = 90) -> bool:
    deadline = time.time() + timeout
    print(f"  Waiting for Forkmark", end="", flush=True)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{URL}/api/health", timeout=2) as r:
                if r.status == 200:
                    print("  ✓", flush=True)
                    return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(2)
    print()
    return False

# ── Browser opener ────────────────────────────────────────────────────────────

def _open_browser() -> None:
    system = _os_name()
    try:
        if system == "Windows":
            os.startfile(URL)                              # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", URL])
        else:
            # Linux — try xdg-open, fall back to webbrowser
            if shutil.which("xdg-open"):
                subprocess.Popen(["xdg-open", URL])
            else:
                webbrowser.open(URL)
    except Exception:
        pass  # browser open is best-effort

# ── Mode 1: Docker ────────────────────────────────────────────────────────────

def _start_docker(compose: list[str]) -> None:
    _ensure_env_file()

    print("  Starting via Docker (recommended)")
    print("  First run builds the image — takes ~2 min.")
    print()

    result = subprocess.run(
        compose + ["-f", COMPOSE_F, "up", "--build", "-d"],
        cwd=HERE,
    )
    if result.returncode != 0:
        die("Docker Compose failed. See output above for details.")

    if _wait_for_health():
        _print_success()
        _open_browser()
    else:
        print(f"\n  Forkmark may still be starting — open {URL} manually.\n")

# ── Mode 2: Python direct ─────────────────────────────────────────────────────

def _start_python() -> None:
    """Run the backend directly via uvicorn (no Docker required)."""
    print("  Starting in Python direct mode")
    print()

    # Install Python deps if uvicorn is missing
    try:
        import uvicorn  # noqa: F401
    except ImportError:
        print("  Installing Python dependencies...")
        _run_pip("install", "-r", "requirements.txt")
        print()

    # Build frontend if needed
    dist_dir = os.path.join(HERE, "frontend", "dist")
    if not os.path.isdir(dist_dir):
        if shutil.which("npm"):
            print("  Building frontend (first run)...")
            fe_dir = os.path.join(HERE, "frontend")
            subprocess.run(["npm", "install"], cwd=fe_dir, check=True)
            subprocess.run(["npm", "run", "build"], cwd=fe_dir, check=True)
            print()
        else:
            print("  ⚠  Frontend not built and npm not found.")
            print("     Install Node.js from https://nodejs.org/ then re-run,")
            print("     or install Docker Desktop for a zero-setup start.")
            print()

    # Launch uvicorn
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--host", "0.0.0.0",
            "--port", str(PORT),
        ],
        cwd=HERE,
    )

    if _wait_for_health(timeout=40):
        _print_success()
        _open_browser()
        print("  Press Ctrl+C to stop.\n")
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("\n  Stopping Forkmark...")
            proc.terminate()
            proc.wait()
            print("  Stopped.\n")
    else:
        proc.terminate()
        die(f"Server did not respond on port {PORT}. Check that it is not already in use.")

def _run_pip(*args: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", *args, "-q"],
        cwd=HERE, check=True,
    )

# ── Success banner ────────────────────────────────────────────────────────────

def _print_success() -> None:
    print()
    print("  ╔══════════════════════════════════════════╗")
    print(f"  ║  Forkmark is running!                   ║")
    print(f"  ║  Open  {URL:<34}║")
    print("  ╚══════════════════════════════════════════╝")
    print()

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    os.chdir(HERE)
    banner()

    system = _os_name()

    # ── Try Docker first (preferred on all platforms) ───────────────────────
    if _docker_available():
        if not _docker_running():
            print("  Docker is installed but not running.")
            if system == "Windows":
                print("  → Open Docker Desktop and wait for the whale icon in your taskbar.")
            elif system == "Darwin":
                print("  → Open Docker Desktop from your Applications folder.")
            else:
                print("  → Run:  sudo systemctl start docker")
            print()
            ans = ask("  Retry after starting Docker? [Y/n] ")
            if ans in ("y", ""):
                if not _docker_running():
                    print()
                    print("  Docker still not running — switching to Python direct mode.")
                    print()
                else:
                    compose = _find_docker_compose()
                    if compose:
                        _start_docker(compose)
                        return
            # fall through to Python mode
        else:
            compose = _find_docker_compose()
            if compose:
                _start_docker(compose)
                return
            else:
                print("  Docker found but Docker Compose is missing.")
                print("  Install Docker Desktop (includes Compose):")
                print("  https://www.docker.com/products/docker-desktop/")
                print()
    else:
        print("  Docker not found — using Python direct mode.")
        print("  Tip: install Docker Desktop for the simplest experience.")
        print()

    # ── Fallback: Python direct mode ────────────────────────────────────────
    _start_python()


if __name__ == "__main__":
    main()
