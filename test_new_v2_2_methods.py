#!/usr/bin/env python3
"""Test all new v2.2 methods with real Rivian credentials."""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from rivian import Rivian
from rivian.rivian import BASE_HEADERS
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

VEHICLE_ID = os.getenv("RIVIAN_VEHICLE_ID")
ACCESS_TOKEN = os.getenv("RIVIAN_ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("RIVIAN_REFRESH_TOKEN")
USER_SESSION_TOKEN = os.getenv("RIVIAN_USER_SESSION_TOKEN")


async def test_user_account_methods(client: Rivian):
    """Test user & account methods."""
    print("\n" + "="*60)
    print("TESTING USER & ACCOUNT METHODS")
    print("="*60)

    # Test 1: Get referral code
    print("\n1. Testing get_referral_code()...")
    try:
        referral = await client.get_referral_code()
        print(f"   ✅ Success!")
        print(f"   Referral Code: {referral.get('code', referral.get('referralCode', 'N/A'))}")
        print(f"   Referral URL: {referral.get('url', 'N/A')}")
        print(f"   Full response: {referral}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 2: Get invitations
    print("\n2. Testing get_invitations_by_user()...")
    try:
        invites = await client.get_invitations_by_user()
        print(f"   ✅ Success!")
        print(f"   Found {len(invites)} invitation(s)")
        for i, invite in enumerate(invites, 1):
            print(f"   Invitation {i}:")
            print(f"      Vehicle: {invite.get('vehicleModel', 'N/A')}")
            print(f"      From: {invite.get('invitedByFirstName', 'N/A')}")
            print(f"      Status: {invite.get('status', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")


async def test_vehicle_services_methods(client: Rivian, vehicle_id: str):
    """Test vehicle services methods."""
    print("\n" + "="*60)
    print("TESTING VEHICLE SERVICES METHODS")
    print("="*60)

    # Test 3: Get service appointments
    print("\n3. Testing get_service_appointments()...")
    try:
        appointments = await client.get_service_appointments(vehicle_id)
        print(f"   ✅ Success!")
        print(f"   Found {len(appointments)} appointment(s)")
        for i, appt in enumerate(appointments, 1):
            print(f"   Appointment {i}:")
            print(f"      Type: {appt.get('serviceType', 'N/A')}")
            print(f"      Time: {appt.get('scheduledTime', 'N/A')}")
            print(f"      Status: {appt.get('status', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 4: Get active service requests
    print("\n4. Testing get_active_service_requests()...")
    try:
        requests = await client.get_active_service_requests(vehicle_id)
        print(f"   ✅ Success!")
        print(f"   Found {len(requests)} active request(s)")
        for i, req in enumerate(requests, 1):
            print(f"   Request {i}:")
            print(f"      Category: {req.get('category', 'N/A')}")
            print(f"      Description: {req.get('description', 'N/A')}")
            print(f"      Status: {req.get('status', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 5: Get provisioned users
    print("\n5. Testing get_vehicle_provisioned_users()...")
    try:
        users = await client.get_vehicle_provisioned_users(vehicle_id)
        print(f"   ✅ Success!")
        print(f"   Found {len(users)} user(s) with vehicle access")
        for i, user in enumerate(users, 1):
            print(f"   User {i}:")
            print(f"      Name: {user.get('firstName', '')} {user.get('lastName', '')}")
            print(f"      Email: {user.get('email', 'N/A')}")
            print(f"      Roles: {', '.join(user.get('roles', []))}")
            print(f"      Status: {user.get('status', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")


async def test_notification_methods(client: Rivian, vehicle_id: str):
    """Test notification methods."""
    print("\n" + "="*60)
    print("TESTING NOTIFICATION METHODS")
    print("="*60)

    # Test 6: Register notification tokens (bulk)
    print("\n6. Testing register_notification_tokens()...")
    try:
        # Use test tokens (these won't actually register but we can test the API call)
        test_tokens = [
            {
                "token": "test_ios_token_12345",
                "platform": "ios",
                "deviceId": "test_device_1",
                "appVersion": "4400"
            }
        ]
        result = await client.register_notification_tokens(test_tokens)
        print(f"   ✅ Success!")
        print(f"   Success: {result.get('success', 'N/A')}")
        print(f"   Message: {result.get('message', 'N/A')}")
        print(f"   Registered Tokens: {result.get('registeredTokens', [])}")
        if result.get('errors'):
            print(f"   Errors: {result.get('errors')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 7: Register single push notification token
    print("\n7. Testing register_push_notification_token()...")
    try:
        result = await client.register_push_notification_token(
            token="test_ios_token_single",
            platform="ios",
            vehicle_id=vehicle_id
        )
        print(f"   ✅ Success!")
        print(f"   Success: {result.get('success', 'N/A')}")
        print(f"   Message: {result.get('message', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 8: Register live notification token
    print("\n8. Testing register_live_notification_token()...")
    try:
        result = await client.register_live_notification_token(
            vehicle_id=vehicle_id,
            token="test_live_notification_token"
        )
        print(f"   ✅ Success!")
        print(f"   Success: {result.get('success', 'N/A')}")
        print(f"   Message: {result.get('message', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")


async def test_content_methods(client: Rivian, vehicle_id: str):
    """Test content/chat methods."""
    print("\n" + "="*60)
    print("TESTING CONTENT/CHAT METHODS")
    print("="*60)

    # Test 9: Get chat session
    print("\n9. Testing get_chat_session()...")
    try:
        session = await client.get_chat_session(vehicle_id)
        print(f"   ✅ Success!")
        print(f"   Session ID: {session.get('sessionId', 'N/A')}")
        print(f"   Active: {session.get('active', 'N/A')}")
        print(f"   Status: {session.get('status', 'N/A')}")
        print(f"   Created: {session.get('createdAt', 'N/A')}")
    except Exception as e:
        print(f"   ❌ Error: {e}")


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("RIVIAN PYTHON CLIENT v2.2 - NEW METHODS TEST SUITE")
    print("="*60)
    print(f"\nVehicle ID: {VEHICLE_ID}")
    print(f"Using iOS headers: {BASE_HEADERS.get('User-Agent', 'N/A')}")

    # Initialize client with existing tokens
    client = Rivian()

    # Set tokens directly
    client._access_token = ACCESS_TOKEN
    client._refresh_token = REFRESH_TOKEN
    client._user_session_token = USER_SESSION_TOKEN
    client._access_token_timestamp = asyncio.get_event_loop().time()

    try:
        # Run all test suites
        await test_user_account_methods(client)
        await test_vehicle_services_methods(client, VEHICLE_ID)
        await test_notification_methods(client, VEHICLE_ID)
        await test_content_methods(client, VEHICLE_ID)

        print("\n" + "="*60)
        print("TEST SUITE COMPLETE")
        print("="*60)
        print("\nSummary:")
        print("- All 9 new methods were tested")
        print("- Check output above for individual test results")
        print("- Some methods may fail if:")
        print("  - No data exists (e.g., no service appointments)")
        print("  - Endpoint requires special auth (e.g., chat session)")
        print("  - Test tokens are invalid (notification methods)")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
