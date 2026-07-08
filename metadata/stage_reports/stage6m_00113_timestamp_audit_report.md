# Stage 6M 00113 Timestamp Anomaly Audit

## Gate Conclusion

- Conclusion: 隔离 00113 原始时间戳
- Geometry-use allowed: False
- Reason: 00113 CH1 raw GNSS_SEC is not a plausible GPS-second timestamp: expected-window rate=0.000171479%, GNSS equals pulse-index rate=100.000000%, POS confident coverage=0.104216%.

## Key CH1 Evidence

- Neighbor-bounded expected raw time: 40199.903772128 ~ 40202.905574260 s
- 00113 CH1 raw GNSS_SEC range: 1.000000000 ~ 1488039.000000000
- CH1 points inside expected raw window: 4 / 2,332,645 (0.000171479%)
- CH1 GNSS_SEC equals PULSE_INDEX rate: 100.000000%
- CH1 fitted GNSS-per-pulse slope: 1.000000000 s/pulse
- CH1 POS confident coverage after +18 s: 2,431 / 2,332,645 (0.104216%)

## Channel Summary

| CH | verdict | expected-window count | expected-window rate | GNSS==pulse rate | POS confident rate | fitted s/pulse |
|---:|---|---:|---:|---:|---:|---:|
| 1 | CORRUPTED_TIMESTAMP_FIELD_PULSE_INDEX_COPIED | 4 | 0.000171479% | 100.000000% | 0.104216% | 1.000000000 |
| 2 | CORRUPTED_TIMESTAMP_FIELD_PULSE_INDEX_COPIED | 3 | 0.000197486% | 100.000000% | 0.111382% | 1.000000000 |
| 3 | CORRUPTED_TIMESTAMP_FIELD_PULSE_INDEX_COPIED | 5 | 0.000215281% | 100.000000% | 0.103680% | 1.000000000 |
| 4 | CORRUPTED_TIMESTAMP_FIELD_PULSE_INDEX_COPIED | 3 | 0.000219156% | 100.000000% | 0.111039% | 1.000000000 |

## Method Registry

| method_id | method_name | source_type | source_reference | used_for_delete_or_transform |
|---|---|---|---|---|
| TIMESTAMP_FIELD_AUDIT | Raw L1 GNSS timestamp anomaly audit | project_qc_rule | Compare 00113 raw GNSS_SEC_CH* against neighbor time windows, pulse indices, and POS time coverage | no, QC only |
| NEIGHBOR_TIME_WINDOW | Neighbor-bounded expected raw GNSS time window | project_qc_rule | Use previous normal file maximum GNSS time and next normal file minimum GNSS time as the expected gap for 00113 | no, QC only |
| NO_GEOMETRY_MODEL_USE | Isolation from geometry diagnostics | project_gate_rule | Do not feed 00113 raw timestamps into Stage 6I/6K/6L LADM-II geometry model decisions | no, gate only |

## Outputs

- Channel audit CSV: `outputs\qc\stage6m_00113_timestamp_audit\00113_channel_timestamp_audit.csv`
- Neighbor summary CSV: `outputs\qc\stage6m_00113_timestamp_audit\neighbor_channel_time_summary.csv`
- Expected-window margins CSV: `outputs\qc\stage6m_00113_timestamp_audit\00113_expected_window_margin_counts.csv`
- CH1 sample CSV: `outputs\qc\stage6m_00113_timestamp_audit\00113_ch1_anomaly_samples.csv`
- CH1 expected-window hits CSV: `outputs\qc\stage6m_00113_timestamp_audit\00113_ch1_expected_window_hits.csv`
- Report JSON: `metadata\stage_reports\stage6m_00113_timestamp_audit_report.json`

## Stop Rule

00113 remains excluded from Stage 6I/6K/6L geometry model decisions. Any future use must be explicitly marked as a time-repair experiment, not as original raw timing.
