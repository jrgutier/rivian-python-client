#!/usr/bin/env python3
"""Interactive test script for Rivian Python Client v2.1 features.

Tests all new v2.1 GraphQL operations with real vehicle data:
- Charging schedule management
- Location sharing
- Trailer management (R1T)
- Trip planning
- Advanced key management (CCC/WCC2)
- Gear Guard monitoring

Usage:
    python examples/v2_1_live_test.py
"""

import asyncio
import getpass
import json
import sys
from typing import Any

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
    print(f"\n{status}: {name}")
    if data and success:
        print(f"Data: {json.dumps(data, indent=2)[:500]}...")


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
        print_result("Get charging schedules", success, schedules)

        if success:
            num_schedules = len(schedules.get("schedules", []))
            smart_enabled = schedules.get("smartChargingEnabled", False)
            print(f"   Found {num_schedules} schedule(s)")
            print(f"   Smart charging: {'enabled' if smart_enabled else 'disabled'}")
    except Exception as e:
        results["get_schedules"] = False
        print_result("Get charging schedules", False)
        print(f"   Error: {e}")

    # Test 2: Smart charging enrollment status
    print("\n2. Smart Charging Enrollment")
    choice = input("   Test smart charging enrollment? (y/n): ")
    if choice.lower() == "y":
        try:
            # Try to enroll
            enrolled = await client.enroll_in_smart_charging(vehicle_id)
            results["enroll_smart_charging"] = enrolled
            print_result("Enroll in smart charging", enrolled)

            if enrolled:
                # Immediately unenroll to restore state
                unenrolled = await client.unenroll_from_smart_charging(vehicle_id)
                results["unenroll_smart_charging"] = unenrolled
                print_result("Unenroll from smart charging", unenrolled)
        except Exception as e:
            results["enroll_smart_charging"] = False
            print_result("Smart charging enrollment", False)
            print(f"   Error: {e}")

    # Test 3: Update departure schedule
    print("\n3. Update Departure Schedule")
    choice = input("   Create/update a departure schedule? (y/n): ")
    if choice.lower() == "y":
        try:
            schedule_data = {
                "name": "V2.1 Test Schedule",
                "enabled": True,
                "days": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
                "departureTime": "08:00",
                "cabinPreconditioning": True,
                "cabinPreconditioningTemp": 21.0,
                "targetSOC": 80,
            }

            print(f"   Creating schedule: {json.dumps(schedule_data, indent=4)}")
            result = await client.update_departure_schedule(vehicle_id, schedule_data)
            success = result.get("success", False)
            results["update_schedule"] = success
            print_result("Update departure schedule", success, result)
        except RivianBadRequestError as e:
            results["update_schedule"] = False
            print_result("Update departure schedule", False)
            print(f"   Validation Error: {e}")
        except Exception as e:
            results["update_schedule"] = False
            print_result("Update departure schedule", False)
            print(f"   Error: {e}")

    return results


