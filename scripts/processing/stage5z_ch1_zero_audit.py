from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5


ROOT = Path(__file__).resolve().parents[2]
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
CALIB_COEFFS = ROOT / "untitled" / "calib_coeffs.mat"
STAGE5_SUMMARY = ROOT / "outputs" / "qc" / "stage5_file_summary.csv"
QC_DIR = ROOT / "outputs" / "qc" / "stage5_zero_audit"
PREVIEW_DIR = ROOT / "outputs" / "preview"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

DIST_FACTOR = 2e-9 / 256.0 * 3e8 / 2.0
DEFAULT_FIRST12 = list(range(2, 14))
DEFAULT_STABLE = [111, 112, 113, 114, 115]
DEFAULT_TIME_REPAIR_CHECK = [14, 113]
DEFAULT_SAMPLE_SEQS = sorted(set(DEFAULT_FIRST12 + DEFAULT_STABLE + DEFAULT_TIME_REPAIR_CHECK))

METHOD_REGISTRY = [
    {
        "method_id": "DG_ALS_001",
        "method_name": "direct georeferencing / range offset audit context",
        "source_type": "peer_reviewed_journal",
        "source_reference": "Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006",
        "used_for_delete_or_transform": "no, audit only",
    },
    {
        "method_id": "STRIP_QC_009",
        "method_name": "overlap / strip consistency QC",
        "source_type": "peer_reviewed_conference",
        "source_reference": "Filin & Vosselman, ISPRS 2004",
        "used_for_delete_or_transform": "no, audit only",
    },
    {
        "method_id": "PROJECT_QC_RULE",
        "method_name": "zero peak support count and warning thresholds",
        "source_type": "project_qc_rule",
        "source_reference": "Project-specific diagnostic threshold; not a deletion or transformation algorithm",
        "used_for_delete_or_transform": "no",
    },
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_seq_from_name(path: Path) -> int | None:
    match = re.search(r"cap_(\d{5})_", path.name)
    return int(match.group(1)) if match else None


def read_stage5_summary(path: Path) -> dict[int, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {int(float(row["seq"])): row for row in csv.DictReader(f) if row.get("seq")}


def select_infos(all_infos: list[stage5.FileInfo], args: argparse.Namespace) -> list[stage5.FileInfo]:
    if args.all:
        selected = all_infos
    elif args.seqs:
        wanted: set[int] = set()
        for token in args.seqs.split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                start, end = token.split("-", 1)
                wanted.update(range(int(start), int(end) + 1))
            else:
                wanted.add(int(token))
        selected = [info for info in all_infos if info.seq in wanted]
    else:
        selected = [info for info in all_infos if info.seq in DEFAULT_SAMPLE_SEQS]
    return sorted(selected, key=lambda item: item.seq)


def finite_percentiles(values: np.ndarray, percentiles: list[float]) -> list[float]:
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return [float("nan") for _ in percentiles]
    return [float(np.percentile(finite, p)) for p in percentiles]


def zero_peak_support_near_peak(range_before: np.ndarray, zero_peak: float, half_width_m: float) -> int:
    if not np.isfinite(zero_peak):
        return 0
    return int(np.count_nonzero((range_before >= zero_peak - half_width_m) & (range_before <= zero_peak + half_width_m)))


def audit_one(
    info: stage5.FileInfo,
    calibration: dict[str, float],
    stage5_rows: dict[int, dict[str, str]],
    min_support_count: int,
    zero_peak_abs_diff_warn_m: float,
    near_peak_half_width_m: float,
) -> dict[str, Any]:
    with h5py.File(info.path, "r") as h5:
        raw_dist = h5["Photon_CH1_DIST"][:].astype(np.uint32)
    range_before = raw_dist.astype(np.float64) * DIST_FACTOR
    range_before = range_before[np.isfinite(range_before) & (range_before > 0)]

    zero_peak = pipe.find_zero_peak(range_before)
    zero_offset = float(calibration["zero_offset"])
    support_0_20 = int(np.count_nonzero((range_before >= 0.0) & (range_before <= 20.0)))
    support_near_peak = zero_peak_support_near_peak(range_before, zero_peak, near_peak_half_width_m)
    p_min, p01, p50, p99, p_max = finite_percentiles(range_before, [0, 1, 50, 99, 100])
    row = stage5_rows.get(info.seq, {})
    try:
        height_bias = float(row.get("reference_height_bias_m") or "nan")
    except ValueError:
        height_bias = float("nan")

    if not np.isfinite(zero_peak):
        recommendation = "USE_FIXED_CALIB_ZERO_OFFSET"
        warning = "auto zero_peak not found"
    elif support_0_20 < min_support_count:
        recommendation = "USE_FIXED_CALIB_ZERO_OFFSET"
        warning = f"low zero support count: {support_0_20} < {min_support_count}"
    elif abs(zero_peak - zero_offset) > zero_peak_abs_diff_warn_m:
        recommendation = "CHECK_AUTO_ZERO_BEFORE_USE"
        warning = f"auto zero differs from calib zero_offset by {abs(zero_peak - zero_offset):.3f} m"
    else:
        recommendation = "AUTO_ZERO_POSSIBLE_BUT_STILL_QC"
        warning = ""

    return {
        "seq": info.seq,
        "file": rel(info.path),
        "manifest_status": info.status,
        "manifest_reason": info.reason,
        "point_count_l1": info.point_count,
        "zero_peak_detected_m": zero_peak,
        "calib_zero_offset_m": zero_offset,
        "zero_peak_minus_calib_offset_m": zero_peak - zero_offset if np.isfinite(zero_peak) else float("nan"),
        "zero_peak_support_count_0_20m": support_0_20,
        "zero_peak_support_count_near_peak": support_near_peak,
        "zero_peak_near_half_width_m": near_peak_half_width_m,
        "range_before_min_m": p_min,
        "range_before_p01_m": p01,
        "range_before_p50_m": p50,
        "range_before_p99_m": p99,
        "range_before_max_m": p_max,
        "height_bias_m_from_v1": height_bias,
        "time_status_from_v1": row.get("time_status", ""),
        "output_l3_from_v1": row.get("output_l3", ""),
        "zero_strategy_recommendation": recommendation,
        "zero_audit_warning": warning,
        "overlap_dz_before_median_m": "",
        "overlap_dz_before_p10_m": "",
        "overlap_dz_before_p90_m": "",
        "overlap_abs_dz_before_median_m": "",
        "overlap_common_cells": "",
        "overlap_neighbor_seq": "",
    }


def v1_l3_path(seq: int, stage5_rows: dict[int, dict[str, str]]) -> Path | None:
    row = stage5_rows.get(seq, {})
    output = row.get("output_l3")
    if output:
        path = ROOT / output
        if path.exists():
            return path
    patterns = [
        ROOT / "outputs" / "h5_ch1" / f"L3S_CH1_cap_{seq:05d}_*.h5",
        ROOT / "outputs" / "h5_ch1" / "raw" / f"L3_CH1_raw_cap_{seq:05d}_*.h5",
    ]
    for pattern in patterns:
        matches = sorted(pattern.parent.glob(pattern.name))
        if matches:
            return matches[0]
    return None


def load_sample_points(path: Path, max_points: int) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        ds = h5["L3/CH1/points"]
        count = int(ds.shape[0])
        if count == 0:
            return np.zeros(0, dtype=ds.dtype)
        if count <= max_points:
            return ds[:]
        step = int(math.ceil(count / max_points))
        return ds[::step]


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
    if z.size == 0:
        return {}
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


def overlap_stats(
    left: dict[int, float],
    right: dict[int, float],
) -> dict[str, Any]:
    common = sorted(set(left).intersection(right))
    if not common:
        return {
            "overlap_common_cells": 0,
            "overlap_dz_before_median_m": float("nan"),
            "overlap_dz_before_p10_m": float("nan"),
            "overlap_dz_before_p90_m": float("nan"),
            "overlap_abs_dz_before_median_m": float("nan"),
        }
    diffs = np.asarray([right[key] - left[key] for key in common], dtype=np.float64)
    return {
        "overlap_common_cells": len(common),
        "overlap_dz_before_median_m": float(np.median(diffs)),
        "overlap_dz_before_p10_m": float(np.percentile(diffs, 10)),
        "overlap_dz_before_p90_m": float(np.percentile(diffs, 90)),
        "overlap_abs_dz_before_median_m": float(np.median(np.abs(diffs))),
    }


def add_overlap_stats(
    rows: list[dict[str, Any]],
    stage5_rows: dict[int, dict[str, str]],
    max_overlap_points: int,
    cell_size_m: float,
    min_points_per_cell: int,
) -> None:
    row_by_seq = {int(row["seq"]): row for row in rows}
    medians_by_seq: dict[int, dict[int, float]] = {}
    for seq in sorted(row_by_seq):
        path = v1_l3_path(seq, stage5_rows)
        if path is None:
            continue
        points = load_sample_points(path, max_overlap_points)
        medians_by_seq[seq] = cell_height_medians(points, cell_size_m, min_points_per_cell)

    for seq in sorted(row_by_seq):
        prev_seq = seq - 1
        if prev_seq not in row_by_seq or prev_seq not in medians_by_seq or seq not in medians_by_seq:
            continue
        stats = overlap_stats(medians_by_seq[prev_seq], medians_by_seq[seq])
        row_by_seq[seq].update(stats)
        row_by_seq[seq]["overlap_neighbor_seq"] = prev_seq


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "seq",
        "file",
        "manifest_status",
        "manifest_reason",
        "point_count_l1",
        "zero_peak_detected_m",
        "calib_zero_offset_m",
        "zero_peak_minus_calib_offset_m",
        "zero_peak_support_count_0_20m",
        "zero_peak_support_count_near_peak",
        "zero_peak_near_half_width_m",
        "range_before_min_m",
        "range_before_p01_m",
        "range_before_p50_m",
        "range_before_p99_m",
        "range_before_max_m",
        "height_bias_m_from_v1",
        "time_status_from_v1",
        "output_l3_from_v1",
        "zero_strategy_recommendation",
        "zero_audit_warning",
        "overlap_neighbor_seq",
        "overlap_common_cells",
        "overlap_dz_before_median_m",
        "overlap_dz_before_p10_m",
        "overlap_dz_before_p90_m",
        "overlap_abs_dz_before_median_m",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def make_preview(path: Path, seqs: list[int], stage5_rows: dict[int, dict[str, str]], max_points_per_file: int) -> None:
    samples: list[np.ndarray] = []
    for seq in seqs:
        l3_path = v1_l3_path(seq, stage5_rows)
        if l3_path is None:
            continue
        points = load_sample_points(l3_path, max_points_per_file)
        if points.size:
            samples.append(points)
    if not samples:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<html><body>No preview points.</body></html>", encoding="utf-8")
        return
    merged = np.concatenate(samples)
    pipe.make_stage3_preview(path, merged["easting_m"], merged["northing_m"], merged["height_m"], sample_count=min(500_000, merged.size))


def summarize(rows: list[dict[str, Any]], min_support_count: int) -> dict[str, Any]:
    low_support = [row for row in rows if int(row["zero_peak_support_count_0_20m"]) < min_support_count]
    fixed_recommended = [row for row in rows if row["zero_strategy_recommendation"] == "USE_FIXED_CALIB_ZERO_OFFSET"]
    overlap_abs = []
    for row in rows:
        try:
            value = float(row.get("overlap_abs_dz_before_median_m") or "nan")
        except ValueError:
            value = float("nan")
        if np.isfinite(value):
            overlap_abs.append(value)
    return {
        "files_audited": len(rows),
        "low_zero_support_files": len(low_support),
        "fixed_zero_recommended_files": len(fixed_recommended),
        "max_overlap_abs_median_dz_m": float(np.max(overlap_abs)) if overlap_abs else None,
        "median_overlap_abs_median_dz_m": float(np.median(overlap_abs)) if overlap_abs else None,
    }


def write_report(
    path: Path,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    args: argparse.Namespace,
    audit_csv: Path,
    first12_preview: Path,
    stable_preview: Path,
) -> None:
    if summary["fixed_zero_recommended_files"]:
        conclusion = "不合理"
        recommendation = "当前自动 zero_peak 支持点不足，建议先用固定 calib zero_offset 生成 Stage 5R 小样本候选，不要继续使用 v1 坐标。"
    else:
        conclusion = "基本合理但有风险"
        recommendation = "自动 zero_peak 未触发低支持告警，但仍需检查小样本 v2 对比后再进入全量。"

    worst = sorted(
        rows,
        key=lambda row: float(row.get("overlap_abs_dz_before_median_m") or "nan")
        if str(row.get("overlap_abs_dz_before_median_m", "")).strip()
        else -1,
        reverse=True,
    )[:10]
    worst_lines = []
    for row in worst:
        value = row.get("overlap_abs_dz_before_median_m")
        if value == "":
            continue
        worst_lines.append(
            f"- seq {row['overlap_neighbor_seq']} -> {row['seq']}: abs median dz = {float(value):.3f} m, common cells = {row['overlap_common_cells']}"
        )

    content = f"""# Stage 5Z CH1 零位返查报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}
- 阶段：stage5z_ch1_zero_audit
- 处理通道：CH1
- 审计范围：{"all L1 CH1 files" if args.all else "sample files"}

## Inputs and Outputs

- L1 source: `{rel(L1_DIR)}`
- Calibration: `{rel(CALIB_COEFFS)}`
- Stage 5 v1 summary: `{rel(STAGE5_SUMMARY)}`
- Audit CSV: `{rel(audit_csv)}`
- First12 preview: `{rel(first12_preview)}`
- Stable preview: `{rel(stable_preview)}`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{chr(10).join(f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |" for m in METHOD_REGISTRY)}

## Parameters

- calib zero_offset CH1: {rows[0]['calib_zero_offset_m'] if rows else float('nan')} m
- zero support range: 0-20 m
- min support count: {args.min_support_count}
- near peak half width: {args.near_peak_half_width_m} m
- zero peak vs calib warning threshold: {args.zero_peak_abs_diff_warn_m} m
- overlap cell size: {args.overlap_cell_m} m
- overlap max sampled points per file: {args.max_overlap_points}

## Key Statistics

- Files audited: {summary['files_audited']}
- Low zero-support files: {summary['low_zero_support_files']}
- Fixed zero-offset recommended files: {summary['fixed_zero_recommended_files']}
- Median overlap abs median dz: {summary['median_overlap_abs_median_dz_m']}
- Max overlap abs median dz: {summary['max_overlap_abs_median_dz_m']}

## Worst Overlap DZ Before

{chr(10).join(worst_lines) if worst_lines else "- 无可用重叠统计"}

## Known Warnings

- 本阶段只做 QC 统计，不删点、不改坐标。
- `zero_peak_support_count_0_20m` 太低时，自动 zero_peak 不可信。
- `PROJECT_QC_RULE` 不是论文算法，只用于人工 gate。
- Stage 5 v1 的逐文件 height median bias 不作为最终坐标修正依据。

## Manual Checklist

- 检查 `zero_peak_support_count_0_20m` 是否普遍过低。
- 检查 `zero_peak_detected_m` 是否相对 `calib_zero_offset_m` 大幅跳变。
- 检查 first12 preview 是否仍存在明显分层。
- 检查 stable 00111-00115 preview 是否相对连续。
- 决定是否运行 Stage 5R 小样本：推荐先用 `Z1 fixed_calib_zero_offset`。

## Gate Rule

Stop here. Do not run full CH1 v2, CH2, joint denoise, or LAZ until this zero audit is manually accepted.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5Z CH1 zero peak audit; no coordinate changes are written.")
    parser.add_argument("--all", action="store_true", help="Audit every manifest file instead of the default diagnostic sample.")
    parser.add_argument("--seqs", default="", help="Comma/range list such as 2-14,111-115.")
    parser.add_argument("--min-support-count", type=int, default=1000)
    parser.add_argument("--zero-peak-abs-diff-warn-m", type=float, default=1.0)
    parser.add_argument("--near-peak-half-width-m", type=float, default=0.5)
    parser.add_argument("--max-overlap-points", type=int, default=400_000)
    parser.add_argument("--preview-points-per-file", type=int, default=80_000)
    parser.add_argument("--overlap-cell-m", type=float, default=1.0)
    parser.add_argument("--min-points-per-cell", type=int, default=3)
    args = parser.parse_args()

    all_infos = stage5.read_manifest(stage5.MANIFEST)
    infos = select_infos(all_infos, args)
    if not infos:
        raise ValueError("No files selected for Stage 5Z zero audit.")

    calibration = pipe.load_channel_calibration(CALIB_COEFFS, "ch1")
    stage5_rows = read_stage5_summary(STAGE5_SUMMARY)
    rows = [
        audit_one(
            info,
            calibration,
            stage5_rows,
            args.min_support_count,
            args.zero_peak_abs_diff_warn_m,
            args.near_peak_half_width_m,
        )
        for info in infos
    ]
    add_overlap_stats(rows, stage5_rows, args.max_overlap_points, args.overlap_cell_m, args.min_points_per_cell)

    audit_csv = QC_DIR / "ch1_zero_peak_audit.csv"
    write_csv(audit_csv, rows)

    first12_preview = PREVIEW_DIR / "stage5_zero_audit_first12.html"
    stable_preview = PREVIEW_DIR / "stage5_zero_audit_stable_00111_00115.html"
    make_preview(first12_preview, DEFAULT_FIRST12, stage5_rows, args.preview_points_per_file)
    make_preview(stable_preview, DEFAULT_STABLE, stage5_rows, args.preview_points_per_file)

    summary = summarize(rows, args.min_support_count)
    report_md = REPORT_DIR / "stage5_zero_audit_report.md"
    report_json = REPORT_DIR / "stage5_zero_audit_report.json"
    write_report(report_md, rows, summary, args, audit_csv, first12_preview, stable_preview)
    report_json.write_text(
        json.dumps(
            {
                "stage_name": "stage5z_ch1_zero_audit",
                "audit_csv": rel(audit_csv),
                "first12_preview": rel(first12_preview),
                "stable_preview": rel(stable_preview),
                "summary": summary,
                "method_registry": METHOD_REGISTRY,
                "gate_rule": "manual confirmation required before Stage 5R sample/full processing",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )

    print("Stage 5Z zero audit complete.")
    print(f"Report: {report_md}")
    print(f"Audit CSV: {audit_csv}")
    print(f"First12 preview: {first12_preview}")
    print(f"Stable preview: {stable_preview}")


if __name__ == "__main__":
    main()
