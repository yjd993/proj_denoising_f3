# External Data Contract

## Input Root

`AIRBORNE_LIDAR_PROJECT_DATA_ROOT` must point to the directory containing:

```text
0510_f3/
  L1-TIME_ANGE_DIST_DATA/L1_cap_XXXXX_YYYYMMDDhhmmss.h5
  0510f3_processed.mat
untitled/
  calib_coeffs.mat
  COEFFS_20260106.mat                 # legacy MATLAB workflow only
metadata/
  l1_manifest_stage5_time_quality.csv
  stage_reports/                    # historical diagnostics for review
outputs/qc/stage6i_ladm2_scan_geometry_diagnostic/
  best_candidate.json
```

Stage 7A needs the L1 files, processed POS MAT, `calib_coeffs.mat`, Stage 5
manifest, and selected Stage 6I calibration candidate. The candidate is real
dataset-specific input, not an arbitrary example that can safely be invented.
Stage 8D uses the same geometry/POS inputs but discovers L1 files directly.
Archived Stage 6M/6N reports add prior QC context; missing context does not
constitute an approved QC gate. Stage 7D additionally uses Stage 6I/6K/6N reports.

Copy the directory structure intact. Copying only the large H5 files is
insufficient: calibration, POS, candidate JSON, manifests, and exclusions
are part of the data package. Real files in `metadata/` and `untitled/*.mat`
are deliberately no longer versioned; existing local copies are retained.

## Stage 5 Manifest

UTF-8 CSV, optional BOM. Required columns: `file`, `seq`, `status`.
Usual columns also include `reason`, `point_count`, `gnss_min`, `gnss_max`,
`pulse_min`, `pulse_max`, and `total_pulses`.

`file` is relative to the input root. Use forward slashes for new manifests;
historical Windows backslashes are accepted. `seq` is numeric; `status=OK`
is required for default 7A selection. Other statuses remain excluded unless
`--include-non-ok` is explicitly used. Do not relabel bad-time files as OK.
`examples/l1_manifest.example.csv` is fabricated format documentation only.

## Result Root And Exclusions

`AIRBORNE_LIDAR_STAGE_ROOT` points to the copied Stage 7/8 result directory:

```text
h5/                                 # Stage 7A full points
laz/
txt/
manifest/
reports/
qc/
stage7d_teacher_package/
stage8a_ladm2_light_denoised/
stage8b_ladm2_local_coords/
stage8c_l2p_intermediate/
  h5/
  txt/
  txt_pos_match_failed_excluded/
  manifest/
    stage8c_pos_match_failed_excluded_txt_manifest.csv
  reports/
```

Stage 8D checks the exclusion CSV above by default. Override with
`--exclude-manifest PATH` or `AIRBORNE_LIDAR_EXCLUDE_MANIFEST`.
The CSV requires `seq` (integer 1..99999, optionally zero-padded) and accepts
optional `reason` or `action`. Existing additional columns are preserved in
the external file and ignored by selection. Duplicate/invalid sequences,
missing headers, and missing explicitly requested files cause an error.
See `examples/exclusions.example.csv` for fabricated rows.

Selection order: sequence range, exclusions, existing TXT, then `--limit`.
Neither `--overwrite` nor `--no-only-missing` disables exclusions.
If there is a quarantine directory but no default exclusion CSV, processing
stops. If neither exists, a fresh dataset may run without exclusions; this
does **not** establish file-level quality approval. Review the first dry run.
For a new output root, explicitly pass the archive's exclusion manifest.
Copy both the list and quarantined files when transferring an existing run.

An empty selection leaves old summaries unchanged. A dry run is entirely
read-only. Real partial batches still replace their own batch manifest and
report; use a fresh result root for experiments.

## Moving An Archive

Old Stage 7/8 CSV/JSON/H5 metadata may contain absolute paths from the original
machine. Setting environment variables changes defaults, not stored paths.
Before consuming an archived manifest on another drive, make a separate
working copy and update its path columns with a CSV parser after verifying
each target exists. Do not apply text replacement to binary H5 files, guess
missing provenance, or overwrite the archival manifest.

New 7A output paths are absolute so downstream consumers work even when the
result root is nested inside the input root. They still require migration
when moving machines. Stage 8C builds source filenames from its result root.

## Coordinate And Quality Notes

- Stage 7A/8A coordinates: EPSG:32651 easting, northing, height in meters.
- Stage 8B TXT: X = easting - origin easting, Y = northing - origin northing,
  Z = height. Default XY origin is (394000, 3417000); override for other areas.
- Stage 8C/8D LIDAR_X/Y/Z: north/east/down offsets after POS rotation.
- Stage 8C/8D POINT_X/Y/Z: POS northing + north offset, POS easting + east
  offset, POS height - down offset. X/Y differ from Stage 7A/8B.
- Stage 8A TXT is sampled. Stage 8B exports all retained 8A points.
- Stage 8C H5 retains all source 7A points; its TXT and Stage 8D TXT require
  good POS and range strictly greater than 30 m by default.
- Stage 8C/8D are intermediate exports, not an additional denoising stage.
- Legacy Stage 7A restored manifests may contain
  `UNKNOWN_FROM_RESTORED_MANIFEST` and incomplete time provenance. Preserve
  that limitation; file presence does not reconstruct missing audit history.

## Before A Full Batch

Run the synthetic tests and both selection dry runs, verify input files
open, and process a single file into a new output directory. Review point
counts, POS coverage, coordinate convention, disk space, and CloudCompare
appearance before a full batch. The scripts load full point arrays for
geometry/denoising; runtime memory needs exceed compressed H5 sizes.
