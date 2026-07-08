# Stage 7C CH1 LADM-II Focused Seam Audit

## Gate

- Conclusion: REVIEW_TIME_OR_POS_BOUNDARY
- Ready for Stage 7A release: False
- Reason: At least one focused boundary has a time gap or POS trajectory continuity issue.

## Scope

- Input root: `C:\proj_denoising_f3_2.0`
- Stage 7B seam CSV: `C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_seam_qc_summary.csv`
- Target boundaries: 18
- Stage 7B warning boundaries: 13
- Isolated bad-time gaps: 5
- Stage 6G legacy route: still skipped.

## Aggregate

- Audit class counts: `{'LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT': 12, 'ISOLATED_BAD_TIME_GAP': 5, 'TIME_GAP_REVIEW': 1}`
- Hard review boundaries: 1
- Time-gap review boundaries: 1
- POS trajectory review boundaries: 0
- Window-distribution review boundaries: 0
- CloudCompare export files: 18
- CloudCompare export points: 1,800,000
- Max endpoint time gap: 6.004290576 s
- Max POS endpoint horizontal gap: 7.108281 m
- Max POS endpoint height delta: 0.116195 m

## Boundary Summary

| from | to | type | class | dt s | POS XY | POS dH | rg30 dH | rg30 0.2 dH | rg30 dR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 52 | 53 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.56127e-06 | 0 | -0.414986 | -0.0998888 | 0.978394 |
| 53 | 55 | gap_skipped_bad_time | ISOLATED_BAD_TIME_GAP | 3.00134 | 3.70393 | 0.116195 | 0.134551 | 0.104757 | 0.212669 |
| 65 | 66 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 1.99601e-06 | 1.99594e-06 | 7.98402e-07 | -0.864296 | 0.532374 | 0.246647 |
| 66 | 67 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 1.996e-06 | 3.41081e-06 | 3.992e-07 | 14.5014 | 0.156528 | -13.8035 |
| 72 | 74 | gap_skipped_bad_time | ISOLATED_BAD_TIME_GAP | 3.00268 | 3.52763 | 0.012 | -0.0213634 | -0.0191267 | -0.116005 |
| 78 | 79 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.88441e-06 | 0 | -0.0554037 | -0.122972 | 2.65396 |
| 81 | 82 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.33235e-06 | 0 | 0.0287545 | -0.0261143 | 0.94207 |
| 92 | 94 | gap_skipped_bad_time | ISOLATED_BAD_TIME_GAP | 3.00154 | 3.63855 | -0.018 | -0.00175665 | -0.00495323 | -1.75525 |
| 102 | 103 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.52984e-06 | 0 | 0.2751 | 0.041971 | 2.00834 |
| 105 | 106 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.52984e-06 | 0 | -0.0209064 | -0.00229344 | 0.667885 |
| 112 | 114 | gap_skipped_bad_time | ISOLATED_BAD_TIME_GAP | 3.0018 | 3.62804 | -0.009 | 0.0131399 | 0.0708311 | 0.0843658 |
| 120 | 121 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 1.996e-06 | 2.32798e-06 | 0 | -0.573411 | -0.0595696 | 2.38094 |
| 131 | 134 | gap_skipped_bad_time | ISOLATED_BAD_TIME_GAP | 6.00429 | 7.10828 | -0.016 | 0.110792 | 0.0421971 | -0.0621033 |
| 134 | 135 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 1.99601e-06 | 1.99606e-06 | 0 | 0.1038 | -0.00313417 | -0.458145 |
| 137 | 138 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.6833e-06 | 0 | 0.360003 | 0.0183197 | 3.40855 |
| 141 | 142 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.33235e-06 | 0 | 0.0486947 | 0.045003 | -2.53679 |
| 142 | 143 | stage7b_warning | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 2e-06 | 2.68325e-06 | 0 | 0.0440244 | -0.0359061 | -2.08215 |
| 144 | 145 | stage7b_warning | TIME_GAP_REVIEW | 0.126661 | 0.157029 | -0.002 | -0.260073 | -0.0622523 | 2.68092 |

## CloudCompare Exports

| from | to | class | points | txt |
| --- | --- | --- | --- | --- |
| 52 | 53 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00052_00053_stage7b_warning.txt |
| 53 | 55 | ISOLATED_BAD_TIME_GAP | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00053_00055_gap_skipped_bad_time.txt |
| 65 | 66 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00065_00066_stage7b_warning.txt |
| 66 | 67 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00066_00067_stage7b_warning.txt |
| 72 | 74 | ISOLATED_BAD_TIME_GAP | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00072_00074_gap_skipped_bad_time.txt |
| 78 | 79 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00078_00079_stage7b_warning.txt |
| 81 | 82 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00081_00082_stage7b_warning.txt |
| 92 | 94 | ISOLATED_BAD_TIME_GAP | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00092_00094_gap_skipped_bad_time.txt |
| 102 | 103 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00102_00103_stage7b_warning.txt |
| 105 | 106 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00105_00106_stage7b_warning.txt |
| 112 | 114 | ISOLATED_BAD_TIME_GAP | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00112_00114_gap_skipped_bad_time.txt |
| 120 | 121 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00120_00121_stage7b_warning.txt |
| 131 | 134 | ISOLATED_BAD_TIME_GAP | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00131_00134_gap_skipped_bad_time.txt |
| 134 | 135 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00134_00135_stage7b_warning.txt |
| 137 | 138 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00137_00138_stage7b_warning.txt |
| 141 | 142 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00141_00142_stage7b_warning.txt |
| 142 | 143 | LIKELY_STAGE7B_EDGE_METRIC_ARTIFACT | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00142_00143_stage7b_warning.txt |
| 144 | 145 | TIME_GAP_REVIEW | 100000 | C:\proj_denoising_f3_2.0\qc\stage7c_ch1_ladm2_focused_seam_audit\cloudcompare_boundaries\stage7c_boundary_00144_00145_stage7b_warning.txt |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| STAGE7B_REVIEW_TARGETS | Use Stage 7B seam warnings and skipped bad-time gaps as focused audit targets | project_qc_rule | C:\proj_denoising_f3_2.0\qc\stage7b_ch1_ladm2_candidate_qc\stage7b_seam_qc_summary.csv | no, target selection only |
| POS_ENDPOINT_CONTINUITY | Check POS trajectory continuity at file boundaries | project_qc_rule | Stage 7A H5 POS match fields | no, QC only |
| EDGE_WINDOW_ROBUST_AUDIT | Compare robust first/last window distributions around target boundaries | project_qc_rule | Range-filtered and all POS-good Stage 7A H5 points | no, QC only |
| BOUNDARY_CLOUDCOMPARE_EXPORT | Export small boundary windows for manual CloudCompare inspection | project_qc_artifact | Focused per-boundary TXT files with both sides of the seam | no, visual QC only |

## Manual Check Rule

Open the exported boundary TXT files in CloudCompare and color by `source_seq` or `side_code`. The focused TXT files contain only the edge windows around the target boundaries; they do not replace the full Stage 7A TXT files.

## Stop Rule

Stage 7C does not modify Stage 7A H5/LAZ/TXT outputs and does not repair skipped bad-time files.
