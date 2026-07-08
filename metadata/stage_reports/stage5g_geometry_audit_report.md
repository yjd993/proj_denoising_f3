# Stage 5G CH1 几何转换模型返查报告

## Gate Conclusion

- 结论：不合理
- 建议：当前 range/scan/body->NED 模型无法稳定复现参考 L3 的 LIDAR_X/Y/Z；优先修正扫描角零位、角度方向、距离零位或 boresight/lever-arm。
- 阶段：stage5g_ch1_geometry_audit
- 样例：00111
- L1 sample count: 2326241
- Reference matched count: 30000
- Match mode: exact
- Max nearest time delta: 2e-06 s

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| DG_ALS_001 | direct georeferencing model diagnostic | peer_reviewed_journal | Skaloud & Lichti, ISPRS Journal of Photogrammetry and Remote Sensing, 2006 | no, diagnostic only |
| STRIP_QC_009 | overlap / strip consistency QC | peer_reviewed_conference | Filin & Vosselman, ISPRS 2004 | no, diagnostic only |
| PROJECT_EMPIRICAL_PARAMETER | candidate zero offset, scan angle convention, body axis mapping | project_empirical_parameter | Project diagnostic candidates only | no, candidates are not final calibration |

## Best Body Candidate

- zero strategy: Z0
- angle mode: 180-angle
- zero used: 0.0 m
- direct LIDAR vector RMSE: 60.95343497745312

说明：参考 L3 的 `LIDAR_X/Y/Z` 已验证为导航系偏移量，不是原始 body 坐标；本项只作为早期候选参考，最终判断看下面的 offset candidate。

## Best Axis Mapping Candidate

- mapping: LIDAR_X=1*body_z+offset;LIDAR_Y=1*body_y+offset;LIDAR_Z=-1*body_x+offset
- allow scale: False
- mean RMSE: 25.22952880075528
- max RMSE: 56.37513840739596

## Best Offset Candidate

- zero strategy: Z0
- angle mode: 360-angle
- rotation mode: current
- north offset RMSE: 10.527656383675584
- east offset RMSE: 10.3126477383124
- down offset RMSE: 57.61857753959786
- vector RMSE: 59.47337833008914

## Best Georef Candidate

- rotation mode: current
- easting RMSE: 10.312649148660094
- northing RMSE: 10.52765702152271
- height RMSE: 66.59130962239549
- diagnostic height bias: -76.25569847224304

## Outputs

- Body candidates CSV: `outputs\qc\stage5g_geometry_audit\body_candidate_errors.csv`
- Axis mapping CSV: `outputs\qc\stage5g_geometry_audit\axis_mapping_errors.csv`
- Offset candidate CSV: `outputs\qc\stage5g_geometry_audit\offset_candidate_errors.csv`
- Georef candidate CSV: `outputs\qc\stage5g_geometry_audit\georef_candidate_errors.csv`

## Known Warnings

- 本阶段只做诊断，不生成最终坐标成果。
- 候选扫描角/轴向/零位均为 `PROJECT_EMPIRICAL_PARAMETER`，不能写成论文算法。
- 若 reference L3 的 `LIDAR_X/Y/Z` 与当前 L1 点序并非一一对应，本报告会作为方向性诊断，而不是最终标定结果。

## Manual Checklist

- 如果 best offset candidate 仍误差很大，先排查 L1->body->NED：零位、扫描角方向、F_BodyFrame_XYZ 参数、boresight、lever-arm。
- 如果 best offset candidate 合理但 georef 误差大，排查 POS 旋转顺序、轴向符号、UTM/EPSG 投影。
- 未通过本 gate 前，不跑全量 CH1 v2、CH2、去噪或 LAZ。
