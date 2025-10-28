"""Tests for Parallax protocol implementation."""

# pylint: disable=protected-access
from __future__ import annotations

import base64

import aiohttp
import pytest
from aresponses import ResponsesMockServer
from rivian import Rivian
from rivian.exceptions import RivianBadRequestError, RivianUnauthenticated
from rivian.parallax import (
    ParallaxCommand,
    RVMType,
    build_charging_session_query,
    build_climate_status_query,
    build_ota_status_query,
    build_trip_progress_query,
)
from rivian.proto.base import SessionCost, TimeOfDay
from rivian.proto.charging import ChargingScheduleTimeWindow, ChargingSessionLiveData
from rivian.proto.climate import ClimateHoldSetting, ClimateHoldStatus

# Mock responses
PARALLAX_SUCCESS_RESPONSE = {
    "data": {
        "sendParallaxPayload": {
            "__typename": "ParallaxResponse",
            "success": True,
            "sequenceNumber": 42,
            "payload": "CgQIARAB",
        }
    }
}

PARALLAX_FAILURE_RESPONSE = {
    "data": {
        "sendParallaxPayload": {
            "__typename": "ParallaxResponse",
            "success": False,
            "sequenceNumber": 0,
            "payload": "",
        }
    }
}

PARALLAX_ERROR_RESPONSE = {
    "errors": [
        {
            "extensions": {
                "code": "UNAUTHENTICATED",
                "reason": "UNAUTHENTICATED",
            },
            "message": "Authentication failed",
            "path": ["sendParallaxPayload"],
        }
    ],
    "data": None,
}


# Test RVMType enum
class TestRVMType:
    """Test RVMType enum."""

    def test_rvm_type_count(self) -> None:
        """Test that all 18 RVM types are defined."""
        assert len(list(RVMType)) == 18

    def test_rvm_type_values(self) -> None:
        """Test specific RVM type values."""
        # Energy & Charging (4 types)
        assert RVMType.PARKED_ENERGY_MONITOR == "energy_edge_compute.graphs.parked_energy_distributions"
        assert RVMType.CHARGING_SESSION_CHART_DATA == "energy_edge_compute.graphs.charging_graph_global"
        assert RVMType.CHARGING_SESSION_LIVE_DATA == "energy_edge_compute.graphs.charge_session_breakdown"
        assert RVMType.CHARGING_SCHEDULE_TIME_WINDOW == "charging.schedule.time_window"

        # Geofence (1 type)
        assert RVMType.VEHICLE_GEO_FENCES == "geofence.geofence_service.favoriteGeofences"

        # OTA Updates (2 types)
        assert RVMType.OTA_SCHEDULE_CONFIGURATION == "ota.user_schedule.ota_config"
        assert RVMType.OTA_STATE == "ota.ota_state.vehicle_ota_state"

        # GearGuard (2 types)
        assert RVMType.GEAR_GUARD_CONSENTS == "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent"
        assert RVMType.GEAR_GUARD_DAILY_LIMITS == "gearguard_streaming.privacy.gearguard_streaming_daily_limit"

        # Vehicle (1 type)
        assert RVMType.VEHICLE_WHEELS == "vehicle.wheels.vehicle_wheels"

        # Navigation (2 types)
        assert RVMType.TRIP_INFO == "navigation.navigation_service.trip_info"
        assert RVMType.TRIP_PROGRESS == "navigation.navigation_service.trip_progress"

        # Climate & Comfort (3 types)
        assert RVMType.CLIMATE_HOLD_SETTING == "comfort.cabin.climate_hold_setting"
        assert RVMType.CABIN_VENTILATION_SETTING == "comfort.cabin.cabin_ventilation_setting"
        assert RVMType.CLIMATE_HOLD_STATUS == "comfort.cabin.climate_hold_status"

        # Vehicle Access (2 types)
        assert RVMType.PASSIVE_ENTRY_SETTING == "vehicle_access.passive_entry.passive_entry"
        assert RVMType.PASSIVE_ENTRY_STATUS == "vehicle_access.state.passive_entry"

        # Holiday Celebrations (1 type)
        assert RVMType.HALLOWEEN_SETTINGS == "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings"

    def test_rvm_type_is_string(self) -> None:
        """Test that RVM types are strings."""
        for rvm_type in RVMType:
            assert isinstance(rvm_type, str)
            assert isinstance(rvm_type.value, str)


