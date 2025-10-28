#!/usr/bin/env python3
"""Test share_location_to_vehicle with various location formats."""

import asyncio
import os

from dotenv import load_dotenv

from rivian import Rivian


async def main() -> None:
    """Test location sharing with different formats."""
    load_dotenv()

    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN", "")
    vehicle_id = "01-276948064"

    print("Testing share_location_to_vehicle with various formats...")
    print("=" * 60)

    async with Rivian(user_session_token=user_session_token) as client:
        # Test 1: Address
        print("\n1. Testing with address...")
        try:
            result = await client.share_location_to_vehicle(
                vehicle_id, location="Rivian Headquarters, Irvine CA"
            )
            status = result.get("publishResponse", {}).get("result")
            print(f"   ✅ Address sent! Status: {status}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        # Test 2: Landmark
        print("\n2. Testing with landmark...")
        try:
            result = await client.share_location_to_vehicle(
                vehicle_id, location="Golden Gate Bridge"
            )
            status = result.get("publishResponse", {}).get("result")
            print(f"   ✅ Landmark sent! Status: {status}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        # Test 3: Coordinates (new format)
        print("\n3. Testing with lat/lon parameters...")
        try:
            result = await client.share_location_to_vehicle(
                vehicle_id, latitude=37.7749, longitude=-122.4194
            )
            status = result.get("publishResponse", {}).get("result")
            print(f"   ✅ Coordinates sent! Status: {status}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        # Test 4: Coordinate string
        print("\n4. Testing with coordinate string...")
        try:
            result = await client.share_location_to_vehicle(
                vehicle_id, location="34.0522,-118.2437"
            )
            status = result.get("publishResponse", {}).get("result")
            print(f"   ✅ Coordinate string sent! Status: {status}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

        # Test 5: Full address
        print("\n5. Testing with full address...")
        try:
            result = await client.share_location_to_vehicle(
                vehicle_id, location="1600 Amphitheatre Parkway, Mountain View, CA 94043"
            )
            status = result.get("publishResponse", {}).get("result")
            print(f"   ✅ Full address sent! Status: {status}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")

    print("\n" + "=" * 60)
    print("✅ Testing complete!")


if __name__ == "__main__":
    asyncio.run(main())
