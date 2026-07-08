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
from pyproj import Transformer

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5


ROOT = Path(__file__).resolve().parents[2]
L1_SAMPLE = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00111_20260510190957.h5"
REFERENCE_L3 = ROOT / "0510_f3" / "L3_DATA" / "L2_cap_00111_20260510190957.h5"
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
QC_DIR = ROOT / "outputs" / "qc" / "stage5g_geometry_audit"
PREVIEW_DIR = ROOT / "outputs" / "preview" / "stage5g_geometry_audit"

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0

METHOD_REGISTRY = [
    {
        "method_id": "DG_ALS_001",
        "method_name": "direct georeferencing model diagnostic",
        "source_type": "peer_reviewed_journal",
        "source_reference": "Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006",
        "used_for_delete_or_transform": "no, diagnostic only",
    },
    {
        "method_id": "STRIP_QC_009",
        "method_name": "overlap / strip consistency QC",
        "source_type": "peer_reviewed_conference",
        "source_reference": "Filin & Vosselman, ISPRS 2004",
        "used_for_delete_or_transform": "no, diagnostic only",
    },
    {
        "method_id": "PROJECT_EMPIRICAL_PARAMETER",
        "method_name": "candidate zero offset, scan angle convention, body axis mapping",
        "source_type": "project_empirical_parameter",
        "source_reference": "Project diagnostic candidates only",
        "used_for_delete_or_transform": "no, candidates are not final calibration",
    },
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def robust_stats(diff: np.ndarray) -> dict[str, float]:
    diff = np.asarray(diff, dtype=np.float64)
    finite = diff[np.isfinite(diff)]
    if finite.size == 0:
        return {
            "median": float("nan"),
            "mad": float("nan"),
            "rmse": float("nan"),
            "p90_abs": float("nan"),
        }
    return {
        "median": float(np.median(finite)),
        "mad": float(np.median(np.abs(finite - np.median(finite)))),
        "rmse": float(np.sqrt(np.mean(finite**2))),
        "p90_abs": float(np.percentile(np.abs(finite), 90)),
    }


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
        n = int(h5["GNSS_SEC_CH1"].shape[0])
        idx = np.arange(n, dtype=np.int64)
        return {
            "idx": idx,
            "gnss": h5["GNSS_SEC_CH1"][idx].astype(np.float64),
            "raw_dist": h5["Photon_CH1_DIST"][idx].astype(np.uint32),
            "coder": h5["Photon_CH1_CODER"][idx].astype(np.float64),
            "pulse_index": h5["PULSE_INDEX_CH1"][idx].astype(np.uint32),
            "pulse_circle": h5["PULSE_CIRCLE_CH1"][idx].astype(np.uint32),
        }


def exact_reference_match(lidar_time: np.ndarray, reference_time: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    _, l1_idx, ref_idx = np.intersect1d(lidar_time, reference_time, assume_unique=False, return_indices=True)
    return l1_idx.astype(np.int64), ref_idx.astype(np.int64)


def nearest_reference_match(lidar_time: np.ndarray, reference_time: np.ndarray, max_dt: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    idx = np.searchsorted(reference_time, lidar_time)
    left = np.clip(idx - 1, 0, reference_time.size - 1)
    right = np.clip(idx, 0, reference_time.size - 1)
    choose_right = np.abs(reference_time[right] - lidar_time) < np.abs(reference_time[left] - lidar_time)
    nearest = np.where(choose_right, right, left)
    dt = np.abs(reference_time[nearest] - lidar_time)
    mask = dt <= max_dt
    return np.flatnonzero(mask), nearest[mask], dt[mask]


def range_for_strategy(range_before: np.ndarray, calibration: dict[str, float], strategy: str) -> tuple[np.ndarray, float]:
    detected = pipe.find_zero_peak(range_before)
    if strategy == "Z0":
        zero = float(detected) if np.isfinite(detected) else 0.0
    elif strategy == "Z1":
        zero = float(calibration["zero_offset"])
    elif strategy == "NONE":
        zero = 0.0
    else:
        raise ValueError(strategy)
    return (range_before - zero - calibration["intercept"]) / calibration["slope"], zero


def candidate_body(range_m: np.ndarray, coder: np.ndarray, angle_mode: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    scan_angle = coder * 360.0 / 65536.0
    if angle_mode == "360-angle":
        model_angle = 360.0 - scan_angle
    elif angle_mode == "angle":
        model_angle = scan_angle
    elif angle_mode == "angle+180":
        model_angle = np.mod(scan_angle + 180.0, 360.0)
    elif angle_mode == "180-angle":
        model_angle = 180.0 - scan_angle
    else:
        raise ValueError(angle_mode)
    x, y, z = pipe.f_body_frame_xyz(range_m, model_angle)
    return x, y, z, model_angle


def fit_similarity_1d(source: np.ndarray, target: np.ndarray) -> tuple[float, float, np.ndarray]:
    source = source.astype(np.float64)
    target = target.astype(np.float64)
    design = np.column_stack([source, np.ones(source.size)])
    scale, offset = np.linalg.lstsq(design, target, rcond=None)[0]
    pred = scale * source + offset
    return float(scale), float(offset), pred


def best_axis_mapping(
    body: np.ndarray,
    reference_lidar: np.ndarray,
    allow_scale: bool,
) -> list[dict[str, Any]]:
    names = ["body_x", "body_y", "body_z"]
    ref_names = ["LIDAR_X", "LIDAR_Y", "LIDAR_Z"]
    rows: list[dict[str, Any]] = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product([-1.0, 1.0], repeat=3):
            errors = []
            details = []
            for out_axis, body_axis_idx in enumerate(perm):
                source = signs[out_axis] * body[:, body_axis_idx]
                target = reference_lidar[:, out_axis]
                if allow_scale:
                    scale, offset, pred = fit_similarity_1d(source, target)
                else:
                    scale = 1.0
                    offset = float(np.median(target - source))
                    pred = source + offset
                diff = pred - target
                st = robust_stats(diff)
                errors.append(st["rmse"])
                details.append(
                    {
                        "target_axis": ref_names[out_axis],
                        "source_axis": names[body_axis_idx],
                        "sign": int(signs[out_axis]),
                        "scale": scale,
                        "offset": offset,
                        "median_error_m": st["median"],
                        "mad_error_m": st["mad"],
                        "rmse_m": st["rmse"],
                        "p90_abs_error_m": st["p90_abs"],
                    }
                )
            rows.append(
                {
                    "mapping": ";".join(f"{d['target_axis']}={d['sign']}*{d['source_axis']}+offset" for d in details),
                    "allow_scale": allow_scale,
                    "mean_rmse_m": float(np.mean(errors)),
                    "max_rmse_m": float(np.max(errors)),
                    "details": details,
                }
            )
    return sorted(rows, key=lambda row: (row["mean_rmse_m"], row["max_rmse_m"]))


def compute_georef_variant(
    body: np.ndarray,
    lidar_time: np.ndarray,
    reference: dict[str, np.ndarray],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    rotation_mode: str,
) -> dict[str, Any]:
    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    pos_e = np.interp(interp_time, pos_time, pos["EASTING"])
    pos_n = np.interp(interp_time, pos_time, pos["NORTHING"])
    pos_h = np.interp(interp_time, pos_time, pos["HEIGHT"])
    roll = np.interp(interp_time, pos_time, pos["ROLL"])
    pitch = np.interp(interp_time, pos_time, pos["PITCH"])
    heading = pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time)

    bx, by, bz = body[:, 0], body[:, 1], body[:, 2]
    if rotation_mode == "current":
        north, east, down = stage5.georef_offsets(bx, by, bz, roll, pitch, heading)
    elif rotation_mode == "flip_xy":
        north, east, down = stage5.georef_offsets(-bx, -by, bz, roll, pitch, heading)
    elif rotation_mode == "no_xy_flip":
        # Same rotation formula but with forward/right taken directly.
        north, east, down = stage5.georef_offsets(-bx, -by, bz, roll, pitch, heading)
    else:
        raise ValueError(rotation_mode)

    pred_e = pos_e + east
    pred_n = pos_n + north
    pred_h = pos_h - down
    ref_e = reference["point_y"]
    ref_n = reference["point_x"]
    ref_h = reference["point_z"]
    # Remove one global median height offset for diagnostic fairness.
    h_bias = float(np.median(ref_h - pred_h))
    pred_h = pred_h + h_bias
    return {
        "rotation_mode": rotation_mode,
        "easting_rmse_m": robust_stats(pred_e - ref_e)["rmse"],
        "northing_rmse_m": robust_stats(pred_n - ref_n)["rmse"],
        "height_rmse_m": robust_stats(pred_h - ref_h)["rmse"],
        "height_bias_m": h_bias,
        "easting_median_error_m": robust_stats(pred_e - ref_e)["median"],
        "northing_median_error_m": robust_stats(pred_n - ref_n)["median"],
        "height_median_error_m": robust_stats(pred_h - ref_h)["median"],
    }


def compute_offset_variant(
    body: np.ndarray,
    lidar_time: np.ndarray,
    ref_lidar_ned: np.ndarray,
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    rotation_mode: str,
) -> dict[str, Any]:
    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    roll = np.interp(interp_time, pos_time, pos["ROLL"])
    pitch = np.interp(interp_time, pos_time, pos["PITCH"])
    heading = pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time)

    bx, by, bz = body[:, 0], body[:, 1], body[:, 2]
    if rotation_mode == "current":
        north, east, down = stage5.georef_offsets(bx, by, bz, roll, pitch, heading)
    else:
        raise ValueError(rotation_mode)

    pred = np.column_stack([north, east, down])
    diff = pred - ref_lidar_ned
    north_stats = robust_stats(diff[:, 0])
    east_stats = robust_stats(diff[:, 1])
    down_stats = robust_stats(diff[:, 2])
    return {
        "rotation_mode": rotation_mode,
        "north_offset_rmse_m": north_stats["rmse"],
        "east_offset_rmse_m": east_stats["rmse"],
        "down_offset_rmse_m": down_stats["rmse"],
        "offset_vector_rmse_m": float(np.sqrt(np.mean(np.sum(diff**2, axis=1)))),
        "north_offset_median_error_m": north_stats["median"],
        "east_offset_median_error_m": east_stats["median"],
        "down_offset_median_error_m": down_stats["median"],
        "north_offset_p90_abs_error_m": north_stats["p90_abs"],
        "east_offset_p90_abs_error_m": east_stats["p90_abs"],
        "down_offset_p90_abs_error_m": down_stats["p90_abs"],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_report(
    path: Path,
    body_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
    offset_rows: list[dict[str, Any]],
    georef_rows: list[dict[str, Any]],
    sample_count: int,
    matched_count: int,
    max_dt: float,
    match_mode: str,
) -> None:
    best_body = body_rows[0] if body_rows else {}
    best_mapping = mapping_rows[0] if mapping_rows else {}
    best_offset = offset_rows[0] if offset_rows else {}
    best_georef = sorted(
        georef_rows,
        key=lambda row: row["easting_rmse_m"] + row["northing_rmse_m"] + row["height_rmse_m"],
    )[0] if georef_rows else {}

    if best_offset and best_offset.get("offset_vector_rmse_m", 999.0) < 1.0:
        conclusion = "基本合理"
        recommendation = "当前 body→NED offset 能较好复现参考 L3；下一步可进入小样本坐标重算验证。"
    else:
        conclusion = "不合理"
        recommendation = "当前 range/scan/body→NED 模型无法稳定复现参考 L3 的 LIDAR_X/Y/Z；优先修正扫描角零位、角度方向、距离零位或 boresight/lever-arm。"

    content = f"""# Stage 5G CH1 几何转换模型返查报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}
- 阶段：stage5g_ch1_geometry_audit
- 样例：00111
- L1 sample count: {sample_count}
- Reference matched count: {matched_count}
- Match mode: {match_mode}
- Max nearest time delta: {max_dt} s

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{chr(10).join(f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |" for m in METHOD_REGISTRY)}

## Best Body Candidate

- zero strategy: {best_body.get('zero_strategy')}
- angle mode: {best_body.get('angle_mode')}
- zero used: {best_body.get('zero_used_m')} m
- direct LIDAR vector RMSE: {best_body.get('direct_lidar_vector_rmse_m')}

说明：参考 L3 的 `LIDAR_X/Y/Z` 已验证为导航系偏移量，不是原始 body 坐标；本项只作为早期候选参考，最终判断看下面的 offset candidate。

## Best Axis Mapping Candidate

- mapping: {best_mapping.get('mapping')}
- allow scale: {best_mapping.get('allow_scale')}
- mean RMSE: {best_mapping.get('mean_rmse_m')}
- max RMSE: {best_mapping.get('max_rmse_m')}

## Best Offset Candidate

- zero strategy: {best_offset.get('zero_strategy')}
- angle mode: {best_offset.get('angle_mode')}
- rotation mode: {best_offset.get('rotation_mode')}
- north offset RMSE: {best_offset.get('north_offset_rmse_m')}
- east offset RMSE: {best_offset.get('east_offset_rmse_m')}
- down offset RMSE: {best_offset.get('down_offset_rmse_m')}
- vector RMSE: {best_offset.get('offset_vector_rmse_m')}

## Best Georef Candidate

- rotation mode: {best_georef.get('rotation_mode')}
- easting RMSE: {best_georef.get('easting_rmse_m')}
- northing RMSE: {best_georef.get('northing_rmse_m')}
- height RMSE: {best_georef.get('height_rmse_m')}
- diagnostic height bias: {best_georef.get('height_bias_m')}

## Outputs

- Body candidates CSV: `outputs\\qc\\stage5g_geometry_audit\\body_candidate_errors.csv`
- Axis mapping CSV: `outputs\\qc\\stage5g_geometry_audit\\axis_mapping_errors.csv`
- Offset candidate CSV: `outputs\\qc\\stage5g_geometry_audit\\offset_candidate_errors.csv`
- Georef candidate CSV: `outputs\\qc\\stage5g_geometry_audit\\georef_candidate_errors.csv`

## Known Warnings

- 本阶段只做诊断，不生成最终坐标成果。
- 候选扫描角/轴向/零位均为 `PROJECT_EMPIRICAL_PARAMETER`，不能写成论文算法。
- 若 reference L3 的 `LIDAR_X/Y/Z` 与当前 L1 点序并非一一对应，本报告会作为方向性诊断，而不是最终标定结果。

## Manual Checklist

- 如果 best body candidate 仍误差很大，先排查 L1→body：零位、扫描角方向、F_BodyFrame_XYZ 参数。
- 如果 best body candidate 合理但 georef 误差大，排查 body→geo：旋转顺序、轴向符号、boresight、lever-arm。
- 未通过本 gate 前，不跑全量 CH1 v2、CH2、去噪或 LAZ。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def write_report_clean(
    path: Path,
    body_rows: list[dict[str, Any]],
    mapping_rows: list[dict[str, Any]],
    offset_rows: list[dict[str, Any]],
    georef_rows: list[dict[str, Any]],
    sample_count: int,
    matched_count: int,
    max_dt: float,
    match_mode: str,
) -> None:
    best_body = body_rows[0] if body_rows else {}
    best_mapping = mapping_rows[0] if mapping_rows else {}
    best_offset = offset_rows[0] if offset_rows else {}
    best_georef = sorted(
        georef_rows,
        key=lambda row: row["easting_rmse_m"] + row["northing_rmse_m"] + row["height_rmse_m"],
    )[0] if georef_rows else {}

    if best_offset and best_offset.get("offset_vector_rmse_m", 999.0) < 1.0:
        conclusion = "基本合理"
        recommendation = "当前 body->NED offset 能较好复现参考 L3；下一步可进入小样本坐标重算验证。"
    else:
        conclusion = "不合理"
        recommendation = "当前 range/scan/body->NED 模型无法稳定复现参考 L3 的 LIDAR_X/Y/Z；优先修正扫描角零位、角度方向、距离零位或 boresight/lever-arm。"

    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 5G CH1 几何转换模型返查报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}
- 阶段：stage5g_ch1_geometry_audit
- 样例：00111
- L1 sample count: {sample_count}
- Reference matched count: {matched_count}
- Match mode: {match_mode}
- Max nearest time delta: {max_dt} s

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Best Body Candidate

- zero strategy: {best_body.get('zero_strategy')}
- angle mode: {best_body.get('angle_mode')}
- zero used: {best_body.get('zero_used_m')} m
- direct LIDAR vector RMSE: {best_body.get('direct_lidar_vector_rmse_m')}

说明：参考 L3 的 `LIDAR_X/Y/Z` 已验证为导航系偏移量，不是原始 body 坐标；本项只作为早期候选参考，最终判断看下面的 offset candidate。

## Best Axis Mapping Candidate

- mapping: {best_mapping.get('mapping')}
- allow scale: {best_mapping.get('allow_scale')}
- mean RMSE: {best_mapping.get('mean_rmse_m')}
- max RMSE: {best_mapping.get('max_rmse_m')}

## Best Offset Candidate

- zero strategy: {best_offset.get('zero_strategy')}
- angle mode: {best_offset.get('angle_mode')}
- rotation mode: {best_offset.get('rotation_mode')}
- north offset RMSE: {best_offset.get('north_offset_rmse_m')}
- east offset RMSE: {best_offset.get('east_offset_rmse_m')}
- down offset RMSE: {best_offset.get('down_offset_rmse_m')}
- vector RMSE: {best_offset.get('offset_vector_rmse_m')}

## Best Georef Candidate

- rotation mode: {best_georef.get('rotation_mode')}
- easting RMSE: {best_georef.get('easting_rmse_m')}
- northing RMSE: {best_georef.get('northing_rmse_m')}
- height RMSE: {best_georef.get('height_rmse_m')}
- diagnostic height bias: {best_georef.get('height_bias_m')}

## Outputs

- Body candidates CSV: `outputs\\qc\\stage5g_geometry_audit\\body_candidate_errors.csv`
- Axis mapping CSV: `outputs\\qc\\stage5g_geometry_audit\\axis_mapping_errors.csv`
- Offset candidate CSV: `outputs\\qc\\stage5g_geometry_audit\\offset_candidate_errors.csv`
- Georef candidate CSV: `outputs\\qc\\stage5g_geometry_audit\\georef_candidate_errors.csv`

## Known Warnings

- 本阶段只做诊断，不生成最终坐标成果。
- 候选扫描角/轴向/零位均为 `PROJECT_EMPIRICAL_PARAMETER`，不能写成论文算法。
- 若 reference L3 的 `LIDAR_X/Y/Z` 与当前 L1 点序并非一一对应，本报告会作为方向性诊断，而不是最终标定结果。

## Manual Checklist

- 如果 best offset candidate 仍误差很大，先排查 L1->body->NED：零位、扫描角方向、F_BodyFrame_XYZ 参数、boresight、lever-arm。
- 如果 best offset candidate 合理但 georef 误差大，排查 POS 旋转顺序、轴向符号、UTM/EPSG 投影。
- 未通过本 gate 前，不跑全量 CH1 v2、CH2、去噪或 LAZ。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5G CH1 geometry model audit against reference L3.")
    parser.add_argument("--max-matched-points", type=int, default=30_000)
    parser.add_argument("--match-mode", choices=["exact", "nearest"], default="exact")
    parser.add_argument("--max-dt-sec", type=float, default=2e-6)
    parser.add_argument("--allow-scale", action="store_true")
    parser.add_argument("--top-candidates", type=int, default=4)
    args = parser.parse_args()

    print("Loading calibration/reference/L1 sample...", flush=True)
    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")
    reference = load_reference()
    l1 = load_l1_all()
    lidar_time = l1["gnss"] + pipe.DEFAULT_TIME_OFFSET_SEC
    if args.match_mode == "exact":
        l1_idx, ref_idx = exact_reference_match(lidar_time, reference["time"])
        dt = np.zeros(l1_idx.size, dtype=np.float64)
    else:
        l1_idx, ref_idx, dt = nearest_reference_match(lidar_time, reference["time"], args.max_dt_sec)
    if l1_idx.size < 100:
        raise RuntimeError(f"Too few matched points: {l1_idx.size}. Increase --max-dt-sec or max sample count.")
    print(f"Matched points before thinning: {l1_idx.size:,}", flush=True)
    if l1_idx.size > args.max_matched_points:
        keep = np.linspace(0, l1_idx.size - 1, args.max_matched_points, dtype=np.int64)
        l1_idx = l1_idx[keep]
        ref_idx = ref_idx[keep]
        dt = dt[keep]
    print(f"Matched points used: {l1_idx.size:,}", flush=True)

    range_before = l1["raw_dist"][l1_idx].astype(np.float64) * DIST_FACTOR
    coder = l1["coder"][l1_idx]
    ref_matched = {key: value[ref_idx] for key, value in reference.items() if key != "time"}
    ref_lidar = np.column_stack([ref_matched["lidar_x"], ref_matched["lidar_y"], ref_matched["lidar_z"]])

    print("Evaluating range/scan angle body candidates...", flush=True)
    body_rows: list[dict[str, Any]] = []
    candidate_bodies: dict[tuple[str, str], np.ndarray] = {}
    for zero_strategy in ["Z0", "Z1", "NONE"]:
        range_m, zero_used = range_for_strategy(range_before, calibration, zero_strategy)
        for angle_mode in ["360-angle", "angle", "angle+180", "180-angle"]:
            bx, by, bz, model_angle = candidate_body(range_m, coder, angle_mode)
            body = np.column_stack([bx, by, bz])
            candidate_bodies[(zero_strategy, angle_mode)] = body
            # Direct vector comparison is only meaningful if reference LIDAR axes match our body axes.
            direct_diff = body - ref_lidar
            body_rows.append(
                {
                    "zero_strategy": zero_strategy,
                    "angle_mode": angle_mode,
                    "zero_used_m": zero_used,
                    "direct_lidar_x_rmse_m": robust_stats(direct_diff[:, 0])["rmse"],
                    "direct_lidar_y_rmse_m": robust_stats(direct_diff[:, 1])["rmse"],
                    "direct_lidar_z_rmse_m": robust_stats(direct_diff[:, 2])["rmse"],
                    "direct_lidar_vector_rmse_m": float(np.sqrt(np.mean(np.sum(direct_diff**2, axis=1)))),
                }
            )
    body_rows = sorted(body_rows, key=lambda row: row["direct_lidar_vector_rmse_m"])

    print("Evaluating body axis mapping candidates...", flush=True)
    mapping_rows: list[dict[str, Any]] = []
    allow_scale_options = [False, True] if args.allow_scale else [False]
    for row in body_rows[: args.top_candidates]:
        body = candidate_bodies[(row["zero_strategy"], row["angle_mode"])]
        for allow_scale in allow_scale_options:
            for mapping in best_axis_mapping(body, ref_lidar, allow_scale)[:3]:
                mapping_rows.append(
                    {
                        "zero_strategy": row["zero_strategy"],
                        "angle_mode": row["angle_mode"],
                        "mapping": mapping["mapping"],
                        "allow_scale": mapping["allow_scale"],
                        "mean_rmse_m": mapping["mean_rmse_m"],
                        "max_rmse_m": mapping["max_rmse_m"],
                        "details_json": json.dumps(mapping["details"], ensure_ascii=False),
                    }
                )
    mapping_rows = sorted(mapping_rows, key=lambda row: (row["mean_rmse_m"], row["max_rmse_m"]))

    print("Evaluating current georeference candidate errors...", flush=True)
    pos_time, pos, _ = stage5.load_pos()
    offset_rows: list[dict[str, Any]] = []
    georef_rows: list[dict[str, Any]] = []
    # Offset/georef diagnostics must cover every zero/scan-angle candidate.
    # Filtering by direct body-vector rank can hide the fixed-zero candidate.
    for row in body_rows:
        body = candidate_bodies[(row["zero_strategy"], row["angle_mode"])]
        for rotation_mode in ["current"]:
            off = compute_offset_variant(
                body,
                lidar_time[l1_idx],
                ref_lidar,
                pos_time,
                pos,
                rotation_mode,
            )
            offset_rows.append({"zero_strategy": row["zero_strategy"], "angle_mode": row["angle_mode"], **off})
            geo = compute_georef_variant(
                body,
                lidar_time[l1_idx],
                {
                    "point_x": ref_matched["point_x"],
                    "point_y": ref_matched["point_y"],
                    "point_z": ref_matched["point_z"],
                },
                pos_time,
                pos,
                rotation_mode,
            )
            georef_rows.append({"zero_strategy": row["zero_strategy"], "angle_mode": row["angle_mode"], **geo})
    offset_rows = sorted(offset_rows, key=lambda row: row["offset_vector_rmse_m"])
    georef_rows = sorted(
        georef_rows,
        key=lambda row: row["easting_rmse_m"] + row["northing_rmse_m"] + row["height_rmse_m"],
    )

    write_csv(
        QC_DIR / "body_candidate_errors.csv",
        body_rows,
        [
            "zero_strategy",
            "angle_mode",
            "zero_used_m",
            "direct_lidar_x_rmse_m",
            "direct_lidar_y_rmse_m",
            "direct_lidar_z_rmse_m",
            "direct_lidar_vector_rmse_m",
        ],
    )
    write_csv(
        QC_DIR / "axis_mapping_errors.csv",
        mapping_rows,
        ["zero_strategy", "angle_mode", "mapping", "allow_scale", "mean_rmse_m", "max_rmse_m", "details_json"],
    )
    write_csv(
        QC_DIR / "offset_candidate_errors.csv",
        offset_rows,
        [
            "zero_strategy",
            "angle_mode",
            "rotation_mode",
            "north_offset_rmse_m",
            "east_offset_rmse_m",
            "down_offset_rmse_m",
            "offset_vector_rmse_m",
            "north_offset_median_error_m",
            "east_offset_median_error_m",
            "down_offset_median_error_m",
            "north_offset_p90_abs_error_m",
            "east_offset_p90_abs_error_m",
            "down_offset_p90_abs_error_m",
        ],
    )
    write_csv(
        QC_DIR / "georef_candidate_errors.csv",
        georef_rows,
        [
            "zero_strategy",
            "angle_mode",
            "rotation_mode",
            "easting_rmse_m",
            "northing_rmse_m",
            "height_rmse_m",
            "height_bias_m",
            "easting_median_error_m",
            "northing_median_error_m",
            "height_median_error_m",
        ],
    )
    write_report_clean(
        REPORT_DIR / "stage5g_geometry_audit_report.md",
        body_rows,
        mapping_rows,
        offset_rows,
        georef_rows,
        int(l1["idx"].size),
        int(l1_idx.size),
        args.max_dt_sec,
        args.match_mode,
    )
    (REPORT_DIR / "stage5g_geometry_audit_report.json").write_text(
        json.dumps(
            {
                "stage_name": "stage5g_ch1_geometry_audit",
                "l1_sample": rel(L1_SAMPLE),
                "reference_l3": rel(REFERENCE_L3),
                "sample_count": int(l1["idx"].size),
                "matched_count": int(l1_idx.size),
                "max_matched_points": args.max_matched_points,
                "match_mode": args.match_mode,
                "max_dt_sec": args.max_dt_sec,
                "best_body": body_rows[0] if body_rows else None,
                "best_mapping": mapping_rows[0] if mapping_rows else None,
                "best_offset": offset_rows[0] if offset_rows else None,
                "best_georef": georef_rows[0] if georef_rows else None,
                "method_registry": METHOD_REGISTRY,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )

    print("Stage 5G geometry audit complete.")
    print(f"Report: {REPORT_DIR / 'stage5g_geometry_audit_report.md'}")
    print(f"Body CSV: {QC_DIR / 'body_candidate_errors.csv'}")
    print(f"Axis mapping CSV: {QC_DIR / 'axis_mapping_errors.csv'}")
    print(f"Offset CSV: {QC_DIR / 'offset_candidate_errors.csv'}")
    print(f"Georef CSV: {QC_DIR / 'georef_candidate_errors.csv'}")


if __name__ == "__main__":
    main()
