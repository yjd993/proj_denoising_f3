import argparse
import csv
import itertools
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5
import stage5g2_ch1_body_to_ned_diagnostic as diag
import stage6d_ch1_rotation_zero_diagnostic as stage6d
import stage6e_ch1_bias_validation as stage6e
import stage6f_ch1_boresight_lever_diagnostic as stage6f


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "outputs" / "qc" / "stage6i_ladm2_scan_geometry_diagnostic"
REPORT_DIR = ROOT / "metadata" / "stage_reports"
STAGE6F_BEST = ROOT / "outputs" / "qc" / "stage6f_boresight_lever_diagnostic" / "best_candidate.json"
PDF_SOURCE = ROOT / "遥感测深数据处理方法研究_曹彬才.pdf"

ZERO_OFFSET_M = stage6e.ZERO_OFFSET_M
ANGLE_DIRECTIONS = ["360-angle", "angle"]
ROTATION_ORDER = stage6e.ROTATION_ORDER
ROTATION_TRANSPOSE = stage6e.ROTATION_TRANSPOSE

COARSE_FRAME_ROTATION_DEG = [-45.0, 45.0]
LOCAL_OFFSET_DELTA_DEG = [-2.0, -1.0, 0.0, 1.0, 2.0]
LOCAL_TILT_DELTA_DEG = [-0.75, -0.25, 0.0, 0.25, 0.75]
LOCAL_FRAME_DELTA_DEG = [-2.0, 0.0, 2.0]
BORESIGHT_COARSE_DEG = [-2.0, -1.0, 0.0, 1.0, 2.0]
BORESIGHT_REFINE_DELTA_DEG = [-0.5, -0.25, 0.0, 0.25, 0.5]
BORESIGHT_OFFSET_REFINE_DELTA_DEG = [-0.5, 0.0, 0.5]
FINE_OFFSET_DELTA_DEG = [-0.2, -0.1, 0.0, 0.1, 0.2]
FINE_TILT_DELTA_DEG = [-0.1, -0.05, 0.0, 0.05, 0.1]
FINE_BORESIGHT_DELTA_DEG = [-0.2, 0.0, 0.2]

METHOD_REGISTRY = [
    {
        "method_id": "CAO2017_LADM2_4_7_4_14",
        "method_name": "LADM-II mirror normal and reflected beam scan geometry",
        "source_type": "doctoral_thesis",
        "source_reference": "曹彬才, 遥感测深数据处理方法研究, section 4.4.2, formulas 4-7 to 4-14",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "PROJECT_DIAGNOSTIC_PARAMETER",
        "method_name": "Stage 6I LADM-II scan geometry candidate search",
        "source_type": "project_diagnostic_parameter",
        "source_reference": "Exact-time comparison with existing L3 00111; not final production calibration",
        "used_for_delete_or_transform": "yes, diagnostic transform only",
    },
    {
        "method_id": "EXACT_TIME_MATCH_QC",
        "method_name": "Reference L3 exact GNSS time validation",
        "source_type": "project_qc_rule",
        "source_reference": "Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18",
        "used_for_delete_or_transform": "no, QC only",
    },
]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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


def load_stage6f_best() -> dict[str, Any]:
    if not STAGE6F_BEST.exists():
        raise FileNotFoundError(f"Stage 6F best candidate not found: {STAGE6F_BEST}")
    return json.loads(STAGE6F_BEST.read_text(encoding="utf-8-sig"))


def axis_mapping_candidates() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for perm in itertools.permutations([0, 1, 2]):
        for signs in itertools.product([1, -1], repeat=3):
            labels = []
            for axis_idx, (src_idx, sign) in enumerate(zip(perm, signs)):
                dst = "FRD"[axis_idx]
                src = "sXYZ"[1 + src_idx]
                labels.append(f"{dst}={'+' if sign > 0 else '-'}{src}")
            rows.append(
                {
                    "axis_mapping": ",".join(labels),
                    "axis_perm": tuple(int(v) for v in perm),
                    "axis_signs": tuple(int(v) for v in signs),
                }
            )
    return rows


AXIS_MAPPINGS = axis_mapping_candidates()


