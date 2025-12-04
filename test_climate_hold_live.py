#!/usr/bin/env python3
"""Live test for climate hold functionality using real Rivian credentials.

This script tests the corrected protobuf implementation for climate hold
commands based on APK analysis.
"""

import asyncio
import base64
import os
from dotenv import load_dotenv
import aiohttp

from src.rivian.rivian import Rivian
from src.rivian.parallax import build_climate_hold_command, build_climate_status_query


async def main():
    """Test climate hold query and command with real credentials."""
    # Load credentials from .env
    load_dotenv()

    username = os.getenv("RIVIAN_USERNAME")
    access_token = os.getenv("RIVIAN_ACCESS_TOKEN")
    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN")
    vehicle_id = os.getenv("RIVIAN_VEHICLE_ID")

    if not all([username, access_token, user_session_token, vehicle_id]):
        print("❌ Error: Missing required credentials in .env file")
        print("   Required: RIVIAN_USERNAME, RIVIAN_ACCESS_TOKEN, RIVIAN_USER_SESSION_TOKEN, RIVIAN_VEHICLE_ID")
        return

    print("=" * 70)
    print("Climate Hold Live Test (APK-Based Protobuf Implementation)")
    print("=" * 70)
    print(f"Vehicle ID: {vehicle_id}")
    print()

    # Initialize Rivian client with existing session
    async with aiohttp.ClientSession() as session:
        rivian = Rivian(
            user_session_token=user_session_token,
            session=session,
        )

        try:
            # Test 1: Query climate hold status
            print("📊 Test 1: Querying climate hold status...")
            print("-" * 70)

            cmd_status = build_climate_status_query()
            print(f"   RVM Type: {cmd_status.rvm}")
            print(f"   Payload (Base64): '{cmd_status.payload_b64}' (empty for query)")
            print(f"   Command ID: {cmd_status.command_id}")
            print()

            try:
                result_status = await rivian.send_parallax_command(vehicle_id, cmd_status)
            except Exception as e:
                print(f"   ⚠️  Query failed with error: {e}")
                print(f"   This might indicate the vehicle doesn't support climate hold via Parallax")
                print(f"   or requires different authentication/vehicle state.")
                print()
                # Continue to test the command anyway to see if it produces a different error
                result_status = None

            if result_status:
                print(f"✓ Status Query Result:")
                print(f"   Success: {result_status.get('success')}")
                print(f"   Sequence Number: {result_status.get('sequenceNumber')}")

            # Decode the response payload if present
            payload_b64 = result_status.get("payload", "") if result_status else ""
            if payload_b64:
                print(f"   Response Payload (Base64): {payload_b64}")
                try:
                    from src.rivian.proto.rivian_climate_pb2 import ClimateHoldStatus

                    payload_bytes = base64.b64decode(payload_b64)
                    status_msg = ClimateHoldStatus()
                    status_msg.ParseFromString(payload_bytes)

                    print(f"   Decoded Status:")
                    print(f"      Status: {ClimateHoldStatus.Status.Name(status_msg.status)}")
                    print(f"      Availability: {ClimateHoldStatus.Availability.Name(status_msg.availability)}")
                    if status_msg.unavailability_reason:
                        print(f"      Unavailability Reason: {ClimateHoldStatus.UnavailabilityReason.Name(status_msg.unavailability_reason)}")
                    if status_msg.hold_end_time.seconds:
                        print(f"      Hold End Time: {status_msg.hold_end_time.seconds}s (Unix timestamp)")
                except Exception as e:
                    print(f"   ⚠️  Could not decode response: {e}")
            print()

            # Test 2: Send climate hold command (2 hours)
            print("🔧 Test 2: Sending climate hold command (2 hours)...")
            print("-" * 70)

            cmd_set = build_climate_hold_command(duration_minutes=120)
            print(f"   RVM Type: {cmd_set.rvm}")
            print(f"   Duration: 120 minutes (7200 seconds)")
            print(f"   Payload (Base64): {cmd_set.payload_b64}")

            # Decode and inspect the protobuf message
            try:
                from src.rivian.proto.rivian_climate_pb2 import ClimateHoldSetting

                payload_bytes = base64.b64decode(cmd_set.payload_b64)
                setting_msg = ClimateHoldSetting()
                setting_msg.ParseFromString(payload_bytes)
                print(f"   Protobuf Field: hold_time_duration_seconds = {setting_msg.hold_time_duration_seconds}")
            except Exception as e:
                print(f"   ⚠️  Could not decode command payload: {e}")
            print()

            result_set = await rivian.send_parallax_command(vehicle_id, cmd_set)
            print(f"✓ Command Result:")
            print(f"   Success: {result_set.get('success')}")
            print(f"   Sequence Number: {result_set.get('sequenceNumber')}")

            # Decode the response payload if present
            payload_b64 = result_set.get("payload", "")
            if payload_b64:
                print(f"   Response Payload (Base64): {payload_b64}")
                # Response might be empty or contain acknowledgment
            print()

            # Test 3: Query status again to confirm
            print("📊 Test 3: Querying climate hold status again...")
            print("-" * 70)

            result_status2 = await rivian.send_parallax_command(vehicle_id, cmd_status)
            print(f"✓ Status Query Result (after command):")
            print(f"   Success: {result_status2.get('success')}")
            print(f"   Sequence Number: {result_status2.get('sequenceNumber')}")

            payload_b64 = result_status2.get("payload", "")
            if payload_b64:
                print(f"   Response Payload (Base64): {payload_b64}")
                try:
                    from src.rivian.proto.rivian_climate_pb2 import ClimateHoldStatus

                    payload_bytes = base64.b64decode(payload_b64)
                    status_msg = ClimateHoldStatus()
                    status_msg.ParseFromString(payload_bytes)

                    print(f"   Decoded Status:")
                    print(f"      Status: {ClimateHoldStatus.Status.Name(status_msg.status)}")
                    print(f"      Availability: {ClimateHoldStatus.Availability.Name(status_msg.availability)}")
                    if status_msg.unavailability_reason:
                        print(f"      Unavailability Reason: {ClimateHoldStatus.UnavailabilityReason.Name(status_msg.unavailability_reason)}")
                    if status_msg.hold_end_time.seconds:
                        print(f"      Hold End Time: {status_msg.hold_end_time.seconds}s (Unix timestamp)")
                except Exception as e:
                    print(f"   ⚠️  Could not decode response: {e}")
            print()

            print("=" * 70)
            print("✓ All tests completed successfully!")
            print("=" * 70)

        except Exception as e:
            print(f"❌ Error occurred: {e}")
            import traceback
            traceback.print_exc()

        finally:
            await rivian.close()


if __name__ == "__main__":
    asyncio.run(main())
