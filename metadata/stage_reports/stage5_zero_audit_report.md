# Stage 5Z CH1 零位返查报告

## Gate Conclusion

- 结论：不合理
- 建议：当前自动 zero_peak 支持点不足，建议先用固定 calib zero_offset 生成 Stage 5R 小样本候选，不要继续使用 v1 坐标。
- 阶段：stage5z_ch1_zero_audit
- 处理通道：CH1
- 审计范围：sample files

## Inputs and Outputs

- L1 source: `0510_f3\L1-TIME_ANGE_DIST_DATA`
- Calibration: `untitled\calib_coeffs.mat`
- Stage 5 v1 summary: `outputs\qc\stage5_file_summary.csv`
- Audit CSV: `outputs\qc\stage5_zero_audit\ch1_zero_peak_audit.csv`
- First12 preview: `outputs\preview\stage5_zero_audit_first12.html`
- Stable preview: `outputs\preview\stage5_zero_audit_stable_00111_00115.html`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | direct georeferencing / range offset audit context | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | no, audit only |
| STRIP_QC_009 | overlap / strip consistency QC | peer_reviewed_conference | Filin & Vosselman, ISPRS 2004 | no, audit only |
| PROJECT_QC_RULE | zero peak support count and warning thresholds | project_qc_rule | Project-specific diagnostic threshold; not a deletion or transformation algorithm | no |

## Parameters

- calib zero_offset CH1: 18.802278358296036 m
- zero support range: 0-20 m
- min support count: 1000
- near peak half width: 0.5 m
- zero peak vs calib warning threshold: 1.0 m
- overlap cell size: 1.0 m
- overlap max sampled points per file: 400000

## Key Statistics

- Files audited: 18
- Low zero-support files: 18
- Fixed zero-offset recommended files: 18
- Median overlap abs median dz: 7.14502728193926
- Max overlap abs median dz: 19.872959252600328

## Worst Overlap DZ Before

- seq 6 -> 7: abs median dz = 19.873 m, common cells = 465
- seq 8 -> 9: abs median dz = 10.619 m, common cells = 849
- seq 11 -> 12: abs median dz = 10.065 m, common cells = 1736
- seq 7 -> 8: abs median dz = 9.900 m, common cells = 764
- seq 13 -> 14: abs median dz = 8.111 m, common cells = 1779
- seq 5 -> 6: abs median dz = 7.849 m, common cells = 344
- seq 12 -> 13: abs median dz = 7.598 m, common cells = 930
- seq 112 -> 113: abs median dz = 7.442 m, common cells = 1257
- seq 111 -> 112: abs median dz = 6.848 m, common cells = 1155
- seq 9 -> 10: abs median dz = 4.658 m, common cells = 1528

## Known Warnings

- 本阶段只做 QC 统计，不删点、不改坐标。
- `zero_peak_support_count_0_20m` 太低时，自动 zero_peak 不可信。
- `PROJECT_QC_RULE` 不是论文算法，只用于人工 gate。
- Stage 5 v1 的逐文件 height median bias 不作为最终坐标修正依据。

## Manual Checklist

- 检查 `zero_peak_support_count_0_20m` 是否普遍过低。
- 检查 `zero_peak_detected_m` 是否相对 `calib_zero_offset_m` 大幅跳变。
- 检查 first12 preview 是否仍存在明显分层。
- 检查 stable 00111-00115 preview 是否相对连续。
- 决定是否运行 Stage 5R 小样本：推荐先用 `Z1 fixed_calib_zero_offset`。

## Gate Rule

Stop here. Do not run full CH1 v2, CH2, joint denoise, or LAZ until this zero audit is manually accepted.
