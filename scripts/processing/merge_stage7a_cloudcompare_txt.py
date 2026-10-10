#!/usr/bin/env python3
"""Merge Stage 7A CloudCompare TXT files while keeping a single header."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from project_paths import STAGE_ROOT


DEFAULT_INPUT_DIR = STAGE_ROOT / "txt"
DEFAULT_OUTPUT_NAME = "stage7a_00050_00150_ch1_ladm2_cloudcompare_merged.txt"
INPUT_GLOB = "stage7a_*_ch1_ladm2_cloudcompare.txt"
COPY_BUFFER_BYTES = 16 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge Stage 7A CloudCompare TXT files in filename order."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-name", default=DEFAULT_OUTPUT_NAME)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def copy_remaining(source, destination) -> int:
    copied = 0
    while True:
        block = source.read(COPY_BUFFER_BYTES)
        if not block:
            return copied
        destination.write(block)
        copied += len(block)


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_path = input_dir / args.output_name
    partial_path = output_path.with_name(output_path.name + ".partial")

    files = sorted(
        path
        for path in input_dir.glob(INPUT_GLOB)
        if path.resolve() not in {output_path.resolve(), partial_path.resolve()}
    )
    if not files:
        raise SystemExit(f"No input files matched {INPUT_GLOB!r} in {input_dir}")
    if output_path.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output_path}; use --overwrite")

    expected_header: bytes | None = None
    total_input_bytes = sum(path.stat().st_size for path in files)
    bytes_copied = 0

    if partial_path.exists():
        partial_path.unlink()

    try:
        with partial_path.open("wb", buffering=0) as destination:
            for index, path in enumerate(files, start=1):
                with path.open("rb", buffering=0) as source:
                    header = source.readline()
                    if not header:
                        raise RuntimeError(f"Empty input file: {path}")
                    normalized_header = header.rstrip(b"\r\n")
                    if expected_header is None:
                        expected_header = normalized_header
                        destination.write(header)
                        bytes_copied += len(header)
                    elif normalized_header != expected_header:
                        raise RuntimeError(
                            f"Header mismatch in {path.name}: {normalized_header!r}"
                        )
                    bytes_copied += copy_remaining(source, destination)

                percent = 100.0 * index / len(files)
                print(
                    f"[{index:03d}/{len(files):03d}] {percent:6.2f}% "
                    f"{path.name}",
                    flush=True,
                )

            destination.flush()
            os.fsync(destination.fileno())

        os.replace(partial_path, output_path)
    except BaseException:
        if partial_path.exists():
            partial_path.unlink()
        raise

    print(f"INPUT_FILES={len(files)}")
    print(f"TOTAL_INPUT_BYTES={total_input_bytes}")
    print(f"OUTPUT_BYTES={output_path.stat().st_size}")
    print(f"OUTPUT={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
