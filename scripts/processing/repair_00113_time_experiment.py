from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np

import ch1_pipeline as pipe


ROOT = Path(__file__).resolve().parents[2]
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
L2_DIR = ROOT / "intermediate" / "l2_body_xyz"
L2_POS_DIR = ROOT / "intermediate" / "l2_pos_matched"
L3_DIR = ROOT / "intermediate" / "l3_georef"
PREVIEW_DIR = ROOT / "outputs" / "preview"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

PREV_L1 = L1_DIR / "L1_cap_00112_20260510191000.h5"
BAD_L1 = L1_DIR / "L1_cap_00113_20260510191003.h5"
NEXT_L1 = L1_DIR / "L1_cap_00114_20260510191006.h5"
BAD_L2 = L2_DIR / "L2_CH1_cap_00113_20260510191003.h5"
REPAIRED_L2 = L2_DIR / "L2_CH1_cap_00113_20260510191003_time_repaired.h5"
REPAIRED_L2P = L2_POS_DIR / "L2P_CH1_cap_00113_20260510191003_time_repaired.h5"
REPAIRED_L3 = L3_DIR / "L3_CH1_cap_00113_20260510191003_time_repaired.h5"
MERGED_L3 = L3_DIR / "L3_CH1_continuous_cap_00111_00115_with_00113_time_repaired.h5"
MERGED_PREVIEW = PREVIEW_DIR / "stage4_ch1_continuous_with_00113_time_repaired_preview.html"
REPORT_MD = REPORT_DIR / "stage4_00113_time_repair_experiment_report.md"
REPORT_JSON = REPORT_DIR / "stage4_00113_time_repair_experiment_report.json"


def ch1_time_bounds(path: Path) -> tuple[float, float]:
    with h5py.File(path, "r") as h5:
        values = h5["GNSS_SEC_CH1"][:].astype(np.float64)
    finite = values[np.isfinite(values)]
    return float(np.min(finite)), float(np.max(finite))


def median_pulse_period_sec(path: Path) -> float:
    with h5py.File(path, "r") as h5:
        pulse = h5["PULSE_INDEX_CH1"][:].astype(np.float64)
        time = h5["GNSS_SEC_CH1"][:].astype(np.float64)
    idx = np.linspace(0, pulse.size - 1, min(pulse.size, 200_000), dtype=np.int64)
    design = np.column_stack([np.ones(idx.size), pulse[idx]])
    _, slope = np.linalg.lstsq(design, time[idx], rcond=None)[0]
    return float(slope)


def build_repaired_l2() -> dict[str, float]:
    prev_min, prev_max = ch1_time_bounds(PREV_L1)
    next_min, next_max = ch1_time_bounds(NEXT_L1)
    prev_period = median_pulse_period_sec(PREV_L1)
    next_period = median_pulse_period_sec(NEXT_L1)
    pulse_period = float(np.median([prev_period, next_period]))

    with h5py.File(BAD_L2, "r") as src:
        points = src["L2/CH1/points"][:]

    pulse = points["pulse_index"].astype(np.float64)
    pulse_min = float(np.min(pulse))
    pulse_max = float(np.max(pulse))
    raw_start = prev_max + pulse_period
    raw_end = next_min - pulse_period
    repaired_raw = raw_start + (pulse - pulse_min) / (pulse_max - pulse_min) * (raw_end - raw_start)
    points["gnss_sec_raw"] = repaired_raw
    points["lidar_time_sec"] = repaired_raw + pipe.DEFAULT_TIME_OFFSET_SEC

    REPAIRED_L2.parent.mkdir(parents=True, exist_ok=True)
    if REPAIRED_L2.exists():
        REPAIRED_L2.unlink()
    with h5py.File(BAD_L2, "r") as src, h5py.File(REPAIRED_L2, "w") as dst:
        for key in src.keys():
            src.copy(key, dst)
        del dst["L2/CH1/points"]
        dst["L2/CH1"].create_dataset("points", data=points, compression="gzip", compression_opts=4)
        processing = dst["metadata/processing"]
        pipe.write_str_attr(processing, "time_repair_status", "REPAIRED_TIME_EXPERIMENT")
        pipe.write_str_attr(processing, "time_repair_method", "linear interpolation from neighboring CH1 GNSS boundaries using PULSE_INDEX_CH1")
        pipe.write_str_attr(processing, "time_repair_prev_l1", str(PREV_L1.relative_to(ROOT)))
        pipe.write_str_attr(processing, "time_repair_next_l1", str(NEXT_L1.relative_to(ROOT)))
        processing.attrs["time_repair_raw_start_sec"] = raw_start
        processing.attrs["time_repair_raw_end_sec"] = raw_end
        processing.attrs["time_repair_pulse_period_sec"] = pulse_period

    return {
        "prev_raw_min": prev_min,
        "prev_raw_max": prev_max,
        "next_raw_min": next_min,
        "next_raw_max": next_max,
        "pulse_min": pulse_min,
        "pulse_max": pulse_max,
        "pulse_period_sec": pulse_period,
        "repaired_raw_start": raw_start,
        "repaired_raw_end": raw_end,
        "repaired_lidar_start": raw_start + pipe.DEFAULT_TIME_OFFSET_SEC,
        "repaired_lidar_end": raw_end + pipe.DEFAULT_TIME_OFFSET_SEC,
        "repaired_point_count": int(points.size),
    }