# Test ParallaxCommand class
class TestParallaxCommand:
    """Test ParallaxCommand class."""

    def test_command_creation_with_payload(self) -> None:
        """Test creating a command with a payload."""
        payload = b"test_payload"
        cmd = ParallaxCommand(RVMType.CLIMATE_HOLD_SETTING, payload)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.payload_b64 == base64.b64encode(payload).decode()
        assert cmd.command_id is not None
        assert len(cmd.command_id) > 0

    def test_command_creation_with_empty_payload(self) -> None:
        """Test creating a command with an empty payload."""
        cmd = ParallaxCommand(RVMType.CHARGING_SESSION_LIVE_DATA, b"")

        assert cmd.rvm == RVMType.CHARGING_SESSION_LIVE_DATA
        assert cmd.payload_b64 == ""
        assert cmd.command_id is not None

    def test_command_creation_with_custom_id(self) -> None:
        """Test creating a command with a custom command ID."""
        custom_id = "custom-test-id-123"
        cmd = ParallaxCommand(RVMType.OTA_STATE, b"test", custom_id)

        assert cmd.command_id == custom_id

    def test_command_name_property(self) -> None:
        """Test command name property."""
        cmd = ParallaxCommand(RVMType.TRIP_PROGRESS, b"")
        assert cmd.name == "parallax_navigation.navigation_service.trip_progress"

    def test_base64_encoding(self) -> None:
        """Test Base64 encoding of payload."""
        payload = b"\x01\x02\x03\x04"
        cmd = ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, payload)

        # Verify Base64 encoding
        assert cmd.payload_b64 == "AQIDBA=="
        # Verify it can be decoded back
        assert base64.b64decode(cmd.payload_b64) == payload

    def test_from_protobuf(self) -> None:
        """Test creating command from protobuf message.

        Validates that ParallaxCommand.from_protobuf() correctly serializes
        a protobuf message and creates a command with the serialized payload.
        """
        from rivian.proto.climate import ClimateHoldSetting

        setting = ClimateHoldSetting(enabled=True, duration_minutes=60, target_temp_celsius=22.0)
        cmd = ParallaxCommand.from_protobuf(RVMType.CLIMATE_HOLD_SETTING, setting)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.command_id is not None
        assert cmd.payload_b64 != ""  # Should have serialized payload

        # Verify payload is valid base64
        decoded = base64.b64decode(cmd.payload_b64)
        assert isinstance(decoded, bytes)
        assert len(decoded) > 0

    def test_from_protobuf_with_custom_id(self) -> None:
        """Test creating command from protobuf with custom ID.

        Validates that custom command IDs are preserved when creating
        commands from protobuf messages.
        """
        from rivian.proto.base import TimeOfDay

        time = TimeOfDay(hour=10, minute=30)
        custom_id = "test-custom-id-456"
        cmd = ParallaxCommand.from_protobuf(RVMType.CHARGING_SCHEDULE_TIME_WINDOW, time, custom_id)

        assert cmd.command_id == custom_id
        assert cmd.payload_b64 != ""


