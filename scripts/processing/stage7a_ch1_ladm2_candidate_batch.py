from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import os
import re
import shutil
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import CRS

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage6e_ch1_bias_validation as stage6e
import stage6k_ch1_ladm2_full_00111_export as stage6k


ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_PROJECT_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3",
    )
)
DEFAULT_OUTPUT_ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_STAGE_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0",
    )
)
STAGE6I_BEST = ROOT / "outputs" / "qc" / "stage6i_ladm2_scan_geometry_diagnostic" / "best_candidate.json"
STAGE6N_REPORT = ROOT / "metadata" / "stage_reports" / "stage6n_ch1_ladm2_continuous_qc_report.json"
STAGE6M_REPORT = ROOT / "metadata" / "stage_reports" / "stage6m_00113_timestamp_audit_report.json"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
CRS_EPSG = 32651

METHOD_REGISTRY = [
    {
        "method_id": "CAO2017_LADM2_4_7_4_14",
        "method_name": "LADM-II mirror normal and reflected beam scan geometry",
        "source_type": "doctoral_thesis",
        "source_reference": "Cao 2017 section 4.4.2, formulas 4-7 to 4-14",
        "used_for_delete_or_transform": "yes, production-candidate transform",
    },
    {
        "method_id": "STAGE6I_BEST_CANDIDATE",
        "method_name": "Stage 6I selected LADM-II calibration candidate",
        "source_type": "project_diagnostic_parameter",
        "source_reference": str(STAGE6I_BEST),
        "used_for_delete_or_transform": "yes, production-candidate transform",
    },
    {
        "method_id": "STAGE7A_RANGE_LIMIT",
        "method_name": "Limited production-candidate batch range",
        "source_type": "user_scope_rule",
        "source_reference": "User requested Stage 7A only for L1 sequences 00050-00150 and output under C:\\proj_denoising_f3_2.0",
        "used_for_delete_or_transform": "no, output scope only",
    },
    {
        "method_id": "BAD_TIME_ISOLATION",
        "method_name": "Skip non-OK timestamp files",
        "source_type": "project_gate_rule",
        "source_reference": "Stage 5 manifest and Stage 6M timestamp audit; do not repair or process corrupted timestamps here",
        "used_for_delete_or_transform": "yes, skip bad-time files",
    },
]

