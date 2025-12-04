"""Debug GraphQL query generation."""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from gql import gql as std_gql
from gql.dsl import DSLMutation, DSLSchema, dsl_gql

from rivian import Rivian
from rivian.parallax import build_climate_status_query


async def main():
    """Debug the GraphQL query generation."""
    load_dotenv()

    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN")
    vehicle_id = os.getenv("RIVIAN_VEHICLE_ID")

    if not all([user_session_token, vehicle_id]):
        print("❌ Missing required environment variables")
        return

    # Initialize client
    client = Rivian(user_session_token=user_session_token)

    # Get the DSL schema
    await client._ensure_client("https://rivian.com/api/gql/gateway/graphql")

    # Build the climate status query command
    cmd = build_climate_status_query()

    print(f"RVM Type: {cmd.rvm}")
    print(f"Payload (Base64): '{cmd.payload_b64}'")
    print(f"Payload Length: {len(cmd.payload_b64)}")

    # Build the mutation using DSL
    assert client._ds is not None
    mutation = dsl_gql(
        DSLMutation(
            client._ds.Mutation.sendParallaxPayload.args(
                payload=cmd.payload_b64,
                meta={
                    "vehicleId": vehicle_id,
                    "model": str(cmd.rvm),
                    "isVehicleModelOp": True,
                    "requiresWakeup": True,
                },
            ).select(
                client._ds.ParallaxResponse.success,
                client._ds.ParallaxResponse.sequenceNumber,
            )
        )
    )

    print("\n" + "=" * 60)
    print("Generated GraphQL Query:")
    print("=" * 60)
    print(mutation)

    # Try to send it
    print("\n" + "=" * 60)
    print("Sending Request:")
    print("=" * 60)

    try:
        result = await client.send_parallax_command(vehicle_id, cmd)
        print(f"✅ Success: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")

    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
