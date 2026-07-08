# Stage 6I CH1 LADM-II Scan Geometry Diagnostic

## 结论

- Gate conclusion: 合理
- Reason: LADM-II 物理扫描几何在 00111 exact-time 复核中优于当前经验 f_body_frame_xyz()+6F 候选，且参数幅度受限。
- Replace production `f_body_frame_xyz()`: True

## PDF 4.4.2 Implementation

- Mirror normal in X'Y'Z': formulas 4-7 to 4-9.
- X'Y'Z' to sensor sXYZ: formula 4-10, searched near ±45 deg because current data/axis convention is not documented.
- Reflected beam direction: implemented as physical mirror reflection, equivalent to deriving φx, φy, φ, γ from formulas 4-11 to 4-14.
- sXYZ to current FRD: searched as an axis/sign mapping because current Stage 6 uses FRD-to-NED diagnostic rotation.

## Current 6F Baseline

- vector_rmse_m: 0.739072
- horizontal_rmse_m: 0.700499
- down_rmse_m: 0.235646

## Best Stage 6I Candidate

- angle_direction: `360-angle`
- angle_offset_deg: 298.900000
- mirror_tilt_deg: 7.750000
- frame_rotation_deg: -45.000000
- axis_mapping: `F=+Y,R=-X,D=-Z`
- boresight roll/pitch/yaw deg: 0.000000, -2.000000, 2.000000
- lever x/y/z m: 0.011067, -0.164929, 0.033791
- lever_norm_m: 0.168719
- vector_rmse_m: 0.284845
- horizontal_rmse_m: 0.159390
- down_rmse_m: 0.236075
- improvement_vs_stage6f_vector_pct: 61.459%
- improvement_vs_stage6f_horizontal_pct: 77.246%

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| CAO2017_LADM2_4_7_4_14 | LADM-II mirror normal and reflected beam scan geometry | doctoral_thesis | 曹彬才, 遥感测深数据处理方法研究, section 4.4.2, formulas 4-7 to 4-14 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6I LADM-II scan geometry candidate search | project_diagnostic_parameter | Exact-time comparison with existing L3 00111; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Coarse candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\coarse_candidates.csv`
- Local geometry candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\local_geometry_candidates.csv`
- Boresight candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\boresight_candidates.csv`
- Refined candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\refined_candidates.csv`
- Fine candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\fine_candidates.csv`
- Top full-eval candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\top_candidates_full_eval.csv`
- Best candidate JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\best_candidate.json`
- Scan-bin residual CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6i_ladm2_scan_geometry_diagnostic\scan_angle_bin_residuals.csv`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6i_ch1_ladm2_scan_geometry_diagnostic_report.json`

## Stop Rule

- 本阶段只诊断 PDF 4.4.2 / LADM-II 扫描几何，不覆盖 H5/LAZ。
- 只有当本阶段明确优于当前 6F，且参数幅度可解释时，才建议在后续阶段切换生产 `f_body_frame_xyz()`。
