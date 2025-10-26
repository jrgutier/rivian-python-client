"""Tests for `rivian.rivian`."""

# pylint: disable=protected-access
from __future__ import annotations

from typing import Any

import aiohttp
import pytest
from aresponses import ResponsesMockServer
from rivian import Rivian
from rivian.exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianBadRequestError,
    RivianDataError,
    RivianInvalidOTP,
    RivianPhoneLimitReachedError,
    RivianTemporarilyLockedError,
    RivianUnauthenticated,
)

from .responses import (
    AUTHENTICATION_OTP_RESPONSE,
    AUTHENTICATION_RESPONSE,
    CSRF_TOKEN_RESPONSE,
    DISENROLL_PHONE_RESPONSE,
    ENROLL_PHONE_RESPONSE,
    MOCK_GET_CHARGING_SCHEDULES_RESPONSE,
    OTP_TOKEN_RESPONSE,
    SEND_LOCATION_TO_VEHICLE_RESPONSE,
    SEND_VEHICLE_COMMAND_RESPONSE,
    USER_INFORMATION_RESPONSE,
    WALLBOXES_RESPONSE,
    error_response,
    load_response,
)


async def test_csrf_token_request(aresponses: ResponsesMockServer) -> None:
    """Test CSRF token request."""
    aresponses.add(
        "rivian.com", "/api/gql/gateway/graphql", "POST", response=CSRF_TOKEN_RESPONSE
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        await rivian.create_csrf_token()
        assert rivian._csrf_token == "valid_csrf_token"
        assert rivian._app_session_token == "valid_app_session_token"
        await rivian.close()


async def test_authentication(aresponses: ResponsesMockServer) -> None:
    """Test authentication."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=AUTHENTICATION_RESPONSE,
    )
    async with aiohttp.ClientSession():
        async with Rivian(csrf_token="token", app_session_token="token") as rivian:
            await rivian.authenticate("username", "password")
            assert rivian._access_token == "valid_access_token"
            assert rivian._refresh_token == "valid_refresh_token"
            assert rivian._user_session_token == "valid_user_session_token"


async def test_invalid_authentication(aresponses: ResponsesMockServer) -> None:
    """Test invalid authentication."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=error_response("UNAUTHENTICATED", "UNAUTHENTICATED"),
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(csrf_token="token", app_session_token="token")
        with pytest.raises(RivianUnauthenticated):
            await rivian.authenticate("username", "bad_password")
        await rivian.close()


async def test_authentication_with_otp(aresponses: ResponsesMockServer) -> None:
    """Test authentication with OTP enabled."""
    aresponses.add(
        "rivian.com", "/api/gql/gateway/graphql", "POST", response=OTP_TOKEN_RESPONSE
    )
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=AUTHENTICATION_OTP_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(csrf_token="token", app_session_token="token")
        await rivian.authenticate("username", "password")
        assert rivian._otp_needed
        assert rivian._otp_token == "token"

        await rivian.validate_otp("username", "code")
        assert rivian._access_token == "token"
        assert rivian._refresh_token == "token"
        assert rivian._user_session_token == "token"
        await rivian.close()


async def test_authentication_with_expired_otp(aresponses: ResponsesMockServer) -> None:
    """Test authentication with expired OTP token."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=error_response("UNAUTHENTICATED", "OTP_TOKEN_EXPIRED"),
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(csrf_token="token", app_session_token="token")
        rivian._otp_needed = True
        rivian._otp_token = "token"

        with pytest.raises(RivianInvalidOTP):
            await rivian.validate_otp("username", "expired_code")
        await rivian.close()


async def test_login(aresponses: ResponsesMockServer) -> None:
    """Test login without MFA (successful login)."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=AUTHENTICATION_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        otp_token = await rivian.login("username", "password")
        assert otp_token is None
        assert rivian._access_token == "valid_access_token"
        assert rivian._refresh_token == "valid_refresh_token"
        assert rivian._user_session_token == "valid_user_session_token"
        assert rivian._otp_needed is False
        await rivian.close()


async def test_login_with_mfa(aresponses: ResponsesMockServer) -> None:
    """Test login with MFA enabled (returns OTP token)."""
    aresponses.add(
        "rivian.com", "/api/gql/gateway/graphql", "POST", response=OTP_TOKEN_RESPONSE
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        otp_token = await rivian.login("username", "password")
        assert otp_token == "token"
        assert rivian._otp_needed is True
        assert rivian._otp_token == "token"
        await rivian.close()


async def test_login_with_otp(aresponses: ResponsesMockServer) -> None:
    """Test OTP validation with login_with_otp."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=AUTHENTICATION_OTP_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        rivian._otp_token = "token"
        await rivian.login_with_otp("username", "123456")
        assert rivian._access_token == "token"
        assert rivian._refresh_token == "token"
        assert rivian._user_session_token == "token"
        await rivian.close()


async def test_get_user_information(aresponses: ResponsesMockServer) -> None:
    """Test get user information request."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=USER_INFORMATION_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        user_data = await rivian.get_user_information()
        assert user_data["id"] == "id"
        assert user_data["firstName"] == "firstName"
        assert user_data["lastName"] == "lastName"
        assert user_data["email"] == "email"
        assert len(user_data["vehicles"]) == 1
        await rivian.close()


async def test_get_registered_wallboxes(aresponses: ResponsesMockServer) -> None:
    """Test GraphQL Response for a getRegisteredWallboxes request"""
    aresponses.add(
        "rivian.com", "/api/gql/chrg/user/graphql", "POST", response=WALLBOXES_RESPONSE
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        wallboxes = await rivian.get_registered_wallboxes()
        assert isinstance(wallboxes, list)
        assert len(wallboxes) == 1
        assert wallboxes[0]["wallboxId"] == "W1-1113-3RV7-1-1234-00012"
        assert wallboxes[0]["name"] == "Wall Charger"
        assert wallboxes[0]["linked"] is True
        await rivian.close()


async def test_graphql_errors(aresponses: ResponsesMockServer) -> None:
    """Test GraphQL error responses."""
    host = "rivian.com"
    path = "/api/gql/gateway/graphql"

    aresponses.add(host, path, "POST", response=error_response("RATE_LIMIT"))
    async with aiohttp.ClientSession():
        rivian = Rivian(user_session_token="token")
        with pytest.raises(RivianApiRateLimitError):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(host, path, "POST", response=error_response("DATA_ERROR"))
    async with aiohttp.ClientSession():
        rivian = Rivian(user_session_token="token")
        with pytest.raises(RivianDataError):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(host, path, "POST", response=error_response("SESSION_MANAGER_ERROR"))
    async with aiohttp.ClientSession():
        rivian = Rivian(user_session_token="token")
        with pytest.raises(RivianTemporarilyLockedError):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(host, path, "POST", response=error_response())
    async with aiohttp.ClientSession():
        rivian = Rivian(user_session_token="token")
        with pytest.raises(RivianApiException):
            await rivian.get_user_information()
        await rivian.close()

    aresponses.add(
        host, path, "POST", response=error_response("BAD_USER_INPUT", "INVALID_OTP")
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()
        with pytest.raises(RivianInvalidOTP):
            await rivian.authenticate("", "")
        await rivian.close()


async def test_get_drivers_and_keys(aresponses: ResponsesMockServer) -> None:
    """Test get drivers and keys."""
    host = "rivian.com"
    path = "/api/gql/gateway/graphql"

    aresponses.add(
        host, path, "POST", response=load_response("drivers_and_keys_success")
    )
    async with aiohttp.ClientSession():
        rivian = Rivian()

        drivers_and_keys = await rivian.get_drivers_and_keys(vehicle_id="vehicleId")
        assert drivers_and_keys["id"] == "id"
        assert len(drivers_and_keys["invitedUsers"]) == 4
        await rivian.close()


async def test_enroll_phone(aresponses: ResponsesMockServer) -> None:
    """Test phone enrollment."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=ENROLL_PHONE_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        success = await rivian.enroll_phone(
            user_id="user-123",
            vehicle_id="vehicle-456",
            device_type="phone/rivian",
            device_name="Test Phone",
            public_key="test-public-key",
        )
        assert success is True
        await rivian.close()


async def test_enroll_phone_limit_reached(aresponses: ResponsesMockServer) -> None:
    """Test phone enrollment when limit is reached."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=error_response("CONFLICT", "ENROLL_PHONE_LIMIT_REACHED"),
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        with pytest.raises(RivianPhoneLimitReachedError):
            await rivian.enroll_phone(
                user_id="user-123",
                vehicle_id="vehicle-456",
                device_type="phone/rivian",
                device_name="Test Phone",
                public_key="test-public-key",
            )
        await rivian.close()


async def test_disenroll_phone(aresponses: ResponsesMockServer) -> None:
    """Test phone disenrollment."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=DISENROLL_PHONE_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        success = await rivian.disenroll_phone(identity_id="identity-123")
        assert success is True
        await rivian.close()


async def test_send_vehicle_command_without_params(
    aresponses: ResponsesMockServer,
) -> None:
    """Test sending vehicle command without params."""
    # Use valid test keys from utils_test.py
    private_key = "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JR0hBZ0VBTUJNR0J5cUdTTTQ5QWdFR0NDcUdTTTQ5QXdFSEJHMHdhd0lCQVFRZ0tzMzNEek8rbjBZbVI1RFUKNUFIb2N6cUw1RlBXdUZSZ2E4ano1QVZmbWl5aFJBTkNBQVRIL2lQSmxtbTh5RjdsUFJOYlcvZFFDTDJseVpjWQo4U0dKcGpNQ1k4WkhCa0xXV3hoSTZ6RVFTdW5QaUM0Vy9zYUpPVW5EVm15N1Vkbm1EOCtzOCtFNAotLS0tLUVORCBQUklWQVRFIEtFWS0tLS0tCg=="
    vehicle_key = "04334cc40a88768920b54bdfdcd38238df2ec65ce3605a1d343ef2ab8c1a1daa0545cbb804ebf3ab89826924ea3011352b1d23957a52de0acd5a326078d222d31c"

    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=SEND_VEHICLE_COMMAND_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        command_id = await rivian.send_vehicle_command(
            command="WAKE_VEHICLE",
            vehicle_id="vehicle-123",
            phone_id="phone-456",
            identity_id="identity-789",
            vehicle_key=vehicle_key,
            private_key=private_key,
        )
        assert command_id == "command-id-123"
        await rivian.close()


async def test_send_vehicle_command_with_params(
    aresponses: ResponsesMockServer,
) -> None:
    """Test sending vehicle command with params."""
    # Use valid test keys from utils_test.py
    private_key = "LS0tLS1CRUdJTiBQUklWQVRFIEtFWS0tLS0tCk1JR0hBZ0VBTUJNR0J5cUdTTTQ5QWdFR0NDcUdTTTQ5QXdFSEJHMHdhd0lCQVFRZ0tzMzNEek8rbjBZbVI1RFUKNUFIb2N6cUw1RlBXdUZSZ2E4ano1QVZmbWl5aFJBTkNBQVRIL2lQSmxtbTh5RjdsUFJOYlcvZFFDTDJseVpjWQo4U0dKcGpNQ1k4WkhCa0xXV3hoSTZ6RVFTdW5QaUM0Vy9zYUpPVW5EVm15N1Vkbm1EOCtzOCtFNAotLS0tLUVORCBQUklWQVRFIEtFWS0tLS0tCg=="
    vehicle_key = "04334cc40a88768920b54bdfdcd38238df2ec65ce3605a1d343ef2ab8c1a1daa0545cbb804ebf3ab89826924ea3011352b1d23957a52de0acd5a326078d222d31c"

    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=SEND_VEHICLE_COMMAND_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        command_id = await rivian.send_vehicle_command(
            command="CHARGING_LIMITS",
            vehicle_id="vehicle-123",
            phone_id="phone-456",
            identity_id="identity-789",
            vehicle_key=vehicle_key,
            private_key=private_key,
            params={"SOC_limit": 80},
        )
        assert command_id == "command-id-123"
        await rivian.close()


async def test_send_location_to_vehicle(aresponses: ResponsesMockServer) -> None:
    """Test sending location to vehicle."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=SEND_LOCATION_TO_VEHICLE_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        result = await rivian.send_location_to_vehicle(
            location_str="123 Main St, Springfield, IL 62701",
            vehicle_id="vehicle-123",
        )
        assert result["publishResponse"]["result"] == 0
        await rivian.close()


async def test_validate_vehicle_command_charging_limits_invalid() -> None:
    """Test vehicle command validation for invalid charging limits."""
    rivian = Rivian()

    # Test SOC_limit too low
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CHARGING_LIMITS", {"SOC_limit": 45})

    # Test SOC_limit too high
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CHARGING_LIMITS", {"SOC_limit": 101})

    # Test missing SOC_limit
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CHARGING_LIMITS", {})

    # Test valid SOC_limit should not raise
    rivian._validate_vehicle_command("CHARGING_LIMITS", {"SOC_limit": 80})

    await rivian.close()


async def test_validate_vehicle_command_hvac_levels_invalid() -> None:
    """Test vehicle command validation for invalid HVAC levels."""
    rivian = Rivian()

    # Test level too low
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CABIN_HVAC_LEFT_SEAT_HEAT", {"level": -1})

    # Test level too high
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CABIN_HVAC_RIGHT_SEAT_VENT", {"level": 5})

    # Test missing level
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CABIN_HVAC_STEERING_HEAT", {})

    # Test valid levels should not raise
    for level in range(5):  # 0-4 inclusive
        rivian._validate_vehicle_command("CABIN_HVAC_LEFT_SEAT_HEAT", {"level": level})

    await rivian.close()


async def test_validate_vehicle_command_temp_invalid() -> None:
    """Test vehicle command validation for invalid temperature settings."""
    rivian = Rivian()

    # Test temp too low (not LO)
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command(
            "CABIN_PRECONDITIONING_SET_TEMP", {"HVAC_set_temp": 15}
        )

    # Test temp too high (not HI)
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command(
            "CABIN_PRECONDITIONING_SET_TEMP", {"HVAC_set_temp": 30}
        )

    # Test missing temp
    with pytest.raises(RivianBadRequestError):
        rivian._validate_vehicle_command("CABIN_PRECONDITIONING_SET_TEMP", {})

    # Test valid temps should not raise
    rivian._validate_vehicle_command(
        "CABIN_PRECONDITIONING_SET_TEMP", {"HVAC_set_temp": 20}
    )
    rivian._validate_vehicle_command(
        "CABIN_PRECONDITIONING_SET_TEMP", {"HVAC_set_temp": 0}
    )  # LO
    rivian._validate_vehicle_command(
        "CABIN_PRECONDITIONING_SET_TEMP", {"HVAC_set_temp": 63.5}
    )  # HI

    await rivian.close()


async def test_subscribe_for_charging_session() -> None:
    """Test WebSocket subscription for charging session updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        unsubscribe = await rivian.subscribe_for_charging_session(
            vehicle_id="test-vehicle-123", callback=test_callback
        )

        # In test environment without WebSocket server, should return None
        assert unsubscribe is None

        await rivian.close()


async def test_subscribe_for_cloud_connection() -> None:
    """Test WebSocket subscription for cloud connection updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        unsubscribe = await rivian.subscribe_for_cloud_connection(
            vehicle_id="test-vehicle-123", callback=test_callback
        )

        # In test environment without WebSocket server, should return None
        assert unsubscribe is None

        await rivian.close()


async def test_subscribe_for_command_state() -> None:
    """Test WebSocket subscription for command state updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        # Note: This method takes command_id instead of vehicle_id
        unsubscribe = await rivian.subscribe_for_command_state(
            command_id="test-command-123", callback=test_callback
        )

        # In test environment without WebSocket server, should return None
        assert unsubscribe is None

        await rivian.close()


async def test_subscribe_for_gear_guard_config() -> None:
    """Test WebSocket subscription for Gear Guard config updates."""
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )

        # Create a simple callback to track if it's called
        callback_called = False

        def test_callback(data: dict[str, Any]) -> None:
            nonlocal callback_called
            callback_called = True

        # Test that method can be called and returns None on error (no actual WebSocket server)
        # The method is designed to return None when connection fails
        unsubscribe = await rivian.subscribe_for_gear_guard_config(
            vehicle_id="test-vehicle-123", callback=test_callback
        )

        # In test environment without WebSocket server, should return None
        assert unsubscribe is None

        await rivian.close()


async def test_refresh_csrf_token(aresponses: ResponsesMockServer) -> None:
    """Test CSRF token refresh."""
    aresponses.add(
        "rivian.com", "/api/gql/gateway/graphql", "POST", response=CSRF_TOKEN_RESPONSE
    )

    async with aiohttp.ClientSession():
        rivian = Rivian()

        await rivian.refresh_csrf_token()

        assert rivian._csrf_token == "valid_csrf_token"
        assert rivian._app_session_token == "valid_app_session_token"
        assert rivian._csrf_refreshed_at > 0

        await rivian.close()


async def test_needs_token_refresh() -> None:
    """Test token refresh age checking."""
    import time

    async with aiohttp.ClientSession():
        # Test with no tokens
        rivian = Rivian()
        assert rivian.needs_token_refresh() is True

        # Test with fresh tokens
        rivian = Rivian(
            access_token="token",
            refresh_token="token",
        )
        rivian._token_refreshed_at = time.time()
        assert rivian.needs_token_refresh(max_age_seconds=3600) is False

        # Test with old tokens
        rivian._token_refreshed_at = time.time() - 7200  # 2 hours ago
        assert rivian.needs_token_refresh(max_age_seconds=3600) is True

        await rivian.close()


async def test_needs_csrf_refresh() -> None:
    """Test CSRF refresh age checking."""
    import time

    async with aiohttp.ClientSession():
        # Test with no CSRF
        rivian = Rivian()
        assert rivian.needs_csrf_refresh() is True

        # Test with fresh CSRF
        rivian = Rivian(csrf_token="token", app_session_token="token")
        rivian._csrf_refreshed_at = time.time()
        assert rivian.needs_csrf_refresh(max_age_seconds=7200) is False

        # Test with old CSRF
        rivian._csrf_refreshed_at = time.time() - 10800  # 3 hours ago
        assert rivian.needs_csrf_refresh(max_age_seconds=7200) is True

        await rivian.close()


async def test_get_charging_schedules(aresponses: ResponsesMockServer) -> None:
    """Test get charging schedules request."""
    aresponses.add(
        "rivian.com",
        "/api/gql/gateway/graphql",
        "POST",
        response=MOCK_GET_CHARGING_SCHEDULES_RESPONSE,
    )
    async with aiohttp.ClientSession():
        rivian = Rivian(
            csrf_token="token", app_session_token="token", user_session_token="token"
        )
        schedules_data = await rivian.get_charging_schedules(vehicle_id="vehicle_abc")

        # Verify top-level structure
        assert schedules_data["vehicleId"] == "vehicle_abc"
        assert schedules_data["smartChargingEnabled"] is True
        assert "schedules" in schedules_data
        assert len(schedules_data["schedules"]) == 2

        # Verify first schedule (Weekday Commute)
        schedule1 = schedules_data["schedules"][0]
        assert schedule1["id"] == "schedule_123"
        assert schedule1["name"] == "Weekday Commute"
        assert schedule1["enabled"] is True
        assert schedule1["days"] == [
            "MONDAY",
            "TUESDAY",
            "WEDNESDAY",
            "THURSDAY",
            "FRIDAY",
        ]
        assert schedule1["departureTime"] == "08:00"
        assert schedule1["cabinPreconditioning"] is True
        assert schedule1["cabinPreconditioningTemp"] == 21.0
        assert schedule1["targetSOC"] == 80
        assert schedule1["offPeakHoursOnly"] is False
        assert schedule1["location"]["latitude"] == 37.7749
        assert schedule1["location"]["longitude"] == -122.4194
        assert schedule1["location"]["radius"] == 100.0

        # Verify second schedule (Weekend Trip)
        schedule2 = schedules_data["schedules"][1]
        assert schedule2["id"] == "schedule_456"
        assert schedule2["name"] == "Weekend Trip"
        assert schedule2["enabled"] is False
        assert schedule2["days"] == ["SATURDAY", "SUNDAY"]
        assert schedule2["departureTime"] == "10:00"
        assert schedule2["cabinPreconditioning"] is False
        assert schedule2["cabinPreconditioningTemp"] is None
        assert schedule2["targetSOC"] == 100
        assert schedule2["offPeakHoursOnly"] is True
        assert schedule2["location"] is None

        await rivian.close()


async def test_bearer_token_never_sent() -> None:
    """Test that Bearer tokens are never sent, matching Android app behavior.

    The official Android app (com.rivian.android.consumer) uses only session
    tokens (U-Sess) for authentication and never sends Authorization: Bearer.
    This prevents UNAUTHENTICATED errors and matches production behavior.
    """
    async with aiohttp.ClientSession():
        rivian = Rivian(
            access_token="access_token",
            csrf_token="csrf_token",
            app_session_token="app_session_token",
            user_session_token="user_session_token",
        )

        # Verify Bearer token is never included, even with valid access token
        await rivian._ensure_client()
        assert rivian._gql_transport is not None
        headers = rivian._gql_transport.headers

        # Bearer token should NOT be present (matches Android app)
        assert "Authorization" not in headers

        # But session tokens should be present
        assert headers["Csrf-Token"] == "csrf_token"
        assert headers["A-Sess"] == "app_session_token"
        assert headers["U-Sess"] == "user_session_token"

        await rivian.close()
