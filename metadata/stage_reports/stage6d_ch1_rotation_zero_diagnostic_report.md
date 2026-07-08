# Stage 6D CH1 Rotation / Scan Angle / Range Zero Diagnostic

## 结论

- Gate conclusion: 基本合理但有风险
- Reason: 候选接近参考 L3，但仍存在米级水平或扫描角相关残差。

## Scope

- 只处理 CH1 `00111` 与已有 L3 精确时间匹配点。
- 传感器坐标仍使用 `f_body_frame_xyz()`。
- 安置角、偏心分量、boresight、lever-arm 全部固定为 0，不参与搜索。
- 本阶段只诊断 heading/roll/pitch 旋转约定、扫描角方向/零位、range zero offset。
- 不生成最终点云，不覆盖 H5/LAZ。

## Best Candidate

- zero_mode: `estimated`
- zero_offset_m: 20.49460272584239
- angle_direction: `360-angle`
- angle_offset_deg: 1.0
- roll_sign: 1
- pitch_sign: 1
- heading_sign: -1
- heading_convention: `heading+180`
- rotation_order: `YXZ`
- rotation_transpose: True
- vector_rmse_m: 1.8170664459454733
- horizontal_rmse_m: 1.7534332971844444
- down_rmse_m: 0.47665725768711503
- median residual N/E/D m: -1.5006186931180263, 0.6625962236673231, 0.3428576246215087
- bias_removed_vector_rmse_m: 0.8082996156737805

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Heading/roll/pitch convention, scan-angle direction/zero, and range-zero diagnostic grid | project_diagnostic_parameter | Exact-time comparison with existing L3 00111; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |


## Outputs

- Candidate summary: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6d_rotation_zero_diagnostic\candidate_summary_search_sample.csv`
- Top candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6d_rotation_zero_diagnostic\top_candidates_full_eval.csv`
- Best candidate JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6d_rotation_zero_diagnostic\best_candidate.json`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6d_ch1_rotation_zero_diagnostic_report.json`

## Manual Check

- 如果 best candidate 仍有明显 N/E 固定偏差，说明还需要后续整体平移或杆臂/安装参数诊断。
- 如果 bias-removed RMSE 明显低于 raw RMSE，说明固定平移占较大比例。
- 如果所有候选 RMSE 仍较大，说明问题不只在本阶段三类参数，需回到 `f_body_frame_xyz()` 或回波匹配/滤波模型。
