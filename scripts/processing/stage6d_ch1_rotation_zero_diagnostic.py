from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6d_rotation_zero_diagnostic"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

MATCH_RETURN_STRATEGY = "far_return_refnorm"
MIN_FAR_RANGE_M = 30.0

ANGLE_DIRECTIONS = ["angle", "360-angle"]
ANGLE_OFFSETS_DEG = [-5.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 5.0]
ROTATION_ORDERS = ["ZYX", "ZXY", "YXZ", "XYZ"]
HEADING_CONVENTIONS = ["heading", "360-heading", "heading+180", "heading-90", "90-heading"]
ZERO_MODES = ["estimated", "fixed_stage6", "fixed_calib", "none"]

DIST_FACTOR = diag.DIST_FACTOR
STAGE6_ZERO_OFFSET_M = 20.486969030907204

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
        "method_name": "Heading/roll/pitch convention, scan-angle direction/zero, and range-zero diagnostic grid",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Exact-time comparison with existing L3 00111; not final production calibration",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "EXACT_TIME_MATCH_QC",
        "method_name": "Reference L3 exact GNSS time validation",
        "source_type": "project_qc_rule",
        "source_reference": "Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18",
        "used_for_delete_or_transform": "no, QC only",
    },
]


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def candidate_fields() -> list[str]:
    return [
        "rank",
        "zero_mode",
        "zero_offset_m",
        "angle_direction",
        "angle_offset_deg",
        "roll_sign",
        "pitch_sign",
        "heading_sign",
        "heading_convention",
        "rotation_order",
        "rotation_transpose",
        "vector_rmse_m",
        "north_rmse_m",
        "east_rmse_m",
        "down_rmse_m",
        "horizontal_rmse_m",
        "north_median_m",
        "east_median_m",
        "down_median_m",
        "north_mad_m",
        "east_mad_m",
        "down_mad_m",
        "north_p90_abs_m",
        "east_p90_abs_m",
        "down_p90_abs_m",
        "horizontal_p90_m",
        "bias_removed_vector_rmse_m",
        "bias_removed_horizontal_rmse_m",
    ]


def robust_sample_indices(size: int, count: int) -> np.ndarray:
    if count <= 0 or count >= size:
        return np.arange(size, dtype=np.int64)
    return np.linspace(0, size - 1, count, dtype=np.int64)


def scan_angle(coder: np.ndarray, direction: str, offset_deg: float) -> np.ndarray:
    base = coder * 360.0 / 65536.0
    if direction == "angle":
        angle = base
    elif direction == "360-angle":
        angle = 360.0 - base
    else:
        raise ValueError(direction)
    return np.mod(angle + offset_deg, 360.0)


