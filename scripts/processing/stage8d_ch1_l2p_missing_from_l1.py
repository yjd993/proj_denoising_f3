from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage6k_ch1_ladm2_full_00111_export as stage6k
import stage7a_ch1_ladm2_candidate_batch as stage7a
from project_paths import DATA_ROOT, STAGE_ROOT


DEFAULT_DATA_ROOT = DATA_ROOT
DEFAULT_OUTPUT_ROOT = STAGE_ROOT
DEFAULT_L1_DIR = DEFAULT_DATA_ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
DEFAULT_MIN_RANGE_M = 30.0
DEFAULT_LOW_CONFIDENCE_SEC = 0.2
DEFAULT_CHUNK_SIZE = 500_000


def jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def parse_seq(path: Path) -> int:
    match = re.search(r"L1_cap_(\d{5})_[0-9]{14}\.h5$", path.name)
    if not match:
        raise ValueError(f"Cannot parse sequence from {path}")
    return int(match.group(1))


def discover_l1_files(l1_dir: Path, start_seq: int | None, end_seq: int | None) -> list[tuple[int, Path]]:
    if not l1_dir.is_dir():
        raise FileNotFoundError(f"Missing L1 directory: {l1_dir}")
    files: list[tuple[int, Path]] = []
    for path in sorted(l1_dir.glob("L1_cap_*.h5")):
        seq = parse_seq(path)
        if start_seq is not None and seq < start_seq:
            continue
        if end_seq is not None and seq > end_seq:
            continue
        files.append((seq, path))
    return files


def txt_path(output_root: Path, seq: int) -> Path:
    return (
        output_root
        / "stage8c_l2p_intermediate"
        / "txt"
        / f"stage8c_{seq:05d}_ch1_ladm2_l2p_offsets_cloudcompare.txt"
    )


def manifest_path(output_root: Path) -> Path:
    return (
        output_root
        / "stage8c_l2p_intermediate"
        / "manifest"
        / "stage8d_ch1_l2p_missing_from_l1_manifest.csv"
    )


def report_paths(output_root: Path) -> dict[str, Path]:
    base = output_root / "stage8c_l2p_intermediate" / "reports"
    return {
        "json": base / "stage8d_ch1_l2p_missing_from_l1_report.json",
        "md": base / "stage8d_ch1_l2p_missing_from_l1_report.md",
    }


def safe_temp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def existing_stage8c_sequences(output_root: Path) -> set[int]:
    out_dir = output_root / "stage8c_l2p_intermediate" / "txt"
    seqs: set[int] = set()
    for path in out_dir.glob("stage8c_*_ch1_ladm2_l2p_offsets_cloudcompare.txt"):
        match = re.search(r"stage8c_(\d{5})_ch1_ladm2_l2p_offsets_cloudcompare\.txt$", path.name)
        if match:
            seqs.add(int(match.group(1)))
    return seqs


def load_stage6i_candidate() -> dict[str, Any]:
    return stage6k.load_json(stage7a.STAGE6I_BEST)


def exclusion_manifest_path(output_root: Path) -> Path:
    return (
        output_root / "stage8c_l2p_intermediate" / "manifest"
        / "stage8c_pos_match_failed_excluded_txt_manifest.csv"
    )


def load_exclusions(path: Path) -> dict[int, str]:
    exclusions: dict[int, str] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or "seq" not in reader.fieldnames:
            raise ValueError(f"Exclusion manifest must contain a seq column: {path}")
        for line, row in enumerate(reader, start=2):
            raw_seq = (row.get("seq") or "").strip()
            if not re.fullmatch(r"[0-9]{1,5}", raw_seq) or int(raw_seq) < 1:
                raise ValueError(f"Invalid exclusion seq at {path}:{line}: {raw_seq!r}")
            seq = int(raw_seq)
            if seq in exclusions:
                raise ValueError(f"Duplicate exclusion seq at {path}:{line}: {seq:05d}")
            exclusions[seq] = row.get("reason") or row.get("action") or "listed in exclusion manifest"
    return exclusions