def build_geom(data: dict[str, np.ndarray], calibration: dict[str, float]) -> dict[str, np.ndarray]:
    range_m = (data["range_before"] - ZERO_OFFSET_M - calibration["intercept"]) / calibration["slope"]
    roll, pitch, heading = stage6d.prepare_angles(
        data,
        stage6e.ROLL_SIGN,
        stage6e.PITCH_SIGN,
        stage6e.HEADING_SIGN,
        stage6e.HEADING_CONVENTION,
    )
    truth = np.column_stack([data["ref_north_offset"], data["ref_east_offset"], data["ref_down_offset"]])
    return {
        "coder": data["coder"].astype(np.float64),
        "range_m": range_m.astype(np.float64),
        "truth_ned": truth.astype(np.float64),
        "roll": roll,
        "pitch": pitch,
        "heading": heading,
    }


def rotation_columns(geom: dict[str, np.ndarray]) -> np.ndarray:
    n = geom["range_m"].size
    basis = []
    for axis_idx in range(3):
        frd = np.zeros((n, 3), dtype=np.float64)
        frd[:, axis_idx] = 1.0
        basis.append(
            diag.rotate_frd_to_ned(
                frd,
                geom["roll"],
                geom["pitch"],
                geom["heading"],
                ROTATION_ORDER,
                ROTATION_TRANSPOSE,
            )
        )
    return np.stack(basis, axis=2)


def ladm2_sensor_unit(
    angle_deg: np.ndarray,
    mirror_tilt_deg: float,
    frame_rotation_deg: float,
) -> np.ndarray:
    """Return reflected beam unit vectors in PDF sensor axes sX/sY/sZ-up.

    This implements the same geometry as Cao 2017 formulas 4-7 to 4-14:
    a mirror normal tilted by 7.5 deg in X'Y'Z', transformed to sXYZ by
    a Y-axis frame rotation, then used as the plane normal for reflection
    of the incoming laser beam along negative sX.
    """
    theta = np.deg2rad(angle_deg.astype(np.float64))
    tilt = math.radians(float(mirror_tilt_deg))
    normal_prime = np.column_stack(
        [
            math.sin(tilt) * np.cos(theta),
            math.sin(tilt) * np.sin(theta),
            -math.cos(tilt) * np.ones_like(theta),
        ]
    )
    gamma = math.radians(float(frame_rotation_deg))
    frame_rotation = np.array(
        [
            [math.cos(gamma), 0.0, math.sin(gamma)],
            [0.0, 1.0, 0.0],
            [-math.sin(gamma), 0.0, math.cos(gamma)],
        ],
        dtype=np.float64,
    )
    normal = normal_prime @ frame_rotation.T
    normal /= np.maximum(np.linalg.norm(normal, axis=1)[:, None], 1e-12)
    incoming = np.array([-1.0, 0.0, 0.0], dtype=np.float64)
    reflected = incoming - 2.0 * np.sum(incoming * normal, axis=1)[:, None] * normal
    reflected /= np.maximum(np.linalg.norm(reflected, axis=1)[:, None], 1e-12)
    return reflected


def map_sensor_to_frd(sensor_unit: np.ndarray, mapping: dict[str, Any]) -> np.ndarray:
    perm = mapping["axis_perm"]
    signs = mapping["axis_signs"]
    return np.column_stack([signs[i] * sensor_unit[:, perm[i]] for i in range(3)])


