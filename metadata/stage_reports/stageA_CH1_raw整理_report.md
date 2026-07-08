# Stage A CH1 Raw 整理报告

## Gate Conclusion

- 结论：合理
- 建议：可以进入 Stage B：CH1 轻度去噪。

## Inputs and Outputs

- Input directory: `outputs\h5_ch1`
- Output raw directory: `outputs\h5_ch1\raw`
- Input files: 446
- Output raw files: 446
- Storage mode: hardlink first, reuse if exists
- Summary CSV: `outputs\qc\stageA_CH1_raw整理_summary.csv`

## Key Statistics

- Total CH1 raw points: 656,367,796
- Time-repaired points retained: 42,063,798
- Hardlink failed files: 0
- Files with non-empty CH2/CH3/CH4: 0

## Method Registry

| method_id | method_name | source_type | used_for_delete_or_transform |
|---|---|---|---|
| DATA_ORG_000 | raw L3 file organization by hardlink | data_management | no |

## Project Empirical Parameters

- 无。本阶段只整理文件，不进行坐标转换、时间修复、去噪或删点。

## Manual Checklist

- 确认 `outputs/h5_ch1/raw` 中只作为 CH1 raw 成果使用。
- 确认 CH2/CH3/CH4 没有写入 CH1 raw 文件。
- 确认 raw 文件数量与当前 CH1 stage5 输出一致。
- 确认硬链接整理方式可以接受：不重复占用 25GB+ 磁盘空间。

## Gate Rule

Stop here. Do not run Stage B until the user manually confirms this Stage A result is acceptable.
