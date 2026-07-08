from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import plotly.graph_objects as go
from pyproj import Transformer

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag


ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_PROJECT_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3",
    )
)
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
REFERENCE_L3 = ROOT / "0510_f3" / "L3_DATA" / "L2_cap_00111_20260510190957.h5"
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
C_OUTPUT_ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_STAGE6_CPP_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0\0510_f30510_f3_data\outputs\stage6_cpp_filter_ch1",
    )
)
QC_DIR = C_OUTPUT_ROOT / "qc"
H5_DIR = C_OUTPUT_ROOT / "h5"
TXT_DIR = C_OUTPUT_ROOT / "txt_cloudcompare"
PREVIEW_DIR = C_OUTPUT_ROOT / "preview"
REPORT_DIR = C_OUTPUT_ROOT / "reports"

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0
ZERO_OFFSET_CANDIDATE_M = 20.486969030907204
MIN_FAR_RANGE_M = 30.0
CRS = "EPSG:32651"

PULSE_NUM_INT = 250
CPP_TIMEINFO_TO_M = 64e-12 * 299792458.0 / 2.0
GLASS_FILTER_THRESHOLD_CPP_COUNT = 3000
GLASS_FILTER_THRESHOLD_M = GLASS_FILTER_THRESHOLD_CPP_COUNT * CPP_TIMEINFO_TO_M
GLASS_FILTER_THRESHOLD_H5_COUNT = int(np.ceil(GLASS_FILTER_THRESHOLD_M / DIST_FACTOR))
HALF_K_NEIGHBOUR = 20
N_STDEV = 1.0
MIN_MEAN_PERCENT = 0.04


METHOD_REGISTRY = [
    {
        "method_id": "CPP_FILTER_009",
        "method_name": "SinglePhotonLidar C++ pre-georeference distance-domain filter",
        "source_type": "project_source_code",
        "source_reference": r"SinglePhotonLidar_copy\SinglePhotonLidar\FilterFunction.cpp",
        "used_for_delete_or_transform": "yes, diagnostic pre-georeference return filtering",
    },
    {
        "method_id": "DG_ALS_001",
        "method_name": "GNSS/IMU assisted airborne LiDAR direct georeferencing model",
        "source_type": "peer_reviewed_journal",
        "source_reference": "Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_PARAMETER",
        "method_name": "Stage 5G2 CH1 diagnostic zero/axis/attitude parameters",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Stage 5G2 exact-time reference-L3 diagnostic; not final production calibration",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "EXACT_TIME_MATCH_QC",
        "method_name": "reference L3 exact GNSS time validation",
        "source_type": "project_qc_rule",
        "source_reference": "Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18",
        "used_for_delete_or_transform": "no, QC only",
    },
]


def parse_seq_text(value: str) -> int:
    return int(value)


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
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


def parse_seq(path: Path) -> int:
    match = re.search(r"L1_cap_(\d+)_([0-9]{14})\.h5$", path.name)
    if not match:
        raise ValueError(f"Cannot parse sequence from {path}")
    return int(match.group(1))


def cap_id(path: Path) -> str:
    return pipe.cap_id_from_l1_path(path)


def l1_for_seq(seq: int) -> Path:
    matches = sorted(L1_DIR.glob(f"L1_cap_{seq:05d}_*.h5"))
    if not matches:
        raise FileNotFoundError(f"Missing L1 sequence {seq:05d} in {L1_DIR}")
    return matches[0]


def load_repair_context() -> tuple[dict[int, stage5.FileInfo], dict[int, dict[str, Any]]]:
    files = stage5.read_manifest(stage5.MANIFEST)
    return {item.seq: item for item in files}, stage5.build_repair_models(files)


def seqs_for_mode(mode: str, seq: int, seq_start: int, seq_end: int) -> list[int]:
    if mode == "single":
        return [seq]
    if mode == "range":
        if seq_start > seq_end:
            raise ValueError("--seq-start must be <= --seq-end")
        return list(range(seq_start, seq_end + 1))
    raise ValueError(mode)


