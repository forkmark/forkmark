#!/usr/bin/env python3
"""
Forkmark — Universal Stop Script
===================================
Stops the running Forkmark instance regardless of how it was started.

Usage
-----
  Windows :  double-click stop.bat  (or: python stop.py)
  macOS   :  ./stop.sh              (or: python3 stop.py)
  Linux   :  ./stop.sh              (or: python3 stop.py)
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

HERE      = os.path.dirname(os.path.abspath(__file__))
COMPOSE_F = "docker-compose.simple.yml"


def _find_docker_compose() -> list[str] | None:
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


def main() -> None:
    os.chdir(HERE)
    system = platform.system()

    print()
    print("  Stopping Forkmark...")
    print()

    stopped = False

    # ── Docker path ──────────────────────────────────────────────────────────
    if shutil.which("docker"):
        compose = _find_docker_compose()
        if compose:
            result = subprocess.run(
                compose + ["-f", COMPOSE_F, "down"],
                cwd=HERE,
            )
            if result.returncode == 0:
                stopped = True
            else:
                print("  Docker Compose reported an error (is Docker running?)")

    if stopped:
        print()
        print("  ✓  Forkmark stopped.")
        print("     Your data is preserved — run start.bat / start.sh to restart.")
        print()
    else:
        print("  Could not find a running Forkmark Docker container.")
        print("  If Forkmark is running in a terminal window, press Ctrl+C there.")
        print()

    if system == "Windows":
        input("  Press Enter to exit...")


if __name__ == "__main__":
    main()
