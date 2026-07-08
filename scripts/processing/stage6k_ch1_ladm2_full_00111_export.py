import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import Transformer

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag
import stage6d_ch1_rotation_zero_diagnostic as stage6d
import stage6e_ch1_bias_validation as stage6e
import stage6j_ch1_ladm2_diagnostic_export as stage6j


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6k_ladm2_full_00111_export"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
STAGE6I_BEST = ROOT / "outputs" / "qc" / "stage6i_ladm2_scan_geometry_diagnostic" / "best_candidate.json"
L1_SAMPLE = ROOT / pipe.DEFAULT_SAMPLE_L1

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0
ZERO_OFFSET_M = stage6e.ZERO_OFFSET_M
ROTATION_ORDER = stage6e.ROTATION_ORDER
ROTATION_TRANSPOSE = stage6e.ROTATION_TRANSPOSE
CRS = "EPSG:32651"

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
        "method_name": "Stage 6K LADM-II full 00111 diagnostic export",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Stage 6I best candidate applied to all CH1 L1 points in 00111",
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8-sig"))


def finite_stats(values: np.ndarray) -> dict[str, float | int]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {"count": int(values.size), "finite_count": 0, "min": np.nan, "max": np.nan, "median": np.nan}
    return {
        "count": int(values.size),
        "finite_count": int(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "median": float(np.median(finite)),
    }


def full_dtype() -> np.dtype:
    return np.dtype(
        [
            ("point_index", "u4"),
            ("source_seq", "u2"),
            ("channel", "u1"),
            ("gnss_sec_raw", "f8"),
            ("gps_time", "f8"),
            ("easting_m", "f8"),
            ("northing_m", "f8"),
            ("height_m", "f8"),
            ("lon", "f8"),
            ("lat", "f8"),
            ("range_before_m", "f4"),
            ("range_m", "f4"),
            ("coder", "f8"),
            ("scan_angle_deg", "f4"),
            ("frd_x_m", "f4"),
            ("frd_y_m", "f4"),
            ("frd_z_m", "f4"),
            ("north_offset_m", "f4"),
            ("east_offset_m", "f4"),
            ("down_offset_m", "f4"),
            ("pulse_index", "u4"),
            ("pulse_circle", "u4"),
            ("photon_start_count", "f8"),
            ("pos_quality_flag", "u2"),
        ]
    )


def load_l1_full(path: Path) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as h5:
        return {
            "gnss": h5["GNSS_SEC_CH1"][:].astype(np.float64),
            "raw_dist": h5["Photon_CH1_DIST"][:].astype(np.uint32),
            "coder": h5["Photon_CH1_CODER"][:].astype(np.float64),
            "pulse_index": h5["PULSE_INDEX_CH1"][:].astype(np.uint32),
            "pulse_circle": h5["PULSE_CIRCLE_CH1"][:].astype(np.uint32),
            "photon_start_count": h5["Photon_Start_Count_CH1"][:].astype(np.float64),
        }


def pos_quality_flags(lidar_time: np.ndarray, pos_time: np.ndarray, low_conf_sec: float) -> tuple[np.ndarray, np.ndarray]:
    no_pos = (lidar_time < pos_time[0]) | (lidar_time > pos_time[-1])
    clipped = np.clip(lidar_time, pos_time[0], pos_time[-1])
    nearest_dt = pipe.nearest_time_delta_abs(pos_time, clipped)
    low_conf = nearest_dt > low_conf_sec
    flags = np.zeros(lidar_time.size, dtype=np.uint16)
    flags[no_pos] |= 1
    flags[low_conf] |= 2
    return flags, nearest_dt


def build_full_points(
    l1: dict[str, np.ndarray],
    calibration: dict[str, float],
    candidate: dict[str, Any],
    txt_range_min_m: float,
    low_conf_sec: float,
    progress: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    raw_dist = l1["raw_dist"]
    range_before = raw_dist.astype(np.float64) * DIST_FACTOR
    range_m = (range_before - ZERO_OFFSET_M - calibration["intercept"]) / calibration["slope"]
    lidar_time = l1["gnss"] + pipe.DEFAULT_TIME_OFFSET_SEC
    angle = stage6d.scan_angle(l1["coder"], candidate["angle_direction"], float(candidate["angle_offset_deg"]))

    boresight = (
        float(candidate["boresight_roll_deg"]),
        float(candidate["boresight_pitch_deg"]),
        float(candidate["boresight_yaw_deg"]),
    )
    if progress:
        print("Computing LADM-II FRD coordinates for all points...", flush=True)
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

    pos_time, pos, pos_corrections = stage5.load_pos()
    pos_flags, nearest_dt = pos_quality_flags(lidar_time, pos_time, low_conf_sec)
    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    pos_easting = np.interp(interp_time, pos_time, pos["EASTING"])
    pos_northing = np.interp(interp_time, pos_time, pos["NORTHING"])
    pos_height = np.interp(interp_time, pos_time, pos["HEIGHT"])
    data_for_angles = {
        "roll_deg": np.interp(interp_time, pos_time, pos["ROLL"]),
        "pitch_deg": np.interp(interp_time, pos_time, pos["PITCH"]),
        "heading_deg": pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time),
    }
    roll, pitch, heading = stage6d.prepare_angles(
        data_for_angles,
        stage6e.ROLL_SIGN,
        stage6e.PITCH_SIGN,
        stage6e.HEADING_SIGN,
        stage6e.HEADING_CONVENTION,
    )
    if progress:
        print("Rotating full-point FRD coordinates to NED...", flush=True)
    pred_no_lever = diag.rotate_frd_to_ned(frd, roll, pitch, heading, ROTATION_ORDER, ROTATION_TRANSPOSE)
    lever = np.array([candidate["lever_x_m"], candidate["lever_y_m"], candidate["lever_z_m"]], dtype=np.float64)
    lever_ned = diag.rotate_frd_to_ned(
        np.broadcast_to(lever, (range_m.size, 3)),
        roll,
        pitch,
        heading,
        ROTATION_ORDER,
        ROTATION_TRANSPOSE,
    )
    pred_ned = pred_no_lever + lever_ned
    easting = pos_easting + pred_ned[:, 1]
    northing = pos_northing + pred_ned[:, 0]
    height = pos_height - pred_ned[:, 2]
    transformer = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(easting, northing)

    if progress:
        print("Packing full diagnostic H5 point array...", flush=True)
    points = np.empty(range_m.size, dtype=full_dtype())
    points["point_index"] = np.arange(points.size, dtype=np.uint32)
    points["source_seq"] = 111
    points["channel"] = 1
    points["gnss_sec_raw"] = l1["gnss"]
    points["gps_time"] = lidar_time
    points["easting_m"] = easting
    points["northing_m"] = northing
    points["height_m"] = height
    points["lon"] = lon
    points["lat"] = lat
    points["range_before_m"] = range_before.astype(np.float32)
    points["range_m"] = range_m.astype(np.float32)
    points["coder"] = l1["coder"]
    points["scan_angle_deg"] = angle.astype(np.float32)
    points["frd_x_m"] = bx.astype(np.float32)
    points["frd_y_m"] = by.astype(np.float32)
    points["frd_z_m"] = bz.astype(np.float32)
    points["north_offset_m"] = pred_ned[:, 0].astype(np.float32)
    points["east_offset_m"] = pred_ned[:, 1].astype(np.float32)
    points["down_offset_m"] = pred_ned[:, 2].astype(np.float32)
    points["pulse_index"] = l1["pulse_index"]
    points["pulse_circle"] = l1["pulse_circle"]
    points["photon_start_count"] = l1["photon_start_count"]
    points["pos_quality_flag"] = pos_flags

    stats = {
        "point_count_l1": int(range_m.size),
        "point_count_h5": int(points.size),
        "range_before_gt_zero_count": int(np.count_nonzero(range_before > 0)),
        "range_m_gt_30_count": int(np.count_nonzero(range_m > txt_range_min_m)),
        "pos_no_pos_count": int(np.count_nonzero(pos_flags & 1)),
        "pos_low_confidence_count": int(np.count_nonzero(pos_flags & 2)),
        "pos_success_rate": float(1.0 - np.count_nonzero(pos_flags & 1) / max(pos_flags.size, 1)),
        "pos_time_corrections": int(pos_corrections),
        "nearest_pos_dt_abs_sec": finite_stats(nearest_dt),
        "gps_time_sec": finite_stats(lidar_time),
        "range_before_m": finite_stats(range_before),
        "range_m": finite_stats(range_m),
        "easting_m": finite_stats(easting),
        "northing_m": finite_stats(northing),
        "height_m": finite_stats(height),
    }
    return points, stats


def write_full_h5(path: Path, points: np.ndarray, candidate: dict[str, Any], stats: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        grp = h5.create_group("STAGE6K")
        ch1 = grp.create_group("CH1")
        ch1.create_dataset("full_points", data=points, compression="gzip", compression_opts=4, chunks=True)
        meta = h5.create_group("metadata")
        proc = meta.create_group("processing")
        pipe.write_str_attr(proc, "stage", "stage6k_ch1_ladm2_full_00111_export")
        pipe.write_str_attr(proc, "source_l1", str(L1_SAMPLE))
        pipe.write_str_attr(proc, "schema", "diagnostic_full_00111_ladm2_points")
        pipe.write_str_attr(proc, "crs", CRS)
        pipe.write_str_attr(proc, "production_status", "diagnostic_only_not_final_l3")
        proc.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        proc.attrs["zero_offset_m"] = ZERO_OFFSET_M
        proc.attrs["point_count_h5"] = stats["point_count_h5"]
        proc.attrs["range_m_gt_30_count"] = stats["range_m_gt_30_count"]
        proc.attrs["pos_success_rate"] = stats["pos_success_rate"]
        cand_grp = meta.create_group("stage6i_best_candidate")
        for key, value in candidate.items():
            if isinstance(value, str):
                pipe.write_str_attr(cand_grp, key, value)
            elif isinstance(value, (int, float, np.integer, np.floating, np.bool_)):
                cand_grp.attrs[key] = value
            elif isinstance(value, list):
                cand_grp.create_dataset(key, data=np.asarray(value))


def write_cloudcompare_txt(path: Path, points: np.ndarray, max_points: int, min_range_m: float | None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if min_range_m is None:
        valid_idx = np.arange(points.size, dtype=np.int64)
    else:
        valid_idx = np.flatnonzero(points["range_m"] > min_range_m).astype(np.int64)
    if max_points > 0 and valid_idx.size > max_points:
        idx = valid_idx[np.linspace(0, valid_idx.size - 1, max_points, dtype=np.int64)]
    else:
        idx = valid_idx
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("X Y Z height_m gps_time range_m scan_angle_deg point_index pos_quality_flag\n")
        for i in idx:
            p = points[i]
            f.write(
                f"{p['easting_m']:.9f} {p['northing_m']:.9f} {p['height_m']:.9f} "
                f"{p['height_m']:.9f} {p['gps_time']:.9f} {float(p['range_m']):.9f} "
                f"{float(p['scan_angle_deg']):.9f} {int(p['point_index'])} {int(p['pos_quality_flag'])}\n"
            )
    return int(idx.size)


def exact_time_qc(candidate: dict[str, Any], max_points: int) -> dict[str, Any]:
    data = diag.load_matched_data(max_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    prediction = stage6j.build_ladm2_prediction(data, calibration, candidate)
    metrics = stage6d.metrics(prediction["diff_ned"])
    current6f = stage6j.current_stage6f_metrics(data, calibration)
    return {
        "matched_points": int(data["matched_time"].size),
        "stage6k_ladm2_exact_time_metrics": metrics,
        "current_stage6f_exact_time_metrics": current6f,
        "vector_improvement_vs_stage6f_pct": float(
            100.0 * (current6f["vector_rmse_m"] - metrics["vector_rmse_m"]) / current6f["vector_rmse_m"]
        ),
        "horizontal_improvement_vs_stage6f_pct": float(
            100.0 * (current6f["horizontal_rmse_m"] - metrics["horizontal_rmse_m"]) / current6f["horizontal_rmse_m"]
        ),
    }


def gate_conclusion(stats: dict[str, Any], qc: dict[str, Any]) -> tuple[str, str, bool]:
    metrics = qc["stage6k_ladm2_exact_time_metrics"]
    if (
        stats["point_count_h5"] == stats["point_count_l1"]
        and stats["pos_success_rate"] >= 0.99
        and metrics["vector_rmse_m"] <= 0.35
        and metrics["horizontal_rmse_m"] <= 0.20
    ):
        return (
            "合理",
            "00111 full-point LADM-II diagnostic export completed and exact-time QC still matches Stage 6J accuracy.",
            True,
        )
    return (
        "基本合理但有风险",
        "Full-point export completed, but count/POS/exact-time QC did not fully meet the 6K gate.",
        False,
    )


def write_report(payload: dict[str, Any]) -> None:
    stats = payload["full_point_stats"]
    qc_metrics = payload["exact_time_qc"]["stage6k_ladm2_exact_time_metrics"]
    current = payload["exact_time_qc"]["current_stage6f_exact_time_metrics"]
    gate = payload["gate"]
    candidate = payload["stage6i_best_candidate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6K CH1 LADM-II Full 00111 Export

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Full-point H5 ready: {gate['full_point_h5_ready']}

## Full-Point Output

- L1 CH1 point count: {stats['point_count_l1']:,}
- H5 point count: {stats['point_count_h5']:,}
- `range_m > 30 m` count: {stats['range_m_gt_30_count']:,}
- POS success rate: {stats['pos_success_rate']:.6%}
- Height median/min/max m: {stats['height_m']['median']:.6f}, {stats['height_m']['min']:.6f}, {stats['height_m']['max']:.6f}

## Exact-Time QC

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| current Stage 6F | {current['vector_rmse_m']:.6f} | {current['horizontal_rmse_m']:.6f} | {current['down_rmse_m']:.6f} | {current['north_median_m']:.6f}, {current['east_median_m']:.6f}, {current['down_median_m']:.6f} |
| Stage 6K LADM-II | {qc_metrics['vector_rmse_m']:.6f} | {qc_metrics['horizontal_rmse_m']:.6f} | {qc_metrics['down_rmse_m']:.6f} | {qc_metrics['north_median_m']:.6f}, {qc_metrics['east_median_m']:.6f}, {qc_metrics['down_median_m']:.6f} |

- vector_improvement_vs_stage6f_pct: {payload['exact_time_qc']['vector_improvement_vs_stage6f_pct']:.3f}%
- horizontal_improvement_vs_stage6f_pct: {payload['exact_time_qc']['horizontal_improvement_vs_stage6f_pct']:.3f}%

## Applied LADM-II Candidate

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

- Full diagnostic H5: `{payload['outputs']['full_h5']}`
- CloudCompare TXT: `{payload['outputs'].get('cloudcompare_txt', 'not written')}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只导出 `00111` 全点诊断 H5/TXT，不覆盖旧 H5/LAZ，不跑连续段。
- 下一步建议先检查 CloudCompare，再做连续小段 Stage 6L。
"""
    path = REPORT_DIR / "stage6k_ch1_ladm2_full_00111_export_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading Stage 6I best candidate and full 00111 L1 data...", flush=True)
    candidate = load_json(STAGE6I_BEST)
    l1 = load_l1_full(L1_SAMPLE)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    points, stats = build_full_points(
        l1,
        calibration,
        candidate,
        args.txt_min_range_m,
        args.low_confidence_sec,
        args.progress,
    )
    full_h5 = OUT_DIR / "stage6k_00111_ladm2_full_points.h5"
    if args.progress:
        print(f"Writing full-point diagnostic H5: {full_h5}", flush=True)
    write_full_h5(full_h5, points, candidate, stats)

    outputs: dict[str, Any] = {
        "full_h5": str(full_h5),
        "report_json": str(REPORT_DIR / "stage6k_ch1_ladm2_full_00111_export_report.json"),
        "report_md": str(REPORT_DIR / "stage6k_ch1_ladm2_full_00111_export_report.md"),
    }
    written_counts: dict[str, int] = {}
    if args.write_cloudcompare_txt:
        txt = OUT_DIR / "stage6k_00111_ladm2_full_points_cloudcompare.txt"
        min_range = None if args.txt_include_all_ranges else args.txt_min_range_m
        if args.progress:
            scope = "all ranges" if min_range is None else f"range_m > {min_range:g} m"
            print(f"Writing CloudCompare TXT sample ({scope}): {txt}", flush=True)
        written_counts["cloudcompare_txt_points"] = write_cloudcompare_txt(
            txt,
            points,
            args.txt_max_points,
            min_range,
        )
        outputs["cloudcompare_txt"] = str(txt)

    if args.progress:
        print("Running exact-time QC consistency check...", flush=True)
    qc = exact_time_qc(candidate, args.max_exact_matched_points)
    conclusion, reason, ready = gate_conclusion(stats, qc)
    payload = {
        "stage_name": "stage6k_ch1_ladm2_full_00111_export",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "l1_sample": str(L1_SAMPLE),
            "reference_l3": str(diag.REFERENCE_L3),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
            "stage6i_best_candidate": str(STAGE6I_BEST),
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
        "full_point_stats": stats,
        "exact_time_qc": qc,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "full_point_h5_ready": ready,
            "criteria": {
                "point_count_h5_equals_l1": True,
                "min_pos_success_rate": 0.99,
                "max_exact_time_vector_rmse_m": 0.35,
                "max_exact_time_horizontal_rmse_m": 0.20,
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
                    "full_point_stats": {
                        "point_count_l1": stats["point_count_l1"],
                        "point_count_h5": stats["point_count_h5"],
                        "range_m_gt_30_count": stats["range_m_gt_30_count"],
                        "pos_success_rate": stats["pos_success_rate"],
                        "height_m": stats["height_m"],
                    },
                    "exact_time_qc": qc,
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
    parser = argparse.ArgumentParser(description="Stage 6K CH1 LADM-II full 00111 diagnostic export.")
    parser.add_argument("--write-cloudcompare-txt", action="store_true")
    parser.add_argument("--txt-max-points", type=int, default=300_000, help="0 writes all selected points.")
    parser.add_argument("--txt-min-range-m", type=float, default=30.0)
    parser.add_argument("--txt-include-all-ranges", action="store_true")
    parser.add_argument("--low-confidence-sec", type=float, default=0.2)
    parser.add_argument("--max-exact-matched-points", type=int, default=100_000)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
