#!/usr/bin/env python3
"""Automated test script for Rivian Python Client v2.1 features.

Tests all new v2.1 GraphQL operations using credentials from .env file.
This is a non-interactive version for CI/CD and automated testing.

Usage:
    python examples/v2_1_automated_test.py [--category CATEGORY]

Categories:
    charging, location, trailer, trip, key_mgmt, gear_guard, all (default)
"""

import asyncio
import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

from rivian import Rivian
from rivian.exceptions import RivianApiException, RivianBadRequestError


def print_section(title: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 60)
    print(f"=== {title} ===")
    print("=" * 60)


def print_result(name: str, success: bool, data: Any = None) -> None:
    """Print a test result."""
    status = "✓ PASS" if success else "✗ FAIL"
    print(f"{status}: {name}")
    if data and success:
        try:
            data_str = json.dumps(data, indent=2)
            preview = data_str[:300] + "..." if len(data_str) > 300 else data_str
            print(f"  Data: {preview}")
        except Exception:
            print(f"  Data: {str(data)[:300]}")


async def test_charging_management(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test charging schedule management features."""
    print_section("Charging Schedule Management")
    results = {}

    # Test 1: Get charging schedules
    print("\n1. Get Charging Schedules")
    try:
        schedules = await client.get_charging_schedules(vehicle_id)
        success = schedules is not None
        results["get_schedules"] = success
        print_result("Get charging schedules", success)

        if success:
            num_schedules = len(schedules.get("schedules", []))
            smart_enabled = schedules.get("smartChargingEnabled", False)
            print(f"  Found {num_schedules} schedule(s), Smart charging: {'enabled' if smart_enabled else 'disabled'}")
    except Exception as e:
        results["get_schedules"] = False
        print_result("Get charging schedules", False)
        print(f"  Error: {e}")

    return results


async def test_location_sharing(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test location sharing features."""
    print_section("Location Sharing")
    results = {}

    # Test 1: Share GPS coordinates (Rivian HQ)
    print("\n1. Share GPS Coordinates")
    try:
        latitude = 33.6846
        longitude = -117.8265
        print(f"  Sending: {latitude}, {longitude} (Rivian HQ, Irvine CA)")

        result = await client.share_location_to_vehicle(
            vehicle_id, latitude, longitude
        )
        success = result.get("publishResponse", {}).get("result") == 0
        results["share_gps"] = success
        print_result("Share GPS coordinates", success)
    except Exception as e:
        results["share_gps"] = False
        print_result("Share GPS coordinates", False)
        print(f"  Error: {e}")

    # Test 2: Share Google Place ID (Statue of Liberty)
    print("\n2. Share Google Place ID")
    try:
        place_id = "ChIJPTacEpBQwokRKwIlDbbNNag"
        print(f"  Sending Place ID: {place_id} (Statue of Liberty)")

        result = await client.share_place_id_to_vehicle(vehicle_id, place_id)
        success = result.get("publishResponse", {}).get("result") == 0
        results["share_place"] = success
        print_result("Share Google Place", success)
    except Exception as e:
        results["share_place"] = False
        print_result("Share Google Place", False)
        print(f"  Error: {e}")

    return results


async def test_trailer_management(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test trailer management features (R1T only)."""
    print_section("Trailer Management (R1T)")
    results = {}

    # Test: Get trailer profiles
    print("\n1. Get Trailer Profiles")
    try:
        trailers = await client.get_trailer_profiles(vehicle_id)
        success = trailers is not None
        results["get_trailers"] = success

        if success:
            num_trailers = len(trailers)
            print_result("Get trailer profiles", success)
            print(f"  Found {num_trailers} trailer profile(s)")

            if num_trailers > 0:
                for trailer in trailers:
                    print(f"    - {trailer.get('name')}: "
                          f"Length={trailer.get('length')}m, "
                          f"Pinned={trailer.get('pinnedToGear')}")
            else:
                print("  (No trailers configured - R1S or no profiles created)")
        else:
            print_result("Get trailer profiles", False)
    except Exception as e:
        results["get_trailers"] = False
        print_result("Get trailer profiles", False)
        print(f"  Error: {e}")

    return results


async def test_trip_planning(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test trip planning features."""
    print_section("Trip Planning")
    results = {}

    # Test: Plan multi-stop trip
    print("\n1. Plan Multi-Stop Trip (SF → Fresno → LA)")
    try:
        waypoints = [
            {"latitude": 37.7749, "longitude": -122.4194, "name": "San Francisco"},
            {"latitude": 36.7783, "longitude": -119.4179, "name": "Fresno"},
            {"latitude": 34.0522, "longitude": -118.2437, "name": "Los Angeles"},
        ]
        options = {
            "avoidTolls": False,
            "avoidHighways": False,
            "minChargingSOC": 10,
            "targetArrivalSOC": 20,
        }

        trip = await client.plan_trip_with_multi_stop(
            vehicle_id, waypoints, options
        )
        success = trip.get("tripId") is not None
        results["plan_trip"] = success
        print_result("Plan multi-stop trip", success)

        if success:
            trip_id = trip.get("tripId")
            distance = trip.get("totalDistance", 0)
            duration = trip.get("totalDuration", 0)
            charging_stops = len(trip.get("chargingStops", []))

            print(f"  Trip ID: {trip_id}")
            print(f"  Distance: {distance:.1f} miles, Duration: {duration // 60}h {duration % 60}m")
            print(f"  Charging stops: {charging_stops}")

            # Clean up - delete the test trip
            try:
                await client.delete_trip(trip_id)
                print("  ✓ Test trip cleaned up")
            except Exception:
                pass  # Ignore cleanup errors
    except Exception as e:
        results["plan_trip"] = False
        print_result("Plan multi-stop trip", False)
        print(f"  Error: {e}")

    return results


async def test_key_management(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test advanced key management features (CCC/WCC2)."""
    print_section("Advanced Key Management (CCC/WCC2)")
    results = {}

    print("Note: These features require compatible hardware and may not be available.")

    # Test: Create signing challenge
    print("\n1. Create Signing Challenge")
    try:
        device_id = "automated-test-device"
        challenge = await client.create_signing_challenge(vehicle_id, device_id)
        success = challenge.get("challengeId") is not None
        results["create_challenge"] = success
        print_result("Create signing challenge", success)

        if success:
            print(f"  Challenge ID: {challenge.get('challengeId')}")
            print(f"  Expires: {challenge.get('expiresAt')}")
    except Exception as e:
        results["create_challenge"] = False
        print_result("Create signing challenge", False)
        print(f"  Error: {e}")

    return results


async def test_gear_guard(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test Gear Guard subscription."""
    print_section("Gear Guard Monitoring")
    results = {}

    print("\n1. Subscribe to Gear Guard Config (5 seconds)")
    try:
        received_update = False

        def on_config_update(config: dict[str, Any]) -> None:
            nonlocal received_update
            received_update = True
            print(f"  📹 Received update: Enabled={config.get('enabled')}, "
                  f"Mode={config.get('videoMode')}, "
                  f"Storage={config.get('storageRemaining')}%")

        unsubscribe = await client.subscribe_for_gear_guard_config(
            vehicle_id, on_config_update
        )

        if unsubscribe:
            await asyncio.sleep(5)
            unsubscribe()

            results["gear_guard_sub"] = received_update
            print_result("Gear Guard subscription", received_update)
            if not received_update:
                print("  (No updates received - may not be available on this vehicle)")
        else:
            results["gear_guard_sub"] = False
            print_result("Gear Guard subscription", False)
            print("  Failed to establish subscription")
    except Exception as e:
        results["gear_guard_sub"] = False
        print_result("Gear Guard subscription", False)
        print(f"  Error: {e}")

    return results


async def main() -> None:
    """Main test flow."""
    # Load environment variables
    load_dotenv()

    print("=" * 60)
    print("   Rivian Python Client v2.1 Automated Test Suite")
    print("=" * 60)
    print("\nUsing credentials from .env file\n")

    # Get credentials from environment
    access_token = os.getenv("RIVIAN_ACCESS_TOKEN", "")
    refresh_token = os.getenv("RIVIAN_REFRESH_TOKEN", "")
    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN", "")
    vehicle_id = os.getenv("RIVIAN_VEHICLE_ID", "")

    if not all([user_session_token, vehicle_id]):
        print("❌ Error: Missing required credentials in .env file")
        print("Required: RIVIAN_USER_SESSION_TOKEN, RIVIAN_VEHICLE_ID")
        sys.exit(1)

    # Parse command line arguments
    category = sys.argv[1] if len(sys.argv) > 1 else "all"
    valid_categories = ["charging", "location", "trailer", "trip", "key_mgmt", "gear_guard", "all"]

    if category not in valid_categories:
        print(f"❌ Invalid category: {category}")
        print(f"Valid categories: {', '.join(valid_categories)}")
        sys.exit(1)

    all_results: dict[str, dict[str, bool]] = {}

    try:
        # Initialize client with tokens
        async with Rivian(
            access_token=access_token,
            refresh_token=refresh_token,
            user_session_token=user_session_token,
        ) as client:
            print(f"✓ Client initialized")
            print(f"✓ Vehicle ID: {vehicle_id}")
            print(f"✓ Testing category: {category}\n")

            # Run test suites based on category
            if category in ["charging", "all"]:
                all_results["charging"] = await test_charging_management(client, vehicle_id)

            if category in ["location", "all"]:
                all_results["location"] = await test_location_sharing(client, vehicle_id)

            if category in ["trailer", "all"]:
                all_results["trailer"] = await test_trailer_management(client, vehicle_id)

            if category in ["trip", "all"]:
                all_results["trip"] = await test_trip_planning(client, vehicle_id)

            if category in ["key_mgmt", "all"]:
                all_results["key_mgmt"] = await test_key_management(client, vehicle_id)

            if category in ["gear_guard", "all"]:
                all_results["gear_guard"] = await test_gear_guard(client, vehicle_id)

            # Final Summary
            print_section("Final Summary")

            total_tests = 0
            passed_tests = 0

            for cat_name, results in all_results.items():
                category_name = cat_name.replace("_", " ").title()
                print(f"\n{category_name}:")
                for test_name, success in results.items():
                    status = "✓" if success else "✗"
                    print(f"  {status} {test_name.replace('_', ' ').title()}")
                    total_tests += 1
                    if success:
                        passed_tests += 1

            print(f"\nOverall Results: {passed_tests}/{total_tests} tests passed")
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
            print(f"Success Rate: {success_rate:.1f}%")

            # Exit with appropriate code
            if passed_tests == total_tests:
                print("\n✅ All tests passed!")
                sys.exit(0)
            elif passed_tests > 0:
                print(f"\n⚠️  {total_tests - passed_tests} test(s) failed")
                sys.exit(1)
            else:
                print("\n❌ All tests failed")
                sys.exit(1)

    except RivianApiException as e:
        print(f"\n❌ Rivian API Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
