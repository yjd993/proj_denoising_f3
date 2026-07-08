# Stage 7B CH1 LADM-II Candidate Automatic QC

## Gate

- Conclusion: REVIEW
- Ready for review: False
- Reason: Automatic QC completed, but these criteria need review: seam_warning

## Scope

- Input root: `C:\proj_denoising_f3_2.0`
- Manifest: `C:\proj_denoising_f3_2.0\manifest\stage7a_ch1_ladm2_00050_00150_manifest.csv`
- Sequence range: `00050` to `00150`.
- Geometry: not recomputed here; Stage 7B only checks existing Stage 7A outputs.
- Skipped bad-time files stay isolated from geometry judgment: [54, 73, 93, 113, 132, 133].

## H5 Chain Schema

Required fields checked in every processed H5:

- L1 timing/range/scan: `gnss_sec_raw`, `gps_time`, `range_before_m`, `range_m`, `coder`, `scan_angle_deg`
- L2 body/FRD: `frd_x_m`, `frd_y_m`, `frd_z_m`
- POS match: `pos_time_sec`, `pos_easting`, `pos_northing`, `pos_height`, `pos_roll`, `pos_pitch`, `pos_heading`, `pos_interp_dt`
- NED offsets: `north_offset_m`, `east_offset_m`, `down_offset_m`
- Final UTM/geographic: `easting_m`, `northing_m`, `height_m`, `lon`, `lat`

## Aggregate

- Manifest processed files: 95
- QC processed files: 95
- Manifest skipped files: 6
- Total H5 points: 217,000,065
- Total analysis points (`range_m > 30.0` and POS good): 142,893,633
- Min POS success rate: 100.000000%
- Max POS interpolation dt p99: 0.002475364 s
- Files missing chain fields: 0
- Evaluated adjacent seams: 89
- Skipped-gap seams: 5
- Seam warning count: 13
- Max endpoint time gap: 0.126660672 s
- Max endpoint horizontal gap: 24.069921 m
- Max endpoint height delta: 20.474959 m
- Scan-angle warning bin count: 765
- Range warning bin count: 276

## Per-File Preview

| seq | points | analysis | pos | dt p99 | t min | t max | h med |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 50 | 2600678 | 1671768 | 1 | 0.00247483 | 40024.8 | 40028.3 | 14.0716 |
| 51 | 2151537 | 1348270 | 1 | 0.00247507 | 40028.3 | 40031.3 | 14.3355 |
| 52 | 2155759 | 1354210 | 1 | 0.00247507 | 40031.3 | 40034.3 | 14.4533 |
| 53 | 2249868 | 1453062 | 1 | 0.00247498 | 40034.3 | 40037.3 | 14.5909 |
| 55 | 2804253 | 1872263 | 1 | 0.00247525 | 40040.3 | 40043.8 | 14.7463 |
| 56 | 2758069 | 1823717 | 1 | 0.00247486 | 40043.8 | 40047.3 | 14.7552 |
| 57 | 2736141 | 1802719 | 1 | 0.00247502 | 40047.3 | 40050.8 | 14.7633 |
| 58 | 2347122 | 1545429 | 1 | 0.00247506 | 40050.8 | 40053.8 | 14.78 |
| 59 | 2345751 | 1544557 | 1 | 0.00247495 | 40053.8 | 40056.8 | 14.795 |
| 60 | 2345985 | 1549005 | 1 | 0.00247498 | 40056.8 | 40059.8 | 14.7779 |
| 61 | 2740713 | 1812918 | 1 | 0.00247513 | 40059.8 | 40063.3 | 14.7942 |
| 62 | 2729363 | 1805566 | 1 | 0.00247511 | 40063.3 | 40066.8 | 14.7789 |
| 63 | 2336524 | 1543871 | 1 | 0.002475 | 40066.8 | 40069.8 | 14.7924 |
| 64 | 2336480 | 1547393 | 1 | 0.00247502 | 40069.8 | 40072.8 | 14.8001 |
| 65 | 2331621 | 1552026 | 1 | 0.00247513 | 40072.8 | 40075.8 | 14.8263 |
| 66 | 2347847 | 1561253 | 1 | 0.00247504 | 40075.8 | 40078.8 | 14.9329 |
| 67 | 2338428 | 1552349 | 1 | 0.00247488 | 40078.8 | 40081.8 | 15.0317 |
| 68 | 2289837 | 1517562 | 1 | 0.00247501 | 40081.8 | 40084.8 | 15.0067 |
| 69 | 2240113 | 1490370 | 1 | 0.00247514 | 40084.8 | 40087.8 | 15.0027 |
| 70 | 2331910 | 1550059 | 1 | 0.00247495 | 40087.8 | 40090.8 | 15.0002 |

## Seam Preview

