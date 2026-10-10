from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from project_paths import STAGE_ROOT


DEFAULT_OUTPUT_ROOT = STAGE_ROOT

DEFAULT_ORIGIN_EASTING = 394000.0
DEFAULT_ORIGIN_NORTHING = 3417000.0
DEFAULT_CHUNK_SIZE = 500_000


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def stage8a_rows(output_root: Path) -> list[dict[str, str]]:
    manifest = (
        output_root
        / "stage8a_ladm2_light_denoised"
        / "manifest"
        / "stage8a_ch1_ladm2_light_denoise_manifest.csv"
    )
    return read_csv(manifest)


def output_paths(output_root: Path, seq: int) -> dict[str, Path]:
    base = output_root / "stage8b_ladm2_local_coords"
    return {
        "txt": base / "txt" / f"stage8b_{seq:05d}_ch1_ladm2_light_denoised_local_cloudcompare.txt",
        "manifest": base / "manifest" / "stage8b_ch1_ladm2_local_coords_manifest.csv",
    }


def open_dataset(h5_path: Path) -> h5py.Dataset:
    h5 = h5py.File(h5_path, "r")
    try:
        return h5["STAGE8A/CH1/denoised_points"]
    except Exception:
        h5.close()
        raise


def append_txt_chunk(
    f,
    data: np.ndarray,
    origin_easting: float,
    origin_northing: float,
) -> None:
    # CloudCompare-friendly ASCII. X/Y are local coordinates matching the
    # standard PCD convention; height_m is retained as Z and scalar field.
    out = np.empty(
        data.size,
        dtype=[
            ("X", "f8"),
            ("Y", "f8"),
            ("Z", "f8"),
            ("source_seq", "u4"),
            ("height_m", "f8"),
            ("gps_time", "f8"),
            ("range_m", "f8"),
            ("scan_angle_deg", "f8"),
            ("point_index", "u8"),
            ("pos_quality_flag", "u4"),
        ],
    )
    out["X"] = data["easting_m"].astype(np.float64) - origin_easting
    out["Y"] = data["northing_m"].astype(np.float64) - origin_northing
    out["Z"] = data["height_m"].astype(np.float64)
    out["source_seq"] = data["source_seq"].astype(np.uint32)
    out["height_m"] = data["height_m"].astype(np.float64)
    out["gps_time"] = data["gps_time"].astype(np.float64)
    out["range_m"] = data["range_m"].astype(np.float64)
    out["scan_angle_deg"] = data["scan_angle_deg"].astype(np.float64)
    out["point_index"] = data["point_index"].astype(np.uint64)
    out["pos_quality_flag"] = data["pos_quality_flag"].astype(np.uint32)
    np.savetxt(
        f,
        out,
        fmt=[
            "%.9f",
            "%.9f",
            "%.9f",
            "%u",
            "%.9f",
            "%.9f",
            "%.9f",
            "%.9f",
            "%u",
            "%u",
        ],
    )


def export_one(
    row: dict[str, str],
    args: argparse.Namespace,
    index: int,
    total: int,
) -> dict[str, Any]:
    seq = int(row["seq"])
    source_h5 = Path(row["h5_path"])
    paths = output_paths(args.output_root, seq)
    txt_path = paths["txt"]
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    if txt_path.exists() and not args.overwrite:
        return {
            "seq": seq,
            "status": "SKIPPED_EXISTS",
            "source_h5": str(source_h5),
            "txt_path": str(txt_path),
            "point_count": "",
            "txt_size_bytes": txt_path.stat().st_size,
            "origin_easting_m": args.origin_easting,
            "origin_northing_m": args.origin_northing,
            "elapsed_sec": 0.0,
        }

    started = time.time()
    with h5py.File(source_h5, "r") as h5:
        ds = h5["STAGE8A/CH1/denoised_points"]
        n = int(ds.shape[0])
        tmp = txt_path.with_suffix(txt_path.suffix + ".tmp")
        if tmp.exists():
            tmp.unlink()
        with tmp.open("w", encoding="utf-8", newline="\n") as f:
            f.write(
                "X Y Z source_seq height_m gps_time range_m scan_angle_deg "
                "point_index pos_quality_flag\n"
            )
            for start in range(0, n, args.chunk_size):
                data = ds[start : min(n, start + args.chunk_size)]
                append_txt_chunk(f, data, args.origin_easting, args.origin_northing)
                if args.progress:
                    done = min(n, start + args.chunk_size)
                    print(
                        f"[{index}/{total}] {seq:05d} {done:,}/{n:,}",
                        flush=True,
                    )
        if txt_path.exists() and args.overwrite:
            txt_path.unlink()
        tmp.replace(txt_path)

    return {
        "seq": seq,
        "status": "PROCESSED",
        "source_h5": str(source_h5),
        "txt_path": str(txt_path),
        "point_count": n,
        "txt_size_bytes": txt_path.stat().st_size,
        "origin_easting_m": args.origin_easting,
        "origin_northing_m": args.origin_northing,
        "elapsed_sec": round(time.time() - started, 3),
    }


def run(args: argparse.Namespace) -> None:
    rows = [row for row in stage8a_rows(args.output_root) if row.get("status") == "PROCESSED"]
    if args.seq:
        wanted = {int(item) for item in args.seq}
        rows = [row for row in rows if int(row["seq"]) in wanted]
    if args.limit > 0:
        rows = rows[: args.limit]

    manifest_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        try:
            manifest_rows.append(export_one(row, args, index, len(rows)))
        except Exception as exc:
            manifest_rows.append(
                {
                    "seq": int(row.get("seq", 0) or 0),
                    "status": "FAILED",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "source_h5": row.get("h5_path", ""),
                    "txt_path": "",
                    "point_count": "",
                    "txt_size_bytes": "",
                    "origin_easting_m": args.origin_easting,
                    "origin_northing_m": args.origin_northing,
                    "elapsed_sec": "",
                }
            )
            if args.stop_on_error:
                raise

    manifest_path = output_paths(args.output_root, 0)["manifest"]
    write_csv(manifest_path, manifest_rows)
    processed = sum(1 for row in manifest_rows if row["status"] == "PROCESSED")
    skipped = sum(1 for row in manifest_rows if row["status"] == "SKIPPED_EXISTS")
    failed = sum(1 for row in manifest_rows if row["status"] == "FAILED")
    print(f"manifest={manifest_path}")
    print(f"processed={processed} skipped_exists={skipped} failed={failed}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage 8B: export Stage 8A CH1 LADM-II denoised points in standard-PCD-like local coordinates."
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--origin-easting", type=float, default=DEFAULT_ORIGIN_EASTING)
    parser.add_argument("--origin-northing", type=float, default=DEFAULT_ORIGIN_NORTHING)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--seq", action="append", default=[], help="Only export selected sequence, e.g. --seq 50")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--progress", action="store_true")
    return parser


def main() -> None:
    run(build_parser().parse_args())


if __name__ == "__main__":
    main()
