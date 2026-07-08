# Stage 4 Continuous CH1 Sample Report

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：连续文件存在超过 0.5 秒的时间间隔；建议人工查看接缝后再进入阶段 5。
- 阶段：stage4_continuous_ch1_sample
- 处理通道：CH1

## Outputs

- Merged L3: `intermediate\l3_georef\L3_CH1_continuous_cap_00111_00115.h5`
- Preview HTML: `outputs\preview\stage4_ch1_continuous_georef_preview.html`

## Summary

- Input files: 5
- Total L2 points: 11,651,757
- Total L3 points: 6,171,844
- Time gaps between files seconds: [1.9999934011138976e-06, 3.00180213200656, 1.9999934011138976e-06]
- Merged GPS time: count=6,171,844, min=40211.900355924, max=40226.908654552, mean=40219.403045445
- Merged Easting: count=6,171,844, min=394531.668779293, max=394676.415033656, mean=394608.793974432
- Merged Northing: count=6,171,844, min=3417438.256767554, max=3417553.206066546, mean=3417483.971595743
- Merged Height: count=6,171,844, min=-146.682510967, max=96.770759199, mean=14.705836208
- Merged Longitude: count=6,171,844, min=121.896571606, max=121.898081411, mean=121.897377309
- Merged Latitude: count=6,171,844, min=30.885541909, max=30.886584473, mean=30.885958339

## Per-file Summary

| File | Skipped | Skip reason | L2 points | L3 points | GPS min | GPS max | Easting mean | Northing mean | Height median | Conclusion | Warnings |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| L1_cap_00111_20260510190957.h5 | False | 无 | 2,326,241 | 1,540,743 | 40211.900356 | 40214.902070 | 394613.068 | 3417476.888 | 15.083 | 基本合理但有风险 | Calibrated range contains values below -5 m.; Height QC inlier rate is 97.42%; raw preview contains vertical outliers.; Applied reference height bias 6.036 m; boresight/lever-arm/range calibration still pending. |
| L1_cap_00112_20260510191000.h5 | False | 无 | 2,335,234 | 1,547,440 | 40214.902072 | 40217.903772 | 394608.617 | 3417479.482 | 15.083 | 基本合理但有风险 | Height QC inlier rate is 96.69%; raw preview contains vertical outliers.; Applied reference height bias 12.872 m; boresight/lever-arm/range calibration still pending. |
| L1_cap_00113_20260510191003.h5 | True | POS match success rate below 95% (0.10%); likely invalid L1 GNSS time. | 2,332,645 | 0 | nan | nan | nan | nan | nan | 不合理 | 2,330,214 points are outside POS time range.; POS match success rate is below 95%: 0.10%.; POS match success rate below 95% (0.10%); likely invalid L1 GNSS time. |
| L1_cap_00114_20260510191006.h5 | False | 无 | 2,329,228 | 1,542,615 | 40220.905574 | 40223.906686 | 394606.371 | 3417487.782 | 15.083 | 基本合理但有风险 | Height QC inlier rate is 97.31%; raw preview contains vertical outliers.; Applied reference height bias 5.891 m; boresight/lever-arm/range calibration still pending. |
| L1_cap_00115_20260510191009.h5 | False | 无 | 2,328,409 | 1,541,046 | 40223.906688 | 40226.908655 | 394607.124 | 3417491.748 | 15.083 | 基本合理但有风险 | Height QC inlier rate is 97.42%; raw preview contains vertical outliers.; Applied reference height bias 9.760 m; boresight/lever-arm/range calibration still pending.; Stage 3 northing mean differs from reference L3 POINT_X mean by more than 10 m. |

## Known Warnings

- L1_cap_00111_20260510190957.h5: Calibrated range contains values below -5 m.
- L1_cap_00111_20260510190957.h5: Height QC inlier rate is 97.42%; raw preview contains vertical outliers.
- L1_cap_00111_20260510190957.h5: Applied reference height bias 6.036 m; boresight/lever-arm/range calibration still pending.
- L1_cap_00112_20260510191000.h5: Height QC inlier rate is 96.69%; raw preview contains vertical outliers.
- L1_cap_00112_20260510191000.h5: Applied reference height bias 12.872 m; boresight/lever-arm/range calibration still pending.
- L1_cap_00113_20260510191003.h5: skipped. POS match success rate below 95% (0.10%); likely invalid L1 GNSS time.
- L1_cap_00114_20260510191006.h5: Height QC inlier rate is 97.31%; raw preview contains vertical outliers.
- L1_cap_00114_20260510191006.h5: Applied reference height bias 5.891 m; boresight/lever-arm/range calibration still pending.
- L1_cap_00115_20260510191009.h5: Height QC inlier rate is 97.42%; raw preview contains vertical outliers.
- L1_cap_00115_20260510191009.h5: Applied reference height bias 9.760 m; boresight/lever-arm/range calibration still pending.
- L1_cap_00115_20260510191009.h5: Stage 3 northing mean differs from reference L3 POINT_X mean by more than 10 m.
- Time gap larger than 0.5 seconds detected between continuous files.

## Gate Rule

Stop here. Do not run Stage 5 until the user manually confirms this Stage 4 result is acceptable.
