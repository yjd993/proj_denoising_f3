from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import Transformer

import ch1_pipeline as pipe


ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_PROJECT_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3",
    )
)
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
POS_SOURCE = ROOT / "0510_f3" / "0510f3_processed.mat"
REFERENCE_L3 = ROOT / "0510_f3" / "L3_DATA" / "L2_cap_00111_20260510190957.h5"
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
MANIFEST = ROOT / "metadata" / "l1_manifest_stage5_time_quality.csv"
OUT_DIR = ROOT / "outputs" / "h5_ch1"
PREVIEW_DIR = ROOT / "outputs" / "preview"
QC_DIR = ROOT / "outputs" / "qc"
REPORT_DIR = ROOT / "metadata" / "stage_reports"


@dataclass
class FileInfo:
    seq: int
    path: Path
    status: str
    reason: str
    gnss_min: float
    gnss_max: float
    point_count: int
    pulse_min: float
    pulse_max: float
    total_pulses: float


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_seq(path: Path) -> int:
    match = re.search(r"L1_cap_(\d+)_([0-9]{14})\.h5$", path.name)
    if not match:
        raise ValueError(f"Cannot parse sequence from {path}")
    return int(match.group(1))


def cap_id(path: Path) -> str:
    return pipe.cap_id_from_l1_path(path)


def output_path_for_l1(path: Path, repaired: bool = False) -> Path:
    suffix = "_time_repaired" if repaired else ""
    return OUT_DIR / f"L3S_CH1_{cap_id(path)}{suffix}.h5"


def read_manifest(path: Path) -> list[FileInfo]:
    if not path.exists():
        raise FileNotFoundError(f"Missing manifest: {path}")
    rows: list[FileInfo] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            l1_path = ROOT / row["file"]
            rows.append(
                FileInfo(
                    seq=int(float(row["seq"])),
                    path=l1_path,
                    status=row["status"],
                    reason=row.get("reason", ""),
                    gnss_min=float(row.get("gnss_min") or "nan"),
                    gnss_max=float(row.get("gnss_max") or "nan"),
                    point_count=int(float(row.get("point_count") or 0)),
                    pulse_min=float(row.get("pulse_min") or "nan"),
                    pulse_max=float(row.get("pulse_max") or "nan"),
                    total_pulses=float(row.get("total_pulses") or "nan"),
                )
            )
    return sorted(rows, key=lambda item: item.seq)


def missing_sequences(files: list[FileInfo]) -> list[int]:
    seqs = {item.seq for item in files}
    if not seqs:
        return []
    return [seq for seq in range(min(seqs), max(seqs) + 1) if seq not in seqs]


def median_pulse_period_sec(path: Path) -> float:
    with h5py.File(path, "r") as h5:
        pulse = h5["PULSE_INDEX_CH1"][:].astype(np.float64)
        time_values = h5["GNSS_SEC_CH1"][:].astype(np.float64)
    idx = np.linspace(0, pulse.size - 1, min(pulse.size, 200_000), dtype=np.int64)
    design = np.column_stack([np.ones(idx.size), pulse[idx]])
    _, slope = np.linalg.lstsq(design, time_values[idx], rcond=None)[0]
    return float(slope)


