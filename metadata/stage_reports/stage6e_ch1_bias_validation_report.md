# Stage 6E CH1 Bias Validation

## 结论

- Gate conclusion: 合理
- Reason: 固定平移能解释主要系统偏差；进入 Stage 6F 检查其是否可由 body/FRD 杆臂和小安置角解释。
- Recommendation: Run Stage 6F next; do not run Stage 6G until Stage 6F is analyzed.

## Fixed Parameters

- zero_offset_m: 20.49460272584239
- angle_direction: `360-angle`
- angle_offset_deg: 1.0
- roll_sign / pitch_sign / heading_sign: 1, 1, -1
- heading_convention: `heading+180`
- rotation_order: `YXZ`
- rotation_transpose: True
- diagnostic bias correction N/E/D m: [1.5006186931180263, -0.6625962236673231, -0.3428576246215087]

## Key Metrics

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| raw Stage 6D fixed | 1.817066 | 1.753433 | 0.476657 | -1.500619, 0.662596, 0.342858 |
| bias corrected | 0.808300 | 0.723938 | 0.359531 | -0.000000, -0.000000, 0.000000 |

- vector_rmse_improvement_m: 1.008767
- vector_rmse_improvement_pct: 55.516%
- horizontal_rmse_improvement_m: 1.029496

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6D rotation/scan/range-zero plus Stage 6E fixed bias diagnostic | project_diagnostic_parameter | Exact-time comparison with existing L3 00111; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Scan-bin residual CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6e_bias_validation\scan_angle_bin_residuals.csv`
- Raw CloudCompare TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6e_bias_validation\stage6e_00111_raw_stage6d_fixed_cloudcompare.txt`
- Bias-corrected CloudCompare TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6e_bias_validation\stage6e_00111_bias_corrected_cloudcompare.txt`
- Reference CloudCompare TXT: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6e_bias_validation\stage6e_00111_reference_l3_cloudcompare.txt`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6e_ch1_bias_validation_report.json`

## Stop Rule

- 本阶段只验证固定平移，不生成最终点云，不覆盖 H5/LAZ。
- 固定平移仍是 `PROJECT_DIAGNOSTIC_PARAMETER`，只能用于判断是否继续 Stage 6F。
