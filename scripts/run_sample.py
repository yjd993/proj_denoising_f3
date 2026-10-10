"""Run one L1 sequence through 7A, 8A, 8B, and 8C in a fresh result directory."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts/processing"))
from project_paths import DATA_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--output-root", type=Path, required=True, help="Must not already exist.")
    parser.add_argument("--seq", type=int, default=111)
    args = parser.parse_args()
    if not 1 <= args.seq <= 99999:
        parser.error("seq must be in 1..99999")
    output = args.output_root.expanduser().resolve()
    if output.exists():
        parser.error(f"Choose a new output directory; this one already exists: {output}")
    data = args.data_root.expanduser().resolve()
    env = os.environ.copy()
    env["AIRBORNE_LIDAR_PROJECT_DATA_ROOT"] = str(data)
    env["AIRBORNE_LIDAR_STAGE_ROOT"] = str(output)
    scope = ["--start-seq", str(args.seq), "--end-seq", str(args.seq)]
    commands = [
        ["scripts/doctor.py", "--data-root", str(data), "--stage-root", str(output), *scope],
        ["scripts/processing/stage7a_ch1_ladm2_candidate_batch.py", *scope, "--stop-on-error", "--progress"],
        ["scripts/processing/stage8a_ch1_ladm2_light_denoise_batch.py",
         "--input-manifest", str(output / "manifest/stage7a_ch1_ladm2_00050_00150_manifest.csv"),
         "--stop-on-error", "--progress"],
        ["scripts/processing/stage8b_ch1_export_local_coords.py", "--seq", str(args.seq), "--stop-on-error"],
        ["scripts/processing/stage8c_00111_l2p_intermediate_export.py", "--seq", str(args.seq), "--stop-on-error"],
    ]
    try:
        for command in commands:
            print("+ " + subprocess.list2cmdline([sys.executable, *command]), flush=True)
            subprocess.run([sys.executable, *command], cwd=REPO, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Sample stopped: {exc}", file=sys.stderr)
        return 1
    print(f"Sample complete: {output}")
    print("Review the candidate outputs before running a full batch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
