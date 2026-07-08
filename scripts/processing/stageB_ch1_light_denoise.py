from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import plotly.graph_objects as go
from scipy.spatial import cKDTree


ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_PROJECT_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3",
    )
)
RAW_DIR = ROOT / "outputs" / "h5_ch1" / "raw"
PROJECT_QC_DIR = ROOT / "outputs" / "qc"
PROJECT_PREVIEW_DIR = ROOT / "outputs" / "preview"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
C_DATA_ROOT = Path(
    os.environ.get(
        "AIRBORNE_LIDAR_C_DATA_ROOT",
        r"E:\yjind_work\Airborne_LiDAR_Data\proj_denoising_f3_2.0\0510_f30510_f3_data",
    )
)
LIGHT_DIR = C_DATA_ROOT / "outputs" / "h5_ch1" / "light_denoised"
SUMMARY_CSV = PROJECT_QC_DIR / "ch1_light_denoise_summary.csv"
OUTPUT_INDEX_CSV = PROJECT_QC_DIR / "ch1_light_denoise_output_index.csv"
PROGRESS_JSON = PROJECT_QC_DIR / "ch1_light_denoise_progress.json"
REPORT_MD = REPORT_DIR / "stage3_5_CH1_light_denoise_report.md"
REPORT_JSON = REPORT_DIR / "stage3_5_CH1_light_denoise_report.json"
PREVIEW_HTML = PROJECT_PREVIEW_DIR / "ch1_light_denoised_overview.html"


SOR_MEAN_K = 12
SOR_STD_MULTIPLIER = 3.0
ROR_RADIUS_M = 1.0
ROR_MIN_NEIGHBORS = 2
MAX_DELETE_RATIO = 0.03
QUERY_CHUNK_SIZE = 100_000
PREVIEW_PER_FILE = 600


def rel(path: Path) -> str:
    for base in (ROOT, C_DATA_ROOT):
        try:
            return str(path.relative_to(base))
        except ValueError:
            pass
    return str(path)


def output_name(raw: Path) -> str:
    return raw.name.replace("L3_CH1_raw_", "L3_CH1_light_denoised_")


def append_csv(path: Path, row: dict[str, Any], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def write_progress(**kwargs: Any) -> None:
    PROGRESS_JSON.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), **kwargs}
    PROGRESS_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8-sig")


def xyz_from_points(points: np.ndarray) -> np.ndarray:
    return np.column_stack(
        [
            points["easting_m"].astype(np.float64),
            points["northing_m"].astype(np.float64),
            points["height_m"].astype(np.float64),
        ]
    )


def sor_mask_exact(points: np.ndarray, file_label: str) -> tuple[np.ndarray, dict[str, Any]]:
    count = points.size
    if count <= SOR_MEAN_K + 1:
        return np.ones(count, dtype=bool), {
            "sor_candidate_count": 0,
            "sor_mean_distance_mean": float("nan"),
            "sor_mean_distance_std": float("nan"),
            "sor_threshold": float("nan"),
        }

    xyz = xyz_from_points(points)
    finite = np.all(np.isfinite(xyz), axis=1)
    keep = finite.copy()
    if not np.any(finite):
        return keep, {
            "sor_candidate_count": count,
            "sor_mean_distance_mean": float("nan"),
            "sor_mean_distance_std": float("nan"),
            "sor_threshold": float("nan"),
        }

    valid_idx = np.flatnonzero(finite)
    valid_xyz = xyz[valid_idx]
    k = min(SOR_MEAN_K + 1, valid_xyz.shape[0])
    tree = cKDTree(valid_xyz)

    mean_dist = np.empty(valid_xyz.shape[0], dtype=np.float64)
    for start in range(0, valid_xyz.shape[0], QUERY_CHUNK_SIZE):
        end = min(start + QUERY_CHUNK_SIZE, valid_xyz.shape[0])
        dist, _ = tree.query(valid_xyz[start:end], k=k, workers=-1)
        if k > 1:
            mean_dist[start:end] = dist[:, 1:].mean(axis=1)
        else:
            mean_dist[start:end] = dist
        print(f"    SOR query {file_label}: {end:,}/{valid_xyz.shape[0]:,}", flush=True)

    dist_mean = float(np.mean(mean_dist))
    dist_std = float(np.std(mean_dist))
    threshold = dist_mean + SOR_STD_MULTIPLIER * dist_std
    sor_outlier = mean_dist > threshold
    keep[valid_idx[sor_outlier]] = False
    return keep, {
        "sor_candidate_count": int(np.count_nonzero(sor_outlier)),
        "sor_mean_distance_mean": dist_mean,
        "sor_mean_distance_std": dist_std,
        "sor_threshold": threshold,
    }


