#!/usr/bin/env python3
"""Test climate hold with sendVehicleOperation mutation (iOS app method)."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

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


async def main():
    """Test climate hold duration changes."""
    print("=" * 80)
    print("Climate Hold Test with sendVehicleOperation (iOS method)")
    print("=" * 80)

    # Load credentials from .env file
    env_vars = load_env_file()

    access_token = env_vars.get("RIVIAN_ACCESS_TOKEN") or os.getenv("RIVIAN_ACCESS_TOKEN")
    refresh_token = env_vars.get("RIVIAN_REFRESH_TOKEN") or os.getenv("RIVIAN_REFRESH_TOKEN")
    user_session_token = env_vars.get("RIVIAN_USER_SESSION_TOKEN") or os.getenv("RIVIAN_USER_SESSION_TOKEN")

    if not access_token or not user_session_token:
        print("ERROR: RIVIAN_ACCESS_TOKEN and RIVIAN_USER_SESSION_TOKEN must be set in .env file")
        return

    # Create client with existing tokens
    client = Rivian(
        access_token=access_token,
        refresh_token=refresh_token,
        user_session_token=user_session_token,
    )

    try:
        print(f"\n[{datetime.now()}] Using existing tokens from .env...")

        # Get user information with enrolled phones
        print(f"\n[{datetime.now()}] Getting user information...")
        user_info = await client.get_user_information(include_phones=True)

        # Extract vehicle ID and phone ID
        if not user_info.get("vehicles"):
            print("ERROR: No vehicles found")
            return

        vehicle_id = user_info["vehicles"][0]["id"]
        print(f"✓ Vehicle ID: {vehicle_id}")

        if not user_info.get("enrolledPhones"):
            print("ERROR: No enrolled phones found. You must enroll a phone first.")
            print("Use the enroll_phone() method to enroll this device.")
            return

        phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
        # Remove any non-hex characters (dashes, spaces, etc.)
        phone_id_hex_clean = "".join(c for c in phone_id_hex if c in "0123456789abcdefABCDEF")
        phone_id = bytes.fromhex(phone_id_hex_clean)
        print(f"✓ Phone ID: {phone_id_hex[:32]}... ({len(phone_id)} bytes)")

        # Test 1: Set climate hold to 8 hours (480 minutes)
        print(f"\n[{datetime.now()}] Test 1: Setting climate hold to 8 hours (480 minutes)...")
        try:
            result = await client.set_climate_hold(
                vehicle_id=vehicle_id,
                duration_minutes=480,
                phone_id=phone_id,
            )
            print(f"✓ Result: {result}")
            if result.get("success"):
                print("✓ Climate hold set to 8 hours successfully")
            else:
                print("✗ Failed to set climate hold")
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

        # Wait a bit before next test
        print("\nWaiting 5 seconds before next test...")
        await asyncio.sleep(5)

        # Test 2: Set climate hold to 2 hours (120 minutes)
        print(f"\n[{datetime.now()}] Test 2: Setting climate hold to 2 hours (120 minutes)...")
        try:
            result = await client.set_climate_hold(
                vehicle_id=vehicle_id,
                duration_minutes=120,
                phone_id=phone_id,
            )
            print(f"✓ Result: {result}")
            if result.get("success"):
                print("✓ Climate hold set to 2 hours successfully")
            else:
                print("✗ Failed to set climate hold")
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

        # Test 3: Test the low-level send_vehicle_operation method directly
        print(f"\n[{datetime.now()}] Test 3: Testing low-level send_vehicle_operation...")
        try:
            from rivian.proto.rivian_climate_pb2 import ClimateHoldSetting

            # Create protobuf message for 4 hours (240 minutes = 14400 seconds)
            setting = ClimateHoldSetting(hold_time_duration_seconds=14400)
            payload = setting.SerializeToString()

            print(f"Payload size: {len(payload)} bytes")
            print(f"Payload hex: {payload.hex()}")

            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="comfort.cabin.climate_hold_setting",
                payload=payload,
                phone_id=phone_id,
            )

            print(f"✓ Result: {result}")
            if result.get("success"):
                print("✓ Climate hold set to 4 hours successfully (low-level)")
            else:
                print("✗ Failed to set climate hold (low-level)")
        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

        print(f"\n[{datetime.now()}] All tests completed!")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
