# Stage 5 Full CH1 Processing Report

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：存在跳过文件；请先检查 summary 和 repair log，再决定是否补跑。
- 阶段：stage5_full_ch1
- 处理通道：CH1
- 时间修正：`GNSS_SEC_CH1 + 18`
- 异常时间策略：类似 00113 的文件按邻近正常文件和 `PULSE_INDEX_CH1` 重建时间，并记录为 `REPAIRED_TIME_EXPERIMENT`

## Summary

- Input files: 447
- Processed/reused files: 446
- Repaired-time files used: 29
- Skipped files: 1
- Missing sequence numbers: [308]
- Total L1 CH1 points: 984,676,612
- Total L3 CH1 points: 656,367,796
- Elapsed minutes: 22.11

## Outputs

- Per-file slim L3 HDF5 directory: `outputs\h5_ch1`
- File summary CSV: `outputs\qc\stage5_file_summary.csv`
- Time repair log CSV: `outputs\qc\stage5_time_repair_log.csv`
- Low-density HTML preview: `outputs\preview\stage5_ch1_full_overview.html`

## Warnings

- Disk-aware output mode was used: Stage 5 writes slim georeferenced HDF5 per file, not full L2/L2P intermediates.
- LAS/LAZ export is deferred until this HDF5 result is accepted.
- Boresight/lever-arm calibration is still an engineering approximation from earlier stages.
- Warning rows in summary: 447

## Skipped Files

- seq 449: 0510_f3\L1-TIME_ANGE_DIST_DATA\L1_cap_00449_20260510192703.h5 - missing normal neighboring file for time interpolation

## Gate Rule

Stop here. Do not expand to CH2-CH4 or convert final LAZ until the user manually confirms this Stage 5 result is acceptable.