def unit_for_candidate(geom: dict[str, np.ndarray], row: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    angle = stage6d.scan_angle(geom["coder"], str(row["angle_direction"]), float(row["angle_offset_deg"]))
    sensor_unit = ladm2_sensor_unit(angle, float(row["mirror_tilt_deg"]), float(row["frame_rotation_deg"]))
    unit_frd = map_sensor_to_frd(sensor_unit, row)
    return angle, unit_frd


def solve_lever_ls(rotation_cols: np.ndarray, residual_no_lever: np.ndarray, lever_limit_m: float) -> np.ndarray:
    normal = np.einsum("nij,nik->jk", rotation_cols, rotation_cols)
    rhs = -np.einsum("nij,ni->j", rotation_cols, residual_no_lever)
    try:
        lever = np.linalg.solve(normal, rhs)
    except np.linalg.LinAlgError:
        lever = np.linalg.lstsq(normal, rhs, rcond=None)[0]
    return np.clip(lever, -lever_limit_m, lever_limit_m).astype(np.float64)


def evaluate_candidate(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    row: dict[str, Any],
    candidate_stage: str,
    lever_limit_m: float,
    resolve_lever: bool = True,
    return_diff: bool = False,
) -> dict[str, Any] | tuple[dict[str, Any], np.ndarray, np.ndarray]:
    angle, unit_frd = unit_for_candidate(geom, row)
    if float(np.mean(unit_frd[:, 2])) <= 0.0:
        empty = {
            **row,
            "candidate_stage": candidate_stage,
            "sample_points_used": int(geom["range_m"].size),
            "invalid_reason": "mean_frd_down_not_positive",
            "vector_rmse_m": float("inf"),
            "horizontal_rmse_m": float("inf"),
            "down_rmse_m": float("inf"),
        }
        return (empty, np.empty((0, 3)), angle) if return_diff else empty

    boresight = (
        float(row.get("boresight_roll_deg", 0.0)),
        float(row.get("boresight_pitch_deg", 0.0)),
        float(row.get("boresight_yaw_deg", 0.0)),
    )
    frd = unit_frd * geom["range_m"][:, None]
    if boresight != (0.0, 0.0, 0.0):
        frd = diag.apply_boresight(frd, *boresight)
    pred_no_lever = diag.rotate_frd_to_ned(
        frd,
        geom["roll"],
        geom["pitch"],
        geom["heading"],
        ROTATION_ORDER,
        ROTATION_TRANSPOSE,
    )
    residual_no_lever = pred_no_lever - geom["truth_ned"]
    if resolve_lever:
        lever = solve_lever_ls(rotation_cols, residual_no_lever, lever_limit_m)
    else:
        lever = np.array(
            [
                float(row.get("lever_x_m", 0.0)),
                float(row.get("lever_y_m", 0.0)),
                float(row.get("lever_z_m", 0.0)),
            ],
            dtype=np.float64,
        )
    pred = pred_no_lever + np.einsum("nij,j->ni", rotation_cols, lever)
    diff = pred - geom["truth_ned"]
    metrics = stage6d.metrics(diff)
    out = {
        **row,
        "candidate_stage": candidate_stage,
        "boresight_roll_deg": boresight[0],
        "boresight_pitch_deg": boresight[1],
        "boresight_yaw_deg": boresight[2],
        "boresight_abs_max_deg": float(max(abs(v) for v in boresight)),
        "lever_x_m": float(lever[0]),
        "lever_y_m": float(lever[1]),
        "lever_z_m": float(lever[2]),
        "lever_norm_m": float(np.linalg.norm(lever)),
        "sample_points_used": int(diff.shape[0]),
        "mean_frd_down": float(np.mean(unit_frd[:, 2])),
        "scan_angle_mean_deg": float(np.mean(angle)),
        "scan_angle_std_deg": float(np.std(angle)),
        **metrics,
    }
    return (out, diff, angle) if return_diff else out


def candidate_key(row: dict[str, Any], include_boresight: bool = True) -> tuple[Any, ...]:
    key: list[Any] = [
        str(row["angle_direction"]),
        round(float(row["angle_offset_deg"]), 6),
        round(float(row["mirror_tilt_deg"]), 6),
        round(float(row["frame_rotation_deg"]), 6),
        str(row["axis_mapping"]),
    ]
    if include_boresight:
        key.extend(
            [
                round(float(row.get("boresight_roll_deg", 0.0)), 6),
                round(float(row.get("boresight_pitch_deg", 0.0)), 6),
                round(float(row.get("boresight_yaw_deg", 0.0)), 6),
            ]
        )
    return tuple(key)


def sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid = [row for row in rows if np.isfinite(float(row.get("vector_rmse_m", float("inf"))))]
    valid = sorted(valid, key=lambda row: (row["vector_rmse_m"], row["horizontal_rmse_m"], row["down_rmse_m"]))
    for idx, row in enumerate(valid, 1):
        row["rank"] = idx
    return valid


def candidate_fields() -> list[str]:
    return [
        "rank",
        "candidate_stage",
        "angle_direction",
        "angle_offset_deg",
        "mirror_tilt_deg",
        "frame_rotation_deg",
        "axis_mapping",
        "boresight_roll_deg",
        "boresight_pitch_deg",
        "boresight_yaw_deg",
        "boresight_abs_max_deg",
        "lever_x_m",
        "lever_y_m",
        "lever_z_m",
        "lever_norm_m",
        "sample_points_used",
        "mean_frd_down",
        "vector_rmse_m",
        "horizontal_rmse_m",
        "down_rmse_m",
        "north_rmse_m",
        "east_rmse_m",
        "north_median_m",
        "east_median_m",
        "down_median_m",
        "north_mad_m",
        "east_mad_m",
        "down_mad_m",
        "north_p90_abs_m",
        "east_p90_abs_m",
        "down_p90_abs_m",
        "horizontal_p90_m",
        "bias_removed_vector_rmse_m",
        "bias_removed_horizontal_rmse_m",
    ]


def base_candidate_rows(coarse_offset_step_deg: float) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offsets = np.arange(0.0, 360.0, coarse_offset_step_deg, dtype=np.float64)
    for direction, offset, frame_rotation, mapping in itertools.product(
        ANGLE_DIRECTIONS,
        offsets,
        COARSE_FRAME_ROTATION_DEG,
        AXIS_MAPPINGS,
    ):
        rows.append(
            {
                "angle_direction": direction,
                "angle_offset_deg": float(offset),
                "mirror_tilt_deg": 7.5,
                "frame_rotation_deg": float(frame_rotation),
                "axis_mapping": mapping["axis_mapping"],
                "axis_perm": mapping["axis_perm"],
                "axis_signs": mapping["axis_signs"],
                "boresight_roll_deg": 0.0,
                "boresight_pitch_deg": 0.0,
                "boresight_yaw_deg": 0.0,
            }
        )
    return rows


def evaluate_rows(
    geom: dict[str, np.ndarray],
    rotation_cols: np.ndarray,
    rows: list[dict[str, Any]],
    candidate_stage: str,
    lever_limit_m: float,
    progress: bool,
    progress_prefix: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    total = len(rows)
    for idx, row in enumerate(rows, 1):
        evaluated = evaluate_candidate(geom, rotation_cols, row, candidate_stage, lever_limit_m)
        out.append(evaluated)  # type: ignore[arg-type]
        if progress and (idx % 1000 == 0 or idx == total):
            print(f"{progress_prefix}: {idx}/{total}", flush=True)
    return sort_rows(out)


def local_geometry_rows(source_rows: list[dict[str, Any]], top_count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in source_rows[:top_count]:
        for offset_delta, tilt_delta, frame_delta in itertools.product(
            LOCAL_OFFSET_DELTA_DEG,
            LOCAL_TILT_DELTA_DEG,
            LOCAL_FRAME_DELTA_DEG,
        ):
            row = dict(source)
            row["angle_offset_deg"] = float((float(source["angle_offset_deg"]) + offset_delta) % 360.0)
            row["mirror_tilt_deg"] = float(np.clip(float(source["mirror_tilt_deg"]) + tilt_delta, 5.0, 10.0))
            row["frame_rotation_deg"] = float(float(source["frame_rotation_deg"]) + frame_delta)
            row["boresight_roll_deg"] = 0.0
            row["boresight_pitch_deg"] = 0.0
            row["boresight_yaw_deg"] = 0.0
            key = candidate_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def boresight_rows(source_rows: list[dict[str, Any]], top_count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in source_rows[:top_count]:
        for boresight in itertools.product(BORESIGHT_COARSE_DEG, repeat=3):
            row = dict(source)
            row["boresight_roll_deg"] = float(boresight[0])
            row["boresight_pitch_deg"] = float(boresight[1])
            row["boresight_yaw_deg"] = float(boresight[2])
            key = candidate_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def refine_rows(source_rows: list[dict[str, Any]], top_count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in source_rows[:top_count]:
        bore = np.array(
            [
                float(source["boresight_roll_deg"]),
                float(source["boresight_pitch_deg"]),
                float(source["boresight_yaw_deg"]),
            ],
            dtype=np.float64,
        )
        for offset_delta, bore_delta in itertools.product(
            BORESIGHT_OFFSET_REFINE_DELTA_DEG,
            itertools.product(BORESIGHT_REFINE_DELTA_DEG, repeat=3),
        ):
            row = dict(source)
            row["angle_offset_deg"] = float((float(source["angle_offset_deg"]) + offset_delta) % 360.0)
            refined = np.clip(bore + np.asarray(bore_delta, dtype=np.float64), -3.0, 3.0)
            row["boresight_roll_deg"] = float(refined[0])
            row["boresight_pitch_deg"] = float(refined[1])
            row["boresight_yaw_deg"] = float(refined[2])
            key = candidate_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def fine_rows(source_rows: list[dict[str, Any]], top_count: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for source in source_rows[:top_count]:
        bore = np.array(
            [
                float(source["boresight_roll_deg"]),
                float(source["boresight_pitch_deg"]),
                float(source["boresight_yaw_deg"]),
            ],
            dtype=np.float64,
        )
        for offset_delta, tilt_delta, bore_delta in itertools.product(
            FINE_OFFSET_DELTA_DEG,
            FINE_TILT_DELTA_DEG,
            itertools.product(FINE_BORESIGHT_DELTA_DEG, repeat=3),
        ):
            row = dict(source)
            row["angle_offset_deg"] = float((float(source["angle_offset_deg"]) + offset_delta) % 360.0)
            row["mirror_tilt_deg"] = float(np.clip(float(source["mirror_tilt_deg"]) + tilt_delta, 5.0, 10.0))
            refined = np.clip(bore + np.asarray(bore_delta, dtype=np.float64), -3.0, 3.0)
            row["boresight_roll_deg"] = float(refined[0])
            row["boresight_pitch_deg"] = float(refined[1])
            row["boresight_yaw_deg"] = float(refined[2])
            key = candidate_key(row)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def select_unique(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in rows:
        key = candidate_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= count:
            break
    return selected


def scan_bin_rows(angle_deg: np.ndarray, current_diff: np.ndarray, best_diff: np.ndarray) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bins = np.arange(0.0, 361.0, 30.0)
    for lo, hi in zip(bins[:-1], bins[1:]):
        if hi >= 360.0:
            mask = (angle_deg >= lo) & (angle_deg <= hi)
        else:
            mask = (angle_deg >= lo) & (angle_deg < hi)
        if not np.any(mask):
            continue
        current = stage6d.metrics(current_diff[mask])
        best = stage6d.metrics(best_diff[mask])
        rows.append(
            {
                "scan_bin_deg": f"{int(lo):03d}-{int(hi):03d}",
                "point_count": int(np.count_nonzero(mask)),
                "current6f_vector_rmse_m": current["vector_rmse_m"],
                "current6f_horizontal_rmse_m": current["horizontal_rmse_m"],
                "current6f_down_rmse_m": current["down_rmse_m"],
                "stage6i_vector_rmse_m": best["vector_rmse_m"],
                "stage6i_horizontal_rmse_m": best["horizontal_rmse_m"],
                "stage6i_down_rmse_m": best["down_rmse_m"],
                "stage6i_north_median_m": best["north_median_m"],
                "stage6i_east_median_m": best["east_median_m"],
                "stage6i_down_median_m": best["down_median_m"],
            }
        )
    return rows


def scan_bin_fields() -> list[str]:
    return [
        "scan_bin_deg",
        "point_count",
        "current6f_vector_rmse_m",
        "current6f_horizontal_rmse_m",
        "current6f_down_rmse_m",
        "stage6i_vector_rmse_m",
        "stage6i_horizontal_rmse_m",
        "stage6i_down_rmse_m",
        "stage6i_north_median_m",
        "stage6i_east_median_m",
        "stage6i_down_median_m",
    ]


def gate_conclusion(best: dict[str, Any], current6f: dict[str, Any]) -> tuple[str, str, bool, dict[str, float]]:
    current_vector = float(current6f["vector_rmse_m"])
    current_horizontal = float(current6f["horizontal_rmse_m"])
    best_vector = float(best["vector_rmse_m"])
    best_horizontal = float(best["horizontal_rmse_m"])
    vector_improvement = 100.0 * (current_vector - best_vector) / current_vector if current_vector > 0 else 0.0
    horizontal_improvement = (
        100.0 * (current_horizontal - best_horizontal) / current_horizontal if current_horizontal > 0 else 0.0
    )
    physically_bounded = (
        float(best["lever_norm_m"]) <= 3.0
        and float(best["boresight_abs_max_deg"]) <= 3.0
        and 5.0 <= float(best["mirror_tilt_deg"]) <= 10.0
        and min(abs(float(best["frame_rotation_deg"]) - 45.0), abs(float(best["frame_rotation_deg"]) + 45.0)) <= 5.0
    )
    stats = {
        "vector_improvement_vs_stage6f_pct": float(vector_improvement),
        "horizontal_improvement_vs_stage6f_pct": float(horizontal_improvement),
    }
    if vector_improvement >= 5.0 and horizontal_improvement >= 5.0 and physically_bounded:
        return (
            "合理",
            "LADM-II 物理扫描几何在 00111 exact-time 复核中优于当前经验 f_body_frame_xyz()+6F 候选，且参数幅度受限。",
            True,
            stats,
        )
    if best_vector <= current_vector * 1.05 and physically_bounded:
        return (
            "基本合理但不足以替换",
            "LADM-II 候选达到或接近当前 6F 精度，但未形成稳定显著优势；不能直接替换生产 f_body_frame_xyz()。",
            False,
            stats,
        )
    return (
        "不建议替换",
        "LADM-II 候选未达到当前 6F 经验模型精度，或需要过大的等效安装参数；应继续核对 PDF 坐标约定/码盘零位。",
        False,
        stats,
    )


def write_report(payload: dict[str, Any]) -> None:
    best = payload["best_candidate"]
    current = payload["current_stage6f_best_metrics"]
    gate = payload["gate"]
    method_rows = "\n".join(
        f"| {m['method_id']} | {m['method_name']} | {m['source_type']} | "
        f"{m['source_reference']} | {m['used_for_delete_or_transform']} |"
        for m in METHOD_REGISTRY
    )
    content = f"""# Stage 6I CH1 LADM-II Scan Geometry Diagnostic

## 结论

- Gate conclusion: {gate['conclusion']}
- Reason: {gate['reason']}
- Replace production `f_body_frame_xyz()`: {gate['replace_f_body_frame_xyz']}

## PDF 4.4.2 Implementation

- Mirror normal in X'Y'Z': formulas 4-7 to 4-9.
- X'Y'Z' to sensor sXYZ: formula 4-10, searched near ±45 deg because current data/axis convention is not documented.
- Reflected beam direction: implemented as physical mirror reflection, equivalent to deriving φx, φy, φ, γ from formulas 4-11 to 4-14.
- sXYZ to current FRD: searched as an axis/sign mapping because current Stage 6 uses FRD-to-NED diagnostic rotation.

## Current 6F Baseline

- vector_rmse_m: {current['vector_rmse_m']:.6f}
- horizontal_rmse_m: {current['horizontal_rmse_m']:.6f}
- down_rmse_m: {current['down_rmse_m']:.6f}

## Best Stage 6I Candidate

- angle_direction: `{best['angle_direction']}`
- angle_offset_deg: {best['angle_offset_deg']:.6f}
- mirror_tilt_deg: {best['mirror_tilt_deg']:.6f}
- frame_rotation_deg: {best['frame_rotation_deg']:.6f}
- axis_mapping: `{best['axis_mapping']}`
- boresight roll/pitch/yaw deg: {best['boresight_roll_deg']:.6f}, {best['boresight_pitch_deg']:.6f}, {best['boresight_yaw_deg']:.6f}
- lever x/y/z m: {best['lever_x_m']:.6f}, {best['lever_y_m']:.6f}, {best['lever_z_m']:.6f}
- lever_norm_m: {best['lever_norm_m']:.6f}
- vector_rmse_m: {best['vector_rmse_m']:.6f}
- horizontal_rmse_m: {best['horizontal_rmse_m']:.6f}
- down_rmse_m: {best['down_rmse_m']:.6f}
- improvement_vs_stage6f_vector_pct: {gate['vector_improvement_vs_stage6f_pct']:.3f}%
- improvement_vs_stage6f_horizontal_pct: {gate['horizontal_improvement_vs_stage6f_pct']:.3f}%

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Coarse candidates: `{payload['outputs']['coarse_candidates_csv']}`
- Local geometry candidates: `{payload['outputs']['local_geometry_candidates_csv']}`
- Boresight candidates: `{payload['outputs']['boresight_candidates_csv']}`
- Refined candidates: `{payload['outputs']['refined_candidates_csv']}`
- Fine candidates: `{payload['outputs']['fine_candidates_csv']}`
- Top full-eval candidates: `{payload['outputs']['top_candidates_csv']}`
- Best candidate JSON: `{payload['outputs']['best_candidate_json']}`
- Scan-bin residual CSV: `{payload['outputs']['scan_bins_csv']}`
- Report JSON: `{payload['outputs']['report_json']}`

## Stop Rule

- 本阶段只诊断 PDF 4.4.2 / LADM-II 扫描几何，不覆盖 H5/LAZ。
- 只有当本阶段明确优于当前 6F，且参数幅度可解释时，才建议在后续阶段切换生产 `f_body_frame_xyz()`。
"""
    path = REPORT_DIR / "stage6i_ch1_ladm2_scan_geometry_diagnostic_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.progress:
        print("Loading exact-time matched 00111 data and Stage 6F baseline...", flush=True)
    data = diag.load_matched_data(args.max_matched_points, "far_return_refnorm", 30.0)
    calibration = pipe.load_channel_calibration(stage5.CALIB_COEFFS, "ch1")
    stage6f_best = load_stage6f_best()

    search_idx = stage6f.stratified_indices(data["matched_time"].size, args.search_points)
    search_data = stage6f.sample_data(data, search_idx)
    search_geom = build_geom(search_data, calibration)
    search_rotation_cols = rotation_columns(search_geom)

    if args.progress:
        print(f"Coarse LADM-II search on {search_geom['range_m'].size} points...", flush=True)
    coarse_rows = evaluate_rows(
        search_geom,
        search_rotation_cols,
        base_candidate_rows(args.coarse_offset_step_deg),
        "coarse_ladm2_lever_ls",
        args.lever_limit_m,
        args.progress,
        "Coarse LADM-II search",
    )

    local_source = select_unique(coarse_rows, args.local_geometry_top_candidates)
    local_rows_in = local_geometry_rows(local_source, args.local_geometry_top_candidates)
    if args.progress:
        print(f"Local geometry refinement: {len(local_rows_in)} candidates...", flush=True)
    local_rows = evaluate_rows(
        search_geom,
        search_rotation_cols,
        local_rows_in,
        "local_ladm2_geometry_lever_ls",
        args.lever_limit_m,
        args.progress,
        "Local geometry refinement",
    )

    geom_combined = sort_rows(coarse_rows + local_rows)
    boresight_rows_in = boresight_rows(geom_combined, args.boresight_top_candidates)
    if args.progress:
        print(f"Coarse boresight search: {len(boresight_rows_in)} candidates...", flush=True)
    boresight_eval_rows = evaluate_rows(
        search_geom,
        search_rotation_cols,
        boresight_rows_in,
        "coarse_ladm2_boresight_lever_ls",
        args.lever_limit_m,
        args.progress,
        "Coarse boresight search",
    )

    refine_rows_in = refine_rows(boresight_eval_rows, args.refine_top_candidates)
    if args.progress:
        print(f"Refined boresight/offset search: {len(refine_rows_in)} candidates...", flush=True)
    refined_rows = evaluate_rows(
        search_geom,
        search_rotation_cols,
        refine_rows_in,
        "refined_ladm2_boresight_lever_ls",
        args.lever_limit_m,
        args.progress,
        "Refined boresight/offset search",
    )

    fine_rows_in = fine_rows(refined_rows, args.fine_top_candidates)
    if args.progress:
        print(f"Fine LADM-II local search: {len(fine_rows_in)} candidates...", flush=True)
    fine_eval_rows = evaluate_rows(
        search_geom,
        search_rotation_cols,
        fine_rows_in,
        "fine_ladm2_geometry_boresight_lever_ls",
        args.lever_limit_m,
        args.progress,
        "Fine LADM-II local search",
    )

    full_geom = build_geom(data, calibration)
    full_rotation_cols = rotation_columns(full_geom)
    search_all = sort_rows(coarse_rows + local_rows + boresight_eval_rows + refined_rows + fine_eval_rows)
    full_rows_in = select_unique(search_all, args.top_final_eval_count)
    if args.progress:
        print(f"Full-sample re-evaluation: {len(full_rows_in)} candidates on {full_geom['range_m'].size} points...", flush=True)
    full_rows = evaluate_rows(
        full_geom,
        full_rotation_cols,
        full_rows_in,
        "full_eval_ladm2_lever_resolved",
        args.lever_limit_m,
        args.progress,
        "Full-sample re-evaluation",
    )
    best = full_rows[0]
    best_eval, best_diff, best_angle = evaluate_candidate(
        full_geom,
        full_rotation_cols,
        best,
        "best_ladm2_full_eval",
        args.lever_limit_m,
        resolve_lever=False,
        return_diff=True,
    )
    best = best_eval

    current_geom = stage6f.build_base_geometry(data, calibration)
    current_rotation_cols = stage6f.rotation_columns(current_geom)
    current_diff = stage6f.diff_for_candidate(current_geom, current_rotation_cols, stage6f_best)
    current_metrics = stage6d.metrics(current_diff)
    scan_rows = scan_bin_rows(best_angle, current_diff, best_diff)
    conclusion, reason, replace_fbody, improvement_stats = gate_conclusion(best, current_metrics)

    coarse_csv = OUT_DIR / "coarse_candidates.csv"
    local_csv = OUT_DIR / "local_geometry_candidates.csv"
    boresight_csv = OUT_DIR / "boresight_candidates.csv"
    refined_csv = OUT_DIR / "refined_candidates.csv"
    fine_csv = OUT_DIR / "fine_candidates.csv"
    top_csv = OUT_DIR / "top_candidates_full_eval.csv"
    best_json = OUT_DIR / "best_candidate.json"
    scan_csv = OUT_DIR / "scan_angle_bin_residuals.csv"
    report_json = REPORT_DIR / "stage6i_ch1_ladm2_scan_geometry_diagnostic_report.json"

    fields = candidate_fields()
    write_csv(coarse_csv, coarse_rows, fields)
    write_csv(local_csv, local_rows, fields)
    write_csv(boresight_csv, boresight_eval_rows, fields)
    write_csv(refined_csv, refined_rows, fields)
    write_csv(fine_csv, fine_eval_rows, fields)
    write_csv(top_csv, full_rows, fields)
    write_json(best_json, best)
    write_csv(scan_csv, scan_rows, scan_bin_fields())

    payload = {
        "stage_name": "stage6i_ch1_ladm2_scan_geometry_diagnostic",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "reference_l3": str(diag.REFERENCE_L3),
            "l1_sample": str(diag.L1_SAMPLE),
            "pos_source": str(stage5.POS_SOURCE),
            "calib_coeffs": str(stage5.CALIB_COEFFS),
            "stage6f_best_candidate": str(STAGE6F_BEST),
            "pdf_source": str(PDF_SOURCE),
        },
        "fixed_parameters": {
            "zero_offset_m": ZERO_OFFSET_M,
            "roll_sign": stage6e.ROLL_SIGN,
            "pitch_sign": stage6e.PITCH_SIGN,
            "heading_sign": stage6e.HEADING_SIGN,
            "heading_convention": stage6e.HEADING_CONVENTION,
            "rotation_order": ROTATION_ORDER,
            "rotation_transpose": ROTATION_TRANSPOSE,
        },
        "search": {
            "max_matched_points": args.max_matched_points,
            "search_points": int(search_geom["range_m"].size),
            "coarse_offset_step_deg": args.coarse_offset_step_deg,
            "axis_mapping_count": len(AXIS_MAPPINGS),
            "coarse_candidate_count": len(coarse_rows),
            "local_candidate_count": len(local_rows),
            "boresight_candidate_count": len(boresight_eval_rows),
            "refined_candidate_count": len(refined_rows),
            "fine_candidate_count": len(fine_eval_rows),
            "top_final_eval_count": len(full_rows),
            "lever_limit_m": args.lever_limit_m,
        },
        "current_stage6f_best_candidate": stage6f_best,
        "current_stage6f_best_metrics": current_metrics,
        "best_candidate": best,
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "replace_f_body_frame_xyz": replace_fbody,
            **improvement_stats,
            "criteria": {
                "replace_min_vector_improvement_pct": 5.0,
                "replace_min_horizontal_improvement_pct": 5.0,
                "max_lever_norm_m": 3.0,
                "max_boresight_abs_deg": 3.0,
                "mirror_tilt_range_deg": [5.0, 10.0],
                "frame_rotation_near_abs_45_deg_tolerance": 5.0,
            },
        },
        "outputs": {
            "coarse_candidates_csv": str(coarse_csv),
            "local_geometry_candidates_csv": str(local_csv),
            "boresight_candidates_csv": str(boresight_csv),
            "refined_candidates_csv": str(refined_csv),
            "fine_candidates_csv": str(fine_csv),
            "top_candidates_csv": str(top_csv),
            "best_candidate_json": str(best_json),
            "scan_bins_csv": str(scan_csv),
            "report_json": str(report_json),
            "report_md": str(REPORT_DIR / "stage6i_ch1_ladm2_scan_geometry_diagnostic_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "current_stage6f_best_metrics": current_metrics,
                    "best_candidate": best,
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6I CH1 LADM-II scan-geometry diagnostic.")
    parser.add_argument("--max-matched-points", type=int, default=100_000)
    parser.add_argument("--search-points", type=int, default=5_000)
    parser.add_argument("--top-final-eval-count", type=int, default=100)
    parser.add_argument("--coarse-offset-step-deg", type=float, default=5.0)
    parser.add_argument("--local-geometry-top-candidates", type=int, default=30)
    parser.add_argument("--boresight-top-candidates", type=int, default=20)
    parser.add_argument("--refine-top-candidates", type=int, default=20)
    parser.add_argument("--fine-top-candidates", type=int, default=10)
    parser.add_argument("--lever-limit-m", type=float, default=3.0)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
