#!/usr/bin/env python3
"""Comprehensive test of all Parallax protocol methods."""

import asyncio
import json
import os

from dotenv import load_dotenv

from rivian import Rivian


async def main() -> None:
    """Test all Parallax protocol operations."""
    load_dotenv()

    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN", "")
    vehicle_id = "01-276948064"

    print("Testing ALL Parallax Protocol Methods...")
    print("=" * 60)

    results = {}

    async with Rivian(user_session_token=user_session_token) as client:
        # Category 1: Energy & Charging
        print("\n📊 ENERGY & CHARGING")
        print("-" * 60)

        # 1. Charging session live data
        print("\n1. get_charging_session_live_data()...")
        try:
            result = await client.get_charging_session_live_data(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            if success:
                print(f"   Payload length: {len(result.get('payload', ''))}")
            results["charging_session_live"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["charging_session_live"] = False

        # 2. Parked energy data
        print("\n2. get_parked_energy_data()...")
        try:
            result = await client.get_parked_energy_data(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["parked_energy"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["parked_energy"] = False

        # 3. Charging session chart data
        print("\n3. get_charging_session_chart_data()...")
        try:
            result = await client.get_charging_session_chart_data(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["charging_chart"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["charging_chart"] = False

        # Category 2: Climate Control
        print("\n\n🌡️  CLIMATE CONTROL")
        print("-" * 60)

        # 4. Climate hold status
        print("\n4. get_climate_hold_status()...")
        try:
            result = await client.get_climate_hold_status(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["climate_status"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["climate_status"] = False

        # 5. Set climate hold (test with disabled)
        print("\n5. set_climate_hold() - disabling...")
        try:
            result = await client.set_climate_hold(vehicle_id, enabled=False)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["climate_hold_cmd"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["climate_hold_cmd"] = False

        # Category 3: OTA Updates
        print("\n\n📱 OTA UPDATES")
        print("-" * 60)

        # 6. OTA status
        print("\n6. get_ota_status()...")
        try:
            result = await client.get_ota_status(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["ota_status"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["ota_status"] = False

        # Category 4: Navigation & Trips
        print("\n\n🗺️  NAVIGATION & TRIPS")
        print("-" * 60)

        # 7. Trip progress
        print("\n7. get_trip_progress()...")
        try:
            result = await client.get_trip_progress(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["trip_progress"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["trip_progress"] = False

        # 8. Trip info
        print("\n8. get_trip_info()...")
        try:
            result = await client.get_trip_info(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["trip_info"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["trip_info"] = False

        # Category 5: Geofencing
        print("\n\n📍 GEOFENCING")
        print("-" * 60)

        # 9. Vehicle geofences
        print("\n9. get_vehicle_geofences()...")
        try:
            result = await client.get_vehicle_geofences(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["geofences"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["geofences"] = False

        # Category 6: Gear Guard
        print("\n\n📹 GEAR GUARD")
        print("-" * 60)

        # 10. Gear Guard consents
        print("\n10. get_gear_guard_consents()...")
        try:
            result = await client.get_gear_guard_consents(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["gear_guard_consents"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["gear_guard_consents"] = False

        # 11. Gear Guard daily limits
        print("\n11. get_gear_guard_daily_limits()...")
        try:
            result = await client.get_gear_guard_daily_limits(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["gear_guard_limits"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["gear_guard_limits"] = False

        # Category 7: Vehicle Configuration
        print("\n\n⚙️  VEHICLE CONFIGURATION")
        print("-" * 60)

        # 12. Vehicle wheels
        print("\n12. get_vehicle_wheels()...")
        try:
            result = await client.get_vehicle_wheels(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["vehicle_wheels"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["vehicle_wheels"] = False

        # 13. Passive entry status
        print("\n13. get_passive_entry_status()...")
        try:
            result = await client.get_passive_entry_status(vehicle_id)
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["passive_entry"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["passive_entry"] = False

    # Summary
    print("\n" + "=" * 60)
    print("📊 SUMMARY")
    print("=" * 60)

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    print(f"\nTotal tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"Success rate: {(passed/total*100):.1f}%")

    print("\n📋 Detailed Results:")
    for name, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {name}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
