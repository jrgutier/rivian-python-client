#!/usr/bin/env python3
"""Verify that existing v2.0 API methods still work correctly."""

import asyncio
import os
import sys

from dotenv import load_dotenv

from rivian import Rivian
from rivian.exceptions import RivianApiException


async def main() -> None:
    """Test existing v2.0 methods."""
    load_dotenv()

    access_token = os.getenv("RIVIAN_ACCESS_TOKEN", "")
    refresh_token = os.getenv("RIVIAN_REFRESH_TOKEN", "")
    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN", "")
    vehicle_id = os.getenv("RIVIAN_VEHICLE_ID", "")

    print("Testing existing v2.0 API methods...")
    print("=" * 60)

    try:
        async with Rivian(
            access_token=access_token,
            refresh_token=refresh_token,
            user_session_token=user_session_token,
        ) as client:
            # Test 1: Get user information
            print("\n✓ Testing: get_user_information()")
            user_info = await client.get_user_information()
            print(f"  User ID: {user_info.get('id')}")
            print(f"  Vehicles: {len(user_info.get('vehicles', []))}")

            # Test 2: Get registered wallboxes
            print("\n✓ Testing: get_registered_wallboxes()")
            wallboxes = await client.get_registered_wallboxes()
            print(f"  Wallboxes: {len(wallboxes)}")

            # Test 3: Get drivers and keys
            print("\n✓ Testing: get_drivers_and_keys()")
            drivers = await client.get_drivers_and_keys(vehicle_id)
            print(f"  VIN: {drivers.get('vin')}")
            print(f"  Invited users: {len(drivers.get('invitedUsers', []))}")

            # Test 4: Get vehicle images
            print("\n✓ Testing: get_vehicle_images()")
            images = await client.get_vehicle_images(extension="png", resolution="@2x")
            mobile_images = len(images.get('getVehicleMobileImages', []))
            print(f"  Mobile images: {mobile_images}")

            print("\n" + "=" * 60)
            print("✅ All existing v2.0 methods work correctly!")
            print("=" * 60)

    except RivianApiException as e:
        print(f"\n❌ API Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