def build_repair_models(files: list[FileInfo]) -> dict[int, dict[str, Any]]:
    by_seq = {item.seq: item for item in files}
    bad = [item for item in files if item.status != "OK"]
    models: dict[int, dict[str, Any]] = {}
    i = 0
    while i < len(bad):
        group = [bad[i]]
        i += 1
        while i < len(bad) and bad[i].seq == group[-1].seq + 1:
            group.append(bad[i])
            i += 1

        prev_seq = group[0].seq - 1
        while prev_seq in by_seq and by_seq[prev_seq].status != "OK":
            prev_seq -= 1
        next_seq = group[-1].seq + 1
        while next_seq in by_seq and by_seq[next_seq].status != "OK":
            next_seq += 1

        prev_info = by_seq.get(prev_seq)
        next_info = by_seq.get(next_seq)
        if prev_info is None or next_info is None or prev_info.status != "OK" or next_info.status != "OK":
            for item in group:
                models[item.seq] = {
                    "repair_status": "UNREPAIRABLE",
                    "repair_reason": "missing normal neighboring file for time interpolation",
                }
            continue

        pulse_period = float(np.median([median_pulse_period_sec(prev_info.path), median_pulse_period_sec(next_info.path)]))
        raw_start = prev_info.gnss_max + pulse_period
        raw_end = next_info.gnss_min - pulse_period
        spans = [max(item.pulse_max - item.pulse_min, 1.0) for item in group]
        total_span = float(sum(spans))
        cursor = 0.0
        for item, span in zip(group, spans):
            file_start = raw_start + cursor / total_span * (raw_end - raw_start)
            file_end = raw_start + (cursor + span) / total_span * (raw_end - raw_start)
            models[item.seq] = {
                "repair_status": "REPAIRED_TIME_EXPERIMENT",
                "repair_reason": item.reason or item.status,
                "repair_group_sequences": ",".join(str(x.seq) for x in group),
                "prev_ok_seq": prev_info.seq,
                "prev_ok_file": rel(prev_info.path),
                "next_ok_seq": next_info.seq,
                "next_ok_file": rel(next_info.path),
                "pulse_period_sec": pulse_period,
                "group_raw_start_sec": raw_start,
                "group_raw_end_sec": raw_end,
                "file_raw_start_sec": file_start,
                "file_raw_end_sec": file_end,
                "file_pulse_min": item.pulse_min,
                "file_pulse_max": item.pulse_max,
            }
            cursor += span
    return models


def load_pos() -> tuple[np.ndarray, dict[str, np.ndarray], int]:
    pos = pipe.load_pos_mat(POS_SOURCE)
    missing = [field for field in pipe.POS_REQUIRED_FIELDS if field not in pos]
    if missing:
        raise ValueError(f"POS source missing fields: {', '.join(missing)}")
    pos_time_sec, corrections = pipe.process_pos_time_seconds(pos["TIME"])
    sort_idx = np.argsort(pos_time_sec)
    sorted_pos: dict[str, np.ndarray] = {}
    for field in pipe.POS_REQUIRED_FIELDS:
        if field == "TIME":
            continue
        sorted_pos[field] = np.asarray(pos[field], dtype=np.float64).reshape(-1)[sort_idx]
    return pos_time_sec[sort_idx], sorted_pos, corrections


def compute_lidar_time(gnss: np.ndarray, pulse: np.ndarray, info: FileInfo, repair_model: dict[str, Any] | None) -> tuple[np.ndarray, np.ndarray, str]:
    if repair_model and repair_model.get("repair_status") == "REPAIRED_TIME_EXPERIMENT":
        pulse_float = pulse.astype(np.float64)
        pmin = float(repair_model["file_pulse_min"])
        pmax = float(repair_model["file_pulse_max"])
        denom = max(pmax - pmin, 1.0)
        raw = float(repair_model["file_raw_start_sec"]) + (pulse_float - pmin) / denom * (
            float(repair_model["file_raw_end_sec"]) - float(repair_model["file_raw_start_sec"])
        )
        return raw, raw + pipe.DEFAULT_TIME_OFFSET_SEC, "REPAIRED_TIME_EXPERIMENT"
    return gnss.astype(np.float64), gnss.astype(np.float64) + pipe.DEFAULT_TIME_OFFSET_SEC, "ORIGINAL"