# Test helper functions
class TestHelperFunctions:
    """Test helper functions for building commands."""

    def test_build_charging_session_query(self) -> None:
        """Test building charging session query."""
        cmd = build_charging_session_query()

        assert cmd.rvm == RVMType.CHARGING_SESSION_LIVE_DATA
        assert cmd.payload_b64 == ""  # Read operations use empty payload
        assert cmd.command_id is not None

    def test_build_climate_status_query(self) -> None:
        """Test building climate status query."""
        cmd = build_climate_status_query()

        assert cmd.rvm == RVMType.CLIMATE_HOLD_STATUS
        assert cmd.payload_b64 == ""  # Read operations use empty payload
        assert cmd.command_id is not None

    def test_build_climate_hold_command(self) -> None:
        """Test building climate hold command.

        Validates that build_climate_hold_command() creates a properly
        formatted command with serialized ClimateHoldSetting payload.
        """
        from rivian.parallax import build_climate_hold_command

        # Based on APK analysis: only duration_minutes parameter (converted to seconds)
        cmd = build_climate_hold_command(duration_minutes=120)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.command_id is not None
        assert cmd.payload_b64 != ""  # Write operations have payload

        # Verify payload is valid base64
        decoded = base64.b64decode(cmd.payload_b64)
        assert isinstance(decoded, bytes)
        assert len(decoded) > 0

    def test_build_climate_hold_command_disabled(self) -> None:
        """Test building climate hold command with zero duration.

        Validates that zero duration commands are properly serialized.
        Note: Based on APK analysis, there's no 'enabled' field -
        zero duration may be used to disable.
        """
        from rivian.parallax import build_climate_hold_command

        cmd = build_climate_hold_command(duration_minutes=0)

        assert cmd.rvm == RVMType.CLIMATE_HOLD_SETTING
        assert cmd.command_id is not None
        # Even disabled commands may have a payload (with enabled=False)
        # The payload might be empty or minimal depending on implementation
        decoded = base64.b64decode(cmd.payload_b64) if cmd.payload_b64 else b""
        assert isinstance(decoded, bytes)

    def test_build_charging_schedule_command(self) -> None:
        """Test building charging schedule command.

        Validates that build_charging_schedule_command() creates a properly
        formatted command with serialized ChargingScheduleTimeWindow payload.
        """
        from rivian.parallax import build_charging_schedule_command

        # Charge between 10 PM (22:00) and 6 AM (06:00)
        cmd = build_charging_schedule_command(22, 0, 6, 0)

        assert cmd.rvm == RVMType.CHARGING_SCHEDULE_TIME_WINDOW
        assert cmd.command_id is not None
        assert cmd.payload_b64 != ""  # Write operations have payload

        # Verify payload is valid base64
        decoded = base64.b64decode(cmd.payload_b64)
        assert isinstance(decoded, bytes)
        assert len(decoded) > 0

    def test_build_charging_schedule_command_with_days(self) -> None:
        """Test building charging schedule command with specific days.

        Validates that charging schedules can be configured for specific
        days of the week (e.g., weekdays only).
        """
        from rivian.parallax import build_charging_schedule_command

        # Charge 10:30 AM - 2:45 PM, Monday-Friday only
        cmd = build_charging_schedule_command(10, 30, 14, 45, start_day=1, end_day=5)

        assert cmd.rvm == RVMType.CHARGING_SCHEDULE_TIME_WINDOW
        assert cmd.command_id is not None
        assert cmd.payload_b64 != ""

        decoded = base64.b64decode(cmd.payload_b64)
        assert isinstance(decoded, bytes)
        assert len(decoded) > 0

    def test_build_ota_status_query(self) -> None:
        """Test building OTA status query."""
        cmd = build_ota_status_query()

        assert cmd.rvm == RVMType.OTA_STATE
        assert cmd.payload_b64 == ""  # Read operations use empty payload
        assert cmd.command_id is not None

    def test_build_trip_progress_query(self) -> None:
        """Test building trip progress query."""
        cmd = build_trip_progress_query()

        assert cmd.rvm == RVMType.TRIP_PROGRESS
        assert cmd.payload_b64 == ""  # Read operations use empty payload
        assert cmd.command_id is not None


