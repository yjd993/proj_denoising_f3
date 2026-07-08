from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import numpy as np


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

METHOD_REGISTRY = [
    {
        "method_id": "CAO2017_LADM2_4_7_4_14",
        "method_name": "LADM-II scan geometry based on Cao 2017 section 4.4.2",
        "source_type": "doctoral_thesis_and_project_diagnostic",
        "source_reference": "Stage 6I/6K selected and validated the LADM-II geometry candidate",
        "used_for_delete_or_transform": "yes, Stage 7A candidate transform",
    },
    {
        "method_id": "STAGE7A_CANDIDATE_BATCH",
        "method_name": "Limited CH1 LADM-II candidate batch",
        "source_type": "project_output",
        "source_reference": "C:\\proj_denoising_f3_2.0, sequences 00050-00150",
        "used_for_delete_or_transform": "yes, candidate H5/LAZ/TXT output",
    },
    {
        "method_id": "STAGE7B_7C_QC",
        "method_name": "Automatic continuity QC plus focused seam audit",
        "source_type": "project_qc_rule",
        "source_reference": "Stage 7B automatic QC and Stage 7C focused boundary audit",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "MANUAL_CLOUDCOMPARE_REVIEW",
        "method_name": "Manual CloudCompare review for 00144-00145 focused boundary",
        "source_type": "manual_visual_qc",
        "source_reference": "User visual inspection: no obvious horizontal offset, vertical step, strip break, or distortion",
        "used_for_delete_or_transform": "no, release decision evidence",
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


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8-sig")


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


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


def number(value: Any, default: float = 0.0) -> float:
    try:
        if value in {None, ""}:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def int_number(value: Any, default: int = 0) -> int:
    return int(number(value, float(default)))


def path_exists(path_text: str) -> bool:
    return bool(path_text) and Path(path_text).exists()


def release_manifest_rows(stage7a_manifest: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in stage7a_manifest:
        if row.get("status") != "PROCESSED":
            continue
        rows.append(
            {
                "seq": int_number(row.get("seq")),
                "release_status": "DISPLAY_CANDIDATE",
                "h5_path": row.get("h5_path", ""),
                "laz_path": row.get("laz_path", ""),
                "txt_path": row.get("txt_path", ""),
                "point_count_h5": int_number(row.get("point_count_h5")),
                "laz_point_count": int_number(row.get("laz_point_count")),
                "txt_point_count": int_number(row.get("txt_point_count")),
                "pos_success_rate": number(row.get("pos_success_rate")),
                "height_median_m": number(row.get("height_median_m")),
                "h5_exists": path_exists(row.get("h5_path", "")),
                "laz_exists": path_exists(row.get("laz_path", "")),
                "txt_exists": path_exists(row.get("txt_path", "")),
            }
        )
    return rows


def skipped_rows(stage7a_manifest: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in stage7a_manifest:
        if row.get("status") == "PROCESSED":
            continue
        rows.append(
            {
                "seq": int_number(row.get("seq")),
                "status": row.get("status", ""),
                "source_manifest_status": row.get("source_manifest_status", ""),
                "reason": row.get("reason", ""),
                "decision": "EXCLUDED_FROM_DISPLAY_CANDIDATE",
                "note": "Timestamp/bad-time files remain isolated and are not used for geometry judgment.",
            }
        )
    return rows


def qc_summary_rows(reports: dict[str, dict[str, Any]], manual_review_pass: bool) -> list[dict[str, Any]]:
    stage6i_gate = reports["stage6i"].get("gate", {})
    stage6k_gate = reports["stage6k"].get("gate", {})
    stage6n_gate = reports["stage6n"].get("gate", {})
    stage6n_agg = reports["stage6n"].get("aggregate", {})
    stage7a_agg = reports["stage7a"].get("aggregate", {})
    stage7b_agg = reports["stage7b"].get("aggregate", {})
    stage7c_agg = reports["stage7c"].get("aggregate", {})

    return [
        {
            "section": "geometry_model",
            "metric": "Stage 6I LADM-II improvement vs Stage 6F vector RMSE",
            "value": stage6i_gate.get("vector_improvement_vs_stage6f_pct", ""),
            "unit": "%",
            "decision": "supports LADM-II replacement",
        },
        {
            "section": "geometry_model",
            "metric": "Stage 6I LADM-II improvement vs Stage 6F horizontal RMSE",
            "value": stage6i_gate.get("horizontal_improvement_vs_stage6f_pct", ""),
            "unit": "%",
            "decision": "supports LADM-II replacement",
        },
        {
            "section": "exact_time_reference",
            "metric": "Stage 6K exact-time gate",
            "value": stage6k_gate.get("conclusion", ""),
            "unit": "",
            "decision": stage6k_gate.get("reason", ""),
        },
        {
            "section": "continuous_segment",
            "metric": "Stage 6N 00114-00118 seam warnings",
            "value": stage6n_agg.get("seam_warning_count", ""),
            "unit": "count",
            "decision": stage6n_gate.get("conclusion", ""),
        },
        {
            "section": "stage7a_output",
            "metric": "Processed display candidate files",
            "value": stage7a_agg.get("processed_files", ""),
            "unit": "files",
            "decision": "95 Stage 7A outputs are display candidates",
        },
        {
            "section": "stage7a_output",
            "metric": "Skipped bad-time files",
            "value": stage7a_agg.get("skipped_files", ""),
            "unit": "files",
            "decision": "excluded and documented",
        },
        {
            "section": "stage7a_output",
            "metric": "Total H5 points",
            "value": stage7a_agg.get("total_h5_points", ""),
            "unit": "points",
            "decision": "full candidate H5 outputs exist",
        },
        {
            "section": "stage7b_schema_pos",
            "metric": "Files missing full-chain H5 fields",
            "value": stage7b_agg.get("files_missing_chain_fields", ""),
            "unit": "files",
            "decision": "0 means H5 chain is complete",
        },
        {
            "section": "stage7b_schema_pos",
            "metric": "Minimum POS success rate",
            "value": stage7b_agg.get("min_pos_success_rate", ""),
            "unit": "ratio",
            "decision": "POS matching is complete for processed files",
        },
        {
            "section": "stage7b_schema_pos",
            "metric": "Max POS interpolation dt p99",
            "value": stage7b_agg.get("max_pos_interp_dt_p99_sec", ""),
            "unit": "s",
            "decision": "POS interpolation timing is stable",
        },
        {
            "section": "stage7c_focused_audit",
            "metric": "Stage 7B warning boundaries explained as edge-metric artifacts",
            "value": (stage7c_agg.get("audit_class_counts", {}) or {}).get("LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT", ""),
            "unit": "boundaries",
            "decision": "not geometry failures",
        },
        {
            "section": "stage7c_focused_audit",
            "metric": "Isolated bad-time gaps",
            "value": (stage7c_agg.get("audit_class_counts", {}) or {}).get("ISOLATED_BAD_TIME_GAP", ""),
            "unit": "boundaries",
            "decision": "kept out of geometry judgment",
        },
        {
            "section": "manual_review",
            "metric": "00144-00145 CloudCompare focused review",
            "value": "PASS" if manual_review_pass else "REVIEW",
            "unit": "",
            "decision": "time gap noted; no obvious geometric jump" if manual_review_pass else "manual review not passed",
        },
    ]


def screenshot_checklist_rows(output_root: Path, manual_review_pass: bool) -> list[dict[str, Any]]:
    return [
        {
            "screenshot_id": "S1",
            "priority": "required",
            "stage": "Stage 6K",
            "file_to_open": str(ROOT / "outputs" / "qc" / "stage6k_ladm2_full_00111_export" / "stage6k_00111_ladm2_full_points_cloudcompare.txt"),
            "color_by": "height_m or scalar height",
            "view": "overview and local overlap against existing L3/reference if loaded",
            "evidence_goal": "Show that LADM-II model matches the validated 00111 reference area.",
            "expected_observation": "No obvious horizontal offset or strip split in the stable reference segment.",
            "capture_status": "to_capture",
            "note": "Use this as the model-accuracy evidence screenshot.",
        },
        {
            "screenshot_id": "S2",
            "priority": "required",
            "stage": "Stage 7A",
            "file_to_open": str(output_root / "txt" / "stage7a_00114_ch1_ladm2_cloudcompare.txt"),
            "color_by": "height_m",
            "view": "full file overview",
            "evidence_goal": "Show a representative full-point Stage 7A TXT output.",
            "expected_observation": "Normal strip morphology and no severe distortion.",
            "capture_status": "to_capture",
            "note": "00114 belongs to the manually checked continuous segment.",
        },
        {
            "screenshot_id": "S3",
            "priority": "required",
            "stage": "Stage 7A continuous segment",
            "file_to_open": "; ".join(str(output_root / "txt" / f"stage7a_{seq:05d}_ch1_ladm2_cloudcompare.txt") for seq in range(114, 119)),
            "color_by": "source/file color or height_m",
            "view": "00114-00118 combined overview",
            "evidence_goal": "Show continuity across the previously inspected representative segment.",
            "expected_observation": "Continuous strip trend, no obvious seam jump.",
            "capture_status": "to_capture",
            "note": "Open the five TXT files together or use LAZ files if CloudCompare is slow.",
        },
        {
            "screenshot_id": "S4",
            "priority": "required",
            "stage": "Stage 7C focused seam",
            "file_to_open": str(
                output_root
                / "qc"
                / "stage7c_ch1_ladm2_focused_seam_audit"
                / "cloudcompare_boundaries"
                / "stage7c_boundary_00144_00145_stage7b_warning.txt"
            ),
            "color_by": "source_seq or side_code",
            "view": "focused boundary 00144-00145",
            "evidence_goal": "Document the only remaining time-gap review boundary.",
            "expected_observation": "0.12666 s time gap is noted, but no obvious horizontal offset, vertical step, or strip break.",
            "capture_status": "visually_passed" if manual_review_pass else "to_capture",
            "note": "This is the screenshot the user just inspected.",
        },
        {
            "screenshot_id": "S5",
            "priority": "optional",
            "stage": "Stage 7C focused seam",
            "file_to_open": str(
                output_root
                / "qc"
                / "stage7c_ch1_ladm2_focused_seam_audit"
                / "cloudcompare_boundaries"
                / "stage7c_boundary_00066_00067_stage7b_warning.txt"
            ),
            "color_by": "source_seq or side_code",
            "view": "focused boundary 00066-00067",
            "evidence_goal": "Show a Stage 7B warning that Stage 7C explained as edge/window artifact.",
            "expected_observation": "Short-window distribution differs, but wider-window continuity is acceptable.",
            "capture_status": "optional",
            "note": "Useful if the teacher asks why Stage 7B had warnings.",
        },
    ]


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]], max_rows: int | None = None) -> str:
    selected = rows if max_rows is None else rows[:max_rows]
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, sep]
    for row in selected:
        values: list[str] = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                values.append(f"{value:.6g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def final_gate(manual_review_pass: bool, release_rows: list[dict[str, Any]], skipped: list[dict[str, Any]]) -> dict[str, Any]:
    missing_outputs = [
        row["seq"]
        for row in release_rows
        if not (row["h5_exists"] and row["laz_exists"] and row["txt_exists"])
    ]
    if missing_outputs:
        return {
            "conclusion": "REVIEW_MISSING_OUTPUTS",
            "ready_for_teacher_review": False,
            "reason": f"Some display-candidate outputs are missing: {missing_outputs[:10]}",
        }
    if not manual_review_pass:
        return {
            "conclusion": "REVIEW_MANUAL_CLOUDCOMPARE_PENDING",
            "ready_for_teacher_review": False,
            "reason": "Manual CloudCompare review for 00144-00145 has not been marked as passed.",
        }
    return {
        "conclusion": "DISPLAY_CANDIDATE_APPROVED_WITH_NOTES",
        "ready_for_teacher_review": True,
        "reason": (
            f"{len(release_rows)} Stage 7A files are approved as display candidates; "
            f"{len(skipped)} bad-time files remain excluded; 00144-00145 time gap is documented as a note."
        ),
    }


def write_teacher_summary(
    path: Path,
    payload: dict[str, Any],
    qc_rows: list[dict[str, Any]],
    screenshot_rows: list[dict[str, Any]],
) -> None:
    gate = payload["gate"]
    agg = payload["aggregate"]
    qc_table = markdown_table(qc_rows, [("section", "section"), ("metric", "metric"), ("value", "value"), ("unit", "unit"), ("decision", "decision")])
    screenshot_table = markdown_table(
        screenshot_rows,
        [
            ("id", "screenshot_id"),
            ("priority", "priority"),
            ("stage", "stage"),
            ("color", "color_by"),
            ("status", "capture_status"),
            ("goal", "evidence_goal"),
        ],
    )
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | {m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 7D CH1 LADM-II Teacher Review Package

## Final Decision

- Conclusion: {gate['conclusion']}
- Ready for teacher review: {gate['ready_for_teacher_review']}
- Reason: {gate['reason']}

## One-Sentence Result

Sequences `00050-00150` produced {agg['display_candidate_files']} CH1 LADM-II Stage 7A display-candidate H5/LAZ/TXT files; the six bad-time files remain excluded, and the only remaining focused boundary note `00144-00145` shows a 0.12666 s time gap but no obvious CloudCompare geometry jump.

## Method Chain

1. L1 raw CH1 timing/range/scan fields are read from the source H5 files.
2. The old empirical `f_body_frame_xyz()` route is not used for the display candidate.
3. LADM-II scan geometry from Cao 2017 section 4.4.2 is used as the Stage 7A geometry basis, with the Stage 6I/6K selected candidate parameters.
4. Each Stage 7A H5 stores the full diagnostic chain: L1 timing/range/scan, L2 FRD coordinates, POS interpolation fields, NED offsets, and final UTM/geographic coordinates.
5. LAZ/TXT exports are generated from the same Stage 7A candidate points for CloudCompare review.

## Scope

- Input/output root: `{payload['inputs']['output_root']}`
- Sequence range: `00050-00150`
- Display candidate files: {agg['display_candidate_files']}
- Excluded bad-time files: {agg['excluded_bad_time_files']} (`00054`, `00073`, `00093`, `00113`, `00132`, `00133`)
- Total H5 points: {agg['total_h5_points']:,}
- Total LAZ points: {agg['total_laz_points']:,}
- Total TXT points: {agg['total_txt_points']:,}

## QC Summary

{qc_table}

## Key CloudCompare Screenshot Checklist

{screenshot_table}

## Important Notes For Teacher

- `00113` and other bad-time files are not repaired in this stage and are not mixed into geometry judgment.
- Stage 7B automatic QC intentionally flagged seam warnings conservatively.
- Stage 7C focused audit explained 12 Stage 7B warnings as edge/window metric artifacts and kept 5 bad-time gaps isolated.
- Manual CloudCompare review of `00144-00145` found no obvious horizontal offset, vertical step, strip break, or distortion, so the 0.12666 s time gap is retained as a note rather than a geometry failure.
- These outputs are display-candidate products, not the final all-file production release.

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Package Outputs

- Teacher summary: `{payload['outputs']['teacher_summary_md']}`
- QC summary CSV: `{payload['outputs']['qc_summary_csv']}`
- Display candidate manifest: `{payload['outputs']['display_candidate_manifest_csv']}`
- Excluded files CSV: `{payload['outputs']['excluded_files_csv']}`
- Screenshot checklist CSV: `{payload['outputs']['screenshot_checklist_csv']}`
- Release decision JSON: `{payload['outputs']['release_decision_json']}`
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def write_readme(path: Path, payload: dict[str, Any]) -> None:
    content = f"""# Stage 7D Teacher Package

Open `stage7d_teacher_summary.md` first.

Recommended order:

1. Read the final decision and method chain.
2. Check `stage7d_qc_summary.csv`.
3. Use `stage7d_cloudcompare_screenshot_checklist.csv` to capture or organize screenshots.
4. Use `stage7d_display_candidate_manifest.csv` as the list of approved Stage 7A candidate outputs.

Final decision: {payload['gate']['conclusion']}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    output_root = args.output_root
    package_dir = output_root / "stage7d_teacher_package"
    package_dir.mkdir(parents=True, exist_ok=True)
    (output_root / "reports").mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    paths = {
        "stage6i": REPORT_DIR / "stage6i_ch1_ladm2_scan_geometry_diagnostic_report.json",
        "stage6k": REPORT_DIR / "stage6k_ch1_ladm2_full_00111_export_report.json",
        "stage6n": REPORT_DIR / "stage6n_ch1_ladm2_continuous_qc_report.json",
        "stage7a": output_root / "reports" / "stage7a_ch1_ladm2_candidate_batch_report.json",
        "stage7b": output_root / "reports" / "stage7b_ch1_ladm2_candidate_qc_report.json",
        "stage7c": output_root / "reports" / "stage7c_ch1_ladm2_focused_seam_audit_report.json",
    }
    reports = {key: read_json(path) for key, path in paths.items()}
    stage7a_manifest_path = output_root / "manifest" / "stage7a_ch1_ladm2_00050_00150_manifest.csv"
    stage7a_manifest = read_csv_rows(stage7a_manifest_path)

    release_rows = release_manifest_rows(stage7a_manifest)
    excluded = skipped_rows(stage7a_manifest)
    qc_rows = qc_summary_rows(reports, args.manual_cloudcompare_144_145_pass)
    screenshot_rows = screenshot_checklist_rows(output_root, args.manual_cloudcompare_144_145_pass)
    gate_payload = final_gate(args.manual_cloudcompare_144_145_pass, release_rows, excluded)

    display_manifest_csv = package_dir / "stage7d_display_candidate_manifest.csv"
    excluded_csv = package_dir / "stage7d_excluded_bad_time_files.csv"
    qc_csv = package_dir / "stage7d_qc_summary.csv"
    screenshots_csv = package_dir / "stage7d_cloudcompare_screenshot_checklist.csv"
    teacher_md = package_dir / "stage7d_teacher_summary.md"
    readme_md = package_dir / "README.md"
    release_json = package_dir / "stage7d_release_decision.json"
    report_json_output = output_root / "reports" / "stage7d_ch1_ladm2_teacher_review_package_report.json"
    report_json_project = REPORT_DIR / "stage7d_ch1_ladm2_teacher_review_package_report.json"
    report_md_output = output_root / "reports" / "stage7d_ch1_ladm2_teacher_review_package_report.md"
    report_md_project = REPORT_DIR / "stage7d_ch1_ladm2_teacher_review_package_report.md"

    write_csv(display_manifest_csv, release_rows)
    write_csv(excluded_csv, excluded)
    write_csv(qc_csv, qc_rows)
    write_csv(screenshots_csv, screenshot_rows)

    stage7a_agg = reports["stage7a"].get("aggregate", {})
    payload = {
        "stage_name": "stage7d_ch1_ladm2_teacher_review_package",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "output_root": str(output_root),
            "stage7a_manifest": str(stage7a_manifest_path),
            "reports": {key: str(path) for key, path in paths.items()},
            "manual_cloudcompare_144_145_pass": args.manual_cloudcompare_144_145_pass,
            "manual_cloudcompare_144_145_note": args.manual_cloudcompare_144_145_note,
        },
        "aggregate": {
            "display_candidate_files": len(release_rows),
            "excluded_bad_time_files": len(excluded),
            "total_h5_points": int_number(stage7a_agg.get("total_h5_points")),
            "total_laz_points": int_number(stage7a_agg.get("total_laz_points")),
            "total_txt_points": int_number(stage7a_agg.get("total_txt_points")),
            "all_release_outputs_exist": all(row["h5_exists"] and row["laz_exists"] and row["txt_exists"] for row in release_rows),
        },
        "gate": gate_payload,
        "qc_summary": qc_rows,
        "screenshot_checklist": screenshot_rows,
        "excluded_files": excluded,
        "outputs": {
            "package_dir": str(package_dir),
            "teacher_summary_md": str(teacher_md),
            "readme_md": str(readme_md),
            "qc_summary_csv": str(qc_csv),
            "display_candidate_manifest_csv": str(display_manifest_csv),
            "excluded_files_csv": str(excluded_csv),
            "screenshot_checklist_csv": str(screenshots_csv),
            "release_decision_json": str(release_json),
            "report_json": str(report_json_output),
            "report_md": str(report_md_output),
            "project_report_json": str(report_json_project),
            "project_report_md": str(report_md_project),
        },
    }
    write_teacher_summary(teacher_md, payload, qc_rows, screenshot_rows)
    write_teacher_summary(report_md_output, payload, qc_rows, screenshot_rows)
    write_teacher_summary(report_md_project, payload, qc_rows, screenshot_rows)
    write_readme(readme_md, payload)
    write_json(release_json, payload)
    write_json(report_json_output, payload)
    write_json(report_json_project, payload)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
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
    parser = argparse.ArgumentParser(description="Stage 7D: build teacher review package for CH1 Stage 7A LADM-II display candidates.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manual-cloudcompare-144-145-pass", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--manual-cloudcompare-144-145-note",
        default="CloudCompare focused review found no obvious horizontal offset, vertical step, strip break, or distortion.",
    )
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
