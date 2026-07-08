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
import stage6d_ch1_rotation_zero_diagnostic as stage6d
import stage6e_ch1_bias_validation as stage6e


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6f_boresight_lever_diagnostic"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

ZERO_OFFSET_M = stage6e.ZERO_OFFSET_M
ANGLE_DIRECTION = stage6e.ANGLE_DIRECTION
ANGLE_OFFSET_DEG = stage6e.ANGLE_OFFSET_DEG
ROLL_SIGN = stage6e.ROLL_SIGN
PITCH_SIGN = stage6e.PITCH_SIGN
HEADING_SIGN = stage6e.HEADING_SIGN
HEADING_CONVENTION = stage6e.HEADING_CONVENTION
ROTATION_ORDER = stage6e.ROTATION_ORDER
ROTATION_TRANSPOSE = stage6e.ROTATION_TRANSPOSE

COARSE_BORESIGHT_GRID_DEG = [-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0]
LOCAL_BORESIGHT_DELTA_DEG = [-0.5, -0.25, 0.0, 0.25, 0.5]

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
        "method_name": "Stage 6F body/FRD boresight and lever-arm diagnostic search",
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


def stratified_indices(size: int, count: int) -> np.ndarray:
    if count <= 0 or count >= size:
        return np.arange(size, dtype=np.int64)
    return np.linspace(0, size - 1, count, dtype=np.int64)


def sample_data(data: dict[str, np.ndarray], indices: np.ndarray) -> dict[str, np.ndarray]:
    full_size = data["matched_time"].size
    sampled: dict[str, np.ndarray] = {}
    for key, value in data.items():
        if isinstance(value, np.ndarray) and value.shape[:1] == (full_size,):
            sampled[key] = value[indices]
        else:
            sampled[key] = value
    return sampled


def build_base_geometry(
    data: dict[str, np.ndarray],
    calibration: dict[str, float],
) -> dict[str, np.ndarray]:
    angle = stage6d.scan_angle(data["coder"], ANGLE_DIRECTION, ANGLE_OFFSET_DEG)
    range_m = (data["range_before"] - ZERO_OFFSET_M - calibration["intercept"]) / calibration["slope"]
    bx, by, bz = pipe.f_body_frame_xyz(range_m, angle)
    frd = np.column_stack([bx, by, bz])
    truth = np.column_stack([data["ref_north_offset"], data["ref_east_offset"], data["ref_down_offset"]])
    roll, pitch, heading = stage6d.prepare_angles(
        data,
        ROLL_SIGN,
        PITCH_SIGN,
        HEADING_SIGN,
        HEADING_CONVENTION,
    )
    return {
        "angle_deg": angle,
        "range_m": range_m,
        "base_frd": frd,
        "truth_ned": truth,
        "roll": roll,
        "pitch": pitch,
        "heading": heading,
    }


def rotation_columns(geom: dict[str, np.ndarray]) -> np.ndarray:
    n = geom["base_frd"].shape[0]
    basis = []
    for axis_idx in range(3):
        frd = np.zeros((n, 3), dtype=np.float64)
        frd[:, axis_idx] = 1.0
        basis.append(
            diag.rotate_frd_to_ned(
                frd,
                geom["roll"],
                geom["pitch"],
                geom["heading"],
                ROTATION_ORDER,
                ROTATION_TRANSPOSE,
            )
        )
    return np.stack(basis, axis=2)


def predict_without_lever(
    geom: dict[str, np.ndarray],
    boresight_deg: tuple[float, float, float],
) -> np.ndarray:
    frd = geom["base_frd"]
    if boresight_deg != (0.0, 0.0, 0.0):
        frd = diag.apply_boresight(frd, *boresight_deg)
    return diag.rotate_frd_to_ned(
        frd,
        geom["roll"],
        geom["pitch"],
        geom["heading"],
        ROTATION_ORDER,
        ROTATION_TRANSPOSE,
    )


def solve_lever_ls(rotation_cols: np.ndarray, residual_no_lever: np.ndarray, lever_limit_m: float) -> np.ndarray:
    normal = np.einsum("nij,nik->jk", rotation_cols, rotation_cols)
    rhs = -np.einsum("nij,ni->j", rotation_cols, residual_no_lever)
    try:
        lever = np.linalg.solve(normal, rhs)
    except np.linalg.LinAlgError:
        lever = np.linalg.lstsq(normal, rhs, rcond=None)[0]
    return np.clip(lever, -lever_limit_m, lever_limit_m).astype(np.float64)