def run_repaired_stage2_stage3() -> tuple[pipe.Stage2Report, pipe.Stage3Report]:
    args = SimpleNamespace(
        input_l2=REPAIRED_L2,
        input_l2_pos=REPAIRED_L2P,
        l2_pos_dir=L2_POS_DIR,
        l3_dir=L3_DIR,
        preview_dir=PREVIEW_DIR,
        metadata_dir=ROOT / "metadata",
        pos_source=ROOT / "0510_f3" / "0510f3_processed.mat",
        reference_l3=ROOT / "0510_f3" / "L3_DATA" / "L2_cap_00111_20260510190957.h5",
        pos_low_confidence_threshold_sec=0.2,
        stage3_range_min_m=30.0,
    )
    stage2 = pipe.run_stage2(args)
    args.input_l2_pos = Path(stage2.output_l2_pos)
    stage3 = pipe.run_stage3(args)
    return stage2, stage3


def merge_with_repaired_00113() -> tuple[np.ndarray, list[float]]:
    source_paths = [
        L3_DIR / "L3_CH1_cap_00111_20260510190957.h5",
        L3_DIR / "L3_CH1_cap_00112_20260510191000.h5",
        REPAIRED_L3,
        L3_DIR / "L3_CH1_cap_00114_20260510191006.h5",
        L3_DIR / "L3_CH1_cap_00115_20260510191009.h5",
    ]
    merged = pipe.write_stage4_merged_l3(MERGED_L3, source_paths)
    pipe.make_stage3_preview(MERGED_PREVIEW, merged["easting_m"], merged["northing_m"], merged["height_m"])

    ranges: list[tuple[float, float]] = []
    for path in source_paths:
        with h5py.File(path, "r") as h5:
            points = h5["L3/CH1/points"][:]
        ranges.append((float(np.min(points["gps_time"])), float(np.max(points["gps_time"]))))
    gaps = [float(current[0] - prev[1]) for prev, current in zip(ranges, ranges[1:])]
    return merged, gaps


