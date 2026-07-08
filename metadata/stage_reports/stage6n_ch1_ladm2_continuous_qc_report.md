# Stage 6N LADM-II Continuous Segment Automatic QC

## Gate

- Conclusion: PASS
- Ready for next stage: True
- Reason: Automatic QC found full POS coverage, adequate analysis-point density, and no seam discontinuity beyond thresholds.

## Scope

- Stage 6G legacy empirical propagation: skipped by design.
- Input: existing Stage 6L full-point H5 files for 00114-00118.
- 00113: excluded from geometry decisions because Stage 6M classified its raw timestamps as corrupted.
- Geometry: not recomputed here; this is QC only.

## Aggregate

- Total H5 points: 11,546,156
- Total analysis points (`range_m > 30.0` and POS good): 7,668,718
- Min POS success rate: 100.000000%
- Min analysis-point rate: 66.166425%
- Max endpoint time gap: 0.000002000 s
- Max endpoint horizontal gap: 0.057324 m
- Max endpoint height delta: 0.196922 m
- Seam warning count: 0
- Scan-angle warning bin count: 16
- Range warning bin count: 15

## Per-File Summary

| seq | points | analysis | pos | t min | t max | h med | h p05 | h p95 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 114 | 2329228 | 1542408 | 1 | 40220.9 | 40223.9 | 15.1052 | 14.5894 | 15.6647 |
| 115 | 2328409 | 1540625 | 1 | 40223.9 | 40226.9 | 14.9617 | 14.5599 | 15.5142 |
| 116 | 2254465 | 1495328 | 1 | 40226.9 | 40229.9 | 14.9027 | 14.4894 | 15.4694 |
| 117 | 2320568 | 1546528 | 1 | 40229.9 | 40232.9 | 14.856 | 14.437 | 15.4218 |
| 118 | 2313486 | 1543829 | 1 | 40232.9 | 40235.9 | 14.8224 | 14.2564 | 18.209 |

## Seam Summary

| from | to | pass | dt s | end XY m | end dH m | cent XY m | cent dH m | warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 114 | 115 | True | 1.99999e-06 | 0.0573004 | -0.16123 | 14.7698 | -0.0341288 |  |
| 115 | 116 | True | 2e-06 | 0.00470353 | 0.00279202 | 20.913 | -0.24629 |  |
| 116 | 117 | True | 2e-06 | 0.057324 | 0.196922 | 21.4719 | -0.137488 |  |
| 117 | 118 | True | 2e-06 | 0.00429163 | -0.0257381 | 16.8368 | -0.487308 |  |

## Scan-Angle Warning Bins

| seq | start | end | count | shift | warn |
| --- | --- | --- | --- | --- | --- |
| 114 | 255 | 270 | 65011 | 0.0514067 | height_distribution_shift |
| 114 | 270 | 285 | 64985 | 0.0833885 | height_distribution_shift |
| 114 | 285 | 300 | 65185 | 0.095927 | height_distribution_shift |
| 115 | 240 | 255 | 63424 | 0.0527561 | height_distribution_shift |
| 115 | 255 | 270 | 63227 | 0.0652886 | height_distribution_shift |
| 116 | 240 | 255 | 61445 | 0.0873464 | height_distribution_shift |
| 117 | 225 | 240 | 64829 | 0.0866896 | height_distribution_shift |
| 118 | 165 | 180 | 63396 | 0.053016 | height_distribution_shift |
| 118 | 180 | 195 | 63806 | 0.101699 | height_distribution_shift |
| 118 | 195 | 210 | 63538 | 0.102694 | height_distribution_shift |
| 118 | 210 | 225 | 63369 | 0.0638956 | height_distribution_shift |
| 118 | 225 | 240 | 63887 | 0.130199 | height_distribution_shift |

## Range Warning Bins

| seq | range | count | internal outlier | warn |
| --- | --- | --- | --- | --- |
| 114 | 30-60 | 206 | 0 | low_count |
| 114 | 60-90 | 155 | 0 | low_count |
| 114 | >=150 | 562 | 0 | low_count |
| 115 | 30-60 | 168 | 0 | low_count |
| 115 | 60-90 | 163 | 0 | low_count |
| 115 | >=150 | 532 | 0 | low_count |
| 116 | 30-60 | 184 | 0 | low_count |
| 116 | 60-90 | 161 | 0 | low_count |
| 116 | >=150 | 498 | 0 | low_count |
| 117 | 30-60 | 173 | 0 | low_count |
| 117 | 60-90 | 158 | 0 | low_count |
| 117 | >=150 | 514 | 0 | low_count |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| STAGE6G_SKIPPED | Skip legacy empirical f_body_frame_xyz propagation | project_gate_rule | Stage 6I LADM-II exact-time QC outperformed Stage 6F empirical geometry by a large margin | no, planning gate only |
| LADM2_CONTINUOUS_QC | LADM-II continuous-segment automatic QC | project_qc_rule | Stage 6L full-point H5 files for 00114-00118 | no, QC only |
| TIMESTAMP_ISOLATION_00113 | Exclude corrupted 00113 timestamps from geometry decisions | project_gate_rule | Stage 6M timestamp audit: GNSS_SEC_CH* equals PULSE_INDEX_CH* for 00113 | no, gate only |

## Outputs

- Per-file summary CSV: `outputs\qc\stage6n_ladm2_continuous_qc\stage6n_per_file_qc_summary.csv`
- Seam summary CSV: `outputs\qc\stage6n_ladm2_continuous_qc\stage6n_seam_qc_summary.csv`
- Scan-angle bin CSV: `outputs\qc\stage6n_ladm2_continuous_qc\stage6n_scan_angle_bin_summary.csv`
- Range bin CSV: `outputs\qc\stage6n_ladm2_continuous_qc\stage6n_range_bin_summary.csv`
- Report JSON: `metadata\stage_reports\stage6n_ch1_ladm2_continuous_qc_report.json`

## Stop Rule

This stage does not produce final L3/LAZ and does not modify Stage 6L H5 files. Use the PASS/REVIEW result only as a gate for the next LADM-II production-candidate stage.
