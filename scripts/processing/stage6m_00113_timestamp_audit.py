from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

import h5py
import numpy as np

import ch1_pipeline as pipe
import stage5_full_ch1 as stage5


ROOT = Path(__file__).resolve().parents[2]
L1_DIR = ROOT / "0510_f3" / "L1-TIME_ANGE_DIST_DATA"
OUT_DIR = ROOT / "outputs" / "qc" / "stage6m_00113_timestamp_audit"
REPORT_DIR = ROOT / "metadata" / "stage_reports"

METHOD_REGISTRY = [
    {
        "method_id": "TIMESTAMP_FIELD_AUDIT",
        "method_name": "Raw L1 GNSS timestamp anomaly audit",
        "source_type": "project_qc_rule",
        "source_reference": "Compare 00113 raw GNSS_SEC_CH* against neighbor time windows, pulse indices, and POS time coverage",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "NEIGHBOR_TIME_WINDOW",
        "method_name": "Neighbor-bounded expected raw GNSS time window",
        "source_type": "project_qc_rule",
        "source_reference": "Use previous normal file maximum GNSS time and next normal file minimum GNSS time as the expected gap for 00113",
        "used_for_delete_or_transform": "no, QC only",
    },
    {
        "method_id": "NO_GEOMETRY_MODEL_USE",
        "method_name": "Isolation from geometry diagnostics",
        "source_type": "project_gate_rule",
        "source_reference": "Do not feed 00113 raw timestamps into Stage 6I/6K/6L LADM-II geometry model decisions",
        "used_for_delete_or_transform": "no, gate only",
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
        field_set: list[str] = []
        for row in rows:
            for key in row:
                if key not in field_set:
                    field_set.append(key)
        fields = field_set
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def l1_sequence(path: Path) -> int:
    match = re.search(r"L1_cap_(\d{5})_", path.name)
    if not match:
        raise ValueError(f"Cannot parse L1 sequence from {path}")
    return int(match.group(1))


def find_l1(seq: int) -> Path:
    matches = sorted(L1_DIR.glob(f"L1_cap_{seq:05d}_*.h5"))
    if not matches:
        raise FileNotFoundError(f"Missing L1 file for sequence {seq:05d} in {L1_DIR}")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple L1 files for sequence {seq:05d}: {matches}")
    return matches[0]


def read_dataset(path: Path, name: str, dtype: Any = np.float64) -> np.ndarray:
    with h5py.File(path, "r") as h5:
        if name not in h5:
            return np.asarray([], dtype=dtype)
        return h5[name][:].astype(dtype)


def finite_percentile(values: np.ndarray, pct: float) -> float:
    finite = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return float("nan")
    return float(np.percentile(finite, pct))


def stats(values: np.ndarray) -> dict[str, float | int]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    finite = flat[np.isfinite(flat)]
    out: dict[str, float | int] = {
        "count": int(flat.size),
        "finite_count": int(finite.size),
        "nonfinite_count": int(flat.size - finite.size),
        "finite_rate": float(finite.size / max(flat.size, 1)),
        "min": float("nan"),
        "max": float("nan"),
        "mean": float("nan"),
        "median": float("nan"),
        "p01": float("nan"),
        "p05": float("nan"),
        "p95": float("nan"),
        "p99": float("nan"),
    }
    if finite.size:
        out.update(
            {
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "median": float(np.median(finite)),
                "p01": float(np.percentile(finite, 1)),
                "p05": float(np.percentile(finite, 5)),
                "p95": float(np.percentile(finite, 95)),
                "p99": float(np.percentile(finite, 99)),
            }
        )
    return out


def add_prefixed(row: dict[str, Any], prefix: str, values: dict[str, Any]) -> None:
    for key, value in values.items():
        row[f"{prefix}_{key}"] = value


def consecutive_diffs(values: np.ndarray) -> np.ndarray:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    if flat.size < 2:
        return np.asarray([], dtype=np.float64)
    valid = np.isfinite(flat[:-1]) & np.isfinite(flat[1:])
    return (flat[1:] - flat[:-1])[valid]


def fit_time_vs_pulse(gnss: np.ndarray, pulse: np.ndarray, max_samples: int) -> dict[str, float | int]:
    n = min(gnss.size, pulse.size)
    if n == 0:
        return {
            "fit_sample_count": 0,
            "gnss_per_pulse_slope": float("nan"),
            "fit_intercept": float("nan"),
            "fit_r2": float("nan"),
            "gnss_equals_pulse_index_rate": float("nan"),
            "integer_gnss_rate": float("nan"),
        }
    g = gnss[:n].astype(np.float64)
    p = pulse[:n].astype(np.float64)
    valid = np.isfinite(g) & np.isfinite(p)
    if not np.any(valid):
        return {
            "fit_sample_count": 0,
            "gnss_per_pulse_slope": float("nan"),
            "fit_intercept": float("nan"),
            "fit_r2": float("nan"),
            "gnss_equals_pulse_index_rate": float("nan"),
            "integer_gnss_rate": float("nan"),
        }

    exact = np.isclose(g[valid], p[valid], rtol=0.0, atol=1e-9)
    integer_like = np.isclose(g[valid], np.round(g[valid]), rtol=0.0, atol=1e-9)

    valid_idx = np.flatnonzero(valid)
    if valid_idx.size > max_samples > 0:
        sample_idx = valid_idx[np.linspace(0, valid_idx.size - 1, max_samples, dtype=np.int64)]
    else:
        sample_idx = valid_idx
    x = p[sample_idx]
    y = g[sample_idx]
    if x.size < 2 or np.nanstd(x) == 0:
        slope = float("nan")
        intercept = float("nan")
        r2 = float("nan")
    else:
        design = np.column_stack([np.ones(x.size), x])
        intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
        pred = intercept + slope * x
        ss_res = float(np.sum((y - pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    return {
        "fit_sample_count": int(sample_idx.size),
        "gnss_per_pulse_slope": float(slope),
        "fit_intercept": float(intercept),
        "fit_r2": float(r2),
        "gnss_equals_pulse_index_rate": float(np.count_nonzero(exact) / max(exact.size, 1)),
        "integer_gnss_rate": float(np.count_nonzero(integer_like) / max(integer_like.size, 1)),
    }


def expected_window(prev_gnss: np.ndarray, next_gnss: np.ndarray) -> dict[str, float]:
    prev_finite = prev_gnss[np.isfinite(prev_gnss)]
    next_finite = next_gnss[np.isfinite(next_gnss)]
    if prev_finite.size == 0 or next_finite.size == 0:
        return {
            "raw_start_sec": float("nan"),
            "raw_end_sec": float("nan"),
            "duration_sec": float("nan"),
        }
    start = float(np.max(prev_finite))
    end = float(np.min(next_finite))
    return {
        "raw_start_sec": start,
        "raw_end_sec": end,
        "duration_sec": float(end - start),
    }


def pos_time_arrays() -> tuple[np.ndarray, int]:
    pos = pipe.load_pos_mat(stage5.POS_SOURCE)
    missing = [field for field in pipe.POS_REQUIRED_FIELDS if field not in pos]
    if missing:
        raise ValueError(f"POS source missing fields: {', '.join(missing)}")
    pos_time, corrections = pipe.process_pos_time_seconds(pos["TIME"])
    pos_time = np.sort(pos_time)
    return pos_time, corrections


def pos_coverage(lidar_time: np.ndarray, pos_time: np.ndarray, low_confidence_sec: float) -> dict[str, Any]:
    finite = np.isfinite(lidar_time)
    in_range = finite & (lidar_time >= pos_time[0]) & (lidar_time <= pos_time[-1])
    nearest = np.full(lidar_time.shape, np.nan, dtype=np.float64)
    if np.any(in_range):
        nearest[in_range] = pipe.nearest_time_delta_abs(pos_time, lidar_time[in_range])
    confident = in_range & (nearest <= low_confidence_sec)
    return {
        "pos_time_min_sec": float(pos_time[0]),
        "pos_time_max_sec": float(pos_time[-1]),
        "pos_in_range_count": int(np.count_nonzero(in_range)),
        "pos_in_range_rate": float(np.count_nonzero(in_range) / max(lidar_time.size, 1)),
        "pos_confident_count": int(np.count_nonzero(confident)),
        "pos_confident_rate": float(np.count_nonzero(confident) / max(lidar_time.size, 1)),
        "nearest_pos_dt_in_range_abs_sec": stats(nearest[in_range]) if np.any(in_range) else stats(np.asarray([], dtype=np.float64)),
    }


def margin_rows(
    seq: int,
    channel: int,
    gnss: np.ndarray,
    window: dict[str, float],
    margins: list[float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    finite = np.isfinite(gnss)
    for margin in margins:
        start = window["raw_start_sec"] - margin
        end = window["raw_end_sec"] + margin
        mask = finite & (gnss >= start) & (gnss <= end)
        rows.append(
            {
                "seq": seq,
                "channel": channel,
                "margin_sec": margin,
                "window_start_sec": start,
                "window_end_sec": end,
                "matching_count": int(np.count_nonzero(mask)),
                "matching_rate": float(np.count_nonzero(mask) / max(gnss.size, 1)),
            }
        )
    return rows


def audit_channel(
    seq: int,
    channel: int,
    bad_path: Path,
    prev_path: Path,
    next_path: Path,
    pos_time: np.ndarray,
    low_confidence_sec: float,
    fit_samples: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    suffix = f"CH{channel}"
    gnss = read_dataset(bad_path, f"GNSS_SEC_{suffix}")
    pulse = read_dataset(bad_path, f"PULSE_INDEX_{suffix}", np.float64)
    prev_gnss = read_dataset(prev_path, f"GNSS_SEC_{suffix}")
    next_gnss = read_dataset(next_path, f"GNSS_SEC_{suffix}")
    diffs = consecutive_diffs(gnss)
    window = expected_window(prev_gnss, next_gnss)
    finite = np.isfinite(gnss)
    in_expected = finite & (gnss >= window["raw_start_sec"]) & (gnss <= window["raw_end_sec"])
    lidar_time = gnss + pipe.DEFAULT_TIME_OFFSET_SEC
    pos = pos_coverage(lidar_time, pos_time, low_confidence_sec)
    fit = fit_time_vs_pulse(gnss, pulse, fit_samples)

    expected_rate = float(np.count_nonzero(in_expected) / max(gnss.size, 1))
    slope = float(fit["gnss_per_pulse_slope"])
    equals_pulse_rate = float(fit["gnss_equals_pulse_index_rate"])
    integer_rate = float(fit["integer_gnss_rate"])
    if gnss.size == 0:
        verdict = "MISSING_CHANNEL_DATASET"
    elif equals_pulse_rate >= 0.99 and integer_rate >= 0.99:
        verdict = "CORRUPTED_TIMESTAMP_FIELD_PULSE_INDEX_COPIED"
    elif expected_rate < 0.001 and pos["pos_confident_rate"] < 0.05:
        verdict = "CORRUPTED_TIMESTAMP_FIELD_OUTSIDE_EXPECTED_TIME"
    elif np.isfinite(slope) and not (1.5e-6 <= abs(slope) <= 3.0e-6):
        verdict = "SUSPICIOUS_GNSS_PER_PULSE_SLOPE"
    else:
        verdict = "PLAUSIBLE_TIMESTAMP"

    row: dict[str, Any] = {
        "seq": seq,
        "channel": channel,
        "source_file": rel(bad_path),
        "previous_file": rel(prev_path),
        "next_file": rel(next_path),
        "verdict": verdict,
        "expected_raw_start_sec": window["raw_start_sec"],
        "expected_raw_end_sec": window["raw_end_sec"],
        "expected_duration_sec": window["duration_sec"],
        "expected_window_count": int(np.count_nonzero(in_expected)),
        "expected_window_rate": expected_rate,
        "lidar_time_offset_sec": pipe.DEFAULT_TIME_OFFSET_SEC,
        "pos_in_range_count": pos["pos_in_range_count"],
        "pos_in_range_rate": pos["pos_in_range_rate"],
        "pos_confident_count": pos["pos_confident_count"],
        "pos_confident_rate": pos["pos_confident_rate"],
        "diff_nonpositive_count": int(np.count_nonzero(diffs <= 0)) if diffs.size else 0,
        "diff_nonpositive_rate": float(np.count_nonzero(diffs <= 0) / max(diffs.size, 1)) if diffs.size else 0.0,
    }
    add_prefixed(row, "gnss", stats(gnss))
    add_prefixed(row, "gnss_diff", stats(diffs))
    add_prefixed(row, "pulse", stats(pulse))
    add_prefixed(row, "fit", fit)
    add_prefixed(row, "nearest_pos_dt_in_range_abs_sec", pos["nearest_pos_dt_in_range_abs_sec"])
    margins = margin_rows(seq, channel, gnss, window, [0.0, 0.001, 0.01, 0.1, 1.0, 3.1])
    return row, margins


def summarize_seq_channel(path: Path, channel: int, fit_samples: int) -> dict[str, Any]:
    seq = l1_sequence(path)
    suffix = f"CH{channel}"
    gnss = read_dataset(path, f"GNSS_SEC_{suffix}")
    pulse = read_dataset(path, f"PULSE_INDEX_{suffix}", np.float64)
    diffs = consecutive_diffs(gnss)
    fit = fit_time_vs_pulse(gnss, pulse, fit_samples)
    row: dict[str, Any] = {
        "seq": seq,
        "channel": channel,
        "source_file": rel(path),
        "point_count": int(gnss.size),
        "duration_by_minmax_sec": float(np.nanmax(gnss) - np.nanmin(gnss)) if gnss.size else float("nan"),
        "diff_nonpositive_count": int(np.count_nonzero(diffs <= 0)) if diffs.size else 0,
    }
    add_prefixed(row, "gnss", stats(gnss))
    add_prefixed(row, "gnss_diff", stats(diffs))
    add_prefixed(row, "fit", fit)
    return row


def write_ch1_samples(
    path: Path,
    bad_path: Path,
    prev_path: Path,
    next_path: Path,
    pos_time: np.ndarray,
    max_rows: int,
) -> dict[str, Any]:
    gnss = read_dataset(bad_path, "GNSS_SEC_CH1")
    pulse = read_dataset(bad_path, "PULSE_INDEX_CH1", np.float64)
    pulse_circle = read_dataset(bad_path, "PULSE_CIRCLE_CH1", np.float64)
    photon_start = read_dataset(bad_path, "Photon_Start_Count_CH1", np.float64)
    prev_gnss = read_dataset(prev_path, "GNSS_SEC_CH1")
    next_gnss = read_dataset(next_path, "GNSS_SEC_CH1")
    window = expected_window(prev_gnss, next_gnss)
    finite = np.isfinite(gnss)
    expected_hit_idx = np.flatnonzero(finite & (gnss >= window["raw_start_sec"]) & (gnss <= window["raw_end_sec"]))

    n = gnss.size
    idx_parts = [
        np.arange(min(12, n), dtype=np.int64),
        np.linspace(0, n - 1, min(max_rows, n), dtype=np.int64) if n else np.asarray([], dtype=np.int64),
        np.arange(max(0, n - 12), n, dtype=np.int64),
        expected_hit_idx[: min(expected_hit_idx.size, 200)],
    ]
    idx = np.unique(np.concatenate(idx_parts)) if idx_parts else np.asarray([], dtype=np.int64)
    rows: list[dict[str, Any]] = []
    for i in idx:
        lidar_time = float(gnss[i] + pipe.DEFAULT_TIME_OFFSET_SEC)
        in_pos = bool(pos_time[0] <= lidar_time <= pos_time[-1])
        rows.append(
            {
                "point_index": int(i),
                "gnss_sec_ch1": float(gnss[i]),
                "lidar_time_sec": lidar_time,
                "pulse_index_ch1": float(pulse[i]) if i < pulse.size else float("nan"),
                "pulse_circle_ch1": float(pulse_circle[i]) if i < pulse_circle.size else float("nan"),
                "photon_start_count_ch1": float(photon_start[i]) if i < photon_start.size else float("nan"),
                "in_neighbor_expected_raw_window": bool(window["raw_start_sec"] <= gnss[i] <= window["raw_end_sec"]),
                "in_pos_time_range_after_plus18": in_pos,
            }
        )
    write_csv(path, rows)

    hits_path = path.with_name("00113_ch1_expected_window_hits.csv")
    hit_rows: list[dict[str, Any]] = []
    for i in expected_hit_idx:
        hit_rows.append(
            {
                "point_index": int(i),
                "gnss_sec_ch1": float(gnss[i]),
                "lidar_time_sec": float(gnss[i] + pipe.DEFAULT_TIME_OFFSET_SEC),
                "pulse_index_ch1": float(pulse[i]) if i < pulse.size else float("nan"),
                "pulse_circle_ch1": float(pulse_circle[i]) if i < pulse_circle.size else float("nan"),
                "photon_start_count_ch1": float(photon_start[i]) if i < photon_start.size else float("nan"),
            }
        )
    write_csv(hits_path, hit_rows)
    return {
        "sample_csv": rel(path),
        "expected_window_hits_csv": rel(hits_path),
        "sample_row_count": int(len(rows)),
        "expected_window_hit_count": int(expected_hit_idx.size),
    }


def channel_audit_fields(rows: list[dict[str, Any]]) -> list[str]:
    preferred = [
        "seq",
        "channel",
        "verdict",
        "source_file",
        "expected_raw_start_sec",
        "expected_raw_end_sec",
        "expected_duration_sec",
        "expected_window_count",
        "expected_window_rate",
        "gnss_count",
        "gnss_min",
        "gnss_max",
        "gnss_median",
        "gnss_p01",
        "gnss_p99",
        "gnss_diff_median",
        "gnss_diff_p01",
        "gnss_diff_p99",
        "diff_nonpositive_count",
        "fit_gnss_per_pulse_slope",
        "fit_fit_intercept",
        "fit_fit_r2",
        "fit_gnss_equals_pulse_index_rate",
        "fit_integer_gnss_rate",
        "pos_in_range_count",
        "pos_in_range_rate",
        "pos_confident_count",
        "pos_confident_rate",
        "nearest_pos_dt_in_range_abs_sec_median",
        "previous_file",
        "next_file",
    ]
    seen = set(preferred)
    extra = [key for row in rows for key in row if key not in seen]
    return preferred + list(dict.fromkeys(extra))


def gate_from_ch1(ch1: dict[str, Any]) -> tuple[str, str, bool]:
    verdict = str(ch1.get("verdict", ""))
    expected_rate = float(ch1.get("expected_window_rate", float("nan")))
    equals_pulse = float(ch1.get("fit_gnss_equals_pulse_index_rate", float("nan")))
    pos_rate = float(ch1.get("pos_confident_rate", float("nan")))
    if "CORRUPTED" in verdict:
        return (
            "隔离 00113 原始时间戳",
            (
                "00113 CH1 raw GNSS_SEC is not a plausible GPS-second timestamp: "
                f"expected-window rate={expected_rate:.9%}, "
                f"GNSS equals pulse-index rate={equals_pulse:.6%}, "
                f"POS confident coverage={pos_rate:.6%}."
            ),
            False,
        )
    return (
        "00113 时间戳仍需人工复核",
        (
            "The automatic checks did not prove a copied pulse-index timestamp, "
            "but the file should still remain isolated until manually reviewed."
        ),
        False,
    )


def write_report(payload: dict[str, Any]) -> None:
    ch1 = payload["key_findings"]["ch1"]
    gate = payload["gate"]
    channel_lines = "\n".join(
        "| {channel} | {verdict} | {expected_window_count:,} | {expected_window_rate:.9%} | "
        "{fit_gnss_equals_pulse_index_rate:.6%} | {pos_confident_rate:.6%} | "
        "{fit_gnss_per_pulse_slope:.9f} |".format(**row)
        for row in payload["channel_audit"]
    )
    method_rows = "\n".join(
        f"| {item['method_id']} | {item['method_name']} | {item['source_type']} | {item['source_reference']} | {item['used_for_delete_or_transform']} |"
        for item in METHOD_REGISTRY
    )
    outputs = payload["outputs"]
    content = f"""# Stage 6M 00113 Timestamp Anomaly Audit

## Gate Conclusion

- Conclusion: {gate['conclusion']}
- Geometry-use allowed: {gate['allow_geometry_model_use']}
- Reason: {gate['reason']}

## Key CH1 Evidence

- Neighbor-bounded expected raw time: {ch1['expected_raw_start_sec']:.9f} ~ {ch1['expected_raw_end_sec']:.9f} s
- 00113 CH1 raw GNSS_SEC range: {ch1['gnss_min']:.9f} ~ {ch1['gnss_max']:.9f}
- CH1 points inside expected raw window: {ch1['expected_window_count']:,} / {ch1['gnss_count']:,} ({ch1['expected_window_rate']:.9%})
- CH1 GNSS_SEC equals PULSE_INDEX rate: {ch1['fit_gnss_equals_pulse_index_rate']:.6%}
- CH1 fitted GNSS-per-pulse slope: {ch1['fit_gnss_per_pulse_slope']:.9f} s/pulse
- CH1 POS confident coverage after +18 s: {ch1['pos_confident_count']:,} / {ch1['gnss_count']:,} ({ch1['pos_confident_rate']:.6%})

## Channel Summary

| CH | verdict | expected-window count | expected-window rate | GNSS==pulse rate | POS confident rate | fitted s/pulse |
|---:|---|---:|---:|---:|---:|---:|
{channel_lines}

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
{method_rows}

## Outputs

- Channel audit CSV: `{outputs['channel_audit_csv']}`
- Neighbor summary CSV: `{outputs['neighbor_summary_csv']}`
- Expected-window margins CSV: `{outputs['expected_window_margin_csv']}`
- CH1 sample CSV: `{outputs['ch1_sample_csv']}`
- CH1 expected-window hits CSV: `{outputs['ch1_expected_window_hits_csv']}`
- Report JSON: `{outputs['report_json']}`

## Stop Rule

00113 remains excluded from Stage 6I/6K/6L geometry model decisions. Any future use must be explicitly marked as a time-repair experiment, not as original raw timing.
"""
    path = REPORT_DIR / "stage6m_00113_timestamp_audit_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    bad_path = find_l1(args.seq)
    prev_path = find_l1(args.prev_seq)
    next_path = find_l1(args.next_seq)
    pos_time, pos_corrections = pos_time_arrays()

    if args.progress:
        print(f"Auditing raw timestamps for {bad_path.name}", flush=True)
        print(f"Neighbor files: {prev_path.name}, {next_path.name}", flush=True)

    channel_rows: list[dict[str, Any]] = []
    margin_rows_all: list[dict[str, Any]] = []
    for channel in args.channels:
        row, margins = audit_channel(
            args.seq,
            channel,
            bad_path,
            prev_path,
            next_path,
            pos_time,
            args.low_confidence_sec,
            args.fit_samples,
        )
        channel_rows.append(row)
        margin_rows_all.extend(margins)

    neighbor_rows: list[dict[str, Any]] = []
    for path in [prev_path, bad_path, next_path]:
        for channel in args.channels:
            neighbor_rows.append(summarize_seq_channel(path, channel, args.fit_samples))

    sample_info = write_ch1_samples(
        OUT_DIR / "00113_ch1_anomaly_samples.csv",
        bad_path,
        prev_path,
        next_path,
        pos_time,
        args.sample_rows,
    )

    channel_csv = OUT_DIR / "00113_channel_timestamp_audit.csv"
    neighbor_csv = OUT_DIR / "neighbor_channel_time_summary.csv"
    margin_csv = OUT_DIR / "00113_expected_window_margin_counts.csv"
    write_csv(channel_csv, channel_rows, channel_audit_fields(channel_rows))
    write_csv(neighbor_csv, neighbor_rows)
    write_csv(margin_csv, margin_rows_all)

    ch1 = next(row for row in channel_rows if int(row["channel"]) == 1)
    conclusion, reason, allow_geometry = gate_from_ch1(ch1)
    report_json = REPORT_DIR / "stage6m_00113_timestamp_audit_report.json"
    payload = {
        "stage_name": "stage6m_00113_timestamp_audit",
        "method_registry": METHOD_REGISTRY,
        "inputs": {
            "bad_l1": rel(bad_path),
            "previous_l1": rel(prev_path),
            "next_l1": rel(next_path),
            "pos_source": rel(stage5.POS_SOURCE),
        },
        "settings": {
            "seq": args.seq,
            "prev_seq": args.prev_seq,
            "next_seq": args.next_seq,
            "channels": args.channels,
            "low_confidence_sec": args.low_confidence_sec,
            "fit_samples": args.fit_samples,
            "sample_rows": args.sample_rows,
        },
        "pos_time": {
            "min_sec": float(pos_time[0]),
            "max_sec": float(pos_time[-1]),
            "count": int(pos_time.size),
            "non_monotonic_corrections": int(pos_corrections),
        },
        "channel_audit": channel_rows,
        "neighbor_summary": neighbor_rows,
        "expected_window_margin_counts": margin_rows_all,
        "key_findings": {
            "ch1": ch1,
            "interpretation": [
                "00113 is audited only as a timestamp-quality problem.",
                "The original 00113 raw timestamp field is not used to judge the LADM-II geometry model.",
                "Neighbor-bounded time repair may be tested separately, but it must remain marked as repaired/experimental.",
            ],
        },
        "gate": {
            "conclusion": conclusion,
            "reason": reason,
            "allow_geometry_model_use": allow_geometry,
            "rule": "Do not include original 00113 timestamps in Stage 6I/6K/6L geometry-model acceptance decisions.",
        },
        "outputs": {
            "channel_audit_csv": rel(channel_csv),
            "neighbor_summary_csv": rel(neighbor_csv),
            "expected_window_margin_csv": rel(margin_csv),
            "ch1_sample_csv": sample_info["sample_csv"],
            "ch1_expected_window_hits_csv": sample_info["expected_window_hits_csv"],
            "report_json": rel(report_json),
            "report_md": rel(REPORT_DIR / "stage6m_00113_timestamp_audit_report.md"),
        },
    }
    write_json(report_json, payload)
    write_report(payload)
    print(
        json.dumps(
            jsonable(
                {
                    "gate": payload["gate"],
                    "ch1_key_evidence": {
                        "expected_raw_start_sec": ch1["expected_raw_start_sec"],
                        "expected_raw_end_sec": ch1["expected_raw_end_sec"],
                        "gnss_min": ch1["gnss_min"],
                        "gnss_max": ch1["gnss_max"],
                        "expected_window_count": ch1["expected_window_count"],
                        "expected_window_rate": ch1["expected_window_rate"],
                        "gnss_equals_pulse_index_rate": ch1["fit_gnss_equals_pulse_index_rate"],
                        "gnss_per_pulse_slope": ch1["fit_gnss_per_pulse_slope"],
                        "pos_confident_rate": ch1["pos_confident_rate"],
                    },
                    "outputs": payload["outputs"],
                }
            ),
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stage 6M: isolated 00113 raw timestamp anomaly audit.")
    parser.add_argument("--seq", type=int, default=113)
    parser.add_argument("--prev-seq", type=int, default=112)
    parser.add_argument("--next-seq", type=int, default=114)
    parser.add_argument("--channels", type=int, nargs="+", default=[1, 2, 3, 4])
    parser.add_argument("--low-confidence-sec", type=float, default=0.2)
    parser.add_argument("--fit-samples", type=int, default=200_000)
    parser.add_argument("--sample-rows", type=int, default=120)
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
