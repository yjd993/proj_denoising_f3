import argparse
import csv
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag
import stage6d_ch1_rotation_zero_diagnostic as stage6d
import stage6e_ch1_bias_validation as stage6e
import stage6f_ch1_boresight_lever_diagnostic as stage6f


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6j_ladm2_diagnostic_export"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
STAGE6I_BEST = ROOT / "outputs" / "qc" / "stage6i_ladm2_scan_geometry_diagnostic" / "best_candidate.json"
STAGE6F_BEST = ROOT / "outputs" / "qc" / "stage6f_boresight_lever_diagnostic" / "best_candidate.json"

ZERO_OFFSET_M = stage6e.ZERO_OFFSET_M
ROTATION_ORDER = stage6e.ROTATION_ORDER
ROTATION_TRANSPOSE = stage6e.ROTATION_TRANSPOSE

METHOD_REGISTRY = [
    {
        "method_id": "CAO2017_LADM2_4_7_4_14",
        "method_name": "LADM-II mirror normal and reflected beam scan geometry",
        "source_type": "doctoral_thesis",
        "source_reference": "曹彬才, 遥感测深数据处理方法研究, section 4.4.2, formulas 4-7 to 4-14",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_PARAMETER",
        "method_name": "Stage 6J LADM-II diagnostic export for CloudCompare/H5 review",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Stage 6I best candidate applied to exact-time existing L3 00111 comparison",
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rotation_columns(n: int, roll: np.ndarray, pitch: np.ndarray, heading: np.ndarray) -> np.ndarray:
    basis = []
    for axis_idx in range(3):
        frd = np.zeros((n, 3), dtype=np.float64)
        frd[:, axis_idx] = 1.0
        basis.append(diag.rotate_frd_to_ned(frd, roll, pitch, heading, ROTATION_ORDER, ROTATION_TRANSPOSE))
    return np.stack(basis, axis=2)


def build_ladm2_prediction(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
    candidate: dict[str, Any],
) -> dict[str, np.ndarray]:
    angle = stage6d.scan_angle(data["coder"], candidate["angle_direction"], float(candidate["angle_offset_deg"]))
    range_m = (data["range_before"] - ZERO_OFFSET_M - calibration["intercept"]) / calibration["slope"]
    boresight = (
        float(candidate["boresight_roll_deg"]),
        float(candidate["boresight_pitch_deg"]),
        float(candidate["boresight_yaw_deg"]),
    )
    bx, by, bz = pipe.f_body_frame_xyz_ladm2(
        range_m,
        angle,
        mirror_tilt_deg=float(candidate["mirror_tilt_deg"]),
        frame_rotation_deg=float(candidate["frame_rotation_deg"]),
        axis_perm=tuple(int(v) for v in candidate["axis_perm"]),
        axis_signs=tuple(int(v) for v in candidate["axis_signs"]),
        boresight_deg=boresight,
    )
    frd = np.column_stack([bx, by, bz])
    roll, pitch, heading = stage6d.prepare_angles(
        data,
        stage6e.ROLL_SIGN,
        stage6e.PITCH_SIGN,
        stage6e.HEADING_SIGN,
        stage6e.HEADING_CONVENTION,
    )
    pred_no_lever = diag.rotate_frd_to_ned(frd, roll, pitch, heading, ROTATION_ORDER, ROTATION_TRANSPOSE)
    lever = np.array(
        [candidate["lever_x_m"], candidate["lever_y_m"], candidate["lever_z_m"]],
        dtype=np.float64,
    )
    pred_ned = pred_no_lever + np.einsum("nij,j->ni", rotation_columns(range_m.size, roll, pitch, heading), lever)
    truth_ned = np.column_stack([data["ref_north_offset"], data["ref_east_offset"], data["ref_down_offset"]])
    diff = pred_ned - truth_ned
    return {
        "angle_deg": angle,
        "range_m": range_m,
        "frd_x": frd[:, 0],
        "frd_y": frd[:, 1],
        "frd_z": frd[:, 2],
        "pred_ned": pred_ned,
        "truth_ned": truth_ned,
        "diff_ned": diff,
        "pred_easting": data["pos_easting"] + pred_ned[:, 1],
        "pred_northing": data["pos_northing"] + pred_ned[:, 0],
        "pred_height": data["pos_height"] - pred_ned[:, 2],
        "ref_easting": data["ref_easting"],
        "ref_northing": data["ref_northing"],
        "ref_height": data["ref_height"],
    }


def current_stage6f_metrics(data: dict[str, np.ndarray], calibration: dict[str, float]) -> dict[str, float]:
    candidate = load_json(STAGE6F_BEST)
    geom = stage6f.build_base_geometry(data, calibration)
    rotation_cols = stage6f.rotation_columns(geom)
    return stage6d.metrics(stage6f.diff_for_candidate(geom, rotation_cols, candidate))


def diagnostic_dtype() -> np.dtype:
    return np.dtype(
        [
            ("point_index", "u4"),
            ("gps_time", "f8"),
            ("easting_m", "f8"),
            ("northing_m", "f8"),
            ("height_m", "f8"),
            ("reference_easting_m", "f8"),
            ("reference_northing_m", "f8"),
            ("reference_height_m", "f8"),
            ("range_before_m", "f8"),
            ("range_m", "f8"),
            ("coder", "f8"),
            ("scan_angle_deg", "f8"),
            ("frd_x_m", "f8"),
            ("frd_y_m", "f8"),
            ("frd_z_m", "f8"),
            ("pred_north_offset_m", "f8"),
            ("pred_east_offset_m", "f8"),
            ("pred_down_offset_m", "f8"),
            ("ref_north_offset_m", "f8"),
            ("ref_east_offset_m", "f8"),
            ("ref_down_offset_m", "f8"),
            ("residual_north_m", "f8"),
            ("residual_east_m", "f8"),
            ("residual_down_m", "f8"),
            ("horizontal_error_m", "f8"),
            ("vector_error_m", "f8"),
        ]
    )


def build_diagnostic_points(data: dict[str, np.ndarray], pred: dict[str, np.ndarray]) -> np.ndarray:
    diff = pred["diff_ned"]
    points = np.empty(data["matched_time"].size, dtype=diagnostic_dtype())
    points["point_index"] = np.arange(points.size, dtype=np.uint32)
    points["gps_time"] = data["matched_time"]
    points["easting_m"] = pred["pred_easting"]
    points["northing_m"] = pred["pred_northing"]
    points["height_m"] = pred["pred_height"]
    points["reference_easting_m"] = pred["ref_easting"]
    points["reference_northing_m"] = pred["ref_northing"]
    points["reference_height_m"] = pred["ref_height"]
    points["range_before_m"] = data["range_before"]
    points["range_m"] = pred["range_m"]
    points["coder"] = data["coder"]
    points["scan_angle_deg"] = pred["angle_deg"]
    points["frd_x_m"] = pred["frd_x"]
    points["frd_y_m"] = pred["frd_y"]
    points["frd_z_m"] = pred["frd_z"]
    points["pred_north_offset_m"] = pred["pred_ned"][:, 0]
    points["pred_east_offset_m"] = pred["pred_ned"][:, 1]
    points["pred_down_offset_m"] = pred["pred_ned"][:, 2]
    points["ref_north_offset_m"] = pred["truth_ned"][:, 0]
    points["ref_east_offset_m"] = pred["truth_ned"][:, 1]
    points["ref_down_offset_m"] = pred["truth_ned"][:, 2]
    points["residual_north_m"] = diff[:, 0]
    points["residual_east_m"] = diff[:, 1]
    points["residual_down_m"] = diff[:, 2]
    points["horizontal_error_m"] = np.sqrt(diff[:, 0] ** 2 + diff[:, 1] ** 2)
    points["vector_error_m"] = np.sqrt(np.sum(diff * diff, axis=1))
    return points


def write_diagnostic_h5(
    path: Path,
    points: np.ndarray,
    candidate: dict[str, Any],
    metrics: dict[str, float],
    current6f: dict[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        grp = h5.create_group("STAGE6J")
        ch1 = grp.create_group("CH1")
        ch1.create_dataset("exact_time_points", data=points, compression="gzip", compression_opts=4, chunks=True)
        meta = h5.create_group("metadata")
        proc = meta.create_group("processing")
        pipe.write_str_attr(proc, "stage", "stage6j_ch1_ladm2_diagnostic_export")
        pipe.write_str_attr(proc, "source_l1", str(diag.L1_SAMPLE))
        pipe.write_str_attr(proc, "reference_l3", str(diag.REFERENCE_L3))
        pipe.write_str_attr(proc, "schema", "diagnostic_exact_time_ladm2_points")
        pipe.write_str_attr(proc, "crs", "EPSG:32651")
        pipe.write_str_attr(proc, "production_status", "diagnostic_only_not_final_l3")
        proc.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        proc.attrs["zero_offset_m"] = ZERO_OFFSET_M
        proc.attrs["stage6j_vector_rmse_m"] = metrics["vector_rmse_m"]
        proc.attrs["stage6j_horizontal_rmse_m"] = metrics["horizontal_rmse_m"]
        proc.attrs["stage6j_down_rmse_m"] = metrics["down_rmse_m"]
        proc.attrs["stage6f_vector_rmse_m"] = current6f["vector_rmse_m"]
        proc.attrs["stage6f_horizontal_rmse_m"] = current6f["horizontal_rmse_m"]
        cand_grp = meta.create_group("stage6i_best_candidate")
        for key, value in candidate.items():
            if isinstance(value, str):
                pipe.write_str_attr(cand_grp, key, value)
            elif isinstance(value, (int, float, np.integer, np.floating, np.bool_)):
                cand_grp.attrs[key] = value
            elif isinstance(value, list):
                cand_grp.create_dataset(key, data=np.asarray(value))


def write_cloudcompare_txt(
    path: Path,
    easting: np.ndarray,
    northing: np.ndarray,
    height: np.ndarray,
    gps_time: np.ndarray,
    angle_deg: np.ndarray,
    range_m: np.ndarray,
    vector_error: np.ndarray,
    horizontal_error: np.ndarray,
    down_error: np.ndarray,
    cloud_id: int,
    max_points: int,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if max_points > 0 and easting.size > max_points:
        idx = np.linspace(0, easting.size - 1, max_points, dtype=np.int64)
    else:
        idx = np.arange(easting.size, dtype=np.int64)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("X Y Z height_m gps_time scan_angle_deg range_m vector_error_m horizontal_error_m down_error_m cloud_id\n")
        for i in idx:
            f.write(
                f"{easting[i]:.9f} {northing[i]:.9f} {height[i]:.9f} {height[i]:.9f} "
                f"{gps_time[i]:.9f} {angle_deg[i]:.9f} {range_m[i]:.9f} "
                f"{vector_error[i]:.9f} {horizontal_error[i]:.9f} {down_error[i]:.9f} {cloud_id}\n"
            )
    return int(idx.size)


def write_merged_cloudcompare_txt(
    path: Path,
    data: dict[str, np.ndarray],
    pred: dict[str, np.ndarray],
    max_points: int,
) -> int:
    diff = pred["diff_ned"]
    vector = np.sqrt(np.sum(diff * diff, axis=1))
    horizontal = np.sqrt(diff[:, 0] ** 2 + diff[:, 1] ** 2)
    if max_points > 0 and vector.size > max_points:
        idx = np.linspace(0, vector.size - 1, max_points, dtype=np.int64)
    else:
        idx = np.arange(vector.size, dtype=np.int64)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("X Y Z height_m gps_time scan_angle_deg range_m vector_error_m horizontal_error_m down_error_m cloud_id\n")
        for cloud_id, easting, northing, height in [
            (1, pred["pred_easting"], pred["pred_northing"], pred["pred_height"]),
            (2, pred["ref_easting"], pred["ref_northing"], pred["ref_height"]),
        ]:
            for i in idx:
                f.write(
                    f"{easting[i]:.9f} {northing[i]:.9f} {height[i]:.9f} {height[i]:.9f} "
                    f"{data['matched_time'][i]:.9f} {pred['angle_deg'][i]:.9f} {pred['range_m'][i]:.9f} "
                    f"{vector[i]:.9f} {horizontal[i]:.9f} {diff[i, 2]:.9f} {cloud_id}\n"
                )
    return int(idx.size) * 2


def scan_bin_rows(angle_deg: np.ndarray, stage6j_diff: np.ndarray, stage6f_diff: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bins = np.arange(0.0, 361.0, 30.0)
    for lo, hi in zip(bins[:-1], bins[1:]):
        if hi >= 360.0:
            mask = (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = (angle_deg >= lo) & (angle_deg < hi)
        if not np.any(mask):
            continue
        stage6j_metrics = stage6d.metrics(stage6j_diff[mask])
        stage6f_metrics = stage6d.metrics(stage6f_diff[mask])
        rows.append(
            {
                "scan_bin_deg": f"{int(lo):03d}-{int(hi):03d}",
                "point_count": int(np.count_nonzero(mask)),
                "stage6f_vector_rmse_m": stage6f_metrics["vector_rmse_m"],
                "stage6j_vector_rmse_m": stage6j_metrics["vector_rmse_m"],
                "stage6f_horizontal_rmse_m": stage6f_metrics["horizontal_rmse_m"],
                "stage6j_horizontal_rmse_m": stage6j_metrics["horizontal_rmse_m"],
                "stage6f_down_rmse_m": stage6f_metrics["down_rmse_m"],
                "stage6j_down_rmse_m": stage6j_metrics["down_rmse_m"],
                "stage6j_north_median_m": stage6j_metrics["north_median_m"],
                "stage6j_east_median_m": stage6j_metrics["east_median_m"],
                "stage6j_down_median_m": stage6j_metrics["down_median_m"],
            }
        )
    return rows


def gate_conclusion(metrics: dict[str, float], current6f: dict[str, float]) -> tuple[str, str, bool, dict[str, float]]:
    vector_improvement = (
        100.0 * (current6f["vector_rmse_m"] - metrics["vector_rmse_m"]) / current6f["vector_rmse_m"]
        if current6f["vector_rmse_m"] > 0
        else 0.0
    )
    horizontal_improvement = (
        100.0 * (current6f["horizontal_rmse_m"] - metrics["horizontal_rmse_m"]) / current6f["horizontal_rmse_m"]
        if current6f["horizontal_rmse_m"] > 0
        else 0.0
    )
    stats = {
        "vector_improvement_vs_stage6f_pct": float(vector_improvement),
        "horizontal_improvement_vs_stage6f_pct": float(horizontal_improvement),
    }
    if metrics["vector_rmse_m"] <= 0.35 and metrics["horizontal_rmse_m"] <= 0.20:
        return (
            "合理",
            "Stage 6J diagnostic export reproduces Stage 6I accuracy and is suitable for CloudCompare inspection.",
            True,
            stats,
        )
    return (
        "基本合理但有风险",
        "Stage 6J exported points do not fully meet the diagnostic threshold; inspect before any production replacement.",
        False,
        stats,
    )


def write_report(payload: dict[str, Any]) -> None:
    metrics = payload["stage6j_metrics"]
    current = payload["current_stage6f_metrics"]
    gate = payload["gate"]
    candidate = payload["stage6i_best_candidate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6J CH1 LADM-II Diagnostic Export

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- CloudCompare inspection ready: {gate['cloudcompare_ready']}

## Metrics

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| current Stage 6F | {current['vector_rmse_m']:.6f} | {current['horizontal_rmse_m']:.6f} | {current['down_rmse_m']:.6f} | {current['north_median_m']:.6f}, {current['east_median_m']:.6f}, {current['down_median_m']:.6f} |
| Stage 6J LADM-II | {metrics['vector_rmse_m']:.6f} | {metrics['horizontal_rmse_m']:.6f} | {metrics['down_rmse_m']:.6f} | {metrics['north_median_m']:.6f}, {metrics['east_median_m']:.6f}, {metrics['down_median_m']:.6f} |

- vector_improvement_vs_stage6f_pct: {gate['vector_improvement_vs_stage6f_pct']:.3f}%
- horizontal_improvement_vs_stage6f_pct: {gate['horizontal_improvement_vs_stage6f_pct']:.3f}%

## Applied Stage 6I Candidate

- angle_direction: `{candidate['angle_direction']}`
- angle_offset_deg: {candidate['angle_offset_deg']}
- mirror_tilt_deg: {candidate['mirror_tilt_deg']}
- frame_rotation_deg: {candidate['frame_rotation_deg']}
- axis_mapping: `{candidate['axis_mapping']}`
- boresight roll/pitch/yaw deg: {candidate['boresight_roll_deg']}, {candidate['boresight_pitch_deg']}, {candidate['boresight_yaw_deg']}
- lever x/y/z m: {candidate['lever_x_m']:.6f}, {candidate['lever_y_m']:.6f}, {candidate['lever_z_m']:.6f}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Diagnostic H5: `{payload['outputs']['diagnostic_h5']}`
- Prediction TXT: `{payload['outputs'].get('prediction_txt', 'not written')}`
- Reference TXT: `{payload['outputs'].get('reference_txt', 'not written')}`
- Merged TXT: `{payload['outputs'].get('merged_txt', 'not written')}`
- Scan-bin CSV: `{payload['outputs']['scan_bins_csv']}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只导出 00111 exact-time 诊断点，不覆盖旧 H5/LAZ，不执行连续段。
- 生产替换前还需要人工看 CloudCompare，并单独做 Stage 6K/6L 连续段验证。
"""
    path = REPORT_DIR / "stage6j_ch1_ladm2_diagnostic_export_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading Stage 6I best candidate and exact-time matched 00111 data...", flush=True)
    candidate = load_json(STAGE6I_BEST)
    data = diag.load_matched_data(args.max_matched_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")

    if args.progress:
        print("Applying LADM-II diagnostic transform...", flush=True)
    prediction = build_ladm2_prediction(data, calibration, candidate)
    metrics = stage6d.metrics(prediction["diff_ned"])
    current6f = current_stage6f_metrics(data, calibration)

    current_geom = stage6f.build_base_geometry(data, calibration)
    current_rotation_cols = stage6f.rotation_columns(current_geom)
    current6f_diff = stage6f.diff_for_candidate(current_geom, current_rotation_cols, load_json(STAGE6F_BEST))
    scan_rows = scan_bin_rows(prediction["angle_deg"], prediction["diff_ned"], current6f_diff)
    scan_bins_csv = OUT_DIR / "scan_angle_bin_residuals.csv"
    write_csv(scan_bins_csv, scan_rows, list(scan_rows[0].keys()) if scan_rows else ["scan_bin_deg"])

    points = build_diagnostic_points(data, prediction)
    diagnostic_h5 = OUT_DIR / "stage6j_00111_ladm2_exact_time_diagnostic.h5"
    write_diagnostic_h5(diagnostic_h5, points, candidate, metrics, current6f)

    outputs: dict[str, Any] = {
        "diagnostic_h5": str(diagnostic_h5),
        "scan_bins_csv": str(scan_bins_csv),
        "report_json": str(REPORT_DIR / "stage6j_ch1_ladm2_diagnostic_export_report.json"),
        "report_md": str(REPORT_DIR / "stage6j_ch1_ladm2_diagnostic_export_report.md"),
    }
    written_counts: dict[str, int] = {}
    if args.write_cloudcompare_txt:
        if args.progress:
            print("Writing CloudCompare TXT files...", flush=True)
        diff = prediction["diff_ned"]
        vector = np.sqrt(np.sum(diff * diff, axis=1))
        horizontal = np.sqrt(diff[:, 0] ** 2 + diff[:, 1] ** 2)
        prediction_txt = OUT_DIR / "stage6j_00111_ladm2_prediction_cloudcompare.txt"
        reference_txt = OUT_DIR / "stage6j_00111_reference_l3_cloudcompare.txt"
        merged_txt = OUT_DIR / "stage6j_00111_prediction_reference_merged_cloudcompare.txt"
        written_counts["prediction_txt_points"] = write_cloudcompare_txt(
            prediction_txt,
            prediction["pred_easting"],
            prediction["pred_northing"],
            prediction["pred_height"],
            data["matched_time"],
            prediction["angle_deg"],
            prediction["range_m"],
            vector,
            horizontal,
            diff[:, 2],
            1,
            args.txt_max_points,
        )
        written_counts["reference_txt_points"] = write_cloudcompare_txt(
            reference_txt,
            prediction["ref_easting"],
            prediction["ref_northing"],
            prediction["ref_height"],
            data["matched_time"],
            prediction["angle_deg"],
            prediction["range_m"],
            vector,
            horizontal,
            diff[:, 2],
            2,
            args.txt_max_points,
        )
        written_counts["merged_txt_points"] = write_merged_cloudcompare_txt(
            merged_txt,
            data,
            prediction,
            args.txt_max_points,
        )
        outputs.update(
            {
                "prediction_txt": str(prediction_txt),
                "reference_txt": str(reference_txt),
                "merged_txt": str(merged_txt),
            }
        )

    conclusion, reason, ready, improvement = gate_conclusion(metrics, current6f)
    payload = {
        "stage_name": "stage6j_ch1_ladm2_diagnostic_export",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "reference_l3": str(diag.REFERENCE_L3),
            "l1_sample": str(diag.L1_SAMPLE),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
            "stage6i_best_candidate": str(STAGE6I_BEST),
            "stage6f_best_candidate": str(STAGE6F_BEST),
        },
        "fixed_parameters": {
            "zero_offset_m": ZERO_OFFSET_M,
            "roll_sign": stage6e.ROLL_SIGN,
            "pitch_sign": stage6e.PITCH_SIGN,
            "heading_sign": stage6e.HEADING_SIGN,
            "heading_convention": stage6e.HEADING_CONVENTION,
            "rotation_order": ROTATION_ORDER,
            "rotation_transpose": ROTATION_TRANSPOSE,
        },
        "stage6i_best_candidate": candidate,
        "current_stage6f_metrics": current6f,
        "stage6j_metrics": metrics,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "cloudcompare_ready": ready,
            **improvement,
            "criteria": {
                "max_vector_rmse_m": 0.35,
                "max_horizontal_rmse_m": 0.20,
            },
        },
        "written_counts": written_counts,
        "outputs": outputs,
    }
    write_json(Path(outputs["report_json"]), payload)
    write_report(payload)

    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "current_stage6f_metrics": current6f,
                    "stage6j_metrics": metrics,
                    "written_counts": written_counts,
                    "outputs": outputs,
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6J CH1 LADM-II diagnostic CloudCompare/H5 export.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--write-cloudcompare-txt", action="store_true")
    parser.add_argument("--txt-max-points", type=int, default=0, help="0 writes all loaded matched points.")
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
