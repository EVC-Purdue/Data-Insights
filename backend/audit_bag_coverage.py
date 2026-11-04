"""Offline, read-only MCAP/import coverage audit. Outputs aggregates, never payloads."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path

from mcap.reader import make_reader
from mcap_ros2.decoder import DecoderFactory

from app import import_bag
from diagnostics import Diagnostics
from command_mapping import commanded_speed


# Mirrors import_bag, not a guess based on topic naming. Tests check parity.
MAPPINGS = {
    'acceleration': ('/imu', 'linear_acceleration.x'),
    'speed': ('/e_comms/kart_speed_m_per_s', 'data'),
    'commanded': ('/cmd_drive', 'data[0]'),
}


def extract(signal, msg):
    """Return eligibility and rejection reasons; never serialize the value."""
    try:
        if signal == 'commanded':
            _, reason = commanded_speed(msg)
            return [reason] if reason else []
        value = float(msg.linear_acceleration.x if signal == 'acceleration' else msg.data)
        reasons = []
        if signal == 'acceleration' and msg.linear_acceleration_covariance[0] == -1:
            reasons.append('covariance_unavailable')
        if not math.isfinite(value):
            reasons.append('nonfinite')
        return reasons
    except (AttributeError, TypeError, ValueError, IndexError, OverflowError):
        return ['extraction_error']


def coverage(times, origin, duration):
    relative = [(t - origin) / 1e9 for t in times]
    run = {'id': 'audit', 'diagnostic': {
        'metadata': {'time': {'start': 0, 'end': duration, 'basis': 'bag_log_relative'}},
        'measurements': {'stage': {'unit': 'timestamp', 'kind': 'availability',
            'source': 'audit', 'samples': [{'time': t, 'value': 1} for t in relative]}}}}
    result = Diagnostics(run).coverage('stage')
    keys = ('samples', 'firstTimestamp', 'lastTimestamp', 'leadingUncovered',
            'trailingUncovered', 'entireRunUncovered', 'cadenceSeconds',
            'gapThresholdSeconds', 'internalGapCount', 'internalGapSeconds',
            'internalGaps', 'gapsTruncated')
    return {**{k: result[k] for k in keys},
            'duplicateTimestamps': len(times) - len(set(times)),
            'backwardStepsInReadOrder': sum(b < a for a, b in zip(times, times[1:]))}


def offset_summary(offsets):
    return {'count': len(offsets), 'minSeconds': min(offsets) / 1e9 if offsets else None,
            'maxSeconds': max(offsets) / 1e9 if offsets else None}


def audit(path):
    factory = DecoderFactory()
    inventory = {}
    stages = {s: {k: [] for k in ('raw', 'decoded', 'extracted', 'accepted', 'publish', 'header',
                                'publishOffsets', 'headerOffsets')}
              for s, (topic, _) in MAPPINGS.items() if topic}
    counters = {s: Counter() for s in stages}
    origin = None
    raw_origin = None
    decoded_end = None
    errors = Counter()
    with path.open('rb') as stream:
        reader = make_reader(stream)
        summary = reader.get_summary()
        if summary:
            for channel in summary.channels.values():
                schema = summary.schemas.get(channel.schema_id)
                inventory[channel.id] = {'topic': channel.topic, 'type': schema.name if schema else None,
                    'encoding': channel.message_encoding, 'raw': 0, 'decoded': 0, 'decodeErrors': {}}
        # File order exposes ordering anomalies; importer requests log-time ordering.
        for schema, channel, message in reader.iter_messages(log_time_order=False):
            item = inventory.setdefault(channel.id, {'topic': channel.topic,
                'type': schema.name if schema else None, 'encoding': channel.message_encoding,
                'raw': 0, 'decoded': 0, 'decodeErrors': {}})
            item['raw'] += 1
            stamp = message.log_time
            raw_origin = stamp if raw_origin is None else min(raw_origin, stamp)
            signal = next((s for s, (topic, _) in MAPPINGS.items() if topic == channel.topic), None)
            if signal:
                st = stages[signal]
                st['raw'].append(stamp)
                st['publish'].append(message.publish_time)
                st['publishOffsets'].append(message.publish_time - stamp)
                counters[signal]['zeroPublishTime'] += message.publish_time == 0
            try:
                decoder = factory.decoder_for(channel.message_encoding, schema)
                if decoder is None:
                    raise LookupError('Unsupported encoding')
                msg = decoder(message.data)
            except Exception as exc:
                # Exception text may embed payload bytes; record only its class.
                name = type(exc).__name__
                item['decodeErrors'][name] = item['decodeErrors'].get(name, 0) + 1
                errors[name] += 1
                continue
            item['decoded'] += 1
            origin = stamp if origin is None else min(origin, stamp)
            decoded_end = stamp if decoded_end is None else max(decoded_end, stamp)
            if not signal:
                continue
            st['decoded'].append(stamp)
            header = getattr(getattr(msg, 'header', None), 'stamp', None)
            if header is not None:
                hs = header.sec * 10**9 + header.nanosec
                counters[signal]['zeroHeaderTime'] += hs == 0
                if hs:
                    st['header'].append(hs)
                    st['headerOffsets'].append(hs - stamp)
            reasons = (['unsupported_schema'] if signal == 'commanded' and schema.name != 'std_msgs/msg/Float32MultiArray'
                       else extract(signal, msg))
            counters[signal].update(reasons)
            if not set(reasons) & {'extraction_error', 'unsupported_schema', 'unsupported_layout_or_length'}:
                st['extracted'].append(stamp)
            if not reasons:
                st['accepted'].append(stamp)
    if origin is None:
        raise ValueError('No decoded messages; common importer origin unavailable')
    duration = (decoded_end - origin) / 1e9
    try:
        run = import_bag(path)
        import_error = None
    except Exception as exc:
        run = None
        import_error = type(exc).__name__
    result = {'run': path.stem, 'originLogTimeNs': origin,
              'rawOriginOffsetSeconds': (raw_origin - origin) / 1e9,
              'durationSeconds': duration, 'inventory': list(inventory.values()),
              'decodeErrors': dict(errors), 'importError': import_error, 'signals': {},
              'policy': 'Importer uses ascending log time, subtracts origin as integer nanoseconds then divides by 1e9; sorts samples, retains duplicates. No speed/acceleration/command cap or downsampling. Invalid commanded values are retained as nulls; accepted counts exclude these. Only MPC cost is sampled at 10 Hz. Decode errors abort import; audit continues to count them.'}
    for signal, (topic, field) in MAPPINGS.items():
        present = any(i['topic'] == topic for i in inventory.values()) if topic else None
        samples = run['telemetry'][signal] if run else []
        entry = {'topic': topic, 'field': field, 'timestampBasis': 'MCAP log_time',
                 'mappingState': 'unsupported_mapping' if topic is None else
                     'absent_mapped_topic' if not present else
                     'present_usable' if stages[signal]['accepted'] else 'present_no_usable_samples',
                 'importedCount': len(samples) if run else None}
        if topic:
            st = stages[signal]
            entry['stages'] = {k: coverage(st[k], origin, duration)
                               for k in ('raw', 'decoded', 'extracted', 'accepted', 'publish', 'header')}
            entry['rejections'] = {k: counters[signal][k] for k in
                                   ('covariance_unavailable', 'nonfinite', 'extraction_error',
                                    'unsupported_schema', 'unsupported_layout_or_length')}
            entry['clockOffsetsFromLog'] = {k: offset_summary(st[k + 'Offsets']) for k in ('publish', 'header')}
            entry['zeroClockCounts'] = {k: counters[signal][k] for k in ('zeroPublishTime', 'zeroHeaderTime')}
            if run:
                # Exact comparison avoids round-tripping epoch timestamps through floats.
                expected = sorted((t - origin) / 1e9 for t in st['accepted'])
                entry['acceptedTimesMatchImportedExactly'] = expected == [p['time'] for p in samples if p['value'] is not None]
                entry['importedNullCount'] = sum(p['value'] is None for p in samples)
        if run:
            entry['importedCoverage'] = Diagnostics(run).coverage(signal)
        result['signals'][signal] = entry
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bags', type=Path, nargs='+', help='Actual MCAP files (opened rb only)')
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.bags], indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
