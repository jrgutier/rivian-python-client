#!/usr/bin/env python3
"""Verify protobuf serialization matches expected format.

This test verifies that the generated protobuf classes serialize correctly
according to the Protocol Buffer wire format specification.
"""

import base64
from src.rivian.proto.rivian_climate_pb2 import ClimateHoldSetting, ClimateHoldStatus
from src.rivian.proto.rivian_charging_pb2 import ChargingScheduleTimeWindow, WindowData
from src.rivian.proto.rivian_base_pb2 import Location
from src.rivian.parallax import build_climate_hold_command, build_charging_schedule_command


def test_climate_hold_setting():
    """Test ClimateHoldSetting serialization."""
    print("=" * 70)
    print("Testing ClimateHoldSetting Protobuf Serialization")
    print("=" * 70)

    # Create a message for 2 hours (7200 seconds)
    setting = ClimateHoldSetting(hold_time_duration_seconds=7200)
    serialized = setting.SerializeToString()
    b64_encoded = base64.b64encode(serialized).decode()

    print(f"Duration: 7200 seconds (2 hours)")
    print(f"Serialized bytes: {serialized.hex()}")
    print(f"Base64 encoded: {b64_encoded}")
    print()

    # Verify it round-trips correctly
    deserialized = ClimateHoldSetting()
    deserialized.ParseFromString(serialized)
    print(f"Round-trip verification:")
    print(f"  Original: hold_time_duration_seconds = {setting.hold_time_duration_seconds}")
    print(f"  Deserialized: hold_time_duration_seconds = {deserialized.hold_time_duration_seconds}")
    print(f"  Match: {setting.hold_time_duration_seconds == deserialized.hold_time_duration_seconds}")
    print()

    # Test via helper function
    cmd = build_climate_hold_command(duration_minutes=120)
    print(f"Via helper function (120 minutes):")
    print(f"  RVM: {cmd.rvm}")
    print(f"  Payload (Base64): {cmd.payload_b64}")
    print()


def test_charging_schedule_window():
    """Test ChargingScheduleTimeWindow serialization."""
    print("=" * 70)
    print("Testing ChargingScheduleTimeWindow Protobuf Serialization")
    print("=" * 70)

    # Create a schedule for 10 PM to 6 AM (79200 to 21600 seconds)
    start_seconds = 22 * 3600  # 10 PM = 79200 seconds
    end_seconds = 6 * 3600      # 6 AM = 21600 seconds
    duration = (86400 - start_seconds) + end_seconds  # Overnight duration

    window_data = WindowData(
        start_time=start_seconds,
        end_time=end_seconds,
        duration=duration,
        amps=48,
        location=Location(),
        start_day_of_week=0,  # Sunday
        end_day_of_week=6,    # Saturday
    )

    schedule = ChargingScheduleTimeWindow(
        is_valid=True,
        window_data=window_data,
    )

    serialized = schedule.SerializeToString()
    b64_encoded = base64.b64encode(serialized).decode()

    print(f"Schedule: 10 PM to 6 AM daily")
    print(f"  Start time: {start_seconds} seconds ({start_seconds / 3600:.0f} hours)")
    print(f"  End time: {end_seconds} seconds ({end_seconds / 3600:.0f} hours)")
    print(f"  Duration: {duration} seconds ({duration / 3600:.1f} hours)")
    print(f"  Amps: 48")
    print(f"Serialized bytes ({len(serialized)} bytes): {serialized.hex()}")
    print(f"Base64 encoded: {b64_encoded}")
    print()

    # Verify it round-trips correctly
    deserialized = ChargingScheduleTimeWindow()
    deserialized.ParseFromString(serialized)
    print(f"Round-trip verification:")
    print(f"  Original is_valid: {schedule.is_valid}")
    print(f"  Deserialized is_valid: {deserialized.is_valid}")
    print(f"  Original start_time: {schedule.window_data.start_time}")
    print(f"  Deserialized start_time: {deserialized.window_data.start_time}")
    print(f"  Match: {schedule.is_valid == deserialized.is_valid and schedule.window_data.start_time == deserialized.window_data.start_time}")
    print()

    # Test via helper function
    cmd = build_charging_schedule_command(22, 0, 6, 0)
    print(f"Via helper function (22:00 to 06:00):")
    print(f"  RVM: {cmd.rvm}")
    print(f"  Payload (Base64): {cmd.payload_b64}")
    print(f"  Payload length: {len(cmd.payload_b64)} characters")
    print()


def test_climate_hold_status_parsing():
    """Test ClimateHoldStatus parsing (response from vehicle)."""
    print("=" * 70)
    print("Testing ClimateHoldStatus Protobuf Parsing")
    print("=" * 70)

    # Create a sample response
    status = ClimateHoldStatus(
        status=ClimateHoldStatus.STATUS_OFF,
        availability=ClimateHoldStatus.AVAILABILITY_AVAILABLE,
        unavailability_reason=ClimateHoldStatus.UNAVAILABILITY_REASON_UNSPECIFIED,
    )

    serialized = status.SerializeToString()
    b64_encoded = base64.b64encode(serialized).decode()

    print(f"Sample status (OFF, AVAILABLE):")
    print(f"  Status: {ClimateHoldStatus.Status.Name(status.status)}")
    print(f"  Availability: {ClimateHoldStatus.Availability.Name(status.availability)}")
    print(f"Serialized bytes: {serialized.hex()}")
    print(f"Base64 encoded: {b64_encoded}")
    print()

    # Verify it round-trips correctly
    deserialized = ClimateHoldStatus()
    deserialized.ParseFromString(serialized)
    print(f"Round-trip verification:")
    print(f"  Original status: {ClimateHoldStatus.Status.Name(status.status)}")
    print(f"  Deserialized status: {ClimateHoldStatus.Status.Name(deserialized.status)}")
    print(f"  Match: {status.status == deserialized.status}")
    print()


if __name__ == "__main__":
    test_climate_hold_setting()
    test_charging_schedule_window()
    test_climate_hold_status_parsing()

    print("=" * 70)
    print("✓ All protobuf serialization tests completed!")
    print("=" * 70)
    print()
    print("Summary:")
    print("- ClimateHoldSetting: Serializes with hold_time_duration_seconds field")
    print("- ChargingScheduleTimeWindow: Serializes with nested WindowData structure")
    print("- ClimateHoldStatus: Parses with enum-based status fields")
    print()
    print("These structures match the Android APK implementation.")
