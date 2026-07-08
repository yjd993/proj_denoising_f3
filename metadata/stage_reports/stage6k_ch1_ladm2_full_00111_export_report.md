# Stage 6K CH1 LADM-II Full 00111 Export

## 结论

- Gate conclusion: 合理
- Reason: 00111 full-point LADM-II diagnostic export completed and exact-time QC still matches Stage 6J accuracy.
- Full-point H5 ready: True

## Full-Point Output

- L1 CH1 point count: 2,326,241
- H5 point count: 2,326,241
- `range_m > 30 m` count: 1,540,533
- POS success rate: 100.000000%
- Height median/min/max m: 15.340969, -140.501626, 124.867294

## Exact-Time QC

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| current Stage 6F | 0.739072 | 0.700499 | 0.235646 | 0.023996, 0.046370, 0.000190 |
| Stage 6K LADM-II | 0.284845 | 0.159390 | 0.236075 | 0.021465, -0.012529, 0.023309 |

- vector_improvement_vs_stage6f_pct: 61.459%
- horizontal_improvement_vs_stage6f_pct: 77.246%

## Applied LADM-II Candidate

- angle_direction: `360-angle`
- angle_offset_deg: 298.9
- mirror_tilt_deg: 7.75
- frame_rotation_deg: -45.0
- axis_mapping: `F=+Y,R=-X,D=-Z`
- boresight roll/pitch/yaw deg: 0.0, -2.0, 2.0
- lever x/y/z m: 0.011067, -0.164929, 0.033791

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| CAO2017_LADM2_4_7_4_14 | LADM-II mirror normal and reflected beam scan geometry | doctoral_thesis | 曹彬才, 遥感测深数据处理方法研究, section 4.4.2, formulas 4-7 to 4-14 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6K LADM-II full 00111 diagnostic export | project_diagnostic_parameter | Stage 6I best candidate applied to all CH1 L1 points in 00111 | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Full diagnostic H5: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6k_ladm2_full_00111_export\stage6k_00111_ladm2_full_points.h5`
- CloudCompare TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6k_ladm2_full_00111_export\stage6k_00111_ladm2_full_points_cloudcompare.txt`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6k_ch1_ladm2_full_00111_export_report.json`

## Stop Rule

- 本阶段只导出 `00111` 全点诊断 H5/TXT，不覆盖旧 H5/LAZ，不跑连续段。
- 下一步建议先检查 CloudCompare，再做连续小段 Stage 6L。
