"""Opt-in gating for live tests.

Skipped unless RIVIAN_LIVE=1 AND credentials are present, so a normal `pytest`
run is unaffected and CI never needs secrets. These exist because the mocked
suite structurally cannot catch a whole class of defect: a mock returns whatever
shape the test author assumed, so a hand-written GraphQL query with a wrong field
name, a rejected websocket handshake, or an expired token all pass 119 mocked
tests and fail only in production.
"""

from __future__ import annotations

import os
import uuid

import pytest
from dotenv import load_dotenv

from rivian import Rivian

ENV_FILE = os.getenv(
    "RIVIAN_ENV_FILE", "/Users/jrgutier/src/ha-rivian/home-assistant-rivian/.env"
)
REQUIRED = ("RIVIAN_ACCESS_TOKEN", "RIVIAN_USER_SESSION_TOKEN")


_HERE = os.path.dirname(os.path.abspath(__file__))


def pytest_collection_modifyitems(config, items):
    """Skip this package unless explicitly enabled.

    Scoped to items under tests/live/ -- a conftest hook fires for the WHOLE
    session, so an unscoped version silently skipped all 129 mocked tests too.
    """
    if os.getenv("RIVIAN_LIVE") == "1":
        load_dotenv(ENV_FILE)
        if all(os.getenv(k) for k in REQUIRED):
            return
        reason = f"RIVIAN_LIVE=1 but {REQUIRED} not found in {ENV_FILE}"
    else:
        reason = "live tests are opt-in: set RIVIAN_LIVE=1"
    skip = pytest.mark.skip(reason=reason)
    for item in items:
        if str(item.fspath).startswith(_HERE):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def creds() -> dict[str, str]:
    load_dotenv(ENV_FILE)
    return {
        k: os.getenv(k, "")
        for k in (
            "RIVIAN_ACCESS_TOKEN",
            "RIVIAN_REFRESH_TOKEN",
            "RIVIAN_USER_SESSION_TOKEN",
        )
    }


@pytest.fixture
async def client(creds):
    """Authenticated client. Read-only use only."""
    async with Rivian(
        access_token=creds["RIVIAN_ACCESS_TOKEN"],
        refresh_token=creds["RIVIAN_REFRESH_TOKEN"],
        user_session_token=creds["RIVIAN_USER_SESSION_TOKEN"],
    ) as c:
        await c.create_csrf_token()
        yield c


@pytest.fixture
async def account(client):
    """vehicle_id and 16-byte phone_id from the live account."""
    resp = await client.get_user_information(include_phones=True)
    data = await resp.json()
    user = (data.get("data") or {}).get("currentUser") or {}
    vehicles = user.get("vehicles") or []
    phones = user.get("enrolledPhones") or []
    if not vehicles:
        pytest.skip("account has no vehicles")
    vas = (phones[0].get("vas") or {}).get("vasPhoneId") if phones else None
    return {
        "vehicle_id": vehicles[0].get("id"),
        "phone_id": uuid.UUID(vas).bytes if vas else None,
    }
