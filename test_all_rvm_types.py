"""Test all 18 Parallax RVM types with live credentials."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

from rivian import Rivian
from rivian.parallax import (
    RVMType,
    build_charging_chart_query,
    build_charging_schedule_command,
    build_charging_session_query,
    build_climate_hold_command,
    build_climate_status_query,
    build_gear_guard_consents_command,
    build_gear_guard_consents_query,
    build_gear_guard_limits_query,
    build_geofences_command,
    build_geofences_query,
    build_halloween_command,
    build_ota_schedule_command,
    build_ota_schedule_query,
    build_ota_status_query,
    build_parked_energy_query,
    build_passive_entry_command,
    build_passive_entry_status_query,
    build_trip_info_query,
    build_trip_progress_query,
    build_vehicle_wheels_query,
    build_ventilation_command,
)


async def test_rvm_type(client: Rivian, vehicle_id: str, name: str, command, verbose: bool = False):
    """Test a single RVM type."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"RVM Type: {command.rvm}")
    print(f"{'='*60}")

    try:
        result = await client.send_parallax_command(vehicle_id, command)
        print(f"✅ SUCCESS")
        print(f"Response: {result}")
        return {"name": name, "rvm": command.rvm, "status": "SUCCESS", "result": result}
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: {error_msg}")

        # Show full exception details in verbose mode
        if verbose:
            print(f"\n📋 Exception Type: {type(e).__name__}")
            print(f"📋 Exception Module: {type(e).__module__}")

            # Show exception attributes
            if hasattr(e, '__dict__'):
                print(f"📋 Exception Attributes:")
                for key, value in e.__dict__.items():
                    print(f"   - {key}: {value}")

            # Check for __cause__ (original exception)
            if hasattr(e, '__cause__') and e.__cause__:
                print(f"\n📋 Original Exception: {type(e.__cause__).__name__}")
                if hasattr(e.__cause__, 'errors'):
                    print(f"📋 GraphQL Errors Detail:")
                    import json
                    print(json.dumps(e.__cause__.errors, indent=2))
                if hasattr(e.__cause__, 'data'):
                    print(f"📋 GraphQL Response Data:")
                    import json
                    print(json.dumps(e.__cause__.data, indent=2))

            # Show stack trace
            import traceback
            print(f"\n📋 Stack Trace:")
            traceback.print_exc()

        # Determine error type
        if "OMS_ERROR" in error_msg:
            status = "OMS_ERROR"
        elif "UNAUTHORIZED" in error_msg or "Unauthenticated" in error_msg:
            status = "AUTH_ERROR"
        elif "INVALID" in error_msg:
            status = "INVALID_REQUEST"
        else:
            status = "UNKNOWN_ERROR"

        return {"name": name, "rvm": command.rvm, "status": status, "error": error_msg, "exception_type": type(e).__name__}


