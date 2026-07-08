# Stage 4 00113 Time Repair Experiment

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：请人工查看修复预览；若缺失扫描带被补上且接缝可接受，再决定是否把 00113 作为修复数据纳入阶段 4。
- 标记：`REPAIRED_TIME_EXPERIMENT`

## Time Repair Model

- Previous file raw max: 40199.903772128
- Next file raw min: 40202.905574260
- Repaired raw time: 40199.903774145 ~ 40202.905572243
- Repaired lidar time: 40217.903774145 ~ 40220.905572243
- Pulse index: 1 ~ 1488039
- Pulse period seconds: 0.000002017194

## Processing Result

- Stage 2 POS match success rate: 100.000000%
- Stage 2 POS match success count: 2,332,645
- Repaired 00113 L3 point count: 1,547,274
- Merged point count with repaired 00113: 7,719,118
- Time gaps seconds: [1.9999934011138976e-06, 2.017193764913827e-06, 2.017193764913827e-06, 1.9999934011138976e-06]
- Merged GPS time: count=7,719,118, min=40211.900355924, max=40226.908654552, mean=40219.402817203
- Merged Easting: count=7,719,118, min=394524.587855553, max=394676.415033656, mean=394608.302158991
- Merged Northing: count=7,719,118, min=3417438.256767554, max=3417553.206066546, mean=3417483.928222192
- Merged Height: count=7,719,118, min=-146.682510967, max=99.450165006, mean=14.718524895

## Outputs

- Repaired L2: `intermediate\l2_body_xyz\L2_CH1_cap_00113_20260510191003_time_repaired.h5`
- Repaired L2 POS: `intermediate\l2_pos_matched\L2P_CH1_cap_00113_20260510191003_time_repaired.h5`
- Repaired L3: `intermediate\l3_georef\L3_CH1_cap_00113_20260510191003_time_repaired.h5`
- Merged L3: `intermediate\l3_georef\L3_CH1_continuous_cap_00111_00115_with_00113_time_repaired.h5`
- Preview HTML: `outputs\preview\stage4_ch1_continuous_with_00113_time_repaired_preview.html`

## Known Warnings

- 00113 原始 GNSS_SEC_CH1 异常，本结果按 PULSE_INDEX_CH1 线性重建时间轴。
- 这是数据修复实验，不是原始可靠时间戳恢复。
- 修复仅用于判断是否能补上缺失扫描带；进入全量处理前应保留 repaired 标记。

## Gate Rule

Stop here. Do not use the repaired 00113 in Stage 5 until the user manually confirms this experiment is acceptable.
