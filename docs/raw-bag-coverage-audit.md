# Raw MCAP versus imported coverage

Follow-up: [verified commanded-speed mapping](cmd-drive-mapping.md) now supersedes the commanded-empty/unsupported rows below. Acceleration and speed findings remain unchanged; this document preserves the original pre-mapping audit.

Offline audit of the external `AutonomousKart_Diagnostics` recordings, 2026-10-31. No Gemini requests, frontend changes, or bag writes. No importer bug was demonstrated; importer behavior is unchanged.

## Reproduce

From the Data-Insights directory in PowerShell:

```powershell
.\.venv\Scripts\python.exe backend\audit_bag_coverage.py `
  C:\Users\chack\Documents\AutonomousKart_Diagnostics\20260519_150616\20260519_150616_0.mcap `
  C:\Users\chack\Documents\AutonomousKart_Diagnostics\20260519_211017\20260519_211017_0.mcap
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -q
```

The script opens bags with `rb`, invokes the real importer, and emits aggregate JSON only: channel inventory, counts, coverage, clock offsets, rejection categories, and exact accepted/imported timestamp parity. It does not output telemetry values, message bytes, or exception text. The local execution output is `.cache/bag-coverage-audit.json` (not a source artifact). No key is needed or accessed. Audit exceptions are represented by class name; malformed MCAP container framing can still abort the audit. A decode error normally aborts the importer; the audit continues counting decodable messages, marks import failure, and leaves imported counts unknown rather than reporting zero.

## Verified comparison

All times below are seconds from the **same bag log-time origin** for every stage and clock. Counts are raw / decoded / extracted / accepted / imported. Extracted means the fields can be read, before covariance and finite-value filters. For these bags all five counts agree, with zero decode failures on every inventoried channel and zero acceleration/speed extraction, covariance, or nonfinite rejections.

| Recording | Signal and importer source | Basis | Counts | Raw and imported bounds | Major uncovered intervals | Conclusion |
|---|---|---|---|---|---|---|
| 150616 (84.750007 s) | acceleration: `/imu`, `linear_acceleration.x` | log time | 5842 / 5842 / 5842 / 5842 / 5842 | 0.000062–58.519716 | trailing 58.519716–84.750007 (26.230291 s); no internal gaps | No raw IMU messages after 58.519716; not import truncation |
| 150616 | speed: `/e_comms/kart_speed_m_per_s`, `data` | log time | 8475 / 8475 / 8475 / 8475 / 8475 | 0.005329–84.750007 | no internal gaps | Raw/imported coverage identical |
| 150616 | commanded velocity: no mapping | not applicable | n/a / n/a / n/a / n/a / 0 | empty | no mapped series | Unsupported import mapping; not evidence of absent commands |
| 211017 (270.398871 s) | acceleration: `/imu`, `linear_acceleration.x` | log time | 18961 / 18961 / 18961 / 18961 / 18961 | 1.935659–270.398871 | leading 1.935659 s; internal 10.485810–86.652062 (76.166252 s), 92.949033–94.973822 (2.024789 s), 86.979795–87.318557 (0.338762 s) | All three gaps present in raw messages |
| 211017 | speed: `/e_comms/kart_speed_m_per_s`, `data` | log time | 24302 / 24302 / 24302 / 24302 / 24302 | 1.725734–270.398139 | leading 1.725734 s; internal 62.823758–88.579452 (25.755694 s); trailing 0.000732 s | Gap present in raw messages |
| 211017 | commanded velocity: no mapping | not applicable | n/a / n/a / n/a / n/a / 0 | empty | no mapped series | Unsupported import mapping; not evidence of absent commands |

Full recording IDs end in `_0`. The stage reports reuse `Diagnostics.coverage`, including its documented rule: sort distinct finite timestamps, require at least three positive spacings, flag spacing > 3 × median + 1e-9 s. Largest three gaps are displayed with total count/duration and explicit truncation. No gaps were omitted here. Cadences for acceleration/speed are 0.009988812/0.009979116 s (150616) and 0.0100019505/0.009988580 s (211017). Leading/trailing intervals are exact endpoint differences, not fault thresholds.

## Inventory (actual MCAP channels)

Counts below are raw messages and also successfully decoded messages. Zero means a registered channel with no messages, not an absent channel. Types use ROS `package/msg/Type` notation.