async def main():
    """Test all 18 RVM types."""
    # Load environment variables
    load_dotenv()

    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN")
    access_token = os.getenv("RIVIAN_ACCESS_TOKEN")

    if not user_session_token:
        print("❌ Missing required environment variable: RIVIAN_USER_SESSION_TOKEN")
        return

    print(f"Access Token: {'✅ Available' if access_token else '❌ Not Available'}")

    # Initialize client with user session token and access token
    client = Rivian(user_session_token=user_session_token, access_token=access_token)

    # Create fresh CSRF token
    print("\n" + "="*60)
    print("Creating Fresh CSRF Token...")
    print("="*60)

    try:
        await client.create_csrf_token()
        print("✅ CSRF token created successfully")
    except Exception as e:
        print(f"⚠️  Warning: Could not create CSRF token: {e}")
        print("Continuing with existing session...")

    # Dynamically fetch vehicle ID from user information
    print("\n" + "="*60)
    print("Fetching Vehicle Information...")
    print("="*60)

    try:
        user_info = await client.get_user_information()
        vehicles = user_info.get("vehicles", [])

        if not vehicles:
            print("❌ No vehicles found for this account")
            await client.close()
            return

        # Use the first vehicle
        vehicle = vehicles[0]
        vehicle_account_id = vehicle.get("id")
        vehicle_vin = vehicle.get("vin", "Unknown")
        vehicle_name = vehicle.get("name", "Unknown")

        # Get VAS (Vehicle Access System) ID for Parallax commands
        vas = vehicle.get("vas", {})
        vehicle_id = vas.get("vasVehicleId")

        print(f"✅ Found {len(vehicles)} vehicle(s)")
        print(f"Using Vehicle: {vehicle_name}")
        print(f"VIN: {vehicle_vin}")
        print(f"Account Vehicle ID: {vehicle_account_id}")
        print(f"VAS Vehicle ID: {vehicle_id}")

        if not vehicle_id:
            print("❌ VAS Vehicle ID is empty")
            await client.close()
            return

    except Exception as e:
        print(f"❌ Error fetching vehicle information: {e}")
        await client.close()
        return

    results = []

    # Enable verbose mode for detailed error analysis
    verbose_mode = True

    # ========================================
    # QUERY OPERATIONS (Read-only, empty payload)
    # ========================================

    print("\n" + "="*60)
    print("PART 1: QUERY OPERATIONS (Read-only)")
    print("="*60)
    print("Note: Verbose mode enabled for detailed error analysis")

    # Energy & Charging Queries
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Parked Energy Monitor (Query)",
        build_parked_energy_query(),
        verbose=verbose_mode
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "Charging Chart Data (Query)",
        build_charging_chart_query(),
        verbose=False  # Disable after first test to reduce noise
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "Charging Session Live Data (Query)",
        build_charging_session_query(),
        verbose=False
    ))

    # Climate Queries (enable verbose to see OMS_ERROR details)
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Climate Hold Status (Query)",
        build_climate_status_query(),
        verbose=verbose_mode
    ))

    # OTA Queries
    results.append(await test_rvm_type(
        client, vehicle_id,
        "OTA Update Status (Query)",
        build_ota_status_query()
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "OTA Schedule Configuration (Query)",
        build_ota_schedule_query()
    ))

    # Navigation Queries
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Trip Progress (Query)",
        build_trip_progress_query()
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "Trip Info (Query)",
        build_trip_info_query()
    ))

    # Security Queries
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Geofences (Query)",
        build_geofences_query()
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "GearGuard Consents (Query)",
        build_gear_guard_consents_query()
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "GearGuard Daily Limits (Query)",
        build_gear_guard_limits_query()
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "Passive Entry Status (Query)",
        build_passive_entry_status_query()
    ))

    # Vehicle Queries
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Vehicle Wheels (Query)",
        build_vehicle_wheels_query()
    ))

    # ========================================
    # COMMAND OPERATIONS (Write, with payloads)
    # ========================================

    print("\n" + "="*60)
    print("PART 2: COMMAND OPERATIONS (Write)")
    print("="*60)

    # Climate Commands
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Climate Hold Command (3 hours)",
        build_climate_hold_command(duration_minutes=180)
    ))

    # Charging Commands
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Charging Schedule Command (12am-6am)",
        build_charging_schedule_command(
            start_hour=0, start_minute=0,
            end_hour=6, end_minute=0,
            amps=32
        )
    ))

    # OTA Commands
    results.append(await test_rvm_type(
        client, vehicle_id,
        "OTA Schedule Command (Daily 2am)",
        build_ota_schedule_command([{
            "id": "test_schedule",
            "is_enabled": True,
            "type": "daily",
            "starts_at_min": 120  # 2:00 AM
        }])
    ))

    # Security Commands
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Geofences Command (Home)",
        build_geofences_command([{
            "type": "HOME",
            "name": "Test Home"
        }])
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "GearGuard Consents Command",
        build_gear_guard_consents_command(consent_status="CONSENTED")
    ))

    results.append(await test_rvm_type(
        client, vehicle_id,
        "Passive Entry Command (60s)",
        build_passive_entry_command(duration_seconds=60)
    ))

    # Ventilation Command
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Cabin Ventilation Command",
        build_ventilation_command(enabled=True, mode="NORMAL")
    ))

    # Halloween Command
    results.append(await test_rvm_type(
        client, vehicle_id,
        "Halloween Settings Command",
        build_halloween_command(light_show_enabled=False)
    ))

    # ========================================
    # SUMMARY
    # ========================================

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    oms_error_count = sum(1 for r in results if r["status"] == "OMS_ERROR")
    auth_error_count = sum(1 for r in results if r["status"] == "AUTH_ERROR")
    invalid_count = sum(1 for r in results if r["status"] == "INVALID_REQUEST")
    other_error_count = sum(1 for r in results if r["status"] == "UNKNOWN_ERROR")

    print(f"\nTotal RVM Types Tested: {len(results)}")
    print(f"✅ Successful: {success_count}")
    print(f"⚠️  OMS_ERROR: {oms_error_count}")
    print(f"🔒 Auth Errors: {auth_error_count}")
    print(f"❌ Invalid Request: {invalid_count}")
    print(f"❓ Other Errors: {other_error_count}")

    # Group by status
    print("\n" + "-"*60)
    print("RESULTS BY STATUS:")
    print("-"*60)

    for status in ["SUCCESS", "OMS_ERROR", "AUTH_ERROR", "INVALID_REQUEST", "UNKNOWN_ERROR"]:
        matching = [r for r in results if r["status"] == status]
        if matching:
            print(f"\n{status} ({len(matching)}):")
            for r in matching:
                print(f"  • {r['name']}")
                print(f"    RVM: {r['rvm']}")
                if "error" in r:
                    # Truncate long error messages
                    error = r["error"]
                    if len(error) > 100:
                        error = error[:100] + "..."
                    print(f"    Error: {error}")

    # Close client
    await client.close()

    print("\n" + "="*60)
    print("Testing Complete!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
