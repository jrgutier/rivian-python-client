"""Inspect the actual payloads being sent to debug INTERNAL_SERVER_ERROR."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rivian.parallax import (
    build_charging_session_query,
    build_climate_hold_command,
    build_climate_status_query,
    build_parked_energy_query,
)


def inspect_command(name: str, cmd):
    """Inspect a parallax command."""
    print(f"\n{'='*60}")
    print(f"{name}")
    print(f"{'='*60}")
    print(f"RVM Type: {cmd.rvm}")
    print(f"Payload (Base64): {cmd.payload_b64}")
    print(f"Payload Length: {len(cmd.payload_b64)}")

    # Decode to see raw bytes
    import base64

    raw_bytes = base64.b64decode(cmd.payload_b64)
    print(f"Raw Bytes: {raw_bytes.hex()}")
    print(f"Raw Bytes Length: {len(raw_bytes)}")


# Test empty payload queries
print("=" * 60)
print("QUERY OPERATIONS (Empty Payloads)")
print("=" * 60)

inspect_command("Parked Energy Query", build_parked_energy_query())
inspect_command("Charging Session Query", build_charging_session_query())
inspect_command("Climate Status Query", build_climate_status_query())

# Test command with payload
print("\n" + "=" * 60)
print("COMMAND OPERATIONS (With Protobuf Payloads)")
print("=" * 60)

inspect_command("Climate Hold Command (120 min)", build_climate_hold_command(120))

# Show what the protobuf message looks like
print("\n" + "=" * 60)
print("PROTOBUF MESSAGE DETAILS")
print("=" * 60)

from rivian.proto import rivian_climate_pb2

msg = rivian_climate_pb2.ClimateHoldSetting()
msg.hold_time_duration_seconds = 7200  # 120 minutes

print(f"Message Type: {type(msg).__name__}")
print(f"Field: hold_time_duration_seconds = {msg.hold_time_duration_seconds}")
print(f"Serialized: {msg.SerializeToString().hex()}")
print(f"Serialized Length: {len(msg.SerializeToString())} bytes")

# Try encoding manually to verify
import base64

manual_b64 = base64.b64encode(msg.SerializeToString()).decode("utf-8")
print(f"Manual Base64: {manual_b64}")

# Compare with what our helper creates
cmd = build_climate_hold_command(120)
print(f"Helper Base64: {cmd.payload_b64}")
print(f"Match: {manual_b64 == cmd.payload_b64}")