def georef_offsets(
    body_x: np.ndarray,
    body_y: np.ndarray,
    body_z: np.ndarray,
    roll_deg: np.ndarray,
    pitch_deg: np.ndarray,
    heading_deg: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    roll = np.deg2rad(roll_deg.astype(np.float64))
    pitch = np.deg2rad(pitch_deg.astype(np.float64))
    heading = np.deg2rad(heading_deg.astype(np.float64))
    cr = np.cos(roll)
    sr = np.sin(roll)
    cp = np.cos(pitch)
    sp = np.sin(pitch)
    ch = np.cos(heading)
    sh = np.sin(heading)

    forward = -body_x.astype(np.float64)
    right = -body_y.astype(np.float64)
    down_body = body_z.astype(np.float64)

    north = cp * ch * forward + (sr * sp * ch - cr * sh) * right + (cr * sp * ch + sr * sh) * down_body
    east = cp * sh * forward + (sr * sp * sh + cr * ch) * right + (cr * sp * sh - sr * ch) * down_body
    down = -sp * forward + sr * cp * right + cr * cp * down_body
    return north, east, down


def slim_dtype() -> np.dtype:
    return np.dtype(
        [
            ("source_seq", "u2"),
            ("channel", "u1"),
            ("gps_time", "f8"),
            ("easting_m", "f8"),
            ("northing_m", "f8"),
            ("height_m", "f8"),
            ("lon", "f8"),
            ("lat", "f8"),
            ("range_m", "f4"),
            ("scan_angle_deg", "f4"),
            ("pulse_index", "u4"),
            ("pulse_circle", "u2"),
            ("quality_flag", "u2"),
            ("pos_quality_flag", "u2"),
            ("time_repair_flag", "u1"),
        ]
    )


def write_l3_slim(
    path: Path,
    points: np.ndarray,
    info: FileInfo,
    time_status: str,
    repair_model: dict[str, Any] | None,
    reference_height_bias_m: float,
    pos_success_rate: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        l3 = h5.create_group("L3")
        metadata = h5.create_group("metadata")
        processing = metadata.create_group("processing")
        pipe.write_str_attr(processing, "stage", "stage5_full_ch1_slim_georef")
        pipe.write_str_attr(processing, "source_l1", rel(info.path))
        pipe.write_str_attr(processing, "crs", "EPSG:32651")
        pipe.write_str_attr(processing, "utm_zone", "51N/51R")
        pipe.write_str_attr(processing, "time_status", time_status)
        pipe.write_str_attr(processing, "schema", "slim_ch1_georeferenced_points")
        processing.attrs["source_seq"] = info.seq
        processing.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        processing.attrs["stage3_range_min_m"] = 30.0
        processing.attrs["reference_height_bias_m"] = float(reference_height_bias_m)
        processing.attrs["pos_success_rate"] = float(pos_success_rate)
        if repair_model:
            for key, value in repair_model.items():
                if isinstance(value, str):
                    pipe.write_str_attr(processing, key, value)
                elif isinstance(value, (int, float, np.integer, np.floating)):
                    processing.attrs[key] = value

        for ch in range(1, 5):
            ch_group = l3.create_group(f"CH{ch}")
            if ch == 1:
                ch_group.create_dataset("points", data=points, compression="gzip", compression_opts=4, chunks=True)
            else:
                ch_group.create_dataset("points", shape=(0,), dtype=points.dtype)


def process_one(
    info: FileInfo,
    calibration: dict[str, float],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    transformer: Transformer,
    reference_median_height: float,
    repair_model: dict[str, Any] | None,
    force: bool,
) -> tuple[dict[str, Any], np.ndarray | None]:
    repaired = bool(repair_model and repair_model.get("repair_status") == "REPAIRED_TIME_EXPERIMENT")
    out_path = output_path_for_l1(info.path, repaired=repaired)
    if out_path.exists() and not force:
        with h5py.File(out_path, "r") as h5:
            count = int(h5["L3/CH1/points"].shape[0])
            attrs = h5["metadata/processing"].attrs
            pos_success_rate = float(attrs.get("pos_success_rate", np.nan))
            height_bias = float(attrs.get("reference_height_bias_m", np.nan))
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "EXISTS",
            "time_status": "REPAIRED_TIME_EXPERIMENT" if repaired else "ORIGINAL",
            "output_l3": rel(out_path),
            "point_count_l1": info.point_count,
            "point_count_l3": count,
            "pos_success_rate": pos_success_rate,
            "reference_height_bias_m": height_bias,
            "warning": "reused existing output",
        }, None

    if repair_model and repair_model.get("repair_status") == "UNREPAIRABLE":
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": "UNREPAIRABLE",
            "output_l3": "",
            "point_count_l1": info.point_count,
            "point_count_l3": 0,
            "pos_success_rate": 0.0,
            "reference_height_bias_m": np.nan,
            "warning": repair_model.get("repair_reason", "unrepairable time"),
        }, None

    with h5py.File(info.path, "r") as h5:
        gnss = h5["GNSS_SEC_CH1"][:].astype(np.float64)
        raw_dist = h5["Photon_CH1_DIST"][:].astype(np.uint32)
        coder = h5["Photon_CH1_CODER"][:].astype(np.float64)
        pulse_index = h5["PULSE_INDEX_CH1"][:].astype(np.uint32)
        pulse_circle = h5["PULSE_CIRCLE_CH1"][:].astype(np.uint32)

    dist_factor = 2e-9 / 256.0 * 3e8 / 2.0
    range_before = raw_dist.astype(np.float64) * dist_factor
    positive = range_before > 0
    raw_dist = raw_dist[positive]
    coder = coder[positive]
    pulse_index = pulse_index[positive]
    pulse_circle = pulse_circle[positive]
    gnss = gnss[positive]
    range_before = range_before[positive]

    gnss_raw, lidar_time, time_status = compute_lidar_time(gnss, pulse_index, info, repair_model)
    range_m, zero_peak = pipe.calibrate_ranges(range_before, calibration)
    scan_angle = coder * 360.0 / 65536.0
    body_x, body_y, body_z = pipe.f_body_frame_xyz(range_m, 360.0 - scan_angle)

    no_pos = (lidar_time < pos_time[0]) | (lidar_time > pos_time[-1])
    nearest_dt = pipe.nearest_time_delta_abs(pos_time, np.clip(lidar_time, pos_time[0], pos_time[-1]))
    low_conf = nearest_dt > 0.2
    pos_flag = np.zeros(lidar_time.size, dtype=np.uint16)
    pos_flag[no_pos] |= 1
    pos_flag[low_conf] |= 2
    pos_success = int(lidar_time.size - np.count_nonzero(no_pos))
    pos_success_rate = pos_success / max(int(lidar_time.size), 1)
    if pos_success_rate < 0.95:
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": time_status,
            "output_l3": "",
            "point_count_l1": info.point_count,
            "point_count_l3": 0,
            "pos_success_rate": pos_success_rate,
            "reference_height_bias_m": np.nan,
            "warning": "POS match success below 95% after optional repair",
        }, None

    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    pos_easting = np.interp(interp_time, pos_time, pos["EASTING"])
    pos_northing = np.interp(interp_time, pos_time, pos["NORTHING"])
    pos_height = np.interp(interp_time, pos_time, pos["HEIGHT"])
    pos_roll = np.interp(interp_time, pos_time, pos["ROLL"])
    pos_pitch = np.interp(interp_time, pos_time, pos["PITCH"])
    pos_heading = pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time)

    valid = (pos_flag == 0) & (range_m > 30.0)
    if not np.any(valid):
        return {
            "seq": info.seq,
            "file": rel(info.path),
            "status": "SKIPPED",
            "time_status": time_status,
            "output_l3": "",
            "point_count_l1": info.point_count,
            "point_count_l3": 0,
            "pos_success_rate": pos_success_rate,
            "reference_height_bias_m": np.nan,
            "warning": "no valid points after range/POS filtering",
        }, None

    north_offset, east_offset, down_offset = georef_offsets(
        body_x[valid],
        body_y[valid],
        body_z[valid],
        pos_roll[valid],
        pos_pitch[valid],
        pos_heading[valid],
    )
    raw_height = pos_height[valid] - down_offset
    height_bias = float(reference_median_height - np.median(raw_height)) if raw_height.size else 0.0
    easting = pos_easting[valid] + east_offset
    northing = pos_northing[valid] + north_offset
    height = raw_height + height_bias
    lon, lat = transformer.transform(easting, northing)

    points = np.empty(easting.size, dtype=slim_dtype())
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

    write_l3_slim(out_path, points, info, time_status, repair_model, height_bias, pos_success_rate)
    warning = ""
    if zero_peak is None:
        warning = "zero peak not found"
    elif np.min(height) < -100 or np.max(height) > 120:
        warning = "height contains large outliers"

    return {
        "seq": info.seq,
        "file": rel(info.path),
        "status": "PROCESSED",
        "time_status": time_status,
        "output_l3": rel(out_path),
        "point_count_l1": info.point_count,
        "point_count_l3": int(points.size),
        "pos_success_rate": pos_success_rate,
        "reference_height_bias_m": height_bias,
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
    }, points


