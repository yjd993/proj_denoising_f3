# Stage 6H CH1 Body-Frame Scan Geometry Diagnostic

## 结论

- Gate conclusion: 合理
- Reason: FRD/body 分解显示残差主要为横向方向误差，物理方向余弦/角度模型在验证集上显著改善。
- Recommendation: Do not run Stage 6G automatically; next step should implement or test a physical scan-geometry replacement for f_body_frame_xyz.

## Body-Frame Residual Decomposition

- total_correction_rms_m: 0.739072
- radial_rms_m: 0.295578
- transverse_rms_m: 0.677393
- radial_energy_pct: 15.994%
- transverse_energy_pct: 84.006%
- instant_angle_energy_explained_pct: 2.756%
- delta_angle_rmse_deg: 0.322950
- delta_angle_p90_abs_deg: 0.520319

## Best Body Model

- model_name: `full_m_fourier_order_4`
- model_type: `full_m`
- validation_vector_rmse: 0.747732 -> 0.271387 m
- validation_horizontal_rmse: 0.699853 -> 0.073563 m
- validation_horizontal_improvement_pct: 89.489%
- full_vector_rmse: 0.739072 -> 0.246355 m

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6H body-frame scan-geometry residual diagnostic models | project_diagnostic_parameter | Exact-time comparison with existing L3 00111; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Model summary CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6h_body_scan_geometry_diagnostic\model_summary.csv`
- Best model JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6h_body_scan_geometry_diagnostic\best_body_scan_model.json`
- Scan-bin decomposition CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6h_body_scan_geometry_diagnostic\scan_angle_body_decomposition_before_after.csv`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6h_ch1_body_scan_geometry_diagnostic_report.json`

## Stop Rule

- 本阶段只做 body/FRD 扫描几何诊断，不执行 Stage 6G，不覆盖 H5/LAZ。
- 如果采用本阶段结果，下一步应修改或重建 `f_body_frame_xyz()` / PDF 4.4.2 扫描几何，而不是把经验补偿直接全量应用。