def snap_values(values: np.ndarray, step: float, limit: float) -> np.ndarray:
    snapped = np.round(values / step) * step
    return np.clip(snapped, -limit, limit).astype(np.float64)


def candidate_key(row: dict[str, Any]) -> tuple[float, ...]:
    return (
        round(float(row["boresight_roll_deg"]), 6),
        round(float(row["boresight_pitch_deg"]), 6),
        round(float(row["boresight_yaw_deg"]), 6),
        round(float(row["lever_x_m"]), 6),
        round(float(row["lever_y_m"]), 6),
        round(float(row["lever_z_m"]), 6),
    )


def evaluate_candidate(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    boresight_deg: tuple[float, float, float],
    lever_m: tuple[float, float, float],
    candidate_stage: str,
) -> dict[str, Any]:
    pred_no_lever = predict_without_lever(geom, boresight_deg)
    lever = np.asarray(lever_m, dtype=np.float64)
    pred = pred_no_lever + np.einsum("nij,j->ni", rotation_cols, lever)
    diff = pred - geom["truth_ned"]
    metrics = stage6d.metrics(diff)
    return {
        "candidate_stage": candidate_stage,
        "boresight_roll_deg": float(boresight_deg[0]),
        "boresight_pitch_deg": float(boresight_deg[1]),
        "boresight_yaw_deg": float(boresight_deg[2]),
        "boresight_abs_max_deg": float(max(abs(v) for v in boresight_deg)),
        "lever_x_m": float(lever[0]),
        "lever_y_m": float(lever[1]),
        "lever_z_m": float(lever[2]),
        "lever_norm_m": float(np.linalg.norm(lever)),
        "sample_points_used": int(diff.shape[0]),
        **metrics,
    }


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda r: (r["vector_rmse_m"], r["horizontal_rmse_m"], r["down_rmse_m"]))
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx
    return rows


