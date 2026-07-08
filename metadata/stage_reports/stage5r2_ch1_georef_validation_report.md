# Stage 5R2 CH1 小样本坐标重算验证报告

## Gate Conclusion

- 结论：不合理
- 建议：接缝高程中位差超过 1 m；暂停，不能进入全量。
- 阶段：stage5r2_ch1_georef_sample
- 模式：range_00050_00100
- 处理通道：CH1

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted airborne LiDAR direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, diagnostic transform only |
| PROJECT_DIAGNOSTIC_PARAMETER | Stage 5G2 CH1 diagnostic return/zero/axis/attitude parameters | project_diagnostic_parameter | Stage 5G2 exact-time reference-L3 diagnostic; not final production calibration | yes, diagnostic transform only |
| EXACT_TIME_MATCH_QC | reference L3 exact GNSS time validation | project_qc_rule | Existing L3 reference GNSS_SEC and L1 GNSS_SEC_CH1 + 18 | no, QC only |
| PROJECT_DIAGNOSTIC_RETURN_POLICY | CH1 same-time far-return selection policy | project_diagnostic_parameter | Stage 5R2 range 00050-00100 diagnostic; not final production classification | yes, diagnostic return selection only |

## Diagnostic Parameters

- `lidar_time = GNSS_SEC_CH1 + 18`
- `zero_offset_candidate_m = 20.486969030907204`
- `min_far_range_m = 30`
- `return_policy = nearest_far`
- `angle_mode = 360-angle`
- `axis_mapping = forward=+body_x, right=+body_y, down=+body_z`
- `roll_sign = +1`, `pitch_sign = +1`, `heading_sign = -1`
- `heading_convention = heading+180`
- `rotation_order = YXZ`, `rotation_transpose = true`
- `height_median_bias_applied_m = 0`

## Key Statistics

- Input sequences: `50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100`
- Processed files: 51
- Total output points: 72,895,507
- Reference validation: N/A
- Max abs seam height edge median delta: 3.6880824964999306

## Outputs

- H5 directory: `outputs\h5_ch1\stage5r2_georef_sample`
- TXT directory: `outputs\txt_ch1\stage5r2_cloudcompare`
- QC directory: `outputs\qc\stage5r2_ch1_georef_validation`
- Preview HTML: `outputs\preview\stage5r2_range_00050_00100_nearest_far_merged_preview.html`

## Known Warnings

- height range contains large outliers
- height range contains large outliers
- time repaired by Stage 5 project repair model
- time repaired by Stage 5 project repair model
- height range contains large outliers
- height range contains large outliers
- height range contains large outliers
- height range contains large outliers
- height range contains large outliers
- time repaired by Stage 5 project repair model
- height range contains large outliers
- height range contains large outliers
- height range contains large outliers
- range mode is a stability screening segment; it is not full-production acceptance by itself.
- nearest_far is a diagnostic same-time return policy; it is not final production classification.

## Manual Checklist

- CloudCompare 中按第 4 列 `height_m` 着色。
- 检查是否仍有明显双层环状分层。
- 检查建筑、地面、道路/水岸形状是否比旧 v1/v2 更稳定。
- 本阶段通过前，不进入 CH2、去噪或 LAZ。
