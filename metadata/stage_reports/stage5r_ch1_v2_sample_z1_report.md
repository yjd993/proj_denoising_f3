# Stage 5R CH1 v2 小样本坐标候选报告

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：v2 仍存在局部重叠高差风险；若 CloudCompare 仍分层，需要进入 boresight/lever-arm/扫描角零位专题。
- 阶段：stage5r_ch1_v2_sample
- 零位策略：Z1
- 高程策略：global fixed empirical bias, no per-file median height bias

## Inputs and Outputs

- Summary CSV: `outputs\qc\stage5r_ch1_v2_sample\ch1_v2_sample_z1_summary.csv`
- Overlap CSV: `outputs\qc\stage5r_ch1_v2_sample\ch1_v2_sample_z1_overlap_height_consistency.csv`
- TXT manifest: `outputs\qc\stage5r_ch1_v2_sample\ch1_v2_sample_z1_txt_manifest.csv`
- First12 preview: `outputs\preview\stage5r_ch1_v2_z1_first12.html`
- Stable preview: `outputs\preview\stage5r_ch1_v2_z1_stable_00111_00115.html`
- H5 output root: `C:\proj_denoising_f3_2.0\0510_f30510_f3_data\outputs\h5_ch1\georef_v2_global_bias\z1`

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | GNSS/IMU assisted direct georeferencing model | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | yes, coordinate transform context |
| PROJ_UTM_002 | UTM to lon/lat projection conversion | official_documentation | PROJ / pyproj official documentation | yes, coordinate conversion |
| PROJECT_EMPIRICAL_PARAMETER | time offset, time repair, axis mapping, fixed CH1 zero offset, global height bias | project_empirical_parameter | Project data diagnosis; must not be described as a published algorithm | yes, explicitly marked empirical transform parameters |
| STRIP_QC_009 | overlap / strip consistency QC | peer_reviewed_conference | Filin & Vosselman, ISPRS 2004 | no, QC only |

## Parameters

- lidar time offset: 18.0 s
- zero strategy: Z1
- min support count for Z2: 1000
- global height bias: 6.036329451805429 m
- range minimum for georeference: 30.0 m
- overlap cell size: 1.0 m
- TXT is CH1 numeric-only; columns are documented in `outputs\qc\stage5r_ch1_v2_sample\ch1_v2_sample_z1_txt_manifest.csv`.

## Key Statistics

- Files requested: 18
- Files processed: 18
- Files skipped: 0
- Median overlap abs median dz: 0.607927070038639
- Max overlap abs median dz: 24.587705084458435

## Known Warnings

- 本阶段是 v2 小样本候选，不覆盖 Stage 5 v1、raw、light denoised。
- 固定零位和 global height bias 均为 `PROJECT_EMPIRICAL_PARAMETER`。
- 本阶段不做去噪、不删点、不做最终 LAS/LAZ。

## Manual Checklist

- CloudCompare 打开 first12 TXT，检查你之前框出的分层是否明显减少。
- CloudCompare 打开 00111-00115 TXT，检查稳定段是否没有变差。
- 查看 `overlap_height_consistency.csv`，重点看 `abs_dz_median_m`。
- 若 first12 改善但仍异常，标记起飞段风险，不直接进入最终成果。
- 若稳定段变差，停止并改查 boresight/lever-arm/扫描角零位。

## Gate Rule

Stop here. Do not run full CH1 v2 until this small-sample result is manually accepted.
