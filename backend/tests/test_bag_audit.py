"""Offline synthetic MCAP tests; no API calls or external recordings required."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcap_ros2.writer import Writer
from mcap.writer import Writer as RawWriter
from audit_bag_coverage import audit, coverage
from app import import_bag
from diagnostics import Diagnostics


IMU = '''std_msgs/Header header
geometry_msgs/Vector3 linear_acceleration
float64[9] linear_acceleration_covariance
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
================================================================================
MSG: geometry_msgs/Vector3
float64 x
float64 y
float64 z
'''


class BagAuditTests(unittest.TestCase):
    def test_commanded_speed_signed_values_nulls_and_asynchronous_times(self):
        definition = '''std_msgs/MultiArrayLayout layout
float32[] data
================================================================================
MSG: std_msgs/MultiArrayLayout
std_msgs/MultiArrayDimension[] dim
uint32 data_offset
================================================================================
MSG: std_msgs/MultiArrayDimension
string label
uint32 size
uint32 stride
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'commands.mcap'
            with path.open('wb') as stream, Writer(stream) as writer:
                speed = writer.register_msgdef('std_msgs/msg/Float32', 'float32 data')
                command = writer.register_msgdef('std_msgs/msg/Float32MultiArray', definition)
                origin = 1_700_000_000_000_000_001
                writer.write_message('/e_comms/kart_speed_m_per_s', speed, {'data': 0.0}, log_time=origin)
                for i, values in enumerate(([2.0, 1.0], [-2.0, -1.0], [0.0, 0.0], [],
                                            [float('nan'), 0.0], [float('inf'), 0.0], [1.0], [1.0, 0.0])):
                    writer.write_message('/cmd_drive', command,
                        {'layout': {'dim': [], 'data_offset': 1 if i == 7 else 0}, 'data': values},
                        log_time=origin + 123 + i * 10**9, publish_time=origin + i * 10**9)
                writer.write_message('/e_comms/kart_speed_m_per_s', speed, {'data': 0.0}, log_time=origin + 10**10)
            run = import_bag(path)
            result = audit(path)['signals']['commanded']
        self.assertEqual([p['value'] for p in run['telemetry']['commanded']], [2, -2, 0, None, None, None, None, None])
        self.assertEqual([p['time'] for p in run['telemetry']['commanded']], [i + 0.000000123 for i in range(8)])
        self.assertTrue(result['acceptedTimesMatchImportedExactly'])
        self.assertEqual(result['importedNullCount'], 5)
        c = Diagnostics(run).coverage('commanded')
        self.assertEqual(c['nullValues'], 5)
        self.assertEqual(c['unit'], 'm/s')
        self.assertIn('/cmd_drive data[0]', c['source'])
        self.assertAlmostEqual(c['lastFiniteTimestamp'], 2.000000123)
        self.assertAlmostEqual(c['trailingUncovered']['duration'], 2.999999877)

    def test_filters_clocks_order_duplicates_and_import_parity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.mcap'
            with path.open('wb') as stream, Writer(stream) as writer:
                speed = writer.register_msgdef('std_msgs/Float32', 'float32 data')
                imu = writer.register_msgdef('sensor_msgs/Imu', IMU)
                origin = 1_700_000_000_000_000_001
                for t in (0, 1, 3, 2, 3, 4, 10):
                    writer.write_message('/e_comms/kart_speed_m_per_s', speed,
                        {'data': float('nan') if t == 4 else 1.0},
                        log_time=origin + t * 10**9, publish_time=origin + t * 10**9 - 100)
                    writer.write_message('/imu', imu, {
                        'header': {'stamp': {'sec': 1700000000 + t, 'nanosec': 0}, 'frame_id': ''},
                        'linear_acceleration': {'x': 1.0, 'y': 0.0, 'z': 0.0},
                        'linear_acceleration_covariance': [-1.0 if t >= 4 else 0.0] + [0.0] * 8},
                        log_time=origin + t * 10**9)
            result = audit(path)
        self.assertIsNone(result['importError'])
        self.assertEqual(result['originLogTimeNs'], origin)
        for name in ('speed', 'acceleration'):
            self.assertTrue(result['signals'][name]['acceptedTimesMatchImportedExactly'])
            self.assertEqual(result['signals'][name]['stages']['raw']['duplicateTimestamps'], 1)
            self.assertEqual(result['signals'][name]['stages']['raw']['backwardStepsInReadOrder'], 1)
        speed = result['signals']['speed']
        self.assertEqual(speed['rejections']['nonfinite'], 1)
        self.assertEqual(speed['importedCount'], 6)
        self.assertEqual(speed['clockOffsetsFromLog']['publish']['minSeconds'], -1e-7)
        accel = result['signals']['acceleration']
        self.assertEqual(accel['rejections']['covariance_unavailable'], 2)
        self.assertEqual(accel['clockOffsetsFromLog']['header']['minSeconds'], -1e-9)
        self.assertEqual(accel['stages']['header']['samples'], 7)
        self.assertEqual(accel['importedCoverage']['trailingUncovered']['duration'], 7)
        self.assertEqual(result['signals']['commanded']['mappingState'], 'absent_mapped_topic')

    def test_present_unusable_is_not_absent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'empty.mcap'
            with path.open('wb') as stream, Writer(stream) as writer:
                schema = writer.register_msgdef('std_msgs/Float32', 'float32 data')
                writer.write_message('/e_comms/kart_speed_m_per_s', schema,
                                     {'data': float('inf')}, log_time=100)
            result = audit(path)
        self.assertEqual(result['signals']['speed']['mappingState'], 'present_no_usable_samples')
        self.assertEqual(result['signals']['acceleration']['mappingState'], 'absent_mapped_topic')

    def test_decode_error_counted_without_payload_or_exception_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'corrupt.mcap'
            with path.open('wb') as stream:
                writer = RawWriter(stream)
                writer.start(profile='ros2')
                schema = writer.register_schema('std_msgs/Float32', 'ros2msg', b'float32 data')
                channel = writer.register_channel('/e_comms/kart_speed_m_per_s', 'cdr', schema)
                writer.add_message(channel, 100, b'\x00\x01\x00\x00\x00\x00\x80\x3f', 100)
                writer.add_message(channel, 200, b'', 200)
                writer.finish()
            result = audit(path)
        self.assertEqual(sum(result['decodeErrors'].values()), 1)
        self.assertIsNotNone(result['importError'])
        self.assertIsNone(result['signals']['speed']['importedCount'])
        self.assertEqual(result['signals']['speed']['stages']['raw']['samples'], 2)
        self.assertEqual(result['signals']['speed']['stages']['decoded']['samples'], 1)

    def test_cadence_rule_and_empty_stage(self):
        result = coverage([t * 10**9 for t in (0, 1, 2, 3, 10)], 0, 12)
        self.assertEqual(result['internalGaps'], [{'start': 3, 'end': 10, 'duration': 7}])
        self.assertEqual(result['trailingUncovered']['duration'], 2)
        self.assertEqual(coverage([], 0, 12)['entireRunUncovered']['duration'], 12)


if __name__ == '__main__':
    unittest.main()
