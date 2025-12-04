#!/usr/bin/env python3
"""Get the correct vehicle ID format."""

import asyncio
import json
import os

from dotenv import load_dotenv

from rivian import Rivian


async def main() -> None:
    """Get vehicle info."""
    load_dotenv()

    user_session_token = os.getenv("RIVIAN_USER_SESSION_TOKEN", "")

    async with Rivian(user_session_token=user_session_token) as client:
        user_info = await client.get_user_information()
        print("User info:")
        print(json.dumps(user_info, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
