from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
STAGE6L_DIR = ROOT / "outputs" / "qc" / "stage6l_ladm2_continuous_segment"
OUT_DIR = ROOT / "outputs" / "qc" / "stage6n_ladm2_continuous_qc"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
STAGE6L_REPORT = REPORT_DIR / "stage6l_ch1_ladm2_continuous_segment_diagnostic_report.json"
STAGE6M_REPORT = REPORT_DIR / "stage6m_00113_timestamp_audit_report.json"

METHOD_REGISTRY = [
    {
        "method_id": "STAGE6G_SKIPPED",
        "method_name": "Skip legacy empirical f_body_frame_xyz propagation",
        "source_type": "project_gate_rule",
        "source_reference": "Stage 6I LADM-II exact-time QC outperformed Stage 6F empirical geometry by a large margin",
        "used_for_delete_or_transform": "no, planning gate only",
    },
    {
        "method_id": "LADM2_CONTINUOUS_QC",
        "method_name": "LADM-II continuous-segment automatic QC",
        "source_type": "project_qc_rule",
        "source_reference": "Stage 6L full-point H5 files for 00114-00118",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "TIMESTAMP_ISOLATION_00113",
        "method_name": "Exclude corrupted 00113 timestamps from geometry decisions",
        "source_type": "project_gate_rule",
        "source_reference": "Stage 6M timestamp audit: GNSS_SEC_CH* equals PULSE_INDEX_CH* for 00113",
        "used_for_delete_or_transform": "no, gate only",
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_seq_from_h5(path: Path) -> int:
    match = re.search(r"stage6l_(\d{5})_ladm2_full_points\.h5$", path.name)
    if not match:
        raise ValueError(f"Cannot parse sequence from {path}")
    return int(match.group(1))


def find_stage6l_h5(start_seq: int, file_count: int) -> list[Path]:
    paths: list[Path] = []
    for seq in range(start_seq, start_seq + file_count):
        path = STAGE6L_DIR / f"stage6l_{seq:05d}_ladm2_full_points.h5"
        if not path.exists():
            raise FileNotFoundError(path)
        paths.append(path)
    return paths


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


def add_prefixed(row: dict[str, Any], prefix: str, values: dict[str, Any], keys: list[str] | None = None) -> None:
    selected = keys if keys is not None else list(values.keys())
    for key in selected:
        row[f"{prefix}_{key}"] = values.get(key)


def robust_height_baseline(height: np.ndarray) -> tuple[float, float, float]:
    finite = height[np.isfinite(height)]
    if finite.size == 0:
        return float("nan"), float("nan"), float("nan")
    median = float(np.median(finite))
    mad = float(np.median(np.abs(finite - median)))
    sigma = 1.4826 * mad if mad > 0 else float("nan")
    return median, mad, sigma


def height_outlier_rate(height: np.ndarray, median: float, sigma: float, z_limit: float) -> float:
    if not np.isfinite(median) or not np.isfinite(sigma) or sigma <= 0:
        return 0.0
    finite = height[np.isfinite(height)]
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


def range_bin_mask(points: np.ndarray) -> np.ndarray:
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
    horizontal = distance_2d(a, b)
    dz = float(b["height_m"]) - float(a["height_m"])
    return float(math.hypot(horizontal, dz))


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


def seam_row(
    prev_seq: int,
    curr_seq: int,
    prev_snap: dict[str, Any],
    curr_snap: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not prev_snap.get("valid_count") or not curr_snap.get("valid_count"):
        return {
            "from_seq": prev_seq,
            "to_seq": curr_seq,
            "valid": False,
            "pass": False,
            "reason": "missing_valid_points",
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
        "valid": True,
        "pass": not warnings,
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


def per_file_row(seq: int, h5_path: Path, points: np.ndarray, mask: np.ndarray, z_limit: float) -> dict[str, Any]:
    n = int(points.size)
    analysis_count = int(np.count_nonzero(mask))
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
        "source_seq": seq,
        "source_h5": rel(h5_path),
        "point_count_h5": n,
        "analysis_count": analysis_count,
        "analysis_rate": float(analysis_count / max(n, 1)),
        "pos_success_rate": float(np.count_nonzero(pos_ok) / max(n, 1)),
        "finite_coord_rate": float(np.count_nonzero(finite_coord) / max(n, 1)),
        "time_original_nonmonotonic_count": int(np.count_nonzero(time_diff_original <= 0)),
        "time_original_nonmonotonic_rate": float(np.count_nonzero(time_diff_original <= 0) / max(time_diff_original.size, 1))
        if time_diff_original.size
        else 0.0,
        "height_mad_m": height_mad,
        "height_robust_sigma_m": height_sigma,
        "height_outlier_6mad_rate": height_outlier_rate(height, height_median, height_sigma, z_limit),
    }
    add_prefixed(row, "gps_time_sec", finite_stats(points["gps_time"]), ["min", "median", "max"])
    row["gps_time_duration_sec"] = float(row["gps_time_sec_max"] - row["gps_time_sec_min"])
    add_prefixed(row, "sorted_time_step_sec", finite_stats(time_diff_sorted), ["min", "p01", "median", "p99", "max"])
    add_prefixed(row, "easting_m", finite_stats(points["easting_m"][mask]), ["min", "median", "max"])
    add_prefixed(row, "northing_m", finite_stats(points["northing_m"][mask]), ["min", "median", "max"])
    add_prefixed(row, "height_m", finite_stats(height), ["min", "p01", "p05", "median", "p95", "p99", "max", "mean", "std"])
    add_prefixed(row, "range_m", finite_stats(points["range_m"][mask]), ["min", "p05", "median", "p95", "max"])
    add_prefixed(row, "scan_angle_deg", finite_stats(points["scan_angle_deg"][mask]), ["min", "median", "max"])
    return row


def scan_angle_bin_rows(
    seq: int,
    points: np.ndarray,
    mask: np.ndarray,
    bin_deg: float,
    z_limit: float,
    min_bin_count: int,
    distribution_shift_warn_rate: float,
) -> list[dict[str, Any]]:
    height = points["height_m"][mask].astype(np.float64)
    file_median, _, file_sigma = robust_height_baseline(height)
    scan = np.mod(points["scan_angle_deg"].astype(np.float64), 360.0)
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
        if shift_rate > distribution_shift_warn_rate:
            warnings.append("height_distribution_shift")
        row = {
            "source_seq": seq,
            "scan_angle_bin_start_deg": start,
            "scan_angle_bin_end_deg": end,
            "count": count,
            "count_rate_of_analysis": float(count / max(np.count_nonzero(mask), 1)),
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
        if value in {"inf", "+inf", "infinity"}:
            out.append(float("inf"))
        else:
            out.append(float(value))
    if len(out) < 2:
        raise ValueError("At least two range bin edges are required.")
    if any(b <= a for a, b in zip(out, out[1:]) if np.isfinite(b)):
        raise ValueError(f"Range bins must be strictly increasing: {text}")
    return out


def range_label(start: float, end: float) -> str:
    if np.isinf(end):
        return f">={start:g}"
    return f"{start:g}-{end:g}"


def range_bin_rows(
    seq: int,
    points: np.ndarray,
    base_mask: np.ndarray,
    edges: list[float],
    z_limit: float,
    min_bin_count: int,
) -> list[dict[str, Any]]:
    ranges = points["range_m"].astype(np.float64)
    rows: list[dict[str, Any]] = []
    for start, end in zip(edges, edges[1:]):
        if np.isinf(end):
            bin_mask = base_mask & (ranges >= start)
        else:
            bin_mask = base_mask & (ranges >= start) & (ranges < end)
        count = int(np.count_nonzero(bin_mask))
        values = points["height_m"][bin_mask].astype(np.float64)
        bin_median, _, bin_sigma = robust_height_baseline(values)
        out_rate = height_outlier_rate(values, bin_median, bin_sigma, z_limit)
        warnings: list[str] = []
        if count < min_bin_count:
            warnings.append("low_count")
        row = {
            "source_seq": seq,
            "range_bin_m": range_label(start, end),
            "range_bin_start_m": start,
            "range_bin_end_m": end,
            "count": count,
            "count_rate_of_pos_finite": float(count / max(np.count_nonzero(base_mask), 1)),
            "height_internal_outlier_6mad_rate": out_rate,
            "warning": ";".join(warnings),
        }
        add_prefixed(row, "height_m", finite_stats(values), ["min", "p05", "median", "p95", "max", "std"])
        add_prefixed(row, "scan_angle_deg", finite_stats(points["scan_angle_deg"][bin_mask]), ["min", "median", "max"])
        rows.append(row)
    return rows


def aggregate_summary(per_file: list[dict[str, Any]], seam_rows: list[dict[str, Any]], scan_rows: list[dict[str, Any]], range_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "file_count": len(per_file),
        "total_points_h5": int(sum(int(row["point_count_h5"]) for row in per_file)),
        "total_analysis_points": int(sum(int(row["analysis_count"]) for row in per_file)),
        "min_pos_success_rate": float(min(float(row["pos_success_rate"]) for row in per_file)) if per_file else 0.0,
        "min_analysis_rate": float(min(float(row["analysis_rate"]) for row in per_file)) if per_file else 0.0,
        "max_abs_endpoint_time_gap_sec": float(max((abs(float(row["endpoint_time_gap_sec"])) for row in seam_rows if row.get("valid")), default=float("nan"))),
        "max_endpoint_horizontal_gap_m": float(max((float(row["endpoint_horizontal_gap_m"]) for row in seam_rows if row.get("valid")), default=float("nan"))),
        "max_abs_endpoint_height_delta_m": float(max((abs(float(row["endpoint_height_delta_m"])) for row in seam_rows if row.get("valid")), default=float("nan"))),
        "max_centroid_horizontal_gap_m": float(max((float(row["centroid_horizontal_gap_m"]) for row in seam_rows if row.get("valid")), default=float("nan"))),
        "max_abs_centroid_height_delta_m": float(max((abs(float(row["centroid_height_mean_delta_m"])) for row in seam_rows if row.get("valid")), default=float("nan"))),
        "seam_warning_count": int(sum(1 for row in seam_rows if not row.get("pass"))),
        "scan_angle_warning_bin_count": int(sum(1 for row in scan_rows if row.get("warning"))),
        "range_warning_bin_count": int(sum(1 for row in range_rows if row.get("warning"))),
    }


def gate_conclusion(summary: dict[str, Any], args: argparse.Namespace) -> tuple[str, str, bool]:
    failures: list[str] = []
    if summary["file_count"] != args.file_count:
        failures.append("file_count")
    if summary["min_pos_success_rate"] < args.min_pos_success_rate:
        failures.append("pos_success_rate")
    if summary["min_analysis_rate"] < args.min_analysis_rate:
        failures.append("analysis_rate")
    if summary["seam_warning_count"] > 0:
        failures.append("seam_warning")
    if failures:
        return (
            "REVIEW",
            "Automatic QC completed, but these criteria need review: " + ", ".join(failures),
            False,
        )
    return (
        "PASS",
        "Automatic QC found full POS coverage, adequate analysis-point density, and no seam discontinuity beyond thresholds.",
        True,
    )


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


def write_report(payload: dict[str, Any]) -> None:
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
            ("t min", "gps_time_sec_min"),
            ("t max", "gps_time_sec_max"),
            ("h med", "height_m_median"),
            ("h p05", "height_m_p05"),
            ("h p95", "height_m_p95"),
        ],
    )
    seam_table = markdown_table(
        payload["seam_summary"],
        [
            ("from", "from_seq"),
            ("to", "to_seq"),
            ("pass", "pass"),
            ("dt s", "endpoint_time_gap_sec"),
            ("end XY m", "endpoint_horizontal_gap_m"),
            ("end dH m", "endpoint_height_delta_m"),
            ("cent XY m", "centroid_horizontal_gap_m"),
            ("cent dH m", "centroid_height_mean_delta_m"),
            ("warnings", "warnings"),
        ],
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

    content = f"""# Stage 6N LADM-II Continuous Segment Automatic QC

## Gate

- Conclusion: {gate['conclusion']}
- Ready for next stage: {gate['ready_for_stage7_candidate']}
- Reason: {gate['reason']}

## Scope

- Stage 6G legacy empirical propagation: skipped by design.
- Input: existing Stage 6L full-point H5 files for {payload['segment']['seq_start']:05d}-{payload['segment']['seq_end']:05d}.
- 00113: excluded from geometry decisions because Stage 6M classified its raw timestamps as corrupted.
- Geometry: not recomputed here; this is QC only.

## Aggregate

- Total H5 points: {summary['total_points_h5']:,}
- Total analysis points (`range_m > {payload['settings']['min_range_m']}` and POS good): {summary['total_analysis_points']:,}
- Min POS success rate: {summary['min_pos_success_rate']:.6%}
- Min analysis-point rate: {summary['min_analysis_rate']:.6%}
- Max endpoint time gap: {summary['max_abs_endpoint_time_gap_sec']:.9f} s
- Max endpoint horizontal gap: {summary['max_endpoint_horizontal_gap_m']:.6f} m
- Max endpoint height delta: {summary['max_abs_endpoint_height_delta_m']:.6f} m
- Seam warning count: {summary['seam_warning_count']}
- Scan-angle warning bin count: {summary['scan_angle_warning_bin_count']}
- Range warning bin count: {summary['range_warning_bin_count']}

## Per-File Summary

{per_file_table}

## Seam Summary

{seam_table}

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
- Report JSON: `{outputs['report_json']}`

## Stop Rule

This stage does not produce final L3/LAZ and does not modify Stage 6L H5 files. Use the PASS/REVIEW result only as a gate for the next LADM-II production-candidate stage.
"""
    report_md = REPORT_DIR / "stage6n_ch1_ladm2_continuous_qc_report.md"
    report_md.parent.mkdir(parents=True, exist_ok=True)
    report_md.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    h5_paths = find_stage6l_h5(args.start_seq, args.file_count)
    stage6l_report = load_json(STAGE6L_REPORT)
    stage6m_report = load_json(STAGE6M_REPORT)
    range_edges = parse_range_bins(args.range_bins)

    per_file_rows: list[dict[str, Any]] = []
    scan_rows: list[dict[str, Any]] = []
    range_rows: list[dict[str, Any]] = []
    seam_rows: list[dict[str, Any]] = []
    snapshots: list[tuple[int, dict[str, Any]]] = []

    for path in h5_paths:
        seq = parse_seq_from_h5(path)
        if args.progress:
            print(f"Reading Stage 6L H5 {seq:05d}: {path}", flush=True)
        with h5py.File(path, "r") as h5:
            points = h5["STAGE6L/CH1/full_points"][:]
        mask = analysis_mask(points, args.min_range_m)
        base_range_mask = range_bin_mask(points)
        per_file_rows.append(per_file_row(seq, path, points, mask, args.height_outlier_z))
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
        range_rows.extend(
            range_bin_rows(
                seq,
                points,
                base_range_mask,
                range_edges,
                args.height_outlier_z,
                args.min_range_bin_count,
            )
        )

    for (prev_seq, prev_snap), (curr_seq, curr_snap) in zip(snapshots, snapshots[1:]):
        seam_rows.append(seam_row(prev_seq, curr_seq, prev_snap, curr_snap, args))

    per_file_csv = OUT_DIR / "stage6n_per_file_qc_summary.csv"
    seam_csv = OUT_DIR / "stage6n_seam_qc_summary.csv"
    scan_csv = OUT_DIR / "stage6n_scan_angle_bin_summary.csv"
    range_csv = OUT_DIR / "stage6n_range_bin_summary.csv"
    write_csv(per_file_csv, per_file_rows)
    write_csv(seam_csv, seam_rows)
    write_csv(scan_csv, scan_rows)
    write_csv(range_csv, range_rows)

    summary = aggregate_summary(per_file_rows, seam_rows, scan_rows, range_rows)
    conclusion, reason, ready = gate_conclusion(summary, args)
    report_json = REPORT_DIR / "stage6n_ch1_ladm2_continuous_qc_report.json"
    payload = {
        "stage_name": "stage6n_ch1_ladm2_continuous_qc",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "stage6l_dir": rel(STAGE6L_DIR),
            "stage6l_report": rel(STAGE6L_REPORT),
            "stage6m_report": rel(STAGE6M_REPORT),
            "source_h5": [rel(path) for path in h5_paths],
        },
        "segment": {
            "seq_start": args.start_seq,
            "seq_end": args.start_seq + args.file_count - 1,
            "file_count": args.file_count,
            "excluded_sequences": [113],
        },
        "settings": {
            "min_range_m": args.min_range_m,
            "scan_angle_bin_deg": args.scan_angle_bin_deg,
            "range_bins": args.range_bins,
            "height_outlier_z": args.height_outlier_z,
            "height_outlier_warn_rate": args.height_outlier_warn_rate,
            "min_range_bin_count": args.min_range_bin_count,
            "seam_sample_points": args.seam_sample_points,
            "min_pos_success_rate": args.min_pos_success_rate,
            "min_analysis_rate": args.min_analysis_rate,
            "max_endpoint_time_gap_sec": args.max_endpoint_time_gap_sec,
            "max_endpoint_horizontal_gap_m": args.max_endpoint_horizontal_gap_m,
            "max_endpoint_height_gap_m": args.max_endpoint_height_gap_m,
            "max_centroid_horizontal_gap_m": args.max_centroid_horizontal_gap_m,
            "max_centroid_height_delta_m": args.max_centroid_height_delta_m,
        },
        "prior_gates": {
            "stage6l_gate": stage6l_report.get("gate", {}),
            "stage6m_gate": stage6m_report.get("gate", {}),
            "stage6g_status": "skipped",
            "stage6g_reason": "Do not continue legacy empirical f_body_frame_xyz() propagation after Stage 6I LADM-II improvement.",
        },
        "aggregate": summary,
        "per_file_summary": per_file_rows,
        "seam_summary": seam_rows,
        "scan_angle_bin_summary": scan_rows,
        "range_bin_summary": range_rows,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "ready_for_stage7_candidate": ready,
        },
        "outputs": {
            "per_file_summary_csv": rel(per_file_csv),
            "seam_summary_csv": rel(seam_csv),
            "scan_angle_bin_csv": rel(scan_csv),
            "range_bin_csv": rel(range_csv),
            "report_json": rel(report_json),
            "report_md": rel(REPORT_DIR / "stage6n_ch1_ladm2_continuous_qc_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)
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
    parser = argparse.ArgumentParser(description="Stage 6N: automatic QC for Stage 6L LADM-II continuous segment H5 outputs.")
    parser.add_argument("--start-seq", type=int, default=114)
    parser.add_argument("--file-count", type=int, default=5)
    parser.add_argument("--min-range-m", type=float, default=30.0)
    parser.add_argument("--scan-angle-bin-deg", type=float, default=15.0)
    parser.add_argument("--range-bins", type=str, default="0,30,60,90,120,150,inf")
    parser.add_argument("--height-outlier-z", type=float, default=6.0)
    parser.add_argument("--height-outlier-warn-rate", type=float, default=0.05)
    parser.add_argument("--min-scan-bin-count", type=int, default=1000)
    parser.add_argument("--min-range-bin-count", type=int, default=1000)
    parser.add_argument("--seam-sample-points", type=int, default=5000)
    parser.add_argument("--min-pos-success-rate", type=float, default=0.99)
    parser.add_argument("--min-analysis-rate", type=float, default=0.50)
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
