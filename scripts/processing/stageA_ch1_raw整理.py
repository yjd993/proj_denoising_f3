from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import h5py
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "outputs" / "h5_ch1"
RAW_DIR = ROOT / "outputs" / "h5_ch1" / "raw"
QC_DIR = ROOT / "outputs" / "qc"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
SUMMARY_CSV = QC_DIR / "stageA_CH1_raw整理_summary.csv"
REPORT_MD = REPORT_DIR / "stageA_CH1_raw整理_report.md"
REPORT_JSON = REPORT_DIR / "stageA_CH1_raw整理_report.json"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def raw_name(src: Path) -> str:
    return src.name.replace("L3S_CH1_", "L3_CH1_raw_")


def create_hardlink_or_reuse(src: Path, dst: Path) -> str:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return "exists"
    try:
        os.link(src, dst)
        return "hardlink"
    except OSError:
        return "failed"


def inspect_h5(path: Path) -> dict[str, object]:
    with h5py.File(path, "r") as h5:
        ch1 = h5["L3/CH1/points"]
        ch1_count = int(ch1.shape[0])
        ch2_count = int(h5["L3/CH2/points"].shape[0])
        ch3_count = int(h5["L3/CH3/points"].shape[0])
        ch4_count = int(h5["L3/CH4/points"].shape[0])
        points = ch1[:]
    return {
        "point_count_ch1": ch1_count,
        "point_count_ch2": ch2_count,
        "point_count_ch3": ch3_count,
        "point_count_ch4": ch4_count,
        "gps_min": float(np.min(points["gps_time"])) if points.size else float("nan"),
        "gps_max": float(np.max(points["gps_time"])) if points.size else float("nan"),
        "time_repair_points": int(np.count_nonzero(points["time_repair_flag"])) if points.size else 0,
        "channel_values": ",".join(map(str, np.unique(points["channel"]).tolist())) if points.size else "",
    }


def main() -> None:
    sources = sorted(SRC_DIR.glob("L3S_CH1_cap_*.h5"))
    rows: list[dict[str, object]] = []
    total_points = 0
    total_repaired_points = 0
    link_failed = []
    nonempty_other_channel = []

    for src in sources:
        dst = RAW_DIR / raw_name(src)
        link_status = create_hardlink_or_reuse(src, dst)
        if link_status == "failed":
            link_failed.append(src.name)
            continue
        stats = inspect_h5(dst)
        total_points += int(stats["point_count_ch1"])
        total_repaired_points += int(stats["time_repair_points"])
        if stats["point_count_ch2"] or stats["point_count_ch3"] or stats["point_count_ch4"]:
            nonempty_other_channel.append(dst.name)
        rows.append(
            {
                "source_file": rel(src),
                "raw_file": rel(dst),
                "storage_mode": link_status,
                **stats,
            }
        )

    QC_DIR.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_file",
        "raw_file",
        "storage_mode",
        "point_count_ch1",
        "point_count_ch2",
        "point_count_ch3",
        "point_count_ch4",
        "gps_min",
        "gps_max",
        "time_repair_points",
        "channel_values",
    ]
    with SUMMARY_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    if link_failed:
        conclusion = "不合理"
        recommendation = "硬链接创建失败；暂停，改用 C 盘备用目录或路径 manifest。"
    elif nonempty_other_channel:
        conclusion = "不合理"
        recommendation = "CH1 raw 文件中发现非空 CH2/CH3/CH4，占位规则被破坏，需排查。"
    elif len(rows) != len(sources):
        conclusion = "不合理"
        recommendation = "raw 文件数量与源文件数量不一致，需排查。"
    else:
        conclusion = "合理"
        recommendation = "可以进入 Stage B：CH1 轻度去噪。"

    report = {
        "stage_name": "Stage A CH1 raw 整理",
        "input_files": len(sources),
        "output_files": len(rows),
        "storage_mode": "hardlink_or_existing",
        "point_count_ch1_total": total_points,
        "time_repair_points_total": total_repaired_points,
        "link_failed": link_failed,
        "nonempty_other_channel_files": nonempty_other_channel,
        "method_registry": [
            {
                "method_id": "DATA_ORG_000",
                "method_name": "raw L3 file organization by hardlink",
                "purpose": "整理 CH1 raw L3，不改变点云坐标或删点",
                "source_type": "data_management",
                "source_reference": "project storage rule",
                "used_for_delete_or_transform": "no",
            }
        ],
        "project_empirical_parameters": [],
        "gate_conclusion": conclusion,
        "recommendation": recommendation,
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8-sig")

    REPORT_MD.write_text(
        f"""# Stage A CH1 Raw 整理报告

## Gate Conclusion

- 结论：{conclusion}
- 建议：{recommendation}

## Inputs and Outputs

- Input directory: `{rel(SRC_DIR)}`
- Output raw directory: `{rel(RAW_DIR)}`
- Input files: {len(sources)}
- Output raw files: {len(rows)}
- Storage mode: hardlink first, reuse if exists
- Summary CSV: `{rel(SUMMARY_CSV)}`

## Key Statistics

- Total CH1 raw points: {total_points:,}
- Time-repaired points retained: {total_repaired_points:,}
- Hardlink failed files: {len(link_failed)}
- Files with non-empty CH2/CH3/CH4: {len(nonempty_other_channel)}

## Method Registry

| method_id | method_name | source_type | used_for_delete_or_transform |
|---|---|---|---|
| DATA_ORG_000 | raw L3 file organization by hardlink | data_management | no |

## Project Empirical Parameters

- 无。本阶段只整理文件，不进行坐标转换、时间修复、去噪或删点。

## Manual Checklist

- 确认 `outputs/h5_ch1/raw` 中只作为 CH1 raw 成果使用。
- 确认 CH2/CH3/CH4 没有写入 CH1 raw 文件。
- 确认 raw 文件数量与当前 CH1 stage5 输出一致。
- 确认硬链接整理方式可以接受：不重复占用 25GB+ 磁盘空间。

## Gate Rule

Stop here. Do not run Stage B until the user manually confirms this Stage A result is acceptable.
""",
        encoding="utf-8-sig",
    )

    print(f"Stage A conclusion: {conclusion}")
    print(f"Recommendation: {recommendation}")
    print(f"Raw dir: {RAW_DIR}")
    print(f"Report: {REPORT_MD}")
    print(f"Summary: {SUMMARY_CSV}")


if __name__ == "__main__":
    main()
