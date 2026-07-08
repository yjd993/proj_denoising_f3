# Stage 6L CH1 LADM-II Continuous Segment Diagnostic

## 结论

- Gate conclusion: 合理
- Reason: Continuous segment export completed with full POS coverage and no large time gap at file seams.
- Continuous segment H5 ready: True

## Segment

- Selected files: `00114` to `00118`
- File count: 5
- Sample limited: False
- Total points written to H5: 11,546,156
- Total `range_m > 30 m` points: 7,668,718

## Applied LADM-II Candidate

- angle_direction: `360-angle`
- angle_offset_deg: 298.9
- mirror_tilt_deg: 7.75
- frame_rotation_deg: -45.0
- axis_mapping: `F=+Y,R=-X,D=-Z`
- boresight roll/pitch/yaw deg: 0.0, -2.0, 2.0
- lever x/y/z m: 0.011067, -0.164929, 0.033791

## Per-File Summary

| seq | H5 points | range_gt_min | POS success | height median m | gps time sec |
|---:|---:|---:|---:|---:|---|
| 114 | 2,329,228 | 1,542,408 | 100.000000% | 15.403 | 40220.905574-40223.906686 |
| 115 | 2,328,409 | 1,540,625 | 100.000000% | 15.330 | 40223.906688-40226.908655 |
| 116 | 2,254,465 | 1,495,328 | 100.000000% | 15.303 | 40226.908657-40229.889371 |
| 117 | 2,320,568 | 1,546,528 | 100.000000% | 15.247 | 40229.889373-40232.911807 |
| 118 | 2,313,486 | 1,543,829 | 100.000000% | 15.294 | 40232.911809-40235.913565 |

## Seam Summary

| seam | valid | endpoint dt sec | endpoint horizontal m | centroid horizontal m | median height delta m |
|---|---|---:|---:|---:|---:|
| 114->115 | True | 0.000002000 | 0.057 | 14.770 | 0.020 |
| 115->116 | True | 0.000002000 | 0.005 | 20.913 | -0.112 |
| 116->117 | True | 0.000002000 | 0.057 | 21.472 | -0.061 |
| 117->118 | True | 0.000002000 | 0.004 | 16.837 | -0.327 |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| CAO2017_LADM2_4_7_4_14 | LADM-II mirror normal and reflected beam scan geometry | doctoral_thesis | Cao 2017 section 4.4.2, formulas 4-7 to 4-14 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6L LADM-II continuous segment diagnostic | project_diagnostic_parameter | Stage 6I best candidate applied to a short continuous CH1 L1 segment after 00111 | yes, diagnostic transform only |
| CONTINUITY_QC | Continuous file seam and POS coverage diagnostics | project_qc_rule | Per-file time coverage, POS confidence flags, coordinate ranges, and file-to-file seam statistics | no, QC only |

## Outputs

- Per-file summary CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6l_ladm2_continuous_segment\per_file_summary.csv`
- Seam summary CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6l_ladm2_continuous_segment\seam_summary.csv`
- CloudCompare TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6l_ladm2_continuous_segment\stage6l_00114_00118_ladm2_segment_cloudcompare.txt`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6l_ch1_ladm2_continuous_segment_diagnostic_report.json`

## Stop Rule

- 本阶段只处理 00111 后面的小连续段，不覆盖旧 H5/LAZ。
- 这些 H5/TXT 仍是诊断输出，不能直接作为最终生产 L3。
