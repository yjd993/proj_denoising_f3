# Stage B CH1 轻度去噪报告

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：CH1 轻度去噪完成；建议人工查看去噪前后形态后再进入 CH2。

## Inputs and Outputs

- Input raw directory: `outputs\h5_ch1\raw`
- Output light denoised directory: `C:\proj_denoising_f3_2.0\0510_f30510_f3_data\outputs\h5_ch1\light_denoised`
- Summary CSV: `outputs\qc\ch1_light_denoise_summary.csv`
- Output index CSV: `outputs\qc\ch1_light_denoise_output_index.csv`
- Progress JSON: `outputs\qc\ch1_light_denoise_progress.json`
- Preview HTML: `outputs\preview\ch1_light_denoised_overview.html`
- Input files: 446
- Output/reused files: 446
- Files skipped by 3% delete-ratio gate: 0

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| SOR_003 | Statistical Outlier Removal | official_documentation | PCL StatisticalOutlierRemoval documentation | yes |
| ROR_004 | Radius Outlier Removal | official_documentation | Open3D / PDAL official documentation | no, disabled in this run |

## Parameters

- SOR mean_k: 12
- SOR std_multiplier: 3.0
- ROR enabled: False
- ROR radius_m: 1.0
- ROR min_neighbors: 2
- Max delete ratio per file: 3.00%
- Query chunk size: 100,000

## Key Statistics

- Point count before: 656,367,796
- Point count after: 648,042,458
- Deleted count: 8,325,338
- Delete ratio: 1.268395%
- Skipped files: 0
- Elapsed minutes: 21.17

## QC Observation Only

- 高程极值、稀疏区域、水体疑似区域、时间修复文件附近异常仅作为人工检查统计，不作为自动删点依据。
- 本阶段没有使用自定义高程分位数删点、网格过滤、人工经验阈值删点。

## Known Warnings

- 无

## Files Requiring Manual Decision

- 无

## Manual Checklist

- 建筑边缘是否保留。
- 屋顶细节是否保留。
- 飞点是否减少。
- 删除比例是否可接受。
- 是否继续 CH2。

## Gate Rule

Stop here. Do not run CH2 until the user manually confirms this Stage B result is acceptable.
