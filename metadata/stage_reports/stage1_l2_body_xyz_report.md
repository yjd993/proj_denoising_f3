# Stage 1 L1 to L2 Body XYZ Report

## Gate Conclusion

- 结论：合理
- 建议：可以进入阶段 2：单文件 CH1 的 POS 时间匹配。
- 阶段：stage1_l1_to_l2_body_xyz
- 处理通道：CH1
- LIDAR 时间修正：`GNSS_SEC_CH1 + 18`

## Inputs and Outputs

- Input L1: `0510_f3\L1-TIME_ANGE_DIST_DATA\L1_cap_00115_20260510191009.h5`
- Output L2: `intermediate\l2_body_xyz\L2_CH1_cap_00115_20260510191009.h5`
- Preview HTML: `outputs\preview\stage1_ch1_body_xyz_cap_00115_20260510191009.html`

## Key Statistics

- Point count before filtering: 2,328,409
- Point count after filtering: 2,328,409
- Non-positive range filtered: 0
- GNSS raw seconds: count=2,328,409, min=40205.906688396, max=40208.908654552, mean=40207.407167139
- LIDAR time seconds: count=2,328,409, min=40223.906688396, max=40226.908654552, mean=40225.407167139
- Raw distance counts: count=2,328,409, min=9289.000000000, max=237000.000000000, mean=74749.151296873
- Range before calibration: count=2,328,409, min=10.885546875, max=277.734375000, mean=87.596661676
- Range after calibration: count=2,328,409, min=0.009994160, max=266.825073826, mean=76.711407281
- Scan angle degrees: count=2,328,409, min=0.000000000, max=359.994506836, mean=180.144938942
- Body X: count=2,328,409, min=-50.381802158, max=42.652614903, mean=-1.379490668
- Body Y: count=2,328,409, min=-66.225808974, max=63.141125197, mean=0.597333362
- Body Z: count=2,328,409, min=0.009789187, max=261.103696982, mean=74.745363738
- Zero peak: 10.884375

## Channel Calibration

- CH1 zero_offset: 18.802278358296036
- CH1 slope: 1.000126486323461
- CH1 intercept: -0.008823548695634469
- Empty channel placeholders: CH2, CH3, CH4

## Known Warnings

- 无

## Gate Rule

Stop here. Do not run Stage 2 until the user manually confirms this Stage 1 result is acceptable.