def ror_mask_exact(points: np.ndarray, current_keep: np.ndarray, file_label: str) -> tuple[np.ndarray, dict[str, Any]]:
    xyz = xyz_from_points(points)
    valid = current_keep & np.all(np.isfinite(xyz), axis=1)
    keep = current_keep.copy()
    if not np.any(valid):
        return keep, {"ror_candidate_count": 0}

    valid_idx = np.flatnonzero(valid)
    valid_xyz = xyz[valid_idx]
    tree = cKDTree(valid_xyz)
    ror_outlier = np.zeros(valid_xyz.shape[0], dtype=bool)

    for start in range(0, valid_xyz.shape[0], QUERY_CHUNK_SIZE):
        end = min(start + QUERY_CHUNK_SIZE, valid_xyz.shape[0])
        counts = tree.query_ball_point(valid_xyz[start:end], r=ROR_RADIUS_M, workers=-1, return_length=True)
        counts = np.asarray(counts, dtype=np.int32)
        ror_outlier[start:end] = counts < ROR_MIN_NEIGHBORS
        print(f"    ROR query {file_label}: {end:,}/{valid_xyz.shape[0]:,}", flush=True)

    keep[valid_idx[ror_outlier]] = False
    return keep, {"ror_candidate_count": int(np.count_nonzero(ror_outlier))}


def write_light_file(raw_path: Path, out_path: Path, kept: np.ndarray, raw_points: np.ndarray, delete_ratio: float, stats: dict[str, Any], enable_ror: bool) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    with h5py.File(raw_path, "r") as src, h5py.File(out_path, "w") as dst:
        l3 = dst.create_group("L3")
        metadata = dst.create_group("metadata")
        processing = metadata.create_group("processing")

        src_processing = src["metadata/processing"]
        for key, value in src_processing.attrs.items():
            processing.attrs[key] = value

        method_ids = "SOR_003,ROR_004" if enable_ror else "SOR_003"
        processing.attrs["stage"] = np.bytes_("stage3_5_ch1_light_denoise")
        processing.attrs["input_raw_l3"] = np.bytes_(rel(raw_path))
        processing.attrs["method_ids"] = np.bytes_(method_ids)
        processing.attrs["sor_mean_k"] = SOR_MEAN_K
        processing.attrs["sor_std_multiplier"] = SOR_STD_MULTIPLIER
        processing.attrs["ror_enabled"] = bool(enable_ror)
        processing.attrs["ror_radius_m"] = ROR_RADIUS_M
        processing.attrs["ror_min_neighbors"] = ROR_MIN_NEIGHBORS
        processing.attrs["delete_ratio"] = float(delete_ratio)
        processing.attrs["delete_ratio_limit"] = MAX_DELETE_RATIO
        for key, value in stats.items():
            if isinstance(value, (int, float, np.integer, np.floating)):
                processing.attrs[key] = value

        points = raw_points[kept].copy()
        if "denoise_flag" in points.dtype.names:
            points["denoise_flag"] = 0

        for ch in range(1, 5):
            group = l3.create_group(f"CH{ch}")
            if ch == 1:
                group.create_dataset("points", data=points, compression="gzip", compression_opts=4, chunks=True)
            else:
                group.create_dataset("points", shape=(0,), dtype=points.dtype)


