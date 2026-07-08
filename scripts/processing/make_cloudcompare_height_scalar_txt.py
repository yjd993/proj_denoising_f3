from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "outputs" / "qc" / "stage5r_ch1_v2_sample" / "ch1_v2_sample_z1_txt_manifest.csv"
DEFAULT_OUT_ROOT = ROOT / "outputs" / "txt_ch1" / "cloudcompare_height_scalar" / "z1"


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def parse_seq(path_text: str) -> int | None:
    match = re.search(r"cap_(\d{5})_", path_text)
    return int(match.group(1)) if match else None


def parse_seq_filter(text: str) -> set[int] | None:
    if not text:
        return None
    seqs: set[int] = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            seqs.update(range(int(start), int(end) + 1))
        else:
            seqs.add(int(token))
    return seqs


def output_path_for(input_path: Path, out_root: Path) -> Path:
    group = "stable_00111_00115" if "georef_v2_stable_00111_00115" in str(input_path) else "first12"
    return out_root / group / input_path.name.replace(".txt", "_height_scalar.txt")


def convert_one(input_path: Path, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with input_path.open("r", encoding="utf-8") as src, output_path.open("w", encoding="utf-8", newline="\n") as dst:
        for line in src:
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split()
            if len(parts) < 3:
                continue
            # CloudCompare-friendly columns:
            # X Y Z height_m gps_time range_m scan_angle_deg source_seq time_repair_flag quality_flag pos_quality_flag
            dst.write("\t".join(parts[:3] + [parts[2]] + parts[3:]) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Duplicate Z as first scalar field for CloudCompare height coloring.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT)
    parser.add_argument("--seqs", default="", help="Comma/range list such as 2,7-10,111-115.")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    wanted = parse_seq_filter(args.seqs)
    rows: list[dict[str, str]] = []
    with args.manifest.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            txt_file = row.get("txt_file", "")
            seq = parse_seq(txt_file)
            if wanted is not None and seq not in wanted:
                continue
            rows.append(row)
            if args.limit and len(rows) >= args.limit:
                break

    manifest_path = args.out_root / "cloudcompare_height_scalar_manifest.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as mf:
        writer = csv.DictWriter(
            mf,
            fieldnames=["source_txt", "output_txt", "point_count", "columns"],
        )
        writer.writeheader()
        for idx, row in enumerate(rows, 1):
            input_path = ROOT / row["txt_file"]
            output_path = output_path_for(input_path, args.out_root)
            count = convert_one(input_path, output_path)
            writer.writerow(
                {
                    "source_txt": rel(input_path),
                    "output_txt": rel(output_path),
                    "point_count": count,
                    "columns": "X|Y|Z|height_m|gps_time|range_m|scan_angle_deg|source_seq|time_repair_flag|quality_flag|pos_quality_flag",
                }
            )
            print(f"[{idx}/{len(rows)}] {input_path.name} -> {output_path} ({count:,} rows)", flush=True)

    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
