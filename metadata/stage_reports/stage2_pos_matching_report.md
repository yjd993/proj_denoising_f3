# Stage 2 POS Matching Report

## Gate Conclusion

- 结论：合理
- 建议：可以进入阶段 3：单文件 CH1 的地理坐标转换。
- 阶段：stage2_pos_matching
- 处理通道：CH1

## Inputs and Outputs

- Input L2: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\intermediate\l2_body_xyz\L2_CH1_cap_00113_20260510191003_time_repaired.h5`
- Output L2 POS: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\intermediate\l2_pos_matched\L2P_CH1_cap_00113_20260510191003_time_repaired.h5`
- POS source: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\0510_f3\0510f3_processed.mat`

## Key Statistics

- Point count before matching: 2,332,645
- Point count after matching: 2,332,645
- POS match success count: 2,332,645
- POS match success rate: 100.000000%
- NO_POS count: 0
- LOW_CONFIDENCE count: 0
- Low-confidence threshold seconds: 0.2
- POS time non-monotonic corrections: 0
- LIDAR time seconds: count=2,332,645, min=40217.903774145, max=40220.905572243, mean=40219.403275896
- POS time seconds: count=340,893, min=39629.016000000, max=41333.476000000, mean=40481.246000000
- |POS interpolation dt|: count=2,332,645, min=0.000000003, max=0.002499996, mean=0.001250917
- POS easting: count=2,332,645, min=394616.772171103, max=394618.079890342, mean=394617.413389530
- POS northing: count=2,332,645, min=3417473.840328974, max=3417477.224486691, mean=3417475.523261415
- POS height: count=2,332,645, min=112.354000000, max=112.394000000, mean=112.368515143
- POS roll: count=2,332,645, min=0.228000174, max=5.196999570, mean=3.138949004
- POS pitch: count=2,332,645, min=4.417000000, max=5.873999267, mean=4.938968059
- POS heading: count=2,332,645, min=336.091000139, max=338.179887831, mean=336.516253625
- Empty channel placeholders: CH2, CH3, CH4

## Known Warnings

- 无

## Gate Rule

Stop here. Do not run Stage 3 until the user manually confirms this Stage 2 result is acceptable.
