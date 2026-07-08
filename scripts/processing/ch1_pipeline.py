from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import plotly.graph_objects as go
from pyproj import Transformer
import scipy.io as sio


DEFAULT_SAMPLE_L1 = Path("0510_f3") / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00111_20260510190957.h5"
DEFAULT_REFERENCE_L3 = Path("0510_f3") / "L3_DATA" / "L2_cap_00111_20260510190957.h5"
DEFAULT_POS_MAT = Path("0510_f3") / "0510f3_processed.mat"
DEFAULT_TIME_OFFSET_SEC = 18.0
DEFAULT_L2_DIR = Path("intermediate") / "l2_body_xyz"
DEFAULT_L2_POS_DIR = Path("intermediate") / "l2_pos_matched"
DEFAULT_L3_DIR = Path("intermediate") / "l3_georef"
DEFAULT_PREVIEW_DIR = Path("outputs") / "preview"
DEFAULT_CALIB_COEFFS = Path("untitled") / "calib_coeffs.mat"
DEFAULT_STAGE1_L2 = DEFAULT_L2_DIR / "L2_CH1_cap_00111_20260510190957.h5"
DEFAULT_STAGE2_L2_POS = DEFAULT_L2_POS_DIR / "L2P_CH1_cap_00111_20260510190957.h5"
DEFAULT_CONTINUOUS_L1_FILES = [
    Path("0510_f3") / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00111_20260510190957.h5",
    Path("0510_f3") / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00112_20260510191000.h5",
    Path("0510_f3") / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00113_20260510191003.h5",
    Path("0510_f3") / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00114_20260510191006.h5",
    Path("0510_f3") / "L1-TIME_ANGE_DIST_DATA" / "L1_cap_00115_20260510191009.h5",
]

CH1_REQUIRED_DATASETS = [
    "GNSS_SEC_CH1",
    "Photon_CH1_DIST",
    "Photon_CH1_CODER",
    "PULSE_INDEX_CH1",
    "PULSE_CIRCLE_CH1",
    "Photon_Start_Count_CH1",
]

REFERENCE_L3_DATASETS = [
    "GNSS_SEC",
    "POINT_X",
    "POINT_Y",
    "POINT_Z",
    "LIDAR_X",
    "LIDAR_Y",
    "LIDAR_Z",
]

POS_REQUIRED_FIELDS = [
    "TIME",
    "EASTING",
    "NORTHING",
    "HEIGHT",
    "ROLL",
    "PITCH",
    "HEADING",
]

FITRESULT_ALPHA = {
    "a0": -0.0181,
    "a1": 0.1829,
    "a2": -0.0118,
    "a3": -0.0002,
    "a4": -0.0001,
    "a5": 0.0000,
    "a6": 0.0000,
    "a7": -0.0001,
    "a8": 0.0000,
    "b1": -1.0484,
    "b2": 1.0231,
    "b3": 0.2563,
    "b4": 1.7250,
    "b5": 0.3178,
    "b6": 1.6729,
    "b7": 1.2308,
    "b8": 0.0403,
}

FITRESULT_BETA = {
    "a0": 0.0059,
    "a1": -0.2587,
    "a2": -0.0085,
    "a3": -0.0000,
    "a4": -0.0000,
    "a5": 0.0000,
    "a6": -0.0000,
    "a7": -0.0000,
    "a8": 0.0000,
    "b1": 0.5087,
    "b2": -0.5403,
    "b3": 7.3798,
    "b4": 1.0729,
    "b5": 1.0629,
    "b6": 0.5218,
    "b7": 1.1444,
    "b8": 0.7787,
}


@dataclass
class RangeStats:
    count: int
    minimum: float
    maximum: float
    mean: float


@dataclass
class Stage0Report:
    stage_name: str
    sample_l1: str
    reference_l3: str
    pos_source: str
    processed_channel: str
    lidar_time_offset_sec: float
    l1_missing_datasets: list[str]
    l3_missing_datasets: list[str]
    pos_missing_fields: list[str]
    l1_ch1_point_count: int
    l1_gnss_sec_raw: RangeStats | None
    l1_lidar_time_sec: RangeStats | None
    l3_gnss_sec: RangeStats | None
    l3_point_x: RangeStats | None
    l3_point_y: RangeStats | None
    l3_point_z: RangeStats | None
    pos_time_sec: RangeStats | None
    pos_time_corrections: int
    time_alignment_abs_error_sec: dict[str, float | None]
    pos_covers_lidar_time: bool
    known_warnings: list[str]
    conclusion: str
    recommendation: str


@dataclass
class Stage1Report:
    stage_name: str
    input_l1: str
    output_l2: str
    preview_html: str
    processed_channel: str
    lidar_time_offset_sec: float
    point_count_before: int
    point_count_after: int
    filtered_nonpositive_range_count: int
    gnss_sec_raw: RangeStats
    lidar_time_sec: RangeStats
    raw_dist: RangeStats
    range_m_before_calibration: RangeStats
    range_m: RangeStats
    scan_angle_deg: RangeStats
    body_x: RangeStats
    body_y: RangeStats
    body_z: RangeStats
    zero_peak_m: float | None
    channel_calibration: dict[str, float]
    empty_channel_placeholders: list[str]
    known_warnings: list[str]
    conclusion: str
    recommendation: str


@dataclass
class Stage2Report:
    stage_name: str
    input_l2: str
    output_l2_pos: str
    pos_source: str
    processed_channel: str
    point_count_before: int
    point_count_after: int
    pos_match_success_count: int
    pos_match_success_rate: float
    no_pos_count: int
    low_confidence_count: int
    lidar_time_sec: RangeStats
    pos_time_sec: RangeStats
    pos_interp_dt_abs: RangeStats
    pos_easting: RangeStats
    pos_northing: RangeStats
    pos_height: RangeStats
    pos_roll: RangeStats
    pos_pitch: RangeStats
    pos_heading: RangeStats
    pos_time_corrections: int
    low_confidence_threshold_sec: float
    empty_channel_placeholders: list[str]
    known_warnings: list[str]
    conclusion: str
    recommendation: str


@dataclass
class Stage3Report:
    stage_name: str
    input_l2_pos: str
    output_l3: str
    preview_html: str
    reference_l3: str
    processed_channel: str
    point_count_before: int
    point_count_after: int
    filtered_count: int
    range_min_for_georef_m: float
    gps_time: RangeStats
    north_offset_m: RangeStats
    east_offset_m: RangeStats
    down_offset_m: RangeStats
    easting_m: RangeStats
    northing_m: RangeStats
    height_m: RangeStats
    lon: RangeStats
    lat: RangeStats
    reference_point_x: RangeStats | None
    reference_point_y: RangeStats | None
    reference_point_z: RangeStats | None
    reference_height_bias_m: float
    height_qc_min_m: float | None
    height_qc_max_m: float | None
    height_qc_inlier_count: int
    height_qc_inlier_rate: float
    height_below_qc_count: int
    height_above_qc_count: int
    qc_preview_html: str
    crs: str
    utm_zone: str
    calibration_status: str
    empty_channel_placeholders: list[str]
    known_warnings: list[str]
    conclusion: str
    recommendation: str


@dataclass
class Stage4FileSummary:
    input_l1: str
    output_l2: str
    output_l2_pos: str
    output_l3: str
    point_count_l2: int
    point_count_l3: int
    gps_time_min: float
    gps_time_max: float
    easting_mean: float
    northing_mean: float
    height_median: float
    conclusion: str
    warnings: list[str]
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class Stage4Report:
    stage_name: str
    processed_channel: str
    input_files: list[str]
    output_l3_merged: str
    preview_html: str
    file_summaries: list[Stage4FileSummary]
    total_l2_points: int
    total_l3_points: int
    time_gap_seconds: list[float]
    merged_gps_time: RangeStats
    merged_easting: RangeStats
    merged_northing: RangeStats
    merged_height: RangeStats
    merged_lon: RangeStats
    merged_lat: RangeStats
    known_warnings: list[str]
    conclusion: str
    recommendation: str


@dataclass
class Stage35Model:
    dx_m: float
    dy_m: float
    dz_m: float
    z_scale: float
    rotation_deg: float
    apply_z_scale: bool
    apply_rotation: bool
    reference_easting_median: float
    reference_northing_median: float
    reference_height_median: float
    source_easting_median: float
    source_northing_median: float
    source_height_median: float


@dataclass
class Stage35FileSummary:
    input_l2_pos: str
    output_l3_calibrated: str
    point_count_before: int
    point_count_after: int
    skipped: bool
    skip_reason: str
    gps_time_min: float | None
    gps_time_max: float | None
    easting_mean: float | None
    northing_mean: float | None
    height_median: float | None
    height_min: float | None
    height_max: float | None


@dataclass
class Stage35Report:
    stage_name: str
    sample_input_l2_pos: str
    reference_l3: str
    calibration_model_path: str
    sample_output_l3_calibrated: str
    sample_preview_html: str
    continuous_output_l3_merged: str
    continuous_preview_html: str
    model: Stage35Model
    file_summaries: list[Stage35FileSummary]
    merged_point_count: int
    merged_gps_time: RangeStats
    merged_easting: RangeStats
    merged_northing: RangeStats
    merged_height: RangeStats
    known_warnings: list[str]
    conclusion: str
    recommendation: str


def finite_stats(values: np.ndarray) -> RangeStats:
    flat = np.asarray(values).reshape(-1)
    finite = flat[np.isfinite(flat)]
    if finite.size == 0:
        return RangeStats(count=int(flat.size), minimum=float("nan"), maximum=float("nan"), mean=float("nan"))
    return RangeStats(
        count=int(flat.size),
        minimum=float(np.min(finite)),
        maximum=float(np.max(finite)),
        mean=float(np.mean(finite)),
    )


def read_h5_dataset(path: Path, dataset: str) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        return np.asarray(h5[dataset][:])


def list_missing_h5_datasets(path: Path, datasets: list[str]) -> list[str]:
    missing: list[str] = []
    if not path.exists():
        return datasets[:]
    with h5py.File(path, "r") as h5:
        for dataset in datasets:
            if dataset not in h5:
                missing.append(dataset)
    return missing


def load_pos_mat(path: Path) -> dict[str, np.ndarray]:
    mat = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    return {key: np.asarray(value) for key, value in mat.items() if not key.startswith("__")}


def process_pos_time_seconds(time_values: np.ndarray) -> tuple[np.ndarray, int]:
    pos_time_second = np.asarray(time_values, dtype=np.float64).reshape(-1).copy()
    if pos_time_second.size == 0:
        return pos_time_second, 0

    int_day = np.fix(pos_time_second[0] / 24.0 / 3600.0)
    pos_time_second = pos_time_second - int_day * 24.0 * 3600.0

    diffs = np.diff(pos_time_second)
    non_monotonic = np.where(diffs <= 0)[0]
    if non_monotonic.size:
        pos_time_second[non_monotonic] = pos_time_second[non_monotonic] - 1e-6
    return pos_time_second, int(non_monotonic.size)


def interp_heading_deg(pos_time: np.ndarray, heading_deg: np.ndarray, target_time: np.ndarray) -> np.ndarray:
    heading_rad = np.deg2rad(np.asarray(heading_deg, dtype=np.float64).reshape(-1))
    unwrapped_rad = np.unwrap(heading_rad)
    interpolated_rad = np.interp(target_time, pos_time, unwrapped_rad)
    return np.mod(np.rad2deg(interpolated_rad), 360.0)


