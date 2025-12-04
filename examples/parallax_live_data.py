#!/usr/bin/env python3
"""Interactive test script for Rivian Parallax Protocol.

Tests all Phase 1 RVM methods with real vehicle data:
- Charging session live data
- Climate hold status
- Cabin preconditioning schedules
- Command execution (set climate hold, set schedules)

Usage:
    python examples/parallax_live_data.py
"""

import asyncio
import getpass
import sys
from typing import Any

from rivian import Rivian
from rivian.exceptions import RivianApiException


async def main() -> None:
    """Main test flow."""
    print("=== Rivian Parallax Protocol Live Test ===\n")

    # Interactive login
    username = input("Email: ")
    password = getpass.getpass("Password: ")

    results: dict[str, bool] = {}

    try:
        async with Rivian() as client:
            # Authenticate
            print("\nAuthenticating...")
            otp_token = await client.login(username, password)
            if otp_token:
                otp_code = input("OTP Code: ")
                await client.login_with_otp(username, otp_code, otp_token)
            print("Authentication successful!\n")

            # Get user information and vehicles
            user_info = await client.get_user_information()
            vehicles = user_info.get("vehicles", [])

            if not vehicles:
                print("No vehicles found in account.")
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
            print(f"\nTesting with: {vehicle_name}\n")

            # Test 1: Charging Session Live Data
            print("=== 1. Charging Session Live Data ===")
            try:
                result = await client.get_charging_session_live_data(vehicle_id)
                success = result.get("success", False)
                results["charging_session"] = success
                print(f"Success: {success}")
                if success and result.get("payload"):
                    payload = result["payload"]
                    preview = payload[:50] + "..." if len(payload) > 50 else payload
                    print(f"Payload: {preview}")
                else:
                    print("Payload: None")
            except Exception as e:
                results["charging_session"] = False
                print(f"Error: {e}")

            # Test 2: Climate Hold Status
            print("\n=== 2. Climate Hold Status ===")
            try:
                result = await client.get_climate_hold_status(vehicle_id)
                success = result.get("success", False)
                results["climate_status"] = success
                print(f"Success: {success}")
                if success and result.get("payload"):
                    payload = result["payload"]
                    preview = payload[:50] + "..." if len(payload) > 50 else payload
                    print(f"Payload: {preview}")
                else:
                    print("Payload: None")
            except Exception as e:
                results["climate_status"] = False
                print(f"Error: {e}")

            # Test 3: Cabin Preconditioning Schedules (Current)
            print("\n=== 3. Cabin Preconditioning Schedules (Current) ===")
            try:
                result = await client.get_cabin_preconditioning_schedules(vehicle_id)
                success = result.get("success", False)
                results["schedules_current"] = success
                print(f"Success: {success}")
                if success and result.get("payload"):
                    payload = result["payload"]
                    preview = payload[:50] + "..." if len(payload) > 50 else payload
                    print(f"Payload: {preview}")
                else:
                    print("Payload: None")
            except Exception as e:
                results["schedules_current"] = False
                print(f"Error: {e}")

            # Test 4: Cabin Preconditioning Schedules (All Vehicles)
            print("\n=== 4. Cabin Preconditioning Schedules (All Vehicles) ===")
            try:
                result = await client.get_cabin_preconditioning_schedules_all()
                success = result.get("success", False)
                results["schedules_all"] = success
                print(f"Success: {success}")
                if success and result.get("payload"):
                    payload = result["payload"]
                    preview = payload[:50] + "..." if len(payload) > 50 else payload
                    print(f"Payload: {preview}")
                else:
                    print("Payload: None")
            except Exception as e:
                results["schedules_all"] = False
                print(f"Error: {e}")

            # Optional: Set Climate Hold
            print("\n=== Optional: Set Climate Hold ===")
            if input("Set climate hold? (y/n): ").lower() == "y":
                try:
                    temp_str = input("Temperature (°C, default 21.0): ")
                    temp = float(temp_str) if temp_str else 21.0

                    duration_str = input("Duration (minutes, default 30): ")
                    duration = int(duration_str) if duration_str else 30

                    enable_str = input("Enable (y/n, default y): ")
                    enable = enable_str.lower() != "n"

                    result = await client.set_climate_hold(
                        vehicle_id, enable, temp, duration
                    )
                    success = result.get("success", False)
                    results["set_climate"] = success
                    print(f"Success: {success}")
                    if success:
                        print(
                            f"Climate hold {'enabled' if enable else 'disabled'}: "
                            f"{temp}°C for {duration} minutes"
                        )
                except Exception as e:
                    results["set_climate"] = False
                    print(f"Error: {e}")

            # Optional: Set Cabin Preconditioning Schedule
            print("\n=== Optional: Set Cabin Preconditioning Schedule ===")
            if input("Set cabin preconditioning schedule? (y/n): ").lower() == "y":
                try:
                    print("\nSchedule format examples:")
                    print('  Enable: {"enabled": true, "time": "07:00", "days": ["MON", "TUE"]}')
                    print('  Disable: {"enabled": false}')

                    schedule_str = input("\nEnter schedule JSON: ")
                    if schedule_str:
                        import json

                        schedule = json.loads(schedule_str)
                        result = await client.set_cabin_preconditioning_schedule(
                            vehicle_id, schedule
                        )
                        success = result.get("success", False)
                        results["set_schedule"] = success
                        print(f"Success: {success}")
                        if success:
                            print(f"Schedule updated: {schedule}")
                except Exception as e:
                    results["set_schedule"] = False
                    print(f"Error: {e}")

            # Results Summary
            print("\n" + "=" * 50)
            print("=== Summary ===")
            print("=" * 50)
            print(f"Vehicle: {vehicle_name}")
            print(f"\nQuery Methods:")
            print(f"  Charging session data:     {'✓' if results.get('charging_session') else '✗'}")
            print(f"  Climate hold status:       {'✓' if results.get('climate_status') else '✗'}")
            print(f"  Schedules (current):       {'✓' if results.get('schedules_current') else '✗'}")
            print(f"  Schedules (all vehicles):  {'✓' if results.get('schedules_all') else '✗'}")

            if "set_climate" in results or "set_schedule" in results:
                print(f"\nCommand Methods:")
                if "set_climate" in results:
                    print(f"  Set climate hold:          {'✓' if results['set_climate'] else '✗'}")
                if "set_schedule" in results:
                    print(f"  Set schedule:              {'✓' if results['set_schedule'] else '✗'}")

            total_tests = len(results)
            passed_tests = sum(1 for v in results.values() if v)
            print(f"\nOverall: {passed_tests}/{total_tests} tests passed")

    except RivianApiException as e:
        print(f"\nRivian API Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