POS_EXTRA_DTYPE = [
    ("pos_time_sec", "f8"),
    ("pos_easting", "f8"),
    ("pos_northing", "f8"),
    ("pos_height", "f8"),
    ("pos_roll", "f8"),
    ("pos_pitch", "f8"),
    ("pos_heading", "f8"),
    ("pos_interp_dt", "f8"),
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


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def cap_id(path: Path) -> str:
    match = re.search(r"L1_cap_(\d{5})_([0-9]{14})\.h5$", path.name)
    if not match:
        raise ValueError(f"Cannot parse cap id from {path}")
    return f"{match.group(1)}_{match.group(2)}"


def output_paths(output_root: Path, seq: int) -> dict[str, Path]:
    name = f"stage7a_{seq:05d}_ch1_ladm2"
    return {
        "h5": output_root / "h5" / f"{name}_full_points.h5",
        "laz": output_root / "laz" / f"{name}_full_points.laz",
        "txt": output_root / "txt" / f"{name}_cloudcompare.txt",
    }


def safe_temp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def ensure_can_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def replace_temp(temp_path: Path, final_path: Path, overwrite: bool) -> None:
    if final_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {final_path}")
    if final_path.exists() and overwrite:
        final_path.unlink()
    temp_path.replace(final_path)


def finite_stats(values: np.ndarray) -> dict[str, float | int]:
    return stage6k.finite_stats(values)


def add_pos_match_fields(points: np.ndarray, pos_time: np.ndarray, pos: dict[str, np.ndarray]) -> np.ndarray:
    existing = set(points.dtype.names or ())
    missing = [item for item in POS_EXTRA_DTYPE if item[0] not in existing]
    if not missing:
        return points

    dtype = np.dtype(points.dtype.descr + missing)
    enriched = np.empty(points.shape, dtype=dtype)
    for name in points.dtype.names or ():
        enriched[name] = points[name]

    lidar_time = points["gps_time"].astype(np.float64)
    interp_time = np.clip(lidar_time, pos_time[0], pos_time[-1])
    enriched["pos_time_sec"] = interp_time
    enriched["pos_easting"] = np.interp(interp_time, pos_time, pos["EASTING"])
    enriched["pos_northing"] = np.interp(interp_time, pos_time, pos["NORTHING"])
    enriched["pos_height"] = np.interp(interp_time, pos_time, pos["HEIGHT"])
    enriched["pos_roll"] = np.interp(interp_time, pos_time, pos["ROLL"])
    enriched["pos_pitch"] = np.interp(interp_time, pos_time, pos["PITCH"])
    enriched["pos_heading"] = pipe.interp_heading_deg(pos_time, pos["HEADING"], interp_time)
    enriched["pos_interp_dt"] = pipe.nearest_time_delta_abs(pos_time, interp_time)
    return enriched


def export_mask(points: np.ndarray, min_range_m: float, pos_good_only: bool) -> np.ndarray:
    mask = (
        np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
        & np.isfinite(points["gps_time"])
        & np.isfinite(points["range_m"])
        & (points["range_m"] >= min_range_m)
    )
    if pos_good_only:
        mask &= points["pos_quality_flag"] == 0
    return mask


def selected_points(points: np.ndarray, min_range_m: float, pos_good_only: bool, max_points: int) -> np.ndarray:
    idx = np.flatnonzero(export_mask(points, min_range_m, pos_good_only)).astype(np.int64)
    if max_points > 0 and idx.size > max_points:
        idx = idx[np.linspace(0, idx.size - 1, max_points, dtype=np.int64)]
    return points[idx]


def write_stage7a_h5(
    path: Path,
    source_l1: Path,
    points: np.ndarray,
    candidate: dict[str, Any],
    stats: dict[str, Any],
    overwrite: bool,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_can_write(path, overwrite)
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()
    with h5py.File(temp_path, "w") as h5:
        grp = h5.create_group("STAGE7A")
        ch1 = grp.create_group("CH1")
        ch1.create_dataset("full_points", data=points, compression="gzip", compression_opts=4, chunks=True)
        meta = h5.create_group("metadata")
        proc = meta.create_group("processing")
        pipe.write_str_attr(proc, "stage", "stage7a_ch1_ladm2_candidate_batch")
        pipe.write_str_attr(proc, "source_l1", str(source_l1))
        pipe.write_str_attr(proc, "schema", "stage7a_ch1_ladm2_candidate_full_points_with_pos_match_fields")
        pipe.write_str_attr(proc, "crs", f"EPSG:{CRS_EPSG}")
        pipe.write_str_attr(proc, "production_status", "production_candidate_not_final_l3")
        proc.attrs["lidar_time_offset_sec"] = pipe.DEFAULT_TIME_OFFSET_SEC
        proc.attrs["zero_offset_m"] = stage6e.ZERO_OFFSET_M
        proc.attrs["point_count_h5"] = stats["point_count_h5"]
        proc.attrs["range_m_gt_30_count"] = stats["range_m_gt_30_count"]
        proc.attrs["pos_success_rate"] = stats["pos_success_rate"]
        proc.attrs["has_pos_match_fields"] = True
        cand_grp = meta.create_group("stage6i_best_candidate")
        for key, value in candidate.items():
            if isinstance(value, str):
                pipe.write_str_attr(cand_grp, key, value)
            elif isinstance(value, (int, float, np.integer, np.floating, np.bool_)):
                cand_grp.attrs[key] = value
            elif isinstance(value, list):
                cand_grp.create_dataset(key, data=np.asarray(value))
    replace_temp(temp_path, path, overwrite)


def write_cloudcompare_txt(
    path: Path,
    points: np.ndarray,
    min_range_m: float,
    pos_good_only: bool,
    max_points: int,
    overwrite: bool,
    chunk_size: int,
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_can_write(path, overwrite)
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()
    selected = selected_points(points, min_range_m, pos_good_only, max_points)
    with temp_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("X Y Z source_seq height_m gps_time range_m scan_angle_deg point_index pos_quality_flag\n")
        for start in range(0, selected.size, chunk_size):
            block = selected[start : start + chunk_size]
            out = np.column_stack(
                [
                    block["easting_m"],
                    block["northing_m"],
                    block["height_m"],
                    block["source_seq"],
                    block["height_m"],
                    block["gps_time"],
                    block["range_m"],
                    block["scan_angle_deg"],
                    block["point_index"],
                    block["pos_quality_flag"],
                ]
            )
            np.savetxt(
                f,
                out,
                fmt=["%.9f", "%.9f", "%.9f", "%d", "%.9f", "%.9f", "%.9f", "%.9f", "%d", "%d"],
                delimiter=" ",
            )
    replace_temp(temp_path, path, overwrite)
    return int(selected.size)


def write_laz(
    path: Path,
    points: np.ndarray,
    min_range_m: float,
    pos_good_only: bool,
    max_points: int,
    overwrite: bool,
) -> int:
    try:
        import laspy
    except ModuleNotFoundError as exc:
        raise RuntimeError("laspy is required to write LAZ. Install laspy and lazrs.") from exc

    selected = selected_points(points, min_range_m, pos_good_only, max_points)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_can_write(path, overwrite)
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()

    header = laspy.LasHeader(point_format=6, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    if selected.size:
        header.offsets = np.array(
            [
                math.floor(float(np.min(selected["easting_m"]))),
                math.floor(float(np.min(selected["northing_m"]))),
                math.floor(float(np.min(selected["height_m"]))),
            ]
        )
    header.add_crs(CRS.from_epsg(CRS_EPSG))
    for name, dtype, description in [
        ("source_seq", np.uint16, "L1 source sequence number"),
        ("range_m", np.float32, "Calibrated range in meters"),
        ("scan_angle_deg", np.float32, "Scan angle in degrees"),
        ("point_index", np.uint32, "Point index inside source L1 CH1"),
        ("pos_quality_flag", np.uint16, "POS quality flag"),
    ]:
        header.add_extra_dim(laspy.ExtraBytesParams(name=name, type=dtype, description=description))

    las = laspy.LasData(header)
    las.x = selected["easting_m"].astype(np.float64)
    las.y = selected["northing_m"].astype(np.float64)
    las.z = selected["height_m"].astype(np.float64)
    las.gps_time = selected["gps_time"].astype(np.float64)
    las.source_seq = selected["source_seq"].astype(np.uint16)
    las.range_m = selected["range_m"].astype(np.float32)
    las.scan_angle_deg = selected["scan_angle_deg"].astype(np.float32)
    las.point_index = selected["point_index"].astype(np.uint32)
    las.pos_quality_flag = selected["pos_quality_flag"].astype(np.uint16)
    las.write(temp_path)
    replace_temp(temp_path, path, overwrite)
    return int(selected.size)


def output_size(path: Path) -> int:
    return int(path.stat().st_size) if path.exists() else 0


def processing_rows_for_scope(start_seq: int, end_seq: int) -> list[stage5.FileInfo]:
    files = stage5.read_manifest(stage5.MANIFEST)
    return [item for item in files if start_seq <= item.seq <= end_seq]


def row_from_skip(info: stage5.FileInfo, status: str, reason: str, paths: dict[str, Path]) -> dict[str, Any]:
    return {
        "seq": info.seq,
        "source_l1": rel(info.path),
        "source_manifest_status": info.status,
        "status": status,
        "reason": reason,
        "point_count_l1": info.point_count,
        "point_count_h5": 0,
        "laz_point_count": 0,
        "txt_point_count": 0,
        "pos_success_rate": "",
        "gps_time_min_sec": "",
        "gps_time_max_sec": "",
        "range_m_gt_30_count": "",
        "height_median_m": "",
        "h5_path": rel(paths["h5"]),
        "laz_path": rel(paths["laz"]),
        "txt_path": rel(paths["txt"]),
        "h5_size_bytes": 0,
        "laz_size_bytes": 0,
        "txt_size_bytes": 0,
    }


def row_from_success(
    info: stage5.FileInfo,
    stats: dict[str, Any],
    paths: dict[str, Path],
    laz_count: int,
    txt_count: int,
) -> dict[str, Any]:
    return {
        "seq": info.seq,
        "source_l1": rel(info.path),
        "source_manifest_status": info.status,
        "status": "PROCESSED",
        "reason": "",
        "point_count_l1": stats["point_count_l1"],
        "point_count_h5": stats["point_count_h5"],
        "laz_point_count": laz_count,
        "txt_point_count": txt_count,
        "pos_success_rate": stats["pos_success_rate"],
        "gps_time_min_sec": stats["gps_time_sec"]["min"],
        "gps_time_max_sec": stats["gps_time_sec"]["max"],
        "range_m_gt_30_count": stats["range_m_gt_30_count"],
        "height_median_m": stats["height_m"]["median"],
        "h5_path": rel(paths["h5"]),
        "laz_path": rel(paths["laz"]),
        "txt_path": rel(paths["txt"]),
        "h5_size_bytes": output_size(paths["h5"]),
        "laz_size_bytes": output_size(paths["laz"]),
        "txt_size_bytes": output_size(paths["txt"]),
    }


def manifest_fields() -> list[str]:
    return [
        "seq",
        "source_l1",
        "source_manifest_status",
        "status",
        "reason",
        "point_count_l1",
        "point_count_h5",
        "laz_point_count",
        "txt_point_count",
        "pos_success_rate",
        "gps_time_min_sec",
        "gps_time_max_sec",
        "range_m_gt_30_count",
        "height_median_m",
        "h5_path",
        "laz_path",
        "txt_path",
        "h5_size_bytes",
        "laz_size_bytes",
        "txt_size_bytes",
    ]


def write_report(payload: dict[str, Any], output_root: Path) -> None:
    aggregate = payload["aggregate"]
    gate = payload["gate"]
    outputs = payload["outputs"]
    skipped = [row for row in payload["manifest_rows"] if row["status"].startswith("SKIPPED")]
    processed_preview = [row for row in payload["manifest_rows"] if row["status"] == "PROCESSED"][:10]
    skipped_lines = "\n".join(
        f"| {row['seq']:05d} | {row['source_manifest_status']} | {row['reason']} |" for row in skipped
    )
    processed_lines = "\n".join(
        f"| {row['seq']:05d} | {int(row['point_count_h5']):,} | {int(row['laz_point_count']):,} | "
        f"{float(row['pos_success_rate']):.6%} | {float(row['height_median_m']):.3f} |"
        for row in processed_preview
    )
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 7A CH1 LADM-II Candidate Batch

## Gate

- Conclusion: {gate['conclusion']}
- Ready for review: {gate['ready_for_review']}
- Reason: {gate['reason']}

## Scope

- Sequence range: `{payload['scope']['start_seq']:05d}` to `{payload['scope']['end_seq']:05d}` inclusive.
- Requested output root: `{output_root}`
- Stage 6G legacy route: skipped.
- Non-OK timestamp files: skipped, not repaired.
- H5 contains full points plus POS interpolation fields. LAZ/TXT use the export filter described below.

## H5 Chain Fields

Each Stage 7A H5 now carries the full diagnostic chain:

- L1 timing/range/scan: `gnss_sec_raw`, `gps_time`, `range_before_m`, `range_m`, `coder`, `scan_angle_deg`
- L2 body/FRD: `frd_x_m`, `frd_y_m`, `frd_z_m`
- POS match: `pos_time_sec`, `pos_easting`, `pos_northing`, `pos_height`, `pos_roll`, `pos_pitch`, `pos_heading`, `pos_interp_dt`
- NED offsets: `north_offset_m`, `east_offset_m`, `down_offset_m`
- Final UTM/geographic coordinates: `easting_m`, `northing_m`, `height_m`, `lon`, `lat`

## Export Filter

- export_min_range_m: {payload['settings']['export_min_range_m']}
- export_pos_good_only: {payload['settings']['export_pos_good_only']}
- laz_max_points_per_file: {payload['settings']['laz_max_points_per_file']}
- txt_max_points_per_file: {payload['settings']['txt_max_points_per_file']}

## Aggregate

- Files in requested range: {aggregate['files_in_scope']}
- Processed files: {aggregate['processed_files']}
- Skipped files: {aggregate['skipped_files']}
- Total H5 points: {aggregate['total_h5_points']:,}
- Total LAZ points: {aggregate['total_laz_points']:,}
- Total TXT points: {aggregate['total_txt_points']:,}
- Output size bytes: {aggregate['total_output_size_bytes']:,}

## Processed Preview

| seq | H5 points | LAZ points | POS success | height median m |
|---:|---:|---:|---:|---:|
{processed_lines}

## Skipped Files

| seq | manifest status | reason |
|---:|---|---|
{skipped_lines}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Manifest CSV: `{outputs['manifest_csv']}`
- Manifest JSON: `{outputs['manifest_json']}`
- Report JSON: `{outputs['report_json']}`
- H5 directory: `{outputs['h5_dir']}`
- LAZ directory: `{outputs['laz_dir']}`
- TXT directory: `{outputs['txt_dir']}`

## Stop Rule

Stage 7A is a production candidate batch, not a final deliverable. Do not merge skipped bad-time files into the candidate set unless a separate time-repair stage is approved and clearly marked.
"""
    report_md_output = output_root / "reports" / "stage7a_ch1_ladm2_candidate_batch_report.md"
    report_md_output.parent.mkdir(parents=True, exist_ok=True)
    report_md_output.write_text(content, encoding="utf-8-sig")
    report_md_project = REPORT_DIR / "stage7a_ch1_ladm2_candidate_batch_report.md"
    report_md_project.parent.mkdir(parents=True, exist_ok=True)
    report_md_project.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    output_root = args.output_root
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "h5").mkdir(parents=True, exist_ok=True)
    (output_root / "laz").mkdir(parents=True, exist_ok=True)
    (output_root / "txt").mkdir(parents=True, exist_ok=True)
    (output_root / "manifest").mkdir(parents=True, exist_ok=True)
    (output_root / "reports").mkdir(parents=True, exist_ok=True)

    candidate = stage6k.load_json(STAGE6I_BEST)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    pos_time, pos, _ = stage5.load_pos()
    files = processing_rows_for_scope(args.start_seq, args.end_seq)
    if args.limit > 0:
        files = files[: args.limit]
    stage6n_report = load_json(STAGE6N_REPORT)
    stage6m_report = load_json(STAGE6M_REPORT)

    rows: list[dict[str, Any]] = []
    for index, info in enumerate(files, start=1):
        paths = output_paths(output_root, info.seq)
        if args.progress:
            print(f"[{index}/{len(files)}] Stage 7A seq {info.seq:05d}: {info.path.name}", flush=True)
        if info.status != "OK" and not args.include_non_ok:
            reason = info.reason or f"manifest status is {info.status}"
            rows.append(row_from_skip(info, "SKIPPED_BAD_TIME", reason, paths))
            if args.progress:
                print(f"  skipped: {reason}", flush=True)
            continue
        if not args.overwrite and any(path.exists() for path in paths.values()):
            rows.append(row_from_skip(info, "SKIPPED_EXISTS", "one or more output files already exist; use --overwrite to regenerate", paths))
            if args.progress:
                print("  skipped: output exists", flush=True)
            continue
        if args.dry_run:
            rows.append(row_from_skip(info, "DRY_RUN", "dry run only; no output written", paths))
            continue

        try:
            l1 = stage6k.load_l1_full(info.path)
            points, stats = stage6k.build_full_points(
                l1,
                calibration,
                candidate,
                args.export_min_range_m,
                args.low_confidence_sec,
                args.progress and args.verbose_geometry,
            )
            points["source_seq"] = info.seq
            points = add_pos_match_fields(points, pos_time, pos)
            stats["source_point_count_l1"] = int(l1["gnss"].size)

            if args.progress:
                print(f"  writing H5: {paths['h5']}", flush=True)
            write_stage7a_h5(paths["h5"], info.path, points, candidate, stats, args.overwrite)

            laz_count = 0
            if args.write_laz:
                if args.progress:
                    print(f"  writing LAZ: {paths['laz']}", flush=True)
                laz_count = write_laz(
                    paths["laz"],
                    points,
                    args.export_min_range_m,
                    args.export_pos_good_only,
                    args.laz_max_points_per_file,
                    args.overwrite,
                )

            txt_count = 0
            if args.write_txt:
                if args.progress:
                    print(f"  writing TXT: {paths['txt']}", flush=True)
                txt_count = write_cloudcompare_txt(
                    paths["txt"],
                    points,
                    args.export_min_range_m,
                    args.export_pos_good_only,
                    args.txt_max_points_per_file,
                    args.overwrite,
                    args.txt_chunk_size,
                )

            rows.append(row_from_success(info, stats, paths, laz_count, txt_count))
            del l1, points
            gc.collect()
        except Exception as exc:
            rows.append(row_from_skip(info, "FAILED", f"{type(exc).__name__}: {exc}", paths))
            if args.stop_on_error:
                raise
            if args.progress:
                print(f"  failed: {type(exc).__name__}: {exc}", flush=True)

    manifest_csv = output_root / "manifest" / "stage7a_ch1_ladm2_00050_00150_manifest.csv"
    manifest_json = output_root / "manifest" / "stage7a_ch1_ladm2_00050_00150_manifest.json"
    report_json_output = output_root / "reports" / "stage7a_ch1_ladm2_candidate_batch_report.json"
    report_json_project = REPORT_DIR / "stage7a_ch1_ladm2_candidate_batch_report.json"
    write_csv(manifest_csv, rows, manifest_fields())

    processed = [row for row in rows if row["status"] == "PROCESSED"]
    skipped = [row for row in rows if row["status"] != "PROCESSED"]
    total_output_size = int(
        sum(int(row.get("h5_size_bytes") or 0) + int(row.get("laz_size_bytes") or 0) + int(row.get("txt_size_bytes") or 0) for row in rows)
    )
    gate_ready = bool(processed) and not any(row["status"] == "FAILED" for row in rows)
    payload = {
        "stage_name": "stage7a_ch1_ladm2_candidate_batch",
        "method_registry": METHOD_REGISTRY,
        "scope": {
            "start_seq": args.start_seq,
            "end_seq": args.end_seq,
            "inclusive_count": args.end_seq - args.start_seq + 1,
            "processed_only_manifest_status": "OK" if not args.include_non_ok else "all",
        },
        "settings": {
            "output_root": str(output_root),
            "write_laz": args.write_laz,
            "write_txt": args.write_txt,
            "export_min_range_m": args.export_min_range_m,
            "export_pos_good_only": args.export_pos_good_only,
            "laz_max_points_per_file": args.laz_max_points_per_file,
            "txt_max_points_per_file": args.txt_max_points_per_file,
            "low_confidence_sec": args.low_confidence_sec,
            "overwrite": args.overwrite,
            "include_non_ok": args.include_non_ok,
            "dry_run": args.dry_run,
        },
        "prior_gates": {
            "stage6n_gate": stage6n_report.get("gate", {}),
            "stage6m_gate": stage6m_report.get("gate", {}),
            "stage6g_status": "skipped",
        },
        "stage6i_best_candidate": candidate,
        "aggregate": {
            "files_in_scope": len(rows),
            "processed_files": len(processed),
            "skipped_files": len(skipped),
            "total_h5_points": int(sum(int(row.get("point_count_h5") or 0) for row in processed)),
            "total_laz_points": int(sum(int(row.get("laz_point_count") or 0) for row in processed)),
            "total_txt_points": int(sum(int(row.get("txt_point_count") or 0) for row in processed)),
            "total_output_size_bytes": total_output_size,
            "skipped_by_status": {
                status: int(sum(1 for row in skipped if row["status"] == status)) for status in sorted({row["status"] for row in skipped})
            },
        },
        "gate": {
            "conclusion": "READY_FOR_REVIEW" if gate_ready else "REVIEW",
            "reason": "Stage 7A candidate batch completed without failed files." if gate_ready else "Stage 7A completed with no processed files or at least one failed file.",
            "ready_for_review": gate_ready,
        },
        "manifest_rows": rows,
        "outputs": {
            "manifest_csv": str(manifest_csv),
            "manifest_json": str(manifest_json),
            "report_json": str(report_json_output),
            "report_md": str(output_root / "reports" / "stage7a_ch1_ladm2_candidate_batch_report.md"),
            "h5_dir": str(output_root / "h5"),
            "laz_dir": str(output_root / "laz"),
            "txt_dir": str(output_root / "txt"),
        },
    }
    write_json(manifest_json, payload)
    write_json(report_json_output, payload)
    write_json(report_json_project, payload)
    write_report(payload, output_root)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "scope": payload["scope"],
                    "aggregate": payload["aggregate"],
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 7A CH1 LADM-II production-candidate batch for a limited L1 sequence range.")
    parser.add_argument("--start-seq", type=int, default=50)
    parser.add_argument("--end-seq", type=int, default=150)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--write-laz", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-txt", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--export-min-range-m", type=float, default=0.0)
    parser.add_argument("--export-pos-good-only", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--laz-max-points-per-file", type=int, default=0, help="0 writes all selected points.")
    parser.add_argument("--txt-max-points-per-file", type=int, default=0, help="0 writes all selected points.")
    parser.add_argument("--txt-chunk-size", type=int, default=200_000)
    parser.add_argument("--low-confidence-sec", type=float, default=0.2)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--include-non-ok", action="store_true", help="Process manifest non-OK files; not recommended.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process only the first N in-scope manifest rows.")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--verbose-geometry", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