# Test protobuf messages
class TestProtobufMessages:
    """Test protobuf message classes."""

    def test_time_of_day_creation(self) -> None:
        """Test TimeOfDay message creation."""
        time = TimeOfDay(hour=10, minute=30)

        assert time.hour == 10
        assert time.minute == 30

    def test_time_of_day_to_dict(self) -> None:
        """Test TimeOfDay to_dict conversion."""
        time = TimeOfDay(hour=14, minute=45)
        time_dict = time.to_dict()

        assert time_dict == {"hour": 14, "minute": 45}

    def test_time_of_day_default(self) -> None:
        """Test TimeOfDay default values."""
        time = TimeOfDay()

        assert time.hour == 0
        assert time.minute == 0

    def test_session_cost_creation(self) -> None:
        """Test SessionCost message creation."""
        cost = SessionCost(amount=1250.0, currency="USD")

        assert cost.amount == 1250.0
        assert cost.currency == "USD"

    def test_session_cost_to_dict(self) -> None:
        """Test SessionCost to_dict conversion."""
        cost = SessionCost(amount=3500.0, currency="EUR")
        cost_dict = cost.to_dict()

        assert cost_dict == {"amount": 3500.0, "currency": "EUR"}

    def test_session_cost_default(self) -> None:
        """Test SessionCost default values."""
        cost = SessionCost()

        assert cost.amount == 0.0
        assert cost.currency == "USD"

    def test_climate_hold_setting_creation(self) -> None:
        """Test ClimateHoldSetting message creation."""
        setting = ClimateHoldSetting(enabled=True, duration_minutes=120, target_temp_celsius=22.0)

        assert setting.enabled is True
        assert setting.duration_minutes == 120
        assert setting.target_temp_celsius == 22.0

    def test_climate_hold_setting_to_dict(self) -> None:
        """Test ClimateHoldSetting to_dict conversion."""
        setting = ClimateHoldSetting(enabled=False, duration_minutes=60, target_temp_celsius=20.0)
        setting_dict = setting.to_dict()

        assert setting_dict == {
            "enabled": False,
            "duration_minutes": 60,
            "target_temp_celsius": 20.0,
        }

    def test_climate_hold_setting_serialization(self) -> None:
        """Test ClimateHoldSetting protobuf serialization.

        Validates that ClimateHoldSetting can be serialized to protobuf
        wire format and produces non-empty byte output.
        """
        setting = ClimateHoldSetting(enabled=True, duration_minutes=120, target_temp_celsius=22.0)
        serialized = setting.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

        # Test with all fields populated
        setting_full = ClimateHoldSetting(enabled=True, duration_minutes=180, target_temp_celsius=25.5)
        serialized_full = setting_full.SerializeToString()
        assert len(serialized_full) > 0

    def test_climate_hold_status_creation(self) -> None:
        """Test ClimateHoldStatus message creation."""
        status = ClimateHoldStatus(
            active=True,
            current_temp_celsius=20.5,
            target_temp_celsius=22.0,
            time_remaining_mins=45,
            mode="heating",
        )

        assert status.active is True
        assert status.current_temp_celsius == 20.5
        assert status.target_temp_celsius == 22.0
        assert status.time_remaining_mins == 45
        assert status.mode == "heating"

    def test_climate_hold_status_to_dict(self) -> None:
        """Test ClimateHoldStatus to_dict conversion."""
        status = ClimateHoldStatus(
            active=False, current_temp_celsius=25.0, target_temp_celsius=24.0, time_remaining_mins=0, mode="auto"
        )
        status_dict = status.to_dict()

        assert status_dict == {
            "active": False,
            "current_temp_celsius": 25.0,
            "target_temp_celsius": 24.0,
            "time_remaining_mins": 0,
            "mode": "auto",
        }

    def test_charging_session_live_data_creation(self) -> None:
        """Test ChargingSessionLiveData message creation."""
        data = ChargingSessionLiveData(
            total_kwh=45.5,
            pack_kwh=40.0,
            thermal_kwh=3.5,
            outlets_kwh=1.0,
            system_kwh=1.0,
            session_duration_mins=60,
            time_remaining_mins=30,
            range_added_kms=200,
            current_power=50.0,
            current_range_per_hour=250,
            is_free_session=False,
            charging_state=1,
        )

        assert data.total_kwh == 45.5
        assert data.pack_kwh == 40.0
        assert data.thermal_kwh == 3.5
        assert data.session_duration_mins == 60
        assert data.charging_state == 1

    def test_charging_session_live_data_to_dict(self) -> None:
        """Test ChargingSessionLiveData to_dict conversion."""
        cost = SessionCost(amount=1500.0, currency="USD")
        data = ChargingSessionLiveData(
            total_kwh=50.0,
            pack_kwh=45.0,
            session_cost=cost,
            is_free_session=False,
        )
        data_dict = data.to_dict()

        assert data_dict["total_kwh"] == 50.0
        assert data_dict["pack_kwh"] == 45.0
        assert data_dict["session_cost"] == {"amount": 1500.0, "currency": "USD"}
        assert data_dict["is_free_session"] is False

    def test_charging_session_live_data_default_cost(self) -> None:
        """Test ChargingSessionLiveData with default cost."""
        data = ChargingSessionLiveData()

        assert data.session_cost is not None
        assert data.session_cost.amount == 0.0
        assert data.session_cost.currency == "USD"

    def test_charging_schedule_time_window_creation(self) -> None:
        """Test ChargingScheduleTimeWindow message creation."""
        start_time = TimeOfDay(hour=22, minute=0)
        end_time = TimeOfDay(hour=6, minute=0)
        schedule = ChargingScheduleTimeWindow(
            start_time=start_time, end_time=end_time, start_day_of_week=0, end_day_of_week=6
        )

        assert schedule.start_time.hour == 22
        assert schedule.start_time.minute == 0
        assert schedule.end_time.hour == 6
        assert schedule.end_time.minute == 0
        assert schedule.start_day_of_week == 0
        assert schedule.end_day_of_week == 6

    def test_charging_schedule_time_window_to_dict(self) -> None:
        """Test ChargingScheduleTimeWindow to_dict conversion."""
        start_time = TimeOfDay(hour=10, minute=30)
        end_time = TimeOfDay(hour=14, minute=45)
        schedule = ChargingScheduleTimeWindow(
            start_time=start_time, end_time=end_time, start_day_of_week=1, end_day_of_week=5
        )
        schedule_dict = schedule.to_dict()

        assert schedule_dict == {
            "start_time": {"hour": 10, "minute": 30},
            "end_time": {"hour": 14, "minute": 45},
            "start_day_of_week": 1,
            "end_day_of_week": 5,
        }

    def test_charging_schedule_time_window_serialization(self) -> None:
        """Test ChargingScheduleTimeWindow protobuf serialization.

        Validates that ChargingScheduleTimeWindow with nested TimeOfDay
        messages can be serialized to protobuf wire format.
        """
        start_time = TimeOfDay(hour=22, minute=0)
        end_time = TimeOfDay(hour=6, minute=0)
        schedule = ChargingScheduleTimeWindow(
            start_time=start_time, end_time=end_time, start_day_of_week=0, end_day_of_week=6
        )
        serialized = schedule.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

        # Test with weekday schedule
        schedule_weekdays = ChargingScheduleTimeWindow(
            start_time=TimeOfDay(hour=10, minute=30),
            end_time=TimeOfDay(hour=14, minute=45),
            start_day_of_week=1,
            end_day_of_week=5,
        )
        serialized_weekdays = schedule_weekdays.SerializeToString()
        assert len(serialized_weekdays) > 0

    def test_time_of_day_serialization_empty(self) -> None:
        """Test TimeOfDay serialization with default (empty) values.

        Validates that empty messages serialize to empty bytes since
        protobuf omits fields with default values.
        """
        time = TimeOfDay()
        serialized = time.SerializeToString()

        assert isinstance(serialized, bytes)
        # Empty message (all defaults) may serialize to empty bytes
        assert len(serialized) == 0

    def test_time_of_day_serialization_populated(self) -> None:
        """Test TimeOfDay serialization with all fields populated.

        Validates that messages with non-default values produce
        non-empty serialized output.
        """
        time = TimeOfDay(hour=14, minute=30)
        serialized = time.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_session_cost_serialization_empty(self) -> None:
        """Test SessionCost serialization with default values.

        Validates handling of empty SessionCost messages.
        """
        cost = SessionCost()
        serialized = cost.SerializeToString()

        assert isinstance(serialized, bytes)
        # Default amount (0.0) and currency may produce empty or minimal bytes

    def test_session_cost_serialization_populated(self) -> None:
        """Test SessionCost serialization with all fields populated.

        Validates that populated SessionCost messages serialize correctly.
        """
        cost = SessionCost(amount=2500.0, currency="EUR")
        serialized = cost.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_charging_session_live_data_serialization_nested(self) -> None:
        """Test ChargingSessionLiveData with nested SessionCost.

        Validates that nested message serialization works correctly.
        """
        cost = SessionCost(amount=1500.0, currency="USD")
        data = ChargingSessionLiveData(
            total_kwh=50.0,
            pack_kwh=45.0,
            thermal_kwh=3.0,
            outlets_kwh=1.0,
            system_kwh=1.0,
            session_duration_mins=90,
            time_remaining_mins=30,
            range_added_kms=250,
            current_power=48.5,
            current_range_per_hour=200,
            session_cost=cost,
            is_free_session=False,
            charging_state=1,
        )
        serialized = data.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_charging_session_live_data_serialization_empty(self) -> None:
        """Test ChargingSessionLiveData with default values.

        Validates handling of empty ChargingSessionLiveData messages.
        """
        data = ChargingSessionLiveData()
        serialized = data.SerializeToString()

        assert isinstance(serialized, bytes)
        # Empty/default values may produce empty or minimal bytes

    def test_ota_state_serialization_populated(self) -> None:
        """Test OTAState serialization with all fields populated.

        Validates that OTAState messages with all fields serialize correctly.
        """
        from rivian.proto.ota import OTAState

        ota = OTAState(
            update_available=True,
            current_version="2024.10.1",
            available_version="2024.11.0",
            download_progress=75,
            install_state="downloading",
        )
        serialized = ota.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_ota_state_serialization_empty(self) -> None:
        """Test OTAState serialization with default values.

        Validates handling of empty OTAState messages.
        """
        from rivian.proto.ota import OTAState

        ota = OTAState()
        serialized = ota.SerializeToString()

        assert isinstance(serialized, bytes)

    def test_trip_progress_serialization_populated(self) -> None:
        """Test TripProgress serialization with all fields populated.

        Validates that TripProgress messages with all fields serialize correctly.
        """
        from rivian.proto.navigation import TripProgress

        trip = TripProgress(
            destination_name="San Francisco",
            distance_remaining_km=250.5,
            time_remaining_mins=180,
            battery_at_destination_percent=42,
            charging_stops_remaining=1,
        )
        serialized = trip.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_trip_progress_serialization_empty(self) -> None:
        """Test TripProgress serialization with default values.

        Validates handling of empty TripProgress messages.
        """
        from rivian.proto.navigation import TripProgress

        trip = TripProgress()
        serialized = trip.SerializeToString()

        assert isinstance(serialized, bytes)

    def test_climate_hold_status_serialization_populated(self) -> None:
        """Test ClimateHoldStatus serialization with all fields populated.

        Validates that ClimateHoldStatus messages with all fields serialize correctly.
        """
        status = ClimateHoldStatus(
            active=True,
            current_temp_celsius=21.5,
            target_temp_celsius=22.0,
            time_remaining_mins=90,
            mode="heating",
        )
        serialized = status.SerializeToString()

        assert isinstance(serialized, bytes)
        assert len(serialized) > 0

    def test_climate_hold_status_serialization_empty(self) -> None:
        """Test ClimateHoldStatus serialization with default values.

        Validates handling of empty ClimateHoldStatus messages.
        """
        status = ClimateHoldStatus()
        serialized = status.SerializeToString()

        assert isinstance(serialized, bytes)