def prepare_angles(
    data: dict[str, np.ndarray],
    roll_sign: int,
    pitch_sign: int,
    heading_sign: int,
    heading_convention: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    roll = roll_sign * np.deg2rad(data["roll_deg"].astype(np.float64))
    pitch = pitch_sign * np.deg2rad(data["pitch_deg"].astype(np.float64))
    heading_base = np.deg2rad(data["heading_deg"].astype(np.float64))
    heading = diag.heading_for_candidate(heading_base, heading_sign, heading_convention)
    return roll, pitch, heading


def metrics(diff: np.ndarray) -> dict[str, float]:
    rmse = np.sqrt(np.mean(diff**2, axis=0))
    med = np.median(diff, axis=0)
    mad = np.median(np.abs(diff - med), axis=0)
    p90 = np.percentile(np.abs(diff), 90, axis=0)
    horizontal = np.sqrt(diff[:, 0] ** 2 + diff[:, 1] ** 2)
    debiased = diff - med
    debiased_horizontal = np.sqrt(debiased[:, 0] ** 2 + debiased[:, 1] ** 2)
    return {
        "north_rmse_m": float(rmse[0]),
        "east_rmse_m": float(rmse[1]),
        "down_rmse_m": float(rmse[2]),
        "horizontal_rmse_m": float(np.sqrt(np.mean(horizontal**2))),
        "vector_rmse_m": float(np.sqrt(np.mean(np.sum(diff**2, axis=1)))),
        "north_median_m": float(med[0]),
        "east_median_m": float(med[1]),
        "down_median_m": float(med[2]),
        "north_mad_m": float(mad[0]),
        "east_mad_m": float(mad[1]),
        "down_mad_m": float(mad[2]),
        "north_p90_abs_m": float(p90[0]),
        "east_p90_abs_m": float(p90[1]),
        "down_p90_abs_m": float(p90[2]),
        "horizontal_p90_m": float(np.percentile(horizontal, 90)),
        "bias_removed_vector_rmse_m": float(np.sqrt(np.mean(np.sum(debiased**2, axis=1)))),
        "bias_removed_horizontal_rmse_m": float(np.sqrt(np.mean(debiased_horizontal**2))),
    }


def estimate_zero_offset(
    range_before: np.ndarray,
    unit_offsets: np.ndarray,
    target_offsets: np.ndarray,
    calibration: dict[str, float],
) -> float:
    """Least-squares zero estimate for pred=(range_before-zero-intercept)/slope * unit."""
    unit_norm_sq = np.sum(unit_offsets * unit_offsets, axis=1)
    numerator = np.sum((range_before - calibration["intercept"]) * unit_norm_sq)
    numerator -= calibration["slope"] * np.sum(np.sum(target_offsets * unit_offsets, axis=1))
    denominator = np.sum(unit_norm_sq)
    if denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def evaluate_candidate(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
    zero_mode: str,
    angle_direction: str,
    angle_offset_deg: float,
    roll_sign: int,
    pitch_sign: int,
    heading_sign: int,
    heading_convention: str,
    rotation_order: str,
    rotation_transpose: bool,
) -> dict[str, Any]:
    angle = scan_angle(data["coder"], angle_direction, angle_offset_deg)
    unit = np.column_stack(pipe.f_body_frame_xyz(np.ones_like(angle), angle))
    roll, pitch, heading = prepare_angles(data, roll_sign, pitch_sign, heading_sign, heading_convention)
    rotated_unit = diag.rotate_frd_to_ned(unit, roll, pitch, heading, rotation_order, rotation_transpose)
    truth = np.column_stack([data["ref_north_offset"], data["ref_east_offset"], data["ref_down_offset"]])

    if zero_mode == "estimated":
        zero = estimate_zero_offset(data["range_before"], rotated_unit, truth, calibration)
    elif zero_mode == "fixed_stage6":
        zero = STAGE6_ZERO_OFFSET_M
    elif zero_mode == "fixed_calib":
        zero = float(calibration["zero_offset"])
    elif zero_mode == "none":
        zero = 0.0
    else:
        raise ValueError(zero_mode)

    corrected_range = (data["range_before"] - zero - calibration["intercept"]) / calibration["slope"]
    pred = rotated_unit * corrected_range[:, None]
    diff = pred - truth
    row: dict[str, Any] = {
        "zero_mode": zero_mode,
        "zero_offset_m": float(zero),
        "angle_direction": angle_direction,
        "angle_offset_deg": float(angle_offset_deg),
        "roll_sign": int(roll_sign),
        "pitch_sign": int(pitch_sign),
        "heading_sign": int(heading_sign),
        "heading_convention": heading_convention,
        "rotation_order": rotation_order,
        "rotation_transpose": bool(rotation_transpose),
    }
    row.update(metrics(diff))
    return row


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda r: (r["vector_rmse_m"], r["down_rmse_m"], r["horizontal_rmse_m"]))
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx
    return rows


def gate_conclusion(best: dict[str, Any]) -> tuple[str, str]:
    if not best:
        return "不合理", "没有生成有效候选。"
    vector = float(best["vector_rmse_m"])
    down = float(best["down_rmse_m"])
    p90_down = float(best["down_p90_abs_m"])
    if vector < 1.5 and down < 0.5 and p90_down < 1.0:
        return "合理", "旋转/扫描角/零位候选可以较好复现参考 L3，但仍需在连续段验证。"
    if vector < 2.5 and down < 1.0:
        return "基本合理但有风险", "候选接近参考 L3，但仍存在米级水平或扫描角相关残差。"
    return "不合理", "仅调整 heading/roll/pitch 约定、扫描角零位/方向和 range zero offset 仍无法充分复现参考 L3。"