async def test_location_sharing(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test location sharing features."""
    print_section("Location Sharing")
    results = {}

    # Test 1: Share GPS coordinates
    print("\n1. Share GPS Coordinates")
    choice = input("   Send test location to vehicle? (y/n): ")
    if choice.lower() == "y":
        try:
            # Send Rivian HQ in Irvine, CA as example
            latitude = 33.6846
            longitude = -117.8265

            print(f"   Sending: {latitude}, {longitude} (Rivian HQ, Irvine CA)")
            result = await client.share_location_to_vehicle(
                vehicle_id, latitude, longitude
            )
            success = result.get("publishResponse", {}).get("result") == 0
            results["share_gps"] = success
            print_result("Share GPS coordinates", success, result)
        except RivianBadRequestError as e:
            results["share_gps"] = False
            print_result("Share GPS coordinates", False)
            print(f"   Validation Error: {e}")
        except Exception as e:
            results["share_gps"] = False
            print_result("Share GPS coordinates", False)
            print(f"   Error: {e}")

    # Test 2: Share Google Place ID
    print("\n2. Share Google Place ID")
    choice = input("   Send Google Place to vehicle? (y/n): ")
    if choice.lower() == "y":
        try:
            # Example: Statue of Liberty
            place_id = "ChIJPTacEpBQwokRKwIlDbbNNag"

            print(f"   Sending Place ID: {place_id} (Statue of Liberty)")
            result = await client.share_place_id_to_vehicle(vehicle_id, place_id)
            success = result.get("publishResponse", {}).get("result") == 0
            results["share_place"] = success
            print_result("Share Google Place", success, result)
        except Exception as e:
            results["share_place"] = False
            print_result("Share Google Place", False)
            print(f"   Error: {e}")

    return results


async def test_trailer_management(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test trailer management features (R1T only)."""
    print_section("Trailer Management (R1T)")
    results = {}

    # Test 1: Get trailer profiles
    print("\n1. Get Trailer Profiles")
    try:
        trailers = await client.get_trailer_profiles(vehicle_id)
        success = trailers is not None
        results["get_trailers"] = success
        print_result("Get trailer profiles", success, trailers)

        if success:
            num_trailers = len(trailers)
            print(f"   Found {num_trailers} trailer profile(s)")

            if num_trailers > 0:
                for trailer in trailers:
                    print(f"   - {trailer.get('name')}: "
                          f"Length={trailer.get('length')}m, "
                          f"Pinned={trailer.get('pinnedToGear')}")

                # Test 2: Update pin to gear
                print("\n2. Update Pin to Gear")
                choice = input("   Toggle pin status for first trailer? (y/n): ")
                if choice.lower() == "y":
                    try:
                        trailer_id = trailers[0]["id"]
                        current_pinned = trailers[0].get("pinnedToGear", False)
                        new_pinned = not current_pinned

                        print(f"   Changing pin status: {current_pinned} → {new_pinned}")
                        success = await client.update_pin_to_gear(
                            vehicle_id, trailer_id, new_pinned
                        )
                        results["update_pin"] = success
                        print_result("Update pin to gear", success)

                        # Restore original state
                        if success:
                            await client.update_pin_to_gear(
                                vehicle_id, trailer_id, current_pinned
                            )
                            print("   Restored original pin status")
                    except Exception as e:
                        results["update_pin"] = False
                        print_result("Update pin to gear", False)
                        print(f"   Error: {e}")
            else:
                print("   No trailers configured (R1S or no profiles created)")
    except Exception as e:
        results["get_trailers"] = False
        print_result("Get trailer profiles", False)
        print(f"   Error: {e}")

    return results


async def test_trip_planning(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test trip planning features."""
    print_section("Trip Planning")
    results = {}

    # Test 1: Plan multi-stop trip
    print("\n1. Plan Multi-Stop Trip")
    choice = input("   Plan a sample trip? (y/n): ")
    if choice.lower() == "y":
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

            print(f"   Planning trip: SF → Fresno → LA")
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

                print(f"   Trip ID: {trip_id}")
                print(f"   Distance: {distance:.1f} miles")
                print(f"   Duration: {duration // 60}h {duration % 60}m")
                print(f"   Charging stops: {charging_stops}")

                # Test 2: Save trip
                print("\n2. Save Trip Plan")
                save_choice = input("   Save this trip? (y/n): ")
                if save_choice.lower() == "y":
                    try:
                        saved = await client.save_trip_plan(trip_id, "V2.1 Test Trip")
                        save_success = saved.get("success", False)
                        results["save_trip"] = save_success
                        print_result("Save trip plan", save_success, saved)

                        # Test 3: Update trip
                        if save_success:
                            print("\n3. Update Trip")
                            update_choice = input("   Update trip name? (y/n): ")
                            if update_choice.lower() == "y":
                                try:
                                    updated = await client.update_trip(
                                        trip_id, {"name": "V2.1 Updated Test Trip"}
                                    )
                                    update_success = updated.get("success", False)
                                    results["update_trip"] = update_success
                                    print_result("Update trip", update_success, updated)
                                except Exception as e:
                                    results["update_trip"] = False
                                    print_result("Update trip", False)
                                    print(f"   Error: {e}")

                            # Test 4: Delete trip
                            print("\n4. Delete Trip")
                            delete_choice = input("   Delete test trip? (y/n): ")
                            if delete_choice.lower() == "y":
                                try:
                                    deleted = await client.delete_trip(trip_id)
                                    results["delete_trip"] = deleted
                                    print_result("Delete trip", deleted)
                                except Exception as e:
                                    results["delete_trip"] = False
                                    print_result("Delete trip", False)
                                    print(f"   Error: {e}")
                    except Exception as e:
                        results["save_trip"] = False
                        print_result("Save trip plan", False)
                        print(f"   Error: {e}")
        except Exception as e:
            results["plan_trip"] = False
            print_result("Plan multi-stop trip", False)
            print(f"   Error: {e}")

    return results


async def test_key_management(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test advanced key management features (CCC/WCC2)."""
    print_section("Advanced Key Management (CCC/WCC2)")
    results = {}

    print("\nNote: These features require compatible hardware and may not be")
    print("available on all vehicles. They are for next-gen digital keys.")

    # Test 1: Create signing challenge
    print("\n1. Create Signing Challenge")
    choice = input("   Test CCC signing challenge? (y/n): ")
    if choice.lower() == "y":
        try:
            device_id = input("   Enter device ID (or press Enter for 'test-device'): ") or "test-device"

            challenge = await client.create_signing_challenge(vehicle_id, device_id)
            success = challenge.get("challengeId") is not None
            results["create_challenge"] = success
            print_result("Create signing challenge", success)

            if success:
                challenge_id = challenge.get("challengeId")
                print(f"   Challenge ID: {challenge_id}")
                print(f"   Expires: {challenge.get('expiresAt')}")

                # Test 2: Verify challenge (will fail without proper signature)
                print("\n2. Verify Signing Challenge")
                print("   (Skipping - requires proper cryptographic signature)")
                # This would need actual ECDSA signing:
                # verified = await client.verify_signing_challenge(
                #     vehicle_id, device_id, challenge_id, signature
                # )
        except Exception as e:
            results["create_challenge"] = False
            print_result("Create signing challenge", False)
            print(f"   Error: {e}")

    # Test 3: Enable CCC
    print("\n3. Enable CCC")
    choice = input("   Test CCC enablement? (y/n): ")
    if choice.lower() == "y":
        try:
            device_id = input("   Enter device ID (or press Enter for 'test-device'): ") or "test-device"

            enabled = await client.enable_ccc(vehicle_id, device_id)
            results["enable_ccc"] = enabled
            print_result("Enable CCC", enabled)
        except Exception as e:
            results["enable_ccc"] = False
            print_result("Enable CCC", False)
            print(f"   Error: {e}")

    # Test 4: Upgrade to WCC2
    print("\n4. Upgrade Key to WCC2")
    choice = input("   Test WCC2 upgrade? (y/n): ")
    if choice.lower() == "y":
        try:
            device_id = input("   Enter device ID (or press Enter for 'test-device'): ") or "test-device"

            upgraded = await client.upgrade_key_to_wcc2(vehicle_id, device_id)
            results["upgrade_wcc2"] = upgraded
            print_result("Upgrade to WCC2", upgraded)
        except Exception as e:
            results["upgrade_wcc2"] = False
            print_result("Upgrade to WCC2", False)
            print(f"   Error: {e}")

    return results


async def test_gear_guard(client: Rivian, vehicle_id: str) -> dict[str, bool]:
    """Test Gear Guard subscription."""
    print_section("Gear Guard Monitoring")
    results = {}

    print("\n1. Subscribe to Gear Guard Config")
    choice = input("   Test Gear Guard subscription? (y/n): ")
    if choice.lower() == "y":
        try:
            print("   Subscribing for 10 seconds...")

            received_update = False

            def on_config_update(config: dict[str, Any]) -> None:
                nonlocal received_update
                received_update = True
                print(f"\n   📹 Gear Guard Update:")
                print(f"      Enabled: {config.get('enabled')}")
                print(f"      Video Mode: {config.get('videoMode')}")
                print(f"      Quality: {config.get('recordingQuality')}")
                print(f"      Streaming: {config.get('streamingAvailable')}")
                print(f"      Storage: {config.get('storageRemaining')}%")

            unsubscribe = await client.subscribe_for_gear_guard_config(
                vehicle_id, on_config_update
            )

            if unsubscribe:
                # Wait for updates
                await asyncio.sleep(10)
                unsubscribe()

                results["gear_guard_sub"] = received_update
                print_result("Gear Guard subscription", received_update)
                if not received_update:
                    print("   Note: No updates received (may not be available on this vehicle)")
            else:
                results["gear_guard_sub"] = False
                print_result("Gear Guard subscription", False)
                print("   Failed to establish subscription")
        except Exception as e:
            results["gear_guard_sub"] = False
            print_result("Gear Guard subscription", False)
            print(f"   Error: {e}")

    return results


async def main() -> None:
    """Main test flow."""
    print("=" * 60)
    print("   Rivian Python Client v2.1 Live Test Suite")
    print("=" * 60)
    print("\nThis script tests all new v2.1 GraphQL operations.")
    print("You will be prompted for credentials and test choices.\n")

    # Interactive login
    username = input("Email: ")
    password = getpass.getpass("Password: ")

    all_results: dict[str, dict[str, bool]] = {}

    try:
        async with Rivian() as client:
            # Authenticate
            print("\n🔐 Authenticating...")
            otp_token = await client.login(username, password)
            if otp_token:
                otp_code = input("OTP Code: ")
                await client.login_with_otp(username, otp_code, otp_token)
            print("✓ Authentication successful!\n")

            # Get user information and vehicles
            user_info = await client.get_user_information()
            vehicles = user_info.get("vehicles", [])

            if not vehicles:
                print("❌ No vehicles found in account.")
                return

            # Vehicle selection
            print("Available vehicles:")
            for i, v in enumerate(vehicles, 1):
                print(f"  {i}. {v['name']} ({v['vin']})")

            choice = int(input("\nSelect vehicle: ")) - 1
            if choice < 0 or choice >= len(vehicles):
                print("Invalid selection.")
                return

            vehicle_id = vehicles[choice]["id"]
            vehicle_name = vehicles[choice]["name"]
            print(f"\n🚗 Testing with: {vehicle_name}\n")

            # Run test suites
            print("\nSelect test categories to run:")
            print("  1. Charging Management (schedules, smart charging)")
            print("  2. Location Sharing (GPS, Google Places)")
            print("  3. Trailer Management (R1T profiles)")
            print("  4. Trip Planning (multi-stop, save/update)")
            print("  5. Key Management (CCC/WCC2)")
            print("  6. Gear Guard (subscription)")
            print("  7. All tests")

            test_choice = input("\nEnter choice (1-7): ")

            if test_choice in ["1", "7"]:
                all_results["charging"] = await test_charging_management(client, vehicle_id)

            if test_choice in ["2", "7"]:
                all_results["location"] = await test_location_sharing(client, vehicle_id)

            if test_choice in ["3", "7"]:
                all_results["trailer"] = await test_trailer_management(client, vehicle_id)

            if test_choice in ["4", "7"]:
                all_results["trip"] = await test_trip_planning(client, vehicle_id)

            if test_choice in ["5", "7"]:
                all_results["key_mgmt"] = await test_key_management(client, vehicle_id)

            if test_choice in ["6", "7"]:
                all_results["gear_guard"] = await test_gear_guard(client, vehicle_id)

            # Final Summary
            print_section("Final Summary")
            print(f"Vehicle: {vehicle_name}\n")

            total_tests = 0
            passed_tests = 0

            for category, results in all_results.items():
                category_name = category.replace("_", " ").title()
                print(f"{category_name}:")
                for test_name, success in results.items():
                    status = "✓" if success else "✗"
                    print(f"  {status} {test_name.replace('_', ' ').title()}")
                    total_tests += 1
                    if success:
                        passed_tests += 1
                print()

            print(f"Overall Results: {passed_tests}/{total_tests} tests passed")
            success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
            print(f"Success Rate: {success_rate:.1f}%")

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
