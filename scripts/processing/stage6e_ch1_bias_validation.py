from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag
import stage6d_ch1_rotation_zero_diagnostic as stage6d


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6e_bias_validation"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

ZERO_OFFSET_M = 20.49460272584239
ANGLE_DIRECTION = "360-angle"
ANGLE_OFFSET_DEG = 1.0
ROLL_SIGN = 1
PITCH_SIGN = 1
HEADING_SIGN = -1
HEADING_CONVENTION = "heading+180"
ROTATION_ORDER = "YXZ"
ROTATION_TRANSPOSE = True

# Stage 6D median residual is pred - reference in N/E/D.
BIAS_CORRECTION_NED_M = np.array(
    [1.5006186931180263, -0.6625962236673231, -0.3428576246215087],
    dtype=np.float64,
)

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
        "method_name": "Stage 6D rotation/scan/range-zero plus Stage 6E fixed bias diagnostic",
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


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_stage6d_prediction(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
) -> dict[str, np.ndarray]:
    angle = stage6d.scan_angle(data["coder"], ANGLE_DIRECTION, ANGLE_OFFSET_DEG)
    unit_frd = np.column_stack(pipe.f_body_frame_xyz(np.ones_like(angle), angle))
    roll, pitch, heading = stage6d.prepare_angles(
        data,
        ROLL_SIGN,
        PITCH_SIGN,
        HEADING_SIGN,
        HEADING_CONVENTION,
    )
    unit_ned = diag.rotate_frd_to_ned(unit_frd, roll, pitch, heading, ROTATION_ORDER, ROTATION_TRANSPOSE)
    range_m = (data["range_before"] - ZERO_OFFSET_M - calibration["intercept"]) / calibration["slope"]
    pred_ned = unit_ned * range_m[:, None]
    truth_ned = np.column_stack(
        [data["ref_north_offset"], data["ref_east_offset"], data["ref_down_offset"]]
    )
    return {
        "angle_deg": angle,
        "range_m": range_m,
        "pred_ned": pred_ned,
        "truth_ned": truth_ned,
        "bias_pred_ned": pred_ned + BIAS_CORRECTION_NED_M[None, :],
    }


