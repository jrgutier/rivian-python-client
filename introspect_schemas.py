#!/usr/bin/env python3
"""Introspect actual GraphQL schemas from Rivian API endpoints."""

import asyncio
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from rivian import Rivian
from rivian.rivian import GRAPHQL_GATEWAY, GRAPHQL_VEHICLE_SERVICES, GRAPHQL_CONTENT
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("RIVIAN_ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("RIVIAN_REFRESH_TOKEN")
USER_SESSION_TOKEN = os.getenv("RIVIAN_USER_SESSION_TOKEN")


async def introspect_endpoint(client: Rivian, endpoint_name: str, endpoint_url: str):
    """Introspect a GraphQL endpoint to get its actual schema."""
    print(f"\n{'='*60}")
    print(f"Introspecting: {endpoint_name}")
    print(f"URL: {endpoint_url}")
    print(f"{'='*60}\n")

    try:
        gql_client = await client._ensure_client(endpoint_url)

        # Get the schema
        schema = gql_client.schema

        # Get Query type
        query_type = schema.query_type
        print(f"Query Type Fields ({len(query_type.fields)}):")
        print("-" * 60)

        # Look for operations related to our methods
        keywords = [
            'referral', 'invitation', 'appointment', 'service', 'request',
            'notification', 'token', 'chat', 'session', 'provision', 'user'
        ]

        matching_fields = []
        for field_name, field in query_type.fields.items():
            if any(keyword in field_name.lower() for keyword in keywords):
                matching_fields.append((field_name, field))

        if matching_fields:
            print("\nRelevant Query Operations Found:")
            for field_name, field in sorted(matching_fields):
                args = ", ".join([f"{arg}: {arg_type.type}" for arg, arg_type in field.args.items()])
                print(f"  - {field_name}({args}): {field.type}")
        else:
            print("  No matching query fields found")

        # Get Mutation type
        if schema.mutation_type:
            mutation_type = schema.mutation_type
            print(f"\nMutation Type Fields ({len(mutation_type.fields)}):")
            print("-" * 60)

            matching_mutations = []
            for field_name, field in mutation_type.fields.items():
                if any(keyword in field_name.lower() for keyword in keywords):
                    matching_mutations.append((field_name, field))

            if matching_mutations:
                print("\nRelevant Mutation Operations Found:")
                for field_name, field in sorted(matching_mutations):
                    args = ", ".join([f"{arg}: {arg_type.type}" for arg, arg_type in field.args.items()])
                    print(f"  - {field_name}({args}): {field.type}")
            else:
                print("  No matching mutation fields found")
        else:
            print("\n  No mutations defined")

        return True

    except Exception as e:
        print(f"❌ Error introspecting {endpoint_name}: {e}")
        return False


async def main():
    """Introspect all Rivian GraphQL endpoints."""
    print("\n" + "="*60)
    print("RIVIAN API - GRAPHQL SCHEMA INTROSPECTION")
    print("="*60)

    # Initialize client with existing tokens
    client = Rivian()
    client._access_token = ACCESS_TOKEN
    client._refresh_token = REFRESH_TOKEN
    client._user_session_token = USER_SESSION_TOKEN
    client._access_token_timestamp = asyncio.get_event_loop().time()

    try:
        # Introspect each endpoint
        endpoints = [
            ("Gateway", GRAPHQL_GATEWAY),
            ("Vehicle Services", GRAPHQL_VEHICLE_SERVICES),
            ("Content", GRAPHQL_CONTENT),
        ]

        results = {}
        for name, url in endpoints:
            success = await introspect_endpoint(client, name, url)
            results[name] = success

        # Summary
        print("\n" + "="*60)
        print("INTROSPECTION COMPLETE")
        print("="*60)
        for name, success in results.items():
            status = "✅ Success" if success else "❌ Failed"
            print(f"{name}: {status}")

        print("\n💡 Use the field names above to update the Python client methods!")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
