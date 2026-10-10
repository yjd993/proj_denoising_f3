"""Read-only installation and external-input preflight for Stage 7A/8D."""

from __future__ import annotations

import argparse
import csv
import importlib
from importlib.metadata import version
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import struct
import sys


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts" / "processing"))
from project_paths import DATA_ROOT, STAGE_ROOT


class Checks:
    def __init__(self):
        self.errors = 0

    def check(self, label, operation):
        try:
            detail = operation()
        except Exception as exc:
            self.errors += 1
            print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
            return None
        print(f"[OK] {label}: {detail if detail is not None else 'passed'}")
        return detail


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_software(checks):
    checks.check("Python", lambda: require(
        sys.version_info[:2] == (3, 13) and struct.calcsize("P") == 8,
        "Install 64-bit Python 3.13 and run scripts/bootstrap.py.",
    ))
    for line in (REPO / "requirements-lock.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        package, expected = line.split("==")

        def probe(package=package, expected=expected):
            actual = version(package)
            require(actual == expected, f"Expected {expected}, found {actual}; rerun scripts/bootstrap.py.")
            importlib.import_module(package)
            return actual

        checks.check(package, probe)
    if checks.errors:
        return
    import laspy
    checks.check("LAZ backend", lambda: require(
        bool(laspy.LazBackend.detect_available()), "No compression backend available.",
    ))


def manifest_files(root, start, end):
    path = root / "metadata/l1_manifest_stage5_time_quality.csv"
    files, seen = [], set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        require({"file", "seq", "status"} <= set(reader.fieldnames or []),
                f"{path}: required columns are file, seq, status")
        for line, row in enumerate(reader, 2):
            raw = row["seq"] or ""
            require(bool(re.fullmatch(r"[0-9]{1,5}", raw)) and int(raw) > 0,
                    f"{path}:{line}: invalid sequence {raw!r}")
            seq = int(raw)
            require(seq not in seen, f"{path}:{line}: duplicate sequence {seq}")
            seen.add(seq)
            if not start <= seq <= end or row["status"] != "OK":
                continue
            name = (row["file"] or "").replace("\\", "/")
            relative = Path(name)
            require(bool(name) and not relative.is_absolute()
                    and not PureWindowsPath(name).drive and ".." not in relative.parts,
                    f"{path}:{line}: file must be relative to the data root")
            file = root / relative
            require(bool(re.fullmatch(rf"L1_cap_{seq:05d}_[0-9]{{14}}\.h5", file.name)),
                    f"{path}:{line}: filename does not match sequence")
            files.append((seq, file))
    require(bool(files), f"No status=OK L1 files in scope {start:05d}-{end:05d}.")
    return files


def check_candidate(path):
    import numpy as np

    candidate = json.loads(path.read_text(encoding="utf-8-sig"))
    require(candidate["angle_direction"] in {"angle", "360-angle"}, "Invalid angle_direction")
    require(sorted(candidate["axis_perm"]) == [0, 1, 2], "Invalid axis_perm")
    require(len(candidate["axis_signs"]) == 3 and set(candidate["axis_signs"]) <= {-1, 1},
            "Invalid axis_signs")
    for key in (
        "angle_offset_deg", "mirror_tilt_deg", "frame_rotation_deg",
        "boresight_roll_deg", "boresight_pitch_deg", "boresight_yaw_deg",
        "lever_x_m", "lever_y_m", "lever_z_m",
    ):
        require(np.isfinite(float(candidate[key])), f"Invalid {key}")
    return "geometry keys and numeric values valid"


def load_pos_bounds(path):
    import numpy as np
    import ch1_pipeline as pipe

    if not path.is_file():
        raise FileNotFoundError(path)
    pos = pipe.load_pos_mat(path)
    count = np.asarray(pos["TIME"]).size
    require(count >= 2, "POS requires at least two samples")
    for field in pipe.POS_REQUIRED_FIELDS:
        values = np.asarray(pos[field], dtype=float).reshape(-1)
        require(values.size == count and np.isfinite(values).all(),
                f"Invalid POS field {field}: length mismatch or nonfinite values")
    times, _ = pipe.process_pos_time_seconds(pos["TIME"])
    times.sort()
    require(bool(np.all(np.diff(times) > 0)), "POS times must be distinct after normalization")
    return float(times[0]), float(times[-1])


def check_calibration(path):
    import numpy as np
    import ch1_pipeline as pipe

    if not path.is_file():
        raise FileNotFoundError(path)
    calibration = pipe.load_channel_calibration(path, "ch1")
    require(np.isfinite(calibration["slope"]) and calibration["slope"] != 0, "Invalid CH1 slope")
    require(np.isfinite(calibration["intercept"]), "Invalid CH1 intercept")
    return "CH1 slope and intercept valid"


def check_l1(path, bounds):
    import h5py
    import numpy as np
    import ch1_pipeline as pipe

    with h5py.File(path, "r") as h5:
        count = h5["GNSS_SEC_CH1"].size
        require(count > 0, "Empty L1 input")
        for field in pipe.CH1_REQUIRED_DATASETS:
            dataset = h5[field]
            require(dataset.shape == (count,) and dataset.dtype.kind in "fiu",
                    f"{field}: expected a numeric vector of length {count}")
            require(np.isfinite(dataset[0]) and np.isfinite(dataset[-1]),
                    f"{field}: nonfinite boundary values")
        indices = np.unique(np.linspace(0, count - 1, min(33, count), dtype=np.int64))
        times = h5["GNSS_SEC_CH1"][indices].astype(float) + pipe.DEFAULT_TIME_OFFSET_SEC
        require(np.isfinite(times).all(), "Sampled L1 times are nonfinite")
        if bounds is not None:
            require(times.min() >= bounds[0] and times.max() <= bounds[1],
                    f"Sampled L1 times outside POS coverage {bounds}")
    return f"{count} points; schema and sampled timestamps passed"


def check_output(path):
    require(not path.exists() or path.is_dir(), f"Result root is a file: {path}")
    ancestor = path
    while not ancestor.exists():
        ancestor = ancestor.parent
    require(ancestor.is_dir() and os.access(ancestor, os.W_OK),
            f"Result parent is not writable: {ancestor}")
    free = shutil.disk_usage(ancestor).free / 1024**3
    return f"{free:.1f} GiB free; no write probe performed"


def check_data(args, checks):
    root = args.data_root.expanduser().resolve()
    output = args.stage_root.expanduser().resolve()
    print(f"Data root: {root}\nResult root: {output}")
    checks.check("Result location", lambda: check_output(output))
    checks.check("Range calibration", lambda: check_calibration(root / "untitled/calib_coeffs.mat"))
    checks.check("Geometry candidate", lambda: check_candidate(
        root / "outputs/qc/stage6i_ladm2_scan_geometry_diagnostic/best_candidate.json"))
    bounds = checks.check("POS time coverage", lambda: load_pos_bounds(root / "0510_f3/0510f3_processed.mat"))
    files = []

    def select():
        nonlocal files
        if args.pipeline == "7a":
            files = manifest_files(root, args.start_seq, args.end_seq)
        else:
            import stage8d_ch1_l2p_missing_from_l1 as stage8d
            selection = argparse.Namespace(output_root=output, exclude_manifest=args.exclude_manifest)
            _, exclusions = stage8d.resolve_exclusions(selection)
            discovered = stage8d.discover_l1_files(
                root / "0510_f3/L1-TIME_ANGE_DIST_DATA", args.start_seq, args.end_seq)
            files = [(seq, path) for seq, path in discovered if seq not in exclusions]
            require(bool(files), "No non-excluded L1 files in scope")
            require(len({seq for seq, _ in files}) == len(files), "Duplicate L1 sequences")
        return f"{len(files)} selected inputs (existing outputs do not skip validation)"

    checks.check("Input selection", select)
    for seq, path in files:
        checks.check(f"L1 {seq:05d}", lambda path=path: check_l1(path, bounds))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--software-only", action="store_true", help="Check installation without mission data.")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--stage-root", type=Path, default=STAGE_ROOT)
    parser.add_argument("--pipeline", choices=("7a", "8d"), default="7a")
    parser.add_argument("--start-seq", type=int, default=50)
    parser.add_argument("--end-seq", type=int, default=150)
    parser.add_argument("--exclude-manifest", type=Path, default=os.environ.get("AIRBORNE_LIDAR_EXCLUDE_MANIFEST") or None)
    args = parser.parse_args(argv)
    if not 1 <= args.start_seq <= args.end_seq <= 99999:
        parser.error("Require 1 <= start-seq <= end-seq <= 99999")
    checks = Checks()
    check_software(checks)
    if not args.software_only and not checks.errors:
        check_data(args, checks)
    if checks.errors:
        print(f"\nPreflight failed: {checks.errors} issue(s). See docs/deployment.md.")
        return 2
    print("\nSoftware checks passed." if args.software_only else
          "\nInput preflight passed for this scope. H5 reads are sampled, not full integrity checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