def write_report(payload: dict[str, Any]) -> None:
    best = payload.get("best_candidate") or {}
    conclusion = payload["gate"]["conclusion"]
    reason = payload["gate"]["reason"]
    content = f"""# Stage 6D CH1 Rotation / Scan Angle / Range Zero Diagnostic

## 结论

- Gate conclusion: {conclusion}
- Reason: {reason}

## Scope

- 只处理 CH1 `00111` 与已有 L3 精确时间匹配点。
- 传感器坐标仍使用 `f_body_frame_xyz()`。
- 安置角、偏心分量、boresight、lever-arm 全部固定为 0，不参与搜索。
- 本阶段只诊断 heading/roll/pitch 旋转约定、扫描角方向/零位、range zero offset。
- 不生成最终点云，不覆盖 H5/LAZ。

## Best Candidate

- zero_mode: `{best.get('zero_mode')}`
- zero_offset_m: {best.get('zero_offset_m')}
- angle_direction: `{best.get('angle_direction')}`
- angle_offset_deg: {best.get('angle_offset_deg')}
- roll_sign: {best.get('roll_sign')}
- pitch_sign: {best.get('pitch_sign')}
- heading_sign: {best.get('heading_sign')}
- heading_convention: `{best.get('heading_convention')}`
- rotation_order: `{best.get('rotation_order')}`
- rotation_transpose: {best.get('rotation_transpose')}
- vector_rmse_m: {best.get('vector_rmse_m')}
- horizontal_rmse_m: {best.get('horizontal_rmse_m')}
- down_rmse_m: {best.get('down_rmse_m')}
- median residual N/E/D m: {best.get('north_median_m')}, {best.get('east_median_m')}, {best.get('down_median_m')}
- bias_removed_vector_rmse_m: {best.get('bias_removed_vector_rmse_m')}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
"""
    for method in METHOD_REGISTRY:
        content += (
            f"| {method['method_id']} | {method['method_name']} | {method['source_type']} | "
            f"{method['source_reference']} | {method['used_for_delete_or_transform']} |\n"
        )
    content += f"""

## Outputs

- Candidate summary: `{payload['outputs']['candidate_summary']}`
- Top candidates: `{payload['outputs']['top_candidates']}`
- Best candidate JSON: `{payload['outputs']['best_candidate_json']}`
- Report JSON: `{payload['outputs']['report_json']}`

## Manual Check

- 如果 best candidate 仍有明显 N/E 固定偏差，说明还需要后续整体平移或杆臂/安装参数诊断。
- 如果 bias-removed RMSE 明显低于 raw RMSE，说明固定平移占较大比例。
- 如果所有候选 RMSE 仍较大，说明问题不只在本阶段三类参数，需回到 `f_body_frame_xyz()` 或回波匹配/滤波模型。
"""
    path = REPORT_DIR / "stage6d_ch1_rotation_zero_diagnostic_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    data = diag.load_matched_data(args.max_matched_points, MATCH_RETURN_STRATEGY, MIN_FAR_RANGE_M)
    sample_idx = robust_sample_indices(data["matched_time"].size, args.search_points)
    search_data = {key: value[sample_idx] if isinstance(value, np.ndarray) and value.shape[:1] == data["matched_time"].shape[:1] else value for key, value in data.items()}

    rows: list[dict[str, Any]] = []
    total = (
        len(ZERO_MODES)
        * len(ANGLE_DIRECTIONS)
        * len(ANGLE_OFFSETS_DEG)
        * 2
        * 2
        * 2
        * len(HEADING_CONVENTIONS)
        * len(ROTATION_ORDERS)
        * 2
    )
    done = 0
    for zero_mode, direction, offset, roll_sign, pitch_sign, heading_sign, heading_conv, order, transpose in itertools.product(
        ZERO_MODES,
        ANGLE_DIRECTIONS,
        ANGLE_OFFSETS_DEG,
        [-1, 1],
        [-1, 1],
        [-1, 1],
        HEADING_CONVENTIONS,
        ROTATION_ORDERS,
        [False, True],
    ):
        rows.append(
            evaluate_candidate(
                search_data,
                calibration,
                zero_mode,
                direction,
                offset,
                roll_sign,
                pitch_sign,
                heading_sign,
                heading_conv,
                order,
                transpose,
            )
        )
        done += 1
        if args.progress and done % 1000 == 0:
            print(f"searched {done}/{total}", flush=True)

    rows = sort_rows(rows)
    top_search = rows[: args.top_final_eval_count]
    final_rows = [
        evaluate_candidate(
            data,
            calibration,
            row["zero_mode"],
            row["angle_direction"],
            row["angle_offset_deg"],
            int(row["roll_sign"]),
            int(row["pitch_sign"]),
            int(row["heading_sign"]),
            row["heading_convention"],
            row["rotation_order"],
            bool(row["rotation_transpose"]),
        )
        for row in top_search
    ]
    final_rows = sort_rows(final_rows)
    best = final_rows[0] if final_rows else {}
    conclusion, reason = gate_conclusion(best)

    candidate_csv = OUT_DIR / "candidate_summary_search_sample.csv"
    top_csv = OUT_DIR / "top_candidates_full_eval.csv"
    best_json = OUT_DIR / "best_candidate.json"
    report_json = REPORT_DIR / "stage6d_ch1_rotation_zero_diagnostic_report.json"
    write_csv(candidate_csv, rows, candidate_fields())
    write_csv(top_csv, final_rows, candidate_fields())
    write_json(best_json, best)

    payload = {
        "stage_name": "stage6d_ch1_rotation_zero_diagnostic",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "reference_l3": str(diag.REFERENCE_L3),
            "l1_sample": str(diag.L1_SAMPLE),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
        },
        "assumptions": {
            "sensor_coordinates": "f_body_frame_xyz",
            "boresight_deg": [0.0, 0.0, 0.0],
            "lever_arm_m": [0.0, 0.0, 0.0],
            "match_return_strategy": MATCH_RETURN_STRATEGY,
            "min_far_range_m": MIN_FAR_RANGE_M,
            "lidar_time_offset_sec": pipe.DEFAULT_TIME_OFFSET_SEC,
        },
        "search": {
            "max_matched_points": args.max_matched_points,
            "search_points": int(search_data["matched_time"].size),
            "full_eval_points": int(data["matched_time"].size),
            "candidate_count": len(rows),
            "top_final_eval_count": args.top_final_eval_count,
            "angle_offsets_deg": ANGLE_OFFSETS_DEG,
            "zero_modes": ZERO_MODES,
        },
        "best_candidate": best,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "recommendation": "人工检查报告后再决定是否进入 Stage 6E 小样本重算；本阶段不允许直接全量应用候选。",
        },
        "outputs": {
            "candidate_summary": str(candidate_csv),
            "top_candidates": str(top_csv),
            "best_candidate_json": str(best_json),
            "report_json": str(report_json),
            "report_md": str(REPORT_DIR / "stage6d_ch1_rotation_zero_diagnostic_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)
    print(json.dumps(jsonable({"gate": payload["gate"], "best_candidate": best, "outputs": payload["outputs"]}), ensure_ascii=False, indent=2), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6D CH1 rotation, scan-angle, and range-zero diagnostic against existing L3 00111.")
    parser.add_argument("--max-matched-points", type=int, default=100_000, help="Maximum exact-time reference points to load.")
    parser.add_argument("--search-points", type=int, default=5_000, help="Stratified points used for broad grid search.")
    parser.add_argument("--top-final-eval-count", type=int, default=100, help="Top candidates re-evaluated on full loaded points.")
    parser.add_argument("--progress", action="store_true", help="Print grid-search progress.")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
