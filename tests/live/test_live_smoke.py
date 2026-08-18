"""Read-only smoke tests against the real Rivian API.

Every assertion here covers a layer the mocked suite cannot reach. Each test
names the specific defect class it exists to catch, because a live test that
merely "checks the API works" decays into noise.

Nothing here changes vehicle state: Parallax reads use an empty payload, which
send_vehicle_operation encodes as operation_type=0 (GET).
"""

from __future__ import annotations

import asyncio
import base64

import pytest

pytestmark = pytest.mark.asyncio

# Verified accepted by sendVehicleOperation. Three are queries; climate_hold_setting
# is the one command, exercised here only in its empty-payload (read) form.
READABLE_RVMS = [
    "comfort.cabin.climate_hold_status",
    "comfort.cabin.climate_hold_setting",
    "vehicle.wheels.vehicle_wheels",
    "ota.user_schedule.ota_config",
]


async def test_credentials_are_still_valid(client) -> None:
    """Catches: an expired token, which makes every other live result meaningless.

    Runs first so a stale credential reports as one clear failure rather than as
    a cascade of confusing ones.
    """
    resp = await client.get_user_information()
    assert resp.status == 200, f"HTTP {resp.status}"
    body = await resp.json()
    assert not body.get("errors"), body.get("errors")


async def test_user_information_returns_the_documented_shape(client) -> None:
    """Catches: upstream changing a field name the integration reads.

    The mocked tests assert against a fixture written from this same shape, so
    they agree with themselves no matter what Rivian actually returns.
    """
    body = await (await client.get_user_information(include_phones=True)).json()
    user = (body.get("data") or {}).get("currentUser") or {}
    assert "vehicles" in user, sorted(user)
    for vehicle in user.get("vehicles") or []:
        assert vehicle.get("id"), "vehicle without an id"
        assert "vas" in vehicle, sorted(vehicle)


async def test_phone_id_is_sixteen_bytes(account) -> None:
    """Catches: the 32-byte phone_id claim that survived in nine docstrings.

    phone_id is uuid.UUID(vasPhoneId).bytes. Sending the wrong width would be
    rejected by the vehicle, not by any local check.
    """
    if account["phone_id"] is None:
        pytest.skip("no enrolled phone on this account")
    assert len(account["phone_id"]) == 16


@pytest.mark.parametrize("rvm", READABLE_RVMS)
async def test_send_vehicle_operation_query_is_accepted(client, account, rvm) -> None:
    """Catches: a malformed sendVehicleOperation GraphQL string.

    THE reason this file exists. That query was hand-written when the transport
    moved off gql, and a wrong field or operation name would satisfy every mocked
    test while failing against Rivian. Empty payload = operation_type 0 = GET.
    """
    if account["phone_id"] is None:
        pytest.skip("no enrolled phone on this account")
    result = await client.send_vehicle_operation(
        vehicle_id=account["vehicle_id"],
        rvm_type=rvm,
        payload=b"",
        phone_id=account["phone_id"],
    )
    assert isinstance(result, dict) and result, f"empty response for {rvm}: {result!r}"
    assert result.get("success") is True, result


async def test_send_vehicle_operation_rejects_an_unknown_rvm(client, account) -> None:
    """Catches: a query that returns success for everything.

    Without a negative case the test above passes even if the server ignores the
    rvm entirely, which would hide a broken protobuf envelope.
    """
    if account["phone_id"] is None:
        pytest.skip("no enrolled phone on this account")
    try:
        result = await client.send_vehicle_operation(
            vehicle_id=account["vehicle_id"],
            rvm_type="not.a.real.rvm",
            payload=b"",
            phone_id=account["phone_id"],
        )
    except Exception:
        return
    assert result.get("success") is not True, (
        "an unknown RVM reported success; sendVehicleOperation is not validating rvm_type"
    )


async def test_parallax_subscription_completes_its_handshake(client, account) -> None:
    """Catches: a websocket that connects but is never acknowledged.

    Observed live: the socket opens (connected True) while connection_ack never
    arrives, so subscribe_for_* times out, swallows the error and returns None.
    Every mocked subscription test passes throughout, because none of them speak
    the handshake. Asserting on the ack rather than on the return value is what
    distinguishes "rejected" from "no data yet".
    """
    unsub = await client.subscribe_for_parallax_messages(
        vehicle_id=account["vehicle_id"], callback=lambda _data: None, rvms=None
    )
    monitor = getattr(client, "_ws_monitor", None)
    ack = getattr(monitor, "connection_ack", None) if monitor else None
    acked = bool(ack and ack.is_set())
    try:
        assert acked, (
            "websocket connected but connection_ack never arrived - the "
            "connection_init payload was rejected"
        )
        assert unsub is not None, (
            "subscription returned None despite a completed handshake"
        )
    finally:
        if unsub:
            await unsub()


async def test_parallax_subscription_delivers_telemetry(client, account) -> None:
    """Catches: a live subscription that acks but never pushes.

    Separate from the handshake test so the two failure modes stay
    distinguishable in a report.
    """
    received: list[dict] = []
    unsub = await client.subscribe_for_parallax_messages(
        vehicle_id=account["vehicle_id"], callback=received.append, rvms=None
    )
    if unsub is None:
        pytest.skip("subscription unavailable - see the handshake test")
    try:
        await asyncio.sleep(20)
    finally:
        await unsub()
    assert received, "no Parallax frames in 20s while the vehicle was reachable"
    payloads = [
        ((f.get("data") or {}).get("parallaxMessages") or {}).get("payload")
        for f in received
    ]
    decoded = [base64.b64decode(p) for p in payloads if p]
    assert decoded, f"frames arrived but none carried a payload: {received[:1]}"
