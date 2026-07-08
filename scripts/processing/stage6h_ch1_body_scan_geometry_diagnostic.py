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
import stage6f_ch1_boresight_lever_diagnostic as stage6f
import stage6f2_ch1_scan_angle_residual_diagnostic as stage6f2


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6h_body_scan_geometry_diagnostic"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
STAGE6F_BEST = ROOT / "outputs" / "qc" / "stage6f_boresight_lever_diagnostic" / "best_candidate.json"

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
        "method_name": "Stage 6H body-frame scan-geometry residual diagnostic models",
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


def load_best_candidate(path: Path = STAGE6F_BEST) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Stage 6F best candidate not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def post_boresight_laser_frd(
    range_m: np.ndarray,
    angle_deg: np.ndarray,
    boresight: tuple[float, float, float],
) -> np.ndarray:
    bx, by, bz = pipe.f_body_frame_xyz(range_m, angle_deg)
    frd = np.column_stack([bx, by, bz])
    if boresight != (0.0, 0.0, 0.0):
        frd = diag.apply_boresight(frd, *boresight)
    return frd


def angle_derivative_frd(
    range_m: np.ndarray,
    angle_deg: np.ndarray,
    boresight: tuple[float, float, float],
    epsilon_deg: float,
) -> np.ndarray:
    plus = post_boresight_laser_frd(range_m, angle_deg + epsilon_deg, boresight)
    minus = post_boresight_laser_frd(range_m, angle_deg - epsilon_deg, boresight)
    epsilon_rad = np.deg2rad(epsilon_deg)
    return (plus - minus) / (2.0 * epsilon_rad)