def coordinate_arrays(data: dict[str, np.ndarray], ned_offsets: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    northing = data["pos_northing"] + ned_offsets[:, 0]
    easting = data["pos_easting"] + ned_offsets[:, 1]
    height = data["pos_height"] - ned_offsets[:, 2]
    return easting, northing, height


def reference_coordinate_arrays(data: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return data["ref_easting"], data["ref_northing"], data["ref_height"]


def metrics_with_prefix(diff: np.ndarray, prefix: str) -> dict[str, float]:
    base = stage6d.metrics(diff)
    return {f"{prefix}_{key}": value for key, value in base.items()}


def scan_bin_rows(angle_deg: np.ndarray, raw_diff: np.ndarray, bias_diff: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bins = np.arange(0.0, 361.0, 30.0)
    for lo, hi in zip(bins[:-1], bins[1:]):
        if hi >= 360.0:
            mask = (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = (angle_deg >= lo) & (angle_deg < hi)
        if not np.any(mask):
            continue
        raw = stage6d.metrics(raw_diff[mask])
        biased = stage6d.metrics(bias_diff[mask])
        rows.append(
            {
                "scan_bin_deg": f"{int(lo):03d}-{int(hi):03d}",
                "point_count": int(np.count_nonzero(mask)),
                "raw_vector_rmse_m": raw["vector_rmse_m"],
                "raw_horizontal_rmse_m": raw["horizontal_rmse_m"],
                "raw_down_rmse_m": raw["down_rmse_m"],
                "raw_north_median_m": raw["north_median_m"],
                "raw_east_median_m": raw["east_median_m"],
                "raw_down_median_m": raw["down_median_m"],
                "bias_vector_rmse_m": biased["vector_rmse_m"],
                "bias_horizontal_rmse_m": biased["horizontal_rmse_m"],
                "bias_down_rmse_m": biased["down_rmse_m"],
                "bias_north_median_m": biased["north_median_m"],
                "bias_east_median_m": biased["east_median_m"],
                "bias_down_median_m": biased["down_median_m"],
            }
        )
    return rows


def write_cloudcompare_txt(
    path: Path,
    easting: np.ndarray,
    northing: np.ndarray,
    height: np.ndarray,
    gps_time: np.ndarray,
    angle_deg: np.ndarray,
    range_m: np.ndarray,
    label: str,
    max_points: int,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if max_points > 0 and easting.size > max_points:
        idx = np.linspace(0, easting.size - 1, max_points, dtype=np.int64)
    else:
        idx = np.arange(easting.size, dtype=np.int64)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("X Y Z height_m gps_time scan_angle_deg range_m label\n")
        for i in idx:
            f.write(
                f"{easting[i]:.9f} {northing[i]:.9f} {height[i]:.9f} "
                f"{height[i]:.9f} {gps_time[i]:.9f} {angle_deg[i]:.9f} {range_m[i]:.9f} {label}\n"
            )
    return int(idx.size)


def gate_conclusion(bias_metrics: dict[str, float]) -> tuple[str, str, bool]:
    vector = bias_metrics["vector_rmse_m"]
    horizontal = bias_metrics["horizontal_rmse_m"]
    med_abs = max(
        abs(bias_metrics["north_median_m"]),
        abs(bias_metrics["east_median_m"]),
        abs(bias_metrics["down_median_m"]),
    )
    if vector <= 0.95 and horizontal <= 0.85 and med_abs <= 0.15:
        return "合理", "固定平移能解释主要系统偏差；进入 Stage 6F 检查其是否可由 body/FRD 杆臂和小安置角解释。", True
    return "基本合理但有风险", "固定平移有改善但未达到 6E gate；Stage 6F 仍可作为诊断，但不能直接进入连续段。", False


def write_report(payload: dict[str, Any]) -> None:
    raw = payload["raw_metrics"]
    biased = payload["bias_corrected_metrics"]
    gate = payload["gate"]
    improvement = payload["improvement"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6E CH1 Bias Validation

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Recommendation: {gate['recommendation']}

## Fixed Parameters

- zero_offset_m: {ZERO_OFFSET_M}
- angle_direction: `{ANGLE_DIRECTION}`
- angle_offset_deg: {ANGLE_OFFSET_DEG}
- roll_sign / pitch_sign / heading_sign: {ROLL_SIGN}, {PITCH_SIGN}, {HEADING_SIGN}
- heading_convention: `{HEADING_CONVENTION}`
- rotation_order: `{ROTATION_ORDER}`
- rotation_transpose: {ROTATION_TRANSPOSE}
- diagnostic bias correction N/E/D m: {BIAS_CORRECTION_NED_M.tolist()}

## Key Metrics

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| raw Stage 6D fixed | {raw['vector_rmse_m']:.6f} | {raw['horizontal_rmse_m']:.6f} | {raw['down_rmse_m']:.6f} | {raw['north_median_m']:.6f}, {raw['east_median_m']:.6f}, {raw['down_median_m']:.6f} |
| bias corrected | {biased['vector_rmse_m']:.6f} | {biased['horizontal_rmse_m']:.6f} | {biased['down_rmse_m']:.6f} | {biased['north_median_m']:.6f}, {biased['east_median_m']:.6f}, {biased['down_median_m']:.6f} |

- vector_rmse_improvement_m: {improvement['vector_rmse_improvement_m']:.6f}
- vector_rmse_improvement_pct: {improvement['vector_rmse_improvement_pct']:.3f}%
- horizontal_rmse_improvement_m: {improvement['horizontal_rmse_improvement_m']:.6f}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Scan-bin residual CSV: `{payload['outputs']['scan_bins_csv']}`
- Raw CloudCompare TXT: `{payload['outputs'].get('raw_txt', 'not written')}`
- Bias-corrected CloudCompare TXT: `{payload['outputs'].get('bias_txt', 'not written')}`
- Reference CloudCompare TXT: `{payload['outputs'].get('reference_txt', 'not written')}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只验证固定平移，不生成最终点云，不覆盖 H5/LAZ。
- 固定平移仍是 `PROJECT_DIAGNOSTIC_PARAMETER`，只能用于判断是否继续 Stage 6F。
"""
    path = REPORT_DIR / "stage6e_ch1_bias_validation_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading exact-time matched 00111 data...", flush=True)
    data = diag.load_matched_data(args.max_matched_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")

    if args.progress:
        print("Computing Stage 6D fixed prediction and Stage 6E bias correction...", flush=True)
    prediction = build_stage6d_prediction(data, calibration)
    raw_diff = prediction["pred_ned"] - prediction["truth_ned"]
    bias_diff = prediction["bias_pred_ned"] - prediction["truth_ned"]
    raw_metrics = stage6d.metrics(raw_diff)
    bias_metrics = stage6d.metrics(bias_diff)

    scan_rows = scan_bin_rows(prediction["angle_deg"], raw_diff, bias_diff)
    scan_bins_csv = OUT_DIR / "scan_angle_bin_residuals.csv"
    write_csv(scan_bins_csv, scan_rows, list(scan_rows[0].keys()) if scan_rows else ["scan_bin_deg"])

    outputs: dict[str, Any] = {
        "scan_bins_csv": str(scan_bins_csv),
        "report_json": str(REPORT_DIR / "stage6e_ch1_bias_validation_report.json"),
        "report_md": str(REPORT_DIR / "stage6e_ch1_bias_validation_report.md"),
    }
    written_counts: dict[str, int] = {}
    if args.write_cloudcompare_txt:
        if args.progress:
            print("Writing CloudCompare TXT files...", flush=True)
        raw_e, raw_n, raw_h = coordinate_arrays(data, prediction["pred_ned"])
        bias_e, bias_n, bias_h = coordinate_arrays(data, prediction["bias_pred_ned"])
        ref_e, ref_n, ref_h = reference_coordinate_arrays(data)
        raw_txt = OUT_DIR / "stage6e_00111_raw_stage6d_fixed_cloudcompare.txt"
        bias_txt = OUT_DIR / "stage6e_00111_bias_corrected_cloudcompare.txt"
        ref_txt = OUT_DIR / "stage6e_00111_reference_l3_cloudcompare.txt"
        written_counts["raw_txt_points"] = write_cloudcompare_txt(
            raw_txt,
            raw_e,
            raw_n,
            raw_h,
            data["matched_time"],
            prediction["angle_deg"],
            prediction["range_m"],
            "raw_stage6d_fixed",
            args.txt_max_points,
        )
        written_counts["bias_txt_points"] = write_cloudcompare_txt(
            bias_txt,
            bias_e,
            bias_n,
            bias_h,
            data["matched_time"],
            prediction["angle_deg"],
            prediction["range_m"],
            "bias_corrected",
            args.txt_max_points,
        )
        written_counts["reference_txt_points"] = write_cloudcompare_txt(
            ref_txt,
            ref_e,
            ref_n,
            ref_h,
            data["matched_time"],
            prediction["angle_deg"],
            prediction["range_m"],
            "reference_l3",
            args.txt_max_points,
        )
        outputs.update({"raw_txt": str(raw_txt), "bias_txt": str(bias_txt), "reference_txt": str(ref_txt)})

    conclusion, reason, passed = gate_conclusion(bias_metrics)
    vector_improvement = raw_metrics["vector_rmse_m"] - bias_metrics["vector_rmse_m"]
    horizontal_improvement = raw_metrics["horizontal_rmse_m"] - bias_metrics["horizontal_rmse_m"]
    payload = {
        "stage_name": "stage6e_ch1_bias_validation",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "reference_l3": str(diag.REFERENCE_L3),
            "l1_sample": str(diag.L1_SAMPLE),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
        },
        "fixed_parameters": {
            "zero_offset_m": ZERO_OFFSET_M,
            "angle_direction": ANGLE_DIRECTION,
            "angle_offset_deg": ANGLE_OFFSET_DEG,
            "roll_sign": ROLL_SIGN,
            "pitch_sign": PITCH_SIGN,
            "heading_sign": HEADING_SIGN,
            "heading_convention": HEADING_CONVENTION,
            "rotation_order": ROTATION_ORDER,
            "rotation_transpose": ROTATION_TRANSPOSE,
            "bias_correction_ned_m": BIAS_CORRECTION_NED_M.tolist(),
        },
        "sampling": {
            "max_matched_points": args.max_matched_points,
            "matched_points_loaded": int(data["matched_time"].size),
            "exact_match_total": int(data["exact_match_total"][0]),
            "txt_max_points": args.txt_max_points,
            **written_counts,
        },
        "raw_metrics": raw_metrics,
        "bias_corrected_metrics": bias_metrics,
        "improvement": {
            "vector_rmse_improvement_m": float(vector_improvement),
            "vector_rmse_improvement_pct": float(100.0 * vector_improvement / raw_metrics["vector_rmse_m"]),
            "horizontal_rmse_improvement_m": float(horizontal_improvement),
            "horizontal_rmse_improvement_pct": float(100.0 * horizontal_improvement / raw_metrics["horizontal_rmse_m"]),
        },
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "passed": passed,
            "recommendation": "Run Stage 6F next; do not run Stage 6G until Stage 6F is analyzed.",
        },
        "outputs": outputs,
    }
    write_json(REPORT_DIR / "stage6e_ch1_bias_validation_report.json", payload)
    write_report(payload)

    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "raw_metrics": raw_metrics,
                    "bias_corrected_metrics": bias_metrics,
                    "improvement": payload["improvement"],
                    "outputs": outputs,
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6E CH1 fixed-bias validation against exact-time L3 00111.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--write-cloudcompare-txt", action="store_true")
    parser.add_argument("--txt-max-points", type=int, default=0, help="0 writes all loaded matched points.")
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