def load_l1_ch1(path: Path) -> dict[str, np.ndarray]:
    with h5py.File(path, "r") as h5:
        return {
            "gnss": h5["GNSS_SEC_CH1"][:].astype(np.float64),
            "raw_dist": h5["Photon_CH1_DIST"][:].astype(np.uint32),
            "coder": h5["Photon_CH1_CODER"][:].astype(np.float64),
            "pulse_index": h5["PULSE_INDEX_CH1"][:].astype(np.uint32),
            "pulse_circle": h5["PULSE_CIRCLE_CH1"][:].astype(np.uint32),
        }


def cpp_filter_mask(raw_dist: np.ndarray, pulse_index: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    keep = np.zeros(raw_dist.size, dtype=bool)
    group_count = 0
    empty_group_count = 0
    start = 0
    n = raw_dist.size
    while start < n:
        start_pulse = int(pulse_index[start])
        end = start + 1
        while end < n and int(pulse_index[end]) <= start_pulse + PULSE_NUM_INT:
            end += 1

        group_idx = np.arange(start, end, dtype=np.int64)
        marker_mask = np.zeros(group_idx.size, dtype=bool)
        photon_mask = raw_dist[group_idx] > GLASS_FILTER_THRESHOLD_H5_COUNT
        eligible = group_idx[marker_mask | photon_mask]
        if eligible.size == 0:
            empty_group_count += 1
            start = end
            continue

        group_count += 1
        order = np.argsort(raw_dist[eligible], kind="mergesort")
        sorted_idx = eligible[order]
        sorted_dist = raw_dist[sorted_idx].astype(np.float64)
        size = sorted_idx.size
        half_k = HALF_K_NEIGHBOUR
        k = min(half_k * 2, size)
        if k <= 0:
            start = end
            continue

        kmean = np.empty(size, dtype=np.float64)
        for i in range(size):
            if i - half_k < 0:
                local_start = 0
            elif i + half_k > size - 1:
                local_start = size - k - 1
            else:
                local_start = i - half_k
            if local_start < 0:
                local_start = 0
            local_end = min(size, local_start + k + 1)
            denom = max(k, 1)
            kmean[i] = np.sum(np.abs(sorted_dist[local_start:local_end] - sorted_dist[i])) / denom

        sorted_kmean = np.sort(kmean)
        stats_idx = int((sorted_kmean.size - 1) * MIN_MEAN_PERCENT)
        mean = float(sorted_kmean[stats_idx])
        stdev = mean * 0.2
        sorted_keep = kmean <= mean + stdev * N_STDEV
        keep[sorted_idx[sorted_keep]] = True
        start = end

    return keep, {
        "group_count": group_count,
        "empty_group_count": empty_group_count,
        "pulse_num_int": PULSE_NUM_INT,
        "glass_filter_threshold_cpp_count": GLASS_FILTER_THRESHOLD_CPP_COUNT,
        "glass_filter_threshold_m": GLASS_FILTER_THRESHOLD_M,
        "glass_filter_threshold_h5_count": GLASS_FILTER_THRESHOLD_H5_COUNT,
        "half_k_neighbour": HALF_K_NEIGHBOUR,
        "n_stdev": N_STDEV,
        "min_mean_percent": MIN_MEAN_PERCENT,
    }


def pos_quality_flags(lidar_time: np.ndarray, pos_time: np.ndarray, low_conf_sec: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    no_pos = (lidar_time < pos_time[0]) | (lidar_time > pos_time[-1])
    nearest_dt = pipe.nearest_time_delta_abs(pos_time, np.clip(lidar_time, pos_time[0], pos_time[-1]))
    flags = np.zeros(lidar_time.size, dtype=np.uint16)
    flags[no_pos] |= 1
    flags[nearest_dt > low_conf_sec] |= 2
    return flags, nearest_dt


def interp_pos(lidar_time: np.ndarray, pos_time: np.ndarray, pos: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    return {
        "easting": np.interp(interp_time, pos_time, pos["EASTING"]),
        "northing": np.interp(interp_time, pos_time, pos["NORTHING"]),
        "height": np.interp(interp_time, pos_time, pos["HEIGHT"]),
        "roll": np.interp(interp_time, pos_time, pos["ROLL"]),
        "pitch": np.interp(interp_time, pos_time, pos["PITCH"]),
        "heading": pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time),
    }


def point_dtype() -> np.dtype:
    return np.dtype(
        [
            ("source_seq", "u2"),
            ("gps_time", "f8"),
            ("easting_m", "f8"),
            ("northing_m", "f8"),
            ("height_m", "f8"),
            ("lon", "f8"),
            ("lat", "f8"),
            ("range_before_m", "f4"),
            ("range_m", "f4"),
            ("scan_angle_deg", "f4"),
            ("pulse_index", "u4"),
            ("quality_flag", "u2"),
            ("pos_quality_flag", "u2"),
            ("cpp_filter_flag", "u1"),
        ]
    )


def transform_stage5g2(
    range_before: np.ndarray,
    coder: np.ndarray,
    pos_arrays: dict[str, np.ndarray],
    calibration: dict[str, float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    range_m = (range_before - ZERO_OFFSET_CANDIDATE_M - calibration["intercept"]) / calibration["slope"]
    scan_angle = coder * 360.0 / 65536.0
    model_angle = 360.0 - scan_angle
    bx, by, bz = pipe.f_body_frame_xyz(range_m, model_angle)
    frd = np.column_stack([bx, by, bz])
    roll = np.deg2rad(pos_arrays["roll"])
    pitch = np.deg2rad(pos_arrays["pitch"])
    heading = -np.deg2rad(pos_arrays["heading"]) + np.pi
    ned = diag.rotate_frd_to_ned(frd, roll, pitch, heading, "YXZ", True)
    return range_m, scan_angle, ned[:, 0], ned[:, 1], ned[:, 2]


def write_h5(path: Path, points: np.ndarray, source_l1: Path, filter_stats: dict[str, Any], mode_label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        l3 = h5.create_group("L3")
        ch1 = l3.create_group("CH1")
        ch1.create_dataset("points", data=points, compression="gzip", compression_opts=4, chunks=True)
        for ch in range(2, 5):
            l3.create_group(f"CH{ch}").create_dataset("points", shape=(0,), dtype=points.dtype)
        meta = h5.create_group("metadata")
        proc = meta.create_group("processing")
        pipe.write_str_attr(proc, "stage", "stage6_cpp_filter_ch1")
        pipe.write_str_attr(proc, "source_l1_name", source_l1.name)
        pipe.write_str_attr(proc, "mode_label", mode_label)
        pipe.write_str_attr(proc, "crs", CRS)
        pipe.write_str_attr(proc, "filter_source", r"SinglePhotonLidar_copy\SinglePhotonLidar\FilterFunction.cpp")
        proc.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        proc.attrs["zero_offset_candidate_m"] = ZERO_OFFSET_CANDIDATE_M
        for key, value in filter_stats.items():
            if isinstance(value, str):
                pipe.write_str_attr(proc, key, value)
            else:
                proc.attrs[key] = value


def write_cloudcompare_txt(path: Path, points: np.ndarray, max_points: int) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if max_points > 0 and points.size > max_points:
        idx = np.linspace(0, points.size - 1, max_points, dtype=np.int64)
        data = points[idx]
    else:
        data = points
    header = "X Y Z height_m gps_time range_m scan_angle_deg source_seq pos_quality_flag cpp_filter_flag"
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(header + "\n")
        for p in data:
            f.write(
                f"{p['easting_m']:.9f} {p['northing_m']:.9f} {p['height_m']:.9f} "
                f"{p['height_m']:.9f} {p['gps_time']:.9f} {float(p['range_m']):.9f} "
                f"{float(p['scan_angle_deg']):.9f} {int(p['source_seq'])} {int(p['pos_quality_flag'])} {int(p['cpp_filter_flag'])}\n"
            )
    return int(data.size)


def make_preview(path: Path, points: np.ndarray, title: str, max_points: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if points.size == 0:
        path.write_text("<html><body>No points</body></html>", encoding="utf-8")
        return
    idx = np.linspace(0, points.size - 1, min(max_points, points.size), dtype=np.int64)
    sample = points[idx]
    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=sample["easting_m"],
                y=sample["northing_m"],
                z=sample["height_m"],
                mode="markers",
                marker={"size": 1.2, "color": sample["height_m"], "colorscale": "Viridis", "opacity": 0.8},
            )
        ]
    )
    fig.update_layout(
        title=title,
        scene={"xaxis_title": "Easting", "yaxis_title": "Northing", "zaxis_title": "Height", "aspectmode": "data"},
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
    )
    fig.write_html(path, include_plotlyjs="cdn")


def reference_arrays() -> dict[str, np.ndarray]:
    with h5py.File(REFERENCE_L3, "r") as h5:
        return {
            "time": h5["GNSS_SEC"][:].astype(np.float64),
            "north_offset": h5["LIDAR_X"][:].astype(np.float64),
            "east_offset": h5["LIDAR_Y"][:].astype(np.float64),
            "down_offset": h5["LIDAR_Z"][:].astype(np.float64),
        }


def reference_validation_for_00111(
    l1: dict[str, np.ndarray],
    keep_mask: np.ndarray,
    calibration: dict[str, float],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    max_points: int,
) -> dict[str, Any]:
    ref = reference_arrays()
    lidar_time = l1["gnss"] + pipe.DEFAULT_TIME_OFFSET_SEC
    range_before = l1["raw_dist"].astype(np.float64) * DIST_FACTOR
    sort_idx = np.argsort(lidar_time, kind="mergesort")
    sorted_time = lidar_time[sort_idx]
    sorted_range = range_before[sort_idx]
    sorted_coder = l1["coder"][sort_idx]
    sorted_keep = keep_mask[sort_idx]
    left = np.searchsorted(sorted_time, ref["time"], side="left")
    right = np.searchsorted(sorted_time, ref["time"], side="right")
    available = np.flatnonzero(right > left).astype(np.int64)
    if available.size > max_points:
        ridx = available[np.linspace(0, available.size - 1, max_points, dtype=np.int64)]
    else:
        ridx = available

    ref_norm = np.sqrt(ref["north_offset"] ** 2 + ref["east_offset"] ** 2 + ref["down_offset"] ** 2)
    selected_range = np.empty(ridx.size, dtype=np.float64)
    selected_coder = np.empty(ridx.size, dtype=np.float64)
    candidate_count = np.empty(ridx.size, dtype=np.int16)
    cpp_candidate_count = np.empty(ridx.size, dtype=np.int16)
    fallback_count = 0
    for out_i, ref_i in enumerate(ridx):
        lo = int(left[ref_i])
        hi = int(right[ref_i])
        local_keep = sorted_keep[lo:hi]
        candidate_count[out_i] = hi - lo
        cpp_candidate_count[out_i] = int(np.count_nonzero(local_keep))
        if np.any(local_keep):
            ranges = sorted_range[lo:hi][local_keep]
            coders = sorted_coder[lo:hi][local_keep]
        else:
            ranges = sorted_range[lo:hi]
            coders = sorted_coder[lo:hi]
            fallback_count += 1
        far = ranges > MIN_FAR_RANGE_M
        if np.any(far):
            ranges = ranges[far]
            coders = coders[far]
        pick = int(np.argmin(np.abs(ranges - ref_norm[ref_i])))
        selected_range[out_i] = ranges[pick]
        selected_coder[out_i] = coders[pick]

    matched_time = ref["time"][ridx]
    pos_arrays = interp_pos(matched_time, pos_time, pos)
    _, _, north, east, down = transform_stage5g2(selected_range, selected_coder, pos_arrays, calibration)
    pred = np.column_stack([north, east, down])
    truth = np.column_stack([ref["north_offset"][ridx], ref["east_offset"][ridx], ref["down_offset"][ridx]])
    diff = pred - truth
    rmse = np.sqrt(np.mean(diff**2, axis=0))
    p90 = np.percentile(np.abs(diff), 90, axis=0)
    vector_rmse = float(np.sqrt(np.mean(np.sum(diff**2, axis=1))))
    return {
        "reference_file": str(REFERENCE_L3),
        "matched_points_used": int(ridx.size),
        "exact_match_total": int(available.size),
        "match_strategy": "cpp_filter_candidates_refnorm_qc",
        "fallback_no_cpp_candidate_count": int(fallback_count),
        "candidate_count_median": float(np.median(candidate_count)),
        "cpp_candidate_count_median": float(np.median(cpp_candidate_count)),
        "north_rmse_m": float(rmse[0]),
        "east_rmse_m": float(rmse[1]),
        "down_rmse_m": float(rmse[2]),
        "vector_rmse_m": vector_rmse,
        "north_p90_abs_error_m": float(p90[0]),
        "east_p90_abs_error_m": float(p90[1]),
        "down_p90_abs_error_m": float(p90[2]),
    }


def process_one(
    seq: int,
    file_info: stage5.FileInfo | None,
    repair_model: dict[str, Any] | None,
    calibration: dict[str, float],
    pos_time: np.ndarray,
    pos: dict[str, np.ndarray],
    transformer: Transformer,
    txt_max_points: int,
    html_preview_points: int,
    mode_label: str,
) -> tuple[dict[str, Any], np.ndarray, dict[str, Any], dict[str, np.ndarray]]:
    path = l1_for_seq(seq)
    l1 = load_l1_ch1(path)
    keep_mask, filter_stats = cpp_filter_mask(l1["raw_dist"], l1["pulse_index"])
    if file_info is not None:
        _raw_time, lidar_time, time_status = stage5.compute_lidar_time(l1["gnss"], l1["pulse_index"], file_info, repair_model)
    else:
        lidar_time = l1["gnss"] + pipe.DEFAULT_TIME_OFFSET_SEC
        time_status = "ORIGINAL_NO_MANIFEST"
    pos_flags, _ = pos_quality_flags(lidar_time, pos_time)
    valid = keep_mask & (pos_flags == 0) & np.isfinite(l1["raw_dist"])
    if not np.any(valid):
        row = {
            "seq": seq,
            "file": str(path),
            "status": "SKIPPED",
            "time_status": time_status,
            "point_count_l1": int(l1["raw_dist"].size),
            "cpp_keep_count": int(np.count_nonzero(keep_mask)),
            "warning": "no cpp-filtered points with POS",
        }
        return row, np.zeros(0, dtype=point_dtype()), filter_stats, l1

    selected_time = lidar_time[valid]
    pos_arrays = interp_pos(selected_time, pos_time, pos)
    range_before = l1["raw_dist"][valid].astype(np.float64) * DIST_FACTOR
    range_m, scan_angle, north_offset, east_offset, down_offset = transform_stage5g2(
        range_before, l1["coder"][valid], pos_arrays, calibration
    )
    easting = pos_arrays["easting"] + east_offset
    northing = pos_arrays["northing"] + north_offset
    height = pos_arrays["height"] - down_offset
    lon, lat = transformer.transform(easting, northing)

    points = np.empty(selected_time.size, dtype=point_dtype())
    points["source_seq"] = seq
    points["gps_time"] = selected_time
    points["easting_m"] = easting
    points["northing_m"] = northing
    points["height_m"] = height
    points["lon"] = lon
    points["lat"] = lat
    points["range_before_m"] = range_before.astype(np.float32)
    points["range_m"] = range_m.astype(np.float32)
    points["scan_angle_deg"] = scan_angle.astype(np.float32)
    points["pulse_index"] = l1["pulse_index"][valid]
    points["quality_flag"] = 0
    points["pos_quality_flag"] = pos_flags[valid]
    points["cpp_filter_flag"] = 1

    h5_path = H5_DIR / f"L3_STAGE6_CPPFILTER_CH1_{cap_id(path)}.h5"
    txt_path = TXT_DIR / f"L3_STAGE6_CPPFILTER_CH1_{cap_id(path)}_height_scalar.txt"
    preview_path = PREVIEW_DIR / f"stage6_cppfilter_ch1_{cap_id(path)}.html"
    write_h5(h5_path, points, path, filter_stats, mode_label)
    txt_count = write_cloudcompare_txt(txt_path, points, txt_max_points)
    make_preview(preview_path, points, f"Stage 6 C++ filter CH1 {cap_id(path)}", html_preview_points)

    edge_count = min(max(1, points.size // 10), 50_000)
    row = {
        "seq": seq,
        "file": str(path),
        "status": "PROCESSED",
        "time_status": time_status,
        "output_h5": str(h5_path),
        "output_txt": str(txt_path),
        "preview_html": str(preview_path),
        "point_count_l1": int(l1["raw_dist"].size),
        "cpp_keep_count": int(np.count_nonzero(keep_mask)),
        "cpp_keep_ratio": float(np.count_nonzero(keep_mask) / max(keep_mask.size, 1)),
        "point_count_l3": int(points.size),
        "txt_point_count": txt_count,
        "pos_success_rate": float(np.count_nonzero(pos_flags == 0) / max(pos_flags.size, 1)),
        "height_min": float(np.min(points["height_m"])),
        "height_p01": float(np.percentile(points["height_m"], 1)),
        "height_median": float(np.median(points["height_m"])),
        "height_p99": float(np.percentile(points["height_m"], 99)),
        "height_max": float(np.max(points["height_m"])),
        "height_first_edge_median": float(np.median(points["height_m"][:edge_count])),
        "height_last_edge_median": float(np.median(points["height_m"][-edge_count:])),
        "range_m_median": float(np.median(points["range_m"])),
        "warning": "",
    }
    if time_status == "REPAIRED_TIME_EXPERIMENT":
        row["warning"] = "time repaired by Stage 5 project repair model"
    if np.min(points["height_m"]) < -100 or np.max(points["height_m"]) > 150:
        row["warning"] = (row["warning"] + "; " if row["warning"] else "") + "height range contains large outliers"
    return row, points, filter_stats, l1


def combine_points(points_by_file: list[np.ndarray], max_points: int) -> np.ndarray:
    non_empty = [points for points in points_by_file if points.size]
    if not non_empty:
        return np.zeros(0, dtype=point_dtype())
    total = sum(points.size for points in non_empty)
    if max_points <= 0 or total <= max_points:
        return np.concatenate(non_empty)
    sampled = []
    for points in non_empty:
        count = max(1, int(round(points.size / total * max_points)))
        idx = np.linspace(0, points.size - 1, min(count, points.size), dtype=np.int64)
        sampled.append(points[idx])
    merged = np.concatenate(sampled)
    if merged.size > max_points:
        idx = np.linspace(0, merged.size - 1, max_points, dtype=np.int64)
        merged = merged[idx]
    return merged


def seam_rows(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    processed = [row for row in file_rows if row.get("status") == "PROCESSED"]
    rows = []
    for prev, curr in zip(processed, processed[1:]):
        rows.append(
            {
                "prev_seq": prev["seq"],
                "next_seq": curr["seq"],
                "height_edge_median_delta_m": float(curr["height_first_edge_median"] - prev["height_last_edge_median"]),
                "prev_warning": prev.get("warning", ""),
                "next_warning": curr.get("warning", ""),
            }
        )
    return rows


def conclusion_for(mode: str, reference_qc: dict[str, Any] | None, seams: list[dict[str, Any]]) -> tuple[str, str]:
    max_abs_seam = max([abs(row["height_edge_median_delta_m"]) for row in seams] or [0.0])
    if mode == "single" and reference_qc:
        if (
            reference_qc["vector_rmse_m"] < 2.5
            and reference_qc["down_rmse_m"] < 1.0
            and reference_qc["down_p90_abs_error_m"] < 1.5
        ):
            return "合理", "00111 reference exact-time QC passed; pause for manual CloudCompare inspection."
        return "不合理", "00111 reference exact-time QC failed; do not expand this model."
    if max_abs_seam < 0.5:
        return "基本合理但有风险", "Range sample seam metric is below 0.5 m; inspect CloudCompare before the next gate."
    if max_abs_seam < 1.0:
        return "基本合理但有风险", "Range sample seam metric is below 1.0 m risk limit; inspect local objects and edges."
    return "不合理", "Range sample seam metric exceeds 1.0 m; keep this as diagnostic only."


def write_report(path: Path, payload: dict[str, Any]) -> None:
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    ref = payload.get("reference_validation")
    ref_text = "N/A"
    if ref:
        ref_text = (
            f"vector RMSE={ref['vector_rmse_m']:.6f} m, "
            f"down RMSE={ref['down_rmse_m']:.6f} m, "
            f"down P90={ref['down_p90_abs_error_m']:.6f} m"
        )
    content = f"""# Stage 6 CH1 C++ Filter Validation

## Gate Conclusion

- 结论：{payload['gate_conclusion']}
- 建议：{payload['recommendation']}
- 模式：{payload['mode_label']}
- 输出根目录：`{C_OUTPUT_ROOT}`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## C++ Filter Parameters

- `PULSE_NUM_INT = {PULSE_NUM_INT}`
- `GLASS_FILTER_THRESHOLD_CPP_COUNT = {GLASS_FILTER_THRESHOLD_CPP_COUNT}`
- `GLASS_FILTER_THRESHOLD_M = {GLASS_FILTER_THRESHOLD_M:.6f}`
- `GLASS_FILTER_THRESHOLD_H5_COUNT = {GLASS_FILTER_THRESHOLD_H5_COUNT}`
- `HALF_K_NEIGHBOUR = {HALF_K_NEIGHBOUR}`
- `N_STDEV = {N_STDEV}`
- `MIN_MEAN_PERCENT = {MIN_MEAN_PERCENT}`

## Key Statistics

- Input sequences: `{', '.join(str(x) for x in payload['input_sequences'])}`
- Processed files: {payload['processed_file_count']}
- Total output points: {payload['total_output_points']:,}
- Reference validation: {ref_text}
- Max abs seam height edge median delta: {payload['max_abs_seam_height_edge_median_delta_m']}

## Outputs

- File summary CSV: `{payload['file_summary_csv']}`
- Seam summary CSV: `{payload['seam_summary_csv']}`
- Merged TXT: `{payload['merged_txt']}`
- Merged preview HTML: `{payload['merged_preview_html']}`

## Manual Checklist

- 在 CloudCompare 中打开 merged TXT，按第 4 列 `height_m` 着色。
- 检查是否仍有大面积上下双层。
- 检查建筑/道路/地面形态是否比 Stage 5R2 all_far/nearest_far 更稳定。
- 本阶段仍是诊断，不进入 CH2、去噪或 LAZ。
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 6 CH1 C++ filter migration and validation.")
    parser.add_argument("--mode", choices=["single", "range"], required=True)
    parser.add_argument("--seq", type=parse_seq_text, default=111)
    parser.add_argument("--seq-start", type=parse_seq_text, default=50)
    parser.add_argument("--seq-end", type=parse_seq_text, default=120)
    parser.add_argument("--txt-max-points", type=int, default=200_000)
    parser.add_argument("--merged-preview-points", type=int, default=300_000)
    parser.add_argument("--html-preview-points", type=int, default=200_000)
    parser.add_argument("--reference-max-points", type=int, default=100_000)
    args = parser.parse_args()

    seqs = seqs_for_mode(args.mode, args.seq, args.seq_start, args.seq_end)
    mode_label = args.mode if args.mode == "single" else f"range_{args.seq_start:05d}_{args.seq_end:05d}"

    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")
    pos_time, pos, _ = stage5.load_pos()
    transformer = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    file_info_by_seq, repair_models = load_repair_context()

    rows: list[dict[str, Any]] = []
    points_by_file: list[np.ndarray] = []
    l1_by_seq: dict[int, dict[str, np.ndarray]] = {}
    keep_by_seq: dict[int, np.ndarray] = {}
    for seq in seqs:
        print(f"Processing Stage 6 seq {seq:05d}", flush=True)
        row, points, _filter_stats, l1 = process_one(
            seq,
            file_info_by_seq.get(seq),
            repair_models.get(seq),
            calibration,
            pos_time,
            pos,
            transformer,
            args.txt_max_points,
            args.html_preview_points,
            mode_label,
        )
        rows.append(row)
        points_by_file.append(points)
        if seq == 111:
            l1_by_seq[seq] = l1
            keep_by_seq[seq], _ = cpp_filter_mask(l1["raw_dist"], l1["pulse_index"])

    reference_qc = None
    if 111 in seqs and REFERENCE_L3.exists():
        print("Running Stage 6 00111 reference validation...", flush=True)
        l1 = l1_by_seq.get(111)
        keep = keep_by_seq.get(111)
        if l1 is None or keep is None:
            l1 = load_l1_ch1(l1_for_seq(111))
            keep, _ = cpp_filter_mask(l1["raw_dist"], l1["pulse_index"])
        reference_qc = reference_validation_for_00111(l1, keep, calibration, pos_time, pos, args.reference_max_points)
        write_json(QC_DIR / "stage6_00111_reference_validation.json", reference_qc)

    seams = seam_rows(rows)
    merged = combine_points(points_by_file, args.merged_preview_points)
    merged_txt = TXT_DIR / f"stage6_cppfilter_ch1_{mode_label}_merged_height_scalar.txt"
    merged_preview = PREVIEW_DIR / f"stage6_cppfilter_ch1_{mode_label}_merged_preview.html"
    merged_txt_count = write_cloudcompare_txt(merged_txt, merged, 0)
    make_preview(merged_preview, merged, f"Stage 6 C++ filter CH1 {mode_label}", args.html_preview_points)

    file_fields = [
        "seq",
        "file",
        "status",
        "output_h5",
        "output_txt",
        "preview_html",
        "time_status",
        "point_count_l1",
        "cpp_keep_count",
        "cpp_keep_ratio",
        "point_count_l3",
        "txt_point_count",
        "pos_success_rate",
        "height_min",
        "height_p01",
        "height_median",
        "height_p99",
        "height_max",
        "height_first_edge_median",
        "height_last_edge_median",
        "range_m_median",
        "warning",
    ]
    file_summary = QC_DIR / f"stage6_cppfilter_ch1_{mode_label}_file_summary.csv"
    seam_summary = QC_DIR / f"stage6_cppfilter_ch1_{mode_label}_seam_summary.csv"
    write_csv(file_summary, rows, file_fields)
    write_csv(seam_summary, seams, ["prev_seq", "next_seq", "height_edge_median_delta_m", "prev_warning", "next_warning"])

    max_abs_seam = max([abs(row["height_edge_median_delta_m"]) for row in seams] or [0.0])
    gate_conclusion, recommendation = conclusion_for(args.mode, reference_qc, seams)
    payload = {
        "stage_name": "stage6_ch1_cpp_filter_validation",
        "mode_label": mode_label,
        "input_sequences": seqs,
        "gate_conclusion": gate_conclusion,
        "recommendation": recommendation,
        "processed_file_count": sum(1 for row in rows if row.get("status") == "PROCESSED"),
        "total_output_points": sum(int(row.get("point_count_l3") or 0) for row in rows),
        "merged_txt": str(merged_txt),
        "merged_txt_point_count": merged_txt_count,
        "merged_preview_html": str(merged_preview),
        "file_summary_csv": str(file_summary),
        "seam_summary_csv": str(seam_summary),
        "max_abs_seam_height_edge_median_delta_m": float(max_abs_seam),
        "reference_validation": reference_qc,
        "method_registry": METHOD_REGISTRY,
        "cpp_filter_parameters": {
            "PULSE_NUM_INT": PULSE_NUM_INT,
            "GLASS_FILTER_THRESHOLD_CPP_COUNT": GLASS_FILTER_THRESHOLD_CPP_COUNT,
            "GLASS_FILTER_THRESHOLD_M": GLASS_FILTER_THRESHOLD_M,
            "GLASS_FILTER_THRESHOLD_H5_COUNT": GLASS_FILTER_THRESHOLD_H5_COUNT,
            "HALF_K_NEIGHBOUR": HALF_K_NEIGHBOUR,
            "N_STDEV": N_STDEV,
            "MIN_MEAN_PERCENT": MIN_MEAN_PERCENT,
        },
    }
    write_json(REPORT_DIR / f"stage6_cppfilter_ch1_{mode_label}_report.json", payload)
    write_report(REPORT_DIR / f"stage6_cppfilter_ch1_{mode_label}_report.md", payload)

    print("Stage 6 complete.", flush=True)
    print(f"Conclusion: {gate_conclusion}", flush=True)
    print(f"Report: {REPORT_DIR / f'stage6_cppfilter_ch1_{mode_label}_report.md'}", flush=True)
    print(f"Merged TXT: {merged_txt}", flush=True)


if __name__ == "__main__":
    main()