def write_report(model: dict[str, float], stage2: pipe.Stage2Report, stage3: pipe.Stage3Report, merged: np.ndarray, gaps: list[float]) -> None:
    report = {
        "stage_name": "stage4_00113_time_repair_experiment",
        "time_repair_status": "REPAIRED_TIME_EXPERIMENT",
        "input_bad_l2": str(BAD_L2.relative_to(ROOT)),
        "output_repaired_l2": str(REPAIRED_L2.relative_to(ROOT)),
        "output_repaired_l2_pos": str(REPAIRED_L2P.relative_to(ROOT)),
        "output_repaired_l3": str(REPAIRED_L3.relative_to(ROOT)),
        "output_merged_l3": str(MERGED_L3.relative_to(ROOT)),
        "preview_html": str(MERGED_PREVIEW.relative_to(ROOT)),
        "model": model,
        "stage2_pos_match_success_rate": stage2.pos_match_success_rate,
        "stage2_pos_match_success_count": stage2.pos_match_success_count,
        "stage3_point_count_after": stage3.point_count_after,
        "merged_point_count": int(merged.size),
        "time_gaps_seconds": gaps,
        "merged_gps_time": pipe.dataclass_to_jsonable(pipe.finite_stats(merged["gps_time"])),
        "merged_easting": pipe.dataclass_to_jsonable(pipe.finite_stats(merged["easting_m"])),
        "merged_northing": pipe.dataclass_to_jsonable(pipe.finite_stats(merged["northing_m"])),
        "merged_height": pipe.dataclass_to_jsonable(pipe.finite_stats(merged["height_m"])),
        "conclusion": "基本合理但有风险",
        "recommendation": "请人工查看修复预览；若缺失扫描带被补上且接缝可接受，再决定是否把 00113 作为修复数据纳入阶段 4。",
        "known_warnings": [
            "00113 原始 GNSS_SEC_CH1 异常，本结果按 PULSE_INDEX_CH1 线性重建时间轴。",
            "这是数据修复实验，不是原始可靠时间戳恢复。",
            "修复仅用于判断是否能补上缺失扫描带；进入全量处理前应保留 repaired 标记。",
        ],
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    warnings = "\n".join(f"- {item}" for item in report["known_warnings"])
    REPORT_MD.write_text(
        f"""# Stage 4 00113 Time Repair Experiment

## Gate Conclusion

- 结论：{report["conclusion"]}
- 建议：{report["recommendation"]}
- 标记：`REPAIRED_TIME_EXPERIMENT`

## Time Repair Model

- Previous file raw max: {model["prev_raw_max"]:.9f}
- Next file raw min: {model["next_raw_min"]:.9f}
- Repaired raw time: {model["repaired_raw_start"]:.9f} ~ {model["repaired_raw_end"]:.9f}
- Repaired lidar time: {model["repaired_lidar_start"]:.9f} ~ {model["repaired_lidar_end"]:.9f}
- Pulse index: {model["pulse_min"]:.0f} ~ {model["pulse_max"]:.0f}
- Pulse period seconds: {model["pulse_period_sec"]:.12f}

## Processing Result

- Stage 2 POS match success rate: {stage2.pos_match_success_rate:.6%}
- Stage 2 POS match success count: {stage2.pos_match_success_count:,}
- Repaired 00113 L3 point count: {stage3.point_count_after:,}
- Merged point count with repaired 00113: {merged.size:,}
- Time gaps seconds: {gaps}
- Merged GPS time: {pipe.format_stats(pipe.finite_stats(merged["gps_time"]))}
- Merged Easting: {pipe.format_stats(pipe.finite_stats(merged["easting_m"]))}
- Merged Northing: {pipe.format_stats(pipe.finite_stats(merged["northing_m"]))}
- Merged Height: {pipe.format_stats(pipe.finite_stats(merged["height_m"]))}

## Outputs

- Repaired L2: `{report["output_repaired_l2"]}`
- Repaired L2 POS: `{report["output_repaired_l2_pos"]}`
- Repaired L3: `{report["output_repaired_l3"]}`
- Merged L3: `{report["output_merged_l3"]}`
- Preview HTML: `{report["preview_html"]}`

## Known Warnings

{warnings}

## Gate Rule

Stop here. Do not use the repaired 00113 in Stage 5 until the user manually confirms this experiment is acceptable.
""",
        encoding="utf-8-sig",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair 00113 CH1 time as an experiment and rebuild the Stage 4 preview.")
    parser.parse_args()
    model = build_repaired_l2()
    stage2, stage3 = run_repaired_stage2_stage3()
    merged, gaps = merge_with_repaired_00113()
    write_report(model, stage2, stage3, merged, gaps)
    print("00113 time repair experiment complete.")
    print(f"POS match success rate: {stage2.pos_match_success_rate:.6%}")
    print(f"Repaired 00113 L3 points: {stage3.point_count_after:,}")
    print(f"Merged points: {merged.size:,}")
    print(f"Preview HTML: {MERGED_PREVIEW}")
    print(f"Markdown report: {REPORT_MD}")


if __name__ == "__main__":
    main()