def resolve_exclusions(args: argparse.Namespace) -> tuple[Path, dict[int, str]]:
    path = args.exclude_manifest or exclusion_manifest_path(args.output_root)
    if path.exists() or args.exclude_manifest is not None:
        return path, load_exclusions(path)
    quarantine = args.output_root / "stage8c_l2p_intermediate" / "txt_pos_match_failed_excluded"
    if quarantine.exists():
        raise FileNotFoundError(
            f"Quarantine directory exists but its exclusion manifest is missing: {path}. "
            "Restore the manifest or supply a reviewed --exclude-manifest."
        )
    return path, {}


def build_l2p_points(
    l1_path: Path,
    seq: int,
    calibration: dict[str, float],
    candidate: dict[str, Any],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    min_range_m: float,
    low_confidence_sec: float,
    progress: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    l1 = stage6k.load_l1_full(l1_path)
    points, stats = stage6k.build_full_points(
        l1,
        calibration,
        candidate,
        min_range_m,
        low_confidence_sec,
        progress,
    )
    points["source_seq"] = seq
    points = stage7a.add_pos_match_fields(points, pos_time, pos)
    stats["source_seq"] = seq
    stats["source_l1"] = str(l1_path)
    stats["pos_good_count"] = int(np.count_nonzero(points["pos_quality_flag"] == 0))
    return points, stats


def write_l2p_txt(
    path: Path,
    points: np.ndarray,
    min_range_m: float,
    overwrite: bool,
    chunk_size: int,
) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()

    count = 0
    with temp_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(
            "POINT_X POINT_Y POINT_Z LIDAR_X LIDAR_Y LIDAR_Z gps_time range_m "
            "scan_angle_deg point_index pos_interp_dt source_seq pos_quality_flag\n"
        )
        for start in range(0, points.size, chunk_size):
            block = points[start : start + chunk_size]
            keep = (
                np.isfinite(block["north_offset_m"])
                & np.isfinite(block["east_offset_m"])
                & np.isfinite(block["down_offset_m"])
                & np.isfinite(block["gps_time"])
                & np.isfinite(block["range_m"])
                & (block["range_m"] > min_range_m)
                & (block["pos_quality_flag"] == 0)
            )
            selected = block[keep]
            count += int(selected.size)
            if selected.size == 0:
                continue
            out = np.column_stack(
                [
                    selected["pos_northing"].astype(np.float64) + selected["north_offset_m"].astype(np.float64),
                    selected["pos_easting"].astype(np.float64) + selected["east_offset_m"].astype(np.float64),
                    selected["pos_height"].astype(np.float64) - selected["down_offset_m"].astype(np.float64),
                    selected["north_offset_m"].astype(np.float64),
                    selected["east_offset_m"].astype(np.float64),
                    selected["down_offset_m"].astype(np.float64),
                    selected["gps_time"].astype(np.float64),
                    selected["range_m"].astype(np.float64),
                    selected["scan_angle_deg"].astype(np.float64),
                    selected["point_index"].astype(np.float64),
                    selected["pos_interp_dt"].astype(np.float64),
                    selected["source_seq"].astype(np.float64),
                    selected["pos_quality_flag"].astype(np.float64),
                ]
            )
            np.savetxt(
                f,
                out,
                fmt=[
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%.0f",
                    "%.9f",
                    "%.0f",
                    "%.0f",
                ],
            )

    if path.exists() and overwrite:
        path.unlink()
    temp_path.replace(path)
    return {"txt_point_count": count, "txt_size_bytes": path.stat().st_size}


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "seq",
        "status",
        "source_l1",
        "txt_path",
        "h5_point_count",
        "txt_point_count",
        "txt_size_bytes",
        "pos_good_count",
        "pos_success_rate",
        "elapsed_sec",
        "reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(output_root: Path, payload: dict[str, Any]) -> None:
    paths = report_paths(output_root)
    paths["json"].parent.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")
    md = f"""# Stage 8D CH1 L2P Missing From L1

## Purpose

Fill missing Stage 8C L2P-style CloudCompare TXT files directly from L1 files.

## Coordinate Semantics

- `LIDAR_X`: `north_offset_m`
- `LIDAR_Y`: `east_offset_m`
- `LIDAR_Z`: `down_offset_m`
- `POINT_X`: `pos_northing + north_offset_m`
- `POINT_Y`: `pos_easting + east_offset_m`
- `POINT_Z`: `pos_height - down_offset_m`

This stage reuses the existing LADM-II scan model, Stage 6I candidate, range calibration,
and POS attitude rotation. It does not introduce a new geometry algorithm.

## Summary

- L1 files discovered: {payload['summary']['l1_files_discovered']:,}
- Existing TXT skipped: {payload['summary']['skipped_existing']:,}
- Excluded by manifest: {payload['summary']['excluded']:,}
- Newly processed: {payload['summary']['processed']:,}
- Failed: {payload['summary']['failed']:,}
- New TXT point count: {payload['summary']['txt_point_count_sum']:,}

## Outputs

- TXT directory: `{payload['settings']['txt_output_dir']}`
- Manifest: `{payload['outputs']['manifest']}`
"""
    paths["md"].write_text(md, encoding="utf-8")


def process_one(
    seq: int,
    l1_path: Path,
    args: argparse.Namespace,
    calibration: dict[str, float],
    candidate: dict[str, Any],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
) -> dict[str, Any]:
    started = time.time()
    out_txt = txt_path(args.output_root, seq)
    points, stats = build_l2p_points(
        l1_path,
        seq,
        calibration,
        candidate,
        pos_time,
        pos,
        args.min_range_m,
        args.low_confidence_sec,
        args.progress,
    )
    txt_stats = write_l2p_txt(out_txt, points, args.min_range_m, args.overwrite, args.chunk_size)
    row = {
        "seq": seq,
        "status": "PROCESSED",
        "source_l1": str(l1_path),
        "txt_path": str(out_txt),
        "h5_point_count": int(stats["point_count_h5"]),
        "txt_point_count": int(txt_stats["txt_point_count"]),
        "txt_size_bytes": int(txt_stats["txt_size_bytes"]),
        "pos_good_count": int(stats["pos_good_count"]),
        "pos_success_rate": float(stats["pos_success_rate"]),
        "elapsed_sec": round(time.time() - started, 3),
        "reason": "",
    }
    del points
    gc.collect()
    return row


def run(args: argparse.Namespace) -> None:
    l1_files = discover_l1_files(args.l1_dir, args.start_seq, args.end_seq)
    exclude_path, exclusions = resolve_exclusions(args)
    excluded = [(seq, path) for seq, path in l1_files if seq in exclusions]
    eligible = [(seq, path) for seq, path in l1_files if seq not in exclusions]
    existing = existing_stage8c_sequences(args.output_root)
    if args.only_missing and not args.overwrite:
        work = [(seq, path) for seq, path in eligible if seq not in existing]
    else:
        work = eligible
    skipped_existing = len(eligible) - len(work)
    if args.limit > 0:
        work = work[: args.limit]

    print(f"L1 files discovered: {len(l1_files)}", flush=True)
    print(f"Existing Stage8C TXT files: {len(existing)}", flush=True)
    print(f"Exclusion manifest: {exclude_path} (present={exclude_path.exists()})", flush=True)
    print(f"Excluded L1 files: {len(excluded)}", flush=True)
    for seq, _ in excluded:
        print(f"EXCLUDED {seq:05d}: {exclusions[seq]}", flush=True)
    print(f"Files selected for this run: {len(work)}", flush=True)

    if args.dry_run:
        for seq, path in work[:20]:
            print(f"DRY-RUN {seq:05d}: {path}", flush=True)
        return

    if not work:
        print("No files selected; existing manifests and reports left unchanged.", flush=True)
        return

    candidate = load_stage6i_candidate()
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    pos_time, pos, _ = stage5.load_pos()

    rows: list[dict[str, Any]] = []
    failed = 0
    processed = 0
    for index, (seq, l1_path) in enumerate(work, start=1):
        out_txt = txt_path(args.output_root, seq)
        if out_txt.exists() and not args.overwrite:
            skipped_existing += 1
            rows.append(
                {
                    "seq": seq,
                    "status": "SKIPPED_EXISTS",
                    "source_l1": str(l1_path),
                    "txt_path": str(out_txt),
                    "reason": "TXT already exists",
                }
            )
            continue
        try:
            if args.progress:
                print(f"[{index}/{len(work)}] Processing {seq:05d}: {l1_path.name}", flush=True)
            row = process_one(seq, l1_path, args, calibration, candidate, pos_time, pos)
            rows.append(row)
            processed += 1
            if args.progress:
                print(
                    f"[{index}/{len(work)}] Wrote {row['txt_point_count']:,} TXT points -> {row['txt_path']}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001 - batch manifest should capture per-file failures.
            failed += 1
            rows.append(
                {
                    "seq": seq,
                    "status": "FAILED",
                    "source_l1": str(l1_path),
                    "txt_path": str(out_txt),
                    "reason": repr(exc),
                }
            )
            print(f"[{index}/{len(work)}] FAILED {seq:05d}: {exc}", flush=True)
            if args.stop_on_error:
                break
        finally:
            gc.collect()

    out_manifest = manifest_path(args.output_root)
    write_manifest(out_manifest, rows)
    summary = {
        "l1_files_discovered": len(l1_files),
        "selected_for_run": len(work),
        "skipped_existing": skipped_existing,
        "excluded": len(excluded),
        "processed": processed,
        "failed": failed,
        "txt_point_count_sum": int(sum(int(row.get("txt_point_count") or 0) for row in rows)),
        "txt_size_bytes_sum": int(sum(int(row.get("txt_size_bytes") or 0) for row in rows)),
    }
    payload = {
        "stage_name": "stage8d_ch1_l2p_missing_from_l1",
        "settings": {
            "l1_dir": str(args.l1_dir),
            "output_root": str(args.output_root),
            "txt_output_dir": str(args.output_root / "stage8c_l2p_intermediate" / "txt"),
            "only_missing": args.only_missing,
            "overwrite": args.overwrite,
            "min_range_m": args.min_range_m,
            "low_confidence_sec": args.low_confidence_sec,
            "chunk_size": args.chunk_size,
            "exclude_manifest": str(exclude_path),
            "algorithm_change": "none; existing LADM-II Stage6I candidate and POS rotation reused",
        },
        "summary": summary,
        "excluded_files": [{"seq": seq, "reason": exclusions[seq]} for seq, _ in excluded],
        "outputs": {"manifest": str(out_manifest), **{k: str(v) for k, v in report_paths(args.output_root).items()}},
    }
    write_report(args.output_root, payload)
    print(json.dumps(jsonable({"summary": summary, "manifest": out_manifest}), ensure_ascii=False, indent=2), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fill missing Stage8C L2P-style CloudCompare TXT files directly from CH1 L1 files. "
            "Existing TXT files are skipped by default."
        )
    )
    parser.add_argument("--l1-dir", type=Path, default=DEFAULT_L1_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--exclude-manifest", type=Path,
        default=os.environ.get("AIRBORNE_LIDAR_EXCLUDE_MANIFEST") or None,
        help="CSV with seq and optional reason/action. Defaults to the Stage8C exclusion manifest.",
    )
    parser.add_argument("--start-seq", type=int, default=None)
    parser.add_argument("--end-seq", type=int, default=None)
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N selected files; 0 means no limit.")
    parser.add_argument("--min-range-m", type=float, default=DEFAULT_MIN_RANGE_M)
    parser.add_argument("--low-confidence-sec", type=float, default=DEFAULT_LOW_CONFIDENCE_SEC)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--only-missing", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    return parser


def parse_args() -> argparse.Namespace:
    return build_parser().parse_args()


if __name__ == "__main__":
    run(parse_args())
