# Stage 6J CH1 LADM-II Diagnostic Export

## 结论

- Gate conclusion: 合理
- Reason: Stage 6J diagnostic export reproduces Stage 6I accuracy and is suitable for CloudCompare inspection.
- CloudCompare inspection ready: True

## Metrics

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| current Stage 6F | 0.739072 | 0.700499 | 0.235646 | 0.023996, 0.046370, 0.000190 |
| Stage 6J LADM-II | 0.284845 | 0.159390 | 0.236075 | 0.021465, -0.012529, 0.023309 |

- vector_improvement_vs_stage6f_pct: 61.459%
- horizontal_improvement_vs_stage6f_pct: 77.246%

## Applied Stage 6I Candidate

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
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6J LADM-II diagnostic export for CloudCompare/H5 review | project_diagnostic_parameter | Stage 6I best candidate applied to exact-time existing L3 00111 comparison | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Diagnostic H5: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6j_ladm2_diagnostic_export\stage6j_00111_ladm2_exact_time_diagnostic.h5`
- Prediction TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6j_ladm2_diagnostic_export\stage6j_00111_ladm2_prediction_cloudcompare.txt`
- Reference TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6j_ladm2_diagnostic_export\stage6j_00111_reference_l3_cloudcompare.txt`
- Merged TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6j_ladm2_diagnostic_export\stage6j_00111_prediction_reference_merged_cloudcompare.txt`
- Scan-bin CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6j_ladm2_diagnostic_export\scan_angle_bin_residuals.csv`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6j_ch1_ladm2_diagnostic_export_report.json`

## Stop Rule

- 本阶段只导出 00111 exact-time 诊断点，不覆盖旧 H5/LAZ，不执行连续段。
- 生产替换前还需要人工看 CloudCompare，并单独做 Stage 6K/6L 连续段验证。
