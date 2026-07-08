from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag
import stage6d_ch1_rotation_zero_diagnostic as stage6d
import stage6f_ch1_boresight_lever_diagnostic as stage6f


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6f2_scan_angle_residual_diagnostic"
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
        "method_name": "Stage 6F2 scan-angle residual diagnostic correction models",
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


def train_validation_masks(angle_deg: np.ndarray, small_bin_deg: float, validation_stride: int) -> tuple[np.ndarray, np.ndarray]:
    if validation_stride < 2:
        raise ValueError("--validation-stride must be >= 2")
    train = np.ones(angle_deg.size, dtype=bool)
    validation = np.zeros(angle_deg.size, dtype=bool)
    bins = np.arange(0.0, 360.0 + small_bin_deg, small_bin_deg)
    for lo, hi in zip(bins[:-1], bins[1:]):
        if hi >= 360.0:
            idx = np.flatnonzero((angle_deg >= lo) & (angle_deg <= hi))
        else:
            idx = np.flatnonzero((angle_deg >= lo) & (angle_deg < hi))
        if idx.size == 0:
            continue
        val_idx = idx[::validation_stride]
        validation[val_idx] = True
        train[val_idx] = False
    return train, validation


def fourier_features(angle_deg: np.ndarray, order: int) -> np.ndarray:
    theta = np.deg2rad(angle_deg)
    cols = [np.ones(theta.size, dtype=np.float64)]
    for k in range(1, order + 1):
        cols.append(np.sin(k * theta))
        cols.append(np.cos(k * theta))
    return np.column_stack(cols)


def fit_fourier_model(angle_deg: np.ndarray, diff: np.ndarray, train_mask: np.ndarray, order: int) -> dict[str, Any]:
    x_train = fourier_features(angle_deg[train_mask], order)
    coef, *_ = np.linalg.lstsq(x_train, diff[train_mask], rcond=None)
    return {
        "model_type": "fourier",
        "model_name": f"fourier_order_{order}",
        "order": order,
        "coefficients_ned": coef,
    }


def apply_fourier_model(model: dict[str, Any], angle_deg: np.ndarray) -> np.ndarray:
    x = fourier_features(angle_deg, int(model["order"]))
    return x @ np.asarray(model["coefficients_ned"], dtype=np.float64)


