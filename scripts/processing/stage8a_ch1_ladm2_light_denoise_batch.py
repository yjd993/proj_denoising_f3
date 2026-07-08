from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import os
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import CRS


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
REPORT_DIR = ROOT / "metadata" / "stage_reports"
CRS_EPSG = 32651

METHOD_REGISTRY = [
    {
        "method_id": "STAGE8A_BASIC_VALIDITY",
        "method_name": "Basic finite/POS/range validity filter",
        "source_type": "project_filter_rule",
        "source_reference": "Keep finite UTM coordinates, POS-good points, and range_m >= configured minimum",
        "used_for_delete_or_transform": "yes, denoise candidate point removal",
    },
    {
        "method_id": "STAGE8A_HEIGHT_QUANTILE_FENCE",
        "method_name": "Conservative per-file height quantile fence",
        "source_type": "project_filter_rule",
        "source_reference": "Remove only extreme height tails after basic validity filtering",
        "used_for_delete_or_transform": "yes, denoise candidate point removal",
    },
    {
        "method_id": "STAGE8A_GRID_DENSITY",
        "method_name": "Approximate 2D grid neighborhood density filter",
        "source_type": "project_filter_rule",
        "source_reference": "Remove isolated spatial speckles using 3x3 cell neighborhood counts",
        "used_for_delete_or_transform": "yes, denoise candidate point removal",
    },
    {
        "method_id": "STAGE8A_LOCAL_HEIGHT_ROBUST",
        "method_name": "Local grid robust height outlier filter",
        "source_type": "project_filter_rule",
        "source_reference": "Within sufficiently populated XY cells, remove large height deviations from local median",
        "used_for_delete_or_transform": "yes, denoise candidate point removal",
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


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def ensure_can_write(path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")


def safe_temp_path(path: Path) -> Path:
    return path.with_name(path.name + ".tmp")


def replace_temp(temp_path: Path, final_path: Path, overwrite: bool) -> None:
    if final_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {final_path}")
    if final_path.exists() and overwrite:
        final_path.unlink()
    temp_path.replace(final_path)


def output_paths(output_root: Path, seq: int) -> dict[str, Path]:
    base = output_root / "stage8a_ladm2_light_denoised"
    name = f"stage8a_{seq:05d}_ch1_ladm2_light_denoised"
    return {
        "h5": base / "h5" / f"{name}.h5",
        "laz": base / "laz" / f"{name}.laz",
        "sample_txt": base / "txt_sample" / f"{name}_cloudcompare_sample.txt",
    }


def finite_stats(values: np.ndarray) -> dict[str, float | int]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flat[np.isfinite(flat)]
    out: dict[str, float | int] = {
        "count": int(flat.size),
        "finite_count": int(finite.size),
        "min": float("nan"),
        "p01": float("nan"),
        "p05": float("nan"),
        "median": float("nan"),
        "p95": float("nan"),
        "p99": float("nan"),
        "max": float("nan"),
        "mean": float("nan"),
        "std": float("nan"),
    }
    if finite.size:
        out.update(
            {
                "min": float(np.min(finite)),
                "p01": float(np.percentile(finite, 1)),
                "p05": float(np.percentile(finite, 5)),
                "median": float(np.median(finite)),
                "p95": float(np.percentile(finite, 95)),
                "p99": float(np.percentile(finite, 99)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "std": float(np.std(finite)),
            }
        )
    return out


def base_valid_mask(points: np.ndarray, min_range_m: float, max_range_m: float) -> np.ndarray:
    mask = (
        np.isfinite(points["easting_m"])
        & np.isfinite(points["northing_m"])
        & np.isfinite(points["height_m"])
        & np.isfinite(points["gps_time"])
        & np.isfinite(points["range_m"])
        & np.isfinite(points["scan_angle_deg"])
        & (points["pos_quality_flag"] == 0)
        & (points["range_m"] >= min_range_m)
    )
    if np.isfinite(max_range_m):
        mask &= points["range_m"] <= max_range_m
    return mask


def height_quantile_mask(points: np.ndarray, current: np.ndarray, low_pct: float, high_pct: float, padding_m: float) -> tuple[np.ndarray, dict[str, Any]]:
    keep = current.copy()
    values = points["height_m"][current].astype(np.float64)
    if values.size == 0:
        return keep, {"height_low_m": float("nan"), "height_high_m": float("nan"), "height_quantile_deleted_count": 0}
    low = float(np.percentile(values, low_pct)) - padding_m
    high = float(np.percentile(values, high_pct)) + padding_m
    before = int(np.count_nonzero(keep))
    keep &= (points["height_m"] >= low) & (points["height_m"] <= high)
    return keep, {
        "height_low_m": low,
        "height_high_m": high,
        "height_quantile_deleted_count": int(before - np.count_nonzero(keep)),
    }


def cell_keys(points: np.ndarray, mask: np.ndarray, grid_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    idx = np.flatnonzero(mask).astype(np.int64)
    if idx.size == 0:
        return idx, np.asarray([], dtype=np.int64), np.asarray([], dtype=np.int64), np.asarray([], dtype=np.int64), 0
    x = np.floor(points["easting_m"][idx].astype(np.float64) / grid_m).astype(np.int64)
    y = np.floor(points["northing_m"][idx].astype(np.float64) / grid_m).astype(np.int64)
    min_x = int(np.min(x))
    min_y = int(np.min(y))
    x = x - min_x
    y = y - min_y
    width = int(np.max(y)) + 3
    keys = x * width + y
    return idx, keys, x, y, width


def density_mask(points: np.ndarray, current: np.ndarray, grid_m: float, min_neighbors: int) -> tuple[np.ndarray, dict[str, Any]]:
    keep = current.copy()
    idx, keys, _, _, width = cell_keys(points, current, grid_m)
    if idx.size == 0:
        return keep, {"density_deleted_count": 0, "density_valid_count": 0}
    unique, inverse, counts = np.unique(keys, return_inverse=True, return_counts=True)
    neighbor_counts = np.zeros(unique.shape[0], dtype=np.int32)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            wanted = unique + dx * width + dy
            pos = np.searchsorted(unique, wanted)
            ok = (pos >= 0) & (pos < unique.size)
            matched = np.zeros(unique.shape[0], dtype=bool)
            matched[ok] = unique[pos[ok]] == wanted[ok]
            neighbor_counts[matched] += counts[pos[matched]]
    point_neighbors = neighbor_counts[inverse]
    deleted_local = point_neighbors < min_neighbors
    keep[idx[deleted_local]] = False
    return keep, {
        "density_deleted_count": int(np.count_nonzero(deleted_local)),
        "density_valid_count": int(idx.size),
        "density_unique_cell_count": int(unique.size),
    }


def local_height_mask(
    points: np.ndarray,
    current: np.ndarray,
    grid_m: float,
    min_cell_count: int,
    mad_multiplier: float,
    abs_floor_m: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    keep = current.copy()
    idx, keys, _, _, _ = cell_keys(points, current, grid_m)
    if idx.size == 0:
        return keep, {"local_height_deleted_count": 0, "local_height_checked_cell_count": 0}
    order = np.argsort(keys, kind="mergesort")
    sorted_idx = idx[order]
    sorted_keys = keys[order]
    starts = np.r_[0, np.flatnonzero(sorted_keys[1:] != sorted_keys[:-1]) + 1]
    ends = np.r_[starts[1:], sorted_idx.size]
    deleted = np.zeros(sorted_idx.size, dtype=bool)
    checked_cells = 0
    for start, end in zip(starts, ends):
        count = int(end - start)
        if count < min_cell_count:
            continue
        checked_cells += 1
        local_idx = sorted_idx[start:end]
        h = points["height_m"][local_idx].astype(np.float64)
        median = float(np.median(h))
        mad = float(np.median(np.abs(h - median)))
        sigma = 1.4826 * mad
        threshold = max(abs_floor_m, mad_multiplier * sigma)
        deleted[start:end] = np.abs(h - median) > threshold
    keep[sorted_idx[deleted]] = False
    return keep, {
        "local_height_deleted_count": int(np.count_nonzero(deleted)),
        "local_height_checked_cell_count": int(checked_cells),
    }


def denoise_mask(points: np.ndarray, args: argparse.Namespace) -> tuple[np.ndarray, dict[str, Any]]:
    total = int(points.size)
    base = base_valid_mask(points, args.min_range_m, args.max_range_m)
    keep = base
    stats: dict[str, Any] = {
        "point_count_before": total,
        "basic_valid_count": int(np.count_nonzero(base)),
        "basic_deleted_count": int(total - np.count_nonzero(base)),
    }
    keep, h_stats = height_quantile_mask(points, keep, args.height_low_pct, args.height_high_pct, args.height_quantile_padding_m)
    stats.update(h_stats)
    keep, d_stats = density_mask(points, keep, args.density_grid_m, args.density_min_neighbors)
    stats.update(d_stats)
    keep, lh_stats = local_height_mask(
        points,
        keep,
        args.local_height_grid_m,
        args.local_height_min_cell_count,
        args.local_height_mad_multiplier,
        args.local_height_abs_floor_m,
    )
    stats.update(lh_stats)
    stats["point_count_after"] = int(np.count_nonzero(keep))
    stats["deleted_count"] = int(total - stats["point_count_after"])
    stats["delete_ratio"] = float(stats["deleted_count"] / max(total, 1))
    stats["kept_ratio"] = float(stats["point_count_after"] / max(total, 1))
    return keep, stats


def write_stage8a_h5(path: Path, source_h5: Path, points: np.ndarray, stats: dict[str, Any], args: argparse.Namespace) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_can_write(path, args.overwrite)
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()
    with h5py.File(temp_path, "w") as h5:
        grp = h5.create_group("STAGE8A")
        ch1 = grp.create_group("CH1")
        ch1.create_dataset("denoised_points", data=points, compression="gzip", compression_opts=4, chunks=True)
        metadata = h5.create_group("metadata")
        proc = metadata.create_group("processing")
        proc.attrs["stage"] = np.bytes_("stage8a_ch1_ladm2_light_denoise_batch")
        proc.attrs["schema"] = np.bytes_("stage8a_ch1_ladm2_light_denoised_points")
        proc.attrs["source_stage7a_h5"] = np.bytes_(str(source_h5))
        proc.attrs["production_status"] = np.bytes_("denoised_display_candidate_not_final_l3")
        proc.attrs["crs"] = np.bytes_(f"EPSG:{CRS_EPSG}")
        for key, value in stats.items():
            if isinstance(value, (int, float, np.integer, np.floating, np.bool_)):
                proc.attrs[key] = value
        proc.attrs["min_range_m"] = float(args.min_range_m)
        proc.attrs["max_range_m"] = float(args.max_range_m)
        proc.attrs["height_low_pct"] = float(args.height_low_pct)
        proc.attrs["height_high_pct"] = float(args.height_high_pct)
        proc.attrs["height_quantile_padding_m"] = float(args.height_quantile_padding_m)
        proc.attrs["density_grid_m"] = float(args.density_grid_m)
        proc.attrs["density_min_neighbors"] = int(args.density_min_neighbors)
        proc.attrs["local_height_grid_m"] = float(args.local_height_grid_m)
        proc.attrs["local_height_min_cell_count"] = int(args.local_height_min_cell_count)
        proc.attrs["local_height_mad_multiplier"] = float(args.local_height_mad_multiplier)
        proc.attrs["local_height_abs_floor_m"] = float(args.local_height_abs_floor_m)
    replace_temp(temp_path, path, args.overwrite)


def write_laz(path: Path, points: np.ndarray, overwrite: bool) -> int:
    try:
        import laspy
    except ModuleNotFoundError as exc:
        raise RuntimeError("laspy is required to write LAZ. Install laspy and lazrs.") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_can_write(path, overwrite)
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.scales = np.array([0.001, 0.001, 0.001])
    if points.size:
        header.offsets = np.array(
            [
                math.floor(float(np.min(points["easting_m"]))),
                math.floor(float(np.min(points["northing_m"]))),
                math.floor(float(np.min(points["height_m"]))),
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
    las.x = points["easting_m"].astype(np.float64)
    las.y = points["northing_m"].astype(np.float64)
    las.z = points["height_m"].astype(np.float64)
    las.gps_time = points["gps_time"].astype(np.float64)
    las.source_seq = points["source_seq"].astype(np.uint16)
    las.range_m = points["range_m"].astype(np.float32)
    las.scan_angle_deg = points["scan_angle_deg"].astype(np.float32)
    las.point_index = points["point_index"].astype(np.uint32)
    las.pos_quality_flag = points["pos_quality_flag"].astype(np.uint16)
    las.write(temp_path)
    replace_temp(temp_path, path, overwrite)
    return int(points.size)


def sample_points(points: np.ndarray, max_points: int, seed: int) -> np.ndarray:
    if max_points <= 0 or points.size <= max_points:
        return points
    rng = np.random.default_rng(seed)
    idx = rng.choice(points.size, size=max_points, replace=False)
    idx.sort()
    return points[idx]


def write_cloudcompare_sample_txt(path: Path, points: np.ndarray, max_points: int, seed: int, overwrite: bool) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_can_write(path, overwrite)
    temp_path = safe_temp_path(path)
    if temp_path.exists():
        temp_path.unlink()
    selected = sample_points(points, max_points, seed)
    with temp_path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("X Y Z source_seq height_m gps_time range_m scan_angle_deg point_index pos_quality_flag\n")
        if selected.size:
            out = np.column_stack(
                [
                    selected["easting_m"],
                    selected["northing_m"],
                    selected["height_m"],
                    selected["source_seq"],
                    selected["height_m"],
                    selected["gps_time"],
                    selected["range_m"],
                    selected["scan_angle_deg"],
                    selected["point_index"],
                    selected["pos_quality_flag"],
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


def output_size(path: Path) -> int:
    return int(path.stat().st_size) if path.exists() else 0


def add_prefixed(row: dict[str, Any], prefix: str, values: dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        row[f"{prefix}_{key}"] = values.get(key)


def process_file(row: dict[str, str], index: int, total: int, args: argparse.Namespace) -> dict[str, Any]:
    seq = int(row["seq"])
    source_h5 = Path(row["h5_path"])
    paths = output_paths(args.output_root, seq)
    if args.progress:
        print(f"[{index}/{total}] Stage 8A denoise seq {seq:05d}: {source_h5}", flush=True)
    if not args.overwrite and any(path.exists() for path in paths.values() if args.write_laz or path.suffix != ".laz"):
        return {
            "seq": seq,
            "status": "SKIPPED_EXISTS",
            "reason": "one or more outputs already exist; use --overwrite",
            "source_h5": str(source_h5),
            "h5_path": str(paths["h5"]),
            "laz_path": str(paths["laz"]),
            "sample_txt_path": str(paths["sample_txt"]),
        }
    with h5py.File(source_h5, "r") as h5:
        points = h5["STAGE7A/CH1/full_points"][:]
    keep, stats = denoise_mask(points, args)
    denoised = points[keep].copy()
    if args.progress:
        print(
            f"  keep {stats['point_count_after']:,}/{stats['point_count_before']:,} "
            f"({stats['kept_ratio']:.2%}); writing H5",
            flush=True,
        )
    write_stage8a_h5(paths["h5"], source_h5, denoised, stats, args)
    laz_count = 0
    if args.write_laz:
        if args.progress:
            print(f"  writing LAZ: {paths['laz']}", flush=True)
        laz_count = write_laz(paths["laz"], denoised, args.overwrite)
    txt_count = 0
    if args.write_sample_txt:
        if args.progress:
            print(f"  writing sample TXT: {paths['sample_txt']}", flush=True)
        txt_count = write_cloudcompare_sample_txt(
            paths["sample_txt"],
            denoised,
            args.sample_txt_max_points,
            20260510 + seq,
            args.overwrite,
        )

    result: dict[str, Any] = {
        "seq": seq,
        "status": "PROCESSED",
        "reason": "",
        "source_h5": str(source_h5),
        "h5_path": str(paths["h5"]),
        "laz_path": str(paths["laz"]) if args.write_laz else "",
        "sample_txt_path": str(paths["sample_txt"]) if args.write_sample_txt else "",
        "h5_size_bytes": output_size(paths["h5"]),
        "laz_size_bytes": output_size(paths["laz"]) if args.write_laz else 0,
        "sample_txt_size_bytes": output_size(paths["sample_txt"]) if args.write_sample_txt else 0,
        "laz_point_count": laz_count,
        "sample_txt_point_count": txt_count,
    }
    result.update(stats)
    add_prefixed(result, "height_after_m", finite_stats(denoised["height_m"]), ["min", "p01", "p05", "median", "p95", "p99", "max"])
    add_prefixed(result, "range_after_m", finite_stats(denoised["range_m"]), ["min", "p05", "median", "p95", "max"])
    del points, denoised, keep
    gc.collect()
    return result


def gate_summary(rows: list[dict[str, Any]], args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    processed = [row for row in rows if row.get("status") == "PROCESSED"]
    failed = [row for row in rows if row.get("status") == "FAILED"]
    skipped = [row for row in rows if row.get("status") not in {"PROCESSED", "FAILED"}]
    before = int(sum(int(row.get("point_count_before") or 0) for row in processed))
    after = int(sum(int(row.get("point_count_after") or 0) for row in processed))
    deleted = before - after
    ratio = float(deleted / max(before, 1))
    max_delete = max((float(row.get("delete_ratio") or 0.0) for row in processed), default=0.0)
    aggregate = {
        "processed_files": len(processed),
        "failed_files": len(failed),
        "skipped_files": len(skipped),
        "point_count_before": before,
        "point_count_after": after,
        "deleted_count": deleted,
        "delete_ratio": ratio,
        "max_file_delete_ratio": max_delete,
        "total_h5_size_bytes": int(sum(int(row.get("h5_size_bytes") or 0) for row in processed)),
        "total_laz_size_bytes": int(sum(int(row.get("laz_size_bytes") or 0) for row in processed)),
        "total_sample_txt_size_bytes": int(sum(int(row.get("sample_txt_size_bytes") or 0) for row in processed)),
    }
    if failed:
        gate = {"conclusion": "REVIEW_FAILED_FILES", "ready_for_cloudcompare_review": False, "reason": f"{len(failed)} files failed during Stage 8A."}
    elif not processed:
        gate = {"conclusion": "REVIEW_NO_OUTPUT", "ready_for_cloudcompare_review": False, "reason": "No files were denoised."}
    elif max_delete > args.max_warn_delete_ratio:
        gate = {
            "conclusion": "REVIEW_HIGH_DELETE_RATIO",
            "ready_for_cloudcompare_review": True,
            "reason": f"Stage 8A completed, but at least one file delete ratio exceeds {args.max_warn_delete_ratio:.1%}.",
        }
    else:
        gate = {
            "conclusion": "READY_FOR_DENOISED_CLOUDCOMPARE_REVIEW",
            "ready_for_cloudcompare_review": True,
            "reason": "Stage 8A light denoise completed without failed files and delete ratios are within review threshold.",
        }
    return aggregate, gate


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], max_rows: int | None = None) -> str:
    selected = rows if max_rows is None else rows[:max_rows]
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in selected:
        values = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                values.append(f"{value:.6g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_report(payload: dict[str, Any], output_root: Path) -> None:
    gate = payload["gate"]
    agg = payload["aggregate"]
    outputs = payload["outputs"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    preview = markdown_table(
        [row for row in payload["manifest_rows"] if row.get("status") == "PROCESSED"][:20],
        [
            ("seq", "seq"),
            ("before", "point_count_before"),
            ("after", "point_count_after"),
            ("deleted", "deleted_count"),
            ("delete ratio", "delete_ratio"),
            ("h med", "height_after_m_median"),
            ("r min", "range_after_m_min"),
        ],
    )
    content = f"""# Stage 8A CH1 LADM-II Light Denoise Batch

## Gate

- Conclusion: {gate['conclusion']}
- Ready for CloudCompare review: {gate['ready_for_cloudcompare_review']}
- Reason: {gate['reason']}

## Scope

- Input: Stage 7D display-candidate manifest, 95 Stage 7A H5 files.
- Output root: `{output_root / 'stage8a_ladm2_light_denoised'}`
- Original Stage 7A outputs are not modified.
- This is light denoise, not final classification.

## Method

1. Keep finite coordinates, POS-good points, and `range_m >= {payload['settings']['min_range_m']}`.
2. Remove only extreme per-file height tails using {payload['settings']['height_low_pct']}-{payload['settings']['height_high_pct']} percentiles plus padding.
3. Remove isolated spatial speckles using a 2D grid-density neighborhood rule.
4. Remove large local height outliers only in sufficiently populated XY cells.

## Aggregate

- Processed files: {agg['processed_files']}
- Failed files: {agg['failed_files']}
- Point count before: {agg['point_count_before']:,}
- Point count after: {agg['point_count_after']:,}
- Deleted count: {agg['deleted_count']:,}
- Delete ratio: {agg['delete_ratio']:.6%}
- Max file delete ratio: {agg['max_file_delete_ratio']:.6%}
- H5 output size: {agg['total_h5_size_bytes']:,} bytes
- LAZ output size: {agg['total_laz_size_bytes']:,} bytes
- Sample TXT output size: {agg['total_sample_txt_size_bytes']:,} bytes

## Processed Preview

{preview}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Manifest CSV: `{outputs['manifest_csv']}`
- Report JSON: `{outputs['report_json']}`
- H5 directory: `{outputs['h5_dir']}`
- LAZ directory: `{outputs['laz_dir']}`
- Sample TXT directory: `{outputs['sample_txt_dir']}`

## Manual Review

Open several denoised LAZ or sample TXT files in CloudCompare and compare with the Stage 7A original display candidates. Focus on whether sparse flying points and near-zero range clutter are reduced without breaking valid strips or roofs/edges.
"""
    report_md_output = output_root / "reports" / "stage8a_ch1_ladm2_light_denoise_batch_report.md"
    report_md_output.parent.mkdir(parents=True, exist_ok=True)
    report_md_output.write_text(content, encoding="utf-8-sig")
    report_md_project = REPORT_DIR / "stage8a_ch1_ladm2_light_denoise_batch_report.md"
    report_md_project.parent.mkdir(parents=True, exist_ok=True)
    report_md_project.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    base = args.output_root / "stage8a_ladm2_light_denoised"
    for sub in ["h5", "laz", "txt_sample", "manifest", "reports"]:
        (base / sub).mkdir(parents=True, exist_ok=True)
    (args.output_root / "reports").mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    manifest_path = args.input_manifest or args.output_root / "stage7d_teacher_package" / "stage7d_display_candidate_manifest.csv"
    input_rows = read_csv_rows(manifest_path)
    if args.limit > 0:
        input_rows = input_rows[: args.limit]

    rows: list[dict[str, Any]] = []
    for index, row in enumerate(input_rows, start=1):
        try:
            rows.append(process_file(row, index, len(input_rows), args))
        except Exception as exc:
            result = {
                "seq": int(row.get("seq", 0) or 0),
                "status": "FAILED",
                "reason": f"{type(exc).__name__}: {exc}",
                "source_h5": row.get("h5_path", ""),
            }
            rows.append(result)
            if args.stop_on_error:
                raise
            if args.progress:
                print(f"  failed: {result['reason']}", flush=True)

    aggregate, gate = gate_summary(rows, args)
    manifest_csv = base / "manifest" / "stage8a_ch1_ladm2_light_denoise_manifest.csv"
    report_json_output = args.output_root / "reports" / "stage8a_ch1_ladm2_light_denoise_batch_report.json"
    report_json_project = REPORT_DIR / "stage8a_ch1_ladm2_light_denoise_batch_report.json"
    write_csv(manifest_csv, rows)
    payload = {
        "stage_name": "stage8a_ch1_ladm2_light_denoise_batch",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "stage7d_display_candidate_manifest": str(manifest_path),
            "output_root": str(args.output_root),
        },
        "settings": {
            "min_range_m": args.min_range_m,
            "max_range_m": args.max_range_m,
            "height_low_pct": args.height_low_pct,
            "height_high_pct": args.height_high_pct,
            "height_quantile_padding_m": args.height_quantile_padding_m,
            "density_grid_m": args.density_grid_m,
            "density_min_neighbors": args.density_min_neighbors,
            "local_height_grid_m": args.local_height_grid_m,
            "local_height_min_cell_count": args.local_height_min_cell_count,
            "local_height_mad_multiplier": args.local_height_mad_multiplier,
            "local_height_abs_floor_m": args.local_height_abs_floor_m,
            "write_laz": args.write_laz,
            "write_sample_txt": args.write_sample_txt,
            "sample_txt_max_points": args.sample_txt_max_points,
        },
        "aggregate": aggregate,
        "gate": gate,
        "manifest_rows": rows,
        "outputs": {
            "manifest_csv": str(manifest_csv),
            "report_json": str(report_json_output),
            "report_md": str(args.output_root / "reports" / "stage8a_ch1_ladm2_light_denoise_batch_report.md"),
            "project_report_json": str(report_json_project),
            "project_report_md": str(REPORT_DIR / "stage8a_ch1_ladm2_light_denoise_batch_report.md"),
            "h5_dir": str(base / "h5"),
            "laz_dir": str(base / "laz"),
            "sample_txt_dir": str(base / "txt_sample"),
        },
    }
    write_json(report_json_output, payload)
    write_json(report_json_project, payload)
    write_report(payload, args.output_root)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": gate,
                    "aggregate": aggregate,
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 8A: light denoise for 95 Stage 7A CH1 LADM-II display candidates.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--input-manifest", type=Path, default=None)
    parser.add_argument("--min-range-m", type=float, default=30.0)
    parser.add_argument("--max-range-m", type=float, default=float("inf"))
    parser.add_argument("--height-low-pct", type=float, default=0.02)
    parser.add_argument("--height-high-pct", type=float, default=99.98)
    parser.add_argument("--height-quantile-padding-m", type=float, default=2.0)
    parser.add_argument("--density-grid-m", type=float, default=2.0)
    parser.add_argument("--density-min-neighbors", type=int, default=4)
    parser.add_argument("--local-height-grid-m", type=float, default=5.0)
    parser.add_argument("--local-height-min-cell-count", type=int, default=20)
    parser.add_argument("--local-height-mad-multiplier", type=float, default=10.0)
    parser.add_argument("--local-height-abs-floor-m", type=float, default=6.0)
    parser.add_argument("--max-warn-delete-ratio", type=float, default=0.45)
    parser.add_argument("--write-laz", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--write-sample-txt", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--sample-txt-max-points", type=int, default=200_000)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
