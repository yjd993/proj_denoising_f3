# Stage 6F CH1 Boresight / Lever Diagnostic

## 结论

- Gate conclusion: 基本合理但有风险
- Reason: Stage 6F 参数幅度可接受，但相对 Stage 6E 改善不足 10%；是否进入 6G 需要人工判断。
- Recommend Stage 6G: False

## Best Candidate

- boresight roll/pitch/yaw deg: 0.000000, -1.250000, 0.500000
- lever x/y/z m: 0.529737, 0.072071, -0.127186
- lever_norm_m: 0.549538
- boresight_abs_max_deg: 1.250000

## Key Metrics

| state | vector_rmse_m | horizontal_rmse_m | down_rmse_m | median N/E/D m |
|---|---:|---:|---:|---|
| Stage 6D fixed no boresight/lever | 1.817066 | 1.753433 | 0.476657 | -1.500619, 0.662596, 0.342858 |
| Stage 6F best | 0.739072 | 0.700499 | 0.235646 | 0.023996, 0.046370, 0.000190 |

- stage6e_bias_vector_rmse_m: 0.808300
- improvement_vs_stage6e_bias_pct: 8.565%
- improvement_vs_stage6d_fixed_pct: 59.326%

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 6F body/FRD boresight and lever-arm diagnostic search | project_diagnostic_parameter | Exact-time comparison with existing L3 00111; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | Reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |

## Outputs

- Coarse candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f_boresight_lever_diagnostic\coarse_candidates.csv`
- Local candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f_boresight_lever_diagnostic\local_candidates.csv`
- Top full-eval candidates: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f_boresight_lever_diagnostic\top_candidates_full_eval.csv`
- Scan-bin residual CSV: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f_boresight_lever_diagnostic\scan_angle_bin_residuals.csv`
- Best candidate JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\qc\stage6f_boresight_lever_diagnostic\best_candidate.json`
- Report JSON: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\metadata\stage_reports\stage6f_ch1_boresight_lever_diagnostic_report.json`

## Stop Rule

- 本阶段只提交 6F 诊断结果，不执行 Stage 6G。
- 所有 boresight/lever 参数仍是 `PROJECT_DIAGNOSTIC_PARAMETER`，不能直接作为最终生产定标。
