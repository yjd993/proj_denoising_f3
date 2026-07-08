from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import plotly.graph_objects as go
from pyproj import Transformer

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag


ROOT = Path(__file__).resolve().parents[2]
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
REFERENCE_L3 = ROOT / "0510_f3" / "L3_DATA" / "L2_cap_00111_20260510190957.h5"
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
OUT_H5_DIR = ROOT / "outputs" / "h5_ch1" / "stage5r2_georef_sample"
OUT_TXT_DIR = ROOT / "outputs" / "txt_ch1" / "stage5r2_cloudcompare"
QC_DIR = ROOT / "outputs" / "qc" / "stage5r2_ch1_georef_validation"
PREVIEW_DIR = ROOT / "outputs" / "preview"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0
ZERO_OFFSET_CANDIDATE_M = 20.486969030907204
MIN_FAR_RANGE_M = 30.0
CRS = "EPSG:32651"
UTM_ZONE = "51N/51R"

METHOD_REGISTRY = [
    {
        "method_id": "DG_ALS_001",
        "method_name": "GNSS/IMU assisted airborne LiDAR direct georeferencing model",
        "source_type": "peer_reviewed_journal",
        "source_reference": "Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_PARAMETER",
        "method_name": "Stage 5G2 CH1 diagnostic return/zero/axis/attitude parameters",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Stage 5G2 exact-time reference-L3 diagnostic; not final production calibration",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "EXACT_TIME_MATCH_QC",
        "method_name": "reference L3 exact GNSS time validation",
        "source_type": "project_qc_rule",
        "source_reference": "Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_RETURN_POLICY",
        "method_name": "CH1 same-time far-return selection policy",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Stage 5R2 range 00050-00100 diagnostic; not final production classification",
        "used_for_delete_or_transform": "yes, diagnostic return selection only",
    },
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def parse_seq_text(value: str) -> int:
    return int(value)


def cap_id(path: Path) -> str:
    return pipe.cap_id_from_l1_path(path)


def output_h5_path(path: Path, repaired: bool, return_policy: str) -> Path:
    suffix = "_time_repaired" if repaired else ""
    policy_suffix = "" if return_policy == "all_far" else f"_{return_policy}"
    return OUT_H5_DIR / f"L3R2_CH1_{cap_id(path)}{suffix}{policy_suffix}.h5"


def output_txt_path(path: Path, repaired: bool, return_policy: str) -> Path:
    suffix = "_time_repaired" if repaired else ""
    policy_suffix = "" if return_policy == "all_far" else f"_{return_policy}"
    return OUT_TXT_DIR / f"L3R2_CH1_{cap_id(path)}{suffix}{policy_suffix}_height_scalar.txt"


def load_manifest() -> tuple[dict[int, stage5.FileInfo], dict[int, dict[str, Any]]]:
    files = stage5.read_manifest(stage5.MANIFEST)
    return {item.seq: item for item in files}, stage5.build_repair_models(files)


def seqs_for_mode(mode: str, seq: int, seq_start: int, seq_end: int) -> list[int]:
    if mode == "single":
        return [seq]
    if mode == "stable":
        return [111, 112, 113, 114, 115]
    if mode == "first12":
        return list(range(2, 14))
    if mode == "range":
        if seq_start > seq_end:
            raise ValueError(f"--seq-start must be <= --seq-end, got {seq_start} > {seq_end}")
        return list(range(seq_start, seq_end + 1))
    raise ValueError(mode)


def interp_pos(lidar_time: np.ndarray, pos_time: np.ndarray, pos: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    return {
        "easting": np.interp(interp_time, pos_time, pos["EASTING"]),
        "northing": np.interp(interp_time, pos_time, pos["NORTHING"]),
        "height": np.interp(interp_time, pos_time, pos["HEIGHT"]),
        "roll": np.interp(interp_time, pos_time, pos["ROLL"]),
        "pitch": np.interp(interp_time, pos_time, pos["PITCH"]),
        "heading": pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time),
    }


def pos_quality_flags(lidar_time: np.ndarray, pos_time: np.ndarray, low_conf_sec: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    no_pos = (lidar_time < pos_time[0]) | (lidar_time > pos_time[-1])
    nearest_dt = pipe.nearest_time_delta_abs(pos_time, np.clip(lidar_time, pos_time[0], pos_time[-1]))
    flags = np.zeros(lidar_time.size, dtype=np.uint16)
    flags[no_pos] |= 1
    flags[nearest_dt > low_conf_sec] |= 2
    return flags, nearest_dt


def return_order_counts(times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if times.size == 0:
        return np.zeros(0, dtype=np.uint16), np.zeros(0, dtype=np.uint16)
    order = np.argsort(times, kind="mergesort")
    sorted_time = times[order]
    _, start_idx, counts = np.unique(sorted_time, return_index=True, return_counts=True)
    sorted_counts = np.repeat(counts, counts.size and counts)
    sorted_order = np.empty(times.size, dtype=np.uint16)
    for start, count in zip(start_idx, counts):
        sorted_order[start : start + count] = np.arange(1, count + 1, dtype=np.uint16)
    out_counts = np.empty(times.size, dtype=np.uint16)
    out_order = np.empty(times.size, dtype=np.uint16)
    out_counts[order] = sorted_counts.astype(np.uint16)
    out_order[order] = sorted_order
    return out_counts, out_order


def nearest_far_indices(times: np.ndarray, ranges: np.ndarray) -> np.ndarray:
    if times.size == 0:
        return np.zeros(0, dtype=np.int64)
    order = np.lexsort((ranges, times))
    sorted_time = times[order]
    first = np.r_[True, sorted_time[1:] != sorted_time[:-1]]
    return np.sort(order[first])


def point_dtype() -> np.dtype:
    return np.dtype(
        [
            ("source_seq", "u2"),
            ("channel", "u1"),
            ("gps_time", "f8"),
            ("easting_m", "f8"),
            ("northing_m", "f8"),
            ("height_m", "f8"),
            ("lon", "f8"),
            ("lat", "f8"),
            ("range_before_m", "f4"),
            ("range_m", "f4"),
            ("scan_angle_deg", "f4"),
            ("pulse_index", "u4"),
            ("pulse_circle", "u2"),
            ("return_count_same_time", "u2"),
            ("return_order_same_time", "u2"),
            ("quality_flag", "u2"),
            ("pos_quality_flag", "u2"),
            ("time_repair_flag", "u1"),
        ]
    )


def transform_stage5r2(
    range_before: np.ndarray,
    coder: np.ndarray,
    pos_arrays: dict[str, np.ndarray],
    calibration: dict[str, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    range_m = (range_before - ZERO_OFFSET_CANDIDATE_M - calibration["intercept"]) / calibration["slope"]
    scan_angle = coder * 360.0 / 65536.0
    model_angle = 360.0 - scan_angle
    bx, by, bz = pipe.f_body_frame_xyz(range_m, model_angle)
    frd = np.column_stack([bx, by, bz])
    roll = np.deg2rad(pos_arrays["roll"])
    pitch = np.deg2rad(pos_arrays["pitch"])
    heading_base = np.deg2rad(pos_arrays["heading"])
    heading = -heading_base + np.pi
    ned = diag.rotate_frd_to_ned(frd, roll, pitch, heading, "YXZ", True)
    return range_m, scan_angle, ned[:, 0], ned[:, 1], ned[:, 2], model_angle


def write_h5(
    path: Path,
    points: np.ndarray,
    info: stage5.FileInfo,
    time_status: str,
    repair_model: dict[str, Any] | None,
    pos_success_rate: float,
    return_policy: str,
    dropped_far_duplicate_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        l3 = h5.create_group("L3")
        metadata = h5.create_group("metadata")
        processing = metadata.create_group("processing")
        pipe.write_str_attr(processing, "stage", "stage5r2_ch1_georef_sample")
        pipe.write_str_attr(processing, "source_l1", rel(info.path))
        pipe.write_str_attr(processing, "crs", CRS)
        pipe.write_str_attr(processing, "utm_zone", UTM_ZONE)
        pipe.write_str_attr(processing, "time_status", time_status)
        pipe.write_str_attr(processing, "calibration_status", "PROJECT_DIAGNOSTIC_PARAMETER_from_stage5g2_not_final_production")
        processing.attrs["source_seq"] = info.seq
        processing.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        processing.attrs["zero_offset_candidate_m"] = ZERO_OFFSET_CANDIDATE_M
        processing.attrs["min_far_range_m"] = MIN_FAR_RANGE_M
        processing.attrs["pos_success_rate"] = float(pos_success_rate)
        processing.attrs["height_median_bias_applied_m"] = 0.0
        pipe.write_str_attr(processing, "return_policy", return_policy)
        processing.attrs["dropped_far_duplicate_count"] = int(dropped_far_duplicate_count)
        if repair_model:
            for key, value in repair_model.items():
                if isinstance(value, str):
                    pipe.write_str_attr(processing, key, value)
                elif isinstance(value, (int, float, np.integer, np.floating)):
                    processing.attrs[key] = value

        for ch in range(1, 5):
            group = l3.create_group(f"CH{ch}")
            if ch == 1:
                group.create_dataset("points", data=points, compression="gzip", compression_opts=4, chunks=True)
            else:
                group.create_dataset("points", shape=(0,), dtype=points.dtype)


def write_cloudcompare_txt(path: Path, points: np.ndarray, max_points: int = 0) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if max_points > 0 and points.size > max_points:
        idx = np.linspace(0, points.size - 1, max_points, dtype=np.int64)
        data = points[idx]
    else:
        data = points
    header = (
        "X Y Z height_m gps_time range_m scan_angle_deg source_seq "
        "time_repair_flag pos_quality_flag return_count_same_time return_order_same_time"
    )
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n")
        for p in data:
            f.write(
                f"{p['easting_m']:.9f} {p['northing_m']:.9f} {p['height_m']:.9f} "
                f"{p['height_m']:.9f} {p['gps_time']:.9f} {float(p['range_m']):.9f} "
                f"{float(p['scan_angle_deg']):.9f} {int(p['source_seq'])} {int(p['time_repair_flag'])} "
                f"{int(p['pos_quality_flag'])} {int(p['return_count_same_time'])} {int(p['return_order_same_time'])}\n"
            )
    return int(data.size)


def make_preview(path: Path, points: np.ndarray, title: str, max_points: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if points.size == 0:
        path.write_text("<html><body>No points</body></html>", encoding="utf-8")
        return
    idx = np.linspace(0, points.size - 1, min(max_points, points.size), dtype=np.int64)
    sample = points[idx]
    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=sample["easting_m"],
                y=sample["northing_m"],
                z=sample["height_m"],
                mode="markers",
                marker={
                    "size": 1.2,
                    "color": sample["height_m"],
                    "colorscale": "Viridis",
                    "opacity": 0.8,
                    "colorbar": {"title": "height_m", "thickness": 14},
                },
                hovertemplate="E:%{x:.3f}<br>N:%{y:.3f}<br>H:%{z:.3f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=title,
        scene={"xaxis_title": "Easting", "yaxis_title": "Northing", "zaxis_title": "Height", "aspectmode": "data"},
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )
    fig.write_html(path, include_plotlyjs="cdn")


def process_one_file(
    info: stage5.FileInfo,
    calibration: dict[str, float],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    transformer: Transformer,
    repair_model: dict[str, Any] | None,
    txt_max_points: int,
    preview_points: int,
    return_policy: str,
) -> tuple[dict[str, Any], np.ndarray]:
    repaired = bool(repair_model and repair_model.get("repair_status") == "REPAIRED_TIME_EXPERIMENT")
    if repair_model and repair_model.get("repair_status") == "UNREPAIRABLE":
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": "UNREPAIRABLE",
            "point_count_l3r2": 0,
            "warning": repair_model.get("repair_reason", "unrepairable time"),
        }, np.zeros(0, dtype=point_dtype())

    with h5py.File(info.path, "r") as h5:
        gnss = h5["GNSS_SEC_CH1"][:].astype(np.float64)
        raw_dist = h5["Photon_CH1_DIST"][:].astype(np.uint32)
        coder = h5["Photon_CH1_CODER"][:].astype(np.float64)
        pulse_index = h5["PULSE_INDEX_CH1"][:].astype(np.uint32)
        pulse_circle = h5["PULSE_CIRCLE_CH1"][:].astype(np.uint32)

    range_before = raw_dist.astype(np.float64) * DIST_FACTOR
    gnss_raw, lidar_time, time_status = stage5.compute_lidar_time(gnss, pulse_index, info, repair_model)
    pos_flags, pos_dt = pos_quality_flags(lidar_time, pos_time)
    far_mask = range_before > MIN_FAR_RANGE_M
    valid = far_mask & (pos_flags == 0) & np.isfinite(range_before)
    pos_success_rate = float(np.count_nonzero(pos_flags == 0) / max(pos_flags.size, 1))

    if not np.any(valid):
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": time_status,
            "point_count_l3r2": 0,
            "near_return_count": int(np.count_nonzero(~far_mask)),
            "pos_success_rate": pos_success_rate,
            "warning": "no valid far-return points with POS",
        }, np.zeros(0, dtype=point_dtype())

    lidar_valid_all = lidar_time[valid]
    range_before_all = range_before[valid]
    coder_all = coder[valid]
    pulse_index_all = pulse_index[valid]
    pulse_circle_all = pulse_circle[valid]
    pos_flags_all = pos_flags[valid]
    return_count_all, return_order_all = return_order_counts(lidar_valid_all)
    if return_policy == "nearest_far":
        selected = nearest_far_indices(lidar_valid_all, range_before_all)
    elif return_policy == "all_far":
        selected = np.arange(lidar_valid_all.size, dtype=np.int64)
    else:
        raise ValueError(f"Unsupported return_policy: {return_policy}")

    lidar_valid = lidar_valid_all[selected]
    range_before_valid = range_before_all[selected]
    coder_valid = coder_all[selected]
    pulse_index_valid = pulse_index_all[selected]
    pulse_circle_valid = pulse_circle_all[selected]
    pos_flags_valid = pos_flags_all[selected]
    return_count = return_count_all[selected]
    return_order = return_order_all[selected]
    dropped_far_duplicate_count = int(lidar_valid_all.size - lidar_valid.size)
    pos_arrays = interp_pos(lidar_valid, pos_time, pos)
    range_m, scan_angle, north_offset, east_offset, down_offset, _ = transform_stage5r2(
        range_before_valid,
        coder_valid,
        pos_arrays,
        calibration,
    )
    easting = pos_arrays["easting"] + east_offset
    northing = pos_arrays["northing"] + north_offset
    height = pos_arrays["height"] - down_offset
    lon, lat = transformer.transform(easting, northing)
    points = np.empty(lidar_valid.size, dtype=point_dtype())
    points["source_seq"] = info.seq
    points["channel"] = 1
    points["gps_time"] = lidar_valid
    points["easting_m"] = easting
    points["northing_m"] = northing
    points["height_m"] = height
    points["lon"] = lon
    points["lat"] = lat
    points["range_before_m"] = range_before_valid.astype(np.float32)
    points["range_m"] = range_m.astype(np.float32)
    points["scan_angle_deg"] = scan_angle.astype(np.float32)
    points["pulse_index"] = pulse_index_valid
    points["pulse_circle"] = pulse_circle_valid.astype(np.uint16)
    points["return_count_same_time"] = return_count
    points["return_order_same_time"] = return_order
    points["quality_flag"] = 0
    points["pos_quality_flag"] = pos_flags_valid
    points["time_repair_flag"] = 1 if time_status == "REPAIRED_TIME_EXPERIMENT" else 0

    h5_path = output_h5_path(info.path, repaired, return_policy)
    txt_path = output_txt_path(info.path, repaired, return_policy)
    policy_suffix = "" if return_policy == "all_far" else f"_{return_policy}"
    preview_path = PREVIEW_DIR / f"stage5r2_{cap_id(info.path)}{'_time_repaired' if repaired else ''}{policy_suffix}_preview.html"
    write_h5(h5_path, points, info, time_status, repair_model, pos_success_rate, return_policy, dropped_far_duplicate_count)
    txt_count = write_cloudcompare_txt(txt_path, points, txt_max_points)
    make_preview(preview_path, points, f"Stage 5R2 CH1 {cap_id(info.path)}", preview_points)

    edge_count = min(max(1, points.size // 10), 50_000)
    summary = {
        "seq": info.seq,
        "file": rel(info.path),
        "status": "PROCESSED",
        "time_status": time_status,
        "output_h5": rel(h5_path),
        "output_txt": rel(txt_path),
        "preview_html": rel(preview_path),
        "point_count_l1": int(gnss.size),
        "point_count_l3r2": int(points.size),
        "txt_point_count": txt_count,
        "near_return_count": int(np.count_nonzero(~far_mask)),
        "far_return_count": int(np.count_nonzero(far_mask)),
        "return_policy": return_policy,
        "dropped_far_duplicate_count": dropped_far_duplicate_count,
        "valid_far_pos_count": int(points.size),
        "pos_success_rate": pos_success_rate,
        "gps_min": float(np.min(points["gps_time"])),
        "gps_max": float(np.max(points["gps_time"])),
        "easting_min": float(np.min(points["easting_m"])),
        "easting_max": float(np.max(points["easting_m"])),
        "northing_min": float(np.min(points["northing_m"])),
        "northing_max": float(np.max(points["northing_m"])),
        "height_min": float(np.min(points["height_m"])),
        "height_max": float(np.max(points["height_m"])),
        "height_median": float(np.median(points["height_m"])),
        "height_first_edge_median": float(np.median(points["height_m"][:edge_count])),
        "height_last_edge_median": float(np.median(points["height_m"][-edge_count:])),
        "max_return_count_same_time": int(np.max(points["return_count_same_time"])),
        "time_repair_flag": int(points["time_repair_flag"][0]) if points.size else 0,
        "warning": "",
    }
    if time_status == "REPAIRED_TIME_EXPERIMENT":
        summary["warning"] = "time repaired by Stage 5 project repair model"
    elif np.min(points["height_m"]) < -100 or np.max(points["height_m"]) > 150:
        summary["warning"] = "height range contains large outliers"
    return summary, points


def reference_validation(max_points: int, calibration: dict[str, float], pos_time: np.ndarray, pos: dict[str, np.ndarray]) -> dict[str, Any]:
    matched = diag.load_matched_data(max_points, "far_return_refnorm", MIN_FAR_RANGE_M)
    pos_arrays = {
        "easting": matched["pos_easting"],
        "northing": matched["pos_northing"],
        "height": matched["pos_height"],
        "roll": matched["roll_deg"],
        "pitch": matched["pitch_deg"],
        "heading": matched["heading_deg"],
    }
    range_m, scan_angle, north, east, down, _ = transform_stage5r2(
        matched["range_before"],
        matched["coder"],
        pos_arrays,
        calibration,
    )
    ref = np.column_stack([matched["ref_north_offset"], matched["ref_east_offset"], matched["ref_down_offset"]])
    pred = np.column_stack([north, east, down])
    diff = pred - ref
    rmse = np.sqrt(np.mean(diff**2, axis=0))
    med = np.median(diff, axis=0)
    p90 = np.percentile(np.abs(diff), 90, axis=0)
    vector = float(np.sqrt(np.mean(np.sum(diff**2, axis=1))))
    return {
        "reference_file": rel(REFERENCE_L3),
        "matched_points_used": int(matched["matched_time"].size),
        "exact_match_total": int(matched["exact_match_total"][0]),
        "match_strategy": "far_return_refnorm",
        "zero_offset_candidate_m": ZERO_OFFSET_CANDIDATE_M,
        "reference_norm_zero_est_m": float(matched["reference_norm_zero_est_m"][0]),
        "north_rmse_m": float(rmse[0]),
        "east_rmse_m": float(rmse[1]),
        "down_rmse_m": float(rmse[2]),
        "vector_rmse_m": vector,
        "north_median_error_m": float(med[0]),
        "east_median_error_m": float(med[1]),
        "down_median_error_m": float(med[2]),
        "north_p90_abs_error_m": float(p90[0]),
        "east_p90_abs_error_m": float(p90[1]),
        "down_p90_abs_error_m": float(p90[2]),
    }


def seam_rows(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    processed = [row for row in file_rows if row.get("status") == "PROCESSED"]
    rows: list[dict[str, Any]] = []
    for prev, curr in zip(processed, processed[1:]):
        rows.append(
            {
                "prev_seq": prev["seq"],
                "next_seq": curr["seq"],
                "time_gap_sec": float(curr["gps_min"] - prev["gps_max"]),
                "height_edge_median_delta_m": float(curr["height_first_edge_median"] - prev["height_last_edge_median"]),
                "prev_time_status": prev["time_status"],
                "next_time_status": curr["time_status"],
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")


def combine_points_for_preview(points_by_file: list[np.ndarray], max_points: int) -> np.ndarray:
    non_empty = [points for points in points_by_file if points.size]
    if not non_empty:
        return np.zeros(0, dtype=point_dtype())
    total = sum(points.size for points in non_empty)
    if max_points <= 0 or total <= max_points:
        return np.concatenate(non_empty)
    sampled: list[np.ndarray] = []
    for points in non_empty:
        count = max(1, int(round(points.size / total * max_points)))
        idx = np.linspace(0, points.size - 1, min(count, points.size), dtype=np.int64)
        sampled.append(points[idx])
    merged = np.concatenate(sampled)
    if merged.size > max_points:
        idx = np.linspace(0, merged.size - 1, max_points, dtype=np.int64)
        merged = merged[idx]
    return merged


def conclusion_for(mode: str, reference_qc: dict[str, Any] | None, seams: list[dict[str, Any]], file_rows: list[dict[str, Any]]) -> tuple[str, str]:
    warnings = [row for row in file_rows if row.get("warning")]
    if mode == "single" and reference_qc:
        if (
            reference_qc["vector_rmse_m"] < 2.5
            and reference_qc["down_rmse_m"] < 1.0
            and reference_qc["down_p90_abs_error_m"] < 1.5
        ):
            return "合理", "00111 与参考 L3 exact-time 验证通过；暂停，人工检查 CloudCompare 后再进入连续段。"
        return "不合理", "00111 与参考 L3 验证未通过；暂停，回到多回波/零位/坐标模型排查。"
    if mode in {"stable", "first12", "range"}:
        max_abs_seam = max([abs(row["height_edge_median_delta_m"]) for row in seams] or [0.0])
        if mode == "stable" and max_abs_seam < 0.5 and not warnings:
            return "合理", "连续段接缝高程中位差满足优先目标；暂停，人工检查 CloudCompare 是否无明显分层。"
        if max_abs_seam < 1.0:
            return "基本合理但有风险", "接缝高程中位差小于风险上限；请重点检查时间修复文件和局部异常。"
        return "不合理", "接缝高程中位差超过 1 m；暂停，不能进入全量。"
    return "基本合理但有风险", "请人工检查输出。"


def write_report(path: Path, payload: dict[str, Any]) -> None:
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    ref_qc = payload.get("reference_validation") or {}
    ref_text = "N/A"
    if ref_qc:
        ref_text = (
            f"vector RMSE={ref_qc['vector_rmse_m']:.6f} m, "
            f"down RMSE={ref_qc['down_rmse_m']:.6f} m, "
            f"down P90={ref_qc['down_p90_abs_error_m']:.6f} m"
        )
    warnings = payload.get("known_warnings") or ["无"]
    content = f"""# Stage 5R2 CH1 小样本坐标重算验证报告

## Gate Conclusion

- 结论：{payload['gate_conclusion']}
- 建议：{payload['recommendation']}
- 阶段：stage5r2_ch1_georef_sample
- 模式：{payload['mode']}
- 处理通道：CH1

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Diagnostic Parameters

- `lidar_time = GNSS_SEC_CH1 + {pipe.DEFAULT_TIME_OFFSET_SEC:g}`
- `zero_offset_candidate_m = {ZERO_OFFSET_CANDIDATE_M:.15f}`
- `min_far_range_m = {MIN_FAR_RANGE_M:g}`
- `return_policy = {payload.get('return_policy', 'all_far')}`
- `angle_mode = 360-angle`
- `axis_mapping = forward=+body_x, right=+body_y, down=+body_z`
- `roll_sign = +1`, `pitch_sign = +1`, `heading_sign = -1`
- `heading_convention = heading+180`
- `rotation_order = YXZ`, `rotation_transpose = true`
- `height_median_bias_applied_m = 0`

## Key Statistics

- Input sequences: `{', '.join(str(x) for x in payload['input_sequences'])}`
- Processed files: {payload['processed_file_count']}
- Total output points: {payload['total_output_points']:,}
- Reference validation: {ref_text}
- Max abs seam height edge median delta: {payload['max_abs_seam_height_edge_median_delta_m']}

## Outputs

- H5 directory: `outputs\\h5_ch1\\stage5r2_georef_sample`
- TXT directory: `outputs\\txt_ch1\\stage5r2_cloudcompare`
- QC directory: `outputs\\qc\\stage5r2_ch1_georef_validation`
- Preview HTML: `{payload.get('merged_preview_html', '')}`

## Known Warnings

{chr(10).join(f"- {warning}" for warning in warnings)}

## Manual Checklist

- CloudCompare 中按第 4 列 `height_m` 着色。
- 检查是否仍有明显双层环状分层。
- 检查建筑、地面、道路/水岸形状是否比旧 v1/v2 更稳定。
- 本阶段通过前，不进入 CH2、去噪或 LAZ。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5R2 CH1 georeference sample validation.")
    parser.add_argument("--mode", choices=["single", "stable", "first12", "range"], required=True)
    parser.add_argument("--seq", type=parse_seq_text, default=111)
    parser.add_argument("--seq-start", type=parse_seq_text, default=50, help="First sequence for --mode range.")
    parser.add_argument("--seq-end", type=parse_seq_text, default=100, help="Last sequence for --mode range.")
    parser.add_argument("--txt-max-points", type=int, default=0, help="0 writes all per-file TXT points.")
    parser.add_argument("--merged-preview-points", type=int, default=300_000)
    parser.add_argument("--html-preview-points", type=int, default=200_000)
    parser.add_argument("--reference-max-points", type=int, default=100_000)
    parser.add_argument(
        "--return-policy",
        choices=["all_far", "nearest_far"],
        default="all_far",
        help="Diagnostic CH1 far-return policy. all_far keeps previous behavior; nearest_far keeps the nearest far return per GNSS time.",
    )
    args = parser.parse_args()

    by_seq, repair_models = load_manifest()
    seqs = seqs_for_mode(args.mode, args.seq, args.seq_start, args.seq_end)
    mode_label = args.mode
    if args.mode == "range":
        mode_label = f"range_{args.seq_start:05d}_{args.seq_end:05d}"
    output_label = mode_label if args.return_policy == "all_far" else f"{mode_label}_{args.return_policy}"
    missing = [seq for seq in seqs if seq not in by_seq]
    if missing:
        raise FileNotFoundError(f"Missing requested sequences in manifest: {missing}")

    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")
    pos_time, pos, _ = stage5.load_pos()
    transformer = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)

    file_rows: list[dict[str, Any]] = []
    points_by_file: list[np.ndarray] = []
    for seq in seqs:
        info = by_seq[seq]
        repair_model = repair_models.get(seq)
        print(f"Processing Stage 5R2 seq {seq:05d}: {info.path.name}", flush=True)
        row, points = process_one_file(
            info,
            calibration,
            pos_time,
            pos,
            transformer,
            repair_model,
            args.txt_max_points,
            args.html_preview_points,
            args.return_policy,
        )
        file_rows.append(row)
        points_by_file.append(points)

    seams = seam_rows(file_rows)
    reference_qc = None
    if 111 in seqs and REFERENCE_L3.exists():
        print("Running 00111 reference validation...", flush=True)
        reference_qc = reference_validation(args.reference_max_points, calibration, pos_time, pos)

    merged_points = combine_points_for_preview(points_by_file, args.merged_preview_points)
    merged_txt_path = OUT_TXT_DIR / f"stage5r2_{output_label}_merged_height_scalar.txt"
    merged_preview_path = PREVIEW_DIR / f"stage5r2_{output_label}_merged_preview.html"
    merged_txt_count = write_cloudcompare_txt(merged_txt_path, merged_points, 0)
    make_preview(merged_preview_path, merged_points, f"Stage 5R2 CH1 {output_label} merged preview", args.html_preview_points)

    file_fields = [
        "seq",
        "file",
        "status",
        "time_status",
        "output_h5",
        "output_txt",
        "preview_html",
        "point_count_l1",
        "point_count_l3r2",
        "txt_point_count",
        "near_return_count",
        "far_return_count",
        "return_policy",
        "dropped_far_duplicate_count",
        "valid_far_pos_count",
        "pos_success_rate",
        "gps_min",
        "gps_max",
        "easting_min",
        "easting_max",
        "northing_min",
        "northing_max",
        "height_min",
        "height_max",
        "height_median",
        "height_first_edge_median",
        "height_last_edge_median",
        "max_return_count_same_time",
        "time_repair_flag",
        "warning",
    ]
    file_summary_path = QC_DIR / f"stage5r2_{output_label}_file_summary.csv"
    seam_summary_path = QC_DIR / f"stage5r2_{output_label}_seam_summary.csv"
    write_csv(file_summary_path, file_rows, file_fields)
    write_csv(
        seam_summary_path,
        seams,
        ["prev_seq", "next_seq", "time_gap_sec", "height_edge_median_delta_m", "prev_time_status", "next_time_status"],
    )
    if reference_qc:
        write_json(QC_DIR / "stage5r2_00111_reference_validation.json", reference_qc)

    processed_file_count = sum(1 for row in file_rows if row.get("status") == "PROCESSED")
    total_output_points = sum(int(row.get("point_count_l3r2") or 0) for row in file_rows)
    max_abs_seam = max([abs(row["height_edge_median_delta_m"]) for row in seams] or [0.0])
    gate_conclusion, recommendation = conclusion_for(args.mode, reference_qc, seams, file_rows)
    known_warnings = [row["warning"] for row in file_rows if row.get("warning")]
    if args.mode == "first12":
        known_warnings.append("first12 is an attitude/takeoff risk review segment; do not use it as full-production acceptance.")
    if args.mode == "range":
        known_warnings.append("range mode is a stability screening segment; it is not full-production acceptance by itself.")
    if args.return_policy == "nearest_far":
        known_warnings.append("nearest_far is a diagnostic same-time return policy; it is not final production classification.")
    if reference_qc:
        known_warnings.append("Reference validation uses L3-informed far-return matching for QC only; production rule remains far-return retention.")

    payload = {
        "stage_name": "stage5r2_ch1_georef_sample",
        "mode": mode_label,
        "mode_requested": args.mode,
        "return_policy": args.return_policy,
        "input_sequences": seqs,
        "gate_conclusion": gate_conclusion,
        "recommendation": recommendation,
        "processed_file_count": processed_file_count,
        "total_output_points": total_output_points,
        "merged_txt": rel(merged_txt_path),
        "merged_txt_point_count": merged_txt_count,
        "merged_preview_html": rel(merged_preview_path),
        "max_abs_seam_height_edge_median_delta_m": float(max_abs_seam),
        "reference_validation": reference_qc,
        "file_summary_csv": rel(file_summary_path),
        "seam_summary_csv": rel(seam_summary_path),
        "method_registry": METHOD_REGISTRY,
        "known_warnings": known_warnings,
    }
    write_json(REPORT_DIR / "stage5r2_ch1_georef_validation_report.json", payload)
    write_report(REPORT_DIR / "stage5r2_ch1_georef_validation_report.md", payload)

    print("Stage 5R2 complete.", flush=True)
    print(f"Conclusion: {gate_conclusion}", flush=True)
    print(f"Report: {REPORT_DIR / 'stage5r2_ch1_georef_validation_report.md'}", flush=True)
    print(f"Merged TXT: {merged_txt_path}", flush=True)


if __name__ == "__main__":
    main()