def fit_bin_median_model(
    angle_deg: np.ndarray,
    diff: np.ndarray,
    train_mask: np.ndarray,
    bin_size_deg: float,
) -> dict[str, Any]:
    edges = np.arange(0.0, 360.0 + bin_size_deg, bin_size_deg)
    rows: list[dict[str, Any]] = []
    global_median = np.median(diff[train_mask], axis=0)
    for idx, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        if hi >= 360.0:
            mask = train_mask & (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = train_mask & (angle_deg >= lo) & (angle_deg < hi)
        if np.count_nonzero(mask) > 0:
            correction = np.median(diff[mask], axis=0)
        else:
            correction = global_median
        rows.append(
            {
                "bin_index": idx,
                "bin_start_deg": float(lo),
                "bin_end_deg": float(hi),
                "correction_ned_m": correction,
                "train_count": int(np.count_nonzero(mask)),
            }
        )
    return {
        "model_type": "bin_median",
        "model_name": f"bin_median_{bin_size_deg:g}deg",
        "bin_size_deg": float(bin_size_deg),
        "bins": rows,
        "global_median_ned_m": global_median,
    }


def apply_bin_median_model(model: dict[str, Any], angle_deg: np.ndarray) -> np.ndarray:
    out = np.empty((angle_deg.size, 3), dtype=np.float64)
    bin_size = float(model["bin_size_deg"])
    bins = model["bins"]
    indices = np.floor(np.mod(angle_deg, 360.0) / bin_size).astype(np.int64)
    indices = np.clip(indices, 0, len(bins) - 1)
    corrections = np.asarray([row["correction_ned_m"] for row in bins], dtype=np.float64)
    out[:] = corrections[indices]
    return out


def apply_model(model: dict[str, Any], angle_deg: np.ndarray) -> np.ndarray:
    if model["model_type"] == "fourier":
        return apply_fourier_model(model, angle_deg)
    if model["model_type"] == "bin_median":
        return apply_bin_median_model(model, angle_deg)
    raise ValueError(model["model_type"])


def summarize_model(model: dict[str, Any], angle_deg: np.ndarray, diff: np.ndarray, train_mask: np.ndarray, validation_mask: np.ndarray) -> dict[str, Any]:
    correction = apply_model(model, angle_deg)
    corrected = diff - correction
    subsets = {
        "train": train_mask,
        "validation": validation_mask,
        "full": np.ones(diff.shape[0], dtype=bool),
    }
    row: dict[str, Any] = {
        "model_name": model["model_name"],
        "model_type": model["model_type"],
    }
    for subset_name, mask in subsets.items():
        before = stage6d.metrics(diff[mask])
        after = stage6d.metrics(corrected[mask])
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
    return row


def model_summary_fields() -> list[str]:
    fields = ["rank", "model_name", "model_type"]
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


def scan_bin_rows(
    angle_deg: np.ndarray,
    before_diff: np.ndarray,
    after_diff: np.ndarray,
    bin_size_deg: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    edges = np.arange(0.0, 360.0 + bin_size_deg, bin_size_deg)
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi >= 360.0:
            mask = (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = (angle_deg >= lo) & (angle_deg < hi)
        if not np.any(mask):
            continue
        before = stage6d.metrics(before_diff[mask])
        after = stage6d.metrics(after_diff[mask])
        rows.append(
            {
                "scan_bin_deg": f"{int(lo):03d}-{int(hi):03d}",
                "point_count": int(np.count_nonzero(mask)),
                "before_vector_rmse_m": before["vector_rmse_m"],
                "after_vector_rmse_m": after["vector_rmse_m"],
                "before_horizontal_rmse_m": before["horizontal_rmse_m"],
                "after_horizontal_rmse_m": after["horizontal_rmse_m"],
                "before_down_rmse_m": before["down_rmse_m"],
                "after_down_rmse_m": after["down_rmse_m"],
                "after_north_median_m": after["north_median_m"],
                "after_east_median_m": after["east_median_m"],
                "after_down_median_m": after["down_median_m"],
            }
        )
    return rows


def gate_conclusion(best_row: dict[str, Any], best_scan_rows: list[dict[str, Any]]) -> tuple[str, str, bool]:
    val_improvement = float(best_row["validation_vector_improvement_pct"])
    val_after = float(best_row["validation_after_vector_rmse_m"])
    max_bin_after = max(float(row["after_vector_rmse_m"]) for row in best_scan_rows)
    if val_improvement >= 15.0 and val_after <= 0.65 and max_bin_after <= 0.80:
        return "合理", "扫描角残差模型在验证集上显著改善，剩余误差主要呈扫描角相关结构。", True
    if val_improvement >= 10.0 and val_after <= 0.70:
        return "基本合理但有风险", "扫描角模型能解释部分剩余误差，但分箱残差仍需人工检查，不能直接作为最终算法。", False
    return "不合理", "扫描角模型在验证集上的改善不足，剩余误差不能主要归因于简单扫描角周期残差。", False


def compact_model(model: dict[str, Any]) -> dict[str, Any]:
    if model["model_type"] == "fourier":
        return {
            "model_type": model["model_type"],
            "model_name": model["model_name"],
            "order": model["order"],
            "coefficients_ned": np.asarray(model["coefficients_ned"], dtype=np.float64),
        }
    return model


def write_report(payload: dict[str, Any]) -> None:
    best = payload["best_model_summary"]
    gate = payload["gate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6F2 CH1 Scan-Angle Residual Diagnostic

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Recommend next: {gate['recommendation']}

## Best Residual Model

- model_name: `{best['model_name']}`
- model_type: `{best['model_type']}`
- validation_vector_rmse: {best['validation_before_vector_rmse_m']:.6f} -> {best['validation_after_vector_rmse_m']:.6f} m
- validation_vector_improvement_pct: {best['validation_vector_improvement_pct']:.3f}%
- validation_horizontal_rmse: {best['validation_before_horizontal_rmse_m']:.6f} -> {best['validation_after_horizontal_rmse_m']:.6f} m
- full_vector_rmse: {best['full_before_vector_rmse_m']:.6f} -> {best['full_after_vector_rmse_m']:.6f} m

## Fixed Upstream Parameters

- Uses Stage 6F best boresight/lever from `{rel(STAGE6F_BEST)}`
- zero_offset_m: {stage6f.ZERO_OFFSET_M}
- angle_direction: `{stage6f.ANGLE_DIRECTION}`
- angle_offset_deg: {stage6f.ANGLE_OFFSET_DEG}
- rotation_order: `{stage6f.ROTATION_ORDER}`, transpose: {stage6f.ROTATION_TRANSPOSE}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Model summary CSV: `{payload['outputs']['model_summary_csv']}`
- Best model JSON: `{payload['outputs']['best_model_json']}`
- Scan-bin before/after CSV: `{payload['outputs']['scan_bins_csv']}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只诊断扫描角残差，不执行 Stage 6G，不覆盖 H5/LAZ。
- residual correction 是 `PROJECT_DIAGNOSTIC_PARAMETER`，不能直接作为最终生产模型。
"""
    path = REPORT_DIR / "stage6f2_ch1_scan_angle_residual_diagnostic_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading Stage 6F best candidate and exact-time matched data...", flush=True)
    best_candidate = load_best_candidate()
    data = diag.load_matched_data(args.max_matched_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    geom = stage6f.build_base_geometry(data, calibration)
    rotation_cols = stage6f.rotation_columns(geom)
    before_diff = stage6f.diff_for_candidate(geom, rotation_cols, best_candidate)
    angle = geom["angle_deg"]
    train_mask, validation_mask = train_validation_masks(angle, args.validation_bin_deg, args.validation_stride)

    if args.progress:
        print(
            f"Fitting scan-angle residual models with {np.count_nonzero(train_mask)} train and "
            f"{np.count_nonzero(validation_mask)} validation points...",
            flush=True,
        )
    models: list[dict[str, Any]] = []
    for order in range(1, args.max_fourier_order + 1):
        models.append(fit_fourier_model(angle, before_diff, train_mask, order))
    for bin_size in args.bin_sizes_deg:
        models.append(fit_bin_median_model(angle, before_diff, train_mask, bin_size))

    summaries = [summarize_model(model, angle, before_diff, train_mask, validation_mask) for model in models]
    summaries = sorted(
        summaries,
        key=lambda row: (
            float(row["validation_after_vector_rmse_m"]),
            -float(row["validation_vector_improvement_pct"]),
            float(row["full_after_vector_rmse_m"]),
        ),
    )
    for idx, row in enumerate(summaries, 1):
        row["rank"] = idx
    model_by_name = {model["model_name"]: model for model in models}
    best_summary = summaries[0]
    best_model = compact_model(model_by_name[best_summary["model_name"]])
    best_correction = apply_model(best_model, angle)
    after_diff = before_diff - best_correction
    scan_rows = scan_bin_rows(angle, before_diff, after_diff, 30.0)
    conclusion, reason, passed = gate_conclusion(best_summary, scan_rows)

    model_summary_csv = OUT_DIR / "model_summary.csv"
    best_model_json = OUT_DIR / "best_scan_angle_residual_model.json"
    scan_bins_csv = OUT_DIR / "scan_angle_bin_before_after.csv"
    report_json = REPORT_DIR / "stage6f2_ch1_scan_angle_residual_diagnostic_report.json"
    write_csv(model_summary_csv, summaries, model_summary_fields())
    write_json(best_model_json, best_model)
    write_csv(scan_bins_csv, scan_rows, list(scan_rows[0].keys()) if scan_rows else ["scan_bin_deg"])

    payload = {
        "stage_name": "stage6f2_ch1_scan_angle_residual_diagnostic",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "reference_l3": str(diag.REFERENCE_L3),
            "l1_sample": str(diag.L1_SAMPLE),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
            "stage6f_best_candidate": str(STAGE6F_BEST),
        },
        "fixed_stage6f_candidate": best_candidate,
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
            "bin_sizes_deg": args.bin_sizes_deg,
            "model_count": len(models),
        },
        "best_model_summary": best_summary,
        "all_model_summaries": summaries,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "passed": passed,
            "recommendation": (
                "Do not run Stage 6G automatically; use this report to decide whether to implement a physical scan-geometry correction."
            ),
        },
        "outputs": {
            "model_summary_csv": str(model_summary_csv),
            "best_model_json": str(best_model_json),
            "scan_bins_csv": str(scan_bins_csv),
            "report_json": str(report_json),
            "report_md": str(REPORT_DIR / "stage6f2_ch1_scan_angle_residual_diagnostic_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)

    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "best_model_summary": best_summary,
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def parse_float_list(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6F2 CH1 scan-angle residual diagnostic against exact-time L3 00111.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--max-fourier-order", type=int, default=4)
    parser.add_argument("--bin-sizes-deg", type=parse_float_list, default=[30.0, 15.0])
    parser.add_argument("--validation-bin-deg", type=float, default=5.0)
    parser.add_argument("--validation-stride", type=int, default=5)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