| Topic | Type | 150616 | 211017 |
|---|---|---:|---:|
| `/imu` | sensor_msgs/msg/Imu | 5842 | 18961 |
| `/imu/calibration_status` | std_msgs/msg/String | 1022 | 489 |
| `/e_comms/kart_speed_m_per_s` | std_msgs/msg/Float32 | 8475 | 24302 |
| `/e_comms/throttle_pwm` | std_msgs/msg/UInt16 | 8237 | 23861 |
| `/e_comms/steering_pwm` | std_msgs/msg/UInt16 | 8235 | 23861 |
| `/gps` | nav_msgs/msg/Odometry | 848 | 2447 |
| `/odom` | nav_msgs/msg/Odometry | 6675 | 21576 |
| `/cmd_drive` | std_msgs/msg/Float32MultiArray | 4620 | 8513 |
| `/mpc/status` | std_msgs/msg/Float32MultiArray | 4621 | 15940 |
| `/mpc/residual_mode` | std_msgs/msg/String | 0 | 1 |
| `/system_state` | std_msgs/msg/String | 0 | 1 |
| `/track_angles` | std_msgs/msg/Float32MultiArray | 0 | 0 |
| `/manual_commands` | std_msgs/msg/Float32MultiArray | 0 | 0 |
| `/pathfinder_params` | std_msgs/msg/Float32MultiArray | 0 | 0 |
| `/mpc/residual_revert` | std_msgs/msg/Empty | 0 | 0 |

`/cmd_drive` exists and decodes, but its name/type alone does not establish which array element, units, or semantics would represent commanded velocity. No alternative mapping was invented. The audit distinguishes `unsupported_mapping` from `absent_mapped_topic` and `present_no_usable_samples`.

## Clock and importer checks

`backend/app.py::import_bag` uses `event.log_time_ns`; `read_ros2_messages` defaults to ascending log-time order. Origin is the first decoded message across all topics, not the first measurement. In these files it equals the earliest raw log timestamp: 1779203177302774960 ns and 1779225018079329256 ns. Subtraction occurs in integer nanoseconds before division by 1e9. Run end is the maximum decoded log time relative to that origin.

- Publish time equals log time for every speed and IMU message in both recordings. Their publish-clock bounds and gaps are identical.
- Speed Float32 messages have no header clock. Every IMU message has a nonzero header stamp. Header times are compared against the common log origin, without independently zeroing each series.
- In 150616, IMU header bounds are -0.019149–58.518614 s; header minus log ranges from -0.019210451 to -0.000286562 s. No header internal gaps.
- In 211017, IMU header bounds are 1.934868–270.398412 s; header minus log ranges from -0.329332700 to -0.000293843 s. Its largest header gap is 10.485402–86.651022 (76.165620 s). The two smaller header gaps are 92.948549–94.972838 (2.024289 s) and 86.989224–87.323565 (0.334341 s). Clock choice does not remove the major gap.
- There are no duplicate or backward timestamps in file order for either measured signal on either clock. Import sorts but does not discard duplicates. Every eligible log timestamp matches the actual imported timestamp exactly, including fractional seconds.
- There is no acceleration/speed sample cap, temporal crop, or downsampling in the importer. Covariance[0] == -1 and nonfinite acceleration are filtered; nonfinite speed is filtered. Neither filter rejected any messages here. The unrelated MPC cost series is sampled at 10 Hz. Frontend-facing `thin()` presentation sampling does not alter the in-memory diagnostic samples.
- Imported samples contain no explicit nulls. The observed gaps are absent source-message timestamps, not null values converted to missing timestamps.

## Limits and tests

Verified: the missing intervals already exist in these MCAP files and survive import without loss. Unknown: why those messages are absent (publisher behavior, transport, recorder behavior, or another upstream condition). These findings alone do not establish a sensor failure. Header/log offsets also do not identify the cause. No source publisher code or recorder operational logs were audited.

56 offline backend tests pass, including synthetic MCAP checks of filter counts, absent versus unusable versus unsupported mappings, malformed-message decode reporting, timestamp ordering/duplicates, nanosecond origin conversion, publish/header offsets, and accepted/imported parity. Existing coverage, evidence validation, provider schema, and six-call tests remain passing. These checks make no live Gemini requests and do not verify model interpretation.
