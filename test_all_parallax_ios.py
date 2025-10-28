#!/usr/bin/env python3
"""Test all Parallax protocol methods using iOS sendVehicleOperation mutation."""

import asyncio
import json
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


async def main() -> None:
    """Test all Parallax protocol operations using iOS method."""
    env_vars = load_env_file()

    access_token = env_vars.get("RIVIAN_ACCESS_TOKEN") or os.getenv("RIVIAN_ACCESS_TOKEN")
    refresh_token = env_vars.get("RIVIAN_REFRESH_TOKEN") or os.getenv("RIVIAN_REFRESH_TOKEN")
    user_session_token = env_vars.get("RIVIAN_USER_SESSION_TOKEN") or os.getenv("RIVIAN_USER_SESSION_TOKEN")

    if not access_token or not user_session_token:
        print("ERROR: RIVIAN_ACCESS_TOKEN and RIVIAN_USER_SESSION_TOKEN must be set in .env file")
        return

    print("=" * 80)
    print("Testing ALL Parallax Methods using iOS sendVehicleOperation")
    print("=" * 80)

    results = {}
    client = Rivian(
        access_token=access_token,
        refresh_token=refresh_token,
        user_session_token=user_session_token,
    )

    try:
        # Get user information with enrolled phones
        print(f"\n[{datetime.now()}] Getting user information...")
        user_info = await client.get_user_information(include_phones=True)

        if not user_info.get("vehicles"):
            print("ERROR: No vehicles found")
            return

        vehicle_id = user_info["vehicles"][0]["id"]
        print(f"✓ Vehicle ID: {vehicle_id}")

        if not user_info.get("enrolledPhones"):
            print("ERROR: No enrolled phones found. You must enroll a phone first.")
            return

        phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
        phone_id_hex_clean = "".join(c for c in phone_id_hex if c in "0123456789abcdefABCDEF")
        phone_id = bytes.fromhex(phone_id_hex_clean)
        print(f"✓ Phone ID: {phone_id_hex[:32]}... ({len(phone_id)} bytes)")

        # Category 1: Energy & Charging (QUERIES - empty payloads)
        print("\n\n📊 ENERGY & CHARGING (Query Operations)")
        print("-" * 80)

        # 1. Charging session live data
        print("\n1. Charging session live data...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="energy_edge_compute.graphs.charge_session_breakdown",
                payload=b"",  # Empty payload for query
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["charging_session_live"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["charging_session_live"] = False

        # 2. Parked energy data
        print("\n2. Parked energy data...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="energy_edge_compute.graphs.parked_energy_distributions",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["parked_energy"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["parked_energy"] = False

        # 3. Charging session chart data
        print("\n3. Charging session chart data...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="energy_edge_compute.graphs.charging_graph_global",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["charging_chart"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["charging_chart"] = False

        # Category 2: Climate Control
        print("\n\n🌡️  CLIMATE CONTROL")
        print("-" * 80)

        # 4. Climate hold status (QUERY)
        print("\n4. Climate hold status (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="comfort.cabin.climate_hold_status",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["climate_status"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["climate_status"] = False

        # 5. Set climate hold (COMMAND with protobuf)
        print("\n5. Set climate hold to 2 hours (command)...")
        try:
            from rivian.proto.rivian_climate_pb2 import ClimateHoldSetting

            setting = ClimateHoldSetting(hold_time_duration_seconds=7200)  # 2 hours
            payload = setting.SerializeToString()

            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="comfort.cabin.climate_hold_setting",
                payload=payload,
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            print(f"   Payload: {payload.hex()}")
            results["climate_hold_cmd"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["climate_hold_cmd"] = False

        # Category 3: OTA Updates (QUERY)
        print("\n\n📱 OTA UPDATES")
        print("-" * 80)

        # 6. OTA status
        print("\n6. OTA status (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="ota.ota_state.vehicle_ota_state",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["ota_status"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["ota_status"] = False

        # Category 4: Navigation & Trips (QUERIES)
        print("\n\n🗺️  NAVIGATION & TRIPS")
        print("-" * 80)

        # 7. Trip progress
        print("\n7. Trip progress (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="navigation.navigation_service.trip_progress",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["trip_progress"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["trip_progress"] = False

        # 8. Trip info
        print("\n8. Trip info (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="navigation.navigation_service.trip_info",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["trip_info"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["trip_info"] = False

        # Category 5: Geofencing (QUERY)
        print("\n\n📍 GEOFENCING")
        print("-" * 80)

        # 9. Vehicle geofences
        print("\n9. Vehicle geofences (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="geofence.geofence_service.favoriteGeofences",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["geofences"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["geofences"] = False

        # Category 6: Gear Guard (QUERIES)
        print("\n\n📹 GEAR GUARD")
        print("-" * 80)

        # 10. Gear Guard consents
        print("\n10. Gear Guard consents (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["gear_guard_consents"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["gear_guard_consents"] = False

        # 11. Gear Guard daily limits
        print("\n11. Gear Guard daily limits (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="gearguard_streaming.privacy.gearguard_streaming_daily_limit",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["gear_guard_limits"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["gear_guard_limits"] = False

        # Category 7: Vehicle Configuration (QUERIES)
        print("\n\n⚙️  VEHICLE CONFIGURATION")
        print("-" * 80)

        # 12. Vehicle wheels
        print("\n12. Vehicle wheels (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="vehicle.wheels.vehicle_wheels",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["vehicle_wheels"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["vehicle_wheels"] = False

        # 13. Passive entry status
        print("\n13. Passive entry status (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="vehicle_access.state.passive_entry",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["passive_entry"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["passive_entry"] = False

        # 14. OTA schedule configuration
        print("\n14. OTA schedule configuration (query)...")
        try:
            result = await client.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="ota.user_schedule.ota_config",
                payload=b"",
                phone_id=phone_id,
            )
            success = result.get("success", False)
            print(f"   {'✅' if success else '❌'} Success: {success}")
            results["ota_schedule"] = success
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            results["ota_schedule"] = False

    finally:
        await client.close()

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)

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

    print("\n" + "=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
