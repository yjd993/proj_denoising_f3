# Stage 7D CH1 LADM-II Teacher Review Package

## Final Decision

- Conclusion: DISPLAY_CANDIDATE_APPROVED_WITH_NOTES
- Ready for teacher review: True
- Reason: 95 Stage 7A files are approved as display candidates; 6 bad-time files remain excluded; 00144-00145 time gap is documented as a note.

## One-Sentence Result

Sequences `00050-00150` produced 95 CH1 LADM-II Stage 7A display-candidate H5/LAZ/TXT files; the six bad-time files remain excluded, and the only remaining focused boundary note `00144-00145` shows a 0.12666 s time gap but no obvious CloudCompare geometry jump.

## Method Chain

1. L1 raw CH1 timing/range/scan fields are read from the source H5 files.
2. The old empirical `f_body_frame_xyz()` route is not used for the display candidate.
3. LADM-II scan geometry from Cao 2017 section 4.4.2 is used as the Stage 7A geometry basis, with the Stage 6I/6K selected candidate parameters.
4. Each Stage 7A H5 stores the full diagnostic chain: L1 timing/range/scan, L2 FRD coordinates, POS interpolation fields, NED offsets, and final UTM/geographic coordinates.
5. LAZ/TXT exports are generated from the same Stage 7A candidate points for CloudCompare review.

## Scope

- Input/output root: `C:\proj_denoising_f3_2.0`
- Sequence range: `00050-00150`
- Display candidate files: 95
- Excluded bad-time files: 6 (`00054`, `00073`, `00093`, `00113`, `00132`, `00133`)
- Total H5 points: 217,000,065
- Total LAZ points: 179,717,052
- Total TXT points: 179,717,052

## QC Summary

| section | metric | value | unit | decision |
| --- | --- | --- | --- | --- |
| geometry_model | Stage 6I LADM-II improvement vs Stage 6F vector RMSE | 61.4591 | % | supports LADM-II replacement |
| geometry_model | Stage 6I LADM-II improvement vs Stage 6F horizontal RMSE | 77.2462 | % | supports LADM-II replacement |
| exact_time_reference | Stage 6K exact-time gate | 合理 |  | 00111 full-point LADM-II diagnostic export completed and exact-time QC still matches Stage 6J accuracy. |
| continuous_segment | Stage 6N 00114-00118 seam warnings | 0 | count | PASS |
| stage7a_output | Processed display candidate files | 95 | files | 95 Stage 7A outputs are display candidates |
| stage7a_output | Skipped bad-time files | 6 | files | excluded and documented |
| stage7a_output | Total H5 points | 217000065 | points | full candidate H5 outputs exist |
| stage7b_schema_pos | Files missing full-chain H5 fields | 0 | files | 0 means H5 chain is complete |
| stage7b_schema_pos | Minimum POS success rate | 1 | ratio | POS matching is complete for processed files |
| stage7b_schema_pos | Max POS interpolation dt p99 | 0.00247536 | s | POS interpolation timing is stable |
| stage7c_focused_audit | Stage 7B warning boundaries explained as edge-metric artifacts | 12 | boundaries | not geometry failures |
| stage7c_focused_audit | Isolated bad-time gaps | 5 | boundaries | kept out of geometry judgment |
| manual_review | 00144-00145 CloudCompare focused review | PASS |  | time gap noted; no obvious geometric jump |

## Key CloudCompare Screenshot Checklist

| id | priority | stage | color | status | goal |
| --- | --- | --- | --- | --- | --- |
| S1 | required | Stage 6K | height_m or scalar height | to_capture | Show that LADM-II model matches the validated 00111 reference area. |
| S2 | required | Stage 7A | height_m | to_capture | Show a representative full-point Stage 7A TXT output. |
| S3 | required | Stage 7A continuous segment | source/file color or height_m | to_capture | Show continuity across the previously inspected representative segment. |
| S4 | required | Stage 7C focused seam | source_seq or side_code | visually_passed | Document the only remaining time-gap review boundary. |
| S5 | optional | Stage 7C focused seam | source_seq or side_code | optional | Show a Stage 7B warning that Stage 7C explained as edge/window artifact. |

## Important Notes For Teacher

- `00113` and other bad-time files are not repaired in this stage and are not mixed into geometry judgment.
- Stage 7B automatic QC intentionally flagged seam warnings conservatively.
- Stage 7C focused audit explained 12 Stage 7B warnings as edge/window metric artifacts and kept 5 bad-time gaps isolated.
- Manual CloudCompare review of `00144-00145` found no obvious horizontal offset, vertical step, strip break, or distortion, so the 0.12666 s time gap is retained as a note rather than a geometry failure.
- These outputs are display-candidate products, not the final all-file production release.

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| CAO2017_LADM2_4_7_4_14 | LADM-II scan geometry based on Cao 2017 section 4.4.2 | doctoral_thesis_and_project_diagnostic | Stage 6I/6K selected and validated the LADM-II geometry candidate | yes, Stage 7A candidate transform |
| STAGE7A_CANDIDATE_BATCH | Limited CH1 LADM-II candidate batch | project_output | C:\proj_denoising_f3_2.0, sequences 00050-00150 | yes, candidate H5/LAZ/TXT output |
| STAGE7B_7C_QC | Automatic continuity QC plus focused seam audit | project_qc_rule | Stage 7B automatic QC and Stage 7C focused boundary audit | no, QC only |
| MANUAL_CLOUDCOMPARE_REVIEW | Manual CloudCompare review for 00144-00145 focused boundary | manual_visual_qc | User visual inspection: no obvious horizontal offset, vertical step, strip break, or distortion | no, release decision evidence |

## Package Outputs

- Teacher summary: `C:\proj_denoising_f3_2.0\stage7d_teacher_package\stage7d_teacher_summary.md`
- QC summary CSV: `C:\proj_denoising_f3_2.0\stage7d_teacher_package\stage7d_qc_summary.csv`
- Display candidate manifest: `C:\proj_denoising_f3_2.0\stage7d_teacher_package\stage7d_display_candidate_manifest.csv`
- Excluded files CSV: `C:\proj_denoising_f3_2.0\stage7d_teacher_package\stage7d_excluded_bad_time_files.csv`
- Screenshot checklist CSV: `C:\proj_denoising_f3_2.0\stage7d_teacher_package\stage7d_cloudcompare_screenshot_checklist.csv`
- Release decision JSON: `C:\proj_denoising_f3_2.0\stage7d_teacher_package\stage7d_release_decision.json`
