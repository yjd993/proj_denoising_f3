# Stage 8A CH1 LADM-II Light Denoise Batch

## Gate

- Conclusion: READY_FOR_DENOISED_CLOUDCOMPARE_REVIEW
- Ready for CloudCompare review: True
- Reason: Stage 8A light denoise completed without failed files and delete ratios are within review threshold.

## Scope

- Input: Stage 7D display-candidate manifest, 95 Stage 7A H5 files.
- Output root: `C:\proj_denoising_f3_2.0\stage8a_ladm2_light_denoised`
- Original Stage 7A outputs are not modified.
- This is light denoise, not final classification.

## Method

1. Keep finite coordinates, POS-good points, and `range_m >= 30.0`.
2. Remove only extreme per-file height tails using 0.02-99.98 percentiles plus padding.
3. Remove isolated spatial speckles using a 2D grid-density neighborhood rule.
4. Remove large local height outliers only in sufficiently populated XY cells.

## Aggregate

- Processed files: 95
- Failed files: 0
- Point count before: 217,000,065
- Point count after: 139,912,812
- Deleted count: 77,087,253
- Delete ratio: 35.524069%
- Max file delete ratio: 40.978620%
- H5 output size: 16,191,313,185 bytes
- LAZ output size: 6,436,272,452 bytes
- Sample TXT output size: 2,231,205,354 bytes

## Processed Preview

| seq | before | after | deleted | delete ratio | h med | r min |
| --- | --- | --- | --- | --- | --- | --- |
| 50 | 2600678 | 1639448 | 961230 | 0.369607 | 14.1 | 85.196 |
| 51 | 2151537 | 1327921 | 823616 | 0.382804 | 14.3606 | 77.5001 |
| 52 | 2155759 | 1331376 | 824383 | 0.38241 | 14.4818 | 75.3453 |
| 53 | 2249868 | 1425166 | 824702 | 0.366556 | 14.6138 | 85.4983 |
| 55 | 2804253 | 1831775 | 972478 | 0.346787 | 14.751 | 82.6768 |
| 56 | 2758069 | 1794082 | 963987 | 0.349515 | 14.7624 | 81.8414 |
| 57 | 2736141 | 1771329 | 964812 | 0.352618 | 14.771 | 87.8183 |
| 58 | 2347122 | 1520637 | 826485 | 0.352127 | 14.7869 | 76.2054 |
| 59 | 2345751 | 1518740 | 827011 | 0.352557 | 14.8006 | 85.0085 |
| 60 | 2345985 | 1519319 | 826666 | 0.352375 | 14.7858 | 89.8161 |
| 61 | 2740713 | 1776727 | 963986 | 0.351728 | 14.802 | 83.7314 |
| 62 | 2729363 | 1771730 | 957633 | 0.350863 | 14.7858 | 86.117 |
| 63 | 2336524 | 1518132 | 818392 | 0.35026 | 14.8004 | 80.8102 |
| 64 | 2336480 | 1518999 | 817481 | 0.349877 | 14.8127 | 79.1663 |
| 65 | 2331621 | 1490894 | 840727 | 0.360576 | 14.8284 | 81.5965 |
| 66 | 2347847 | 1503143 | 844704 | 0.359778 | 14.9394 | 81.2063 |
| 67 | 2338428 | 1509597 | 828831 | 0.354439 | 15.041 | 80.9837 |
| 68 | 2289837 | 1492571 | 797266 | 0.348176 | 15.0144 | 84.5785 |
| 69 | 2240113 | 1460746 | 779367 | 0.347914 | 15.0109 | 89.1506 |
| 70 | 2331910 | 1523411 | 808499 | 0.346711 | 15.0084 | 80.9966 |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| STAGE8A_BASIC_VALIDITY | Basic finite/POS/range validity filter | project_filter_rule | Keep finite UTM coordinates, POS-good points, and range_m >= configured minimum | yes, denoise candidate point removal |
| STAGE8A_HEIGHT_QUANTILE_FENCE | Conservative per-file height quantile fence | project_filter_rule | Remove only extreme height tails after basic validity filtering | yes, denoise candidate point removal |
| STAGE8A_GRID_DENSITY | Approximate 2D grid neighborhood density filter | project_filter_rule | Remove isolated spatial speckles using 3x3 cell neighborhood counts | yes, denoise candidate point removal |
| STAGE8A_LOCAL_HEIGHT_ROBUST | Local grid robust height outlier filter | project_filter_rule | Within sufficiently populated XY cells, remove large height deviations from local median | yes, denoise candidate point removal |

## Outputs

- Manifest CSV: `C:\proj_denoising_f3_2.0\stage8a_ladm2_light_denoised\manifest\stage8a_ch1_ladm2_light_denoise_manifest.csv`
- Report JSON: `C:\proj_denoising_f3_2.0\reports\stage8a_ch1_ladm2_light_denoise_batch_report.json`
- H5 directory: `C:\proj_denoising_f3_2.0\stage8a_ladm2_light_denoised\h5`
- LAZ directory: `C:\proj_denoising_f3_2.0\stage8a_ladm2_light_denoised\laz`
- Sample TXT directory: `C:\proj_denoising_f3_2.0\stage8a_ladm2_light_denoised\txt_sample`

## Manual Review

Open several denoised LAZ or sample TXT files in CloudCompare and compare with the Stage 7A original display candidates. Focus on whether sparse flying points and near-zero range clutter are reduced without breaking valid strips or roofs/edges.