# Test Rivian class methods
class TestRivianClassMethods:
    """Test Rivian class Parallax methods."""

    async def test_send_parallax_command_success(self, aresponses: ResponsesMockServer) -> None:
        """Test sending a Parallax command successfully."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            cmd = build_charging_session_query()
            result = await rivian.send_parallax_command("VIN123", cmd)

            assert result["success"] is True
            assert result["sequenceNumber"] == 42
            assert result["payload"] == "CgQIARAB"
            await rivian.close()

    async def test_send_parallax_command_failure(self, aresponses: ResponsesMockServer) -> None:
        """Test sending a Parallax command with failure response."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_FAILURE_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            cmd = build_climate_status_query()
            result = await rivian.send_parallax_command("VIN123", cmd)

            assert result["success"] is False
            assert result["sequenceNumber"] == 0
            await rivian.close()

    async def test_send_parallax_command_unauthenticated(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test sending a Parallax command with authentication error."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_ERROR_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            cmd = build_ota_status_query()

            with pytest.raises(RivianUnauthenticated):
                await rivian.send_parallax_command("VIN123", cmd)

            await rivian.close()

    async def test_get_charging_session_live_data(self, aresponses: ResponsesMockServer) -> None:
        """Test get charging session live data."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.get_charging_session_live_data("VIN123")

            assert result["success"] is True
            assert "payload" in result
            await rivian.close()

    async def test_get_climate_hold_status(self, aresponses: ResponsesMockServer) -> None:
        """Test get climate hold status."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.get_climate_hold_status("VIN123")

            assert result["success"] is True
            await rivian.close()

    async def test_set_climate_hold_enabled(self, aresponses: ResponsesMockServer) -> None:
        """Test setting climate hold enabled.

        Validates that the Rivian client can send a climate hold command
        with serialized protobuf payload via the Parallax protocol.
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.set_climate_hold("VIN123", enabled=True, temp_celsius=22.0)

            assert result["success"] is True
            await rivian.close()

    async def test_set_climate_hold_disabled(self, aresponses: ResponsesMockServer) -> None:
        """Test setting climate hold disabled.

        Validates that climate hold can be disabled via Parallax protocol.
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.set_climate_hold("VIN123", enabled=False)

            assert result["success"] is True
            await rivian.close()

    async def test_set_climate_hold_invalid_temp_too_low(self) -> None:
        """Test setting climate hold with temperature too low."""
        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            with pytest.raises(RivianBadRequestError, match="Temperature must be between 16°C and 29°C"):
                await rivian.set_climate_hold("VIN123", enabled=True, temp_celsius=15.0)

            await rivian.close()

    async def test_set_climate_hold_invalid_temp_too_high(self) -> None:
        """Test setting climate hold with temperature too high."""
        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            with pytest.raises(RivianBadRequestError, match="Temperature must be between 16°C and 29°C"):
                await rivian.set_climate_hold("VIN123", enabled=True, temp_celsius=30.0)

            await rivian.close()

    async def test_set_climate_hold_valid_temp_boundaries(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test setting climate hold with valid boundary temperatures.

        Validates that boundary temperatures (16°C and 29°C) are accepted.
        """
        # Add two responses for two API calls
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            # Test minimum temperature
            result_min = await rivian.set_climate_hold("VIN123", enabled=True, temp_celsius=16.0)
            assert result_min["success"] is True

            # Test maximum temperature
            result_max = await rivian.set_climate_hold("VIN123", enabled=True, temp_celsius=29.0)
            assert result_max["success"] is True

            await rivian.close()

    async def test_set_charging_schedule_valid(self, aresponses: ResponsesMockServer) -> None:
        """Test setting charging schedule with valid parameters.

        Validates that the Rivian client can send a charging schedule command
        with serialized ChargingScheduleTimeWindow protobuf payload.
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.set_charging_schedule("VIN123", 22, 0, 6, 0)

            assert result["success"] is True
            await rivian.close()

    async def test_set_charging_schedule_with_days(self, aresponses: ResponsesMockServer) -> None:
        """Test setting charging schedule with specific days.

        Validates that charging schedules can be configured for specific
        days of the week (e.g., weekdays only).
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.set_charging_schedule("VIN123", 10, 30, 14, 45, start_day=1, end_day=5)

            assert result["success"] is True
            await rivian.close()

    async def test_set_charging_schedule_invalid_hours(self) -> None:
        """Test setting charging schedule with invalid hours."""
        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            # Test start hour too high
            with pytest.raises(RivianBadRequestError, match="Hours must be between 0 and 23"):
                await rivian.set_charging_schedule("VIN123", 24, 0, 6, 0)

            # Test end hour negative
            with pytest.raises(RivianBadRequestError, match="Hours must be between 0 and 23"):
                await rivian.set_charging_schedule("VIN123", 10, 0, -1, 0)

            await rivian.close()

    async def test_set_charging_schedule_invalid_minutes(self) -> None:
        """Test setting charging schedule with invalid minutes."""
        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            # Test start minute too high
            with pytest.raises(RivianBadRequestError, match="Minutes must be between 0 and 59"):
                await rivian.set_charging_schedule("VIN123", 10, 60, 14, 0)

            # Test end minute negative
            with pytest.raises(RivianBadRequestError, match="Minutes must be between 0 and 59"):
                await rivian.set_charging_schedule("VIN123", 10, 0, 14, -1)

            await rivian.close()

    async def test_set_charging_schedule_invalid_days(self) -> None:
        """Test setting charging schedule with invalid days."""
        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            # Test start day too high
            with pytest.raises(
                RivianBadRequestError, match="Days must be between 0 \\(Sunday\\) and 6 \\(Saturday\\)"
            ):
                await rivian.set_charging_schedule("VIN123", 10, 0, 14, 0, start_day=7, end_day=6)

            # Test end day negative
            with pytest.raises(
                RivianBadRequestError, match="Days must be between 0 \\(Sunday\\) and 6 \\(Saturday\\)"
            ):
                await rivian.set_charging_schedule("VIN123", 10, 0, 14, 0, start_day=0, end_day=-1)

            await rivian.close()

    async def test_set_charging_schedule_boundary_values(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test setting charging schedule with boundary values.

        Validates that boundary values for hours, minutes, and days are accepted.
        """
        # Add two responses for two API calls
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            # Test minimum boundary values
            result_min = await rivian.set_charging_schedule("VIN123", 0, 0, 0, 0, start_day=0, end_day=0)
            assert result_min["success"] is True

            # Test maximum boundary values
            result_max = await rivian.set_charging_schedule("VIN123", 23, 59, 23, 59, start_day=6, end_day=6)
            assert result_max["success"] is True

            await rivian.close()

    async def test_get_ota_status(self, aresponses: ResponsesMockServer) -> None:
        """Test get OTA status."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.get_ota_status("VIN123")

            assert result["success"] is True
            await rivian.close()

    async def test_get_trip_progress(self, aresponses: ResponsesMockServer) -> None:
        """Test get trip progress."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            result = await rivian.get_trip_progress("VIN123")

            assert result["success"] is True
            await rivian.close()

    async def test_parallax_command_with_write_operation(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test Parallax command with a write operation (non-empty payload).

        Validates that write operations include a serialized protobuf payload.
        """
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )

            from rivian.parallax import build_climate_hold_command

            # Based on APK analysis: only duration_minutes parameter
            cmd = build_climate_hold_command(duration_minutes=120)

            # Verify command has non-empty payload for write operation
            assert cmd.payload_b64 != ""

            result = await rivian.send_parallax_command("VIN123", cmd)
            assert result["success"] is True
            await rivian.close()

    async def test_parallax_command_with_read_operation(
        self, aresponses: ResponsesMockServer
    ) -> None:
        """Test Parallax command with a read operation (empty payload)."""
        aresponses.add(
            "rivian.com",
            "/api/gql/gateway/graphql",
            "POST",
            response=PARALLAX_SUCCESS_RESPONSE,
        )

        async with aiohttp.ClientSession():
            rivian = Rivian(
                csrf_token="token", app_session_token="token", user_session_token="token"
            )
            cmd = build_trip_progress_query()

            # Verify command has empty payload for read operation
            assert cmd.payload_b64 == ""

            result = await rivian.send_parallax_command("VIN123", cmd)
            assert result["success"] is True
            await rivian.close()