def nearest_time_delta_abs(sorted_time: np.ndarray, target_time: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(sorted_time, target_time)
    left_idx = np.clip(idx - 1, 0, sorted_time.size - 1)
    right_idx = np.clip(idx, 0, sorted_time.size - 1)
    left_delta = np.abs(target_time - sorted_time[left_idx])
    right_delta = np.abs(target_time - sorted_time[right_idx])
    return np.minimum(left_delta, right_delta)


def body_to_ned_offsets(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    # Empirical axis mapping for this project, checked against the existing L3 sample:
    # body_x/body_y/body_z -> forward/right/down = -x/-y/+z, then yaw-pitch-roll to NED.
    roll = np.deg2rad(points["pos_roll"].astype(np.float64))
    pitch = np.deg2rad(points["pos_pitch"].astype(np.float64))
    heading = np.deg2rad(points["pos_heading"].astype(np.float64))
    cr = np.cos(roll)
    sr = np.sin(roll)
    cp = np.cos(pitch)
    sp = np.sin(pitch)
    ch = np.cos(heading)
    sh = np.sin(heading)

    forward = -points["body_x"].astype(np.float64)
    right = -points["body_y"].astype(np.float64)
    down_body = points["body_z"].astype(np.float64)

    north = cp * ch * forward + (sr * sp * ch - cr * sh) * right + (cr * sp * ch + sr * sh) * down_body
    east = cp * sh * forward + (sr * sp * sh + cr * ch) * right + (cr * sp * sh - sr * ch) * down_body
    down = -sp * forward + sr * cp * right + cr * cp * down_body
    return north, east, down


def compare_time_ranges(lidar_time: np.ndarray | None, l3_time: np.ndarray | None) -> dict[str, float | None]:
    if lidar_time is None or l3_time is None or lidar_time.size == 0 or l3_time.size == 0:
        return {"min": None, "max": None, "mean": None}
    lidar_stats = finite_stats(lidar_time)
    l3_stats = finite_stats(l3_time)
    return {
        "min": abs(lidar_stats.minimum - l3_stats.minimum),
        "max": abs(lidar_stats.maximum - l3_stats.maximum),
        "mean": abs(lidar_stats.mean - l3_stats.mean),
    }


def build_stage0_report(
    sample_l1: Path,
    reference_l3: Path,
    pos_source: Path,
    lidar_time_offset_sec: float,
) -> Stage0Report:
    warnings: list[str] = []
    l1_missing = list_missing_h5_datasets(sample_l1, CH1_REQUIRED_DATASETS)
    l3_missing = list_missing_h5_datasets(reference_l3, REFERENCE_L3_DATASETS)

    l1_gnss = None
    lidar_time = None
    l3_time = None
    l3_x = None
    l3_y = None
    l3_z = None
    pos_time_second = None
    pos_time_corrections = 0
    pos_missing: list[str] = []

    if not sample_l1.exists():
        warnings.append(f"Sample L1 file does not exist: {sample_l1}")
    elif l1_missing:
        warnings.append(f"Sample L1 is missing required CH1 datasets: {', '.join(l1_missing)}")
    else:
        l1_gnss = read_h5_dataset(sample_l1, "GNSS_SEC_CH1").astype(np.float64)
        lidar_time = l1_gnss + lidar_time_offset_sec

    if not reference_l3.exists():
        warnings.append(f"Reference L3 file does not exist: {reference_l3}")
    elif l3_missing:
        warnings.append(f"Reference L3 is missing required datasets: {', '.join(l3_missing)}")
    else:
        l3_time = read_h5_dataset(reference_l3, "GNSS_SEC").astype(np.float64)
        l3_x = read_h5_dataset(reference_l3, "POINT_X").astype(np.float64)
        l3_y = read_h5_dataset(reference_l3, "POINT_Y").astype(np.float64)
        l3_z = read_h5_dataset(reference_l3, "POINT_Z").astype(np.float64)

    if not pos_source.exists():
        pos_missing = POS_REQUIRED_FIELDS[:]
        warnings.append(f"POS MAT file does not exist: {pos_source}")
    else:
        pos = load_pos_mat(pos_source)
        pos_missing = [field for field in POS_REQUIRED_FIELDS if field not in pos]
        if pos_missing:
            warnings.append(f"POS MAT is missing required fields: {', '.join(pos_missing)}")
        else:
            pos_time_second, pos_time_corrections = process_pos_time_seconds(pos["TIME"])

    time_error = compare_time_ranges(lidar_time, l3_time)

    pos_covers = False
    if lidar_time is not None and pos_time_second is not None and lidar_time.size and pos_time_second.size:
        lidar_stats = finite_stats(lidar_time)
        pos_stats = finite_stats(pos_time_second)
        pos_covers = pos_stats.minimum <= lidar_stats.minimum and pos_stats.maximum >= lidar_stats.maximum
        if not pos_covers:
            warnings.append("POS time range does not fully cover CH1 lidar_time_sec.")

    if time_error["min"] is None:
        warnings.append("Cannot compare L1 CH1 + offset with reference L3 time.")
    elif max(time_error["min"], time_error["max"]) > 1e-6:
        warnings.append("L1 CH1 + offset does not exactly align with reference L3 GNSS time range.")

    if l1_gnss is not None:
        if not np.all(np.isfinite(l1_gnss)):
            warnings.append("L1 GNSS_SEC_CH1 contains non-finite values.")
        if l1_gnss.size == 0:
            warnings.append("L1 GNSS_SEC_CH1 is empty.")

    if l1_missing or l3_missing or pos_missing or not pos_covers:
        conclusion = "不合理"
        recommendation = "暂停排查：阶段 0 的必要输入或 POS 时间覆盖不满足要求。"
    elif warnings:
        conclusion = "基本合理但有风险"
        recommendation = "建议人工查看警告；如警告可接受，再进入阶段 1。"
    else:
        conclusion = "合理"
        recommendation = "可以进入阶段 1：单文件 CH1 的 L1 到 L2 局部 XYZ。"

    return Stage0Report(
        stage_name="stage0_baseline_check",
        sample_l1=str(sample_l1),
        reference_l3=str(reference_l3),
        pos_source=str(pos_source),
        processed_channel="CH1",
        lidar_time_offset_sec=float(lidar_time_offset_sec),
        l1_missing_datasets=l1_missing,
        l3_missing_datasets=l3_missing,
        pos_missing_fields=pos_missing,
        l1_ch1_point_count=int(l1_gnss.size) if l1_gnss is not None else 0,
        l1_gnss_sec_raw=finite_stats(l1_gnss) if l1_gnss is not None else None,
        l1_lidar_time_sec=finite_stats(lidar_time) if lidar_time is not None else None,
        l3_gnss_sec=finite_stats(l3_time) if l3_time is not None else None,
        l3_point_x=finite_stats(l3_x) if l3_x is not None else None,
        l3_point_y=finite_stats(l3_y) if l3_y is not None else None,
        l3_point_z=finite_stats(l3_z) if l3_z is not None else None,
        pos_time_sec=finite_stats(pos_time_second) if pos_time_second is not None else None,
        pos_time_corrections=pos_time_corrections,
        time_alignment_abs_error_sec=time_error,
        pos_covers_lidar_time=pos_covers,
        known_warnings=warnings,
        conclusion=conclusion,
        recommendation=recommendation,
    )


def dataclass_to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: dataclass_to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: dataclass_to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [dataclass_to_jsonable(item) for item in value]
    return value


def format_stats(stats: RangeStats | None) -> str:
    if stats is None:
        return "N/A"
    return (
        f"count={stats.count:,}, "
        f"min={stats.minimum:.9f}, "
        f"max={stats.maximum:.9f}, "
        f"mean={stats.mean:.9f}"
    )


def write_stage0_markdown(report: Stage0Report, path: Path) -> None:
    warnings = report.known_warnings or ["无"]
    content = f"""# Stage 0 Baseline Check Report

## Gate Conclusion

- 结论：{report.conclusion}
- 建议：{report.recommendation}
- 阶段：{report.stage_name}
- 处理通道：{report.processed_channel}
- LIDAR 时间修正：`GNSS_SEC_CH1 + {report.lidar_time_offset_sec:g}`

## Inputs

- Sample L1: `{report.sample_l1}`
- Reference L3: `{report.reference_l3}`
- POS source: `{report.pos_source}`

## Required Dataset Check

- Missing L1 CH1 datasets: `{', '.join(report.l1_missing_datasets) if report.l1_missing_datasets else 'none'}`
- Missing L3 datasets: `{', '.join(report.l3_missing_datasets) if report.l3_missing_datasets else 'none'}`
- Missing POS fields: `{', '.join(report.pos_missing_fields) if report.pos_missing_fields else 'none'}`

## Key Statistics

- L1 CH1 point count: {report.l1_ch1_point_count:,}
- L1 raw GNSS seconds: {format_stats(report.l1_gnss_sec_raw)}
- L1 lidar_time_sec: {format_stats(report.l1_lidar_time_sec)}
- L3 GNSS seconds: {format_stats(report.l3_gnss_sec)}
- L3 POINT_X: {format_stats(report.l3_point_x)}
- L3 POINT_Y: {format_stats(report.l3_point_y)}
- L3 POINT_Z: {format_stats(report.l3_point_z)}
- POS time seconds: {format_stats(report.pos_time_sec)}
- POS non-monotonic corrections: {report.pos_time_corrections}

## Alignment Checks

- Time alignment absolute error, min sec: {report.time_alignment_abs_error_sec.get('min')}
- Time alignment absolute error, max sec: {report.time_alignment_abs_error_sec.get('max')}
- Time alignment absolute error, mean sec: {report.time_alignment_abs_error_sec.get('mean')}
- POS covers lidar_time_sec: {report.pos_covers_lidar_time}

## Known Warnings

{chr(10).join(f'- {warning}' for warning in warnings)}

## Gate Rule

Stop here. Do not run Stage 1 until the user manually confirms this Stage 0 result is acceptable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def load_channel_calibration(path: Path, channel: str = "ch1") -> dict[str, float]:
    mat = sio.loadmat(path, squeeze_me=True, struct_as_record=False)
    calib_data = mat["calib_data"]
    ch = getattr(calib_data, channel)
    return {field: float(getattr(ch, field)) for field in ch._fieldnames}


def find_zero_peak(
    data: np.ndarray,
    peak_range: tuple[float, float] = (0.0, 20.0),
    bin_width: float = 0.01875,
    fit_range: float = 0.5,
) -> float:
    all_ranges = np.asarray(data, dtype=np.float64).reshape(-1)
    all_ranges = all_ranges[np.isfinite(all_ranges) & (all_ranges > 0)]
    if all_ranges.size == 0:
        return float("nan")

    range_data = all_ranges[(all_ranges >= peak_range[0]) & (all_ranges <= peak_range[1])]
    if range_data.size == 0:
        return float("nan")

    edges = np.arange(peak_range[0], peak_range[1] + bin_width, bin_width)
    counts, _ = np.histogram(range_data, bins=edges)
    if counts.size == 0 or np.max(counts) == 0:
        return float("nan")

    max_idx = int(np.argmax(counts))
    peak_center_initial = float(edges[max_idx] + bin_width / 2.0)

    fit_min = max(0.0, peak_center_initial - fit_range)
    fit_max = peak_center_initial + fit_range
    fit_data = all_ranges[(all_ranges >= fit_min) & (all_ranges <= fit_max)]
    if fit_data.size < 10:
        return peak_center_initial

    fit_edges = np.arange(fit_min, fit_max + bin_width, bin_width)
    fit_counts, fit_edges = np.histogram(fit_data, bins=fit_edges)
    if fit_counts.size == 0 or np.max(fit_counts) == 0:
        return peak_center_initial
    centers = fit_edges[:-1] + bin_width / 2.0
    return float(centers[int(np.argmax(fit_counts))])


def calibrate_ranges(range_m: np.ndarray, calibration: dict[str, float]) -> tuple[np.ndarray, float | None]:
    zero_peak = find_zero_peak(range_m)
    if not np.isfinite(zero_peak):
        return range_m, None
    corrected = (range_m - zero_peak - calibration["intercept"]) / calibration["slope"]
    return corrected, float(zero_peak)


def f_body_frame_xyz(
    distance_m: np.ndarray,
    angle_deg: np.ndarray,
    alpha: dict[str, float] = FITRESULT_ALPHA,
    beta: dict[str, float] = FITRESULT_BETA,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    angle = np.deg2rad(angle_deg)

    d_rx = np.full_like(angle, alpha["a0"], dtype=np.float64)
    d_ry = np.full_like(angle, beta["a0"], dtype=np.float64)
    for idx in range(1, 9):
        d_rx += alpha[f"a{idx}"] * np.sin(idx * angle + alpha[f"b{idx}"])
        d_ry += beta[f"a{idx}"] * np.sin(idx * angle + beta[f"b{idx}"])

    d_rz_squared = 1.0 - d_rx**2 - d_ry**2
    d_rz = np.sqrt(np.maximum(d_rz_squared, 0.0))
    return distance_m * d_rx, distance_m * d_ry, distance_m * d_rz


def rotate_xyz(
    xyz: np.ndarray,
    roll_deg: float = 0.0,
    pitch_deg: float = 0.0,
    yaw_deg: float = 0.0,
) -> np.ndarray:
    x = xyz[:, 0]
    y = xyz[:, 1]
    z = xyz[:, 2]
    for axis, angle_deg_value in (("X", roll_deg), ("Y", pitch_deg), ("Z", yaw_deg)):
        if angle_deg_value == 0.0:
            continue
        angle = np.deg2rad(float(angle_deg_value))
        ca = np.cos(angle)
        sa = np.sin(angle)
        if axis == "X":
            y, z = ca * y - sa * z, sa * y + ca * z
        elif axis == "Y":
            x, z = ca * x + sa * z, -sa * x + ca * z
        elif axis == "Z":
            x, y = ca * x - sa * y, sa * x + ca * y
    return np.column_stack([x, y, z])


def f_body_frame_xyz_ladm2(
    distance_m: np.ndarray,
    angle_deg: np.ndarray,
    mirror_tilt_deg: float = 7.75,
    frame_rotation_deg: float = -45.0,
    axis_perm: tuple[int, int, int] = (1, 0, 2),
    axis_signs: tuple[int, int, int] = (1, -1, -1),
    boresight_deg: tuple[float, float, float] = (0.0, -2.0, 2.0),
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """LADM-II mirror-reflection scan geometry in the current FRD convention.

    This is an optional diagnostic replacement for ``f_body_frame_xyz``. It
    follows Cao 2017 section 4.4.2 formulas 4-7 to 4-14: build the mirror
    normal in X'Y'Z', rotate it into sensor sXYZ, reflect the incoming beam,
    then map sXYZ into the current forward-right-down axes.
    """
    angle = np.deg2rad(angle_deg.astype(np.float64))
    tilt = np.deg2rad(float(mirror_tilt_deg))
    normal_prime = np.column_stack(
        [
            np.sin(tilt) * np.cos(angle),
            np.sin(tilt) * np.sin(angle),
            -np.cos(tilt) * np.ones_like(angle),
        ]
    )
    gamma = np.deg2rad(float(frame_rotation_deg))
    frame_rotation = np.array(
        [
            [np.cos(gamma), 0.0, np.sin(gamma)],
            [0.0, 1.0, 0.0],
            [-np.sin(gamma), 0.0, np.cos(gamma)],
        ],
        dtype=np.float64,
    )
    normal = normal_prime @ frame_rotation.T
    normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-12)

    incoming = np.array([-1.0, 0.0, 0.0], dtype=np.float64)
    reflected_s = incoming - 2.0 * np.sum(incoming * normal, axis=1)[:, None] * normal
    reflected_s /= np.maximum(np.linalg.norm(reflected_s, axis=1)[:, None], 1e-12)

    unit_frd = np.column_stack(
        [axis_signs[i] * reflected_s[:, axis_perm[i]] for i in range(3)]
    )
    if boresight_deg != (0.0, 0.0, 0.0):
        unit_frd = rotate_xyz(unit_frd, *boresight_deg)
    frd = distance_m[:, None] * unit_frd
    return frd[:, 0], frd[:, 1], frd[:, 2]


def h5_create_or_replace(parent: h5py.Group, name: str, data: np.ndarray, **kwargs: Any) -> None:
    if name in parent:
        del parent[name]
    parent.create_dataset(name, data=data, **kwargs)


def write_str_attr(obj: h5py.Group | h5py.Dataset, key: str, value: str) -> None:
    obj.attrs[key] = np.bytes_(value)


def cap_id_from_l1_path(path: Path) -> str:
    match = re.search(r"(?:L1|L2_CH1|L2P_CH1|L3_CH1)_cap_(\d+)_([0-9]{14})\.h5$", path.name)
    if match:
        return f"cap_{match.group(1)}_{match.group(2)}"
    return path.stem.replace("L1_", "")


def default_l2_path(l2_dir: Path, sample_l1: Path) -> Path:
    return l2_dir / f"L2_CH1_{cap_id_from_l1_path(sample_l1)}.h5"


def default_l2_pos_path(l2_pos_dir: Path, l2_path: Path) -> Path:
    name = l2_path.name.replace("L2_CH1_", "L2P_CH1_")
    return l2_pos_dir / name


def default_l3_path(l3_dir: Path, l2_pos_path: Path) -> Path:
    name = l2_pos_path.name.replace("L2P_CH1_", "L3_CH1_")
    return l3_dir / name


def write_stage1_l2(
    output_path: Path,
    source_file: Path,
    arrays: dict[str, np.ndarray],
    calibration: dict[str, float],
    zero_peak: float | None,
    lidar_time_offset_sec: float,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with h5py.File(output_path, "w") as h5:
        l2_group = h5.create_group("L2")
        metadata = h5.create_group("metadata")
        channel_params = metadata.create_group("channel_params")
        processing = metadata.create_group("processing")

        write_str_attr(processing, "source_file", str(source_file))
        write_str_attr(processing, "stage", "stage1_l1_to_l2_body_xyz")
        processing.attrs["lidar_time_offset_sec"] = float(lidar_time_offset_sec)
        processing.attrs["zero_peak_m"] = np.nan if zero_peak is None else float(zero_peak)
        write_str_attr(processing, "coordinate_frame", "body/sensor frame from existing F_BodyFrame_XYZ model")

        dtype = np.dtype(
            [
                ("source_file_id", "u2"),
                ("channel", "u1"),
                ("pulse_index", "u4"),
                ("pulse_circle", "u4"),
                ("gnss_sec_raw", "f8"),
                ("lidar_time_sec", "f8"),
                ("raw_dist", "u4"),
                ("range_m", "f8"),
                ("coder", "f8"),
                ("scan_angle_deg", "f8"),
                ("body_x", "f8"),
                ("body_y", "f8"),
                ("body_z", "f8"),
                ("quality_flag", "u2"),
            ]
        )

        points = np.empty(arrays["range_m"].size, dtype=dtype)
        points["source_file_id"] = 1
        points["channel"] = 1
        points["pulse_index"] = arrays["pulse_index"].astype(np.uint32)
        points["pulse_circle"] = arrays["pulse_circle"].astype(np.uint32)
        points["gnss_sec_raw"] = arrays["gnss_sec_raw"]
        points["lidar_time_sec"] = arrays["lidar_time_sec"]
        points["raw_dist"] = arrays["raw_dist"].astype(np.uint32)
        points["range_m"] = arrays["range_m"]
        points["coder"] = arrays["coder"]
        points["scan_angle_deg"] = arrays["scan_angle_deg"]
        points["body_x"] = arrays["body_x"]
        points["body_y"] = arrays["body_y"]
        points["body_z"] = arrays["body_z"]
        points["quality_flag"] = arrays["quality_flag"].astype(np.uint16)

        for ch in range(1, 5):
            ch_group = l2_group.create_group(f"CH{ch}")
            params = channel_params.create_group(f"CH{ch}")
            params.attrs["processed"] = ch == 1
            if ch == 1:
                params.attrs["zero_offset"] = calibration["zero_offset"]
                params.attrs["slope"] = calibration["slope"]
                params.attrs["intercept"] = calibration["intercept"]
                params.attrs["zero_peak_m"] = np.nan if zero_peak is None else float(zero_peak)
                ch_group.create_dataset("points", data=points, compression="gzip", compression_opts=4)
            else:
                write_str_attr(params, "status", "not_processed_in_this_stage")
                ch_group.create_dataset("points", shape=(0,), dtype=dtype)


def make_stage1_preview(
    preview_path: Path,
    body_x: np.ndarray,
    body_y: np.ndarray,
    body_z: np.ndarray,
    range_m: np.ndarray,
    sample_count: int = 200_000,
    seed: int = 42,
) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    count = body_x.size
    if count > sample_count:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(count, size=sample_count, replace=False))
    else:
        idx = np.arange(count)

    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=body_x[idx],
                y=body_y[idx],
                z=body_z[idx],
                mode="markers",
                marker={
                    "size": 1.4,
                    "color": range_m[idx],
                    "colorscale": "Viridis",
                    "opacity": 0.8,
                    "colorbar": {"title": "range_m", "thickness": 14},
                },
                hovertemplate="X: %{x:.3f}<br>Y: %{y:.3f}<br>Z: %{z:.3f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Stage 1 CH1 Body-Frame XYZ Preview",
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        scene={
            "xaxis_title": "body_x (m)",
            "yaxis_title": "body_y (m)",
            "zaxis_title": "body_z (m)",
            "aspectmode": "data",
        },
        template="plotly_white",
    )
    fig.write_html(preview_path, include_plotlyjs=True, full_html=True)


def build_stage1_report(
    sample_l1: Path,
    output_l2: Path,
    preview_html: Path,
    calibration: dict[str, float],
    zero_peak: float | None,
    point_count_before: int,
    filtered_nonpositive_range_count: int,
    arrays: dict[str, np.ndarray],
    lidar_time_offset_sec: float,
) -> Stage1Report:
    warnings: list[str] = []
    range_stats = finite_stats(arrays["range_m"])
    raw_range_stats = finite_stats(arrays["range_m_before_calibration"])
    x_stats = finite_stats(arrays["body_x"])
    y_stats = finite_stats(arrays["body_y"])
    z_stats = finite_stats(arrays["body_z"])

    if arrays["range_m"].size == 0:
        warnings.append("CH1 has no valid positive ranges after basic filtering.")
    if range_stats.minimum < -5:
        warnings.append("Calibrated range contains values below -5 m.")
    if not np.all(np.isfinite(arrays["body_x"])) or not np.all(np.isfinite(arrays["body_y"])) or not np.all(np.isfinite(arrays["body_z"])):
        warnings.append("Body-frame XYZ contains non-finite values.")
    if zero_peak is None:
        warnings.append("Zero peak was not found; ranges were not zero-peak calibrated.")

    invalid_ratio = filtered_nonpositive_range_count / max(point_count_before, 1)
    if invalid_ratio > 0.05:
        warnings.append(f"More than 5% ranges were non-positive before L2 conversion: {invalid_ratio:.2%}.")

    if arrays["range_m"].size == 0 or any("non-finite" in warning for warning in warnings):
        conclusion = "不合理"
        recommendation = "暂停排查：阶段 1 输出为空或包含非有限 XYZ。"
    elif warnings:
        conclusion = "基本合理但有风险"
        recommendation = "建议人工查看局部 XYZ 预览和警告；如形态可接受，再进入阶段 2。"
    else:
        conclusion = "合理"
        recommendation = "可以进入阶段 2：单文件 CH1 的 POS 时间匹配。"

    return Stage1Report(
        stage_name="stage1_l1_to_l2_body_xyz",
        input_l1=str(sample_l1),
        output_l2=str(output_l2),
        preview_html=str(preview_html),
        processed_channel="CH1",
        lidar_time_offset_sec=float(lidar_time_offset_sec),
        point_count_before=int(point_count_before),
        point_count_after=int(arrays["range_m"].size),
        filtered_nonpositive_range_count=int(filtered_nonpositive_range_count),
        gnss_sec_raw=finite_stats(arrays["gnss_sec_raw"]),
        lidar_time_sec=finite_stats(arrays["lidar_time_sec"]),
        raw_dist=finite_stats(arrays["raw_dist"]),
        range_m_before_calibration=raw_range_stats,
        range_m=range_stats,
        scan_angle_deg=finite_stats(arrays["scan_angle_deg"]),
        body_x=x_stats,
        body_y=y_stats,
        body_z=z_stats,
        zero_peak_m=zero_peak,
        channel_calibration=calibration,
        empty_channel_placeholders=["CH2", "CH3", "CH4"],
        known_warnings=warnings,
        conclusion=conclusion,
        recommendation=recommendation,
    )


def write_stage1_markdown(report: Stage1Report, path: Path) -> None:
    warnings = report.known_warnings or ["无"]
    content = f"""# Stage 1 L1 to L2 Body XYZ Report

## Gate Conclusion

- 结论：{report.conclusion}
- 建议：{report.recommendation}
- 阶段：{report.stage_name}
- 处理通道：{report.processed_channel}
- LIDAR 时间修正：`GNSS_SEC_CH1 + {report.lidar_time_offset_sec:g}`

## Inputs and Outputs

- Input L1: `{report.input_l1}`
- Output L2: `{report.output_l2}`
- Preview HTML: `{report.preview_html}`

## Key Statistics

- Point count before filtering: {report.point_count_before:,}
- Point count after filtering: {report.point_count_after:,}
- Non-positive range filtered: {report.filtered_nonpositive_range_count:,}
- GNSS raw seconds: {format_stats(report.gnss_sec_raw)}
- LIDAR time seconds: {format_stats(report.lidar_time_sec)}
- Raw distance counts: {format_stats(report.raw_dist)}
- Range before calibration: {format_stats(report.range_m_before_calibration)}
- Range after calibration: {format_stats(report.range_m)}
- Scan angle degrees: {format_stats(report.scan_angle_deg)}
- Body X: {format_stats(report.body_x)}
- Body Y: {format_stats(report.body_y)}
- Body Z: {format_stats(report.body_z)}
- Zero peak: {report.zero_peak_m}

## Channel Calibration

- CH1 zero_offset: {report.channel_calibration.get('zero_offset')}
- CH1 slope: {report.channel_calibration.get('slope')}
- CH1 intercept: {report.channel_calibration.get('intercept')}
- Empty channel placeholders: {', '.join(report.empty_channel_placeholders)}

## Known Warnings

{chr(10).join(f'- {warning}' for warning in warnings)}

## Gate Rule

Stop here. Do not run Stage 2 until the user manually confirms this Stage 1 result is acceptable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def write_stage2_l2_pos(
    output_path: Path,
    input_l2: Path,
    ch1_points: np.ndarray,
    pos_arrays: dict[str, np.ndarray],
    pos_source: Path,
    pos_time_corrections: int,
    low_confidence_threshold_sec: float,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    input_dtype = ch1_points.dtype
    dtype = np.dtype(input_dtype.descr + [
        ("pos_time_sec", "f8"),
        ("pos_easting", "f8"),
        ("pos_northing", "f8"),
        ("pos_height", "f8"),
        ("pos_roll", "f8"),
        ("pos_pitch", "f8"),
        ("pos_heading", "f8"),
        ("pos_interp_dt", "f8"),
        ("pos_quality_flag", "u2"),
    ])

    output_points = np.empty(ch1_points.shape, dtype=dtype)
    for name in input_dtype.names or []:
        output_points[name] = ch1_points[name]
    for name, values in pos_arrays.items():
        output_points[name] = values

    with h5py.File(input_l2, "r") as src, h5py.File(output_path, "w") as dst:
        l2p = dst.create_group("L2_POS")
        metadata = dst.create_group("metadata")
        channel_params = metadata.create_group("channel_params")
        processing = metadata.create_group("processing")

        write_str_attr(processing, "input_l2", str(input_l2))
        write_str_attr(processing, "pos_source", str(pos_source))
        write_str_attr(processing, "stage", "stage2_pos_matching")
        processing.attrs["pos_time_corrections"] = int(pos_time_corrections)
        processing.attrs["low_confidence_threshold_sec"] = float(low_confidence_threshold_sec)

        if "metadata/channel_params" in src:
            for ch in range(1, 5):
                src_params = src[f"metadata/channel_params/CH{ch}"]
                dst_params = channel_params.create_group(f"CH{ch}")
                for key, value in src_params.attrs.items():
                    dst_params.attrs[key] = value
        else:
            for ch in range(1, 5):
                channel_params.create_group(f"CH{ch}")

        for ch in range(1, 5):
            ch_group = l2p.create_group(f"CH{ch}")
            if ch == 1:
                ch_group.create_dataset("points", data=output_points, compression="gzip", compression_opts=4)
            else:
                ch_group.create_dataset("points", shape=(0,), dtype=dtype)


def build_stage2_report(
    input_l2: Path,
    output_l2_pos: Path,
    pos_source: Path,
    ch1_points: np.ndarray,
    pos_time_sec: np.ndarray,
    pos_arrays: dict[str, np.ndarray],
    pos_time_corrections: int,
    low_confidence_threshold_sec: float,
) -> Stage2Report:
    warnings: list[str] = []
    flags = pos_arrays["pos_quality_flag"]
    no_pos_count = int(np.count_nonzero(flags & 1))
    low_confidence_count = int(np.count_nonzero(flags & 2))
    success_count = int(ch1_points.size - no_pos_count)
    success_rate = success_count / max(int(ch1_points.size), 1)

    if no_pos_count:
        warnings.append(f"{no_pos_count:,} points are outside POS time range.")
    if low_confidence_count:
        warnings.append(f"{low_confidence_count:,} points exceed POS nearest-time threshold.")
    if not np.all(np.isfinite(pos_arrays["pos_easting"][flags == 0])):
        warnings.append("Matched POS easting contains non-finite values for valid points.")
    if success_rate < 0.95:
        warnings.append(f"POS match success rate is below 95%: {success_rate:.2%}.")

    if success_rate < 0.95 or any("non-finite" in warning for warning in warnings):
        conclusion = "不合理"
        recommendation = "暂停排查：POS 匹配成功率或插值结果不满足要求。"
    elif warnings:
        conclusion = "基本合理但有风险"
        recommendation = "建议人工查看 POS 轨迹和匹配统计；如可接受，再进入阶段 3。"
    else:
        conclusion = "合理"
        recommendation = "可以进入阶段 3：单文件 CH1 的地理坐标转换。"

    return Stage2Report(
        stage_name="stage2_pos_matching",
        input_l2=str(input_l2),
        output_l2_pos=str(output_l2_pos),
        pos_source=str(pos_source),
        processed_channel="CH1",
        point_count_before=int(ch1_points.size),
        point_count_after=int(ch1_points.size),
        pos_match_success_count=success_count,
        pos_match_success_rate=float(success_rate),
        no_pos_count=no_pos_count,
        low_confidence_count=low_confidence_count,
        lidar_time_sec=finite_stats(ch1_points["lidar_time_sec"]),
        pos_time_sec=finite_stats(pos_time_sec),
        pos_interp_dt_abs=finite_stats(np.abs(pos_arrays["pos_interp_dt"])),
        pos_easting=finite_stats(pos_arrays["pos_easting"]),
        pos_northing=finite_stats(pos_arrays["pos_northing"]),
        pos_height=finite_stats(pos_arrays["pos_height"]),
        pos_roll=finite_stats(pos_arrays["pos_roll"]),
        pos_pitch=finite_stats(pos_arrays["pos_pitch"]),
        pos_heading=finite_stats(pos_arrays["pos_heading"]),
        pos_time_corrections=pos_time_corrections,
        low_confidence_threshold_sec=low_confidence_threshold_sec,
        empty_channel_placeholders=["CH2", "CH3", "CH4"],
        known_warnings=warnings,
        conclusion=conclusion,
        recommendation=recommendation,
    )


def write_stage2_markdown(report: Stage2Report, path: Path) -> None:
    warnings = report.known_warnings or ["无"]
    content = f"""# Stage 2 POS Matching Report

## Gate Conclusion

- 结论：{report.conclusion}
- 建议：{report.recommendation}
- 阶段：{report.stage_name}
- 处理通道：{report.processed_channel}

## Inputs and Outputs

- Input L2: `{report.input_l2}`
- Output L2 POS: `{report.output_l2_pos}`
- POS source: `{report.pos_source}`

## Key Statistics

- Point count before matching: {report.point_count_before:,}
- Point count after matching: {report.point_count_after:,}
- POS match success count: {report.pos_match_success_count:,}
- POS match success rate: {report.pos_match_success_rate:.6%}
- NO_POS count: {report.no_pos_count:,}
- LOW_CONFIDENCE count: {report.low_confidence_count:,}
- Low-confidence threshold seconds: {report.low_confidence_threshold_sec}
- POS time non-monotonic corrections: {report.pos_time_corrections}
- LIDAR time seconds: {format_stats(report.lidar_time_sec)}
- POS time seconds: {format_stats(report.pos_time_sec)}
- |POS interpolation dt|: {format_stats(report.pos_interp_dt_abs)}
- POS easting: {format_stats(report.pos_easting)}
- POS northing: {format_stats(report.pos_northing)}
- POS height: {format_stats(report.pos_height)}
- POS roll: {format_stats(report.pos_roll)}
- POS pitch: {format_stats(report.pos_pitch)}
- POS heading: {format_stats(report.pos_heading)}
- Empty channel placeholders: {', '.join(report.empty_channel_placeholders)}

## Known Warnings

{chr(10).join(f'- {warning}' for warning in warnings)}

## Gate Rule

Stop here. Do not run Stage 3 until the user manually confirms this Stage 2 result is acceptable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def write_stage3_l3(
    output_path: Path,
    input_l2_pos: Path,
    georef_points: np.ndarray,
    reference_height_bias_m: float,
    range_min_for_georef_m: float,
    crs: str,
    utm_zone: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    with h5py.File(input_l2_pos, "r") as src, h5py.File(output_path, "w") as dst:
        l3 = dst.create_group("L3")
        metadata = dst.create_group("metadata")
        channel_params = metadata.create_group("channel_params")
        processing = metadata.create_group("processing")

        write_str_attr(processing, "input_l2_pos", str(input_l2_pos))
        write_str_attr(processing, "stage", "stage3_georeference_ch1")
        write_str_attr(processing, "crs", crs)
        write_str_attr(processing, "utm_zone", utm_zone)
        write_str_attr(processing, "calibration_status", "engineering_transform_reference_aligned; boresight_lever_arm_pending")
        processing.attrs["reference_height_bias_m"] = float(reference_height_bias_m)
        processing.attrs["range_min_for_georef_m"] = float(range_min_for_georef_m)

        if "metadata/channel_params" in src:
            for ch in range(1, 5):
                src_params = src[f"metadata/channel_params/CH{ch}"]
                dst_params = channel_params.create_group(f"CH{ch}")
                for key, value in src_params.attrs.items():
                    dst_params.attrs[key] = value
        else:
            for ch in range(1, 5):
                channel_params.create_group(f"CH{ch}")

        for ch in range(1, 5):
            ch_group = l3.create_group(f"CH{ch}")
            if ch == 1:
                ch_group.create_dataset("points", data=georef_points, compression="gzip", compression_opts=4)
            else:
                ch_group.create_dataset("points", shape=(0,), dtype=georef_points.dtype)


def make_stage3_preview(
    preview_path: Path,
    easting: np.ndarray,
    northing: np.ndarray,
    height: np.ndarray,
    sample_count: int = 200_000,
    seed: int = 42,
) -> None:
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    count = easting.size
    if count > sample_count:
        rng = np.random.default_rng(seed)
        idx = np.sort(rng.choice(count, size=sample_count, replace=False))
    else:
        idx = np.arange(count)

    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=easting[idx],
                y=northing[idx],
                z=height[idx],
                mode="markers",
                marker={
                    "size": 1.4,
                    "color": height[idx],
                    "colorscale": "Viridis",
                    "opacity": 0.82,
                    "colorbar": {"title": "height_m", "thickness": 14},
                },
                hovertemplate="E: %{x:.3f}<br>N: %{y:.3f}<br>H: %{z:.3f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="Stage 3 CH1 Georeferenced Point Cloud Preview",
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        scene={
            "xaxis_title": "Easting (m, UTM 51N)",
            "yaxis_title": "Northing (m, UTM 51N)",
            "zaxis_title": "Height (m)",
            "aspectmode": "data",
        },
        template="plotly_white",
    )
    fig.write_html(preview_path, include_plotlyjs=True, full_html=True)


def load_reference_l3_stats(reference_l3: Path) -> tuple[RangeStats | None, RangeStats | None, RangeStats | None, float | None]:
    if not reference_l3.exists():
        return None, None, None, None
    with h5py.File(reference_l3, "r") as h5:
        point_x = h5["POINT_X"][:].astype(np.float64)
        point_y = h5["POINT_Y"][:].astype(np.float64)
        point_z = h5["POINT_Z"][:].astype(np.float64)
    return finite_stats(point_x), finite_stats(point_y), finite_stats(point_z), float(np.median(point_z))


def build_stage3_report(
    input_l2_pos: Path,
    output_l3: Path,
    preview_html: Path,
    reference_l3: Path,
    point_count_before: int,
    georef_points: np.ndarray,
    reference_stats: tuple[RangeStats | None, RangeStats | None, RangeStats | None, float | None],
    reference_height_bias_m: float,
    range_min_for_georef_m: float,
    crs: str,
    utm_zone: str,
    qc_preview_html: Path,
) -> Stage3Report:
    warnings: list[str] = []
    ref_x, ref_y, ref_z, _ = reference_stats
    point_count_after = int(georef_points.size)
    height_qc_min = ref_z.minimum if ref_z is not None else None
    height_qc_max = ref_z.maximum if ref_z is not None else None
    if height_qc_min is not None and height_qc_max is not None and point_count_after:
        height = georef_points["height_m"]
        height_qc_mask = (height >= height_qc_min) & (height <= height_qc_max)
        height_qc_inlier_count = int(np.count_nonzero(height_qc_mask))
        height_below_qc_count = int(np.count_nonzero(height < height_qc_min))
        height_above_qc_count = int(np.count_nonzero(height > height_qc_max))
    else:
        height_qc_inlier_count = 0
        height_below_qc_count = 0
        height_above_qc_count = 0
    height_qc_inlier_rate = height_qc_inlier_count / max(point_count_after, 1)

    if point_count_after == 0:
        warnings.append("No points remained after Stage 3 georeference filtering.")
    if height_qc_min is not None and height_qc_max is not None and height_qc_inlier_rate < 0.99:
        warnings.append(
            f"Height QC inlier rate is {height_qc_inlier_rate:.2%}; raw preview contains vertical outliers."
        )
    if abs(reference_height_bias_m) > 1.0:
        warnings.append(
            f"Applied reference height bias {reference_height_bias_m:.3f} m; boresight/lever-arm/range calibration still pending."
        )
    if ref_x is None or ref_y is None or ref_z is None:
        warnings.append("Reference L3 statistics unavailable; cannot compare Stage 3 output to existing L3.")
    else:
        e_stats = finite_stats(georef_points["easting_m"])
        n_stats = finite_stats(georef_points["northing_m"])
        h_stats = finite_stats(georef_points["height_m"])
        if abs(e_stats.mean - ref_y.mean) > 10.0:
            warnings.append("Stage 3 easting mean differs from reference L3 POINT_Y mean by more than 10 m.")
        if abs(n_stats.mean - ref_x.mean) > 10.0:
            warnings.append("Stage 3 northing mean differs from reference L3 POINT_X mean by more than 10 m.")
        if abs(h_stats.mean - ref_z.mean) > 10.0:
            warnings.append("Stage 3 height mean differs from reference L3 POINT_Z mean by more than 10 m.")

    if point_count_after == 0:
        conclusion = "不合理"
        recommendation = "暂停排查：阶段 3 没有生成有效地理点。"
    elif warnings:
        conclusion = "基本合理但有风险"
        recommendation = "建议人工查看地理点云预览和标定警告；如可接受，再进入阶段 4。"
    else:
        conclusion = "合理"
        recommendation = "可以进入阶段 4：连续几个 L1 文件的 CH1 小样本。"

    return Stage3Report(
        stage_name="stage3_georeference_ch1",
        input_l2_pos=str(input_l2_pos),
        output_l3=str(output_l3),
        preview_html=str(preview_html),
        reference_l3=str(reference_l3),
        processed_channel="CH1",
        point_count_before=int(point_count_before),
        point_count_after=point_count_after,
        filtered_count=int(point_count_before - point_count_after),
        range_min_for_georef_m=float(range_min_for_georef_m),
        gps_time=finite_stats(georef_points["gps_time"]),
        north_offset_m=finite_stats(georef_points["north_offset_m"]),
        east_offset_m=finite_stats(georef_points["east_offset_m"]),
        down_offset_m=finite_stats(georef_points["down_offset_m"]),
        easting_m=finite_stats(georef_points["easting_m"]),
        northing_m=finite_stats(georef_points["northing_m"]),
        height_m=finite_stats(georef_points["height_m"]),
        lon=finite_stats(georef_points["lon"]),
        lat=finite_stats(georef_points["lat"]),
        reference_point_x=ref_x,
        reference_point_y=ref_y,
        reference_point_z=ref_z,
        reference_height_bias_m=float(reference_height_bias_m),
        height_qc_min_m=None if height_qc_min is None else float(height_qc_min),
        height_qc_max_m=None if height_qc_max is None else float(height_qc_max),
        height_qc_inlier_count=height_qc_inlier_count,
        height_qc_inlier_rate=float(height_qc_inlier_rate),
        height_below_qc_count=height_below_qc_count,
        height_above_qc_count=height_above_qc_count,
        qc_preview_html=str(qc_preview_html),
        crs=crs,
        utm_zone=utm_zone,
        calibration_status="engineering_transform_reference_aligned; boresight_lever_arm_pending",
        empty_channel_placeholders=["CH2", "CH3", "CH4"],
        known_warnings=warnings,
        conclusion=conclusion,
        recommendation=recommendation,
    )


def write_stage3_markdown(report: Stage3Report, path: Path) -> None:
    warnings = report.known_warnings or ["无"]
    content = f"""# Stage 3 Georeference CH1 Report

## Gate Conclusion

- 结论：{report.conclusion}
- 建议：{report.recommendation}
- 阶段：{report.stage_name}
- 处理通道：{report.processed_channel}
- 坐标系：{report.crs}
- UTM 分区：{report.utm_zone}
- 标定状态：{report.calibration_status}

## Inputs and Outputs

- Input L2 POS: `{report.input_l2_pos}`
- Output L3: `{report.output_l3}`
- Raw Preview HTML: `{report.preview_html}`
- Height-QC Preview HTML: `{report.qc_preview_html}`
- Reference L3: `{report.reference_l3}`

## Key Statistics

- Point count before georeference filtering: {report.point_count_before:,}
- Point count after georeference filtering: {report.point_count_after:,}
- Filtered count: {report.filtered_count:,}
- Range minimum for georeference: {report.range_min_for_georef_m} m
- Reference height bias: {report.reference_height_bias_m:.6f} m
- Height QC range from reference L3: {report.height_qc_min_m} m to {report.height_qc_max_m} m
- Height QC inliers: {report.height_qc_inlier_count:,} ({report.height_qc_inlier_rate:.6%})
- Height below QC range: {report.height_below_qc_count:,}
- Height above QC range: {report.height_above_qc_count:,}
- GPS time: {format_stats(report.gps_time)}
- North offset: {format_stats(report.north_offset_m)}
- East offset: {format_stats(report.east_offset_m)}
- Down offset: {format_stats(report.down_offset_m)}
- Easting: {format_stats(report.easting_m)}
- Northing: {format_stats(report.northing_m)}
- Height: {format_stats(report.height_m)}
- Longitude: {format_stats(report.lon)}
- Latitude: {format_stats(report.lat)}
- Reference POINT_X: {format_stats(report.reference_point_x)}
- Reference POINT_Y: {format_stats(report.reference_point_y)}
- Reference POINT_Z: {format_stats(report.reference_point_z)}
- Empty channel placeholders: {', '.join(report.empty_channel_placeholders)}

## Known Warnings

{chr(10).join(f'- {warning}' for warning in warnings)}

## Gate Rule

Stop here. Do not run Stage 4 until the user manually confirms this Stage 3 result is acceptable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def write_stage4_merged_l3(output_path: Path, source_paths: list[Path]) -> np.ndarray:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    arrays = []
    for path in source_paths:
        with h5py.File(path, "r") as h5:
            arrays.append(h5["L3/CH1/points"][:])
    merged = np.concatenate(arrays) if arrays else np.array([], dtype=[])

    with h5py.File(output_path, "w") as h5:
        l3 = h5.create_group("L3")
        metadata = h5.create_group("metadata")
        processing = metadata.create_group("processing")
        write_str_attr(processing, "stage", "stage4_continuous_ch1_sample_merge")
        write_str_attr(processing, "source_l3_files", json.dumps([str(path) for path in source_paths], ensure_ascii=False))
        for ch in range(1, 5):
            ch_group = l3.create_group(f"CH{ch}")
            if ch == 1:
                ch_group.create_dataset("points", data=merged, compression="gzip", compression_opts=4)
            else:
                ch_group.create_dataset("points", shape=(0,), dtype=merged.dtype)
    return merged


def write_stage4_markdown(report: Stage4Report, path: Path) -> None:
    warnings = report.known_warnings or ["无"]
    table_rows = []
    for item in report.file_summaries:
        table_rows.append(
            "| "
            + " | ".join(
                [
                    Path(item.input_l1).name,
                    str(item.skipped),
                    item.skip_reason or "无",
                    f"{item.point_count_l2:,}",
                    f"{item.point_count_l3:,}",
                    f"{item.gps_time_min:.6f}",
                    f"{item.gps_time_max:.6f}",
                    f"{item.easting_mean:.3f}",
                    f"{item.northing_mean:.3f}",
                    f"{item.height_median:.3f}",
                    item.conclusion,
                    "; ".join(item.warnings) if item.warnings else "无",
                ]
            )
            + " |"
        )

    content = f"""# Stage 4 Continuous CH1 Sample Report

## Gate Conclusion

- 结论：{report.conclusion}
- 建议：{report.recommendation}
- 阶段：{report.stage_name}
- 处理通道：{report.processed_channel}

## Outputs

- Merged L3: `{report.output_l3_merged}`
- Preview HTML: `{report.preview_html}`

## Summary

- Input files: {len(report.input_files)}
- Total L2 points: {report.total_l2_points:,}
- Total L3 points: {report.total_l3_points:,}
- Time gaps between files seconds: {report.time_gap_seconds}
- Merged GPS time: {format_stats(report.merged_gps_time)}
- Merged Easting: {format_stats(report.merged_easting)}
- Merged Northing: {format_stats(report.merged_northing)}
- Merged Height: {format_stats(report.merged_height)}
- Merged Longitude: {format_stats(report.merged_lon)}
- Merged Latitude: {format_stats(report.merged_lat)}

## Per-file Summary

| File | Skipped | Skip reason | L2 points | L3 points | GPS min | GPS max | Easting mean | Northing mean | Height median | Conclusion | Warnings |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
{chr(10).join(table_rows)}

## Known Warnings

{chr(10).join(f'- {warning}' for warning in warnings)}

## Gate Rule

Stop here. Do not run Stage 5 until the user manually confirms this Stage 4 result is acceptable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def robust_percentile_filter(values: np.ndarray, low: float, high: float) -> np.ndarray:
    if values.size == 0:
        return np.zeros(0, dtype=bool)
    lo, hi = np.percentile(values[np.isfinite(values)], [low, high])
    return (values >= lo) & (values <= hi)


def compute_pca_angle_deg(x: np.ndarray, y: np.ndarray) -> float:
    if x.size < 10:
        return 0.0
    xy = np.column_stack([x - np.mean(x), y - np.mean(y)])
    cov = np.cov(xy, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    vec = eigvecs[:, int(np.argmax(eigvals))]
    return float(np.rad2deg(np.arctan2(vec[1], vec[0])))


def derive_stage35_model(
    source_points: np.ndarray,
    reference_l3: Path,
    apply_z_scale: bool = False,
    apply_rotation: bool = False,
) -> Stage35Model:
    with h5py.File(reference_l3, "r") as h5:
        ref_northing = h5["POINT_X"][:].astype(np.float64)
        ref_easting = h5["POINT_Y"][:].astype(np.float64)
        ref_height = h5["POINT_Z"][:].astype(np.float64)

    src_easting = source_points["easting_m"].astype(np.float64)
    src_northing = source_points["northing_m"].astype(np.float64)
    src_height = source_points["height_m"].astype(np.float64)

    src_height_mask = robust_percentile_filter(src_height, 1, 99)
    src_space_mask = robust_percentile_filter(src_easting, 1, 99) & robust_percentile_filter(src_northing, 1, 99)
    src_mask = src_height_mask & src_space_mask
    if np.count_nonzero(src_mask) < 100:
        src_mask = np.isfinite(src_easting) & np.isfinite(src_northing) & np.isfinite(src_height)

    ref_mask = (
        np.isfinite(ref_easting)
        & np.isfinite(ref_northing)
        & np.isfinite(ref_height)
        & robust_percentile_filter(ref_height, 1, 99)
    )

    ref_e_med = float(np.median(ref_easting[ref_mask]))
    ref_n_med = float(np.median(ref_northing[ref_mask]))
    ref_h_med = float(np.median(ref_height[ref_mask]))
    src_e_med = float(np.median(src_easting[src_mask]))
    src_n_med = float(np.median(src_northing[src_mask]))
    src_h_med = float(np.median(src_height[src_mask]))

    ref_iqr = float(np.percentile(ref_height[ref_mask], 75) - np.percentile(ref_height[ref_mask], 25))
    src_iqr = float(np.percentile(src_height[src_mask], 75) - np.percentile(src_height[src_mask], 25))
    z_scale = ref_iqr / src_iqr if src_iqr > 1e-9 else 1.0

    ref_angle = compute_pca_angle_deg(ref_easting[ref_mask], ref_northing[ref_mask])
    src_angle = compute_pca_angle_deg(src_easting[src_mask], src_northing[src_mask])
    rotation_deg = ref_angle - src_angle
    if rotation_deg > 90:
        rotation_deg -= 180
    if rotation_deg < -90:
        rotation_deg += 180

    return Stage35Model(
        dx_m=ref_e_med - src_e_med,
        dy_m=ref_n_med - src_n_med,
        dz_m=ref_h_med - src_h_med,
        z_scale=float(z_scale),
        rotation_deg=float(rotation_deg),
        apply_z_scale=apply_z_scale,
        apply_rotation=apply_rotation,
        reference_easting_median=ref_e_med,
        reference_northing_median=ref_n_med,
        reference_height_median=ref_h_med,
        source_easting_median=src_e_med,
        source_northing_median=src_n_med,
        source_height_median=src_h_med,
    )


def apply_stage35_model(points: np.ndarray, model: Stage35Model) -> np.ndarray:
    calibrated = points.copy()
    easting = calibrated["easting_m"].astype(np.float64)
    northing = calibrated["northing_m"].astype(np.float64)
    height = calibrated["height_m"].astype(np.float64)

    if model.apply_rotation:
        angle = np.deg2rad(model.rotation_deg)
        ce = np.cos(angle)
        se = np.sin(angle)
        e0 = model.source_easting_median
        n0 = model.source_northing_median
        de = easting - e0
        dn = northing - n0
        easting = e0 + ce * de - se * dn
        northing = n0 + se * de + ce * dn

    easting = easting + model.dx_m
    northing = northing + model.dy_m
    if model.apply_z_scale:
        height = model.reference_height_median + (height - model.source_height_median) * model.z_scale
    else:
        height = height + model.dz_m

    transformer = Transformer.from_crs("EPSG:32651", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(easting, northing)
    calibrated["easting_m"] = easting
    calibrated["northing_m"] = northing
    calibrated["height_m"] = height
    calibrated["lon"] = lon
    calibrated["lat"] = lat
    return calibrated


def height_qc_mask(points: np.ndarray, reference_l3: Path, margin_m: float = 30.0) -> np.ndarray:
    with h5py.File(reference_l3, "r") as h5:
        ref_height = h5["POINT_Z"][:].astype(np.float64)
    lo = float(np.percentile(ref_height, 1) - margin_m)
    hi = float(np.percentile(ref_height, 99) + margin_m)
    height = points["height_m"]
    return np.isfinite(height) & (height >= lo) & (height <= hi) & np.isfinite(points["easting_m"]) & np.isfinite(points["northing_m"])


def write_calibrated_l3(output_path: Path, source_path: Path, calibrated_points: np.ndarray, model: Stage35Model) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    with h5py.File(source_path, "r") as src, h5py.File(output_path, "w") as dst:
        l3 = dst.create_group("L3_CALIBRATED")
        metadata = dst.create_group("metadata")
        processing = metadata.create_group("processing")
        write_str_attr(processing, "source_l3", str(source_path))
        write_str_attr(processing, "stage", "stage35_empirical_calibration")
        processing.attrs["dx_m"] = model.dx_m
        processing.attrs["dy_m"] = model.dy_m
        processing.attrs["dz_m"] = model.dz_m
        processing.attrs["z_scale"] = model.z_scale
        processing.attrs["rotation_deg"] = model.rotation_deg
        processing.attrs["apply_z_scale"] = model.apply_z_scale
        processing.attrs["apply_rotation"] = model.apply_rotation
        for ch in range(1, 5):
            ch_group = l3.create_group(f"CH{ch}")
            if ch == 1:
                ch_group.create_dataset("points", data=calibrated_points, compression="gzip", compression_opts=4)
            else:
                ch_group.create_dataset("points", shape=(0,), dtype=calibrated_points.dtype)


def write_stage35_markdown(report: Stage35Report, path: Path) -> None:
    warnings = report.known_warnings or ["无"]
    rows = []
    for item in report.file_summaries:
        rows.append(
            "| "
            + " | ".join(
                [
                    Path(item.input_l2_pos).name,
                    str(item.skipped),
                    item.skip_reason or "无",
                    f"{item.point_count_after:,}",
                    f"{item.gps_time_min:.6f}" if item.gps_time_min is not None else "N/A",
                    f"{item.gps_time_max:.6f}" if item.gps_time_max is not None else "N/A",
                    f"{item.easting_mean:.3f}" if item.easting_mean is not None else "N/A",
                    f"{item.northing_mean:.3f}" if item.northing_mean is not None else "N/A",
                    f"{item.height_median:.3f}" if item.height_median is not None else "N/A",
                    f"{item.height_min:.3f}" if item.height_min is not None else "N/A",
                    f"{item.height_max:.3f}" if item.height_max is not None else "N/A",
                ]
            )
            + " |"
        )

    content = f"""# Stage 3.5 Empirical Calibration Report

## Gate Conclusion

- 结论：{report.conclusion}
- 建议：{report.recommendation}
- 阶段：{report.stage_name}

## Calibration Model

- dx_m: {report.model.dx_m:.6f}
- dy_m: {report.model.dy_m:.6f}
- dz_m: {report.model.dz_m:.6f}
- z_scale: {report.model.z_scale:.6f}
- rotation_deg: {report.model.rotation_deg:.6f}
- apply_z_scale: {report.model.apply_z_scale}
- apply_rotation: {report.model.apply_rotation}
- reference median E/N/H: {report.model.reference_easting_median:.3f}, {report.model.reference_northing_median:.3f}, {report.model.reference_height_median:.3f}
- source median E/N/H: {report.model.source_easting_median:.3f}, {report.model.source_northing_median:.3f}, {report.model.source_height_median:.3f}

## Outputs

- Calibration model JSON: `{report.calibration_model_path}`
- Sample calibrated L3: `{report.sample_output_l3_calibrated}`
- Sample preview HTML: `{report.sample_preview_html}`
- Continuous calibrated merged L3: `{report.continuous_output_l3_merged}`
- Continuous preview HTML: `{report.continuous_preview_html}`

## Merged Summary

- Merged point count: {report.merged_point_count:,}
- Merged GPS time: {format_stats(report.merged_gps_time)}
- Merged Easting: {format_stats(report.merged_easting)}
- Merged Northing: {format_stats(report.merged_northing)}
- Merged Height: {format_stats(report.merged_height)}

## Per-file Summary

| File | Skipped | Reason | Points | GPS min | GPS max | Easting mean | Northing mean | Height median | Height min | Height max |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Known Warnings

{chr(10).join(f'- {warning}' for warning in warnings)}

## Gate Rule

Stop here. Do not run Stage 4/5 until the user manually confirms this Stage 3.5 result is acceptable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run_stage1(args: argparse.Namespace) -> Stage1Report:
    calibration = load_channel_calibration(args.calib_coeffs, "ch1")

    with h5py.File(args.sample_l1, "r") as h5:
        gnss = h5["GNSS_SEC_CH1"][:].astype(np.float64)
        raw_dist = h5["Photon_CH1_DIST"][:].astype(np.uint32)
        coder = h5["Photon_CH1_CODER"][:].astype(np.float64)
        pulse_index = h5["PULSE_INDEX_CH1"][:].astype(np.uint32)
        pulse_circle = h5["PULSE_CIRCLE_CH1"][:].astype(np.uint32)

    point_count_before = int(raw_dist.size)
    dist_factor = 2e-9 / 256.0 * 3e8 / 2.0
    range_before_calibration = raw_dist.astype(np.float64) * dist_factor
    positive_mask = range_before_calibration > 0
    filtered_nonpositive = int(np.count_nonzero(~positive_mask))

    gnss = gnss[positive_mask]
    raw_dist = raw_dist[positive_mask]
    coder = coder[positive_mask]
    pulse_index = pulse_index[positive_mask]
    pulse_circle = pulse_circle[positive_mask]
    range_before_calibration = range_before_calibration[positive_mask]

    range_m, zero_peak = calibrate_ranges(range_before_calibration, calibration)
    scan_angle_deg = coder * 360.0 / 65536.0
    body_x, body_y, body_z = f_body_frame_xyz(range_m, 360.0 - scan_angle_deg)

    arrays = {
        "gnss_sec_raw": gnss,
        "lidar_time_sec": gnss + args.lidar_time_offset_sec,
        "raw_dist": raw_dist,
        "range_m_before_calibration": range_before_calibration,
        "range_m": range_m,
        "coder": coder,
        "scan_angle_deg": scan_angle_deg,
        "pulse_index": pulse_index,
        "pulse_circle": pulse_circle,
        "body_x": body_x,
        "body_y": body_y,
        "body_z": body_z,
        "quality_flag": np.zeros(range_m.size, dtype=np.uint16),
    }

    output_l2 = default_l2_path(args.l2_dir, args.sample_l1)
    preview_html = args.preview_dir / f"stage1_ch1_body_xyz_{cap_id_from_l1_path(args.sample_l1)}.html"
    write_stage1_l2(output_l2, args.sample_l1, arrays, calibration, zero_peak, args.lidar_time_offset_sec)
    make_stage1_preview(preview_html, body_x, body_y, body_z, range_m)

    report = build_stage1_report(
        sample_l1=args.sample_l1,
        output_l2=output_l2,
        preview_html=preview_html,
        calibration=calibration,
        zero_peak=zero_peak,
        point_count_before=point_count_before,
        filtered_nonpositive_range_count=filtered_nonpositive,
        arrays=arrays,
        lidar_time_offset_sec=args.lidar_time_offset_sec,
    )

    reports_dir = args.metadata_dir / "stage_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage1_l2_body_xyz_report.json"
    md_path = reports_dir / "stage1_l2_body_xyz_report.md"
    json_path.write_text(
        json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_stage1_markdown(report, md_path)

    print(f"Stage 1 conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"L2 output: {output_l2.resolve()}")
    print(f"Preview HTML: {preview_html.resolve()}")
    print(f"Markdown report: {md_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return report


def run_stage2(args: argparse.Namespace) -> Stage2Report:
    input_l2 = args.input_l2
    output_l2_pos = default_l2_pos_path(args.l2_pos_dir, input_l2)

    with h5py.File(input_l2, "r") as h5:
        ch1_points = h5["L2/CH1/points"][:]

    pos = load_pos_mat(args.pos_source)
    missing = [field for field in POS_REQUIRED_FIELDS if field not in pos]
    if missing:
        raise ValueError(f"POS source is missing required fields: {', '.join(missing)}")

    pos_time_sec, corrections = process_pos_time_seconds(pos["TIME"])
    sort_idx = np.argsort(pos_time_sec)
    pos_time_sec = pos_time_sec[sort_idx]

    lidar_time = ch1_points["lidar_time_sec"].astype(np.float64)
    no_pos = (lidar_time < pos_time_sec[0]) | (lidar_time > pos_time_sec[-1])
    nearest_dt = nearest_time_delta_abs(pos_time_sec, np.clip(lidar_time, pos_time_sec[0], pos_time_sec[-1]))
    low_confidence = nearest_dt > args.pos_low_confidence_threshold_sec

    pos_quality_flag = np.zeros(ch1_points.size, dtype=np.uint16)
    pos_quality_flag[no_pos] |= 1
    pos_quality_flag[low_confidence] |= 2

    interp_time = np.clip(lidar_time, pos_time_sec[0], pos_time_sec[-1])
    pos_arrays = {
        "pos_time_sec": interp_time.astype(np.float64),
        "pos_easting": np.interp(interp_time, pos_time_sec, np.asarray(pos["EASTING"], dtype=np.float64).reshape(-1)[sort_idx]),
        "pos_northing": np.interp(interp_time, pos_time_sec, np.asarray(pos["NORTHING"], dtype=np.float64).reshape(-1)[sort_idx]),
        "pos_height": np.interp(interp_time, pos_time_sec, np.asarray(pos["HEIGHT"], dtype=np.float64).reshape(-1)[sort_idx]),
        "pos_roll": np.interp(interp_time, pos_time_sec, np.asarray(pos["ROLL"], dtype=np.float64).reshape(-1)[sort_idx]),
        "pos_pitch": np.interp(interp_time, pos_time_sec, np.asarray(pos["PITCH"], dtype=np.float64).reshape(-1)[sort_idx]),
        "pos_heading": interp_heading_deg(pos_time_sec, np.asarray(pos["HEADING"], dtype=np.float64).reshape(-1)[sort_idx], interp_time),
        "pos_interp_dt": nearest_dt.astype(np.float64),
        "pos_quality_flag": pos_quality_flag,
    }

    write_stage2_l2_pos(
        output_l2_pos,
        input_l2,
        ch1_points,
        pos_arrays,
        args.pos_source,
        corrections,
        args.pos_low_confidence_threshold_sec,
    )

    report = build_stage2_report(
        input_l2=input_l2,
        output_l2_pos=output_l2_pos,
        pos_source=args.pos_source,
        ch1_points=ch1_points,
        pos_time_sec=pos_time_sec,
        pos_arrays=pos_arrays,
        pos_time_corrections=corrections,
        low_confidence_threshold_sec=args.pos_low_confidence_threshold_sec,
    )

    reports_dir = args.metadata_dir / "stage_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage2_pos_matching_report.json"
    md_path = reports_dir / "stage2_pos_matching_report.md"
    json_path.write_text(
        json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_stage2_markdown(report, md_path)

    print(f"Stage 2 conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"L2 POS output: {output_l2_pos.resolve()}")
    print(f"Markdown report: {md_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return report


def run_stage3(args: argparse.Namespace) -> Stage3Report:
    input_l2_pos = args.input_l2_pos
    output_l3 = default_l3_path(args.l3_dir, input_l2_pos)
    preview_html = args.preview_dir / f"stage3_ch1_georef_{cap_id_from_l1_path(input_l2_pos)}.html"
    qc_preview_html = args.preview_dir / "stage3_ch1_georef_height_qc_preview.html"
    crs = "EPSG:32651"
    utm_zone = "51N/51R"

    with h5py.File(input_l2_pos, "r") as h5:
        points = h5["L2_POS/CH1/points"][:]

    point_count_before = int(points.size)
    valid = (points["pos_quality_flag"] == 0) & (points["range_m"] > args.stage3_range_min_m)
    valid_points = points[valid]
    north_offset, east_offset, down_offset = body_to_ned_offsets(valid_points)

    ref_stats = load_reference_l3_stats(args.reference_l3)
    _, _, _, reference_median_height = ref_stats
    raw_height = valid_points["pos_height"] - down_offset
    if reference_median_height is not None and raw_height.size:
        reference_height_bias = float(reference_median_height - np.median(raw_height))
    else:
        reference_height_bias = 0.0

    height = raw_height + reference_height_bias
    easting = valid_points["pos_easting"] + east_offset
    northing = valid_points["pos_northing"] + north_offset
    transformer = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(easting, northing)

    dtype = np.dtype(
        [
            ("source_file_id", "u2"),
            ("channel", "u1"),
            ("pulse_index", "u4"),
            ("pulse_circle", "u4"),
            ("gps_time", "f8"),
            ("range_m", "f8"),
            ("scan_angle_deg", "f8"),
            ("north_offset_m", "f8"),
            ("east_offset_m", "f8"),
            ("down_offset_m", "f8"),
            ("easting_m", "f8"),
            ("northing_m", "f8"),
            ("height_m", "f8"),
            ("lon", "f8"),
            ("lat", "f8"),
            ("pos_easting", "f8"),
            ("pos_northing", "f8"),
            ("pos_height", "f8"),
            ("pos_roll", "f8"),
            ("pos_pitch", "f8"),
            ("pos_heading", "f8"),
            ("quality_flag", "u2"),
            ("pos_quality_flag", "u2"),
        ]
    )
    georef_points = np.empty(valid_points.size, dtype=dtype)
    georef_points["source_file_id"] = valid_points["source_file_id"]
    georef_points["channel"] = valid_points["channel"]
    georef_points["pulse_index"] = valid_points["pulse_index"]
    georef_points["pulse_circle"] = valid_points["pulse_circle"]
    georef_points["gps_time"] = valid_points["lidar_time_sec"]
    georef_points["range_m"] = valid_points["range_m"]
    georef_points["scan_angle_deg"] = valid_points["scan_angle_deg"]
    georef_points["north_offset_m"] = north_offset
    georef_points["east_offset_m"] = east_offset
    georef_points["down_offset_m"] = down_offset
    georef_points["easting_m"] = easting
    georef_points["northing_m"] = northing
    georef_points["height_m"] = height
    georef_points["lon"] = lon
    georef_points["lat"] = lat
    georef_points["pos_easting"] = valid_points["pos_easting"]
    georef_points["pos_northing"] = valid_points["pos_northing"]
    georef_points["pos_height"] = valid_points["pos_height"]
    georef_points["pos_roll"] = valid_points["pos_roll"]
    georef_points["pos_pitch"] = valid_points["pos_pitch"]
    georef_points["pos_heading"] = valid_points["pos_heading"]
    georef_points["quality_flag"] = valid_points["quality_flag"]
    georef_points["pos_quality_flag"] = valid_points["pos_quality_flag"]

    write_stage3_l3(
        output_l3,
        input_l2_pos,
        georef_points,
        reference_height_bias,
        args.stage3_range_min_m,
        crs,
        utm_zone,
    )
    make_stage3_preview(preview_html, easting, northing, height)
    ref_stats = load_reference_l3_stats(args.reference_l3)
    ref_x, ref_y, ref_z, _ = ref_stats
    if ref_z is not None:
        height_qc_mask = (height >= ref_z.minimum) & (height <= ref_z.maximum)
        make_stage3_preview(
            qc_preview_html,
            easting[height_qc_mask],
            northing[height_qc_mask],
            height[height_qc_mask],
        )
    else:
        make_stage3_preview(qc_preview_html, easting, northing, height)

    report = build_stage3_report(
        input_l2_pos=input_l2_pos,
        output_l3=output_l3,
        preview_html=preview_html,
        reference_l3=args.reference_l3,
        point_count_before=point_count_before,
        georef_points=georef_points,
        reference_stats=ref_stats,
        reference_height_bias_m=reference_height_bias,
        range_min_for_georef_m=args.stage3_range_min_m,
        crs=crs,
        utm_zone=utm_zone,
        qc_preview_html=qc_preview_html,
    )

    reports_dir = args.metadata_dir / "stage_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage3_georeference_report.json"
    md_path = reports_dir / "stage3_georeference_report.md"
    json_path.write_text(
        json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_stage3_markdown(report, md_path)

    print(f"Stage 3 conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"L3 output: {output_l3.resolve()}")
    print(f"Preview HTML: {preview_html.resolve()}")
    print(f"Markdown report: {md_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return report


def parse_l1_file_list(raw_values: list[str] | None) -> list[Path]:
    if not raw_values:
        return DEFAULT_CONTINUOUS_L1_FILES
    result: list[Path] = []
    for value in raw_values:
        for part in value.split(","):
            cleaned = part.strip()
            if cleaned:
                result.append(Path(cleaned))
    return result


def run_stage4(args: argparse.Namespace) -> Stage4Report:
    l1_files = parse_l1_file_list(args.stage4_l1_files)
    file_summaries: list[Stage4FileSummary] = []
    l3_paths: list[Path] = []
    all_warnings: list[str] = []

    for l1_path in l1_files:
        print(f"Stage 4 processing {l1_path}")
        args.sample_l1 = l1_path
        stage1 = run_stage1(args)
        args.input_l2 = Path(stage1.output_l2)
        stage2 = run_stage2(args)
        args.input_l2_pos = Path(stage2.output_l2_pos)
        if stage2.pos_match_success_rate < 0.95:
            skip_reason = (
                f"POS match success rate below 95% ({stage2.pos_match_success_rate:.2%}); "
                "likely invalid L1 GNSS time."
            )
            all_warnings.append(f"{l1_path.name}: skipped. {skip_reason}")
            file_summaries.append(
                Stage4FileSummary(
                    input_l1=str(l1_path),
                    output_l2=stage1.output_l2,
                    output_l2_pos=stage2.output_l2_pos,
                    output_l3="",
                    point_count_l2=stage1.point_count_after,
                    point_count_l3=0,
                    gps_time_min=float("nan"),
                    gps_time_max=float("nan"),
                    easting_mean=float("nan"),
                    northing_mean=float("nan"),
                    height_median=float("nan"),
                    conclusion="不合理",
                    warnings=stage1.known_warnings + stage2.known_warnings + [skip_reason],
                    skipped=True,
                    skip_reason=skip_reason,
                )
            )
            continue

        stage3 = run_stage3(args)
        l3_path = Path(stage3.output_l3)
        l3_paths.append(l3_path)

        warnings = stage1.known_warnings + stage2.known_warnings + stage3.known_warnings
        all_warnings.extend([f"{l1_path.name}: {warning}" for warning in warnings])
        file_summaries.append(
            Stage4FileSummary(
                input_l1=str(l1_path),
                output_l2=stage1.output_l2,
                output_l2_pos=stage2.output_l2_pos,
                output_l3=stage3.output_l3,
                point_count_l2=stage1.point_count_after,
                point_count_l3=stage3.point_count_after,
                gps_time_min=stage3.gps_time.minimum,
                gps_time_max=stage3.gps_time.maximum,
                easting_mean=stage3.easting_m.mean,
                northing_mean=stage3.northing_m.mean,
                height_median=float(np.nan),
                conclusion=stage3.conclusion,
                warnings=warnings,
                skipped=False,
                skip_reason="",
            )
        )

    merged_l3_path = args.l3_dir / "L3_CH1_continuous_cap_00111_00115.h5"
    merged = write_stage4_merged_l3(merged_l3_path, l3_paths)
    preview_html = args.preview_dir / "stage4_ch1_continuous_georef_preview.html"
    if merged.size:
        make_stage3_preview(preview_html, merged["easting_m"], merged["northing_m"], merged["height_m"])
    else:
        preview_html.parent.mkdir(parents=True, exist_ok=True)
        preview_html.write_text("<html><body>No points</body></html>", encoding="utf-8")

    # Fill medians after merged dtype is known and per-file data are readable.
    for item in file_summaries:
        if item.skipped or not item.output_l3:
            continue
        with h5py.File(item.output_l3, "r") as h5:
            pts = h5["L3/CH1/points"]
            item.height_median = float(np.median(pts["height_m"][:])) if pts.shape[0] else float("nan")

    time_gap_seconds: list[float] = []
    valid_summaries = [item for item in file_summaries if not item.skipped and np.isfinite(item.gps_time_min)]
    sorted_summaries = sorted(valid_summaries, key=lambda item: item.gps_time_min)
    for prev, current in zip(sorted_summaries, sorted_summaries[1:]):
        time_gap_seconds.append(float(current.gps_time_min - prev.gps_time_max))

    if merged.size == 0:
        conclusion = "不合理"
        recommendation = "暂停排查：连续小样本没有生成有效 L3 点。"
    elif any(abs(gap) > 0.5 for gap in time_gap_seconds):
        conclusion = "基本合理但有风险"
        recommendation = "连续文件存在超过 0.5 秒的时间间隔；建议人工查看接缝后再进入阶段 5。"
        all_warnings.append("Time gap larger than 0.5 seconds detected between continuous files.")
    elif all_warnings:
        conclusion = "基本合理但有风险"
        recommendation = "建议人工查看合并预览和警告；如形态连续，再进入阶段 5。"
    else:
        conclusion = "合理"
        recommendation = "可以进入阶段 5：扩展到所有 L1 文件的 CH1。"

    report = Stage4Report(
        stage_name="stage4_continuous_ch1_sample",
        processed_channel="CH1",
        input_files=[str(path) for path in l1_files],
        output_l3_merged=str(merged_l3_path),
        preview_html=str(preview_html),
        file_summaries=file_summaries,
        total_l2_points=int(sum(item.point_count_l2 for item in file_summaries)),
        total_l3_points=int(merged.size),
        time_gap_seconds=time_gap_seconds,
        merged_gps_time=finite_stats(merged["gps_time"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_easting=finite_stats(merged["easting_m"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_northing=finite_stats(merged["northing_m"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_height=finite_stats(merged["height_m"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_lon=finite_stats(merged["lon"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_lat=finite_stats(merged["lat"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        known_warnings=all_warnings,
        conclusion=conclusion,
        recommendation=recommendation,
    )

    reports_dir = args.metadata_dir / "stage_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage4_continuous_ch1_report.json"
    md_path = reports_dir / "stage4_continuous_ch1_report.md"
    json_path.write_text(
        json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_stage4_markdown(report, md_path)

    print(f"Stage 4 conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Merged L3 output: {merged_l3_path.resolve()}")
    print(f"Preview HTML: {preview_html.resolve()}")
    print(f"Markdown report: {md_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return report


def run_stage35(args: argparse.Namespace) -> Stage35Report:
    sample_l3 = default_l3_path(args.l3_dir, args.input_l2_pos)
    if not sample_l3.exists():
        args.input_l2_pos = DEFAULT_STAGE2_L2_POS
        stage3 = run_stage3(args)
        sample_l3 = Path(stage3.output_l3)

    with h5py.File(sample_l3, "r") as h5:
        sample_points = h5["L3/CH1/points"][:]

    model = derive_stage35_model(
        sample_points,
        args.reference_l3,
        apply_z_scale=args.stage35_apply_z_scale,
        apply_rotation=args.stage35_apply_rotation,
    )

    model_path = args.metadata_dir / "stage_reports" / "stage35_empirical_model.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(json.dumps(dataclass_to_jsonable(model), ensure_ascii=False, indent=2), encoding="utf-8-sig")

    l1_files = parse_l1_file_list(args.stage4_l1_files)
    summaries: list[Stage35FileSummary] = []
    calibrated_paths: list[Path] = []
    warnings: list[str] = [
        "Stage 3.5 is empirical alignment against the existing L3 sample; it is not a substitute for final boresight/lever-arm calibration."
    ]

    for l1_path in l1_files:
        l2_path = default_l2_path(args.l2_dir, l1_path)
        l2p_path = default_l2_pos_path(args.l2_pos_dir, l2_path)
        l3_path = default_l3_path(args.l3_dir, l2p_path)
        cap_id = cap_id_from_l1_path(l1_path)
        out_path = args.l3_dir / f"L3C_CH1_{cap_id}.h5"

        if not l3_path.exists():
            args.sample_l1 = l1_path
            stage1 = run_stage1(args)
            args.input_l2 = Path(stage1.output_l2)
            stage2 = run_stage2(args)
            args.input_l2_pos = Path(stage2.output_l2_pos)
            stage3 = run_stage3(args)
            l3_path = Path(stage3.output_l3)

        with h5py.File(l2p_path, "r") as h5:
            l2p_points = h5["L2_POS/CH1/points"][:]
            flags = l2p_points["pos_quality_flag"]
            success_rate = float(np.mean(flags == 0)) if flags.size else 0.0

        if success_rate < 0.95:
            reason = f"POS match success rate below 95% ({success_rate:.2%}); likely invalid L1 GNSS time."
            warnings.append(f"{l1_path.name}: skipped. {reason}")
            summaries.append(
                Stage35FileSummary(
                    input_l2_pos=str(l2p_path),
                    output_l3_calibrated=str(out_path),
                    point_count_before=int(flags.size),
                    point_count_after=0,
                    skipped=True,
                    skip_reason=reason,
                    gps_time_min=None,
                    gps_time_max=None,
                    easting_mean=None,
                    northing_mean=None,
                    height_median=None,
                    height_min=None,
                    height_max=None,
                )
            )
            continue

        with h5py.File(l3_path, "r") as h5:
            points = h5["L3/CH1/points"][:]
        calibrated = apply_stage35_model(points, model)
        mask = height_qc_mask(calibrated, args.reference_l3, margin_m=args.stage35_height_margin_m)
        calibrated = calibrated[mask]
        write_calibrated_l3(out_path, l3_path, calibrated, model)
        calibrated_paths.append(out_path)

        summaries.append(
            Stage35FileSummary(
                input_l2_pos=str(l2p_path),
                output_l3_calibrated=str(out_path),
                point_count_before=int(points.size),
                point_count_after=int(calibrated.size),
                skipped=False,
                skip_reason="",
                gps_time_min=float(np.min(calibrated["gps_time"])) if calibrated.size else None,
                gps_time_max=float(np.max(calibrated["gps_time"])) if calibrated.size else None,
                easting_mean=float(np.mean(calibrated["easting_m"])) if calibrated.size else None,
                northing_mean=float(np.mean(calibrated["northing_m"])) if calibrated.size else None,
                height_median=float(np.median(calibrated["height_m"])) if calibrated.size else None,
                height_min=float(np.min(calibrated["height_m"])) if calibrated.size else None,
                height_max=float(np.max(calibrated["height_m"])) if calibrated.size else None,
            )
        )

    sample_output = args.l3_dir / f"L3C_CH1_{cap_id_from_l1_path(DEFAULT_CONTINUOUS_L1_FILES[0])}.h5"
    sample_preview = args.preview_dir / "stage35_ch1_calibrated_sample_preview.html"
    if sample_output.exists():
        with h5py.File(sample_output, "r") as h5:
            pts = h5["L3_CALIBRATED/CH1/points"][:]
        make_stage3_preview(sample_preview, pts["easting_m"], pts["northing_m"], pts["height_m"])

    merged_output = args.l3_dir / "L3C_CH1_continuous_cap_00111_00115.h5"
    merged_arrays = []
    for path in calibrated_paths:
        with h5py.File(path, "r") as h5:
            merged_arrays.append(h5["L3_CALIBRATED/CH1/points"][:])
    merged = np.concatenate(merged_arrays) if merged_arrays else np.array([], dtype=[])
    if merged_output.exists():
        merged_output.unlink()
    with h5py.File(merged_output, "w") as h5:
        group = h5.create_group("L3_CALIBRATED")
        for ch in range(1, 5):
            ch_group = group.create_group(f"CH{ch}")
            if ch == 1:
                ch_group.create_dataset("points", data=merged, compression="gzip", compression_opts=4)
            else:
                ch_group.create_dataset("points", shape=(0,), dtype=merged.dtype)

    continuous_preview = args.preview_dir / "stage35_ch1_calibrated_continuous_preview.html"
    if merged.size:
        make_stage3_preview(continuous_preview, merged["easting_m"], merged["northing_m"], merged["height_m"])
    else:
        continuous_preview.write_text("<html><body>No calibrated points</body></html>", encoding="utf-8")

    skipped = [item for item in summaries if item.skipped]
    if merged.size == 0:
        conclusion = "不合理"
        recommendation = "暂停排查：经验校正后没有可用点。"
    elif skipped:
        conclusion = "基本合理但有风险"
        recommendation = "经验校正后的可用文件已生成，但存在被跳过的时间异常文件；建议确认后再继续阶段 4/5。"
    else:
        conclusion = "合理"
        recommendation = "经验校正后连续样本可用，可以继续阶段 4/5。"

    report = Stage35Report(
        stage_name="stage35_empirical_calibration",
        sample_input_l2_pos=str(DEFAULT_STAGE2_L2_POS),
        reference_l3=str(args.reference_l3),
        calibration_model_path=str(model_path),
        sample_output_l3_calibrated=str(sample_output),
        sample_preview_html=str(sample_preview),
        continuous_output_l3_merged=str(merged_output),
        continuous_preview_html=str(continuous_preview),
        model=model,
        file_summaries=summaries,
        merged_point_count=int(merged.size),
        merged_gps_time=finite_stats(merged["gps_time"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_easting=finite_stats(merged["easting_m"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_northing=finite_stats(merged["northing_m"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        merged_height=finite_stats(merged["height_m"]) if merged.size else RangeStats(0, float("nan"), float("nan"), float("nan")),
        known_warnings=warnings,
        conclusion=conclusion,
        recommendation=recommendation,
    )

    reports_dir = args.metadata_dir / "stage_reports"
    md_path = reports_dir / "stage35_empirical_calibration_report.md"
    json_path = reports_dir / "stage35_empirical_calibration_report.json"
    json_path.write_text(json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2), encoding="utf-8-sig")
    write_stage35_markdown(report, md_path)

    print(f"Stage 3.5 conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Sample calibrated preview: {sample_preview.resolve()}")
    print(f"Continuous calibrated preview: {continuous_preview.resolve()}")
    print(f"Markdown report: {md_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return report


def run_stage0(args: argparse.Namespace) -> Stage0Report:
    report = build_stage0_report(
        sample_l1=args.sample_l1,
        reference_l3=args.reference_l3,
        pos_source=args.pos_source,
        lidar_time_offset_sec=args.lidar_time_offset_sec,
    )

    reports_dir = args.metadata_dir / "stage_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "stage0_baseline_report.json"
    md_path = reports_dir / "stage0_baseline_report.md"

    json_path.write_text(
        json.dumps(dataclass_to_jsonable(report), ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )
    write_stage0_markdown(report, md_path)

    print(f"Stage 0 conclusion: {report.conclusion}")
    print(f"Recommendation: {report.recommendation}")
    print(f"Markdown report: {md_path.resolve()}")
    print(f"JSON report: {json_path.resolve()}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CH1 gated airborne LiDAR processing pipeline.")
    parser.add_argument(
        "stage",
        choices=["stage0", "stage1", "stage2", "stage3", "stage35", "stage4"],
        help="Pipeline stage to run. Respect the manual gate before advancing.",
    )
    parser.add_argument("--sample-l1", type=Path, default=DEFAULT_SAMPLE_L1)
    parser.add_argument("--reference-l3", type=Path, default=DEFAULT_REFERENCE_L3)
    parser.add_argument("--pos-source", type=Path, default=DEFAULT_POS_MAT)
    parser.add_argument("--lidar-time-offset-sec", type=float, default=DEFAULT_TIME_OFFSET_SEC)
    parser.add_argument("--metadata-dir", type=Path, default=Path("metadata"))
    parser.add_argument("--input-l2", type=Path, default=DEFAULT_STAGE1_L2)
    parser.add_argument("--input-l2-pos", type=Path, default=DEFAULT_STAGE2_L2_POS)
    parser.add_argument("--l2-dir", type=Path, default=DEFAULT_L2_DIR)
    parser.add_argument("--l2-pos-dir", type=Path, default=DEFAULT_L2_POS_DIR)
    parser.add_argument("--l3-dir", type=Path, default=DEFAULT_L3_DIR)
    parser.add_argument("--preview-dir", type=Path, default=DEFAULT_PREVIEW_DIR)
    parser.add_argument("--calib-coeffs", type=Path, default=DEFAULT_CALIB_COEFFS)
    parser.add_argument("--pos-low-confidence-threshold-sec", type=float, default=0.2)
    parser.add_argument("--stage3-range-min-m", type=float, default=30.0)
    parser.add_argument("--stage4-l1-files", action="append")
    parser.add_argument("--stage35-apply-z-scale", action="store_true")
    parser.add_argument("--stage35-apply-rotation", action="store_true")
    parser.add_argument("--stage35-height-margin-m", type=float, default=30.0)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.stage == "stage0":
        run_stage0(args)
    elif args.stage == "stage1":
        run_stage1(args)
    elif args.stage == "stage2":
        run_stage2(args)
    elif args.stage == "stage3":
        run_stage3(args)
    elif args.stage == "stage35":
        run_stage35(args)
    elif args.stage == "stage4":
        run_stage4(args)
    else:
        raise ValueError(f"Unsupported stage: {args.stage}")


if __name__ == "__main__":
    main()
