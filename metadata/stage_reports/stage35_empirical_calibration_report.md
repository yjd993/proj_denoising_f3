# Stage 3.5 Empirical Calibration Report

## Gate Conclusion

- 结论：基本合理但有风险
- 建议：经验校正后的可用文件已生成，但存在被跳过的时间异常文件；建议确认后再继续阶段 4/5。
- 阶段：stage35_empirical_calibration

## Calibration Model

- dx_m: -0.622464
- dy_m: 0.950740
- dz_m: -0.001392
- z_scale: 1.400123
- rotation_deg: -0.046903
- apply_z_scale: False
- apply_rotation: False
- reference median E/N/H: 394612.074, 3417477.012, 15.083
- source median E/N/H: 394612.696, 3417476.061, 15.084

## Outputs

- Calibration model JSON: `metadata\stage_reports\stage35_empirical_model.json`
- Sample calibrated L3: `intermediate\l3_georef\L3C_CH1_cap_00111_20260510190957.h5`
- Sample preview HTML: `outputs\preview\stage35_ch1_calibrated_sample_preview.html`
- Continuous calibrated merged L3: `intermediate\l3_georef\L3C_CH1_continuous_cap_00111_00115.h5`
- Continuous preview HTML: `outputs\preview\stage35_ch1_calibrated_continuous_preview.html`

## Merged Summary

- Merged point count: 6,158,028
- Merged GPS time: count=6,158,028, min=40211.900355924, max=40226.908654552, mean=40219.403091080
- Merged Easting: count=6,158,028, min=394564.454511593, max=394650.497320776, mean=394608.172830299
- Merged Northing: count=6,158,028, min=3417451.809301061, max=3417527.852286401, mean=3417484.921671074
- Merged Height: count=6,158,028, min=-15.434819383, max=47.952883285, mean=14.758909264

## Per-file Summary

| File | Skipped | Reason | Points | GPS min | GPS max | Easting mean | Northing mean | Height median | Height min | Height max |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| L2P_CH1_cap_00111_20260510190957.h5 | False | 无 | 1,537,517 | 40211.900356 | 40214.902070 | 394612.449 | 3417477.837 | 15.082 | -15.433 | 47.932 |
| L2P_CH1_cap_00112_20260510191000.h5 | False | 无 | 1,543,622 | 40214.902072 | 40217.903772 | 394607.997 | 3417480.435 | 15.083 | -15.435 | 47.953 |
| L2P_CH1_cap_00113_20260510191003.h5 | True | POS match success rate below 95% (0.10%); likely invalid L1 GNSS time. | 0 | N/A | N/A | N/A | N/A | N/A | N/A | N/A |
| L2P_CH1_cap_00114_20260510191006.h5 | False | 无 | 1,539,247 | 40220.905574 | 40223.906686 | 394605.749 | 3417488.732 | 15.082 | -15.434 | 47.832 |
| L2P_CH1_cap_00115_20260510191009.h5 | False | 无 | 1,537,642 | 40223.906688 | 40226.908655 | 394606.500 | 3417492.696 | 15.083 | -15.428 | 47.943 |

## Known Warnings

- Stage 3.5 is empirical alignment against the existing L3 sample; it is not a substitute for final boresight/lever-arm calibration.
- L1_cap_00113_20260510191003.h5: skipped. POS match success rate below 95% (0.10%); likely invalid L1 GNSS time.

## Gate Rule

Stop here. Do not run Stage 4/5 until the user manually confirms this Stage 3.5 result is acceptable.
