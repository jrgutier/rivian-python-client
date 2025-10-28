#!/usr/bin/env python3
"""Quick test of the GraphQL fixes based on Android app analysis."""

import asyncio
import os
import sys

from dotenv import load_dotenv

from rivian import Rivian


async def main() -> None:
    """Test the fixed GraphQL operations."""
    load_dotenv()

    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN", "")
    # Use the correct vehicle ID format (from user info, not hash)
    vehicle_id = "01-276948064"  # R1T VIN 7FCTGAAL5NN002984

    if not all([user_session_token, vehicle_id]):
        print("❌ Missing credentials in .env")
        sys.exit(1)

    print("Testing fixed GraphQL operations...")
    print("=" * 60)

    try:
        async with Rivian(user_session_token=user_session_token) as client:
            # Test 1: Get charging schedules (now uses getVehicle wrapper)
            print("\n1. Testing get_charging_schedules()...")
            try:
                schedules = await client.get_charging_schedules(vehicle_id)
                print(f"   ✅ Success! Got {len(schedules)} schedule(s)")
            except Exception as e:
                print(f"   ❌ Failed: {e}")

            # Test 2: Share location (now uses parseAndShareLocationToVehicle)
            print("\n2. Testing share_location_to_vehicle()...")
            try:
                result = await client.share_location_to_vehicle(
                    vehicle_id, 33.6846, -117.8265
                )
                status = result.get("publishResponse", {}).get("result")
                if status == 0:
                    print(f"   ✅ Success! Sent location to vehicle")
                else:
                    print(f"   ⚠️  Returned status: {status}")
            except Exception as e:
                print(f"   ❌ Failed: {e}")

            # Test 3: Plan trip (now uses planTrip2 query)
            print("\n3. Testing plan_trip_with_multi_stop()...")
            try:
                waypoints = [
                    {"latitude": 37.7749, "longitude": -122.4194},  # SF
                    {"latitude": 34.0522, "longitude": -118.2437},  # LA
                ]
                result = await client.plan_trip_with_multi_stop(
                    vehicle_id, waypoints, starting_soc=80.0
                )
                plans = result.get("plans", [])
                print(f"   ✅ Success! Got {len(plans)} plan(s)")
                if plans:
                    summary = plans[0].get("summary", {})
                    print(
                        f"      Distance: {summary.get('totalDriveDistanceMeters', 0) / 1000:.1f}km"
                    )
            except Exception as e:
                print(f"   ❌ Failed: {e}")

            print("\n" + "=" * 60)
            print("✅ Testing complete!")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
