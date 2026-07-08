from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import Transformer

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5


ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_PROJECT_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3",
    )
)
C_DATA_ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_C_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0\0510_f30510_f3_data",
    )
)
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
QC_DIR = ROOT / "outputs" / "qc" / "stage5r_ch1_v2_sample"
PREVIEW_DIR = ROOT / "outputs" / "preview"
TXT_ROOT = ROOT / "outputs" / "txt_ch1"
H5_ROOT = C_DATA_ROOT / "outputs" / "h5_ch1" / "georef_v2_global_bias"

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0
DEFAULT_GLOBAL_HEIGHT_BIAS_M = 6.036329451805429
DEFAULT_FIRST12 = list(range(2, 14))
DEFAULT_STABLE = [111, 112, 113, 114, 115]
DEFAULT_TIME_REPAIR_CHECK = [14, 113]
DEFAULT_SAMPLE_SEQS = sorted(set(DEFAULT_FIRST12 + DEFAULT_STABLE + DEFAULT_TIME_REPAIR_CHECK))

METHOD_REGISTRY = [
    {
        "method_id": "DG_ALS_001",
        "method_name": "GNSS/IMU assisted direct georeferencing model",
        "source_type": "peer_reviewed_journal",
        "source_reference": "Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006",
        "used_for_delete_or_transform": "yes, coordinate transform context",
    },
    {
        "method_id": "PROJ_UTM_002",
        "method_name": "UTM to lon/lat projection conversion",
        "source_type": "official_documentation",
        "source_reference": "PROJ / pyproj official documentation",
        "used_for_delete_or_transform": "yes, coordinate conversion",
    },
    {
        "method_id": "PROJECT_EMPIRICAL_PARAMETER",
        "method_name": "time offset, time repair, axis mapping, fixed CH1 zero offset, global height bias",
        "source_type": "project_empirical_parameter",
        "source_reference": "Project data diagnosis; must not be described as a published algorithm",
        "used_for_delete_or_transform": "yes, explicitly marked empirical transform parameters",
    },
    {
        "method_id": "STRIP_QC_009",
        "method_name": "overlap / strip consistency QC",
        "source_type": "peer_reviewed_conference",
        "source_reference": "Filin & Vosselman, ISPRS 2004",
        "used_for_delete_or_transform": "no, QC only",
    },
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def select_infos(all_infos: list[stage5.FileInfo], seq_text: str) -> list[stage5.FileInfo]:
    wanted: set[int] = set()
    if seq_text:
        for token in seq_text.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                start, end = token.split("-", 1)
                wanted.update(range(int(start), int(end) + 1))
            else:
                wanted.add(int(token))
    else:
        wanted.update(DEFAULT_SAMPLE_SEQS)
    return [info for info in sorted(all_infos, key=lambda item: item.seq) if info.seq in wanted]


def cap_id(path: Path) -> str:
    return pipe.cap_id_from_l1_path(path)


def output_h5_path(info: stage5.FileInfo, strategy: str, time_status: str) -> Path:
    suffix = "_time_repaired" if time_status == "REPAIRED_TIME_EXPERIMENT" else ""
    return H5_ROOT / strategy.lower() / f"L3_CH1_georef_v2_{strategy}_{cap_id(info.path)}{suffix}.h5"


def txt_path_for(info: stage5.FileInfo, strategy: str, time_status: str) -> Path:
    group = "georef_v2_stable_00111_00115" if info.seq in DEFAULT_STABLE else "georef_v2_first12"
    suffix = "_time_repaired" if time_status == "REPAIRED_TIME_EXPERIMENT" else ""
    return TXT_ROOT / group / strategy.lower() / f"L3_CH1_georef_v2_{strategy}_{cap_id(info.path)}{suffix}.txt"


def zero_calibrate(
    range_before: np.ndarray,
    calibration: dict[str, float],
    strategy: str,
    min_support_count: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    zero_detected = pipe.find_zero_peak(range_before)
    zero_offset = float(calibration["zero_offset"])
    support_0_20 = int(np.count_nonzero((range_before >= 0.0) & (range_before <= 20.0)))
    warning = ""

    if strategy == "Z0":
        zero_used = zero_detected
        strategy_used = "Z0_current_auto_zero_peak"
        if not np.isfinite(zero_used):
            zero_used = 0.0
            warning = "auto zero not found; used 0 m fallback to keep diagnostic output"
    elif strategy == "Z1":
        zero_used = zero_offset
        strategy_used = "Z1_fixed_calib_zero_offset"
    elif strategy == "Z2":
        if np.isfinite(zero_detected) and support_0_20 >= min_support_count:
            zero_used = float(zero_detected)
            strategy_used = "Z2_auto_zero_high_support"
        else:
            zero_used = zero_offset
            strategy_used = "Z2_fixed_calib_zero_due_low_support"
            warning = f"auto zero support {support_0_20} < {min_support_count}; fixed calib zero_offset used"
    else:
        raise ValueError(f"Unsupported zero strategy: {strategy}")

    corrected = (range_before - float(zero_used) - calibration["intercept"]) / calibration["slope"]
    return corrected, {
        "zero_strategy_requested": strategy,
        "zero_strategy_used": strategy_used,
        "zero_peak_detected_m": float(zero_detected) if np.isfinite(zero_detected) else float("nan"),
        "zero_used_m": float(zero_used),
        "calib_zero_offset_m": zero_offset,
        "zero_peak_support_count_0_20m": support_0_20,
        "zero_warning": warning,
    }


def write_l3_v2(
    path: Path,
    points: np.ndarray,
    info: stage5.FileInfo,
    time_status: str,
    repair_model: dict[str, Any] | None,
    zero_meta: dict[str, Any],
    global_height_bias_m: float,
    pos_success_rate: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        l3 = h5.create_group("L3")
        metadata = h5.create_group("metadata")
        processing = metadata.create_group("processing")
        pipe.write_str_attr(processing, "stage", "stage5r_ch1_v2_sample_georef")
        pipe.write_str_attr(processing, "source_l1", rel(info.path))
        pipe.write_str_attr(processing, "crs", "EPSG:32651")
        pipe.write_str_attr(processing, "utm_zone", "51N/51R")
        pipe.write_str_attr(processing, "time_status", time_status)
        pipe.write_str_attr(processing, "schema", "slim_ch1_georeferenced_points")
        pipe.write_str_attr(processing, "height_bias_policy", "global fixed empirical bias; no per-file median height bias")
        processing.attrs["source_seq"] = info.seq
        processing.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        processing.attrs["stage3_range_min_m"] = 30.0
        processing.attrs["global_height_bias_m"] = float(global_height_bias_m)
        processing.attrs["pos_success_rate"] = float(pos_success_rate)
        for key, value in zero_meta.items():
            if isinstance(value, str):
                pipe.write_str_attr(processing, key, value)
            else:
                processing.attrs[key] = value
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


def write_cloudcompare_txt(path: Path, points: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    data = np.column_stack(
        [
            points["easting_m"],
            points["northing_m"],
            points["height_m"],
            points["gps_time"],
            points["range_m"].astype(np.float64),
            points["scan_angle_deg"].astype(np.float64),
            points["source_seq"].astype(np.float64),
            points["time_repair_flag"].astype(np.float64),
            points["quality_flag"].astype(np.float64),
            points["pos_quality_flag"].astype(np.float64),
        ]
    )
    np.savetxt(path, data, fmt="%.9f", delimiter="\t")


def write_txt_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "easting_m",
        "northing_m",
        "height_m",
        "gps_time",
        "range_m",
        "scan_angle_deg",
        "source_seq",
        "time_repair_flag",
        "quality_flag",
        "pos_quality_flag",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["txt_file", "columns", "source_h5", "point_count"])
        writer.writeheader()
        for row in rows:
            if row.get("output_txt"):
                writer.writerow(
                    {
                        "txt_file": row["output_txt"],
                        "columns": "|".join(columns),
                        "source_h5": row["output_h5"],
                        "point_count": row["point_count_l3"],
                    }
                )


def process_one(
    info: stage5.FileInfo,
    calibration: dict[str, float],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    transformer: Transformer,
    repair_model: dict[str, Any] | None,
    args: argparse.Namespace,
) -> tuple[dict[str, Any], np.ndarray | None]:
    if repair_model and repair_model.get("repair_status") == "UNREPAIRABLE":
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": "UNREPAIRABLE",
            "warning": repair_model.get("repair_reason", "unrepairable time"),
        }, None

    with h5py.File(info.path, "r") as h5:
        gnss = h5["GNSS_SEC_CH1"][:].astype(np.float64)
        raw_dist = h5["Photon_CH1_DIST"][:].astype(np.uint32)
        coder = h5["Photon_CH1_CODER"][:].astype(np.float64)
        pulse_index = h5["PULSE_INDEX_CH1"][:].astype(np.uint32)
        pulse_circle = h5["PULSE_CIRCLE_CH1"][:].astype(np.uint32)

    range_before = raw_dist.astype(np.float64) * DIST_FACTOR
    positive = range_before > 0
    gnss = gnss[positive]
    coder = coder[positive]
    pulse_index = pulse_index[positive]
    pulse_circle = pulse_circle[positive]
    range_before = range_before[positive]

    gnss_raw, lidar_time, time_status = stage5.compute_lidar_time(gnss, pulse_index, info, repair_model)
    range_m, zero_meta = zero_calibrate(range_before, calibration, args.zero_strategy, args.min_support_count)
    scan_angle = coder * 360.0 / 65536.0
    body_x, body_y, body_z = pipe.f_body_frame_xyz(range_m, 360.0 - scan_angle)

    no_pos = (lidar_time < pos_time[0]) | (lidar_time > pos_time[-1])
    nearest_dt = pipe.nearest_time_delta_abs(pos_time, np.clip(lidar_time, pos_time[0], pos_time[-1]))
    low_conf = nearest_dt > 0.2
    pos_flag = np.zeros(lidar_time.size, dtype=np.uint16)
    pos_flag[no_pos] |= 1
    pos_flag[low_conf] |= 2
    pos_success_rate = (lidar_time.size - np.count_nonzero(no_pos)) / max(int(lidar_time.size), 1)
    if pos_success_rate < 0.95:
        row = {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": time_status,
            "point_count_l1": info.point_count,
            "point_count_l3": 0,
            "pos_success_rate": pos_success_rate,
            "warning": "POS match success below 95% after optional repair",
        }
        row.update(zero_meta)
        return row, None

    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    pos_easting = np.interp(interp_time, pos_time, pos["EASTING"])
    pos_northing = np.interp(interp_time, pos_time, pos["NORTHING"])
    pos_height = np.interp(interp_time, pos_time, pos["HEIGHT"])
    pos_roll = np.interp(interp_time, pos_time, pos["ROLL"])
    pos_pitch = np.interp(interp_time, pos_time, pos["PITCH"])
    pos_heading = pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time)

    valid = (pos_flag == 0) & (range_m > 30.0)
    if not np.any(valid):
        row = {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": time_status,
            "point_count_l1": info.point_count,
            "point_count_l3": 0,
            "pos_success_rate": pos_success_rate,
            "warning": "no valid points after range/POS filtering",
        }
        row.update(zero_meta)
        return row, None

    north_offset, east_offset, down_offset = stage5.georef_offsets(
        body_x[valid],
        body_y[valid],
        body_z[valid],
        pos_roll[valid],
        pos_pitch[valid],
        pos_heading[valid],
    )
    raw_height = pos_height[valid] - down_offset
    height = raw_height + float(args.global_height_bias_m)
    easting = pos_easting[valid] + east_offset
    northing = pos_northing[valid] + north_offset
    lon, lat = transformer.transform(easting, northing)

    points = np.empty(easting.size, dtype=stage5.slim_dtype())
    points["source_seq"] = info.seq
    points["channel"] = 1
    points["gps_time"] = lidar_time[valid]
    points["easting_m"] = easting
    points["northing_m"] = northing
    points["height_m"] = height
    points["lon"] = lon
    points["lat"] = lat
    points["range_m"] = range_m[valid].astype(np.float32)
    points["scan_angle_deg"] = scan_angle[valid].astype(np.float32)
    points["pulse_index"] = pulse_index[valid]
    points["pulse_circle"] = pulse_circle[valid].astype(np.uint16)
    points["quality_flag"] = 0
    points["pos_quality_flag"] = pos_flag[valid]
    points["time_repair_flag"] = 1 if time_status == "REPAIRED_TIME_EXPERIMENT" else 0

    out_h5 = output_h5_path(info, args.zero_strategy, time_status)
    write_l3_v2(out_h5, points, info, time_status, repair_model, zero_meta, args.global_height_bias_m, pos_success_rate)

    out_txt = ""
    if not args.no_txt:
        txt_path = txt_path_for(info, args.zero_strategy, time_status)
        write_cloudcompare_txt(txt_path, points)
        out_txt = rel(txt_path)

    warning = zero_meta.get("zero_warning", "")
    if np.min(height) < -100 or np.max(height) > 120:
        warning = (warning + "; " if warning else "") + "height contains large outliers"

    row = {
        "seq": info.seq,
        "file": rel(info.path),
        "status": "PROCESSED",
        "time_status": time_status,
        "output_h5": str(out_h5),
        "output_txt": out_txt,
        "point_count_l1": info.point_count,
        "point_count_l3": int(points.size),
        "pos_success_rate": pos_success_rate,
        "global_height_bias_m": float(args.global_height_bias_m),
        "gps_min": float(np.min(points["gps_time"])),
        "gps_max": float(np.max(points["gps_time"])),
        "easting_min": float(np.min(points["easting_m"])),
        "easting_max": float(np.max(points["easting_m"])),
        "northing_min": float(np.min(points["northing_m"])),
        "northing_max": float(np.max(points["northing_m"])),
        "height_min": float(np.min(points["height_m"])),
        "height_max": float(np.max(points["height_m"])),
        "height_median": float(np.median(points["height_m"])),
        "warning": warning,
    }
    row.update(zero_meta)
    return row, points


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "seq",
        "file",
        "status",
        "time_status",
        "zero_strategy_requested",
        "zero_strategy_used",
        "zero_peak_detected_m",
        "zero_used_m",
        "calib_zero_offset_m",
        "zero_peak_support_count_0_20m",
        "global_height_bias_m",
        "output_h5",
        "output_txt",
        "point_count_l1",
        "point_count_l3",
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
        "warning",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def cell_height_medians(points: np.ndarray, cell_size_m: float, min_points_per_cell: int) -> dict[int, float]:
    if points.size == 0:
        return {}
    e_idx = np.floor(points["easting_m"].astype(np.float64) / cell_size_m).astype(np.int64)
    n_idx = np.floor(points["northing_m"].astype(np.float64) / cell_size_m).astype(np.int64)
    z = points["height_m"].astype(np.float64)
    finite = np.isfinite(e_idx) & np.isfinite(n_idx) & np.isfinite(z)
    e_idx = e_idx[finite]
    n_idx = n_idx[finite]
    z = z[finite]
    keys = e_idx * 20_000_000 + n_idx
    order = np.argsort(keys)
    keys = keys[order]
    z = z[order]
    medians: dict[int, float] = {}
    start = 0
    for idx in range(1, keys.size + 1):
        if idx == keys.size or keys[idx] != keys[start]:
            if idx - start >= min_points_per_cell:
                medians[int(keys[start])] = float(np.median(z[start:idx]))
            start = idx
    return medians


def downsample_points(points: np.ndarray, max_points: int) -> np.ndarray:
    if points.size <= max_points:
        return points
    step = int(math.ceil(points.size / max_points))
    return points[::step]


def overlap_rows(
    point_sets: dict[int, np.ndarray],
    cell_size_m: float,
    min_points_per_cell: int,
    max_points: int,
) -> list[dict[str, Any]]:
    medians = {
        seq: cell_height_medians(downsample_points(points, max_points), cell_size_m, min_points_per_cell)
        for seq, points in point_sets.items()
        if points is not None and points.size
    }
    rows: list[dict[str, Any]] = []
    for seq in sorted(medians):
        prev = seq - 1
        if prev not in medians:
            continue
        common = sorted(set(medians[prev]).intersection(medians[seq]))
        if not common:
            rows.append({"from_seq": prev, "to_seq": seq, "common_cells": 0})
            continue
        diffs = np.asarray([medians[seq][key] - medians[prev][key] for key in common], dtype=np.float64)
        rows.append(
            {
                "from_seq": prev,
                "to_seq": seq,
                "common_cells": len(common),
                "dz_median_m": float(np.median(diffs)),
                "dz_p10_m": float(np.percentile(diffs, 10)),
                "dz_p90_m": float(np.percentile(diffs, 90)),
                "abs_dz_median_m": float(np.median(np.abs(diffs))),
            }
        )
    return rows


def write_overlap_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = ["from_seq", "to_seq", "common_cells", "dz_median_m", "dz_p10_m", "dz_p90_m", "abs_dz_median_m"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_preview(path: Path, point_sets: dict[int, np.ndarray], seqs: list[int], max_points_per_file: int) -> None:
    samples = [downsample_points(point_sets[seq], max_points_per_file) for seq in seqs if seq in point_sets and point_sets[seq].size]
    if not samples:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html><body>No preview points.</body></html>", encoding="utf-8")
        return
    merged = np.concatenate(samples)
    pipe.make_stage3_preview(path, merged["easting_m"], merged["northing_m"], merged["height_m"], sample_count=min(500_000, merged.size))


def write_report(
    report_path: Path,
    rows: list[dict[str, Any]],
    overlap: list[dict[str, Any]],
    summary_csv: Path,
    overlap_csv: Path,
    txt_manifest: Path,
    first12_preview: Path,
    stable_preview: Path,
    args: argparse.Namespace,
) -> None:
    processed = [row for row in rows if row.get("status") == "PROCESSED"]
    skipped = [row for row in rows if row.get("status") == "SKIPPED"]
    abs_overlap = [float(row["abs_dz_median_m"]) for row in overlap if row.get("abs_dz_median_m") not in (None, "")]
    max_abs_overlap = max(abs_overlap) if abs_overlap else None
    median_abs_overlap = float(np.median(abs_overlap)) if abs_overlap else None
    conclusion = "基本合理但需人工检查"
    recommendation = "请先用 CloudCompare 检查 first12 与 00111-00115 的 v2 TXT/HTML，再决定是否允许全量 CH1 v2。"
    if max_abs_overlap is not None and max_abs_overlap > 1.0:
        conclusion = "基本合理但有风险"
        recommendation = "v2 仍存在局部重叠高差风险；若 CloudCompare 仍分层，需要进入 boresight/lever-arm/扫描角零位专题。"

    content = f"""# Stage 5R CH1 v2 小样本坐标候选报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}
- 阶段：stage5r_ch1_v2_sample
- 零位策略：{args.zero_strategy}
- 高程策略：global fixed empirical bias, no per-file median height bias

## Inputs and Outputs

- Summary CSV: `{rel(summary_csv)}`
- Overlap CSV: `{rel(overlap_csv)}`
- TXT manifest: `{rel(txt_manifest)}`
- First12 preview: `{rel(first12_preview)}`
- Stable preview: `{rel(stable_preview)}`
- H5 output root: `{H5_ROOT / args.zero_strategy.lower()}`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{chr(10).join(f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |" for m in METHOD_REGISTRY)}

## Parameters

- lidar time offset: {pipe.DEFAULT_TIME_OFFSET_SEC} s
- zero strategy: {args.zero_strategy}
- min support count for Z2: {args.min_support_count}
- global height bias: {args.global_height_bias_m} m
- range minimum for georeference: 30.0 m
- overlap cell size: {args.overlap_cell_m} m
- TXT is CH1 numeric-only; columns are documented in `{rel(txt_manifest)}`.

## Key Statistics

- Files requested: {len(rows)}
- Files processed: {len(processed)}
- Files skipped: {len(skipped)}
- Median overlap abs median dz: {median_abs_overlap}
- Max overlap abs median dz: {max_abs_overlap}

## Known Warnings

- 本阶段是 v2 小样本候选，不覆盖 Stage 5 v1、raw、light denoised。
- 固定零位和 global height bias 均为 `PROJECT_EMPIRICAL_PARAMETER`。
- 本阶段不做去噪、不删点、不做最终 LAS/LAZ。

## Manual Checklist

- CloudCompare 打开 first12 TXT，检查你之前框出的分层是否明显减少。
- CloudCompare 打开 00111-00115 TXT，检查稳定段是否没有变差。
- 查看 `overlap_height_consistency.csv`，重点看 `abs_dz_median_m`。
- 若 first12 改善但仍异常，标记起飞段风险，不直接进入最终成果。
- 若稳定段变差，停止并改查 boresight/lever-arm/扫描角零位。

## Gate Rule

Stop here. Do not run full CH1 v2 until this small-sample result is manually accepted.
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5R CH1 v2 sample georeference candidate.")
    parser.add_argument("--zero-strategy", choices=["Z0", "Z1", "Z2"], default="Z1")
    parser.add_argument("--seqs", default="", help="Comma/range list such as 2-14,111-115. Default uses the required sample set.")
    parser.add_argument("--global-height-bias-m", type=float, default=DEFAULT_GLOBAL_HEIGHT_BIAS_M)
    parser.add_argument("--min-support-count", type=int, default=1000)
    parser.add_argument("--no-txt", action="store_true", help="Skip CloudCompare TXT export.")
    parser.add_argument("--preview-points-per-file", type=int, default=80_000)
    parser.add_argument("--overlap-max-points", type=int, default=400_000)
    parser.add_argument("--overlap-cell-m", type=float, default=1.0)
    parser.add_argument("--min-points-per-cell", type=int, default=3)
    args = parser.parse_args()

    all_infos = stage5.read_manifest(stage5.MANIFEST)
    infos = select_infos(all_infos, args.seqs)
    if not infos:
        raise ValueError("No files selected for Stage 5R sample.")

    repair_models = stage5.build_repair_models(all_infos)
    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")
    pos_time, pos, _ = stage5.load_pos()
    transformer = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)

    rows: list[dict[str, Any]] = []
    point_sets: dict[int, np.ndarray] = {}
    for index, info in enumerate(infos, 1):
        row, points = process_one(info, calibration, pos_time, pos, transformer, repair_models.get(info.seq), args)
        rows.append(row)
        if points is not None:
            point_sets[info.seq] = points
        print(f"[{index}/{len(infos)}] seq {info.seq:05d} {row.get('status')} points={row.get('point_count_l3', 0)}")

    overlap = overlap_rows(point_sets, args.overlap_cell_m, args.min_points_per_cell, args.overlap_max_points)
    summary_csv = QC_DIR / f"ch1_v2_sample_{args.zero_strategy.lower()}_summary.csv"
    overlap_csv = QC_DIR / f"ch1_v2_sample_{args.zero_strategy.lower()}_overlap_height_consistency.csv"
    txt_manifest = QC_DIR / f"ch1_v2_sample_{args.zero_strategy.lower()}_txt_manifest.csv"
    write_summary_csv(summary_csv, rows)
    write_overlap_csv(overlap_csv, overlap)
    write_txt_manifest(txt_manifest, rows)

    first12_preview = PREVIEW_DIR / f"stage5r_ch1_v2_{args.zero_strategy.lower()}_first12.html"
    stable_preview = PREVIEW_DIR / f"stage5r_ch1_v2_{args.zero_strategy.lower()}_stable_00111_00115.html"
    make_preview(first12_preview, point_sets, DEFAULT_FIRST12 + [14], args.preview_points_per_file)
    make_preview(stable_preview, point_sets, DEFAULT_STABLE, args.preview_points_per_file)

    report_md = REPORT_DIR / f"stage5r_ch1_v2_sample_{args.zero_strategy.lower()}_report.md"
    report_json = REPORT_DIR / f"stage5r_ch1_v2_sample_{args.zero_strategy.lower()}_report.json"
    write_report(report_md, rows, overlap, summary_csv, overlap_csv, txt_manifest, first12_preview, stable_preview, args)
    report_json.write_text(
        json.dumps(
            {
                "stage_name": "stage5r_ch1_v2_sample",
                "zero_strategy": args.zero_strategy,
                "summary_csv": rel(summary_csv),
                "overlap_csv": rel(overlap_csv),
                "txt_manifest": rel(txt_manifest),
                "first12_preview": rel(first12_preview),
                "stable_preview": rel(stable_preview),
                "h5_output_root": str(H5_ROOT / args.zero_strategy.lower()),
                "method_registry": METHOD_REGISTRY,
                "gate_rule": "manual confirmation required before full CH1 v2",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )

    print("Stage 5R CH1 v2 sample complete.")
    print(f"Report: {report_md}")
    print(f"Summary CSV: {summary_csv}")
    print(f"Overlap CSV: {overlap_csv}")
    print(f"TXT manifest: {txt_manifest}")


if __name__ == "__main__":
    main()
