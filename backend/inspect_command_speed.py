"""Read-only offline comparison selection; no Gemini client or API request."""
import argparse
import json
from pathlib import Path

from app import import_bag
from diagnostics import Diagnostics


def inspect(path):
    d = Diagnostics(import_bag(path))
    command, speed = d.coverage('commanded'), d.coverage('speed')
    first = [c['firstFiniteTimestamp'] for c in (command, speed)]
    last = [c['lastFiniteTimestamp'] for c in (command, speed)]
    if None in first + last or max(first) >= min(last):
        return {'run': path.stem, 'unavailable': 'No overlapping finite timestamp bounds'}
    start, end = max(first), min(last)
    summary = d.summary('speed', start, end)
    extremum = max((summary['min'], summary['max']), key=lambda p: abs(p['value']))
    a, b = max(start, extremum['time'] - 5), min(end, extremum['time'] + 5)
    result = d.command_speed_window(a, b)
    return {'run': path.stem, 'selection': {
        'reason': 'Largest absolute measured-speed extremum within common finite bounds; up to five seconds each side clipped to those bounds. An observation anchor, not a fault threshold. Tool availability must still confirm usable overlap.',
        'anchor': extremum, 'commonFiniteBounds': {'start': start, 'end': end}}, 'tool': result}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bags', nargs='+', type=Path)
    args = parser.parse_args()
    print(json.dumps([inspect(path) for path in args.bags], indent=2, allow_nan=False))