def apply_candidate_prediction(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    candidate: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    diff = stage6f.diff_for_candidate(geom, rotation_cols, candidate)
    correction_needed_ned = -diff
    correction_needed_frd = np.einsum("nij,ni->nj", rotation_cols, correction_needed_ned)
    return diff, correction_needed_frd


def decompose_correction(
    geom: dict[str, np.ndarray],
    candidate: dict[str, Any],
    correction_frd: np.ndarray,
    angle_derivative: np.ndarray,
) -> dict[str, Any]:
    boresight = (
        float(candidate["boresight_roll_deg"]),
        float(candidate["boresight_pitch_deg"]),
        float(candidate["boresight_yaw_deg"]),
    )
    laser_frd = post_boresight_laser_frd(geom["range_m"], geom["angle_deg"], boresight)
    norms = np.linalg.norm(laser_frd, axis=1)
    unit = laser_frd / np.maximum(norms[:, None], 1e-12)
    radial_m = np.sum(correction_frd * unit, axis=1)
    radial_vec = radial_m[:, None] * unit
    transverse_vec = correction_frd - radial_vec
    deriv_norm_sq = np.sum(angle_derivative * angle_derivative, axis=1)
    delta_angle_rad = np.sum(correction_frd * angle_derivative, axis=1) / np.maximum(deriv_norm_sq, 1e-12)
    angle_vec = delta_angle_rad[:, None] * angle_derivative
    angle_residual = correction_frd - angle_vec
    total_rms = float(np.sqrt(np.mean(np.sum(correction_frd * correction_frd, axis=1))))
    radial_rms = float(np.sqrt(np.mean(radial_m * radial_m)))
    transverse_rms = float(np.sqrt(np.mean(np.sum(transverse_vec * transverse_vec, axis=1))))
    angle_vec_rms = float(np.sqrt(np.mean(np.sum(angle_vec * angle_vec, axis=1))))
    angle_residual_rms = float(np.sqrt(np.mean(np.sum(angle_residual * angle_residual, axis=1))))
    return {
        "laser_frd": laser_frd,
        "unit": unit,
        "radial_m": radial_m,
        "radial_vec": radial_vec,
        "transverse_vec": transverse_vec,
        "delta_angle_rad": delta_angle_rad,
        "delta_angle_deg": np.rad2deg(delta_angle_rad),
        "angle_vec": angle_vec,
        "angle_residual_vec": angle_residual,
        "summary": {
            "total_correction_rms_m": total_rms,
            "radial_rms_m": radial_rms,
            "transverse_rms_m": transverse_rms,
            "radial_energy_pct": float(100.0 * radial_rms**2 / total_rms**2) if total_rms > 0 else 0.0,
            "transverse_energy_pct": float(100.0 * transverse_rms**2 / total_rms**2) if total_rms > 0 else 0.0,
            "instant_angle_vector_rms_m": angle_vec_rms,
            "instant_angle_residual_rms_m": angle_residual_rms,
            "instant_angle_energy_explained_pct": (
                float(100.0 * (1.0 - angle_residual_rms**2 / total_rms**2)) if total_rms > 0 else 0.0
            ),
            "delta_angle_mean_deg": float(np.mean(np.rad2deg(delta_angle_rad))),
            "delta_angle_median_deg": float(np.median(np.rad2deg(delta_angle_rad))),
            "delta_angle_rmse_deg": float(np.sqrt(np.mean(np.rad2deg(delta_angle_rad) ** 2))),
            "delta_angle_p90_abs_deg": float(np.percentile(np.abs(np.rad2deg(delta_angle_rad)), 90)),
        },
    }


def fit_linear_fourier(angle_deg: np.ndarray, target: np.ndarray, train_mask: np.ndarray, order: int) -> np.ndarray:
    x_train = stage6f2.fourier_features(angle_deg[train_mask], order)
    coef, *_ = np.linalg.lstsq(x_train, target[train_mask], rcond=None)
    return coef


def build_model(
    model_type: str,
    order: int,
    coef: np.ndarray,
) -> dict[str, Any]:
    return {
        "model_name": f"{model_type}_fourier_order_{order}",
        "model_type": model_type,
        "order": int(order),
        "coefficients": coef,
    }


def apply_body_model(
    model: dict[str, Any],
    angle_deg: np.ndarray,
    range_m: np.ndarray,
    unit: np.ndarray,
    angle_derivative: np.ndarray,
) -> np.ndarray:
    x = stage6f2.fourier_features(angle_deg, int(model["order"]))
    pred = x @ np.asarray(model["coefficients"], dtype=np.float64)
    kind = model["model_type"]
    if kind == "radial_m":
        return pred.reshape(-1, 1) * unit
    if kind == "angle_delta_rad":
        return pred.reshape(-1, 1) * angle_derivative
    if kind == "transverse_unit":
        pred = pred - np.sum(pred * unit, axis=1)[:, None] * unit
        return range_m[:, None] * pred
    if kind == "full_unit":
        return range_m[:, None] * pred
    if kind == "full_m":
        return pred
    raise ValueError(kind)


def evaluate_model(
    model: dict[str, Any],
    angle_deg: np.ndarray,
    range_m: np.ndarray,
    unit: np.ndarray,
    angle_derivative: np.ndarray,
    rotation_cols: np.ndarray,
    before_diff_ned: np.ndarray,
    train_mask: np.ndarray,
    validation_mask: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray]:
    correction_frd = apply_body_model(model, angle_deg, range_m, unit, angle_derivative)
    correction_ned = np.einsum("nij,nj->ni", rotation_cols, correction_frd)
    after_diff = before_diff_ned + correction_ned
    subsets = {
        "train": train_mask,
        "validation": validation_mask,
        "full": np.ones(before_diff_ned.shape[0], dtype=bool),
    }
    row: dict[str, Any] = {
        "model_name": model["model_name"],
        "model_type": model["model_type"],
        "order": int(model["order"]),
    }
    for subset_name, mask in subsets.items():
        before = stage6d.metrics(before_diff_ned[mask])
        after = stage6d.metrics(after_diff[mask])
        row[f"{subset_name}_points"] = int(np.count_nonzero(mask))
        row[f"{subset_name}_before_vector_rmse_m"] = before["vector_rmse_m"]
        row[f"{subset_name}_after_vector_rmse_m"] = after["vector_rmse_m"]
        row[f"{subset_name}_before_horizontal_rmse_m"] = before["horizontal_rmse_m"]
        row[f"{subset_name}_after_horizontal_rmse_m"] = after["horizontal_rmse_m"]
        row[f"{subset_name}_before_down_rmse_m"] = before["down_rmse_m"]
        row[f"{subset_name}_after_down_rmse_m"] = after["down_rmse_m"]
        row[f"{subset_name}_vector_improvement_pct"] = (
            100.0 * (before["vector_rmse_m"] - after["vector_rmse_m"]) / before["vector_rmse_m"]
            if before["vector_rmse_m"] > 0
            else 0.0
        )
        row[f"{subset_name}_horizontal_improvement_pct"] = (
            100.0 * (before["horizontal_rmse_m"] - after["horizontal_rmse_m"]) / before["horizontal_rmse_m"]
            if before["horizontal_rmse_m"] > 0
            else 0.0
        )
    return row, after_diff


def model_fields() -> list[str]:
    fields = ["rank", "model_name", "model_type", "order"]
    for subset in ["train", "validation", "full"]:
        fields.extend(
            [
                f"{subset}_points",
                f"{subset}_before_vector_rmse_m",
                f"{subset}_after_vector_rmse_m",
                f"{subset}_vector_improvement_pct",
                f"{subset}_before_horizontal_rmse_m",
                f"{subset}_after_horizontal_rmse_m",
                f"{subset}_horizontal_improvement_pct",
                f"{subset}_before_down_rmse_m",
                f"{subset}_after_down_rmse_m",
            ]
        )
    return fields


def fit_models(
    angle_deg: np.ndarray,
    range_m: np.ndarray,
    correction_frd: np.ndarray,
    decomposition: dict[str, Any],
    train_mask: np.ndarray,
    max_order: int,
) -> list[dict[str, Any]]:
    unit = decomposition["unit"]
    models: list[dict[str, Any]] = []
    targets = {
        "radial_m": decomposition["radial_m"],
        "angle_delta_rad": decomposition["delta_angle_rad"],
        "transverse_unit": decomposition["transverse_vec"] / np.maximum(range_m[:, None], 1e-12),
        "full_unit": correction_frd / np.maximum(range_m[:, None], 1e-12),
        "full_m": correction_frd,
    }
    for order in range(1, max_order + 1):
        for model_type, target in targets.items():
            coef = fit_linear_fourier(angle_deg, target, train_mask, order)
            if model_type in {"transverse_unit", "full_unit"}:
                # Store the raw least-squares coefficient; transverse projection is enforced during application.
                _ = unit
            models.append(build_model(model_type, order, coef))
    return models


def scan_bin_rows(
    angle_deg: np.ndarray,
    correction_frd: np.ndarray,
    decomposition: dict[str, Any],
    before_diff: np.ndarray,
    after_diff: np.ndarray,
    bin_size_deg: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    edges = np.arange(0.0, 360.0 + bin_size_deg, bin_size_deg)
    radial = decomposition["radial_m"]
    transverse = decomposition["transverse_vec"]
    delta = decomposition["delta_angle_deg"]
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi >= 360.0:
            mask = (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = (angle_deg >= lo) & (angle_deg < hi)
        if not np.any(mask):
            continue
        before = stage6d.metrics(before_diff[mask])
        after = stage6d.metrics(after_diff[mask])
        total_rms = np.sqrt(np.mean(np.sum(correction_frd[mask] * correction_frd[mask], axis=1)))
        radial_rms = np.sqrt(np.mean(radial[mask] * radial[mask]))
        transverse_rms = np.sqrt(np.mean(np.sum(transverse[mask] * transverse[mask], axis=1)))
        rows.append(
            {
                "scan_bin_deg": f"{int(lo):03d}-{int(hi):03d}",
                "point_count": int(np.count_nonzero(mask)),
                "correction_total_rms_m": float(total_rms),
                "radial_rms_m": float(radial_rms),
                "transverse_rms_m": float(transverse_rms),
                "delta_angle_median_deg": float(np.median(delta[mask])),
                "delta_angle_p90_abs_deg": float(np.percentile(np.abs(delta[mask]), 90)),
                "before_vector_rmse_m": before["vector_rmse_m"],
                "after_vector_rmse_m": after["vector_rmse_m"],
                "before_horizontal_rmse_m": before["horizontal_rmse_m"],
                "after_horizontal_rmse_m": after["horizontal_rmse_m"],
                "before_down_rmse_m": before["down_rmse_m"],
                "after_down_rmse_m": after["down_rmse_m"],
            }
        )
    return rows


def scan_bin_fields() -> list[str]:
    return [
        "scan_bin_deg",
        "point_count",
        "correction_total_rms_m",
        "radial_rms_m",
        "transverse_rms_m",
        "delta_angle_median_deg",
        "delta_angle_p90_abs_deg",
        "before_vector_rmse_m",
        "after_vector_rmse_m",
        "before_horizontal_rmse_m",
        "after_horizontal_rmse_m",
        "before_down_rmse_m",
        "after_down_rmse_m",
    ]


def gate_conclusion(best: dict[str, Any], rows_by_type: dict[str, dict[str, Any]], decomp: dict[str, Any]) -> tuple[str, str, bool]:
    horizontal_improvement = float(best["validation_horizontal_improvement_pct"])
    vector_after = float(best["validation_after_vector_rmse_m"])
    model_type = str(best["model_type"])
    transverse_energy = float(decomp["summary"]["transverse_energy_pct"])
    angle_model = rows_by_type.get("angle_delta_rad")
    transverse_model = rows_by_type.get("transverse_unit")
    physical_model_ok = False
    if angle_model and float(angle_model["validation_horizontal_improvement_pct"]) >= 50.0:
        physical_model_ok = True
    if transverse_model and float(transverse_model["validation_horizontal_improvement_pct"]) >= 80.0:
        physical_model_ok = True

    if horizontal_improvement >= 80.0 and vector_after <= 0.30 and transverse_energy >= 80.0 and physical_model_ok:
        return "合理", "FRD/body 分解显示残差主要为横向方向误差，物理方向余弦/角度模型在验证集上显著改善。", True
    if horizontal_improvement >= 70.0 and vector_after <= 0.35:
        return "基本合理但有风险", "body 坐标扫描残差模型有效，但需进一步替换为可解释的扫描几何公式后再做连续段。", False
    return "不合理", "body 坐标模型未能稳定解释剩余误差，不建议继续沿扫描几何方向直接推广。", False


def write_report(payload: dict[str, Any]) -> None:
    best = payload["best_model_summary"]
    decomp = payload["body_decomposition_summary"]
    gate = payload["gate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6H CH1 Body-Frame Scan Geometry Diagnostic

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Recommendation: {gate['recommendation']}

## Body-Frame Residual Decomposition

- total_correction_rms_m: {decomp['total_correction_rms_m']:.6f}
- radial_rms_m: {decomp['radial_rms_m']:.6f}
- transverse_rms_m: {decomp['transverse_rms_m']:.6f}
- radial_energy_pct: {decomp['radial_energy_pct']:.3f}%
- transverse_energy_pct: {decomp['transverse_energy_pct']:.3f}%
- instant_angle_energy_explained_pct: {decomp['instant_angle_energy_explained_pct']:.3f}%
- delta_angle_rmse_deg: {decomp['delta_angle_rmse_deg']:.6f}
- delta_angle_p90_abs_deg: {decomp['delta_angle_p90_abs_deg']:.6f}

## Best Body Model

- model_name: `{best['model_name']}`
- model_type: `{best['model_type']}`
- validation_vector_rmse: {best['validation_before_vector_rmse_m']:.6f} -> {best['validation_after_vector_rmse_m']:.6f} m
- validation_horizontal_rmse: {best['validation_before_horizontal_rmse_m']:.6f} -> {best['validation_after_horizontal_rmse_m']:.6f} m
- validation_horizontal_improvement_pct: {best['validation_horizontal_improvement_pct']:.3f}%
- full_vector_rmse: {best['full_before_vector_rmse_m']:.6f} -> {best['full_after_vector_rmse_m']:.6f} m

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Model summary CSV: `{payload['outputs']['model_summary_csv']}`
- Best model JSON: `{payload['outputs']['best_body_model_json']}`
- Scan-bin decomposition CSV: `{payload['outputs']['scan_bins_csv']}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只做 body/FRD 扫描几何诊断，不执行 Stage 6G，不覆盖 H5/LAZ。
- 如果采用本阶段结果，下一步应修改或重建 `f_body_frame_xyz()` / PDF 4.4.2 扫描几何，而不是把经验补偿直接全量应用。
"""
    path = REPORT_DIR / "stage6h_ch1_body_scan_geometry_diagnostic_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading Stage 6F best candidate and exact-time matched data...", flush=True)
    candidate = load_best_candidate()
    data = diag.load_matched_data(args.max_matched_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    geom = stage6f.build_base_geometry(data, calibration)
    rotation_cols = stage6f.rotation_columns(geom)
    before_diff, correction_frd = apply_candidate_prediction(geom, rotation_cols, candidate)
    boresight = (
        float(candidate["boresight_roll_deg"]),
        float(candidate["boresight_pitch_deg"]),
        float(candidate["boresight_yaw_deg"]),
    )
    derivative = angle_derivative_frd(geom["range_m"], geom["angle_deg"], boresight, args.derivative_epsilon_deg)
    decomposition = decompose_correction(geom, candidate, correction_frd, derivative)
    train_mask, validation_mask = stage6f2.train_validation_masks(
        geom["angle_deg"], args.validation_bin_deg, args.validation_stride
    )

    if args.progress:
        print(
            f"Fitting body-frame residual models with {np.count_nonzero(train_mask)} train and "
            f"{np.count_nonzero(validation_mask)} validation points...",
            flush=True,
        )
    models = fit_models(geom["angle_deg"], geom["range_m"], correction_frd, decomposition, train_mask, args.max_fourier_order)
    rows: list[dict[str, Any]] = []
    after_by_model: dict[str, np.ndarray] = {}
    for model in models:
        row, after = evaluate_model(
            model,
            geom["angle_deg"],
            geom["range_m"],
            decomposition["unit"],
            derivative,
            rotation_cols,
            before_diff,
            train_mask,
            validation_mask,
        )
        rows.append(row)
        after_by_model[model["model_name"]] = after
    rows = sorted(
        rows,
        key=lambda row: (
            float(row["validation_after_vector_rmse_m"]),
            -float(row["validation_horizontal_improvement_pct"]),
            float(row["full_after_vector_rmse_m"]),
        ),
    )
    for idx, row in enumerate(rows, 1):
        row["rank"] = idx
    model_by_name = {model["model_name"]: model for model in models}
    rows_by_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        rows_by_type.setdefault(str(row["model_type"]), row)
    best_row = rows[0]
    best_model = model_by_name[best_row["model_name"]]
    best_after = after_by_model[best_row["model_name"]]
    scan_rows = scan_bin_rows(
        geom["angle_deg"],
        correction_frd,
        decomposition,
        before_diff,
        best_after,
        30.0,
    )
    conclusion, reason, passed = gate_conclusion(best_row, rows_by_type, decomposition)

    model_summary_csv = OUT_DIR / "model_summary.csv"
    best_model_json = OUT_DIR / "best_body_scan_model.json"
    scan_bins_csv = OUT_DIR / "scan_angle_body_decomposition_before_after.csv"
    report_json = REPORT_DIR / "stage6h_ch1_body_scan_geometry_diagnostic_report.json"
    write_csv(model_summary_csv, rows, model_fields())
    write_json(best_model_json, best_model)
    write_csv(scan_bins_csv, scan_rows, scan_bin_fields())

    payload = {
        "stage_name": "stage6h_ch1_body_scan_geometry_diagnostic",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "reference_l3": str(diag.REFERENCE_L3),
            "l1_sample": str(diag.L1_SAMPLE),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
            "stage6f_best_candidate": str(STAGE6F_BEST),
        },
        "fixed_stage6f_candidate": candidate,
        "body_decomposition_summary": decomposition["summary"],
        "split": {
            "validation_bin_deg": args.validation_bin_deg,
            "validation_stride": args.validation_stride,
            "train_points": int(np.count_nonzero(train_mask)),
            "validation_points": int(np.count_nonzero(validation_mask)),
        },
        "search": {
            "max_matched_points": args.max_matched_points,
            "matched_points_loaded": int(data["matched_time"].size),
            "max_fourier_order": args.max_fourier_order,
            "model_count": len(models),
            "derivative_epsilon_deg": args.derivative_epsilon_deg,
        },
        "best_model_summary": best_row,
        "best_by_model_type": rows_by_type,
        "all_model_summaries": rows,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "passed": passed,
            "recommendation": (
                "Do not run Stage 6G automatically; next step should implement or test a physical scan-geometry replacement for f_body_frame_xyz."
            ),
        },
        "outputs": {
            "model_summary_csv": str(model_summary_csv),
            "best_body_model_json": str(best_model_json),
            "scan_bins_csv": str(scan_bins_csv),
            "report_json": str(report_json),
            "report_md": str(REPORT_DIR / "stage6h_ch1_body_scan_geometry_diagnostic_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "body_decomposition_summary": payload["body_decomposition_summary"],
                    "best_model_summary": best_row,
                    "best_by_model_type": rows_by_type,
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6H CH1 body-frame scan-geometry residual diagnostic.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--max-fourier-order", type=int, default=4)
    parser.add_argument("--validation-bin-deg", type=float, default=5.0)
    parser.add_argument("--validation-stride", type=int, default=5)
    parser.add_argument("--derivative-epsilon-deg", type=float, default=0.01)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
