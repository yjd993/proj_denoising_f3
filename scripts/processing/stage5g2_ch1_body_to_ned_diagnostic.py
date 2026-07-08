from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
from typing import Any

import h5py
import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5


ROOT = Path(__file__).resolve().parents[2]
L1_SAMPLE = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00111_20260510190957.h5"
REFERENCE_L3 = ROOT / "0510_f3" / "L3_DATA" / "L2_cap_00111_20260510190957.h5"
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
QC_DIR = ROOT / "outputs" / "qc" / "stage5g2_body_to_ned"

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0
ZERO_STRATEGIES = ["NONE", "Z0_auto", "Z1_fixed_calib_zero_offset", "Z2_ref_norm_median_zero"]
ANGLE_MODES = ["360-angle", "angle", "angle+180", "180-angle"]
ROTATION_ORDERS = ["ZYX", "ZXY", "YXZ"]
HEADING_CONVENTIONS = ["heading", "360-heading", "heading+180", "heading-90", "90-heading"]
BORESIGHT_GRID_DEG = [-5.0, -2.0, 0.0, 2.0, 5.0]
LEVER_GRID_M = [-2.0, 0.0, 2.0]

METHOD_REGISTRY = [
    {
        "method_id": "DG_ALS_001",
        "method_name": "GNSS/IMU assisted airborne LiDAR direct georeferencing diagnostic",
        "source_type": "peer_reviewed_journal",
        "source_reference": "Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006",
        "used_for_delete_or_transform": "no, diagnostic only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_PARAMETER",
        "method_name": "candidate axis/sign/angle/attitude/boresight/lever-arm conventions",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Project diagnostic candidates only; not final calibration",
        "used_for_delete_or_transform": "no, diagnostic only",
    },
    {
        "method_id": "EXACT_TIME_MATCH_QC",
        "method_name": "exact GNSS time intersection against existing L3 reference",
        "source_type": "project_qc_rule",
        "source_reference": "Existing project L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18",
        "used_for_delete_or_transform": "no, diagnostic only",
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
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")


def stratified_indices(size: int, count: int) -> np.ndarray:
    if size <= 0:
        return np.zeros(0, dtype=np.int64)
    if count <= 0 or count >= size:
        return np.arange(size, dtype=np.int64)
    return np.linspace(0, size - 1, count, dtype=np.int64)


def load_reference() -> dict[str, np.ndarray]:
    with h5py.File(REFERENCE_L3, "r") as h5:
        return {
            "time": h5["GNSS_SEC"][:].astype(np.float64),
            "point_x": h5["POINT_X"][:].astype(np.float64),
            "point_y": h5["POINT_Y"][:].astype(np.float64),
            "point_z": h5["POINT_Z"][:].astype(np.float64),
            "lidar_x": h5["LIDAR_X"][:].astype(np.float64),
            "lidar_y": h5["LIDAR_Y"][:].astype(np.float64),
            "lidar_z": h5["LIDAR_Z"][:].astype(np.float64),
        }


def load_l1_all() -> dict[str, np.ndarray]:
    with h5py.File(L1_SAMPLE, "r") as h5:
        return {
            "gnss": h5["GNSS_SEC_CH1"][:].astype(np.float64),
            "raw_dist": h5["Photon_CH1_DIST"][:].astype(np.uint32),
            "coder": h5["Photon_CH1_CODER"][:].astype(np.float64),
        }


def exact_reference_match(lidar_time: np.ndarray, reference_time: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _, l1_idx, ref_idx = np.intersect1d(lidar_time, reference_time, assume_unique=False, return_indices=True)
    return l1_idx.astype(np.int64), ref_idx.astype(np.int64)


def load_matched_data(max_matched_points: int, match_return_strategy: str, min_far_range_m: float) -> dict[str, np.ndarray]:
    reference = load_reference()
    l1 = load_l1_all()
    lidar_time = l1["gnss"] + pipe.DEFAULT_TIME_OFFSET_SEC
    sort_idx = np.argsort(lidar_time, kind="mergesort")
    sorted_time = lidar_time[sort_idx]
    sorted_range = l1["raw_dist"][sort_idx].astype(np.float64) * DIST_FACTOR
    sorted_coder = l1["coder"][sort_idx].astype(np.float64)

    left = np.searchsorted(sorted_time, reference["time"], side="left")
    right = np.searchsorted(sorted_time, reference["time"], side="right")
    ref_available = np.flatnonzero(right > left).astype(np.int64)
    exact_match_total = int(ref_available.size)
    if ref_available.size < 100:
        raise RuntimeError(f"Too few exact matched reference points: {ref_available.size}")
    if ref_available.size > max_matched_points:
        ref_idx = ref_available[stratified_indices(ref_available.size, max_matched_points)]
    else:
        ref_idx = ref_available

    ref_norm_all = np.sqrt(
        reference["lidar_x"] ** 2 + reference["lidar_y"] ** 2 + reference["lidar_z"] ** 2
    )
    selected_range = np.empty(ref_idx.size, dtype=np.float64)
    selected_coder = np.empty(ref_idx.size, dtype=np.float64)
    selected_candidate_count = np.empty(ref_idx.size, dtype=np.int16)
    selected_far_candidate_count = np.empty(ref_idx.size, dtype=np.int16)

    for out_idx, ridx in enumerate(ref_idx):
        lo = int(left[ridx])
        hi = int(right[ridx])
        ranges = sorted_range[lo:hi]
        coders = sorted_coder[lo:hi]
        selected_candidate_count[out_idx] = hi - lo
        far_mask = ranges > min_far_range_m
        selected_far_candidate_count[out_idx] = int(np.count_nonzero(far_mask))
        if match_return_strategy == "first_time_record":
            local_idx = 0
        elif match_return_strategy == "far_return_refnorm":
            if np.any(far_mask):
                candidate_ranges = ranges[far_mask]
                candidate_coders = coders[far_mask]
            else:
                candidate_ranges = ranges
                candidate_coders = coders
            local_idx = int(np.argmin(np.abs(candidate_ranges - ref_norm_all[ridx])))
            selected_range[out_idx] = candidate_ranges[local_idx]
            selected_coder[out_idx] = candidate_coders[local_idx]
            continue
        else:
            raise ValueError(match_return_strategy)
        selected_range[out_idx] = ranges[local_idx]
        selected_coder[out_idx] = coders[local_idx]

    pos_time, pos, pos_corrections = stage5.load_pos()
    matched_time = reference["time"][ref_idx]
    interp_time = np.clip(matched_time, pos_time[0], pos_time[-1])
    pos_e = np.interp(interp_time, pos_time, pos["EASTING"])
    pos_n = np.interp(interp_time, pos_time, pos["NORTHING"])
    pos_h = np.interp(interp_time, pos_time, pos["HEIGHT"])
    roll = np.interp(interp_time, pos_time, pos["ROLL"])
    pitch = np.interp(interp_time, pos_time, pos["PITCH"])
    heading = pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time)

    return {
        "matched_time": matched_time,
        "range_before": selected_range,
        "coder": selected_coder,
        "ref_north_offset": reference["lidar_x"][ref_idx],
        "ref_east_offset": reference["lidar_y"][ref_idx],
        "ref_down_offset": reference["lidar_z"][ref_idx],
        "ref_offset_norm": ref_norm_all[ref_idx],
        "ref_northing": reference["point_x"][ref_idx],
        "ref_easting": reference["point_y"][ref_idx],
        "ref_height": reference["point_z"][ref_idx],
        "pos_northing": pos_n,
        "pos_easting": pos_e,
        "pos_height": pos_h,
        "roll_deg": roll,
        "pitch_deg": pitch,
        "heading_deg": heading,
        "total_l1_points": np.array([l1["gnss"].size], dtype=np.int64),
        "exact_match_total": np.array([exact_match_total], dtype=np.int64),
        "pos_time_corrections": np.array([pos_corrections], dtype=np.int64),
        "match_candidate_count": selected_candidate_count,
        "match_far_candidate_count": selected_far_candidate_count,
        "reference_norm_zero_est_m": np.array([float(np.median(selected_range - ref_norm_all[ref_idx]))], dtype=np.float64),
    }


def range_for_strategy(
    range_before: np.ndarray,
    calibration: dict[str, float],
    strategy: str,
    reference_norm_zero_est_m: float | None = None,
) -> tuple[np.ndarray, float]:
    detected = pipe.find_zero_peak(range_before)
    if strategy == "NONE":
        zero = 0.0
    elif strategy == "Z0_auto":
        zero = float(detected) if np.isfinite(detected) else 0.0
    elif strategy == "Z1_fixed_calib_zero_offset":
        zero = float(calibration["zero_offset"])
    elif strategy == "Z2_ref_norm_median_zero":
        if reference_norm_zero_est_m is None or not np.isfinite(reference_norm_zero_est_m):
            raise ValueError("Z2_ref_norm_median_zero requires a finite reference_norm_zero_est_m")
        zero = float(reference_norm_zero_est_m)
    else:
        raise ValueError(strategy)
    return (range_before - zero - calibration["intercept"]) / calibration["slope"], zero


def scan_angle_for_mode(coder: np.ndarray, mode: str) -> np.ndarray:
    scan_angle = coder * 360.0 / 65536.0
    if mode == "360-angle":
        return 360.0 - scan_angle
    if mode == "angle":
        return scan_angle
    if mode == "angle+180":
        return np.mod(scan_angle + 180.0, 360.0)
    if mode == "180-angle":
        return 180.0 - scan_angle
    raise ValueError(mode)


def build_body(range_m: np.ndarray, coder: np.ndarray, angle_mode: str) -> np.ndarray:
    angle = scan_angle_for_mode(coder, angle_mode)
    bx, by, bz = pipe.f_body_frame_xyz(range_m, angle)
    return np.column_stack([bx, by, bz])


def axis_mapping_candidates() -> list[dict[str, Any]]:
    names = ["body_x", "body_y", "body_z"]
    target = ["forward", "right", "down"]
    rows: list[dict[str, Any]] = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product([-1.0, 1.0], repeat=3):
            rows.append(
                {
                    "axis_perm": perm,
                    "axis_signs": signs,
                    "axis_mapping": ";".join(
                        f"{target[i]}={'+' if signs[i] > 0 else '-'}{names[perm[i]]}" for i in range(3)
                    ),
                }
            )
    return rows


def attitude_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for roll_sign, pitch_sign, heading_sign in itertools.product([-1, 1], repeat=3):
        for heading_convention in HEADING_CONVENTIONS:
            for rotation_order in ROTATION_ORDERS:
                for transpose in [False, True]:
                    rows.append(
                        {
                            "roll_sign": roll_sign,
                            "pitch_sign": pitch_sign,
                            "heading_sign": heading_sign,
                            "heading_convention": heading_convention,
                            "rotation_order": rotation_order,
                            "rotation_transpose": transpose,
                        }
                    )
    return rows


def heading_for_candidate(heading_rad: np.ndarray, sign: int, convention: str) -> np.ndarray:
    signed = sign * heading_rad
    if convention == "heading":
        return signed
    if convention == "360-heading":
        return -signed
    if convention == "heading+180":
        return signed + math.pi
    if convention == "heading-90":
        return signed - math.pi / 2.0
    if convention == "90-heading":
        return math.pi / 2.0 - signed
    raise ValueError(convention)


def rotate_one_axis(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    axis: str,
    angle: np.ndarray | float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ca = np.cos(angle)
    sa = np.sin(angle)
    if axis == "X":
        return x, ca * y - sa * z, sa * y + ca * z
    if axis == "Y":
        return ca * x + sa * z, y, -sa * x + ca * z
    if axis == "Z":
        return ca * x - sa * y, sa * x + ca * y, z
    raise ValueError(axis)


def rotate_frd_to_ned(
    frd: np.ndarray,
    roll_rad: np.ndarray,
    pitch_rad: np.ndarray,
    heading_rad: np.ndarray,
    order: str,
    transpose: bool,
) -> np.ndarray:
    x = frd[:, 0]
    y = frd[:, 1]
    z = frd[:, 2]
    angles = {"X": roll_rad, "Y": pitch_rad, "Z": heading_rad}
    if transpose:
        axes = list(order)
        angle_multiplier = -1.0
    else:
        axes = list(reversed(order))
        angle_multiplier = 1.0
    for axis in axes:
        x, y, z = rotate_one_axis(x, y, z, axis, angle_multiplier * angles[axis])
    return np.column_stack([x, y, z])


def apply_boresight(frd: np.ndarray, roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
    x = frd[:, 0]
    y = frd[:, 1]
    z = frd[:, 2]
    x, y, z = rotate_one_axis(x, y, z, "X", math.radians(roll_deg))
    x, y, z = rotate_one_axis(x, y, z, "Y", math.radians(pitch_deg))
    x, y, z = rotate_one_axis(x, y, z, "Z", math.radians(yaw_deg))
    return np.column_stack([x, y, z])


def frd_from_body(body: np.ndarray, mapping: dict[str, Any]) -> np.ndarray:
    perm = mapping["axis_perm"]
    signs = mapping["axis_signs"]
    return np.column_stack([signs[i] * body[:, perm[i]] for i in range(3)])


def prepare_angles(data: dict[str, np.ndarray], attitude: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    roll = attitude["roll_sign"] * np.deg2rad(data["roll_deg"].astype(np.float64))
    pitch = attitude["pitch_sign"] * np.deg2rad(data["pitch_deg"].astype(np.float64))
    heading_base = np.deg2rad(data["heading_deg"].astype(np.float64))
    heading = heading_for_candidate(heading_base, int(attitude["heading_sign"]), str(attitude["heading_convention"]))
    return roll, pitch, heading


def residual_metrics(diff: np.ndarray, robust_idx: np.ndarray) -> dict[str, float]:
    diff = diff.astype(np.float64, copy=False)
    robust = diff[robust_idx] if robust_idx.size and robust_idx.size < diff.shape[0] else diff
    med = np.median(robust, axis=0)
    mad = np.median(np.abs(robust - med), axis=0)
    p90 = np.percentile(np.abs(robust), 90, axis=0)
    rmse = np.sqrt(np.mean(diff**2, axis=0))
    centered = diff - med
    centered_rmse = np.sqrt(np.mean(centered**2, axis=0))
    return {
        "north_rmse_m": float(rmse[0]),
        "east_rmse_m": float(rmse[1]),
        "down_rmse_m": float(rmse[2]),
        "north_median_error_m": float(med[0]),
        "east_median_error_m": float(med[1]),
        "down_median_error_m": float(med[2]),
        "north_mad_m": float(mad[0]),
        "east_mad_m": float(mad[1]),
        "down_mad_m": float(mad[2]),
        "north_p90_abs_error_m": float(p90[0]),
        "east_p90_abs_error_m": float(p90[1]),
        "down_p90_abs_error_m": float(p90[2]),
        "vector_rmse_m": float(np.sqrt(np.mean(np.sum(diff**2, axis=1)))),
        "north_rmse_bias_removed_m": float(centered_rmse[0]),
        "east_rmse_bias_removed_m": float(centered_rmse[1]),
        "down_rmse_bias_removed_m": float(centered_rmse[2]),
        "vector_rmse_bias_removed_m": float(np.sqrt(np.mean(np.sum(centered**2, axis=1)))),
        "northing_rmse_m": float(rmse[0]),
        "easting_rmse_m": float(rmse[1]),
        "height_rmse_m": float(rmse[2]),
        "height_median_error_m": float(-med[2]),
    }


def evaluate_candidate(
    data: dict[str, np.ndarray],
    body_cache: dict[tuple[str, str], np.ndarray],
    row: dict[str, Any],
    robust_idx: np.ndarray,
    boresight: tuple[float, float, float] = (0.0, 0.0, 0.0),
    lever: tuple[float, float, float] = (0.0, 0.0, 0.0),
    candidate_stage: str = "coarse",
) -> dict[str, Any]:
    body = body_cache[(row["zero_strategy"], row["angle_mode"])]
    frd = frd_from_body(body, row)
    if boresight != (0.0, 0.0, 0.0):
        frd = apply_boresight(frd, *boresight)
    if lever != (0.0, 0.0, 0.0):
        frd = frd + np.asarray(lever, dtype=np.float64)

    roll, pitch, heading = prepare_angles(data, row)
    pred = rotate_frd_to_ned(frd, roll, pitch, heading, row["rotation_order"], bool(row["rotation_transpose"]))
    ref = np.column_stack([data["ref_north_offset"], data["ref_east_offset"], data["ref_down_offset"]])
    metrics = residual_metrics(pred - ref, robust_idx)
    boresight_abs_max = max(abs(boresight[0]), abs(boresight[1]), abs(boresight[2]))
    lever_norm = float(np.linalg.norm(np.asarray(lever, dtype=np.float64)))
    return {
        "candidate_stage": candidate_stage,
        "zero_strategy": row["zero_strategy"],
        "angle_mode": row["angle_mode"],
        "zero_used_m": row.get("zero_used_m", 0.0),
        "axis_mapping": row["axis_mapping"],
        "roll_sign": row["roll_sign"],
        "pitch_sign": row["pitch_sign"],
        "heading_sign": row["heading_sign"],
        "heading_convention": row["heading_convention"],
        "rotation_order": row["rotation_order"],
        "rotation_transpose": bool(row["rotation_transpose"]),
        "boresight_roll_deg": boresight[0],
        "boresight_pitch_deg": boresight[1],
        "boresight_yaw_deg": boresight[2],
        "boresight_abs_max_deg": boresight_abs_max,
        "lever_x_m": lever[0],
        "lever_y_m": lever[1],
        "lever_z_m": lever[2],
        "lever_norm_m": lever_norm,
        "sample_points_used": int(data["matched_time"].size),
        **metrics,
    }


def build_body_cache(data: dict[str, np.ndarray], calibration: dict[str, float]) -> tuple[dict[tuple[str, str], np.ndarray], dict[str, float]]:
    body_cache: dict[tuple[str, str], np.ndarray] = {}
    zero_values: dict[str, float] = {}
    ref_zero = float(data["reference_norm_zero_est_m"][0])
    for zero_strategy in ZERO_STRATEGIES:
        range_m, zero_used = range_for_strategy(data["range_before"], calibration, zero_strategy, ref_zero)
        zero_values[zero_strategy] = zero_used
        for angle_mode in ANGLE_MODES:
            body_cache[(zero_strategy, angle_mode)] = build_body(range_m, data["coder"], angle_mode)
    return body_cache, zero_values


def base_candidate_rows(zero_values: dict[str, float]) -> list[dict[str, Any]]:
    axis_rows = axis_mapping_candidates()
    attitude_rows = attitude_candidates()
    rows: list[dict[str, Any]] = []
    for zero_strategy in ZERO_STRATEGIES:
        for angle_mode in ANGLE_MODES:
            for axis_row in axis_rows:
                for attitude_row in attitude_rows:
                    rows.append(
                        {
                            "zero_strategy": zero_strategy,
                            "angle_mode": angle_mode,
                            "zero_used_m": zero_values[zero_strategy],
                            **axis_row,
                            **attitude_row,
                        }
                    )
    return rows


def candidate_fields() -> list[str]:
    return [
        "candidate_stage",
        "zero_strategy",
        "angle_mode",
        "zero_used_m",
        "axis_mapping",
        "roll_sign",
        "pitch_sign",
        "heading_sign",
        "heading_convention",
        "rotation_order",
        "rotation_transpose",
        "boresight_roll_deg",
        "boresight_pitch_deg",
        "boresight_yaw_deg",
        "boresight_abs_max_deg",
        "lever_x_m",
        "lever_y_m",
        "lever_z_m",
        "lever_norm_m",
        "sample_points_used",
        "north_rmse_m",
        "east_rmse_m",
        "down_rmse_m",
        "north_median_error_m",
        "east_median_error_m",
        "down_median_error_m",
        "north_mad_m",
        "east_mad_m",
        "down_mad_m",
        "north_p90_abs_error_m",
        "east_p90_abs_error_m",
        "down_p90_abs_error_m",
        "vector_rmse_m",
        "north_rmse_bias_removed_m",
        "east_rmse_bias_removed_m",
        "down_rmse_bias_removed_m",
        "vector_rmse_bias_removed_m",
        "northing_rmse_m",
        "easting_rmse_m",
        "height_rmse_m",
        "height_median_error_m",
    ]


def sort_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (row["vector_rmse_m"], row["down_rmse_m"], row["east_rmse_m"] + row["north_rmse_m"]))


def evaluate_many(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
    rows: list[dict[str, Any]],
    robust_points: int,
    progress_label: str,
) -> list[dict[str, Any]]:
    body_cache, zero_values = build_body_cache(data, calibration)
    robust_idx = stratified_indices(data["matched_time"].size, robust_points)
    out: list[dict[str, Any]] = []
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        eval_row = dict(row)
        eval_row["zero_used_m"] = zero_values[eval_row["zero_strategy"]]
        out.append(evaluate_candidate(data, body_cache, eval_row, robust_idx))
        if idx % 1000 == 0 or idx == total:
            print(f"{progress_label}: {idx:,}/{total:,}", flush=True)
    return sort_candidates(out)


def re_evaluate_existing_rows(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
    rows: list[dict[str, Any]],
    robust_points: int,
    progress_label: str,
) -> list[dict[str, Any]]:
    body_cache, zero_values = build_body_cache(data, calibration)
    robust_idx = stratified_indices(data["matched_time"].size, robust_points)
    out: list[dict[str, Any]] = []
    total = len(rows)
    for idx, row in enumerate(rows, start=1):
        base = row_to_base_candidate(row)
        base["zero_used_m"] = zero_values[base["zero_strategy"]]
        boresight = (
            float(row.get("boresight_roll_deg", 0.0)),
            float(row.get("boresight_pitch_deg", 0.0)),
            float(row.get("boresight_yaw_deg", 0.0)),
        )
        lever = (
            float(row.get("lever_x_m", 0.0)),
            float(row.get("lever_y_m", 0.0)),
            float(row.get("lever_z_m", 0.0)),
        )
        stage = str(row.get("candidate_stage", "coarse"))
        out.append(
            evaluate_candidate(
                data,
                body_cache,
                base,
                robust_idx,
                boresight=boresight,
                lever=lever,
                candidate_stage=f"{stage}_final_eval",
            )
        )
        if idx % 100 == 0 or idx == total:
            print(f"{progress_label}: {idx:,}/{total:,}", flush=True)
    return sort_candidates(out)


def row_to_base_candidate(row: dict[str, Any]) -> dict[str, Any]:
    mapping_text = row["axis_mapping"]
    body_names = ["body_x", "body_y", "body_z"]
    target_names = ["forward", "right", "down"]
    perm: list[int] = []
    signs: list[float] = []
    parts = mapping_text.split(";")
    by_target = {part.split("=")[0]: part.split("=")[1] for part in parts}
    for target in target_names:
        value = by_target[target]
        signs.append(-1.0 if value.startswith("-") else 1.0)
        name = value[1:] if value[0] in "+-" else value
        perm.append(body_names.index(name))
    return {
        "zero_strategy": row["zero_strategy"],
        "angle_mode": row["angle_mode"],
        "zero_used_m": float(row["zero_used_m"]),
        "axis_perm": tuple(perm),
        "axis_signs": tuple(signs),
        "axis_mapping": mapping_text,
        "roll_sign": int(row["roll_sign"]),
        "pitch_sign": int(row["pitch_sign"]),
        "heading_sign": int(row["heading_sign"]),
        "heading_convention": row["heading_convention"],
        "rotation_order": row["rotation_order"],
        "rotation_transpose": bool(row["rotation_transpose"]),
    }


def evaluate_boresight_lever(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
    top_rows: list[dict[str, Any]],
    robust_points: int,
    max_rows: int,
) -> list[dict[str, Any]]:
    body_cache, zero_values = build_body_cache(data, calibration)
    robust_idx = stratified_indices(data["matched_time"].size, robust_points)
    out: list[dict[str, Any]] = []
    boresights = list(itertools.product(BORESIGHT_GRID_DEG, repeat=3))
    levers = list(itertools.product(LEVER_GRID_M, repeat=3))
    total = min(max_rows, len(top_rows)) * len(boresights) * len(levers)
    done = 0
    for source_row in top_rows[:max_rows]:
        base = row_to_base_candidate(source_row)
        base["zero_used_m"] = zero_values[base["zero_strategy"]]
        for boresight in boresights:
            for lever in levers:
                out.append(
                    evaluate_candidate(
                        data,
                        body_cache,
                        base,
                        robust_idx,
                        boresight=boresight,
                        lever=lever,
                        candidate_stage="boresight_lever",
                    )
                )
                done += 1
                if done % 1000 == 0 or done == total:
                    print(f"Boresight/lever diagnostic: {done:,}/{total:,}", flush=True)
    return sort_candidates(out)


def gate_for_best(best: dict[str, Any]) -> tuple[str, str]:
    vector = float(best["vector_rmse_m"])
    down = float(best["down_rmse_m"])
    max_axis = max(float(best["north_rmse_m"]), float(best["east_rmse_m"]), float(best["down_rmse_m"]))
    max_p90 = max(
        float(best["north_p90_abs_error_m"]),
        float(best["east_p90_abs_error_m"]),
        float(best["down_p90_abs_error_m"]),
    )
    boresight_abs = float(best.get("boresight_abs_max_deg", 0.0))
    lever_norm = float(best.get("lever_norm_m", 0.0))

    if vector < 2.0 and down < 2.0 and max_p90 < 5.0 and boresight_abs <= 2.0 and lever_norm <= 2.0:
        return "合理", "候选模型在参考 L3 exact-time 匹配点上通过诊断阈值；暂停，人工确认后才规划 Stage 5R2 小样本重算。"
    if vector <= 5.0 and max_axis <= 5.0 and boresight_abs <= 5.0 and lever_norm <= math.sqrt(12.0):
        return "基本合理但有风险", "候选模型残差进入 2-5 m 风险区间；暂停，需人工判断 boresight/lever-arm 候选是否物理可信。"
    return "不合理", "当前候选仍无法稳定复现参考 L3；不要进入全量 CH1 v2、CH2、去噪或 LAZ。优先排查 F_BodyFrame_XYZ、扫描角模型、距离公式或参考回波对应关系。"


def write_report(
    path: Path,
    args: argparse.Namespace,
    matched_data: dict[str, np.ndarray],
    search_rows: list[dict[str, Any]],
    final_rows: list[dict[str, Any]],
    boresight_rows: list[dict[str, Any]],
    best: dict[str, Any],
    conclusion: str,
    recommendation: str,
) -> None:
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    best_json = json.dumps(jsonable(best), ensure_ascii=False, indent=2)
    content = f"""# Stage 5G2 CH1 Body->NED 几何模型诊断报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}
- 阶段：stage5g2_ch1_body_to_ned_diagnostic
- 处理通道：CH1
- 参考 L3：`{rel(REFERENCE_L3)}`
- 样例 L1：`{rel(L1_SAMPLE)}`
- LIDAR 时间：`GNSS_SEC_CH1 + {pipe.DEFAULT_TIME_OFFSET_SEC:g}`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Inputs And Sampling

- L1 total points: {int(matched_data['total_l1_points'][0]):,}
- Exact matched points before cap: {int(matched_data['exact_match_total'][0]):,}
- Matched points loaded: {matched_data['matched_time'].size:,}
- L1 return match strategy: `{args.match_return_strategy}`
- Minimum far-return range: {args.min_far_range_m:g} m
- Median diagnostic zero from reference norm: {float(matched_data['reference_norm_zero_est_m'][0]):.6f} m
- Median L1 return candidates per reference point: {float(np.median(matched_data['match_candidate_count'])):.3f}
- Far-return availability rate: {float(np.count_nonzero(matched_data['match_far_candidate_count']) / matched_data['match_far_candidate_count'].size):.6%}
- Search sample points: {min(args.search_points, matched_data['matched_time'].size):,}
- Robust statistic sample points: {min(args.robust_points, matched_data['matched_time'].size):,}
- Boresight/lever sample points: {0 if args.coarse_only else min(args.boresight_max_points, matched_data['matched_time'].size):,}
- POS time corrections: {int(matched_data['pos_time_corrections'][0])}

## Candidate Coverage

- Range/scan zero strategies: `{', '.join(ZERO_STRATEGIES)}`
- Angle modes: `{', '.join(ANGLE_MODES)}`
- Body axis mappings: all 48 permutations/sign combinations to `forward/right/down`
- Attitude candidates: roll/pitch/heading signs, heading conventions, rotation orders, transpose/non-transpose
- Coarse candidates evaluated: {len(search_rows):,}
- Final coarse candidates re-evaluated: {len(final_rows):,}
- Boresight/lever candidates evaluated: {len(boresight_rows):,}

## Best Candidate

```json
{best_json}
```

## Key Outputs

- Candidate summary: `outputs\\qc\\stage5g2_body_to_ned\\candidate_summary.csv`
- Top candidates: `outputs\\qc\\stage5g2_body_to_ned\\top_candidates.csv`
- Boresight candidates: `outputs\\qc\\stage5g2_body_to_ned\\boresight_candidates.csv`
- Best candidate JSON: `outputs\\qc\\stage5g2_body_to_ned\\best_candidate.json`

## Warnings

- 本阶段只做诊断，不生成最终点云，不写 `outputs/h5_ch1`、`outputs/h5_merged` 或 `outputs/laz`。
- 所有轴向、符号、角度、boresight、lever-arm 都是 `PROJECT_DIAGNOSTIC_PARAMETER`，不能当作最终算法。
- 默认先用搜索样本筛选候选，再对前排候选做较大样本复核；这是为了避免全候选在 100000 点上运行过慢。
- `Z2_ref_norm_median_zero` 是利用已有参考 L3 offset 模长估计的诊断零位，只能作为问题定位线索，不能直接作为最终量产算法。
- 不使用逐文件 height median bias。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5G2 CH1 body-to-NED diagnostic against exact-time L3 reference.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--search-points", type=int, default=5_000)
    parser.add_argument("--robust-points", type=int, default=1_000)
    parser.add_argument("--top-output-count", type=int, default=200)
    parser.add_argument("--top-final-eval-count", type=int, default=200)
    parser.add_argument("--boresight-top-candidates", type=int, default=50)
    parser.add_argument("--boresight-max-points", type=int, default=5_000)
    parser.add_argument("--match-return-strategy", choices=["far_return_refnorm", "first_time_record"], default="far_return_refnorm")
    parser.add_argument("--min-far-range-m", type=float, default=30.0)
    parser.add_argument("--coarse-only", action="store_true")
    args = parser.parse_args()

    print("Loading exact-time matched CH1/L3/POS data...", flush=True)
    matched = load_matched_data(args.max_matched_points, args.match_return_strategy, args.min_far_range_m)
    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")

    search_idx = stratified_indices(matched["matched_time"].size, args.search_points)
    search_data = {key: value[search_idx] if isinstance(value, np.ndarray) and value.shape[:1] == (matched["matched_time"].size,) else value for key, value in matched.items()}
    search_body_cache, zero_values = build_body_cache(search_data, calibration)
    base_rows = base_candidate_rows(zero_values)

    print(f"Evaluating coarse candidate search: {len(base_rows):,} candidates on {search_data['matched_time'].size:,} points.", flush=True)
    robust_idx = stratified_indices(search_data["matched_time"].size, args.robust_points)
    search_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(base_rows, start=1):
        search_rows.append(evaluate_candidate(search_data, search_body_cache, row, robust_idx))
        if idx % 1000 == 0 or idx == len(base_rows):
            print(f"Coarse search: {idx:,}/{len(base_rows):,}", flush=True)
    search_rows = sort_candidates(search_rows)

    print("Re-evaluating top coarse candidates on matched sample...", flush=True)
    final_base_rows = [row_to_base_candidate(row) for row in search_rows[: args.top_final_eval_count]]
    final_rows = evaluate_many(matched, calibration, final_base_rows, args.robust_points, "Final coarse evaluation")

    boresight_rows: list[dict[str, Any]] = []
    if not args.coarse_only:
        print("Evaluating boresight/lever-arm diagnostic candidates...", flush=True)
        b_idx = stratified_indices(matched["matched_time"].size, args.boresight_max_points)
        b_data = {key: value[b_idx] if isinstance(value, np.ndarray) and value.shape[:1] == (matched["matched_time"].size,) else value for key, value in matched.items()}
        boresight_search_rows = evaluate_boresight_lever(
            b_data,
            calibration,
            final_rows,
            min(args.robust_points, args.boresight_max_points),
            args.boresight_top_candidates,
        )
        print("Re-evaluating top boresight/lever-arm candidates on matched sample...", flush=True)
        boresight_rows = re_evaluate_existing_rows(
            matched,
            calibration,
            boresight_search_rows[: args.top_final_eval_count],
            args.robust_points,
            "Final boresight/lever evaluation",
        )
    else:
        print("Skipping boresight/lever-arm grid because --coarse-only was set.", flush=True)

    combined = sort_candidates(final_rows + boresight_rows)
    best = combined[0] if combined else {}
    conclusion, recommendation = gate_for_best(best)

    QC_DIR.mkdir(parents=True, exist_ok=True)
    write_csv(QC_DIR / "candidate_summary.csv", search_rows, candidate_fields())
    write_csv(QC_DIR / "top_candidates.csv", combined[: args.top_output_count], candidate_fields())
    write_csv(QC_DIR / "boresight_candidates.csv", boresight_rows, candidate_fields())
    write_json(QC_DIR / "best_candidate.json", best)

    report_payload = {
        "stage_name": "stage5g2_ch1_body_to_ned_diagnostic",
        "gate_conclusion": conclusion,
        "recommendation": recommendation,
        "input_l1": rel(L1_SAMPLE),
        "reference_l3": rel(REFERENCE_L3),
        "pos_source": rel(stage5.POS_SOURCE),
        "calib_coeffs": rel(CALIB_COEFFS),
        "lidar_time_offset_sec": pipe.DEFAULT_TIME_OFFSET_SEC,
        "max_matched_points": args.max_matched_points,
        "match_return_strategy": args.match_return_strategy,
        "min_far_range_m": args.min_far_range_m,
        "matched_points_loaded": int(matched["matched_time"].size),
        "exact_match_total": int(matched["exact_match_total"][0]),
        "reference_norm_zero_est_m": float(matched["reference_norm_zero_est_m"][0]),
        "median_match_candidate_count": float(np.median(matched["match_candidate_count"])),
        "far_return_availability_rate": float(
            np.count_nonzero(matched["match_far_candidate_count"]) / matched["match_far_candidate_count"].size
        ),
        "search_points": int(search_data["matched_time"].size),
        "robust_points": min(args.robust_points, int(search_data["matched_time"].size)),
        "coarse_candidate_count": len(search_rows),
        "final_candidate_count": len(final_rows),
        "boresight_candidate_count": len(boresight_rows),
        "best_candidate": best,
        "method_registry": METHOD_REGISTRY,
        "outputs": {
            "candidate_summary": rel(QC_DIR / "candidate_summary.csv"),
            "top_candidates": rel(QC_DIR / "top_candidates.csv"),
            "boresight_candidates": rel(QC_DIR / "boresight_candidates.csv"),
            "best_candidate": rel(QC_DIR / "best_candidate.json"),
            "report_md": rel(REPORT_DIR / "stage5g2_body_to_ned_diagnostic_report.md"),
            "report_json": rel(REPORT_DIR / "stage5g2_body_to_ned_diagnostic_report.json"),
        },
    }
    write_json(REPORT_DIR / "stage5g2_body_to_ned_diagnostic_report.json", report_payload)
    write_report(
        REPORT_DIR / "stage5g2_body_to_ned_diagnostic_report.md",
        args,
        matched,
        search_rows,
        final_rows,
        boresight_rows,
        best,
        conclusion,
        recommendation,
    )

    print("Stage 5G2 diagnostic complete.", flush=True)
    print(f"Conclusion: {conclusion}", flush=True)
    print(f"Report: {REPORT_DIR / 'stage5g2_body_to_ned_diagnostic_report.md'}", flush=True)
    print(f"Best candidate: {QC_DIR / 'best_candidate.json'}", flush=True)


if __name__ == "__main__":
    main()