def append_csv(path: Path, row: dict[str, Any], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def write_repair_log(path: Path, files: list[FileInfo], models: dict[int, dict[str, Any]]) -> None:
    fields = [
        "seq",
        "file",
        "original_status",
        "original_reason",
        "repair_status",
        "repair_reason",
        "repair_group_sequences",
        "prev_ok_seq",
        "prev_ok_file",
        "next_ok_seq",
        "next_ok_file",
        "pulse_period_sec",
        "group_raw_start_sec",
        "group_raw_end_sec",
        "file_raw_start_sec",
        "file_raw_end_sec",
        "file_pulse_min",
        "file_pulse_max",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for info in files:
            if info.status == "OK":
                continue
            model = models.get(info.seq, {})
            row = {
                "seq": info.seq,
                "file": rel(info.path),
                "original_status": info.status,
                "original_reason": info.reason,
            }
            row.update(model)
            writer.writerow(row)


def make_overview_preview(path: Path, samples: list[np.ndarray]) -> None:
    if samples:
        merged = np.concatenate(samples)
        pipe.make_stage3_preview(path, merged["easting_m"], merged["northing_m"], merged["height_m"], sample_count=min(500_000, merged.size))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html><body>No preview points.</body></html>", encoding="utf-8")


def write_report(
    report_path: Path,
    summary_rows: list[dict[str, Any]],
    repair_count: int,
    missing: list[int],
    preview: Path,
    elapsed_sec: float,
) -> None:
    total_l1 = sum(int(row.get("point_count_l1") or 0) for row in summary_rows)
    total_l3 = sum(int(row.get("point_count_l3") or 0) for row in summary_rows)
    processed = [row for row in summary_rows if row.get("status") in {"PROCESSED", "EXISTS"}]
    skipped = [row for row in summary_rows if row.get("status") == "SKIPPED"]
    repaired = [row for row in summary_rows if row.get("time_status") == "REPAIRED_TIME_EXPERIMENT" and row.get("status") in {"PROCESSED", "EXISTS"}]
    warnings = [row for row in summary_rows if row.get("warning")]
    if skipped:
        conclusion = "基本合理但有风险"
        recommendation = "存在跳过文件；请先检查 summary 和 repair log，再决定是否补跑。"
    elif repair_count:
        conclusion = "基本合理但有风险"
        recommendation = "全量 CH1 已生成，但包含时间修复文件；建议人工查看预览和修复记录。"
    else:
        conclusion = "合理"
        recommendation = "全量 CH1 已生成；可进入 LAS/LAZ 转换和更严格去噪。"

    content = f"""# Stage 5 Full CH1 Processing Report

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}
- 阶段：stage5_full_ch1
- 处理通道：CH1
- 时间修正：`GNSS_SEC_CH1 + 18`
- 异常时间策略：类似 00113 的文件按邻近正常文件和 `PULSE_INDEX_CH1` 重建时间，并记录为 `REPAIRED_TIME_EXPERIMENT`

## Summary

- Input files: {len(summary_rows)}
- Processed/reused files: {len(processed)}
- Repaired-time files used: {len(repaired)}
- Skipped files: {len(skipped)}
- Missing sequence numbers: {missing}
- Total L1 CH1 points: {total_l1:,}
- Total L3 CH1 points: {total_l3:,}
- Elapsed minutes: {elapsed_sec / 60.0:.2f}

## Outputs

- Per-file slim L3 HDF5 directory: `{rel(OUT_DIR)}`
- File summary CSV: `{rel(QC_DIR / "stage5_file_summary.csv")}`
- Time repair log CSV: `{rel(QC_DIR / "stage5_time_repair_log.csv")}`
- Low-density HTML preview: `{rel(preview)}`

## Warnings

- Disk-aware output mode was used: Stage 5 writes slim georeferenced HDF5 per file, not full L2/L2P intermediates.
- LAS/LAZ export is deferred until this HDF5 result is accepted.
- Boresight/lever-arm calibration is still an engineering approximation from earlier stages.
- Warning rows in summary: {len(warnings)}

## Skipped Files

{chr(10).join(f'- seq {row.get("seq")}: {row.get("file")} - {row.get("warning")}' for row in skipped) if skipped else '- 无'}

## Gate Rule

Stop here. Do not expand to CH2-CH4 or convert final LAZ until the user manually confirms this Stage 5 result is acceptable.
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5 full CH1 georeferenced processing with logged time repair.")
    parser.add_argument("--force", action="store_true", help="Reprocess files even if slim L3 output exists.")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N manifest files for testing.")
    parser.add_argument("--sample-per-file", type=int, default=800)
    parser.add_argument("--min-free-gb", type=float, default=8.0)
    args = parser.parse_args()

    start = time.time()
    files = read_manifest(MANIFEST)
    if args.limit:
        files = files[: args.limit]
    repair_models = build_repair_models(files)
    write_repair_log(QC_DIR / "stage5_time_repair_log.csv", files, repair_models)

    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")
    pos_time, pos, _ = load_pos()
    _, _, _, ref_median_height = pipe.load_reference_l3_stats(REFERENCE_L3)
    if ref_median_height is None:
        raise ValueError(f"Reference median height unavailable: {REFERENCE_L3}")
    transformer = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)

    summary_path = QC_DIR / "stage5_file_summary.csv"
    if summary_path.exists() and args.force:
        summary_path.unlink()
    fields = [
        "seq",
        "file",
        "status",
        "time_status",
        "output_l3",
        "point_count_l1",
        "point_count_l3",
        "pos_success_rate",
        "reference_height_bias_m",
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
    summary_rows: list[dict[str, Any]] = []
    samples: list[np.ndarray] = []
    rng = np.random.default_rng(20260510)

    for idx, info in enumerate(files, 1):
        free_gb = shutil.disk_usage(ROOT).free / (1024**3)
        if free_gb < args.min_free_gb:
            row = {
                "seq": info.seq,
                "file": rel(info.path),
                "status": "SKIPPED",
                "time_status": "NOT_PROCESSED_LOW_DISK",
                "output_l3": "",
                "point_count_l1": info.point_count,
                "point_count_l3": 0,
                "pos_success_rate": np.nan,
                "reference_height_bias_m": np.nan,
                "warning": f"free disk below {args.min_free_gb} GB",
            }
            summary_rows.append(row)
            append_csv(summary_path, row, fields)
            print(f"[{idx}/{len(files)}] LOW DISK, stopping at seq {info.seq}. Free GB={free_gb:.2f}")
            break

        repair_model = repair_models.get(info.seq)
        try:
            row, points = process_one(info, calibration, pos_time, pos, transformer, float(ref_median_height), repair_model, args.force)
        except Exception as exc:
            row = {
                "seq": info.seq,
                "file": rel(info.path),
                "status": "SKIPPED",
                "time_status": "ERROR",
                "output_l3": "",
                "point_count_l1": info.point_count,
                "point_count_l3": 0,
                "pos_success_rate": np.nan,
                "reference_height_bias_m": np.nan,
                "warning": repr(exc),
            }
            points = None

        summary_rows.append(row)
        append_csv(summary_path, row, fields)
        if points is not None and points.size:
            take = min(args.sample_per_file, points.size)
            sample_idx = rng.choice(points.size, size=take, replace=False)
            samples.append(points[np.sort(sample_idx)])

        print(
            f"[{idx}/{len(files)}] seq {info.seq:05d} {row['status']} "
            f"{row['time_status']} L3={int(row.get('point_count_l3') or 0):,} "
            f"free={free_gb:.2f}GB"
        )

    preview = PREVIEW_DIR / "stage5_ch1_full_overview.html"
    make_overview_preview(preview, samples)
    write_report(
        REPORT_DIR / "stage5_full_ch1_processing_report.md",
        summary_rows,
        repair_count=sum(1 for item in repair_models.values() if item.get("repair_status") == "REPAIRED_TIME_EXPERIMENT"),
        missing=missing_sequences(read_manifest(MANIFEST)),
        preview=preview,
        elapsed_sec=time.time() - start,
    )
    (REPORT_DIR / "stage5_full_ch1_processing_report.json").write_text(
        json.dumps(
            {
                "stage_name": "stage5_full_ch1",
                "summary_csv": rel(summary_path),
                "repair_log_csv": rel(QC_DIR / "stage5_time_repair_log.csv"),
                "preview_html": rel(preview),
                "output_dir": rel(OUT_DIR),
                "elapsed_sec": time.time() - start,
                "files_attempted": len(summary_rows),
                "files_processed_or_reused": sum(1 for row in summary_rows if row.get("status") in {"PROCESSED", "EXISTS"}),
                "files_skipped": sum(1 for row in summary_rows if row.get("status") == "SKIPPED"),
                "repaired_files_used": sum(
                    1
                    for row in summary_rows
                    if row.get("time_status") == "REPAIRED_TIME_EXPERIMENT" and row.get("status") in {"PROCESSED", "EXISTS"}
                ),
                "total_l3_points": sum(int(row.get("point_count_l3") or 0) for row in summary_rows),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )
    print("Stage 5 complete.")
    print(f"Report: {REPORT_DIR / 'stage5_full_ch1_processing_report.md'}")
    print(f"Preview: {preview}")
    print(f"Summary CSV: {summary_path}")
    print(f"Repair log CSV: {QC_DIR / 'stage5_time_repair_log.csv'}")


if __name__ == "__main__":
    main()