| from | to | eval | pass | dt s | end XY m | end dH m | status | warnings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 50 | 51 | True | True | 2e-06 | 0.081236 | 0.261899 | PASS |  |
| 51 | 52 | True | True | 2e-06 | 0.0224261 | 0.173214 | PASS |  |
| 52 | 53 | True | False | 4e-06 | 0.0286991 | -0.0898157 | REVIEW | centroid_horizontal_gap |
| 53 | 55 | False | True |  |  |  | GAP_SKIPPED_BAD_TIME |  |
| 55 | 56 | True | True | 2e-06 | 0.0145012 | -0.050871 | PASS |  |
| 56 | 57 | True | True | 2e-06 | 0.0191003 | -0.20422 | PASS |  |
| 57 | 58 | True | True | 2e-06 | 0.0478977 | 0.143386 | PASS |  |
| 58 | 59 | True | True | 2e-06 | 0.00855619 | 0.0864316 | PASS |  |
| 59 | 60 | True | True | 2e-06 | 0.0191361 | 0.05438 | PASS |  |
| 60 | 61 | True | True | 2e-06 | 0.016036 | -0.114913 | PASS |  |
| 61 | 62 | True | True | 2e-06 | 0.0179578 | 0.0535481 | PASS |  |
| 62 | 63 | True | True | 2e-06 | 0.017233 | -0.118364 | PASS |  |
| 63 | 64 | True | True | 2e-06 | 0.0500526 | -0.222972 | PASS |  |
| 64 | 65 | True | True | 1.996e-06 | 0.048112 | 0.148312 | PASS |  |
| 65 | 66 | True | False | 1.99601e-06 | 0.00367664 | 0.00304526 | REVIEW | centroid_height_delta |
| 66 | 67 | True | False | 1.996e-06 | 0.0134423 | -0.083434 | REVIEW | centroid_height_delta |
| 67 | 68 | True | True | 2e-06 | 0.00797207 | 0.0309578 | PASS |  |
| 68 | 69 | True | True | 2e-06 | 0.0115319 | 0.121416 | PASS |  |
| 69 | 70 | True | True | 2e-06 | 0.00332794 | -0.00518435 | PASS |  |
| 70 | 71 | True | True | 2e-06 | 0.0730736 | -0.196659 | PASS |  |
| 71 | 72 | True | True | 2.004e-06 | 0.006379 | 0.00862964 | PASS |  |
| 72 | 74 | False | True |  |  |  | GAP_SKIPPED_BAD_TIME |  |
| 74 | 75 | True | True | 2e-06 | 0.036279 | 0.140729 | PASS |  |
| 75 | 76 | True | True | 2e-06 | 0.0577804 | 0.159832 | PASS |  |
| 76 | 77 | True | True | 1.99999e-06 | 0.0122568 | 0.0441533 | PASS |  |
| 77 | 78 | True | True | 2e-06 | 0.0748936 | 0.215879 | PASS |  |
| 78 | 79 | True | False | 2e-06 | 3.98106 | 12.468 | REVIEW | endpoint_horizontal_gap;endpoint_height_delta |
| 79 | 80 | True | True | 2e-06 | 0.0492231 | 0.14045 | PASS |  |
| 80 | 81 | True | True | 2e-06 | 0.0380481 | 0.124455 | PASS |  |
| 81 | 82 | True | False | 6.004e-06 | 0.0185984 | 0.0446552 | REVIEW | centroid_horizontal_gap |

## CloudCompare Sample Checklist Preview

| seq | reason | txt pts | h med |
| --- | --- | --- | --- |
| 50 | first_processed_files | 2146343 | 14.0716 |
| 51 | first_processed_files | 1755099 | 14.3355 |
| 52 | first_processed_files;seam_warning_neighbor | 1761979 | 14.4533 |
| 53 | around_skipped_00054_00054;seam_warning_neighbor | 1859297 | 14.5909 |
| 55 | around_skipped_00054_00054 | 2345089 | 14.7463 |
| 65 | seam_warning_neighbor | 1948818 | 14.8263 |
| 66 | seam_warning_neighbor | 1960271 | 14.9329 |
| 67 | seam_warning_neighbor | 1949386 | 15.0317 |
| 72 | around_skipped_00073_00073 | 1941262 | 14.9881 |
| 74 | around_skipped_00073_00073 | 2260181 | 14.9472 |
| 78 | seam_warning_neighbor | 2029562 | 14.8356 |
| 79 | seam_warning_neighbor | 2026007 | 14.7037 |
| 81 | seam_warning_neighbor | 1572055 | 14.6466 |
| 82 | seam_warning_neighbor | 1630951 | 14.6121 |
| 92 | around_skipped_00093_00093 | 1695866 | 14.8912 |
| 94 | around_skipped_00093_00093 | 1739685 | 14.8642 |
| 102 | seam_warning_neighbor | 1890837 | 14.913 |
| 103 | seam_warning_neighbor | 1808863 | 14.9174 |
| 105 | seam_warning_neighbor | 1928397 | 14.9599 |
| 106 | seam_warning_neighbor | 1923722 | 15.0124 |
| 112 | around_skipped_00113_00113 | 1930595 | 15.0858 |
| 114 | around_skipped_00113_00113;known_stage6l_visual_segment | 1925889 | 15.1052 |
| 115 | known_stage6l_visual_segment | 1923454 | 14.9617 |
| 116 | known_stage6l_visual_segment | 1865581 | 14.9027 |
| 117 | known_stage6l_visual_segment | 1926521 | 14.856 |
| 118 | known_stage6l_visual_segment | 1919816 | 14.8224 |
| 120 | seam_warning_neighbor | 1902709 | 14.7277 |
| 121 | seam_warning_neighbor | 1819755 | 14.6029 |
| 131 | around_skipped_00132_00133 | 1716837 | 14.8323 |
| 134 | around_skipped_00132_00133;seam_warning_neighbor | 1568205 | 14.7673 |
| 135 | seam_warning_neighbor | 1723872 | 14.4513 |
| 137 | seam_warning_neighbor | 1731216 | 14.9127 |
| 138 | seam_warning_neighbor | 1815543 | 14.9594 |
| 141 | seam_warning_neighbor | 1829729 | 14.9571 |
| 142 | seam_warning_neighbor | 1928147 | 14.9539 |
| 143 | seam_warning_neighbor | 1938387 | 14.9929 |
| 144 | seam_warning_neighbor | 1928302 | 14.9566 |
| 145 | seam_warning_neighbor | 2144207 | 14.9004 |
| 148 | last_processed_files | 1815163 | 15.0512 |
| 149 | last_processed_files | 1911101 | 15.0528 |

