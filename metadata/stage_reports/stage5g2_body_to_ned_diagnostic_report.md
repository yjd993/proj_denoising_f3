# Stage 5G2 CH1 Body->NED 几何模型诊断报告

## Gate Conclusion

- 结论：合理
- 建议：候选模型在参考 L3 exact-time 匹配点上通过诊断阈值；暂停，人工确认后才规划 Stage 5R2 小样本重算。
- 阶段：stage5g2_ch1_body_to_ned_diagnostic
- 处理通道：CH1
- 参考 L3：`0510_f3\L3_DATA\L2_cap_00111_20260510190957.h5`
- 样例 L1：`0510_f3\L1-TIME_ANGE_DIST_DATA\L1_cap_00111_20260510190957.h5`
- LIDAR 时间：`GNSS_SEC_CH1 + 18`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing diagnostic | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | no, diagnostic only |
| PROJECT_DIAGNOSTIC_PARAMETER | candidate axis/sign/angle/attitude/boresight/lever-arm conventions | project_diagnostic_parameter | Project diagnostic candidates only; not final calibration | no, diagnostic only |
| EXACT_TIME_MATCH_QC | exact GNSS time intersection against existing L3 reference | project_qc_rule | Existing project L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, diagnostic only |

## Inputs And Sampling

- L1 total points: 2,326,241
- Exact matched points before cap: 1,490,688
- Matched points loaded: 100,000
- L1 return match strategy: `far_return_refnorm`
- Minimum far-return range: 30 m
- Median diagnostic zero from reference norm: 20.486969 m
- Median L1 return candidates per reference point: 2.000
- Far-return availability rate: 100.000000%
- Search sample points: 5,000
- Robust statistic sample points: 1,000
- Boresight/lever sample points: 0
- POS time corrections: 0

## Candidate Coverage

- Range/scan zero strategies: `NONE, Z0_auto, Z1_fixed_calib_zero_offset, Z2_ref_norm_median_zero`
- Angle modes: `360-angle, angle, angle+180, 180-angle`
- Body axis mappings: all 48 permutations/sign combinations to `forward/right/down`
- Attitude candidates: roll/pitch/heading signs, heading conventions, rotation orders, transpose/non-transpose
- Coarse candidates evaluated: 184,320
- Final coarse candidates re-evaluated: 200
- Boresight/lever candidates evaluated: 0

## Best Candidate

```json
{
  "candidate_stage": "coarse",
  "zero_strategy": "Z2_ref_norm_median_zero",
  "angle_mode": "360-angle",
  "zero_used_m": 20.486969030907204,
  "axis_mapping": "forward=+body_x;right=+body_y;down=+body_z",
  "roll_sign": 1,
  "pitch_sign": 1,
  "heading_sign": -1,
  "heading_convention": "heading+180",
  "rotation_order": "YXZ",
  "rotation_transpose": true,
  "boresight_roll_deg": 0.0,
  "boresight_pitch_deg": 0.0,
  "boresight_yaw_deg": 0.0,
  "boresight_abs_max_deg": 0.0,
  "lever_x_m": 0.0,
  "lever_y_m": 0.0,
  "lever_z_m": 0.0,
  "lever_norm_m": 0.0,
  "sample_points_used": 100000,
  "north_rmse_m": 1.6010945489748714,
  "east_rmse_m": 0.8854743532738272,
  "down_rmse_m": 0.4793640891644698,
  "north_median_error_m": -1.507915228920775,
  "east_median_error_m": 0.6645412989088522,
  "down_median_error_m": 0.36110688445947403,
  "north_mad_m": 0.6125297725405687,
  "east_mad_m": 0.6100366594628044,
  "down_mad_m": 0.24744706001890648,
  "north_p90_abs_error_m": 2.317693247229146,
  "east_p90_abs_error_m": 1.4391252620652808,
  "down_p90_abs_error_m": 0.6538946633427927,
  "vector_rmse_m": 1.891390629944868,
  "north_rmse_bias_removed_m": 0.6323319414290026,
  "east_rmse_bias_removed_m": 0.6324357642184496,
  "down_rmse_bias_removed_m": 0.35758763744713734,
  "vector_rmse_bias_removed_m": 0.9631654055607309,
  "northing_rmse_m": 1.6010945489748714,
  "easting_rmse_m": 0.8854743532738272,
  "height_rmse_m": 0.4793640891644698,
  "height_median_error_m": -0.36110688445947403
}
```

## Key Outputs

- Candidate summary: `outputs\qc\stage5g2_body_to_ned\candidate_summary.csv`
- Top candidates: `outputs\qc\stage5g2_body_to_ned\top_candidates.csv`
- Boresight candidates: `outputs\qc\stage5g2_body_to_ned\boresight_candidates.csv`
- Best candidate JSON: `outputs\qc\stage5g2_body_to_ned\best_candidate.json`

## Warnings

- 本阶段只做诊断，不生成最终点云，不写 `outputs/h5_ch1`、`outputs/h5_merged` 或 `outputs/laz`。
- 所有轴向、符号、角度、boresight、lever-arm 都是 `PROJECT_DIAGNOSTIC_PARAMETER`，不能当作最终算法。
- 默认先用搜索样本筛选候选，再对前排候选做较大样本复核；这是为了避免全候选在 100000 点上运行过慢。
- `Z2_ref_norm_median_zero` 是利用已有参考 L3 offset 模长估计的诊断零位，只能作为问题定位线索，不能直接作为最终量产算法。
- 不使用逐文件 height median bias。
