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

METHOD_REGISTRY = [
    {
        "method_id": "STAGE7B_REVIEW_TARGETS",
        "method_name": "Use Stage 7B seam warnings and skipped bad-time gaps as focused audit targets",
        "source_type": "project_qc_rule",
        "source_reference": "C:\\proj_denoising_f3_2.0\\qc\\stage7b_ch1_ladm2_candidate_qc\\stage7b_seam_qc_summary.csv",
        "used_for_delete_or_transform": "no, target selection only",
    },
    {
        "method_id": "POS_ENDPOINT_CONTINUITY",
        "method_name": "Check POS trajectory continuity at file boundaries",
        "source_type": "project_qc_rule",
        "source_reference": "Stage 7A H5 POS match fields",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "EDGE_WINDOW_ROBUST_AUDIT",
        "method_name": "Compare robust first/last window distributions around target boundaries",
        "source_type": "project_qc_rule",
        "source_reference": "Range-filtered and all POS-good Stage 7A H5 points",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "BOUNDARY_CLOUDCOMPARE_EXPORT",
        "method_name": "Export small boundary windows for manual CloudCompare inspection",
        "source_type": "project_qc_artifact",
        "source_reference": "Focused per-boundary TXT files with both sides of the seam",
        "used_for_delete_or_transform": "no, visual QC only",
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_bool(text: str) -> bool:
    return str(text).strip().lower() in {"true", "1", "yes"}


def parse_float(text: str | None, default: float = float("nan")) -> float:
    if text in {None, ""}:
        return default
    return float(text)


def finite_base_mask(points: np.ndarray) -> np.ndarray:
    return (
        np.isfinite(points["gps_time"])
        & np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
        & np.isfinite(points["range_m"])
        & np.isfinite(points["scan_angle_deg"])
        & np.isfinite(points["pos_easting"])
        & np.isfinite(points["pos_northing"])
        & np.isfinite(points["pos_height"])
        & np.isfinite(points["pos_roll"])
        & np.isfinite(points["pos_pitch"])
        & np.isfinite(points["pos_heading"])
        & np.isfinite(points["pos_interp_dt"])
        & (points["pos_quality_flag"] == 0)
    )


def selection_mask(points: np.ndarray, selection: str, min_range_m: float) -> np.ndarray:
    mask = finite_base_mask(points)
    if selection == "range_gt_min":
        mask &= points["range_m"] > min_range_m
    elif selection == "pos_good_all_ranges":
        pass
    else:
        raise ValueError(f"Unknown selection: {selection}")
    return mask


def circular_delta_deg(a: float, b: float) -> float:
    return float((b - a + 180.0) % 360.0 - 180.0)


def circular_median_deg(values: np.ndarray) -> float:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return float("nan")
    radians = np.deg2rad(finite)
    mean = math.atan2(float(np.mean(np.sin(radians))), float(np.mean(np.cos(radians))))
    return float(np.rad2deg(mean) % 360.0)


def stats(values: np.ndarray) -> dict[str, float | int]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flat[np.isfinite(flat)]
    out: dict[str, float | int] = {
        "count": int(flat.size),
        "finite_count": int(finite.size),
        "min": float("nan"),
        "p05": float("nan"),
        "median": float("nan"),
        "p95": float("nan"),
        "max": float("nan"),
        "mean": float("nan"),
        "std": float("nan"),
    }
    if finite.size:
        out.update(
            {
                "min": float(np.min(finite)),
                "p05": float(np.percentile(finite, 5)),
                "median": float(np.median(finite)),
                "p95": float(np.percentile(finite, 95)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "std": float(np.std(finite)),
            }
        )
    return out


def add_stats(row: dict[str, Any], prefix: str, values: np.ndarray) -> None:
    for key, value in stats(values).items():
        row[f"{prefix}_{key}"] = value


def endpoint_point(points: np.ndarray, side: str) -> np.void | None:
    mask = finite_base_mask(points)
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return None
    times = points["gps_time"][idx]
    selected = idx[int(np.argmin(times))] if side == "start" else idx[int(np.argmax(times))]
    return points[selected]


def point_fields(point: np.void | None) -> dict[str, float]:
    if point is None:
        return {}
    return {
        "gps_time": float(point["gps_time"]),
        "easting_m": float(point["easting_m"]),
        "northing_m": float(point["northing_m"]),
        "height_m": float(point["height_m"]),
        "range_m": float(point["range_m"]),
        "scan_angle_deg": float(point["scan_angle_deg"]),
        "pos_easting": float(point["pos_easting"]),
        "pos_northing": float(point["pos_northing"]),
        "pos_height": float(point["pos_height"]),
        "pos_roll": float(point["pos_roll"]),
        "pos_pitch": float(point["pos_pitch"]),
        "pos_heading": float(point["pos_heading"]),
        "pos_interp_dt": float(point["pos_interp_dt"]),
    }


def horizontal(a: dict[str, float], b: dict[str, float], east_key: str = "easting_m", north_key: str = "northing_m") -> float:
    return float(math.hypot(float(b[east_key]) - float(a[east_key]), float(b[north_key]) - float(a[north_key])))


def window_indices(points: np.ndarray, side: str, window_sec: float, selection: str, min_range_m: float) -> np.ndarray:
    mask = selection_mask(points, selection, min_range_m)
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return idx
    times = points["gps_time"][idx]
    if side == "tail":
        edge_time = float(np.max(times))
        keep = times >= edge_time - window_sec
    elif side == "head":
        edge_time = float(np.min(times))
        keep = times <= edge_time + window_sec
    else:
        raise ValueError(side)
    idx = idx[keep]
    order = np.argsort(points["gps_time"][idx], kind="mergesort")
    return idx[order]


def window_stats(points: np.ndarray, idx: np.ndarray) -> dict[str, Any]:
    row: dict[str, Any] = {"count": int(idx.size)}
    if idx.size == 0:
        return row
    row["gps_time_min"] = float(np.min(points["gps_time"][idx]))
    row["gps_time_median"] = float(np.median(points["gps_time"][idx]))
    row["gps_time_max"] = float(np.max(points["gps_time"][idx]))
    for name in [
        "easting_m",
        "northing_m",
        "height_m",
        "range_m",
        "pos_easting",
        "pos_northing",
        "pos_height",
        "pos_roll",
        "pos_pitch",
        "pos_interp_dt",
    ]:
        s = stats(points[name][idx])
        row[f"{name}_median"] = s["median"]
        row[f"{name}_p05"] = s["p05"]
        row[f"{name}_p95"] = s["p95"]
        row[f"{name}_mean"] = s["mean"]
    row["scan_angle_deg_circular_mean"] = circular_median_deg(points["scan_angle_deg"][idx])
    row["pos_heading_circular_mean"] = circular_median_deg(points["pos_heading"][idx])
    return row


def metric_delta(prev: dict[str, Any], curr: dict[str, Any], key: str) -> float:
    a = prev.get(key, float("nan"))
    b = curr.get(key, float("nan"))
    if a in {None, ""} or b in {None, ""}:
        return float("nan")
    return float(b) - float(a)


def pair_window_row(
    from_seq: int,
    to_seq: int,
    boundary_type: str,
    stage7b_status: str,
    prev_points: np.ndarray,
    curr_points: np.ndarray,
    selection: str,
    window_sec: float,
    args: argparse.Namespace,
) -> dict[str, Any]:
    prev_idx = window_indices(prev_points, "tail", window_sec, selection, args.min_range_m)
    curr_idx = window_indices(curr_points, "head", window_sec, selection, args.min_range_m)
    prev = window_stats(prev_points, prev_idx)
    curr = window_stats(curr_points, curr_idx)
    row: dict[str, Any] = {
        "from_seq": from_seq,
        "to_seq": to_seq,
        "boundary_type": boundary_type,
        "stage7b_status": stage7b_status,
        "selection": selection,
        "window_sec": window_sec,
        "prev_count": prev["count"],
        "curr_count": curr["count"],
    }
    if prev["count"] and curr["count"]:
        row.update(
            {
                "window_time_gap_sec": float(curr["gps_time_min"] - prev["gps_time_max"]),
                "window_median_time_gap_sec": float(curr["gps_time_median"] - prev["gps_time_median"]),
                "median_horizontal_gap_m": float(
                    math.hypot(
                        float(curr["easting_m_median"]) - float(prev["easting_m_median"]),
                        float(curr["northing_m_median"]) - float(prev["northing_m_median"]),
                    )
                ),
                "median_height_delta_m": metric_delta(prev, curr, "height_m_median"),
                "p05_height_delta_m": metric_delta(prev, curr, "height_m_p05"),
                "p95_height_delta_m": metric_delta(prev, curr, "height_m_p95"),
                "median_range_delta_m": metric_delta(prev, curr, "range_m_median"),
                "pos_median_horizontal_gap_m": float(
                    math.hypot(
                        float(curr["pos_easting_median"]) - float(prev["pos_easting_median"]),
                        float(curr["pos_northing_median"]) - float(prev["pos_northing_median"]),
                    )
                ),
                "pos_median_height_delta_m": metric_delta(prev, curr, "pos_height_median"),
                "pos_roll_delta_deg": metric_delta(prev, curr, "pos_roll_median"),
                "pos_pitch_delta_deg": metric_delta(prev, curr, "pos_pitch_median"),
                "pos_heading_delta_deg": circular_delta_deg(
                    float(prev["pos_heading_circular_mean"]),
                    float(curr["pos_heading_circular_mean"]),
                ),
                "scan_angle_delta_deg": circular_delta_deg(
                    float(prev["scan_angle_deg_circular_mean"]),
                    float(curr["scan_angle_deg_circular_mean"]),
                ),
                "prev_range_median_m": prev["range_m_median"],
                "curr_range_median_m": curr["range_m_median"],
                "prev_height_median_m": prev["height_m_median"],
                "curr_height_median_m": curr["height_m_median"],
                "prev_scan_angle_circular_mean_deg": prev["scan_angle_deg_circular_mean"],
                "curr_scan_angle_circular_mean_deg": curr["scan_angle_deg_circular_mean"],
            }
        )
    return row


def classify_boundary(summary: dict[str, Any], args: argparse.Namespace) -> str:
    if summary["boundary_type"] == "gap_skipped_bad_time":
        return "ISOLATED_BAD_TIME_GAP"
    if abs(float(summary["lidar_endpoint_time_gap_sec"])) > args.max_adjacent_endpoint_time_gap_sec:
        return "TIME_GAP_REVIEW"
    if float(summary["pos_endpoint_horizontal_gap_m"]) > args.max_pos_endpoint_horizontal_gap_m:
        return "POS_TRAJECTORY_REVIEW"
    if abs(float(summary["pos_endpoint_height_delta_m"])) > args.max_pos_endpoint_height_delta_m:
        return "POS_TRAJECTORY_REVIEW"
    height_005 = abs(float(summary.get("rg30_005_height_median_delta_m", 0.0)))
    height_020 = abs(float(summary.get("rg30_020_height_median_delta_m", 0.0)))
    range_005 = abs(float(summary.get("rg30_005_range_median_delta_m", 0.0)))
    range_020 = abs(float(summary.get("rg30_020_range_median_delta_m", 0.0)))
    if height_005 > args.max_window_height_median_delta_m and height_020 > args.max_window_height_median_delta_m:
        return "WINDOW_DISTRIBUTION_REVIEW"
    if range_005 > args.max_window_range_median_delta_m and range_020 > args.max_window_range_median_delta_m:
        return "WINDOW_RANGE_COMPOSITION_REVIEW"
    return "LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT"


def target_rows(stage7b_seam_csv: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in read_csv_rows(stage7b_seam_csv):
        evaluated = parse_bool(row.get("evaluated", ""))
        passed = parse_bool(row.get("pass", ""))
        if evaluated and passed:
            continue
        boundary_type = "stage7b_warning" if evaluated else "gap_skipped_bad_time"
        rows.append(
            {
                "from_seq": int(row["from_seq"]),
                "to_seq": int(row["to_seq"]),
                "boundary_type": boundary_type,
                "stage7b_status": row.get("status", ""),
                "stage7b_warnings": row.get("warnings", ""),
                "stage7b_reason": row.get("reason", ""),
                "stage7b_endpoint_time_gap_sec": parse_float(row.get("endpoint_time_gap_sec")),
                "stage7b_endpoint_horizontal_gap_m": parse_float(row.get("endpoint_horizontal_gap_m")),
                "stage7b_endpoint_height_delta_m": parse_float(row.get("endpoint_height_delta_m")),
                "stage7b_centroid_horizontal_gap_m": parse_float(row.get("centroid_horizontal_gap_m")),
                "stage7b_centroid_height_mean_delta_m": parse_float(row.get("centroid_height_mean_delta_m")),
            }
        )
    return rows


def manifest_by_seq(manifest_csv: Path) -> dict[int, dict[str, str]]:
    out: dict[int, dict[str, str]] = {}
    for row in read_csv_rows(manifest_csv):
        out[int(row["seq"])] = row
    return out


def load_points(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        return h5["STAGE7A/CH1/full_points"][:]


def export_indices(points: np.ndarray, side: str, window_sec: float, min_range_m: float, max_points: int) -> np.ndarray:
    idx = window_indices(points, "tail" if side == "prev" else "head", window_sec, "range_gt_min", min_range_m)
    if idx.size > max_points > 0:
        keep = np.linspace(0, idx.size - 1, max_points, dtype=np.int64)
        idx = idx[keep]
    return idx


def write_boundary_txt(path: Path, from_seq: int, to_seq: int, prev_points: np.ndarray, curr_points: np.ndarray, args: argparse.Namespace) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    prev_idx = export_indices(prev_points, "prev", args.export_window_sec, args.export_min_range_m, args.export_max_points_per_side)
    curr_idx = export_indices(curr_points, "curr", args.export_window_sec, args.export_min_range_m, args.export_max_points_per_side)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("X Y Z source_seq side_code gps_time range_m scan_angle_deg point_index pos_interp_dt boundary_from boundary_to\n")
        for points, idx, side_code, seq in [(prev_points, prev_idx, 0, from_seq), (curr_points, curr_idx, 1, to_seq)]:
            if idx.size == 0:
                continue
            arr = np.column_stack(
                [
                    points["easting_m"][idx].astype(np.float64),
                    points["northing_m"][idx].astype(np.float64),
                    points["height_m"][idx].astype(np.float64),
                    np.full(idx.size, seq, dtype=np.int64),
                    np.full(idx.size, side_code, dtype=np.int64),
                    points["gps_time"][idx].astype(np.float64),
                    points["range_m"][idx].astype(np.float64),
                    points["scan_angle_deg"][idx].astype(np.float64),
                    points["point_index"][idx].astype(np.int64),
                    points["pos_interp_dt"][idx].astype(np.float64),
                    np.full(idx.size, from_seq, dtype=np.int64),
                    np.full(idx.size, to_seq, dtype=np.int64),
                ]
            )
            np.savetxt(
                f,
                arr,
                fmt=[
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%d",
                    "%d",
                    "%.9f",
                    "%.9f",
                    "%.9f",
                    "%d",
                    "%.9f",
                    "%d",
                    "%d",
                ],
            )
    return int(prev_idx.size + curr_idx.size)


def boundary_summary_row(
    target: dict[str, Any],
    prev_points: np.ndarray,
    curr_points: np.ndarray,
    metric_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    prev_end = point_fields(endpoint_point(prev_points, "end"))
    curr_start = point_fields(endpoint_point(curr_points, "start"))
    row = dict(target)
    row.update(
        {
            "lidar_endpoint_time_gap_sec": float(curr_start["gps_time"] - prev_end["gps_time"]),
            "lidar_endpoint_horizontal_gap_m": horizontal(prev_end, curr_start),
            "lidar_endpoint_height_delta_m": float(curr_start["height_m"] - prev_end["height_m"]),
            "prev_endpoint_range_m": prev_end["range_m"],
            "curr_endpoint_range_m": curr_start["range_m"],
            "prev_endpoint_scan_angle_deg": prev_end["scan_angle_deg"],
            "curr_endpoint_scan_angle_deg": curr_start["scan_angle_deg"],
            "pos_endpoint_horizontal_gap_m": horizontal(prev_end, curr_start, "pos_easting", "pos_northing"),
            "pos_endpoint_height_delta_m": float(curr_start["pos_height"] - prev_end["pos_height"]),
            "pos_endpoint_roll_delta_deg": float(curr_start["pos_roll"] - prev_end["pos_roll"]),
            "pos_endpoint_pitch_delta_deg": float(curr_start["pos_pitch"] - prev_end["pos_pitch"]),
            "pos_endpoint_heading_delta_deg": circular_delta_deg(prev_end["pos_heading"], curr_start["pos_heading"]),
            "endpoint_pos_interp_dt_max_sec": max(prev_end["pos_interp_dt"], curr_start["pos_interp_dt"]),
        }
    )
    rg30_005 = next(
        (
            item
            for item in metric_rows
            if item["from_seq"] == row["from_seq"]
            and item["to_seq"] == row["to_seq"]
            and item["selection"] == "range_gt_min"
            and abs(float(item["window_sec"]) - 0.05) < 1e-9
        ),
        {},
    )
    row["rg30_005_prev_count"] = rg30_005.get("prev_count", 0)
    row["rg30_005_curr_count"] = rg30_005.get("curr_count", 0)
    row["rg30_005_height_median_delta_m"] = rg30_005.get("median_height_delta_m", float("nan"))
    row["rg30_005_range_median_delta_m"] = rg30_005.get("median_range_delta_m", float("nan"))
    row["rg30_005_pos_median_horizontal_gap_m"] = rg30_005.get("pos_median_horizontal_gap_m", float("nan"))
    row["rg30_005_pos_height_median_delta_m"] = rg30_005.get("pos_median_height_delta_m", float("nan"))
    rg30_020 = next(
        (
            item
            for item in metric_rows
            if item["from_seq"] == row["from_seq"]
            and item["to_seq"] == row["to_seq"]
            and item["selection"] == "range_gt_min"
            and abs(float(item["window_sec"]) - 0.20) < 1e-9
        ),
        {},
    )
    row["rg30_020_prev_count"] = rg30_020.get("prev_count", 0)
    row["rg30_020_curr_count"] = rg30_020.get("curr_count", 0)
    row["rg30_020_height_median_delta_m"] = rg30_020.get("median_height_delta_m", float("nan"))
    row["rg30_020_range_median_delta_m"] = rg30_020.get("median_range_delta_m", float("nan"))
    row["rg30_020_pos_median_horizontal_gap_m"] = rg30_020.get("pos_median_horizontal_gap_m", float("nan"))
    row["rg30_020_pos_height_median_delta_m"] = rg30_020.get("pos_median_height_delta_m", float("nan"))
    row["audit_class"] = classify_boundary(row, args)
    return row


def aggregate(boundary_rows: list[dict[str, Any]], export_rows: list[dict[str, Any]]) -> dict[str, Any]:
    class_counts: dict[str, int] = {}
    for row in boundary_rows:
        key = str(row["audit_class"])
        class_counts[key] = class_counts.get(key, 0) + 1
    hard_review = [
        row
        for row in boundary_rows
        if row["audit_class"] in {"TIME_GAP_REVIEW", "POS_TRAJECTORY_REVIEW", "WINDOW_DISTRIBUTION_REVIEW"}
    ]
    return {
        "target_boundary_count": len(boundary_rows),
        "stage7b_warning_boundary_count": int(sum(1 for row in boundary_rows if row["boundary_type"] == "stage7b_warning")),
        "isolated_bad_time_gap_count": int(sum(1 for row in boundary_rows if row["boundary_type"] == "gap_skipped_bad_time")),
        "audit_class_counts": class_counts,
        "hard_review_boundary_count": len(hard_review),
        "time_gap_review_count": int(sum(1 for row in boundary_rows if row["audit_class"] == "TIME_GAP_REVIEW")),
        "pos_trajectory_review_count": int(sum(1 for row in boundary_rows if row["audit_class"] == "POS_TRAJECTORY_REVIEW")),
        "window_distribution_review_count": int(sum(1 for row in boundary_rows if row["audit_class"] == "WINDOW_DISTRIBUTION_REVIEW")),
        "cloudcompare_export_count": len(export_rows),
        "cloudcompare_export_points": int(sum(int(row["export_point_count"]) for row in export_rows)),
        "max_abs_lidar_endpoint_time_gap_sec": float(max((abs(float(row["lidar_endpoint_time_gap_sec"])) for row in boundary_rows), default=float("nan"))),
        "max_pos_endpoint_horizontal_gap_m": float(max((float(row["pos_endpoint_horizontal_gap_m"]) for row in boundary_rows), default=float("nan"))),
        "max_abs_pos_endpoint_height_delta_m": float(max((abs(float(row["pos_endpoint_height_delta_m"])) for row in boundary_rows), default=float("nan"))),
    }


def gate(summary: dict[str, Any]) -> dict[str, Any]:
    if summary["time_gap_review_count"] or summary["pos_trajectory_review_count"]:
        return {
            "conclusion": "REVIEW_TIME_OR_POS_BOUNDARY",
            "ready_for_stage7a_release": False,
            "reason": "At least one focused boundary has a time gap or POS trajectory continuity issue.",
        }
    if summary["window_distribution_review_count"]:
        return {
            "conclusion": "MANUAL_CLOUDCOMPARE_CHECK_REQUIRED",
            "ready_for_stage7a_release": False,
            "reason": "No POS continuity failure was found, but some boundary windows still need visual review.",
        }
    return {
        "conclusion": "PASS_WITH_ISOLATED_BAD_TIME_GAPS",
        "ready_for_stage7a_release": True,
        "reason": "Stage 7B seam warnings are explained by edge/window metrics; skipped bad-time files remain isolated.",
    }


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
    summary = payload["aggregate"]
    gate_payload = payload["gate"]
    outputs = payload["outputs"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    boundary_table = markdown_table(
        payload["boundary_summary"],
        [
            ("from", "from_seq"),
            ("to", "to_seq"),
            ("type", "boundary_type"),
            ("class", "audit_class"),
            ("dt s", "lidar_endpoint_time_gap_sec"),
            ("POS XY", "pos_endpoint_horizontal_gap_m"),
            ("POS dH", "pos_endpoint_height_delta_m"),
            ("rg30 dH", "rg30_005_height_median_delta_m"),
            ("rg30 0.2 dH", "rg30_020_height_median_delta_m"),
            ("rg30 dR", "rg30_005_range_median_delta_m"),
        ],
        max_rows=30,
    )
    export_table = markdown_table(
        payload["cloudcompare_exports"],
        [
            ("from", "from_seq"),
            ("to", "to_seq"),
            ("class", "audit_class"),
            ("points", "export_point_count"),
            ("txt", "txt_path"),
        ],
        max_rows=30,
    )
    content = f"""# Stage 7C CH1 LADM-II Focused Seam Audit

## Gate

- Conclusion: {gate_payload['conclusion']}
- Ready for Stage 7A release: {gate_payload['ready_for_stage7a_release']}
- Reason: {gate_payload['reason']}

## Scope

- Input root: `{payload['inputs']['output_root']}`
- Stage 7B seam CSV: `{payload['inputs']['stage7b_seam_csv']}`
- Target boundaries: {summary['target_boundary_count']}
- Stage 7B warning boundaries: {summary['stage7b_warning_boundary_count']}
- Isolated bad-time gaps: {summary['isolated_bad_time_gap_count']}
- Stage 6G legacy route: still skipped.

## Aggregate

- Audit class counts: `{summary['audit_class_counts']}`
- Hard review boundaries: {summary['hard_review_boundary_count']}
- Time-gap review boundaries: {summary['time_gap_review_count']}
- POS trajectory review boundaries: {summary['pos_trajectory_review_count']}
- Window-distribution review boundaries: {summary['window_distribution_review_count']}
- CloudCompare export files: {summary['cloudcompare_export_count']}
- CloudCompare export points: {summary['cloudcompare_export_points']:,}
- Max endpoint time gap: {summary['max_abs_lidar_endpoint_time_gap_sec']:.9f} s
- Max POS endpoint horizontal gap: {summary['max_pos_endpoint_horizontal_gap_m']:.6f} m
- Max POS endpoint height delta: {summary['max_abs_pos_endpoint_height_delta_m']:.6f} m

## Boundary Summary

{boundary_table}

## CloudCompare Exports

{export_table}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Manual Check Rule

Open the exported boundary TXT files in CloudCompare and color by `source_seq` or `side_code`. The focused TXT files contain only the edge windows around the target boundaries; they do not replace the full Stage 7A TXT files.

## Stop Rule

Stage 7C does not modify Stage 7A H5/LAZ/TXT outputs and does not repair skipped bad-time files.
"""
    md_output = output_root / "reports" / "stage7c_ch1_ladm2_focused_seam_audit_report.md"
    md_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.write_text(content, encoding="utf-8-sig")
    md_project = REPORT_DIR / "stage7c_ch1_ladm2_focused_seam_audit_report.md"
    md_project.parent.mkdir(parents=True, exist_ok=True)
    md_project.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    output_root = args.output_root
    qc_dir = output_root / "qc" / "stage7c_ch1_ladm2_focused_seam_audit"
    txt_dir = qc_dir / "cloudcompare_boundaries"
    qc_dir.mkdir(parents=True, exist_ok=True)
    txt_dir.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (output_root / "reports").mkdir(parents=True, exist_ok=True)

    manifest_csv = args.manifest or output_root / "manifest" / "stage7a_ch1_ladm2_00050_00150_manifest.csv"
    seam_csv = args.stage7b_seam_csv or output_root / "qc" / "stage7b_ch1_ladm2_candidate_qc" / "stage7b_seam_qc_summary.csv"
    manifest = manifest_by_seq(manifest_csv)
    targets = target_rows(seam_csv)

    boundary_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []

    for index, target in enumerate(targets, start=1):
        from_seq = int(target["from_seq"])
        to_seq = int(target["to_seq"])
        if args.progress:
            print(f"[{index}/{len(targets)}] Stage 7C boundary {from_seq:05d}->{to_seq:05d}", flush=True)
        prev_points = load_points(Path(manifest[from_seq]["h5_path"]))
        curr_points = load_points(Path(manifest[to_seq]["h5_path"]))

        pair_metrics: list[dict[str, Any]] = []
        for selection in ["range_gt_min", "pos_good_all_ranges"]:
            for window_sec in args.window_seconds:
                row = pair_window_row(
                    from_seq,
                    to_seq,
                    str(target["boundary_type"]),
                    str(target["stage7b_status"]),
                    prev_points,
                    curr_points,
                    selection,
                    window_sec,
                    args,
                )
                pair_metrics.append(row)
                metric_rows.append(row)

        summary = boundary_summary_row(target, prev_points, curr_points, pair_metrics, args)
        boundary_rows.append(summary)

        txt_name = f"stage7c_boundary_{from_seq:05d}_{to_seq:05d}_{summary['boundary_type']}.txt"
        txt_path = txt_dir / txt_name
        export_count = write_boundary_txt(txt_path, from_seq, to_seq, prev_points, curr_points, args)
        export_rows.append(
            {
                "from_seq": from_seq,
                "to_seq": to_seq,
                "boundary_type": summary["boundary_type"],
                "audit_class": summary["audit_class"],
                "export_point_count": export_count,
                "txt_path": str(txt_path),
                "cloudcompare_note": "Color by source_seq or side_code; side_code 0=from_seq tail, 1=to_seq head.",
            }
        )

        del prev_points, curr_points
        gc.collect()

    boundary_csv = qc_dir / "stage7c_focused_boundary_summary.csv"
    metrics_csv = qc_dir / "stage7c_window_metrics.csv"
    export_csv = qc_dir / "stage7c_cloudcompare_boundary_exports_manifest.csv"
    write_csv(boundary_csv, boundary_rows)
    write_csv(metrics_csv, metric_rows)
    write_csv(export_csv, export_rows)

    summary = aggregate(boundary_rows, export_rows)
    gate_payload = gate(summary)
    report_json_output = output_root / "reports" / "stage7c_ch1_ladm2_focused_seam_audit_report.json"
    report_json_project = REPORT_DIR / "stage7c_ch1_ladm2_focused_seam_audit_report.json"
    payload = {
        "stage_name": "stage7c_ch1_ladm2_focused_seam_audit",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "output_root": str(output_root),
            "stage7a_manifest": str(manifest_csv),
            "stage7b_seam_csv": str(seam_csv),
        },
        "settings": {
            "min_range_m": args.min_range_m,
            "window_seconds": args.window_seconds,
            "export_window_sec": args.export_window_sec,
            "export_min_range_m": args.export_min_range_m,
            "export_max_points_per_side": args.export_max_points_per_side,
            "max_adjacent_endpoint_time_gap_sec": args.max_adjacent_endpoint_time_gap_sec,
            "max_pos_endpoint_horizontal_gap_m": args.max_pos_endpoint_horizontal_gap_m,
            "max_pos_endpoint_height_delta_m": args.max_pos_endpoint_height_delta_m,
            "max_window_height_median_delta_m": args.max_window_height_median_delta_m,
            "max_window_range_median_delta_m": args.max_window_range_median_delta_m,
        },
        "aggregate": summary,
        "gate": gate_payload,
        "boundary_summary": boundary_rows,
        "window_metrics": metric_rows,
        "cloudcompare_exports": export_rows,
        "outputs": {
            "qc_dir": str(qc_dir),
            "boundary_summary_csv": str(boundary_csv),
            "window_metrics_csv": str(metrics_csv),
            "cloudcompare_exports_manifest_csv": str(export_csv),
            "cloudcompare_boundaries_dir": str(txt_dir),
            "report_json": str(report_json_output),
            "report_md": str(output_root / "reports" / "stage7c_ch1_ladm2_focused_seam_audit_report.md"),
            "project_report_json": str(report_json_project),
            "project_report_md": str(REPORT_DIR / "stage7c_ch1_ladm2_focused_seam_audit_report.md"),
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


def window_seconds_arg(text: str) -> list[float]:
    values = [float(item.strip()) for item in text.split(",") if item.strip()]
    if not values:
        raise argparse.ArgumentTypeError("At least one window duration is required.")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 7C: focused audit for Stage 7B warning seams and skipped bad-time gap boundaries.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--stage7b-seam-csv", type=Path, default=None)
    parser.add_argument("--min-range-m", type=float, default=30.0)
    parser.add_argument("--window-seconds", type=window_seconds_arg, default=[0.02, 0.05, 0.20])
    parser.add_argument("--export-window-sec", type=float, default=0.20)
    parser.add_argument("--export-min-range-m", type=float, default=30.0)
    parser.add_argument("--export-max-points-per-side", type=int, default=50_000)
    parser.add_argument("--max-adjacent-endpoint-time-gap-sec", type=float, default=0.01)
    parser.add_argument("--max-pos-endpoint-horizontal-gap-m", type=float, default=1.0)
    parser.add_argument("--max-pos-endpoint-height-delta-m", type=float, default=0.5)
    parser.add_argument("--max-window-height-median-delta-m", type=float, default=5.0)
    parser.add_argument("--max-window-range-median-delta-m", type=float, default=25.0)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
