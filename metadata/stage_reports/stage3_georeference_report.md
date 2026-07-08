# Stage 3 Georeference CH1 Report

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：建议人工查看地理点云预览和标定警告；如可接受，再进入阶段 4。
- 阶段：stage3_georeference_ch1
- 处理通道：CH1
- 坐标系：EPSG:32651
- UTM 分区：51N/51R
- 标定状态：engineering_transform_reference_aligned; boresight_lever_arm_pending

## Inputs and Outputs

- Input L2 POS: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\intermediate\l2_pos_matched\L2P_CH1_cap_00113_20260510191003_time_repaired.h5`
- Output L3: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\intermediate\l3_georef\L3_CH1_cap_00113_20260510191003_time_repaired.h5`
- Raw Preview HTML: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\preview\stage3_ch1_georef_L2P_CH1_cap_00113_20260510191003_time_repaired.html`
- Height-QC Preview HTML: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\outputs\preview\stage3_ch1_georef_height_qc_preview.html`
- Reference L3: `D:\Programdata\Airborne_LiDAR_Data\proj_denoising_f3\0510_f3\L3_DATA\L2_cap_00111_20260510190957.h5`

## Key Statistics

- Point count before georeference filtering: 2,332,645
- Point count after georeference filtering: 1,547,274
- Filtered count: 785,371
- Range minimum for georeference: 30.0 m
- Reference height bias: 15.607716 m
- Height QC range from reference L3: 14.345937014235716 m to 19.451964598407585 m
- Height QC inliers: 1,487,503 (96.137013%)
- Height below QC range: 40,257
- Height above QC range: 19,514
- GPS time: count=1,547,274, min=40217.903774145, max=40220.905572243, mean=40219.401906778
- North offset: count=1,547,274, min=-32.427519672, max=69.323001411, mean=8.233483244
- East offset: count=1,547,274, min=-92.553577208, max=40.895430522, mean=-11.073622291
- Down offset: count=1,547,274, min=28.531551426, max=267.329463980, mean=113.207111398
- Easting: count=1,547,274, min=394524.587855553, max=394658.133288115, mean=394606.340380934
- Northing: count=1,547,274, min=3417442.230575380, max=3417545.322525696, mean=3417483.755211600
- Height: count=1,547,274, min=-139.364747548, max=99.450165006, mean=14.769138166
- Longitude: count=1,547,274, min=121.896496588, max=121.897889645, mean=121.897351665
- Latitude: count=1,547,274, min=30.885580187, max=30.886512001, mean=30.885956168
- Reference POINT_X: count=1,490,688, min=3417456.384768354, max=3417500.643597920, mean=3417477.918733510
- Reference POINT_Y: count=1,490,688, min=394583.823238620, max=394643.470363453, mean=394612.903691116
- Reference POINT_Z: count=1,490,688, min=14.345937014, max=19.451964598, mean=15.136239097
- Empty channel placeholders: CH2, CH3, CH4

## Known Warnings

- Height QC inlier rate is 96.14%; raw preview contains vertical outliers.
- Applied reference height bias 15.608 m; boresight/lever-arm/range calibration still pending.

## Gate Rule

Stop here. Do not run Stage 4 until the user manually confirms this Stage 3 result is acceptable.