def candidate_fields() -> list[str]:
    return [
        "rank",
        "candidate_stage",
        "boresight_roll_deg",
        "boresight_pitch_deg",
        "boresight_yaw_deg",
        "boresight_abs_max_deg",
        "lever_x_m",
        "lever_y_m",
        "lever_z_m",
        "lever_norm_m",
        "sample_points_used",
        "vector_rmse_m",
        "horizontal_rmse_m",
        "down_rmse_m",
        "north_rmse_m",
        "east_rmse_m",
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


def coarse_search(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    lever_limit_m: float,
    progress: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    boresights = list(itertools.product(COARSE_BORESIGHT_GRID_DEG, repeat=3))
    total = len(boresights)
    for idx, boresight in enumerate(boresights, 1):
        boresight_tuple = tuple(float(v) for v in boresight)
        pred_no_lever = predict_without_lever(geom, boresight_tuple)
        residual_no_lever = pred_no_lever - geom["truth_ned"]
        lever_ls = solve_lever_ls(rotation_cols, residual_no_lever, lever_limit_m)
        lever_snap = snap_values(lever_ls, 0.5, lever_limit_m)
        rows.append(evaluate_candidate(geom, rotation_cols, boresight_tuple, tuple(lever_ls), "coarse_ls"))
        rows.append(evaluate_candidate(geom, rotation_cols, boresight_tuple, tuple(lever_snap), "coarse_snap_0p5"))
        if progress and (idx % 25 == 0 or idx == total):
            print(f"Coarse boresight/lever search: {idx}/{total}", flush=True)
    return sort_rows(rows)


def local_search(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    top_rows: list[dict[str, Any]],
    local_top_candidates: int,
    lever_limit_m: float,
    progress: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[float, ...]] = set()
    sources = top_rows[:local_top_candidates]
    total = len(sources) * (len(LOCAL_BORESIGHT_DELTA_DEG) ** 3)
    done = 0
    for source in sources:
        center = np.array(
            [
                source["boresight_roll_deg"],
                source["boresight_pitch_deg"],
                source["boresight_yaw_deg"],
            ],
            dtype=np.float64,
        )
        for delta in itertools.product(LOCAL_BORESIGHT_DELTA_DEG, repeat=3):
            boresight = np.clip(center + np.asarray(delta, dtype=np.float64), -2.5, 2.5)
            boresight_tuple = tuple(float(v) for v in boresight)
            pred_no_lever = predict_without_lever(geom, boresight_tuple)
            residual_no_lever = pred_no_lever - geom["truth_ned"]
            lever_ls = solve_lever_ls(rotation_cols, residual_no_lever, lever_limit_m)
            lever_snap = snap_values(lever_ls, 0.25, lever_limit_m)
            for lever, stage in [(lever_ls, "local_ls"), (lever_snap, "local_snap_0p25")]:
                temp = {
                    "boresight_roll_deg": boresight_tuple[0],
                    "boresight_pitch_deg": boresight_tuple[1],
                    "boresight_yaw_deg": boresight_tuple[2],
                    "lever_x_m": lever[0],
                    "lever_y_m": lever[1],
                    "lever_z_m": lever[2],
                }
                key = candidate_key(temp)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(evaluate_candidate(geom, rotation_cols, boresight_tuple, tuple(lever), stage))
            done += 1
            if progress and (done % 250 == 0 or done == total):
                print(f"Local boresight/lever search: {done}/{total}", flush=True)
    return sort_rows(rows)


def re_evaluate_rows(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    rows: list[dict[str, Any]],
    top_count: int,
    progress: bool,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[float, ...]] = set()
    selected: list[dict[str, Any]] = []
    for row in rows:
        key = candidate_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= top_count:
            break
    for idx, row in enumerate(selected, 1):
        out.append(
            evaluate_candidate(
                geom,
                rotation_cols,
                (
                    float(row["boresight_roll_deg"]),
                    float(row["boresight_pitch_deg"]),
                    float(row["boresight_yaw_deg"]),
                ),
                (float(row["lever_x_m"]), float(row["lever_y_m"]), float(row["lever_z_m"])),
                f"{row['candidate_stage']}_full_eval",
            )
        )
        if progress and (idx % 20 == 0 or idx == len(selected)):
            print(f"Full-sample candidate evaluation: {idx}/{len(selected)}", flush=True)
    return sort_rows(out)


def scan_bin_rows(
    angle_deg: np.ndarray,
    baseline_diff: np.ndarray,
    best_diff: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bins = np.arange(0.0, 361.0, 30.0)
    for lo, hi in zip(bins[:-1], bins[1:]):
        if hi >= 360.0:
            mask = (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = (angle_deg >= lo) & (angle_deg < hi)
        if not np.any(mask):
            continue
        baseline = stage6d.metrics(baseline_diff[mask])
        best = stage6d.metrics(best_diff[mask])
        rows.append(
            {
                "scan_bin_deg": f"{int(lo):03d}-{int(hi):03d}",
                "point_count": int(np.count_nonzero(mask)),
                "baseline_vector_rmse_m": baseline["vector_rmse_m"],
                "baseline_horizontal_rmse_m": baseline["horizontal_rmse_m"],
                "baseline_down_rmse_m": baseline["down_rmse_m"],
                "best_vector_rmse_m": best["vector_rmse_m"],
                "best_horizontal_rmse_m": best["horizontal_rmse_m"],
                "best_down_rmse_m": best["down_rmse_m"],
                "best_north_median_m": best["north_median_m"],
                "best_east_median_m": best["east_median_m"],
                "best_down_median_m": best["down_median_m"],
            }
        )
    return rows


def diff_for_candidate(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    row: dict[str, Any],
) -> np.ndarray:
    pred_no_lever = predict_without_lever(
        geom,
        (
            float(row["boresight_roll_deg"]),
            float(row["boresight_pitch_deg"]),
            float(row["boresight_yaw_deg"]),
        ),
    )
    lever = np.array([row["lever_x_m"], row["lever_y_m"], row["lever_z_m"]], dtype=np.float64)
    pred = pred_no_lever + np.einsum("nij,j->ni", rotation_cols, lever)
    return pred - geom["truth_ned"]


def load_stage6e_bias_rmse(default_value: float) -> float:
    report = REPORT_DIR / "stage6e_ch1_bias_validation_report.json"
    if not report.exists():
        return default_value
    try:
        payload = json.loads(report.read_text(encoding="utf-8-sig"))
        return float(payload["bias_corrected_metrics"]["vector_rmse_m"])
    except Exception:
        return default_value


def gate_conclusion(best: dict[str, Any], stage6e_vector_rmse: float) -> tuple[str, str, bool, float]:
    improvement = (stage6e_vector_rmse - best["vector_rmse_m"]) / stage6e_vector_rmse if stage6e_vector_rmse > 0 else 0.0
    physically_plausible = best["lever_norm_m"] <= 3.0 and best["boresight_abs_max_deg"] <= 2.0
    if improvement >= 0.10 and physically_plausible:
        return "合理", "Stage 6F 相对 Stage 6E 继续明显改善，且杆臂/安置角幅度在预设物理范围内。", True, improvement
    if physically_plausible:
        return "基本合理但有风险", "Stage 6F 参数幅度可接受，但相对 Stage 6E 改善不足 10%；是否进入 6G 需要人工判断。", False, improvement
    return "不合理", "Stage 6F 最优候选参数幅度过大或改善不足；不建议进入 6G，应回查扫描几何。", False, improvement


def write_report(payload: dict[str, Any]) -> None:
    best = payload["best_candidate"]
    baseline = payload["baseline_metrics"]
    gate = payload["gate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6F CH1 Boresight / Lever Diagnostic

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Recommend Stage 6G: {gate['recommend_stage6g']}

## Best Candidate

- boresight roll/pitch/yaw deg: {best['boresight_roll_deg']:.6f}, {best['boresight_pitch_deg']:.6f}, {best['boresight_yaw_deg']:.6f}
- lever x/y/z m: {best['lever_x_m']:.6f}, {best['lever_y_m']:.6f}, {best['lever_z_m']:.6f}
- lever_norm_m: {best['lever_norm_m']:.6f}
- boresight_abs_max_deg: {best['boresight_abs_max_deg']:.6f}

## Key Metrics

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| Stage 6D fixed no boresight/lever | {baseline['vector_rmse_m']:.6f} | {baseline['horizontal_rmse_m']:.6f} | {baseline['down_rmse_m']:.6f} | {baseline['north_median_m']:.6f}, {baseline['east_median_m']:.6f}, {baseline['down_median_m']:.6f} |
| Stage 6F best | {best['vector_rmse_m']:.6f} | {best['horizontal_rmse_m']:.6f} | {best['down_rmse_m']:.6f} | {best['north_median_m']:.6f}, {best['east_median_m']:.6f}, {best['down_median_m']:.6f} |

- stage6e_bias_vector_rmse_m: {payload['stage6e_bias_vector_rmse_m']:.6f}
- improvement_vs_stage6e_bias_pct: {gate['improvement_vs_stage6e_bias_pct']:.3f}%
- improvement_vs_stage6d_fixed_pct: {payload['improvement_vs_stage6d_fixed_pct']:.3f}%

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Coarse candidates: `{payload['outputs']['coarse_candidates_csv']}`
- Local candidates: `{payload['outputs']['local_candidates_csv']}`
- Top full-eval candidates: `{payload['outputs']['top_candidates_csv']}`
- Scan-bin residual CSV: `{payload['outputs']['scan_bins_csv']}`
- Best candidate JSON: `{payload['outputs']['best_candidate_json']}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只提交 6F 诊断结果，不执行 Stage 6G。
- 所有 boresight/lever 参数仍是 `PROJECT_DIAGNOSTIC_PARAMETER`，不能直接作为最终生产定标。
"""
    path = REPORT_DIR / "stage6f_ch1_boresight_lever_diagnostic_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading exact-time matched 00111 data...", flush=True)
    data = diag.load_matched_data(args.max_matched_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")

    search_idx = stratified_indices(data["matched_time"].size, args.search_points)
    search_data = sample_data(data, search_idx)
    if args.progress:
        print(f"Building search geometry on {search_data['matched_time'].size} points...", flush=True)
    search_geom = build_base_geometry(search_data, calibration)
    search_rotation_cols = rotation_columns(search_geom)
    coarse_rows = coarse_search(search_geom, search_rotation_cols, args.lever_limit_m, args.progress)
    local_rows = local_search(
        search_geom,
        search_rotation_cols,
        coarse_rows,
        args.local_top_candidates,
        args.lever_limit_m,
        args.progress,
    )
    search_combined = sort_rows(coarse_rows + local_rows)

    if args.progress:
        print(f"Building full geometry on {data['matched_time'].size} points...", flush=True)
    full_geom = build_base_geometry(data, calibration)
    full_rotation_cols = rotation_columns(full_geom)
    final_rows = re_evaluate_rows(
        full_geom,
        full_rotation_cols,
        search_combined,
        args.top_final_eval_count,
        args.progress,
    )
    best = final_rows[0]

    baseline_row = evaluate_candidate(full_geom, full_rotation_cols, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), "baseline")
    baseline_diff = diff_for_candidate(full_geom, full_rotation_cols, baseline_row)
    best_diff = diff_for_candidate(full_geom, full_rotation_cols, best)
    scan_rows = scan_bin_rows(full_geom["angle_deg"], baseline_diff, best_diff)

    stage6e_vector_rmse = load_stage6e_bias_rmse(stage6d.metrics(baseline_diff - stage6e.BIAS_CORRECTION_NED_M[None, :])["vector_rmse_m"])
    conclusion, reason, recommend_stage6g, improvement_vs_stage6e = gate_conclusion(best, stage6e_vector_rmse)
    improvement_vs_stage6d = (
        (baseline_row["vector_rmse_m"] - best["vector_rmse_m"]) / baseline_row["vector_rmse_m"]
        if baseline_row["vector_rmse_m"] > 0
        else 0.0
    )

    coarse_csv = OUT_DIR / "coarse_candidates.csv"
    local_csv = OUT_DIR / "local_candidates.csv"
    top_csv = OUT_DIR / "top_candidates_full_eval.csv"
    scan_csv = OUT_DIR / "scan_angle_bin_residuals.csv"
    best_json = OUT_DIR / "best_candidate.json"
    report_json = REPORT_DIR / "stage6f_ch1_boresight_lever_diagnostic_report.json"
    write_csv(coarse_csv, coarse_rows, candidate_fields())
    write_csv(local_csv, local_rows, candidate_fields())
    write_csv(top_csv, final_rows, candidate_fields())
    write_csv(scan_csv, scan_rows, list(scan_rows[0].keys()) if scan_rows else ["scan_bin_deg"])
    write_json(best_json, best)

    payload = {
        "stage_name": "stage6f_ch1_boresight_lever_diagnostic",
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
        },
        "search": {
            "max_matched_points": args.max_matched_points,
            "search_points": int(search_data["matched_time"].size),
            "full_eval_points": int(data["matched_time"].size),
            "top_final_eval_count": args.top_final_eval_count,
            "local_top_candidates": args.local_top_candidates,
            "lever_limit_m": args.lever_limit_m,
            "coarse_boresight_grid_deg": COARSE_BORESIGHT_GRID_DEG,
            "local_boresight_delta_deg": LOCAL_BORESIGHT_DELTA_DEG,
            "coarse_candidate_count": len(coarse_rows),
            "local_candidate_count": len(local_rows),
        },
        "baseline_metrics": baseline_row,
        "best_candidate": best,
        "stage6e_bias_vector_rmse_m": stage6e_vector_rmse,
        "improvement_vs_stage6d_fixed_pct": float(100.0 * improvement_vs_stage6d),
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "recommend_stage6g": recommend_stage6g,
            "improvement_vs_stage6e_bias_pct": float(100.0 * improvement_vs_stage6e),
            "criteria": {
                "min_improvement_vs_stage6e_bias_pct": 10.0,
                "max_lever_norm_m": 3.0,
                "max_boresight_abs_deg": 2.0,
            },
        },
        "outputs": {
            "coarse_candidates_csv": str(coarse_csv),
            "local_candidates_csv": str(local_csv),
            "top_candidates_csv": str(top_csv),
            "scan_bins_csv": str(scan_csv),
            "best_candidate_json": str(best_json),
            "report_json": str(report_json),
            "report_md": str(REPORT_DIR / "stage6f_ch1_boresight_lever_diagnostic_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)

    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "baseline_metrics": baseline_row,
                    "best_candidate": best,
                    "stage6e_bias_vector_rmse_m": stage6e_vector_rmse,
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6F CH1 boresight/lever-arm diagnostic against exact-time L3 00111.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--search-points", type=int, default=5_000)
    parser.add_argument("--top-final-eval-count", type=int, default=100)
    parser.add_argument("--local-top-candidates", type=int, default=20)
    parser.add_argument("--lever-limit-m", type=float, default=3.0)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
