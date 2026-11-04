"""Verified AutonomousKart /cmd_drive contract; see docs/cmd-drive-mapping.md."""
import math

SOURCE = '/cmd_drive data[0] (requested linear speed; before actuator clamping)'


def commanded_speed(msg):
    """Keep invalid messages as timestamped nulls; never infer a unit conversion."""
    try:
        if msg.layout.data_offset != 0 or msg.layout.dim or len(msg.data) != 2:
            return None, 'unsupported_layout_or_length'
        value = float(msg.data[0])
        if not math.isfinite(value):
            return None, 'nonfinite'
        return value, None
    except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
        return None, 'extraction_error'
