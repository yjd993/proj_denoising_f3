# Stage 0 Baseline Check Report

## Gate Conclusion

- 结论：合理
- 建议：可以进入阶段 1：单文件 CH1 的 L1 到 L2 局部 XYZ。
- 阶段：stage0_baseline_check
- 处理通道：CH1
- LIDAR 时间修正：`GNSS_SEC_CH1 + 18`

## Inputs

- Sample L1: `0510_f3\L1-TIME_ANGE_DIST_DATA\L1_cap_00111_20260510190957.h5`
- Reference L3: `0510_f3\L3_DATA\L2_cap_00111_20260510190957.h5`
- POS source: `0510_f3\0510f3_processed.mat`

## Required Dataset Check

- Missing L1 CH1 datasets: `none`
- Missing L3 datasets: `none`
- Missing POS fields: `none`

## Key Statistics

- L1 CH1 point count: 2,326,241
- L1 raw GNSS seconds: count=2,326,241, min=40193.900355924, max=40196.902070032, mean=40195.400443416
- L1 lidar_time_sec: count=2,326,241, min=40211.900355924, max=40214.902070032, mean=40213.400443416
- L3 GNSS seconds: count=1,490,688, min=40211.900355924, max=40214.902070032, mean=40213.401158353
- L3 POINT_X: count=1,490,688, min=3417456.384768354, max=3417500.643597920, mean=3417477.918733510
- L3 POINT_Y: count=1,490,688, min=394583.823238620, max=394643.470363453, mean=394612.903691116
- L3 POINT_Z: count=1,490,688, min=14.345937014, max=19.451964598, mean=15.136239097
- POS time seconds: count=340,893, min=39629.016000000, max=41333.476000000, mean=40481.246000000
- POS non-monotonic corrections: 0

## Alignment Checks

- Time alignment absolute error, min sec: 0.0
- Time alignment absolute error, max sec: 0.0
- Time alignment absolute error, mean sec: 0.0007149372759158723
- POS covers lidar_time_sec: True

## Known Warnings

- 无

## Gate Rule

Stop here. Do not run Stage 1 until the user manually confirms this Stage 0 result is acceptable.
