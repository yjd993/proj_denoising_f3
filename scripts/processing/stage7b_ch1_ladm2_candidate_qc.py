from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_PROJECT_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3",
    )
)
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_STAGE_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0",
    )
)
REPORT_DIR = ROOT / "metadata" / "stage_reports"

REQUIRED_CHAIN_FIELDS = [
    "point_index",
    "source_seq",
    "gnss_sec_raw",
    "gps_time",
    "range_before_m",
    "range_m",
    "coder",
    "scan_angle_deg",
    "frd_x_m",
    "frd_y_m",
    "frd_z_m",
    "pos_time_sec",
    "pos_easting",
    "pos_northing",
    "pos_height",
    "pos_roll",
    "pos_pitch",
    "pos_heading",
    "pos_interp_dt",
    "pos_quality_flag",
    "north_offset_m",
    "east_offset_m",
    "down_offset_m",
    "easting_m",
    "northing_m",
    "height_m",
    "lon",
    "lat",
]

METHOD_REGISTRY = [
    {
        "method_id": "STAGE7A_CHAIN_SCHEMA_QC",
        "method_name": "Verify Stage 7A H5 full-chain fields",
        "source_type": "project_qc_rule",
        "source_reference": "L1 timing/range/scan -> L2 FRD -> POS match -> NED offset -> UTM/geographic coordinate",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "STAGE7A_CONTINUITY_QC",
        "method_name": "Stage 7A candidate continuity QC",
        "source_type": "project_qc_rule",
        "source_reference": "Adjacent processed files in C:\\proj_denoising_f3_2.0, sequences 00050-00150",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "BAD_TIME_ISOLATION",
        "method_name": "Keep skipped bad-time files out of geometry judgment",
        "source_type": "project_gate_rule",
        "source_reference": "Stage 7A skipped non-OK timestamp files; Stage 6M isolated 00113 timestamp corruption",
        "used_for_delete_or_transform": "no, gap annotation only",
    },
]


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_manifest(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["seq"] = int(row["seq"])
        for key in [
            "point_count_l1",
            "point_count_h5",
            "laz_point_count",
            "txt_point_count",
            "h5_size_bytes",
            "laz_size_bytes",
            "txt_size_bytes",
        ]:
            row[key] = int(float(row[key] or 0))
        for key in ["pos_success_rate", "gps_time_min_sec", "gps_time_max_sec", "height_median_m"]:
            row[key] = float(row[key]) if row.get(key) not in {"", None} else float("nan")
    return rows


def finite_stats(values: np.ndarray) -> dict[str, float | int]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flat[np.isfinite(flat)]
    out: dict[str, float | int] = {
        "count": int(flat.size),
        "finite_count": int(finite.size),
        "finite_rate": float(finite.size / max(flat.size, 1)),
        "min": float("nan"),
        "p01": float("nan"),
        "p05": float("nan"),
        "p25": float("nan"),
        "median": float("nan"),
        "p75": float("nan"),
        "p95": float("nan"),
        "p99": float("nan"),
        "max": float("nan"),
        "mean": float("nan"),
        "std": float("nan"),
    }
    if finite.size:
        out.update(
            {
                "min": float(np.min(finite)),
                "p01": float(np.percentile(finite, 1)),
                "p05": float(np.percentile(finite, 5)),
                "p25": float(np.percentile(finite, 25)),
                "median": float(np.median(finite)),
                "p75": float(np.percentile(finite, 75)),
                "p95": float(np.percentile(finite, 95)),
                "p99": float(np.percentile(finite, 99)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "std": float(np.std(finite)),
            }
        )
    return out


def add_prefixed(row: dict[str, Any], prefix: str, values: dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        row[f"{prefix}_{key}"] = values.get(key)


def robust_height_baseline(height: np.ndarray) -> tuple[float, float, float]:
    finite = np.asarray(height, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return float("nan"), float("nan"), float("nan")
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    sigma = 1.4826 * mad if mad > 0 else float("nan")
    return median, mad, sigma


def height_outlier_rate(height: np.ndarray, median: float, sigma: float, z_limit: float) -> float:
    if not np.isfinite(median) or not np.isfinite(sigma) or sigma <= 0:
        return 0.0
    finite = np.asarray(height, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 0.0
    return float(np.count_nonzero(np.abs(finite - median) > z_limit * sigma) / finite.size)


def analysis_mask(points: np.ndarray, min_range_m: float) -> np.ndarray:
    return (
        np.isfinite(points["gps_time"])
        & np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
        & np.isfinite(points["range_m"])
        & np.isfinite(points["scan_angle_deg"])
        & (points["pos_quality_flag"] == 0)
        & (points["range_m"] > min_range_m)
    )


def pos_finite_mask(points: np.ndarray) -> np.ndarray:
    return (
        np.isfinite(points["gps_time"])
        & np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
        & np.isfinite(points["range_m"])
        & np.isfinite(points["scan_angle_deg"])
        & (points["pos_quality_flag"] == 0)
    )


def point_summary(point: np.void) -> dict[str, float]:
    return {
        "gps_time": float(point["gps_time"]),
        "easting_m": float(point["easting_m"]),
        "northing_m": float(point["northing_m"]),
        "height_m": float(point["height_m"]),
        "range_m": float(point["range_m"]),
        "scan_angle_deg": float(point["scan_angle_deg"]),
    }


def cloud_summary(points: np.ndarray) -> dict[str, float | int]:
    return {
        "count": int(points.size),
        "gps_time_min_sec": float(np.min(points["gps_time"])),
        "gps_time_median_sec": float(np.median(points["gps_time"])),
        "gps_time_max_sec": float(np.max(points["gps_time"])),
        "easting_mean_m": float(np.mean(points["easting_m"])),
        "northing_mean_m": float(np.mean(points["northing_m"])),
        "height_mean_m": float(np.mean(points["height_m"])),
        "height_median_m": float(np.median(points["height_m"])),
        "height_p05_m": float(np.percentile(points["height_m"], 5)),
        "height_p95_m": float(np.percentile(points["height_m"], 95)),
        "range_median_m": float(np.median(points["range_m"])),
        "scan_angle_median_deg": float(np.median(points["scan_angle_deg"])),
    }


def distance_2d(a: dict[str, float], b: dict[str, float]) -> float:
    return float(math.hypot(float(b["easting_m"]) - float(a["easting_m"]), float(b["northing_m"]) - float(a["northing_m"])))


def distance_3d(a: dict[str, float], b: dict[str, float]) -> float:
    return float(math.hypot(distance_2d(a, b), float(b["height_m"]) - float(a["height_m"])))


def seam_snapshot(points: np.ndarray, mask: np.ndarray, sample_count: int) -> dict[str, Any]:
    idx = np.flatnonzero(mask).astype(np.int64)
    if idx.size == 0:
        return {"valid_count": 0}
    order = np.argsort(points["gps_time"][idx], kind="mergesort")
    idx = idx[order]
    head = idx[: min(sample_count, idx.size)]
    tail = idx[-min(sample_count, idx.size) :]
    return {
        "valid_count": int(idx.size),
        "start": point_summary(points[idx[0]]),
        "end": point_summary(points[idx[-1]]),
        "head": cloud_summary(points[head]),
        "tail": cloud_summary(points[tail]),
    }


def seam_row(prev_seq: int, curr_seq: int, prev_snap: dict[str, Any], curr_snap: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    if curr_seq != prev_seq + 1:
        return {
            "from_seq": prev_seq,
            "to_seq": curr_seq,
            "sequence_gap": curr_seq - prev_seq - 1,
            "evaluated": False,
            "pass": True,
            "status": "GAP_SKIPPED_BAD_TIME",
            "reason": "not evaluated because one or more skipped bad-time files are isolated from geometry QC",
        }
    if not prev_snap.get("valid_count") or not curr_snap.get("valid_count"):
        return {
            "from_seq": prev_seq,
            "to_seq": curr_seq,
            "sequence_gap": 0,
            "evaluated": True,
            "pass": False,
            "status": "NO_VALID_POINTS",
            "reason": "missing valid analysis points near seam",
        }

    prev_end = prev_snap["end"]
    curr_start = curr_snap["start"]
    prev_tail = prev_snap["tail"]
    curr_head = curr_snap["head"]
    tail_centroid = {
        "easting_m": float(prev_tail["easting_mean_m"]),
        "northing_m": float(prev_tail["northing_mean_m"]),
        "height_m": float(prev_tail["height_mean_m"]),
    }
    head_centroid = {
        "easting_m": float(curr_head["easting_mean_m"]),
        "northing_m": float(curr_head["northing_mean_m"]),
        "height_m": float(curr_head["height_mean_m"]),
    }

    endpoint_time_gap = float(curr_start["gps_time"] - prev_end["gps_time"])
    endpoint_horizontal = distance_2d(prev_end, curr_start)
    endpoint_height_delta = float(curr_start["height_m"] - prev_end["height_m"])
    endpoint_3d = distance_3d(prev_end, curr_start)
    centroid_time_gap = float(curr_head["gps_time_median_sec"] - prev_tail["gps_time_median_sec"])
    centroid_horizontal = distance_2d(tail_centroid, head_centroid)
    centroid_height_delta = float(curr_head["height_mean_m"] - prev_tail["height_mean_m"])
    centroid_3d = distance_3d(tail_centroid, head_centroid)

    warnings: list[str] = []
    if abs(endpoint_time_gap) > args.max_endpoint_time_gap_sec:
        warnings.append("endpoint_time_gap")
    if endpoint_horizontal > args.max_endpoint_horizontal_gap_m:
        warnings.append("endpoint_horizontal_gap")
    if abs(endpoint_height_delta) > args.max_endpoint_height_gap_m:
        warnings.append("endpoint_height_delta")
    if centroid_horizontal > args.max_centroid_horizontal_gap_m:
        warnings.append("centroid_horizontal_gap")
    if abs(centroid_height_delta) > args.max_centroid_height_delta_m:
        warnings.append("centroid_height_delta")

    return {
        "from_seq": prev_seq,
        "to_seq": curr_seq,
        "sequence_gap": 0,
        "evaluated": True,
        "pass": not warnings,
        "status": "PASS" if not warnings else "REVIEW",
        "warnings": ";".join(warnings),
        "endpoint_time_gap_sec": endpoint_time_gap,
        "endpoint_horizontal_gap_m": endpoint_horizontal,
        "endpoint_height_delta_m": endpoint_height_delta,
        "endpoint_3d_gap_m": endpoint_3d,
        "centroid_time_gap_sec": centroid_time_gap,
        "centroid_horizontal_gap_m": centroid_horizontal,
        "centroid_height_mean_delta_m": centroid_height_delta,
        "centroid_height_median_delta_m": float(curr_head["height_median_m"] - prev_tail["height_median_m"]),
        "centroid_height_p05_delta_m": float(curr_head["height_p05_m"] - prev_tail["height_p05_m"]),
        "centroid_height_p95_delta_m": float(curr_head["height_p95_m"] - prev_tail["height_p95_m"]),
        "centroid_3d_gap_m": centroid_3d,
        "tail_count": int(prev_tail["count"]),
        "head_count": int(curr_head["count"]),
    }


def h5_attrs(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as h5:
        proc = h5.get("metadata/processing")
        if proc is None:
            return {}
        return {key: proc.attrs.get(key) for key in proc.attrs.keys()}


def decode_attr(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def per_file_row(manifest_row: dict[str, Any], h5_path: Path, laz_path: Path, txt_path: Path, points: np.ndarray, attrs: dict[str, Any], mask: np.ndarray, z_limit: float) -> dict[str, Any]:
    names = set(points.dtype.names or ())
    missing_fields = [name for name in REQUIRED_CHAIN_FIELDS if name not in names]
    n = int(points.size)
    pos_ok = points["pos_quality_flag"] == 0
    finite_coord = (
        np.isfinite(points["gps_time"])
        & np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
    )
    height = points["height_m"][mask].astype(np.float64)
    height_median, height_mad, height_sigma = robust_height_baseline(height)
    gps = points["gps_time"][np.isfinite(points["gps_time"])].astype(np.float64)
    time_diff_original = np.diff(gps) if gps.size > 1 else np.asarray([], dtype=np.float64)
    time_diff_sorted = np.diff(np.sort(gps)) if gps.size > 1 else np.asarray([], dtype=np.float64)

    row: dict[str, Any] = {
        "source_seq": int(manifest_row["seq"]),
        "source_h5": str(h5_path),
        "source_laz": str(laz_path),
        "source_txt": str(txt_path),
        "point_count_h5": n,
        "manifest_point_count_h5": manifest_row["point_count_h5"],
        "point_count_match_manifest": n == manifest_row["point_count_h5"],
        "analysis_count": int(np.count_nonzero(mask)),
        "analysis_rate": float(np.count_nonzero(mask) / max(n, 1)),
        "pos_success_rate": float(np.count_nonzero(pos_ok) / max(n, 1)),
        "finite_coord_rate": float(np.count_nonzero(finite_coord) / max(n, 1)),
        "missing_chain_fields": ";".join(missing_fields),
        "has_all_chain_fields": not missing_fields,
        "h5_schema": decode_attr(attrs.get("schema", "")),
        "h5_has_pos_match_fields": bool(attrs.get("has_pos_match_fields", False)),
        "laz_exists": laz_path.exists(),
        "txt_exists": txt_path.exists(),
        "laz_size_bytes": laz_path.stat().st_size if laz_path.exists() else 0,
        "txt_size_bytes": txt_path.stat().st_size if txt_path.exists() else 0,
        "height_mad_m": height_mad,
        "height_robust_sigma_m": height_sigma,
        "height_outlier_6mad_rate": height_outlier_rate(height, height_median, height_sigma, z_limit),
        "time_original_nonmonotonic_count": int(np.count_nonzero(time_diff_original <= 0)),
        "time_original_nonmonotonic_rate": float(np.count_nonzero(time_diff_original <= 0) / max(time_diff_original.size, 1))
        if time_diff_original.size
        else 0.0,
    }
    add_prefixed(row, "gps_time_sec", finite_stats(points["gps_time"]), ["min", "median", "max"])
    row["gps_time_duration_sec"] = float(row["gps_time_sec_max"] - row["gps_time_sec_min"])
    add_prefixed(row, "sorted_time_step_sec", finite_stats(time_diff_sorted), ["min", "p01", "median", "p99", "max"])
    add_prefixed(row, "pos_interp_dt_sec", finite_stats(np.abs(points["pos_interp_dt"])), ["min", "median", "p95", "p99", "max"])
    add_prefixed(row, "easting_m", finite_stats(points["easting_m"][mask]), ["min", "median", "max"])
    add_prefixed(row, "northing_m", finite_stats(points["northing_m"][mask]), ["min", "median", "max"])
    add_prefixed(row, "height_m", finite_stats(height), ["min", "p01", "p05", "median", "p95", "p99", "max", "mean", "std"])
    add_prefixed(row, "range_m", finite_stats(points["range_m"][mask]), ["min", "p05", "median", "p95", "max"])
    add_prefixed(row, "scan_angle_deg", finite_stats(points["scan_angle_deg"][mask]), ["min", "median", "max"])
    return row


def scan_angle_bin_rows(seq: int, points: np.ndarray, mask: np.ndarray, bin_deg: float, z_limit: float, min_bin_count: int, warn_rate: float) -> list[dict[str, Any]]:
    height = points["height_m"][mask].astype(np.float64)
    file_median, _, file_sigma = robust_height_baseline(height)
    scan = np.mod(points["scan_angle_deg"].astype(np.float64), 360.0)
    analysis_total = int(np.count_nonzero(mask))
    rows: list[dict[str, Any]] = []
    start = 0.0
    while start < 360.0 - 1e-9:
        end = min(start + bin_deg, 360.0)
        bin_mask = mask & (scan >= start) & (scan < end)
        values = points["height_m"][bin_mask].astype(np.float64)
        count = int(np.count_nonzero(bin_mask))
        stats_h = finite_stats(values)
        shift_rate = height_outlier_rate(values, file_median, file_sigma, z_limit)
        warnings: list[str] = []
        if count < min_bin_count:
            warnings.append("low_count")
        if shift_rate > warn_rate:
            warnings.append("height_distribution_shift")
        row: dict[str, Any] = {
            "source_seq": seq,
            "scan_angle_bin_start_deg": start,
            "scan_angle_bin_end_deg": end,
            "count": count,
            "count_rate_of_analysis": float(count / max(analysis_total, 1)),
            "height_file_robust_shift_rate": shift_rate,
            "height_median_delta_from_file_median_m": float(stats_h["median"] - file_median)
            if np.isfinite(float(stats_h["median"])) and np.isfinite(file_median)
            else float("nan"),
            "warning": ";".join(warnings),
        }
        add_prefixed(row, "height_m", stats_h, ["min", "p05", "median", "p95", "max", "std"])
        add_prefixed(row, "range_m", finite_stats(points["range_m"][bin_mask]), ["median", "p95"])
        rows.append(row)
        start = end
    return rows


def parse_range_bins(text: str) -> list[float]:
    out: list[float] = []
    for item in text.split(","):
        value = item.strip().lower()
        out.append(float("inf") if value in {"inf", "+inf", "infinity"} else float(value))
    if len(out) < 2:
        raise ValueError("At least two range bin edges are required.")
    for a, b in zip(out, out[1:]):
        if not b > a:
            raise ValueError(f"Range bins must be strictly increasing: {text}")
    return out


def range_label(start: float, end: float) -> str:
    return f">={start:g}" if np.isinf(end) else f"{start:g}-{end:g}"


def range_bin_rows(seq: int, points: np.ndarray, base_mask: np.ndarray, edges: list[float], z_limit: float, min_bin_count: int) -> list[dict[str, Any]]:
    ranges = points["range_m"].astype(np.float64)
    rows: list[dict[str, Any]] = []
    base_total = int(np.count_nonzero(base_mask))
    for start, end in zip(edges, edges[1:]):
        if np.isinf(end):
            bin_mask = base_mask & (ranges >= start)
        else:
            bin_mask = base_mask & (ranges >= start) & (ranges < end)
        count = int(np.count_nonzero(bin_mask))
        values = points["height_m"][bin_mask].astype(np.float64)
        bin_median, _, bin_sigma = robust_height_baseline(values)
        warnings: list[str] = []
        if count < min_bin_count:
            warnings.append("low_count")
        row: dict[str, Any] = {
            "source_seq": seq,
            "range_bin_m": range_label(start, end),
            "range_bin_start_m": start,
            "range_bin_end_m": end,
            "count": count,
            "count_rate_of_pos_finite": float(count / max(base_total, 1)),
            "height_internal_outlier_6mad_rate": height_outlier_rate(values, bin_median, bin_sigma, z_limit),
            "warning": ";".join(warnings),
        }
        add_prefixed(row, "height_m", finite_stats(values), ["min", "p05", "median", "p95", "max", "std"])
        add_prefixed(row, "scan_angle_deg", finite_stats(points["scan_angle_deg"][bin_mask]), ["min", "median", "max"])
        rows.append(row)
    return rows


def aggregate_summary(
    manifest_rows: list[dict[str, Any]],
    per_file_rows: list[dict[str, Any]],
    seam_rows: list[dict[str, Any]],
    scan_rows: list[dict[str, Any]],
    range_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    processed = [row for row in manifest_rows if row["status"] == "PROCESSED"]
    skipped = [row for row in manifest_rows if row["status"] != "PROCESSED"]
    evaluated_seams = [row for row in seam_rows if row.get("evaluated")]
    return {
        "manifest_rows": len(manifest_rows),
        "manifest_processed_files": len(processed),
        "manifest_skipped_files": len(skipped),
        "qc_processed_files": len(per_file_rows),
        "skipped_sequences": [int(row["seq"]) for row in skipped],
        "total_points_h5": int(sum(int(row["point_count_h5"]) for row in per_file_rows)),
        "total_analysis_points": int(sum(int(row["analysis_count"]) for row in per_file_rows)),
        "min_pos_success_rate": float(min((float(row["pos_success_rate"]) for row in per_file_rows), default=0.0)),
        "min_analysis_rate": float(min((float(row["analysis_rate"]) for row in per_file_rows), default=0.0)),
        "max_pos_interp_dt_p99_sec": float(max((float(row["pos_interp_dt_sec_p99"]) for row in per_file_rows), default=float("nan"))),
        "max_pos_interp_dt_max_sec": float(max((float(row["pos_interp_dt_sec_max"]) for row in per_file_rows), default=float("nan"))),
        "files_missing_chain_fields": int(sum(1 for row in per_file_rows if row.get("missing_chain_fields"))),
        "files_missing_laz": int(sum(1 for row in per_file_rows if not row.get("laz_exists"))),
        "files_missing_txt": int(sum(1 for row in per_file_rows if not row.get("txt_exists"))),
        "evaluated_adjacent_seams": len(evaluated_seams),
        "skipped_gap_seams": int(sum(1 for row in seam_rows if not row.get("evaluated"))),
        "seam_warning_count": int(sum(1 for row in evaluated_seams if not row.get("pass"))),
        "max_abs_endpoint_time_gap_sec": float(max((abs(float(row["endpoint_time_gap_sec"])) for row in evaluated_seams), default=float("nan"))),
        "max_endpoint_horizontal_gap_m": float(max((float(row["endpoint_horizontal_gap_m"]) for row in evaluated_seams), default=float("nan"))),
        "max_abs_endpoint_height_delta_m": float(max((abs(float(row["endpoint_height_delta_m"])) for row in evaluated_seams), default=float("nan"))),
        "max_centroid_horizontal_gap_m": float(max((float(row["centroid_horizontal_gap_m"]) for row in evaluated_seams), default=float("nan"))),
        "max_abs_centroid_height_delta_m": float(max((abs(float(row["centroid_height_mean_delta_m"])) for row in evaluated_seams), default=float("nan"))),
        "scan_angle_warning_bin_count": int(sum(1 for row in scan_rows if row.get("warning"))),
        "range_warning_bin_count": int(sum(1 for row in range_rows if row.get("warning"))),
    }


def gate_conclusion(summary: dict[str, Any], args: argparse.Namespace) -> tuple[str, str, bool]:
    failures: list[str] = []
    if summary["manifest_processed_files"] != args.expected_processed_files:
        failures.append("processed_file_count")
    if summary["qc_processed_files"] != summary["manifest_processed_files"]:
        failures.append("qc_file_count")
    if summary["files_missing_chain_fields"] > 0:
        failures.append("missing_chain_fields")
    if summary["files_missing_laz"] > 0 or summary["files_missing_txt"] > 0:
        failures.append("missing_laz_or_txt")
    if summary["min_pos_success_rate"] < args.min_pos_success_rate:
        failures.append("pos_success_rate")
    if summary["min_analysis_rate"] < args.min_analysis_rate:
        failures.append("analysis_rate")
    if summary["max_pos_interp_dt_p99_sec"] > args.max_pos_interp_dt_p99_sec:
        failures.append("pos_interp_dt_p99")
    if summary["seam_warning_count"] > 0:
        failures.append("seam_warning")
    if failures:
        return "REVIEW", "Automatic QC completed, but these criteria need review: " + ", ".join(failures), False
    return (
        "PASS",
        "Stage 7A outputs contain the full diagnostic chain, POS interpolation is stable, and adjacent processed seams pass threshold checks.",
        True,
    )


def cluster_skipped_sequences(skipped: list[int]) -> list[list[int]]:
    clusters: list[list[int]] = []
    for seq in sorted(skipped):
        if not clusters or seq != clusters[-1][-1] + 1:
            clusters.append([seq])
        else:
            clusters[-1].append(seq)
    return clusters


def add_sample(sample: dict[int, set[str]], seq: int, reason: str) -> None:
    sample.setdefault(seq, set()).add(reason)


def build_cloudcompare_checklist(
    manifest_rows: list[dict[str, Any]],
    per_file_rows: list[dict[str, Any]],
    seam_rows: list[dict[str, Any]],
    edge_count: int,
) -> list[dict[str, Any]]:
    processed_manifest = {int(row["seq"]): row for row in manifest_rows if row["status"] == "PROCESSED"}
    per_file_by_seq = {int(row["source_seq"]): row for row in per_file_rows}
    processed = sorted(processed_manifest)
    skipped = sorted(int(row["seq"]) for row in manifest_rows if row["status"] != "PROCESSED")
    sample: dict[int, set[str]] = {}

    for seq in processed[:edge_count]:
        add_sample(sample, seq, "first_processed_files")
    for seq in processed[-edge_count:]:
        add_sample(sample, seq, "last_processed_files")
    for seq in range(114, 119):
        if seq in processed_manifest:
            add_sample(sample, seq, "known_stage6l_visual_segment")

    for cluster in cluster_skipped_sequences(skipped):
        before = max((seq for seq in processed if seq < cluster[0]), default=None)
        after = min((seq for seq in processed if seq > cluster[-1]), default=None)
        label = f"around_skipped_{cluster[0]:05d}_{cluster[-1]:05d}"
        if before is not None:
            add_sample(sample, before, label)
        if after is not None:
            add_sample(sample, after, label)

    warning_pairs = [row for row in seam_rows if row.get("evaluated") and not row.get("pass")]
    for row in warning_pairs:
        add_sample(sample, int(row["from_seq"]), "seam_warning_neighbor")
        add_sample(sample, int(row["to_seq"]), "seam_warning_neighbor")

    rows: list[dict[str, Any]] = []
    for seq in sorted(sample):
        m = processed_manifest[seq]
        qc = per_file_by_seq.get(seq, {})
        rows.append(
            {
                "source_seq": seq,
                "reason": ";".join(sorted(sample[seq])),
                "laz_path": m["laz_path"],
                "txt_path": m["txt_path"],
                "h5_path": m["h5_path"],
                "point_count_h5": m["point_count_h5"],
                "txt_point_count": m["txt_point_count"],
                "gps_time_min_sec": qc.get("gps_time_sec_min", m["gps_time_min_sec"]),
                "gps_time_max_sec": qc.get("gps_time_sec_max", m["gps_time_max_sec"]),
                "height_median_m": qc.get("height_m_median", m["height_median_m"]),
            }
        )
    return rows


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], max_rows: int | None = None) -> str:
    selected = rows if max_rows is None else rows[:max_rows]
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in selected:
        values = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                values.append(f"{value:.6g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(payload: dict[str, Any], output_root: Path) -> None:
    gate = payload["gate"]
    summary = payload["aggregate"]
    outputs = payload["outputs"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    per_file_table = markdown_table(
        payload["per_file_summary"],
        [
            ("seq", "source_seq"),
            ("points", "point_count_h5"),
            ("analysis", "analysis_count"),
            ("pos", "pos_success_rate"),
            ("dt p99", "pos_interp_dt_sec_p99"),
            ("t min", "gps_time_sec_min"),
            ("t max", "gps_time_sec_max"),
            ("h med", "height_m_median"),
        ],
        max_rows=20,
    )
    seam_table = markdown_table(
        payload["seam_summary"],
        [
            ("from", "from_seq"),
            ("to", "to_seq"),
            ("eval", "evaluated"),
            ("pass", "pass"),
            ("dt s", "endpoint_time_gap_sec"),
            ("end XY m", "endpoint_horizontal_gap_m"),
            ("end dH m", "endpoint_height_delta_m"),
            ("status", "status"),
            ("warnings", "warnings"),
        ],
        max_rows=30,
    )
    checklist_table = markdown_table(
        payload["cloudcompare_sample_checklist"],
        [
            ("seq", "source_seq"),
            ("reason", "reason"),
            ("txt pts", "txt_point_count"),
            ("h med", "height_median_m"),
        ],
        max_rows=40,
    )
    scan_warnings = [row for row in payload["scan_angle_bin_summary"] if row.get("warning")]
    range_warnings = [row for row in payload["range_bin_summary"] if row.get("warning")]
    scan_warning_table = markdown_table(
        scan_warnings,
        [
            ("seq", "source_seq"),
            ("start", "scan_angle_bin_start_deg"),
            ("end", "scan_angle_bin_end_deg"),
            ("count", "count"),
            ("shift", "height_file_robust_shift_rate"),
            ("warn", "warning"),
        ],
        max_rows=12,
    )
    range_warning_table = markdown_table(
        range_warnings,
        [
            ("seq", "source_seq"),
            ("range", "range_bin_m"),
            ("count", "count"),
            ("internal outlier", "height_internal_outlier_6mad_rate"),
            ("warn", "warning"),
        ],
        max_rows=12,
    )

    content = f"""# Stage 7B CH1 LADM-II Candidate Automatic QC

## Gate

- Conclusion: {gate['conclusion']}
- Ready for review: {gate['ready_for_review']}
- Reason: {gate['reason']}

## Scope

- Input root: `{payload['inputs']['output_root']}`
- Manifest: `{payload['inputs']['stage7a_manifest']}`
- Sequence range: `{payload['scope']['start_seq']:05d}` to `{payload['scope']['end_seq']:05d}`.
- Geometry: not recomputed here; Stage 7B only checks existing Stage 7A outputs.
- Skipped bad-time files stay isolated from geometry judgment: {summary['skipped_sequences']}.

## H5 Chain Schema

Required fields checked in every processed H5:

- L1 timing/range/scan: `gnss_sec_raw`, `gps_time`, `range_before_m`, `range_m`, `coder`, `scan_angle_deg`
- L2 body/FRD: `frd_x_m`, `frd_y_m`, `frd_z_m`
- POS match: `pos_time_sec`, `pos_easting`, `pos_northing`, `pos_height`, `pos_roll`, `pos_pitch`, `pos_heading`, `pos_interp_dt`
- NED offsets: `north_offset_m`, `east_offset_m`, `down_offset_m`
- Final UTM/geographic: `easting_m`, `northing_m`, `height_m`, `lon`, `lat`

## Aggregate

- Manifest processed files: {summary['manifest_processed_files']}
- QC processed files: {summary['qc_processed_files']}
- Manifest skipped files: {summary['manifest_skipped_files']}
- Total H5 points: {summary['total_points_h5']:,}
- Total analysis points (`range_m > {payload['settings']['min_range_m']}` and POS good): {summary['total_analysis_points']:,}
- Min POS success rate: {summary['min_pos_success_rate']:.6%}
- Max POS interpolation dt p99: {summary['max_pos_interp_dt_p99_sec']:.9f} s
- Files missing chain fields: {summary['files_missing_chain_fields']}
- Evaluated adjacent seams: {summary['evaluated_adjacent_seams']}
- Skipped-gap seams: {summary['skipped_gap_seams']}
- Seam warning count: {summary['seam_warning_count']}
- Max endpoint time gap: {summary['max_abs_endpoint_time_gap_sec']:.9f} s
- Max endpoint horizontal gap: {summary['max_endpoint_horizontal_gap_m']:.6f} m
- Max endpoint height delta: {summary['max_abs_endpoint_height_delta_m']:.6f} m
- Scan-angle warning bin count: {summary['scan_angle_warning_bin_count']}
- Range warning bin count: {summary['range_warning_bin_count']}

## Per-File Preview

{per_file_table}

## Seam Preview

{seam_table}

## CloudCompare Sample Checklist Preview

{checklist_table}

## Scan-Angle Warning Bins

{scan_warning_table if scan_warnings else 'No scan-angle warning bins.'}

## Range Warning Bins

{range_warning_table if range_warnings else 'No range warning bins.'}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Per-file summary CSV: `{outputs['per_file_summary_csv']}`
- Seam summary CSV: `{outputs['seam_summary_csv']}`
- Scan-angle bin CSV: `{outputs['scan_angle_bin_csv']}`
- Range bin CSV: `{outputs['range_bin_csv']}`
- CloudCompare checklist CSV: `{outputs['cloudcompare_sample_checklist_csv']}`
- Report JSON: `{outputs['report_json']}`
- Report Markdown: `{outputs['report_md']}`

## Stop Rule

Stage 7B is QC only. It does not repair skipped files, does not run Stage 6G, and does not modify Stage 7A H5/LAZ/TXT outputs.
"""
    report_md_output = output_root / "reports" / "stage7b_ch1_ladm2_candidate_qc_report.md"
    report_md_output.parent.mkdir(parents=True, exist_ok=True)
    report_md_output.write_text(content, encoding="utf-8-sig")
    report_md_project = REPORT_DIR / "stage7b_ch1_ladm2_candidate_qc_report.md"
    report_md_project.parent.mkdir(parents=True, exist_ok=True)
    report_md_project.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    output_root = args.output_root
    qc_dir = output_root / "qc" / "stage7b_ch1_ladm2_candidate_qc"
    qc_dir.mkdir(parents=True, exist_ok=True)
    (output_root / "reports").mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = args.manifest or output_root / "manifest" / "stage7a_ch1_ladm2_00050_00150_manifest.csv"
    manifest_rows = read_manifest(manifest_path)
    processed_rows = [row for row in manifest_rows if row["status"] == "PROCESSED"]
    range_edges = parse_range_bins(args.range_bins)

    per_file_rows: list[dict[str, Any]] = []
    scan_rows: list[dict[str, Any]] = []
    range_rows: list[dict[str, Any]] = []
    snapshots: list[tuple[int, dict[str, Any]]] = []

    for index, row in enumerate(processed_rows, start=1):
        seq = int(row["seq"])
        h5_path = Path(row["h5_path"])
        laz_path = Path(row["laz_path"])
        txt_path = Path(row["txt_path"])
        if args.progress:
            print(f"[{index}/{len(processed_rows)}] Stage 7B QC seq {seq:05d}: {h5_path}", flush=True)
        attrs = h5_attrs(h5_path)
        with h5py.File(h5_path, "r") as h5:
            points = h5["STAGE7A/CH1/full_points"][:]
        mask = analysis_mask(points, args.min_range_m)
        base_mask = pos_finite_mask(points)
        per_file_rows.append(per_file_row(row, h5_path, laz_path, txt_path, points, attrs, mask, args.height_outlier_z))
        snapshots.append((seq, seam_snapshot(points, mask, args.seam_sample_points)))
        scan_rows.extend(
            scan_angle_bin_rows(
                seq,
                points,
                mask,
                args.scan_angle_bin_deg,
                args.height_outlier_z,
                args.min_scan_bin_count,
                args.height_outlier_warn_rate,
            )
        )
        range_rows.extend(range_bin_rows(seq, points, base_mask, range_edges, args.height_outlier_z, args.min_range_bin_count))
        del points
        gc.collect()

    seam_rows = [
        seam_row(prev_seq, curr_seq, prev_snap, curr_snap, args)
        for (prev_seq, prev_snap), (curr_seq, curr_snap) in zip(snapshots, snapshots[1:])
    ]
    checklist_rows = build_cloudcompare_checklist(manifest_rows, per_file_rows, seam_rows, args.sample_edge_count)

    per_file_csv = qc_dir / "stage7b_per_file_qc_summary.csv"
    seam_csv = qc_dir / "stage7b_seam_qc_summary.csv"
    scan_csv = qc_dir / "stage7b_scan_angle_bin_summary.csv"
    range_csv = qc_dir / "stage7b_range_bin_summary.csv"
    checklist_csv = qc_dir / "stage7b_cloudcompare_sample_checklist.csv"
    write_csv(per_file_csv, per_file_rows)
    write_csv(seam_csv, seam_rows)
    write_csv(scan_csv, scan_rows)
    write_csv(range_csv, range_rows)
    write_csv(checklist_csv, checklist_rows)

    summary = aggregate_summary(manifest_rows, per_file_rows, seam_rows, scan_rows, range_rows)
    conclusion, reason, ready = gate_conclusion(summary, args)
    report_json_output = output_root / "reports" / "stage7b_ch1_ladm2_candidate_qc_report.json"
    report_json_project = REPORT_DIR / "stage7b_ch1_ladm2_candidate_qc_report.json"
    payload = {
        "stage_name": "stage7b_ch1_ladm2_candidate_qc",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "output_root": str(output_root),
            "stage7a_manifest": str(manifest_path),
        },
        "scope": {
            "start_seq": min(int(row["seq"]) for row in manifest_rows) if manifest_rows else None,
            "end_seq": max(int(row["seq"]) for row in manifest_rows) if manifest_rows else None,
            "processed_only": True,
            "bad_time_files_are_gap_annotations": True,
        },
        "settings": {
            "min_range_m": args.min_range_m,
            "scan_angle_bin_deg": args.scan_angle_bin_deg,
            "range_bins": args.range_bins,
            "height_outlier_z": args.height_outlier_z,
            "height_outlier_warn_rate": args.height_outlier_warn_rate,
            "min_scan_bin_count": args.min_scan_bin_count,
            "min_range_bin_count": args.min_range_bin_count,
            "seam_sample_points": args.seam_sample_points,
            "min_pos_success_rate": args.min_pos_success_rate,
            "min_analysis_rate": args.min_analysis_rate,
            "max_pos_interp_dt_p99_sec": args.max_pos_interp_dt_p99_sec,
            "max_endpoint_time_gap_sec": args.max_endpoint_time_gap_sec,
            "max_endpoint_horizontal_gap_m": args.max_endpoint_horizontal_gap_m,
            "max_endpoint_height_gap_m": args.max_endpoint_height_gap_m,
            "max_centroid_horizontal_gap_m": args.max_centroid_horizontal_gap_m,
            "max_centroid_height_delta_m": args.max_centroid_height_delta_m,
        },
        "aggregate": summary,
        "per_file_summary": per_file_rows,
        "seam_summary": seam_rows,
        "scan_angle_bin_summary": scan_rows,
        "range_bin_summary": range_rows,
        "cloudcompare_sample_checklist": checklist_rows,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "ready_for_review": ready,
        },
        "outputs": {
            "qc_dir": str(qc_dir),
            "per_file_summary_csv": str(per_file_csv),
            "seam_summary_csv": str(seam_csv),
            "scan_angle_bin_csv": str(scan_csv),
            "range_bin_csv": str(range_csv),
            "cloudcompare_sample_checklist_csv": str(checklist_csv),
            "report_json": str(report_json_output),
            "report_md": str(output_root / "reports" / "stage7b_ch1_ladm2_candidate_qc_report.md"),
            "project_report_json": str(report_json_project),
            "project_report_md": str(REPORT_DIR / "stage7b_ch1_ladm2_candidate_qc_report.md"),
        },
    }
    write_json(report_json_output, payload)
    write_json(report_json_project, payload)
    write_report(payload, output_root)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "aggregate": payload["aggregate"],
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 7B: automatic QC for Stage 7A CH1 LADM-II candidate outputs.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--min-range-m", type=float, default=30.0)
    parser.add_argument("--scan-angle-bin-deg", type=float, default=15.0)
    parser.add_argument("--range-bins", type=str, default="0,30,60,90,120,150,inf")
    parser.add_argument("--height-outlier-z", type=float, default=6.0)
    parser.add_argument("--height-outlier-warn-rate", type=float, default=0.05)
    parser.add_argument("--min-scan-bin-count", type=int, default=1000)
    parser.add_argument("--min-range-bin-count", type=int, default=1000)
    parser.add_argument("--seam-sample-points", type=int, default=5000)
    parser.add_argument("--sample-edge-count", type=int, default=3)
    parser.add_argument("--expected-processed-files", type=int, default=95)
    parser.add_argument("--min-pos-success-rate", type=float, default=0.99)
    parser.add_argument("--min-analysis-rate", type=float, default=0.50)
    parser.add_argument("--max-pos-interp-dt-p99-sec", type=float, default=0.01)
    parser.add_argument("--max-endpoint-time-gap-sec", type=float, default=0.01)
    parser.add_argument("--max-endpoint-horizontal-gap-m", type=float, default=0.50)
    parser.add_argument("--max-endpoint-height-gap-m", type=float, default=0.75)
    parser.add_argument("--max-centroid-horizontal-gap-m", type=float, default=30.0)
    parser.add_argument("--max-centroid-height-delta-m", type=float, default=5.0)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
