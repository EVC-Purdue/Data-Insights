# Recorded requested-speed mapping

## Evidence inspected offline

Source checkout: `C:\Users\chack\Documents\AutonomousKart_Kevin`, HEAD `f057b01a6cdec7ba10eb142f0d0957f413228c9d` (September 2026). Also inspected historical revision `7ee424356ddba86613233c39c79134989cf0a1ef` (May 19, 2026) and `6d33e75` (May 20). These are available source revisions, not proof of which executable was deployed during each recording.

Both actual MCAP schemas declare `std_msgs/msg/Float32MultiArray`: `MultiArrayLayout layout`, `float32[] data`, with nested layout dimensions (label, size, stride) and data_offset. No header timestamp or unit annotations are embedded. All 4,620 messages in `20260519_150616_0` and all 8,513 in `20260519_211017_0` have exactly two elements, empty dimensions, and offset zero. No schema/shape mismatch with the inspected publisher was found. The generic schema alone would not establish units.

The following paths are relative to `src/autonomous_kart/autonomous_kart/` in that checkout:

- Publisher `nodes/pathfinder/pathfinder_node.py::_autonomous_tick` unpacks `(motor_mps, steering_deg)` from the planner/safety result and publishes those two floats unchanged. `planners/base.py::Planner.plan` specifies `(throttle_mps, steering_deg)`. `_manual_tick` publishes requested speed and steering, limits manual speed to nonnegative values, and publishes zero on expired input. State transitions also publish `[0, 0]`. The inspected `SafetyChecker.check` returns the proposal unchanged.
- Hardware consumer `nodes/e_comms/e_comms_node.py::cmd_drive` reads `data[0]` as m/s and `data[1]` as degrees (negative left, positive right). `convert` clamps speed and calls `powertrain.speed_to_erpm`. This is dimensional evidence beyond variable names: `nodes/e_comms/powertrain.py` converts m/s into wheel RPM using wheel circumference in meters and seconds per minute, then applies motor/axle gearing and pole pairs to produce electrical RPM. The reverse function produces the separately measured `/e_comms/kart_speed_m_per_s` from VESC status.
- `nodes/master/master_node.py::_drive_callback` stores the two values for telemetry. `nodes/localization/localization_node.py::_cb_drive` passes the command pair to the simulation model; it is not an independent measured-speed source. `nodes/metrics/metrics_node.py` subscribes for logging.

| Element | Verified meaning | Units/sign | Distinction |
|---|---|---|---|
| `data[0]` | Requested linear vehicle/wheel speed before consumer clamping | m/s; positive forward request, zero zero-speed request; signed values retained | Not measured speed, PWM, normalized percent, or guaranteed applied speed |
| `data[1]` | Steering actuator command | degrees; negative left, positive right per hardware consumer | Not a measured front-wheel angle or calibrated physical wheel deflection |

Negative speed requests are preserved by Data-Insights, but do **not** establish reverse actuation: current `params/actuators.yaml` sets `min_speed: 0.0`, and the hardware consumer clamps to its configured range. Zero requested speed does not prove the kart stopped. Hardware sign/calibration and deployed parameters were not independently measured.

Historical source agrees on speed units and field order. Steering scaling changed: May 19's inspected `convert` has no preliminary multiplier, May 20 multiplies steering by three, and current HEAD multiplies by two before clamping/normalization. Current wheel-diameter calibration also postdates these bags. None of those conversions are applied to the imported speed request; steering is not newly imported by this change. Confirm the deployed revision/configuration with controls before interpreting actual actuation or wheel deflection.

## Import behavior

`backend/app.py::import_bag` now populates existing `telemetry.commanded` from `/cmd_drive data[0]`. `backend/command_mapping.py` validates the inspected flat two-element layout. The importer requires the recorded `std_msgs/msg/Float32MultiArray` type. Unsupported schemas/layouts/lengths and missing/nonfinite speed fields produce a timestamped null, never zero or a carried-forward value. Finite signed commands are retained unchanged. A missing topic leaves an empty series; absent messages create gaps. The second element is not used to infer speed validity or tracking.

Timestamps remain asynchronous MCAP log times with the same all-topic origin as other imported signals; no interpolation, resampling, PWM conversion, or alignment is performed. Diagnostics identify the source as `/cmd_drive data[0] (requested linear speed; before actuator clamping)`, unit m/s, classification command. Existing coverage and evidence validation apply. Live streams retain their previous unavailable mapping. No automatic tracking, correlation, or causal assessment was added.

The audit reports accepted finite command timestamps separately from imported timestamps with nulls; `importedNullCount` makes this distinction explicit. Its mapping states distinguish absent topics from present topics without usable commands. Other signal filters remain unchanged. The earlier [raw-bag audit](raw-bag-coverage-audit.md) records the pre-mapping findings; its commanded-empty rows are superseded by this investigation.

## Verification

Rerun results (seconds from each bag's common log origin):

| Run | Raw / decoded / extracted / finite accepted / imported | Command bounds | Leading / trailing uncovered | Internal gaps |
|---|---|---|---|---|
| `20260519_150616_0` | 4620 / 4620 / 4620 / 4620 / 4620 | 0.851842789–84.743531557 | 0.851842789 / 0.006475186 s | 0 |
| `20260519_211017_0` | 8513 / 8513 / 8513 / 8513 / 8513 | 115.467506708–270.391070134 | 115.467506708 / 0.007800711 s | 0 |

No command decoding errors, field/layout rejections, nulls, duplicate timestamps, or backward timestamps occurred. Accepted/imported times match exactly. Command publish time equals log time; there is no header clock. Cadences are 0.017525318 and 0.0173819745 s, respectively, under the existing median-spacing rule. Acceleration/speed counts and gaps remain unchanged. In 211017, the command recording begins after the earlier major acceleration and speed gaps; this signal cannot assess requests during those gaps. Absence of recorded commands does not establish absence of actuation or its cause.

Run the same offline audit commands documented in [raw-bag-coverage-audit.md](raw-bag-coverage-audit.md). Focused synthetic MCAP tests cover positive/negative/zero commands, empty/short arrays, nonfinite fields, unsupported layout, exact asynchronous log-time conversion, timestamped null coverage, and audit/import parity. At the mapping implementation stage, the backend suite passed 57 tests; subsequent verification is documented in [command-speed-investigation.md](command-speed-investigation.md). No live Gemini request was made.
