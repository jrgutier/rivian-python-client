#!/usr/bin/env python3
"""Test Halloween settings using sendVehicleOperation (iOS method)."""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from rivian import Rivian


def load_env_file():
    """Load environment variables from .env file."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return {}

    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value
    return env_vars


def build_halloween_payload(
    enabled: bool = True,
    interior_sound: int = 0,  # 0=default, 1-4=sounds, 6=off
) -> bytes:
    """Build Halloween settings protobuf payload.

    Based on MITM analysis, this builds the raw protobuf bytes.

    Args:
        enabled: Enable Halloween mode
        interior_sound: Interior sound selection (0=default, 1-4=sounds, 6=off)

    Returns:
        Raw protobuf bytes
    """
    def encode_varint(value: int) -> bytes:
        """Encode an integer as a protobuf varint."""
        result = bytearray()
        while value > 0x7F:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    def encode_field_tag(field_number: int, wire_type: int) -> bytes:
        """Encode a field tag (field number + wire type)."""
        tag = (field_number << 3) | wire_type
        return encode_varint(tag)

    def encode_bool_wrapper(field_number: int, value: bool, varint_value: int = 1) -> bytes:
        """Encode a BoolValue wrapper field."""
        if not value:
            return b""

        # Inner message: field 1 = varint_value
        inner = encode_field_tag(1, 0) + encode_varint(varint_value)
        # Outer field
        return encode_field_tag(field_number, 2) + encode_varint(len(inner)) + inner

    def encode_int_wrapper(field_number: int, value: int) -> bytes:
        """Encode an IntValue wrapper field."""
        if value == 0:
            # Empty field
            return encode_field_tag(field_number, 2) + encode_varint(0)

        # Inner message: field 1 = value
        inner = encode_field_tag(1, 0) + encode_varint(value)
        # Outer field
        return encode_field_tag(field_number, 2) + encode_varint(len(inner)) + inner

    def encode_string(field_number: int, value: str) -> bytes:
        """Encode a string field."""
        if not value:
            return encode_field_tag(field_number, 2) + encode_varint(0)
        value_bytes = value.encode("utf-8")
        return encode_field_tag(field_number, 2) + encode_varint(len(value_bytes)) + value_bytes

    def encode_varint_field(field_number: int, value: int) -> bytes:
        """Encode a varint field."""
        return encode_field_tag(field_number, 0) + encode_varint(value)

    output = bytearray()

    if enabled:
        # Halloween ON with optional custom sound
        output.extend(encode_bool_wrapper(1, True, 5))   # Field 1: 5
        output.extend(encode_bool_wrapper(2, True, 13))  # Field 2: 13
        output.extend(encode_bool_wrapper(3, True, 1))   # Field 3: light_show_enabled
        output.extend(encode_bool_wrapper(4, True, 1))   # Field 4: motion_detection

        if interior_sound > 0:
            # Custom sound mode
            output.extend(encode_int_wrapper(5, interior_sound))  # Interior sound selection
            output.extend(encode_varint_field(6, 4))              # Mode = 4 (custom)
            output.extend(encode_bool_wrapper(7, True, 1))
            output.extend(encode_bool_wrapper(8, True, 1))
            output.extend(encode_bool_wrapper(9, True, 1))
            output.extend(encode_string(10, ""))
            output.extend(encode_int_wrapper(11, 10))             # Sound setting
            output.extend(encode_int_wrapper(12, 2))
        else:
            # Default mode (no custom sound)
            output.extend(encode_int_wrapper(5, 0))               # Empty/default sound
            output.extend(encode_varint_field(6, 1))              # Mode = 1 (normal)
            output.extend(encode_bool_wrapper(7, True, 1))
            output.extend(encode_bool_wrapper(8, True, 1))
            output.extend(encode_bool_wrapper(9, True, 1))
            output.extend(encode_string(10, ""))
            output.extend(encode_string(11, ""))
            output.extend(encode_int_wrapper(12, 2))
    else:
        # Halloween OFF
        output.extend(encode_string(1, ""))                    # Empty
        output.extend(encode_string(2, ""))                    # Empty
        output.extend(encode_string(3, ""))                    # Empty
        output.extend(encode_bool_wrapper(4, True, 1))
        output.extend(encode_int_wrapper(5, 6))                # 6 = OFF
        output.extend(encode_varint_field(6, 4))               # Mode = 4
        output.extend(encode_bool_wrapper(7, True, 1))
        output.extend(encode_string(8, ""))
        output.extend(encode_string(9, ""))
        output.extend(encode_string(10, ""))
        output.extend(encode_int_wrapper(11, 10))
        output.extend(encode_int_wrapper(12, 2))

    return bytes(output)


async def main():
    """Test Halloween settings."""
    env_vars = load_env_file()

    access_token = env_vars.get("RIVIAN_ACCESS_TOKEN") or os.getenv("RIVIAN_ACCESS_TOKEN")
    refresh_token = env_vars.get("RIVIAN_REFRESH_TOKEN") or os.getenv("RIVIAN_REFRESH_TOKEN")
    user_session_token = env_vars.get("RIVIAN_USER_SESSION_TOKEN") or os.getenv("RIVIAN_USER_SESSION_TOKEN")

    if not access_token or not user_session_token:
        print("ERROR: RIVIAN_ACCESS_TOKEN and RIVIAN_USER_SESSION_TOKEN must be set in .env file")
        return

    print("=" * 80)
    print("Testing Halloween Settings with sendVehicleOperation (iOS method)")
    print("=" * 80)

    client = Rivian(
        access_token=access_token,
        refresh_token=refresh_token,
        user_session_token=user_session_token,
    )

    try:
        # Get user information
        print(f"\n[{datetime.now()}] Getting user information...")
        user_info = await client.get_user_information(include_phones=True)

        vehicle_id = user_info["vehicles"][0]["id"]
        print(f"✓ Vehicle ID: {vehicle_id}")

        phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
        phone_id_hex_clean = "".join(c for c in phone_id_hex if c in "0123456789abcdefABCDEF")
        phone_id = bytes.fromhex(phone_id_hex_clean)
        print(f"✓ Phone ID: {phone_id_hex[:32]}... ({len(phone_id)} bytes)")

        # Test 1: Enable Halloween mode (default sounds)
        print(f"\n[{datetime.now()}] Test 1: Enable Halloween mode (default sounds)...")
        try:
            payload = build_halloween_payload(enabled=True, interior_sound=0)
            print(f"Payload hex: {payload.hex()}")
            print(f"Payload size: {len(payload)} bytes")

            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings",
                payload=payload,
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        # Wait before next test
        print("\nWaiting 3 seconds...")
        await asyncio.sleep(3)

        # Test 2: Enable with interior sound #1
        print(f"\n[{datetime.now()}] Test 2: Enable with interior sound #1...")
        try:
            payload = build_halloween_payload(enabled=True, interior_sound=1)
            print(f"Payload hex: {payload.hex()}")
            print(f"Payload size: {len(payload)} bytes")

            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings",
                payload=payload,
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        # Wait before next test
        print("\nWaiting 3 seconds...")
        await asyncio.sleep(3)

        # Test 3: Disable Halloween mode
        print(f"\n[{datetime.now()}] Test 3: Disable Halloween mode...")
        try:
            payload = build_halloween_payload(enabled=False)
            print(f"Payload hex: {payload.hex()}")
            print(f"Payload size: {len(payload)} bytes")

            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings",
                payload=payload,
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        print(f"\n[{datetime.now()}] All tests completed!")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