def process_file(raw_path: Path, force: bool, enable_ror: bool, index: int, total: int) -> tuple[dict[str, Any], np.ndarray | None]:
    out_path = LIGHT_DIR / output_name(raw_path)
    file_label = raw_path.name
    if out_path.exists() and not force:
        with h5py.File(out_path, "r") as h5:
            count_after = int(h5["L3/CH1/points"].shape[0])
        return {
            "raw_file": rel(raw_path),
            "light_file": rel(out_path),
            "status": "EXISTS",
            "point_count_before": "",
            "point_count_after": count_after,
            "deleted_count": "",
            "delete_ratio": "",
            "sor_candidate_count": "",
            "ror_candidate_count": "",
            "warning": "reused existing output",
        }, None

    print(f"[{index}/{total}] start {file_label}", flush=True)
    write_progress(current_file=file_label, file_index=index, total_files=total, step="read_raw")
    with h5py.File(raw_path, "r") as h5:
        raw_points = h5["L3/CH1/points"][:]

    point_count = int(raw_points.size)
    write_progress(current_file=file_label, file_index=index, total_files=total, step="sor", point_count=point_count)
    keep, stats = sor_mask_exact(raw_points, file_label)
    if enable_ror:
        write_progress(current_file=file_label, file_index=index, total_files=total, step="ror", point_count=point_count)
        keep, ror_stats = ror_mask_exact(raw_points, keep, file_label)
        stats.update(ror_stats)
    else:
        stats["ror_candidate_count"] = 0

    deleted = int(point_count - np.count_nonzero(keep))
    delete_ratio = deleted / max(point_count, 1)
    warning = ""
    status = "PROCESSED"

    if delete_ratio > MAX_DELETE_RATIO:
        status = "SKIPPED_DELETE_RATIO_EXCEEDED"
        warning = f"delete ratio {delete_ratio:.4%} exceeds 3%; no light denoised file written"
        print(f"[{index}/{total}] skip {file_label}: {warning}", flush=True)
        return {
            "raw_file": rel(raw_path),
            "light_file": "",
            "status": status,
            "point_count_before": point_count,
            "point_count_after": 0,
            "deleted_count": deleted,
            "delete_ratio": delete_ratio,
            "sor_candidate_count": stats["sor_candidate_count"],
            "ror_candidate_count": stats["ror_candidate_count"],
            "warning": warning,
        }, None

    write_progress(current_file=file_label, file_index=index, total_files=total, step="write_light", point_count=point_count)
    write_light_file(raw_path, out_path, keep, raw_points, delete_ratio, stats, enable_ror)

    preview_points = raw_points[keep]
    if preview_points.size > PREVIEW_PER_FILE:
        seed = 20260510 + int(preview_points["source_seq"][0])
        rng = np.random.default_rng(seed)
        sample_idx = rng.choice(preview_points.size, size=PREVIEW_PER_FILE, replace=False)
        preview_points = preview_points[np.sort(sample_idx)]

    print(f"[{index}/{total}] done {file_label}: before={point_count:,} after={np.count_nonzero(keep):,} delete_ratio={delete_ratio:.4%}", flush=True)
    return {
        "raw_file": rel(raw_path),
        "light_file": rel(out_path),
        "status": status,
        "point_count_before": point_count,
        "point_count_after": int(np.count_nonzero(keep)),
        "deleted_count": deleted,
        "delete_ratio": delete_ratio,
        "sor_candidate_count": stats["sor_candidate_count"],
        "ror_candidate_count": stats["ror_candidate_count"],
        "warning": warning,
    }, preview_points


def make_preview(samples: list[np.ndarray]) -> None:
    PROJECT_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    if not samples:
        PREVIEW_HTML.write_text("<html><body>No CH1 light denoised preview points.</body></html>", encoding="utf-8")
        return
    pts = np.concatenate(samples)
    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=pts["easting_m"],
                y=pts["northing_m"],
                z=pts["height_m"],
                mode="markers",
                marker={"size": 1.2, "color": pts["height_m"], "colorscale": "Viridis", "opacity": 0.75},
                hovertemplate="E: %{x:.3f}<br>N: %{y:.3f}<br>H: %{z:.3f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title="CH1 Light Denoised Overview",
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        scene={"xaxis_title": "Easting", "yaxis_title": "Northing", "zaxis_title": "Height", "aspectmode": "data"},
        template="plotly_white",
    )
    fig.write_html(PREVIEW_HTML, include_plotlyjs=True, full_html=True)


