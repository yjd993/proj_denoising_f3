# Stage 6F2 CH1 Scan-Angle Residual Diagnostic

## 结论

- Gate conclusion: 合理
- Reason: 扫描角残差模型在验证集上显著改善，剩余误差主要呈扫描角相关结构。
- Recommend next: Do not run Stage 6G automatically; use this report to decide whether to implement a physical scan-geometry correction.

## Best Residual Model

- model_name: `fourier_order_4`
- model_type: `fourier`
- validation_vector_rmse: 0.747732 -> 0.270721 m
- validation_vector_improvement_pct: 63.794%
- validation_horizontal_rmse: 0.699853 -> 0.070597 m
- full_vector_rmse: 0.739072 -> 0.245700 m

## Fixed Upstream Parameters

- Uses Stage 6F best boresight/lever from `outputs\qc\stage6f_boresight_lever_diagnostic\best_candidate.json`
- zero_offset_m: 20.49460272584239
- angle_direction: `360-angle`
- angle_offset_deg: 1.0
- rotation_order: `YXZ`, transpose: True

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6F2 scan-angle residual diagnostic correction models | project_diagnostic_parameter | Exact-time comparison with existing L3 00111; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Model summary CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f2_scan_angle_residual_diagnostic\model_summary.csv`
- Best model JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f2_scan_angle_residual_diagnostic\best_scan_angle_residual_model.json`
- Scan-bin before/after CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f2_scan_angle_residual_diagnostic\scan_angle_bin_before_after.csv`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6f2_ch1_scan_angle_residual_diagnostic_report.json`

## Stop Rule

- 本阶段只诊断扫描角残差，不执行 Stage 6G，不覆盖 H5/LAZ。
- residual correction 是 `PROJECT_DIAGNOSTIC_PARAMETER`，不能直接作为最终生产模型。
