from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from project_paths import STAGE_ROOT


DEFAULT_OUTPUT_ROOT = STAGE_ROOT
DEFAULT_SEQ = 111
DEFAULT_MIN_RANGE_M = 30.0
DEFAULT_CHUNK_SIZE = 500_000


def stage7a_manifest_path(output_root: Path) -> Path:
    return output_root / "manifest" / "stage7a_ch1_ladm2_00050_00150_manifest.csv"


def read_stage7a_sequences(output_root: Path) -> list[int]:
    path = stage7a_manifest_path(output_root)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    seqs: list[int] = []
    for row in rows:
        seq = int(row["seq"])
        if source_h5_path(output_root, seq).exists():
            seqs.append(seq)
    return seqs


def write_batch_manifest(output_root: Path, rows: list[dict[str, Any]]) -> Path:
    path = output_root / "stage8c_l2p_intermediate" / "manifest" / "stage8c_ch1_l2p_intermediate_manifest.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return path
    fieldnames = [
        "seq",
        "status",
        "source_h5",
        "h5_path",
        "txt_path",
        "h5_point_count",
        "txt_point_count",
        "h5_size_bytes",
        "txt_size_bytes",
        "elapsed_sec",
        "reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def source_h5_path(output_root: Path, seq: int) -> Path:
    return output_root / "h5" / f"stage7a_{seq:05d}_ch1_ladm2_full_points.h5"


def output_paths(output_root: Path, seq: int) -> dict[str, Path]:
    base = output_root / "stage8c_l2p_intermediate"
    return {
        "h5": base / "h5" / f"stage8c_{seq:05d}_ch1_ladm2_l2p_intermediate.h5",
        "txt": base / "txt" / f"stage8c_{seq:05d}_ch1_ladm2_l2p_offsets_cloudcompare.txt",
        "json": base / "reports" / f"stage8c_{seq:05d}_ch1_ladm2_l2p_intermediate_report.json",
        "md": base / "reports" / f"stage8c_{seq:05d}_ch1_ladm2_l2p_intermediate_report.md",
    }


def ensure_write(path: Path, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def finite_stats(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float64)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return {"count": 0}
    return {
        "count": int(finite.size),
        "min": float(np.min(finite)),
        "median": float(np.median(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
    }


def create_h5(source_h5: Path, out_h5: Path, overwrite: bool) -> dict[str, Any]:
    ensure_write(out_h5, overwrite)
    tmp = out_h5.with_suffix(out_h5.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    stats_samples: dict[str, list[np.ndarray]] = {
        "LIDAR_X": [],
        "LIDAR_Y": [],
        "LIDAR_Z": [],
        "FRD_X": [],
        "FRD_Y": [],
        "FRD_Z": [],
    }
    chunk_size = DEFAULT_CHUNK_SIZE

    with h5py.File(source_h5, "r") as src, h5py.File(tmp, "w") as dst:
        points = src["STAGE7A/CH1/full_points"]
        n = int(points.shape[0])

        l2p = dst.create_group("L2P")
        l2p.attrs["stage"] = "stage8c_00111_l2p_intermediate_export"
        l2p.attrs["source_stage7a_h5"] = str(source_h5)
        l2p.attrs["method_note"] = (
            "Export existing Stage7A intermediate fields only. "
            "LIDAR_X/Y/Z are N/E/D offsets after POS attitude rotation; "
            "POINT_X/Y/Z are also written by adding the matched POS position "
            "to the existing N/E/D offsets, matching the legacy reference H5 convention."
        )
        l2p.attrs["lidar_x_semantics"] = "north_offset_m"
        l2p.attrs["lidar_y_semantics"] = "east_offset_m"
        l2p.attrs["lidar_z_semantics"] = "down_offset_m"
        l2p.attrs["point_x_semantics"] = "pos_northing + north_offset_m"
        l2p.attrs["point_y_semantics"] = "pos_easting + east_offset_m"
        l2p.attrs["point_z_semantics"] = "pos_height - down_offset_m"

        dsets = {
            "GNSS_SEC": l2p.create_dataset("GNSS_SEC", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "LIDAR_X": l2p.create_dataset("LIDAR_X", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "LIDAR_Y": l2p.create_dataset("LIDAR_Y", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "LIDAR_Z": l2p.create_dataset("LIDAR_Z", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "POINT_X": l2p.create_dataset("POINT_X", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POINT_Y": l2p.create_dataset("POINT_Y", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POINT_Z": l2p.create_dataset("POINT_Z", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "FRD_X": l2p.create_dataset("FRD_X", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "FRD_Y": l2p.create_dataset("FRD_Y", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "FRD_Z": l2p.create_dataset("FRD_Z", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "POS_TIME_SEC": l2p.create_dataset("POS_TIME_SEC", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_EASTING": l2p.create_dataset("POS_EASTING", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_NORTHING": l2p.create_dataset("POS_NORTHING", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_HEIGHT": l2p.create_dataset("POS_HEIGHT", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_ROLL": l2p.create_dataset("POS_ROLL", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_PITCH": l2p.create_dataset("POS_PITCH", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_HEADING": l2p.create_dataset("POS_HEADING", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_INTERP_DT": l2p.create_dataset("POS_INTERP_DT", shape=(n,), dtype="f8", compression="gzip", shuffle=True),
            "POS_QUALITY_FLAG": l2p.create_dataset("POS_QUALITY_FLAG", shape=(n,), dtype="u2", compression="gzip", shuffle=True),
            "RANGE_M": l2p.create_dataset("RANGE_M", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "SCAN_ANGLE_DEG": l2p.create_dataset("SCAN_ANGLE_DEG", shape=(n,), dtype="f4", compression="gzip", shuffle=True),
            "POINT_INDEX": l2p.create_dataset("POINT_INDEX", shape=(n,), dtype="u4", compression="gzip", shuffle=True),
            "SOURCE_SEQ": l2p.create_dataset("SOURCE_SEQ", shape=(n,), dtype="u2", compression="gzip", shuffle=True),
        }

        for start in range(0, n, chunk_size):
            stop = min(n, start + chunk_size)
            data = points[start:stop]
            mapping = {
                "GNSS_SEC": data["gps_time"],
                "LIDAR_X": data["north_offset_m"],
                "LIDAR_Y": data["east_offset_m"],
                "LIDAR_Z": data["down_offset_m"],
                "POINT_X": data["pos_northing"].astype(np.float64) + data["north_offset_m"].astype(np.float64),
                "POINT_Y": data["pos_easting"].astype(np.float64) + data["east_offset_m"].astype(np.float64),
                "POINT_Z": data["pos_height"].astype(np.float64) - data["down_offset_m"].astype(np.float64),
                "FRD_X": data["frd_x_m"],
                "FRD_Y": data["frd_y_m"],
                "FRD_Z": data["frd_z_m"],
                "POS_TIME_SEC": data["pos_time_sec"],
                "POS_EASTING": data["pos_easting"],
                "POS_NORTHING": data["pos_northing"],
                "POS_HEIGHT": data["pos_height"],
                "POS_ROLL": data["pos_roll"],
                "POS_PITCH": data["pos_pitch"],
                "POS_HEADING": data["pos_heading"],
                "POS_INTERP_DT": data["pos_interp_dt"],
                "POS_QUALITY_FLAG": data["pos_quality_flag"],
                "RANGE_M": data["range_m"],
                "SCAN_ANGLE_DEG": data["scan_angle_deg"],
                "POINT_INDEX": data["point_index"],
                "SOURCE_SEQ": data["source_seq"],
            }
            for name, values in mapping.items():
                dsets[name][start:stop] = values
            for name in stats_samples:
                vals = mapping[name].astype(np.float64, copy=False)
                step = max(1, vals.size // 10_000)
                stats_samples[name].append(vals[::step][:10_000])

    if out_h5.exists() and overwrite:
        out_h5.unlink()
    tmp.replace(out_h5)

    stats = {
        name: finite_stats(np.concatenate(parts) if parts else np.array([], dtype=np.float64))
        for name, parts in stats_samples.items()
    }
    stats["point_count"] = n
    return stats


def write_txt(source_h5: Path, txt_path: Path, min_range_m: float, overwrite: bool, chunk_size: int) -> dict[str, Any]:
    ensure_write(txt_path, overwrite)
    tmp = txt_path.with_suffix(txt_path.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    count = 0
    with h5py.File(source_h5, "r") as src, tmp.open("w", encoding="utf-8", newline="\n") as f:
        points = src["STAGE7A/CH1/full_points"]
        f.write(
            "POINT_X POINT_Y POINT_Z LIDAR_X LIDAR_Y LIDAR_Z gps_time range_m "
            "scan_angle_deg point_index pos_interp_dt source_seq pos_quality_flag\n"
        )
        for start in range(0, points.shape[0], chunk_size):
            data = points[start : min(points.shape[0], start + chunk_size)]
            keep = (
                np.isfinite(data["north_offset_m"])
                & np.isfinite(data["east_offset_m"])
                & np.isfinite(data["down_offset_m"])
                & np.isfinite(data["gps_time"])
                & (data["range_m"] > min_range_m)
                & (data["pos_quality_flag"] == 0)
            )
            selected = data[keep]
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

    if txt_path.exists() and overwrite:
        txt_path.unlink()
    tmp.replace(txt_path)
    return {"txt_point_count": count, "txt_size_bytes": txt_path.stat().st_size}


def write_reports(paths: dict[str, Path], payload: dict[str, Any]) -> None:
    paths["json"].parent.mkdir(parents=True, exist_ok=True)
    paths["json"].write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    md = f"""# Stage 8C {payload['settings']['seq']:05d} L2P Intermediate Export

## Purpose

Export the existing Stage7A intermediate result as an L2P-style product using the legacy reference H5 convention.

## Coordinate Semantics

- `LIDAR_X`: `north_offset_m`
- `LIDAR_Y`: `east_offset_m`
- `LIDAR_Z`: `down_offset_m`
- `POINT_X`: `pos_northing + north_offset_m`
- `POINT_Y`: `pos_easting + east_offset_m`
- `POINT_Z`: `pos_height - down_offset_m`

No new georeferencing algorithm is introduced here; this file exports existing Stage7A POS-matched fields and the legacy-style POS+offset point coordinates.

## Outputs

- H5: `{payload['outputs']['h5']}`
- TXT: `{payload['outputs']['txt']}`

## Counts

- Full H5 point count: {payload['h5_stats']['point_count']:,}
- TXT point count (`range_m > {payload['settings']['min_range_m']}` and POS-good): {payload['txt_stats']['txt_point_count']:,}
"""
    paths["md"].write_text(md, encoding="utf-8")


def run_one(args: argparse.Namespace, seq: int) -> dict[str, Any]:
    started = time.time()
    source_h5 = source_h5_path(args.output_root, seq)
    if not source_h5.exists():
        raise FileNotFoundError(source_h5)
    paths = output_paths(args.output_root, seq)
    h5_stats = create_h5(source_h5, paths["h5"], args.overwrite)
    txt_stats = write_txt(source_h5, paths["txt"], args.min_range_m, args.overwrite, args.chunk_size)
    payload = {
        "stage_name": "stage8c_ch1_l2p_intermediate_export",
        "source_h5": str(source_h5),
        "settings": {
            "seq": seq,
            "min_range_m": args.min_range_m,
            "chunk_size": args.chunk_size,
            "algorithm_change": "none; export existing Stage7A intermediate fields only",
        },
        "h5_stats": h5_stats,
        "txt_stats": txt_stats,
        "outputs": {k: str(v) for k, v in paths.items()},
        "elapsed_sec": round(time.time() - started, 3),
    }
    write_reports(paths, payload)
    return payload


def run(args: argparse.Namespace) -> None:
    if args.all:
        seqs = read_stage7a_sequences(args.output_root)
    else:
        seqs = [args.seq]

    batch_rows: list[dict[str, Any]] = []
    last_payload: dict[str, Any] | None = None
    for index, seq in enumerate(seqs, start=1):
        if args.progress or args.all:
            print(f"[{index}/{len(seqs)}] exporting {seq:05d}", flush=True)
        started = time.time()
        try:
            payload = run_one(args, seq)
            last_payload = payload
            paths = output_paths(args.output_root, seq)
            batch_rows.append(
                {
                    "seq": seq,
                    "status": "PROCESSED",
                    "source_h5": payload["source_h5"],
                    "h5_path": str(paths["h5"]),
                    "txt_path": str(paths["txt"]),
                    "h5_point_count": payload["h5_stats"]["point_count"],
                    "txt_point_count": payload["txt_stats"]["txt_point_count"],
                    "h5_size_bytes": paths["h5"].stat().st_size,
                    "txt_size_bytes": paths["txt"].stat().st_size,
                    "elapsed_sec": payload["elapsed_sec"],
                    "reason": "",
                }
            )
        except Exception as exc:
            batch_rows.append(
                {
                    "seq": seq,
                    "status": "FAILED",
                    "source_h5": str(source_h5_path(args.output_root, seq)),
                    "h5_path": str(output_paths(args.output_root, seq)["h5"]),
                    "txt_path": str(output_paths(args.output_root, seq)["txt"]),
                    "h5_point_count": "",
                    "txt_point_count": "",
                    "h5_size_bytes": "",
                    "txt_size_bytes": "",
                    "elapsed_sec": round(time.time() - started, 3),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            if args.stop_on_error:
                raise
    manifest = write_batch_manifest(args.output_root, batch_rows)
    processed = sum(1 for row in batch_rows if row["status"] == "PROCESSED")
    failed = sum(1 for row in batch_rows if row["status"] == "FAILED")
    summary = {
        "stage_name": "stage8c_ch1_l2p_intermediate_export",
        "seq_count": len(seqs),
        "processed": processed,
        "failed": failed,
        "manifest": str(manifest),
        "output_root": str(args.output_root / "stage8c_l2p_intermediate"),
    }
    if args.all:
        print(json.dumps(jsonable(summary), ensure_ascii=False, indent=2))
    elif last_payload is not None:
        print(json.dumps(jsonable(last_payload), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(jsonable(summary), ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export 00111 Stage7A POS-matched L2P intermediate offsets and legacy-style POS+offset point coordinates."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--seq", type=int, default=DEFAULT_SEQ)
    parser.add_argument("--all", action="store_true", help="Export every existing Stage7A 00050-00150 candidate.")
    parser.add_argument("--min-range-m", type=float, default=DEFAULT_MIN_RANGE_M)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
