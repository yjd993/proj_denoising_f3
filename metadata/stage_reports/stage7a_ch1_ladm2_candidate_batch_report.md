# Stage 7A CH1 LADM-II Candidate Batch

## Gate

- Conclusion: READY_FOR_REVIEW
- Ready for review: True
- Reason: Stage 7A candidate batch completed without failed files.

## Scope

- Sequence range: `00050` to `00150` inclusive.
- Requested output root: `C:\proj_denoising_f3_2.0`
- Stage 6G legacy route: skipped.
- Non-OK timestamp files: skipped, not repaired.
- H5 contains full points plus POS interpolation fields. LAZ/TXT use the export filter described below.

## H5 Chain Fields

Each Stage 7A H5 now carries the full diagnostic chain:

- L1 timing/range/scan: `gnss_sec_raw`, `gps_time`, `range_before_m`, `range_m`, `coder`, `scan_angle_deg`
- L2 body/FRD: `frd_x_m`, `frd_y_m`, `frd_z_m`
- POS match: `pos_time_sec`, `pos_easting`, `pos_northing`, `pos_height`, `pos_roll`, `pos_pitch`, `pos_heading`, `pos_interp_dt`
- NED offsets: `north_offset_m`, `east_offset_m`, `down_offset_m`
- Final UTM/geographic coordinates: `easting_m`, `northing_m`, `height_m`, `lon`, `lat`

## Export Filter

- export_min_range_m: 0.0
- export_pos_good_only: True
- laz_max_points_per_file: 0
- txt_max_points_per_file: 0

## Aggregate

- Files in requested range: 101
- Processed files: 95
- Skipped files: 6
- Total H5 points: 217,000,065
- Total LAZ points: 179,717,052
- Total TXT points: 179,717,052
- Output size bytes: 54,717,250,520

## Processed Preview

| seq | H5 points | LAZ points | POS success | height median m |
|---:|---:|---:|---:|---:|
| 00050 | 2,600,678 | 2,146,343 | 100.000000% | 14.758 |
| 00051 | 2,151,537 | 1,755,099 | 100.000000% | 14.840 |
| 00052 | 2,155,759 | 1,761,979 | 100.000000% | 14.856 |
| 00053 | 2,249,868 | 1,859,297 | 100.000000% | 14.886 |
| 00055 | 2,804,253 | 2,345,089 | 100.000000% | 14.995 |
| 00056 | 2,758,069 | 2,297,721 | 100.000000% | 15.009 |
| 00057 | 2,736,141 | 2,275,896 | 100.000000% | 14.983 |
| 00058 | 2,347,122 | 1,949,313 | 100.000000% | 14.991 |
| 00059 | 2,345,751 | 1,950,524 | 100.000000% | 14.968 |
| 00060 | 2,345,985 | 1,951,781 | 100.000000% | 14.959 |

## Skipped Files

| seq | manifest status | reason |
|---:|---|---|
| 00054 | REPAIR_CANDIDATE | GNSS_SEC_CH1 appears to contain pulse index/count values |
| 00073 | REPAIR_CANDIDATE | GNSS_SEC_CH1 appears to contain pulse index/count values |
| 00093 | REPAIR_CANDIDATE | GNSS_SEC_CH1 appears to contain pulse index/count values |
| 00113 | REPAIR_CANDIDATE | GNSS_SEC_CH1 appears to contain pulse index/count values |
| 00132 | REPAIR_CANDIDATE | GNSS_SEC_CH1 appears to contain pulse index/count values |
| 00133 | BAD_TIME | less than 95% lidar_time_sec within POS range |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| CAO2017_LADM2_4_7_4_14 | LADM-II mirror normal and reflected beam scan geometry | doctoral_thesis | Cao 2017 section 4.4.2, formulas 4-7 to 4-14 | yes, production-candidate transform |
| STAGE6I_BEST_CANDIDATE | Stage 6I selected LADM-II calibration candidate | project_diagnostic_parameter | D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\best_candidate.json | yes, production-candidate transform |
| STAGE7A_RANGE_LIMIT | Limited production-candidate batch range | user_scope_rule | User requested Stage 7A only for L1 sequences 00050-00150 and output under C:\proj_denoising_f3_2.0 | no, output scope only |
| BAD_TIME_ISOLATION | Skip non-OK timestamp files | project_gate_rule | Stage 5 manifest and Stage 6M timestamp audit; do not repair or process corrupted timestamps here | yes, skip bad-time files |

## Outputs

- Manifest CSV: `C:\proj_denoising_f3_2.0\manifest\stage7a_ch1_ladm2_00050_00150_manifest.csv`
- Manifest JSON: `C:\proj_denoising_f3_2.0\manifest\stage7a_ch1_ladm2_00050_00150_manifest.json`
- Report JSON: `C:\proj_denoising_f3_2.0\reports\stage7a_ch1_ladm2_candidate_batch_report.json`
- H5 directory: `C:\proj_denoising_f3_2.0\h5`
- LAZ directory: `C:\proj_denoising_f3_2.0\laz`
- TXT directory: `C:\proj_denoising_f3_2.0\txt`

## Stop Rule

Stage 7A is a production candidate batch, not a final deliverable. Do not merge skipped bad-time files into the candidate set unless a separate time-repair stage is approved and clearly marked.