def write_reports(rows: list[dict[str, Any]], elapsed_sec: float, enable_ror: bool) -> None:
    processed = [row for row in rows if row["status"] in {"PROCESSED", "EXISTS"}]
    skipped = [row for row in rows if str(row["status"]).startswith("SKIPPED")]
    before = sum(int(float(row["point_count_before"] or 0)) for row in rows)
    after = sum(int(float(row["point_count_after"] or 0)) for row in rows)
    deleted = sum(int(float(row["deleted_count"] or 0)) for row in rows)
    delete_ratio = deleted / max(before, 1)

    if skipped:
        conclusion = "基本合理但有风险"
        recommendation = "存在文件因删除比例超过 3% 未写出去噪成果；建议人工检查这些边缘/稀疏文件是否沿用 raw。"
    elif delete_ratio > MAX_DELETE_RATIO:
        conclusion = "不合理"
        recommendation = "总体删除比例超过 3%；暂停检查。"
    elif deleted == 0:
        conclusion = "基本合理但有风险"
        recommendation = "轻度去噪没有删除点，可能参数过保守；建议人工查看预览。"
    else:
        conclusion = "基本合理但有风险"
        recommendation = "CH1 轻度去噪完成；建议人工查看去噪前后形态后再进入 CH2。"

    method_registry = [
        {
            "method_id": "SOR_003",
            "method_name": "Statistical Outlier Removal",
            "purpose": "light channel-internal point cloud outlier removal",
            "source_type": "official_documentation",
            "source_reference": "PCL StatisticalOutlierRemoval documentation",
            "used_for_delete_or_transform": "yes",
        }
    ]
    if enable_ror:
        method_registry.append(
            {
                "method_id": "ROR_004",
                "method_name": "Radius Outlier Removal",
                "purpose": "light channel-internal isolated point removal",
                "source_type": "official_documentation",
                "source_reference": "Open3D / PDAL official documentation",
                "used_for_delete_or_transform": "yes",
            }
        )

    report = {
        "stage_name": "Stage B CH1 light denoise",
        "input_files": len(rows),
        "output_files": len(processed),
        "method_registry": method_registry,
        "project_empirical_parameters": [],
        "point_count_before": before,
        "point_count_after": after,
        "deleted_or_flagged_count": deleted,
        "delete_ratio": delete_ratio,
        "delete_ratio_limit": MAX_DELETE_RATIO,
        "time_repair_files": "retained from raw; not modified in this stage",
        "known_warnings": [row["warning"] for row in rows if row.get("warning")],
        "gate_conclusion": conclusion,
        "manual_checklist": ["建筑边缘是否保留", "屋顶细节是否保留", "飞点是否减少", "删除比例是否可接受", "是否继续 CH2"],
        "recommendation": recommendation,
        "elapsed_sec": elapsed_sec,
        "output_dir": str(LIGHT_DIR),
        "summary_csv": str(SUMMARY_CSV),
        "preview_html": str(PREVIEW_HTML),
        "ror_enabled": enable_ror,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    ror_row = (
        "| ROR_004 | Radius Outlier Removal | official_documentation | Open3D / PDAL official documentation | yes |"
        if enable_ror
        else "| ROR_004 | Radius Outlier Removal | official_documentation | Open3D / PDAL official documentation | no, disabled in this run |"
    )
    REPORT_MD.write_text(
        f"""# Stage B CH1 轻度去噪报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}

## Inputs and Outputs

- Input raw directory: `{rel(RAW_DIR)}`
- Output light denoised directory: `{LIGHT_DIR}`
- Summary CSV: `{rel(SUMMARY_CSV)}`
- Output index CSV: `{rel(OUTPUT_INDEX_CSV)}`
- Progress JSON: `{rel(PROGRESS_JSON)}`
- Preview HTML: `{rel(PREVIEW_HTML)}`
- Input files: {len(rows)}
- Output/reused files: {len(processed)}
- Files skipped by 3% delete-ratio gate: {len(skipped)}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| SOR_003 | Statistical Outlier Removal | official_documentation | PCL StatisticalOutlierRemoval documentation | yes |
{ror_row}

## Parameters

- SOR mean_k: {SOR_MEAN_K}
- SOR std_multiplier: {SOR_STD_MULTIPLIER}
- ROR enabled: {enable_ror}
- ROR radius_m: {ROR_RADIUS_M}
- ROR min_neighbors: {ROR_MIN_NEIGHBORS}
- Max delete ratio per file: {MAX_DELETE_RATIO:.2%}
- Query chunk size: {QUERY_CHUNK_SIZE:,}

## Key Statistics

- Point count before: {before:,}
- Point count after: {after:,}
- Deleted count: {deleted:,}
- Delete ratio: {delete_ratio:.6%}
- Skipped files: {len(skipped)}
- Elapsed minutes: {elapsed_sec / 60.0:.2f}

## QC Observation Only

- 高程极值、稀疏区域、水体疑似区域、时间修复文件附近异常仅作为人工检查统计，不作为自动删点依据。
- 本阶段没有使用自定义高程分位数删点、网格过滤、人工经验阈值删点。

## Known Warnings

{chr(10).join(f'- {row["warning"]}' for row in rows if row.get("warning")) or '- 无'}

## Files Requiring Manual Decision

{chr(10).join(f'- {row["raw_file"]}: {row["warning"]}' for row in skipped) if skipped else '- 无'}

## Manual Checklist

- 建筑边缘是否保留。
- 屋顶细节是否保留。
- 飞点是否减少。
- 删除比例是否可接受。
- 是否继续 CH2。

## Gate Rule

Stop here. Do not run CH2 until the user manually confirms this Stage B result is acceptable.
""",
        encoding="utf-8-sig",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage B CH1 light denoise using whitelisted SOR and optional ROR.")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--disable-ror", action="store_true", help="Disable exact Radius Outlier Removal for diagnostic runs.")
    args = parser.parse_args()

    free_c_gb = shutil.disk_usage(C_DATA_ROOT.parent if C_DATA_ROOT.parent.exists() else Path("C:\\")).free / (1024**3)
    if free_c_gb < 40:
        raise RuntimeError(f"C drive free space is too low for CH1 light denoised output: {free_c_gb:.2f} GB")
    C_DATA_ROOT.mkdir(parents=True, exist_ok=True)

    if args.force:
        for path in (SUMMARY_CSV, OUTPUT_INDEX_CSV, PROGRESS_JSON):
            if path.exists():
                path.unlink()

    rows: list[dict[str, Any]] = []
    samples: list[np.ndarray] = []
    fields = [
        "raw_file",
        "light_file",
        "status",
        "point_count_before",
        "point_count_after",
        "deleted_count",
        "delete_ratio",
        "sor_candidate_count",
        "ror_candidate_count",
        "warning",
    ]
    index_fields = ["raw_file", "light_file", "storage_root"]

    raw_files = sorted(RAW_DIR.glob("L3_CH1_raw_cap_*.h5"))
    if args.limit:
        raw_files = raw_files[: args.limit]

    start_time = time.time()
    for index, raw_path in enumerate(raw_files, 1):
        enable_ror = not args.disable_ror
        row, preview_points = process_file(raw_path, args.force, enable_ror, index, len(raw_files))
        rows.append(row)
        append_csv(SUMMARY_CSV, row, fields)
        if row.get("light_file"):
            append_csv(
                OUTPUT_INDEX_CSV,
                {"raw_file": row["raw_file"], "light_file": row["light_file"], "storage_root": str(C_DATA_ROOT)},
                index_fields,
            )
        if preview_points is not None and preview_points.size:
            samples.append(preview_points)

        # Refresh report incrementally so a long run always has inspectable state.
        write_reports(rows, time.time() - start_time, enable_ror)
        write_progress(current_file=raw_path.name, file_index=index, total_files=len(raw_files), step="file_complete")

    make_preview(samples)
    write_reports(rows, time.time() - start_time, not args.disable_ror)
    write_progress(current_file="", file_index=len(raw_files), total_files=len(raw_files), step="complete")
    print("Stage B CH1 light denoise complete.", flush=True)
    print(f"Report: {REPORT_MD}", flush=True)
    print(f"Summary: {SUMMARY_CSV}", flush=True)
    print(f"Preview: {PREVIEW_HTML}", flush=True)


if __name__ == "__main__":
    main()