## Scan-Angle Warning Bins

| seq | start | end | count | shift | warn |
| --- | --- | --- | --- | --- | --- |
| 50 | 105 | 120 | 76030 | 0.21093 | height_distribution_shift |
| 50 | 120 | 135 | 72419 | 0.199036 | height_distribution_shift |
| 51 | 165 | 180 | 66561 | 0.339673 | height_distribution_shift |
| 51 | 180 | 195 | 64991 | 0.177055 | height_distribution_shift |
| 52 | 30 | 45 | 49135 | 0.0927852 | height_distribution_shift |
| 52 | 45 | 60 | 26835 | 0.297075 | height_distribution_shift |
| 52 | 60 | 75 | 23112 | 0.395509 | height_distribution_shift |
| 52 | 75 | 90 | 25053 | 0.404063 | height_distribution_shift |
| 52 | 90 | 105 | 32147 | 0.378418 | height_distribution_shift |
| 52 | 105 | 120 | 40005 | 0.07989 | height_distribution_shift |
| 52 | 150 | 165 | 68918 | 0.292449 | height_distribution_shift |
| 52 | 165 | 180 | 66245 | 0.601223 | height_distribution_shift |

## Range Warning Bins

| seq | range | count | internal outlier | warn |
| --- | --- | --- | --- | --- |
| 50 | 30-60 | 185 | 0 | low_count |
| 50 | 60-90 | 206 | 0 | low_count |
| 50 | >=150 | 538 | 0 | low_count |
| 51 | 30-60 | 159 | 0 | low_count |
| 51 | 60-90 | 192 | 0 | low_count |
| 51 | >=150 | 443 | 0 | low_count |
| 52 | 30-60 | 170 | 0 | low_count |
| 52 | 60-90 | 187 | 0 | low_count |
| 52 | >=150 | 470 | 0 | low_count |
| 53 | 30-60 | 165 | 0 | low_count |
| 53 | 60-90 | 151 | 0 | low_count |
| 53 | >=150 | 532 | 0 | low_count |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| STAGE7A_CHAIN_SCHEMA_QC | Verify Stage 7A H5 full-chain fields | project_qc_rule | L1 timing/range/scan -> L2 FRD -> POS match -> NED offset -> UTM/geographic coordinate | no, QC only |
| STAGE7A_CONTINUITY_QC | Stage 7A candidate continuity QC | project_qc_rule | Adjacent processed files in C:\proj_denoising_f3_2.0, sequences 00050-00150 | no, QC only |
| BAD_TIME_ISOLATION | Keep skipped bad-time files out of geometry judgment | project_gate_rule | Stage 7A skipped non-OK timestamp files; Stage 6M isolated 00113 timestamp corruption | no, gap annotation only |

## Outputs

- Per-file summary CSV: `C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_per_file_qc_summary.csv`
- Seam summary CSV: `C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_seam_qc_summary.csv`
- Scan-angle bin CSV: `C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_scan_angle_bin_summary.csv`
- Range bin CSV: `C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_range_bin_summary.csv`
- CloudCompare checklist CSV: `C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_cloudcompare_sample_checklist.csv`
- Report JSON: `C:\proj_denoising_f3_2.0\reports\stage7b_ch1_ladm2_candidate_qc_report.json`
- Report Markdown: `C:\proj_denoising_f3_2.0\reports\stage7b_ch1_ladm2_candidate_qc_report.md`

## Stop Rule

Stage 7B is QC only. It does not repair skipped files, does not run Stage 6G, and does not modify Stage 7A H5/LAZ/TXT outputs.
