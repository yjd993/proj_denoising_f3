import argparse
import csv
import gc
import json
import math
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage6e_ch1_bias_validation as stage6e
import stage6i_ch1_ladm2_scan_geometry_diagnostic as stage6i
import stage6k_ch1_ladm2_full_00111_export as stage6k


ROOT = Path(__file__).resolve().parents[2]
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
OUT_DIR = ROOT / "outputs" / "qc" / "stage6l_ladm2_continuous_segment"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
STAGE6I_BEST = ROOT / "outputs" / "qc" / "stage6i_ladm2_scan_geometry_diagnostic" / "best_candidate.json"
CRS = stage6k.CRS

METHOD_REGISTRY = [
    {
        "method_id": "CAO2017_LADM2_4_7_4_14",
        "method_name": "LADM-II mirror normal and reflected beam scan geometry",
        "source_type": "doctoral_thesis",
        "source_reference": "Cao 2017 section 4.4.2, formulas 4-7 to 4-14",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_PARAMETER",
        "method_name": "Stage 6L LADM-II continuous segment diagnostic",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Stage 6I best candidate applied to a short continuous CH1 L1 segment after 00111",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "CONTINUITY_QC",
        "method_name": "Continuous file seam and POS coverage diagnostics",
        "source_type": "project_qc_rule",
        "source_reference": "Per-file time coverage, POS confidence flags, coordinate ranges, and file-to-file seam statistics",
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


def l1_sequence(path: Path) -> int:
    match = re.search(r"L1_cap_(\d{5})_", path.name)
    if not match:
        raise ValueError(f"Cannot parse L1 sequence from {path}")
    return int(match.group(1))


def find_l1_segment(start_seq: int, file_count: int) -> list[Path]:
    by_seq = {l1_sequence(path): path for path in L1_DIR.glob("L1_cap_*.h5")}
    paths: list[Path] = []
    for seq in range(start_seq, start_seq + file_count):
        path = by_seq.get(seq)
        if path is None:
            raise FileNotFoundError(f"Missing L1 file for sequence {seq:05d} in {L1_DIR}")
        paths.append(path)
    return paths


def sample_l1_arrays(l1: dict[str, np.ndarray], max_points: int) -> dict[str, np.ndarray]:
    if max_points <= 0:
        return l1
    size = int(l1["gnss"].size)
    if max_points >= size:
        return l1
    idx = np.linspace(0, size - 1, max_points, dtype=np.int64)
    out: dict[str, np.ndarray] = {}
    for key, value in l1.items():
        if isinstance(value, np.ndarray) and value.shape[:1] == (size,):
            out[key] = value[idx]
        else:
            out[key] = value
    return out


def filter_l1_by_pos_coverage(
    l1: dict[str, np.ndarray],
    pos_time: np.ndarray,
    low_confidence_sec: float,
) -> tuple[dict[str, np.ndarray], int]:
    lidar_time = l1["gnss"].astype(np.float64) + pipe.DEFAULT_TIME_OFFSET_SEC
    in_range = (lidar_time >= pos_time[0]) & (lidar_time <= pos_time[-1])
    clipped = np.clip(lidar_time, pos_time[0], pos_time[-1])
    nearest_dt = pipe.nearest_time_delta_abs(pos_time, clipped)
    keep = in_range & (nearest_dt <= low_confidence_sec)
    kept = int(np.count_nonzero(keep))
    if kept == lidar_time.size:
        return l1, kept
    idx = np.flatnonzero(keep).astype(np.int64)
    out: dict[str, np.ndarray] = {}
    for key, value in l1.items():
        if isinstance(value, np.ndarray) and value.shape[:1] == (lidar_time.size,):
            out[key] = value[idx]
        else:
            out[key] = value
    return out, kept


def finite_stats(values: np.ndarray) -> dict[str, float | int]:
    return stage6k.finite_stats(values)


def per_file_row(seq: int, source_path: Path, h5_path: Path, stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_seq": seq,
        "source_file": str(source_path),
        "output_h5": str(h5_path),
        "source_point_count_l1": stats.get("source_point_count_l1", stats["point_count_l1"]),
        "pos_time_filter_kept_count": stats.get("pos_time_filter_kept_count", stats["point_count_l1"]),
        "point_count_l1": stats["point_count_l1"],
        "point_count_h5": stats["point_count_h5"],
        "range_m_gt_30_count": stats["range_m_gt_30_count"],
        "pos_success_rate": stats["pos_success_rate"],
        "pos_no_pos_count": stats["pos_no_pos_count"],
        "pos_low_confidence_count": stats["pos_low_confidence_count"],
        "gps_time_min_sec": stats["gps_time_sec"]["min"],
        "gps_time_max_sec": stats["gps_time_sec"]["max"],
        "range_m_median": stats["range_m"]["median"],
        "height_m_min": stats["height_m"]["min"],
        "height_m_median": stats["height_m"]["median"],
        "height_m_max": stats["height_m"]["max"],
        "easting_m_min": stats["easting_m"]["min"],
        "easting_m_max": stats["easting_m"]["max"],
        "northing_m_min": stats["northing_m"]["min"],
        "northing_m_max": stats["northing_m"]["max"],
    }


def per_file_fields() -> list[str]:
    return [
        "source_seq",
        "source_file",
        "output_h5",
        "source_point_count_l1",
        "pos_time_filter_kept_count",
        "point_count_l1",
        "point_count_h5",
        "range_m_gt_30_count",
        "pos_success_rate",
        "pos_no_pos_count",
        "pos_low_confidence_count",
        "gps_time_min_sec",
        "gps_time_max_sec",
        "range_m_median",
        "height_m_min",
        "height_m_median",
        "height_m_max",
        "easting_m_min",
        "easting_m_max",
        "northing_m_min",
        "northing_m_max",
    ]


def write_segment_h5(
    path: Path,
    source_path: Path,
    points: np.ndarray,
    candidate: dict[str, Any],
    stats: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    with h5py.File(path, "w") as h5:
        grp = h5.create_group("STAGE6L")
        ch1 = grp.create_group("CH1")
        ch1.create_dataset("full_points", data=points, compression="gzip", compression_opts=4, chunks=True)
        meta = h5.create_group("metadata")
        proc = meta.create_group("processing")
        pipe.write_str_attr(proc, "stage", "stage6l_ch1_ladm2_continuous_segment_diagnostic")
        pipe.write_str_attr(proc, "source_l1", str(source_path))
        pipe.write_str_attr(proc, "schema", "diagnostic_continuous_segment_ladm2_points")
        pipe.write_str_attr(proc, "crs", CRS)
        pipe.write_str_attr(proc, "production_status", "diagnostic_only_not_final_l3")
        proc.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        proc.attrs["zero_offset_m"] = stage6e.ZERO_OFFSET_M
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


def selected_indices(points: np.ndarray, max_points: int, min_range_m: float | None) -> np.ndarray:
    if min_range_m is None:
        valid_idx = np.arange(points.size, dtype=np.int64)
    else:
        valid_idx = np.flatnonzero(points["range_m"] > min_range_m).astype(np.int64)
    if max_points > 0 and valid_idx.size > max_points:
        return valid_idx[np.linspace(0, valid_idx.size - 1, max_points, dtype=np.int64)]
    return valid_idx


def append_cloudcompare_txt(path: Path, points: np.ndarray, max_points: int, min_range_m: float | None, write_header: bool) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    idx = selected_indices(points, max_points, min_range_m)
    mode = "w" if write_header else "a"
    with path.open(mode, encoding="utf-8", newline="\n") as f:
        if write_header:
            f.write("X Y Z source_seq height_m gps_time range_m scan_angle_deg point_index pos_quality_flag\n")
        for i in idx:
            p = points[i]
            f.write(
                f"{p['easting_m']:.9f} {p['northing_m']:.9f} {p['height_m']:.9f} "
                f"{int(p['source_seq'])} {p['height_m']:.9f} {p['gps_time']:.9f} "
                f"{float(p['range_m']):.9f} {float(p['scan_angle_deg']):.9f} "
                f"{int(p['point_index'])} {int(p['pos_quality_flag'])}\n"
            )
    return int(idx.size)


def seam_snapshot(points: np.ndarray, min_range_m: float, sample_count: int) -> dict[str, Any]:
    finite = (
        np.isfinite(points["gps_time"])
        & np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
        & (points["range_m"] > min_range_m)
        & (points["pos_quality_flag"] == 0)
    )
    idx = np.flatnonzero(finite).astype(np.int64)
    if idx.size == 0:
        return {"valid_count": 0}
    order = np.argsort(points["gps_time"][idx], kind="mergesort")
    sorted_idx = idx[order]
    head = sorted_idx[: min(sample_count, sorted_idx.size)]
    tail = sorted_idx[-min(sample_count, sorted_idx.size) :]
    return {
        "valid_count": int(sorted_idx.size),
        "start": point_summary(points[sorted_idx[0]]),
        "end": point_summary(points[sorted_idx[-1]]),
        "head": cloud_summary(points[head]),
        "tail": cloud_summary(points[tail]),
    }


def point_summary(point: np.void) -> dict[str, float]:
    return {
        "gps_time": float(point["gps_time"]),
        "easting_m": float(point["easting_m"]),
        "northing_m": float(point["northing_m"]),
        "height_m": float(point["height_m"]),
        "range_m": float(point["range_m"]),
        "scan_angle_deg": float(point["scan_angle_deg"]),
    }


def cloud_summary(points: np.ndarray) -> dict[str, float | int]:
    return {
        "count": int(points.size),
        "gps_time_median": float(np.median(points["gps_time"])),
        "easting_mean_m": float(np.mean(points["easting_m"])),
        "northing_mean_m": float(np.mean(points["northing_m"])),
        "height_mean_m": float(np.mean(points["height_m"])),
        "height_median_m": float(np.median(points["height_m"])),
        "range_median_m": float(np.median(points["range_m"])),
        "scan_angle_median_deg": float(np.median(points["scan_angle_deg"])),
    }


def distance_2d(a: dict[str, float], b: dict[str, float]) -> float:
    return float(math.hypot(float(b["easting_m"]) - float(a["easting_m"]), float(b["northing_m"]) - float(a["northing_m"])))


def distance_3d(a: dict[str, float], b: dict[str, float]) -> float:
    horizontal = distance_2d(a, b)
    dz = float(b["height_m"]) - float(a["height_m"])
    return float(math.hypot(horizontal, dz))


def seam_row(prev_seq: int, curr_seq: int, prev_snap: dict[str, Any], curr_snap: dict[str, Any]) -> dict[str, Any]:
    if not prev_snap.get("valid_count") or not curr_snap.get("valid_count"):
        return {
            "from_seq": prev_seq,
            "to_seq": curr_seq,
            "valid": False,
            "reason": "missing_valid_points",
        }
    prev_end = prev_snap["end"]
    curr_start = curr_snap["start"]
    prev_tail = prev_snap["tail"]
    curr_head = curr_snap["head"]
    tail_centroid = {
        "easting_m": float(prev_tail["easting_mean_m"]),
        "northing_m": float(prev_tail["northing_mean_m"]),
        "height_m": float(prev_tail["height_mean_m"]),
    }
    head_centroid = {
        "easting_m": float(curr_head["easting_mean_m"]),
        "northing_m": float(curr_head["northing_mean_m"]),
        "height_m": float(curr_head["height_mean_m"]),
    }
    return {
        "from_seq": prev_seq,
        "to_seq": curr_seq,
        "valid": True,
        "endpoint_time_gap_sec": float(curr_start["gps_time"] - prev_end["gps_time"]),
        "endpoint_horizontal_gap_m": distance_2d(prev_end, curr_start),
        "endpoint_3d_gap_m": distance_3d(prev_end, curr_start),
        "endpoint_height_delta_m": float(curr_start["height_m"] - prev_end["height_m"]),
        "tail_head_centroid_time_gap_sec": float(curr_head["gps_time_median"] - prev_tail["gps_time_median"]),
        "tail_head_centroid_horizontal_gap_m": distance_2d(tail_centroid, head_centroid),
        "tail_head_centroid_3d_gap_m": distance_3d(tail_centroid, head_centroid),
        "tail_head_height_mean_delta_m": float(curr_head["height_mean_m"] - prev_tail["height_mean_m"]),
        "tail_head_height_median_delta_m": float(curr_head["height_median_m"] - prev_tail["height_median_m"]),
        "tail_head_range_median_delta_m": float(curr_head["range_median_m"] - prev_tail["range_median_m"]),
        "tail_head_scan_angle_median_delta_deg": float(curr_head["scan_angle_median_deg"] - prev_tail["scan_angle_median_deg"]),
        "prev_tail_count": int(prev_tail["count"]),
        "curr_head_count": int(curr_head["count"]),
    }


def seam_fields() -> list[str]:
    return [
        "from_seq",
        "to_seq",
        "valid",
        "reason",
        "endpoint_time_gap_sec",
        "endpoint_horizontal_gap_m",
        "endpoint_3d_gap_m",
        "endpoint_height_delta_m",
        "tail_head_centroid_time_gap_sec",
        "tail_head_centroid_horizontal_gap_m",
        "tail_head_centroid_3d_gap_m",
        "tail_head_height_mean_delta_m",
        "tail_head_height_median_delta_m",
        "tail_head_range_median_delta_m",
        "tail_head_scan_angle_median_delta_deg",
        "prev_tail_count",
        "curr_head_count",
    ]


def gate_conclusion(per_file_rows: list[dict[str, Any]], seam_rows: list[dict[str, Any]], sample_limited: bool) -> tuple[str, str, bool]:
    min_pos_success = min(float(row["pos_success_rate"]) for row in per_file_rows) if per_file_rows else 0.0
    counts_ok = all(int(row["point_count_h5"]) > 0 for row in per_file_rows)
    valid_seams = [row for row in seam_rows if row.get("valid")]
    max_time_gap = max((abs(float(row["endpoint_time_gap_sec"])) for row in valid_seams), default=float("inf"))
    if sample_limited:
        return (
            "烟雾测试通过",
            "Stage 6L sample-limited diagnostic completed; run without --max-points-per-file for formal continuity results.",
            False,
        )
    if counts_ok and min_pos_success >= 0.99 and max_time_gap <= 0.2 and len(valid_seams) == max(len(per_file_rows) - 1, 0):
        return (
            "合理",
            "Continuous segment export completed with full POS coverage and no large time gap at file seams.",
            True,
        )
    return (
        "基本合理但需复核",
        "Continuous segment export completed, but count/POS/seam timing checks did not fully meet the 6L gate.",
        False,
    )


def write_report(payload: dict[str, Any]) -> None:
    gate = payload["gate"]
    rows = payload["per_file_summary"]
    seams = payload["seam_summary"]
    candidate = payload["stage6i_best_candidate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    per_file_lines = "\n".join(
        f"| {row['source_seq']} | {int(row['point_count_h5']):,} | {int(row['range_m_gt_30_count']):,} | "
        f"{float(row['pos_success_rate']):.6%} | {float(row['height_m_median']):.3f} | "
        f"{float(row['gps_time_min_sec']):.6f}-{float(row['gps_time_max_sec']):.6f} |"
        for row in rows
    )
    seam_lines = "\n".join(
        f"| {row.get('from_seq')}->{row.get('to_seq')} | {row.get('valid')} | "
        f"{float(row.get('endpoint_time_gap_sec', float('nan'))):.9f} | "
        f"{float(row.get('endpoint_horizontal_gap_m', float('nan'))):.3f} | "
        f"{float(row.get('tail_head_centroid_horizontal_gap_m', float('nan'))):.3f} | "
        f"{float(row.get('tail_head_height_median_delta_m', float('nan'))):.3f} |"
        for row in seams
    )
    content = f"""# Stage 6L CH1 LADM-II Continuous Segment Diagnostic

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Continuous segment H5 ready: {gate['continuous_segment_h5_ready']}

## Segment

- Selected files: `{payload['segment']['seq_start']:05d}` to `{payload['segment']['seq_end']:05d}`
- File count: {payload['segment']['file_count']}
- Sample limited: {payload['segment']['sample_limited']}
- Total points written to H5: {payload['aggregate']['total_points_h5']:,}
- Total `range_m > {payload['settings']['txt_min_range_m']:g} m` points: {payload['aggregate']['total_range_gt_min_count']:,}

## Applied LADM-II Candidate

- angle_direction: `{candidate['angle_direction']}`
- angle_offset_deg: {candidate['angle_offset_deg']}
- mirror_tilt_deg: {candidate['mirror_tilt_deg']}
- frame_rotation_deg: {candidate['frame_rotation_deg']}
- axis_mapping: `{candidate['axis_mapping']}`
- boresight roll/pitch/yaw deg: {candidate['boresight_roll_deg']}, {candidate['boresight_pitch_deg']}, {candidate['boresight_yaw_deg']}
- lever x/y/z m: {candidate['lever_x_m']:.6f}, {candidate['lever_y_m']:.6f}, {candidate['lever_z_m']:.6f}

## Per-File Summary

| seq | H5 points | range_gt_min | POS success | height median m | gps time sec |
|---:|---:|---:|---:|---:|---|
{per_file_lines}

## Seam Summary

| seam | valid | endpoint dt sec | endpoint horizontal m | centroid horizontal m | median height delta m |
|---|---|---:|---:|---:|---:|
{seam_lines}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Per-file summary CSV: `{payload['outputs']['per_file_summary_csv']}`
- Seam summary CSV: `{payload['outputs']['seam_summary_csv']}`
- CloudCompare TXT: `{payload['outputs'].get('cloudcompare_txt', 'not written')}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只处理 00111 后面的小连续段，不覆盖旧 H5/LAZ。
- 这些 H5/TXT 仍是诊断输出，不能直接作为最终生产 L3。
"""
    path = REPORT_DIR / "stage6l_ch1_ladm2_continuous_segment_diagnostic_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    candidate = load_json(STAGE6I_BEST)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    paths = find_l1_segment(args.start_seq, args.file_count)
    pos_time, _, _ = stage5.load_pos()

    per_file_rows: list[dict[str, Any]] = []
    seam_rows_out: list[dict[str, Any]] = []
    outputs_h5: list[str] = []
    previous_snapshot: dict[str, Any] | None = None
    previous_seq: int | None = None
    txt_path = OUT_DIR / f"stage6l_{args.start_seq:05d}_{args.start_seq + args.file_count - 1:05d}_ladm2_segment_cloudcompare.txt"
    write_txt = bool(args.write_cloudcompare_txt)
    txt_written = 0
    txt_header_needed = True
    if write_txt and txt_path.exists():
        txt_path.unlink()
    if args.txt_max_points > 0:
        base_txt_per_file = args.txt_max_points // len(paths)
        txt_remainder = args.txt_max_points % len(paths)
    else:
        base_txt_per_file = 0
        txt_remainder = 0

    if args.progress:
        print(f"Stage 6L selected files: {[path.name for path in paths]}", flush=True)
    for file_idx, path in enumerate(paths):
        seq = l1_sequence(path)
        if args.progress:
            print(f"Loading L1 {seq:05d}: {path}", flush=True)
        l1_full = stage6k.load_l1_full(path)
        source_count = int(l1_full["gnss"].size)
        if not args.keep_pos_uncovered:
            l1_full, kept_count = filter_l1_by_pos_coverage(l1_full, pos_time, args.low_confidence_sec)
            if args.progress and kept_count < source_count:
                print(f"POS-time filtered {seq:05d}: {source_count} -> {kept_count} points", flush=True)
        else:
            kept_count = source_count
        l1 = sample_l1_arrays(l1_full, args.max_points_per_file)
        if args.progress and args.max_points_per_file > 0 and int(l1["gnss"].size) < source_count:
            print(f"Sample-limited {seq:05d}: {source_count} -> {int(l1['gnss'].size)} points", flush=True)
        points, stats = stage6k.build_full_points(
            l1,
            calibration,
            candidate,
            args.txt_min_range_m,
            args.low_confidence_sec,
            args.progress,
        )
        points["source_seq"] = seq
        stats["source_point_count_l1"] = source_count
        stats["pos_time_filter_kept_count"] = kept_count
        h5_path = OUT_DIR / f"stage6l_{seq:05d}_ladm2_full_points.h5"
        if args.progress:
            print(f"Writing Stage 6L H5 for {seq:05d}: {h5_path}", flush=True)
        write_segment_h5(h5_path, path, points, candidate, stats)
        outputs_h5.append(str(h5_path))
        per_file_rows.append(per_file_row(seq, path, h5_path, stats))

        if write_txt:
            if args.txt_max_points > 0:
                per_file_max = base_txt_per_file + (1 if file_idx < txt_remainder else 0)
            else:
                per_file_max = 0
            min_range = None if args.txt_include_all_ranges else args.txt_min_range_m
            txt_written += append_cloudcompare_txt(txt_path, points, per_file_max, min_range, txt_header_needed)
            txt_header_needed = False

        snapshot = seam_snapshot(points, args.txt_min_range_m, args.seam_sample_points)
        if previous_snapshot is not None and previous_seq is not None:
            seam_rows_out.append(seam_row(previous_seq, seq, previous_snapshot, snapshot))
        previous_snapshot = snapshot
        previous_seq = seq
        del points, l1, l1_full
        gc.collect()

    per_file_csv = OUT_DIR / "per_file_summary.csv"
    seam_csv = OUT_DIR / "seam_summary.csv"
    write_csv(per_file_csv, per_file_rows, per_file_fields())
    write_csv(seam_csv, seam_rows_out, seam_fields())

    total_points = int(sum(int(row["point_count_h5"]) for row in per_file_rows))
    total_range_gt_min = int(sum(int(row["range_m_gt_30_count"]) for row in per_file_rows))
    conclusion, reason, ready = gate_conclusion(per_file_rows, seam_rows_out, args.max_points_per_file > 0)
    report_json = REPORT_DIR / "stage6l_ch1_ladm2_continuous_segment_diagnostic_report.json"
    outputs: dict[str, Any] = {
        "per_file_summary_csv": str(per_file_csv),
        "seam_summary_csv": str(seam_csv),
        "per_file_h5": outputs_h5,
        "report_json": str(report_json),
        "report_md": str(REPORT_DIR / "stage6l_ch1_ladm2_continuous_segment_diagnostic_report.md"),
    }
    if write_txt:
        outputs["cloudcompare_txt"] = str(txt_path)
    payload = {
        "stage_name": "stage6l_ch1_ladm2_continuous_segment_diagnostic",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "l1_dir": str(L1_DIR),
            "stage6i_best_candidate": str(STAGE6I_BEST),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
        },
        "settings": {
            "txt_min_range_m": args.txt_min_range_m,
            "txt_max_points": args.txt_max_points,
            "txt_include_all_ranges": args.txt_include_all_ranges,
            "low_confidence_sec": args.low_confidence_sec,
            "seam_sample_points": args.seam_sample_points,
            "max_points_per_file": args.max_points_per_file,
            "keep_pos_uncovered": args.keep_pos_uncovered,
        },
        "segment": {
            "seq_start": args.start_seq,
            "seq_end": args.start_seq + args.file_count - 1,
            "file_count": args.file_count,
            "sample_limited": args.max_points_per_file > 0,
            "source_files": [str(path) for path in paths],
        },
        "fixed_parameters": {
            "zero_offset_m": stage6e.ZERO_OFFSET_M,
            "roll_sign": stage6e.ROLL_SIGN,
            "pitch_sign": stage6e.PITCH_SIGN,
            "heading_sign": stage6e.HEADING_SIGN,
            "heading_convention": stage6e.HEADING_CONVENTION,
            "rotation_order": stage6e.ROTATION_ORDER,
            "rotation_transpose": stage6e.ROTATION_TRANSPOSE,
        },
        "stage6i_best_candidate": candidate,
        "aggregate": {
            "total_points_h5": total_points,
            "total_range_gt_min_count": total_range_gt_min,
            "cloudcompare_txt_points": txt_written,
        },
        "per_file_summary": per_file_rows,
        "seam_summary": seam_rows_out,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "continuous_segment_h5_ready": ready,
            "criteria": {
                "min_pos_success_rate": 0.99,
                "max_abs_endpoint_time_gap_sec": 0.2,
                "all_seams_valid": True,
            },
        },
        "outputs": outputs,
    }
    write_json(report_json, payload)
    write_report(payload)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "segment": payload["segment"],
                    "aggregate": payload["aggregate"],
                    "per_file_summary": per_file_rows,
                    "seam_summary": seam_rows_out,
                    "outputs": outputs,
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6L CH1 LADM-II continuous segment diagnostic.")
    parser.add_argument("--start-seq", type=int, default=114, help="First L1 sequence to process; default skips corrupted 00113 timing.")
    parser.add_argument("--file-count", type=int, default=5)
    parser.add_argument("--write-cloudcompare-txt", action="store_true")
    parser.add_argument("--txt-max-points", type=int, default=500_000, help="0 writes all selected points.")
    parser.add_argument("--txt-min-range-m", type=float, default=30.0)
    parser.add_argument("--txt-include-all-ranges", action="store_true")
    parser.add_argument("--low-confidence-sec", type=float, default=0.2)
    parser.add_argument("--keep-pos-uncovered", action="store_true", help="Keep points outside confident POS time coverage.")
    parser.add_argument("--seam-sample-points", type=int, default=5000)
    parser.add_argument("--max-points-per-file", type=int, default=0, help="Diagnostic smoke-test limiter; 0 uses all points.")
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
