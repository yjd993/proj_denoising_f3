"""Install and test the core pipeline without downloading mission data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import struct
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=REPO / ".venv")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 13) or struct.calcsize("P") != 8:
        parser.error("Use 64-bit Python 3.13 (Windows: py -3.13 scripts/bootstrap.py).")
    target = args.venv.expanduser().resolve()
    if target.exists() and not (target / "pyvenv.cfg").is_file():
        parser.error(f"Refusing to use a non-venv directory: {target}")
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    env["PYTHONNOUSERSITE"] = "1"

    def run(*command: str) -> None:
        print("+ " + subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, cwd=REPO, env=env, check=True)

    try:
        if not target.exists():
            run(sys.executable, "-m", "venv", str(target))
        python = str(target / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
        run(python, "-c", (
            "import sys, struct; "
            "assert sys.version_info[:2] == (3, 13), 'Venv must use Python 3.13'; "
            "assert struct.calcsize('P') == 8, '64-bit Python required'; "
            "assert sys.prefix != sys.base_prefix, 'An isolated venv is required'"
        ))
        config = (target / "pyvenv.cfg").read_text(encoding="utf-8").lower()
        if "include-system-site-packages = true" in config:
            raise ValueError("The venv must not include system site packages.")
        run(python, "-m", "pip", "install", "--only-binary=:all:", "-r", "requirements.txt")
        run(python, "-m", "pip", "check")
        run(python, "scripts/doctor.py", "--software-only")
        run(python, "-m", "unittest", "discover", "-s", "tests", "-v")
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Setup failed: {exc}", file=sys.stderr)
        return 1
    print(f"\nSetup passed. Python: {python}")
    print("Download mission data separately, then follow docs/deployment.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
