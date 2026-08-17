"""Parallax protocol: telemetry decoding and vehicle-operation commands.

Two halves that meet here.

READ -- decodes base64 protobuf payloads from the Parallax WebSocket subscription
into structured dicts. Hand-rolled varint parsing, no protobuf dependency.
Reference: https://github.com/kaedenbrinkman/rivian-api (RivDocs)

WRITE -- builds outbound Parallax operations: the RVMType catalogue reverse
engineered from the Android app (EnumC6207c.java) and the build_* helpers that
produce payloads for send_vehicle_operation.

The two were developed independently -- upstream is read-only, this fork added
the write path -- and share no symbols, which is why they simply sit side by
side. Only one RVM overlaps them at all
(energy_edge_compute.graphs.charging_graph_global).

Note the asymmetry: every RVM here can be *read*, but Rivian currently accepts
only one as a *write* (comfort.cabin.climate_hold_setting). The other builders
are retained until the entities that call them are removed.
"""

from __future__ import annotations

import base64
import logging
import struct
import sys
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from backports.strenum import StrEnum

from google.protobuf import message as _message

_LOGGER = logging.getLogger(__name__)

CLOSURE_MAP = {
    1: "doorFrontLeftClosed",
    2: "doorFrontRightClosed",
    3: "doorRearLeftClosed",
    4: "doorRearRightClosed",
    5: "closureFrunkClosed",
    6: "closureSideBinLeftClosed",
    7: "closureLiftgateClosed",
}

LOCK_MAP = {
    1: "doorFrontLeftLocked",
    2: "doorFrontRightLocked",
    3: "doorRearLeftLocked",
    4: "doorRearRightLocked",
    5: "closureFrunkLocked",
    7: "closureLiftgateLocked",
}

POWER_STATE_MAP = {
    1: "sleep",
    2: "standby",
    3: "ready",
    4: "go",
}

TIRE_POSITION_MAP = {
    1: "FrontLeft",
    2: "FrontRight",
    3: "RearLeft",
    4: "RearRight",
}


def _decode_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Decode a protobuf varint, return (value, new_offset)."""
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        shift += 7
        offset += 1
        if not (byte & 0x80):
            break
    return result, offset


def _decode_protobuf_fields(data: bytes) -> list[tuple[int, int, Any]]:
    """Decode raw protobuf bytes into a list of (field_number, wire_type, value) tuples."""
    fields = []
    i = 0
    while i < len(data):
        tag, i = _decode_varint(data, i)
        field_num = tag >> 3
        wire_type = tag & 0x07
        value: Any

        if wire_type == 0:  # Varint
            value, i = _decode_varint(data, i)
            fields.append((field_num, wire_type, value))
        elif wire_type == 1:  # 64-bit float
            if i + 8 <= len(data):
                value = struct.unpack("<d", data[i : i + 8])[0]
                i += 8
                fields.append((field_num, wire_type, value))
            else:
                break
        elif wire_type == 2:  # Length-delimited
            length, i = _decode_varint(data, i)
            if i + length <= len(data):
                value = data[i : i + length]
                i += length
                fields.append((field_num, wire_type, value))
            else:
                break
        elif wire_type == 5:  # 32-bit float
            if i + 4 <= len(data):
                value = struct.unpack("<f", data[i : i + 4])[0]
                i += 4
                fields.append((field_num, wire_type, value))
            else:
                break
        else:
            _LOGGER.debug("Unknown wire type %d for field %d", wire_type, field_num)
            break

    return fields


def decode_battery_state(payload: str) -> dict[str, Any]:
    """Decode energy.high_voltage.battery_state.

    Returns dict with keys:
        - soc: float (percentage, 0-100)
        - packEnergyKwh: float
        - rangeKm: float (if present)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 2:
                # Nested charge_state message
                inner_fields = _decode_protobuf_fields(value)
                for inner_num, inner_wt, inner_val in inner_fields:
                    if inner_num == 1 and inner_wt == 1:  # soc (float)
                        result["soc"] = round(inner_val, 2)
                    elif inner_num == 2 and inner_wt == 1:  # packEnergyKwh (float)
                        result["packEnergyKwh"] = round(inner_val, 2)
                    elif inner_num == 3 and inner_wt == 5:  # rangeKm (float)
                        result["rangeKm"] = round(inner_val, 1)

        return result
    except Exception:
        _LOGGER.debug("Failed to decode battery_state payload", exc_info=True)
        return {}


def decode_cabin_temperatures(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_temperatures.

    Returns dict with keys:
        - cabinClimateInteriorTemperature: float (Celsius)
        - cabinClimateDriverTemperature: float (Celsius)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 3 and wire_type == 5:  # interior temp (float, Celsius)
                result["cabinClimateInteriorTemperature"] = round(value, 1)
            if field_num == 4 and wire_type == 5:  # interior temp (float, Celsius)
                result["cabinClimateDriverTemperature"] = round(value, 1)

        return result
    except Exception:
        _LOGGER.debug("Failed to decode cabin temperatures payload", exc_info=True)
        return {}


def decode_charge_session_breakdown(payload: str) -> dict[str, Any]:
    """Decode energy_edge_compute.graphs.charge_session_breakdown.

    Returns dict with keys matching legacy getLiveSessionData field names:
        - totalChargedEnergy: float (kWh total)
        - power: float (kW, current charge rate)
        - timeElapsed: int (seconds, estimated)
        - rangeAddedThisSession: float (km, estimated from energy)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        total_kwh = 0.0

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 5:  # totalKwh (float)
                total_kwh = round(value, 4)
                result["totalChargedEnergy"] = total_kwh
            elif field_num == 9 and wire_type == 5:  # currentPower (float, kW)
                result["power"] = round(value, 2)
            elif field_num == 7 and wire_type == 0:  # timeRemainingMins or elapsed secs
                result["_time_field_7"] = value
            elif field_num == 10 and wire_type == 0:  # charge power integer (kW)
                if "power" not in result:
                    result["power"] = float(value)
            elif field_num == 13 and wire_type == 0:  # chargingState enum
                result["_charging_state"] = value

        # Estimate range added: ~3.5 km/kWh (~2.17 mi/kWh) is a typical Rivian average
        if total_kwh > 0:
            result["rangeAddedThisSession"] = round(total_kwh * 3.5, 1)

        # Derive charge rate (km/h) from current power (kW)
        if "power" in result:
            p = result["power"]
            result["kilometersChargedPerHour"] = round(p * 3.5, 1) if p > 0 else 0.0

        return result
    except Exception:
        _LOGGER.debug(
            "Failed to decode charge_session_breakdown payload", exc_info=True
        )
        return {}


def decode_charging_graph_global(payload: str) -> dict[str, Any]:
    """Decode energy_edge_compute.graphs.charging_graph_global.

    Returns dict with keys:
        - startTime: str (ISO format timestamp of session start)
        - timeElapsed: int (seconds elapsed since session start)
        - power: float (kW, latest segment power)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        outer = _decode_protobuf_fields(data)
        segments = []
        for field_num, wire_type, value in outer:
            if field_num == 1 and wire_type == 2:
                inner = _decode_protobuf_fields(value)
                seg: dict[str, Any] = {}
                for in_num, in_wt, in_val in inner:
                    if in_num == 1 and in_wt == 0:
                        seg["soc"] = in_val
                    elif in_num == 2 and in_wt == 5:
                        seg["power"] = round(in_val, 2)
                    elif in_num == 3 and in_wt == 0:
                        seg["start_ms"] = in_val
                    elif in_num == 4 and in_wt == 0:
                        seg["end_ms"] = in_val
                    elif in_num == 6 and in_wt == 0:
                        seg["state"] = in_val
                segments.append(seg)

        if not segments:
            return {}

        active_segments = [
            s for s in segments if s.get("power", 0) > 0 or s.get("state") == 3
        ]

        first_seg = active_segments[0] if active_segments else segments[0]
        result: dict[str, Any] = {}

        if "start_ms" in first_seg:
            st = datetime.fromtimestamp(first_seg["start_ms"] / 1000, timezone.utc)
            result["startTime"] = st.strftime("%Y-%m-%dT%H:%M:%S.%f%z")

        if active_segments:
            result["timeElapsed"] = sum(
                max(0, int((s["end_ms"] - s["start_ms"]) / 1000))
                for s in active_segments
                if "end_ms" in s and "start_ms" in s
            )
        else:
            result["timeElapsed"] = 0

        latest_segment = segments[-1]
        if (
            "power" in latest_segment
            and latest_segment.get("power", 0) > 0
            and latest_segment.get("state") != 8
        ):
            result["power"] = latest_segment["power"]
            result["kilometersChargedPerHour"] = round(result["power"] * 3.5, 1)
        else:
            result["power"] = 0.0
            result["kilometersChargedPerHour"] = 0.0

        return result
    except Exception:
        _LOGGER.debug("Failed to decode charging_graph_global payload", exc_info=True)
        return {}


def decode_charging_session_status(payload: str) -> dict[str, Any]:
    """Decode charging.session.status.

    Returns dict with keys:
        - plugConnectionStatus: int (enum)
        - displayStatus: int (enum)
        - evseType: int (enum)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["plugConnectionStatus"] = value
            elif field_num == 2 and wire_type == 0:
                result["displayStatus"] = value
            elif field_num == 3 and wire_type == 0:
                result["evseType"] = value

        return result
    except Exception:
        _LOGGER.debug("Failed to decode charging.session.status payload", exc_info=True)
        return {}


def decode_closures(payload: str) -> dict[str, Any]:
    """Decode body.closures.states.

    Returns dict with keys:
        - doorFrontLeftClosed, doorFrontRightClosed, closureFrunkClosed, etc. ("closed" / "open")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 2:  # Repeated nested closure state
                inner = _decode_protobuf_fields(value)
                cid = None
                state_val = None
                for in_num, in_type, in_val in inner:
                    if in_num == 1 and in_type == 0:
                        cid = in_val
                    elif in_num == 2 and in_type == 0:
                        state_val = in_val

                if cid and cid in CLOSURE_MAP and state_val is not None:
                    # 1 = open, 2 = closed
                    result[CLOSURE_MAP[cid]] = "closed" if state_val == 2 else "open"

        return result
    except Exception:
        _LOGGER.debug("Failed to decode closures payload", exc_info=True)
        return {}


def decode_defrost(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.defrost_defog_status.

    Returns dict with keys:
        - defrostDefogStatus: str ("Defrost", "Off")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["defrostDefogStatus"] = "Defrost" if value == 2 else "Off"
        return result
    except Exception:
        _LOGGER.debug("Failed to decode defrost payload", exc_info=True)
        return {}


def decode_gnss(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.gnss.

    Returns dict with keys:
        - gnssLocation: {"latitude": float, "longitude": float, "timeStamp": str}
        - gnssAltitude: float (meters)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        lat = None
        lon = None
        alt = None
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 1:  # latitude (float)
                lat = round(value, 6)
            elif field_num == 2 and wire_type == 1:  # longitude (float)
                lon = round(value, 6)
            elif field_num == 3 and wire_type == 1:  # altitude (float)
                alt = round(value, 1)

        result: dict[str, Any] = {}
        if lat is not None and lon is not None:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            result["gnssLocation"] = {
                "latitude": lat,
                "longitude": lon,
                "timeStamp": now_iso,
            }
        if alt is not None:
            result["gnssAltitude"] = alt
        return result
    except Exception:
        _LOGGER.debug("Failed to decode dynamics.vehicle.gnss payload", exc_info=True)
        return {}


def decode_locks(payload: str) -> dict[str, Any]:
    """Decode body.locks.states.

    Returns dict with keys:
        - doorFrontLeftLocked, closureFrunkLocked, etc. ("locked" / "unlocked")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 2:  # Repeated nested lock state
                inner = _decode_protobuf_fields(value)
                lid = None
                state_val = None
                for in_num, in_type, in_val in inner:
                    if in_num == 1 and in_type == 0:
                        lid = in_val
                    elif in_num == 2 and in_type == 0:
                        state_val = in_val

                if lid and lid in LOCK_MAP and state_val is not None:
                    # 1 = locked, 2 = unlocked
                    result[LOCK_MAP[lid]] = "locked" if state_val == 1 else "unlocked"

        return result
    except Exception:
        _LOGGER.debug("Failed to decode locks payload", exc_info=True)
        return {}


def decode_odometer(payload: str) -> dict[str, Any]:
    """Decode dynamics.vehicle.odometer.

    Returns dict with keys:
        - vehicleMileage: float (meters)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                # Value is distance in km; HA expects meters
                result["vehicleMileage"] = value * 1000

        return result
    except Exception:
        _LOGGER.debug("Failed to decode odometer payload", exc_info=True)
        return {}


def decode_power_state(payload: str) -> dict[str, Any]:
    """Decode vehicle.power.state.

    Returns dict with keys:
        - powerState: str ("sleep", "standby", "ready", "go")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["powerState"] = POWER_STATE_MAP.get(value, "standby")

        return result
    except Exception:
        _LOGGER.debug("Failed to decode power state payload", exc_info=True)
        return {}


def decode_preconditioning(payload: str) -> dict[str, Any]:
    """Decode comfort.cabin.cabin_preconditioning_status.

    Returns dict with keys:
        - cabinPreconditioningStatus: str ("active", "initiate", "off")
    """
    if not payload:
        return {"cabinPreconditioningStatus": "off"}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        status_val = None
        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                status_val = value

        if status_val == 4:
            return {"cabinPreconditioningStatus": "active"}
        elif status_val in (1, 2):
            return {"cabinPreconditioningStatus": "initiate"}
        return {"cabinPreconditioningStatus": "off"}
    except Exception:
        _LOGGER.debug("Failed to decode preconditioning payload", exc_info=True)
        return {}


def decode_time_estimation(payload: str) -> dict[str, Any]:
    """Decode charging.session.time_estimation.

    Returns dict with keys:
        - timeToEndOfCharge: int (seconds remaining)
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 1 and wire_type == 0:
                result["timeToEndOfCharge"] = value

        return result
    except Exception:
        _LOGGER.debug("Failed to decode time_estimation payload", exc_info=True)
        return {}


def decode_tires(payload: str) -> dict[str, Any]:
    """Decode dynamics.tires.state.

    Returns dict with keys:
        - tirePressureFrontLeft, tirePressureFrontRight, etc. (bar)
        - tirePressureStatusFrontLeft, etc. ("OK")
    """
    if not payload:
        return {}
    try:
        data = base64.b64decode(payload)
        fields = _decode_protobuf_fields(data)
        result: dict[str, Any] = {}

        for field_num, wire_type, value in fields:
            if field_num == 2 and wire_type == 2:  # Repeated nested tire state
                inner = _decode_protobuf_fields(value)
                pos = None
                status = None
                pressure = None
                for in_num, in_type, in_val in inner:
                    if in_num == 1 and in_type == 0:
                        pos = in_val
                    elif in_num == 2 and in_type == 0:
                        status = "OK" if in_val == 1 else "Warning"
                    elif in_num == 3 and in_type == 1:  # 64-bit float (bar)
                        pressure = round(in_val, 2)

                if pos and pos in TIRE_POSITION_MAP:
                    suffix = TIRE_POSITION_MAP[pos]
                    if pressure is not None:
                        result[f"tirePressure{suffix}"] = pressure
                    if status is not None:
                        result[f"tirePressureStatus{suffix}"] = status

        return result
    except Exception:
        _LOGGER.debug("Failed to decode tires payload", exc_info=True)
        return {}


# Map of RVM topic -> decoder function
RVM_DECODERS: dict[str, Callable[[str], dict[str, Any]]] = {
    "body.closures.states": decode_closures,
    "body.locks.states": decode_locks,
    "charging.session.status": decode_charging_session_status,
    "charging.session.time_estimation": decode_time_estimation,
    "comfort.cabin.cabin_preconditioning_status": decode_preconditioning,
    "comfort.cabin.cabin_temperatures": decode_cabin_temperatures,
    "comfort.cabin.defrost_defog_status": decode_defrost,
    "dynamics.tires.state": decode_tires,
    "dynamics.vehicle.gnss": decode_gnss,
    "dynamics.vehicle.odometer": decode_odometer,
    "energy.high_voltage.battery_state": decode_battery_state,
    "energy_edge_compute.graphs.charge_session_breakdown": decode_charge_session_breakdown,
    "energy_edge_compute.graphs.charging_graph_global": decode_charging_graph_global,
    "vehicle.power.state": decode_power_state,
}

# Full list of Parallax RVMs subscribed for vehicle & charging telemetry
PARALLAX_RVMS: list[str] = list(RVM_DECODERS.keys())
CHARGING_RVMS: list[str] = [
    "charging.session.notification",
    "charging.session.remote_command",
    "charging.session.soc_slider",
    "charging.session.status",
    "charging.session.time_estimation",
    "energy.high_voltage.battery_state",
    "energy_edge_compute.graphs.charge_session_breakdown",
    "energy_edge_compute.graphs.charging_graph_global",
]


def decode_parallax_message(
    rvm: str, payload: str, **kwargs: Any
) -> dict[str, Any] | None:
    """Decode a Parallax message payload given its RVM topic.

    Accepts the GraphQL message fields directly (rvm, payload, and optional kwargs/timestamp).
    Returns a dict of decoded fields, or None if no decoder exists for this RVM.
    """
    decoder = RVM_DECODERS.get(rvm)
    if decoder is None:
        _LOGGER.warning("Unknown Parallax RVM topic %s", rvm)
        return None
    return decoder(payload)


# ======================================================================
# WRITE PATH -- outbound Parallax operations (this fork; not in upstream)
# ======================================================================


class RVMType(StrEnum):
    """Remote Vehicle Module types supported by Parallax protocol.

    All 18 RVM types from Rivian's Android app (EnumC6207c.java).
    Phase 1 focuses on types marked with ✓.
    """

    # Energy & Charging
    PARKED_ENERGY_MONITOR = "energy_edge_compute.graphs.parked_energy_distributions"
    CHARGING_SESSION_CHART_DATA = "energy_edge_compute.graphs.charging_graph_global"
    CHARGING_SESSION_LIVE_DATA = (
        "energy_edge_compute.graphs.charge_session_breakdown"  # ✓ Phase 1
    )
    CHARGING_SCHEDULE_TIME_WINDOW = "charging.schedule.time_window"  # ✓ Phase 1

    # Geofence
    VEHICLE_GEO_FENCES = "geofence.geofence_service.favoriteGeofences"

    # OTA Updates
    OTA_SCHEDULE_CONFIGURATION = "ota.user_schedule.ota_config"
    OTA_STATE = "ota.ota_state.vehicle_ota_state"  # ✓ Phase 1

    # GearGuard
    GEAR_GUARD_CONSENTS = (
        "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent"
    )
    GEAR_GUARD_DAILY_LIMITS = (
        "gearguard_streaming.privacy.gearguard_streaming_daily_limit"
    )

    # Vehicle
    VEHICLE_WHEELS = "vehicle.wheels.vehicle_wheels"

    # Navigation
    TRIP_INFO = "navigation.navigation_service.trip_info"
    TRIP_PROGRESS = "navigation.navigation_service.trip_progress"  # ✓ Phase 1

    # Climate & Comfort
    CLIMATE_HOLD_SETTING = "comfort.cabin.climate_hold_setting"  # ✓ Phase 1
    CABIN_VENTILATION_SETTING = "comfort.cabin.cabin_ventilation_setting"
    CLIMATE_HOLD_STATUS = "comfort.cabin.climate_hold_status"  # ✓ Phase 1

    # Vehicle Access
    PASSIVE_ENTRY_SETTING = "vehicle_access.passive_entry.passive_entry"
    PASSIVE_ENTRY_STATUS = "vehicle_access.state.passive_entry"

    # Holiday Celebrations
    HALLOWEEN_SETTINGS = (
        "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings"
    )


class ParallaxCommand:
    """Parallax command wrapper for cloud-based vehicle operations.

    Attributes:
        rvm: Remote Vehicle Module type
        payload_b64: Base64-encoded protobuf payload
        command_id: Unique command identifier
    """

    def __init__(self, rvm: RVMType, payload: bytes, command_id: str | None = None):
        """Initialize ParallaxCommand.

        Args:
            rvm: RVM type identifier
            payload: Protobuf message bytes (operation-specific)
            command_id: Optional command UUID (generated if not provided)
        """
        self.rvm = rvm
        self.payload_b64 = base64.b64encode(payload).decode() if payload else ""
        self.command_id = command_id or str(uuid.uuid4())

    @property
    def name(self) -> str:
        """Get command name for logging/debugging."""
        return f"parallax_{self.rvm}"

    @classmethod
    def from_protobuf(
        cls, rvm: RVMType, message: _message.Message, command_id: str | None = None
    ) -> ParallaxCommand:
        """Create ParallaxCommand from a protobuf message.

        Args:
            rvm: RVM type identifier
            message: Protobuf message instance
            command_id: Optional command UUID

        Returns:
            ParallaxCommand instance with serialized message
        """
        payload = message.SerializeToString()
        return cls(rvm, payload, command_id)


# Helper functions for Phase 1 RVM types


def build_charging_session_query() -> ParallaxCommand:
    """Build a query for charging session live data.

    Returns:
        ParallaxCommand for RVM #3 (CHARGING_SESSION_LIVE_DATA)

    Example:
        >>> cmd = build_charging_session_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.CHARGING_SESSION_LIVE_DATA, b"")


def build_parked_energy_query() -> ParallaxCommand:
    """Build command to query parked energy monitor data.

    Returns:
        ParallaxCommand for PARKED_ENERGY_MONITOR

    Example:
        >>> cmd = build_parked_energy_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    return ParallaxCommand(RVMType.PARKED_ENERGY_MONITOR, b"")


def build_charging_chart_query() -> ParallaxCommand:
    """Build command to query charging session chart data.

    Returns:
        ParallaxCommand for CHARGING_SESSION_CHART_DATA

    Example:
        >>> cmd = build_charging_chart_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    return ParallaxCommand(RVMType.CHARGING_SESSION_CHART_DATA, b"")


def build_climate_status_query() -> ParallaxCommand:
    """Build a query for climate hold status.

    Returns:
        ParallaxCommand for RVM #14 (CLIMATE_HOLD_STATUS)

    Example:
        >>> cmd = build_climate_status_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.CLIMATE_HOLD_STATUS, b"")


def build_climate_hold_command(duration_minutes: int = 120) -> ParallaxCommand:
    """Build a climate hold command.

    Args:
        duration_minutes: Hold duration in minutes (converted to seconds)

    Returns:
        ParallaxCommand for RVM #12 (CLIMATE_HOLD_SETTING)

    Note:
        Based on APK analysis, ClimateHoldSetting only has one field:
        hold_time_duration_seconds. Temperature and enabled state are not
        part of the protobuf message - they may be controlled separately
        via GraphQL or other commands.

    Example:
        >>> cmd = build_climate_hold_command(120)  # 2 hours
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_climate_pb2 import ClimateHoldSetting

    # Convert minutes to seconds as per APK definition
    setting = ClimateHoldSetting(hold_time_duration_seconds=duration_minutes * 60)

    return ParallaxCommand.from_protobuf(RVMType.CLIMATE_HOLD_SETTING, setting)


def build_charging_schedule_command(
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
    start_day: int = 0,
    end_day: int = 6,
    amps: int = 48,
) -> ParallaxCommand:
    """Build a charging schedule command.

    Args:
        start_hour: Start hour (0-23)
        start_minute: Start minute (0-59)
        end_hour: End hour (0-23)
        end_minute: End minute (0-59)
        start_day: Start day of week (0=Sunday, 6=Saturday)
        end_day: End day of week (0=Sunday, 6=Saturday)
        amps: Charging amperage limit (default: 48A)

    Returns:
        ParallaxCommand for RVM #16 (CHARGING_SCHEDULE_TIME_WINDOW)

    Note:
        Based on APK analysis, the structure is:
        ChargingScheduleTimeWindow (is_valid, WindowData)
          └─ WindowData (start_time/end_time as seconds since midnight)

    Example:
        >>> # Charge only between 10 PM and 6 AM every day
        >>> cmd = build_charging_schedule_command(22, 0, 6, 0)
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_base_pb2 import Location
    from .proto.rivian_charging_pb2 import ChargingScheduleTimeWindow, WindowData

    # Convert time to seconds since midnight (0-86399)
    start_time_seconds = start_hour * 3600 + start_minute * 60
    end_time_seconds = end_hour * 3600 + end_minute * 60

    # Calculate duration in seconds
    if end_time_seconds > start_time_seconds:
        duration = end_time_seconds - start_time_seconds
    else:
        # Handle overnight schedules
        duration = (86400 - start_time_seconds) + end_time_seconds

    # Create WindowData with all required fields
    window_data = WindowData(
        start_time=start_time_seconds,
        end_time=end_time_seconds,
        duration=duration,
        amps=amps,
        location=Location(),  # Empty location for global schedule
        start_day_of_week=start_day,
        end_day_of_week=end_day,
    )

    # Wrap in ChargingScheduleTimeWindow
    schedule = ChargingScheduleTimeWindow(
        is_valid=True,
        window_data=window_data,
    )

    return ParallaxCommand.from_protobuf(
        RVMType.CHARGING_SCHEDULE_TIME_WINDOW, schedule
    )


def build_ota_status_query() -> ParallaxCommand:
    """Build a query for OTA update status.

    Returns:
        ParallaxCommand for RVM #6 (OTA_STATE)

    Example:
        >>> cmd = build_ota_status_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.OTA_STATE, b"")


def build_trip_progress_query() -> ParallaxCommand:
    """Build a query for trip progress.

    Returns:
        ParallaxCommand for RVM #11 (TRIP_PROGRESS)

    Example:
        >>> cmd = build_trip_progress_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.TRIP_PROGRESS, b"")


# Phase 2: Security & Access helper functions


def build_geofences_query() -> ParallaxCommand:
    """Build a query for vehicle geofences.

    Returns:
        ParallaxCommand for RVM #5 (VEHICLE_GEO_FENCES)

    Example:
        >>> cmd = build_geofences_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.VEHICLE_GEO_FENCES, b"")


def build_geofences_command(fences: list[dict]) -> ParallaxCommand:
    """Build a command to set vehicle favorite geofences.

    Args:
        fences: List of geofence definitions, each with:
            - type: Geofence type ("HOME", "WORK", "CUSTOM")
            - name: Human-readable name

    Returns:
        ParallaxCommand for RVM #4 (VEHICLE_GEO_FENCES)

    Note:
        Based on APK analysis (tj.C20772b), geofences only contain type
        and name. Geographic coordinates are managed server-side.

    Example:
        >>> fences = [
        ...     {"type": "HOME", "name": "Home"},
        ...     {"type": "WORK", "name": "Office"},
        ... ]
        >>> cmd = build_geofences_command(fences)
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_security_pb2 import FavoriteGeofences, Geofence, GeofenceType

    # Map string types to enum values
    type_map = {
        "HOME": GeofenceType.GEOFENCE_TYPE_HOME,
        "WORK": GeofenceType.GEOFENCE_TYPE_WORK,
        "CUSTOM": GeofenceType.GEOFENCE_TYPE_CUSTOM,
    }

    geofence_objects = [
        Geofence(
            type=type_map.get(
                f.get("type", "CUSTOM").upper(), GeofenceType.GEOFENCE_TYPE_CUSTOM
            ),
            name=f.get("name", ""),
        )
        for f in fences
    ]

    favorite_geofences = FavoriteGeofences(favorites=geofence_objects)

    return ParallaxCommand.from_protobuf(RVMType.VEHICLE_GEO_FENCES, favorite_geofences)


def build_gear_guard_consents_query() -> ParallaxCommand:
    """Build a query for GearGuard consent settings.

    Returns:
        ParallaxCommand for RVM #7 (GEAR_GUARD_CONSENTS)

    Example:
        >>> cmd = build_gear_guard_consents_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.GEAR_GUARD_CONSENTS, b"")


def build_gear_guard_consents_command(
    consent_status: str = "CONSENTED",
) -> ParallaxCommand:
    """Build a command to set GearGuard consent settings.

    Args:
        consent_status: Consent status - one of:
            "CONSENTED", "NOT_CONSENTED", "NOT_APPLICABLE", "UNKNOWN"

    Returns:
        ParallaxCommand for RVM #7 (GEAR_GUARD_CONSENTS)

    Note:
        Based on APK analysis (sj.C20102g), GearGuard consents only has
        one field: user_consent (enum), not individual permission flags.

    Example:
        >>> cmd = build_gear_guard_consents_command("CONSENTED")
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_security_pb2 import (
        GearGuardConsentStatus,
        GearGuardStreamingInVehicleConsent,
    )

    # Map string to enum value
    status_map = {
        "CONSENTED": GearGuardConsentStatus.GEAR_GUARD_CONSENTED,
        "NOT_CONSENTED": GearGuardConsentStatus.GEAR_GUARD_NOT_CONSENTED,
        "NOT_APPLICABLE": GearGuardConsentStatus.GEAR_GUARD_NOT_APPLICABLE,
        "UNKNOWN": GearGuardConsentStatus.GEAR_GUARD_UNKNOWN,
    }

    consent = GearGuardStreamingInVehicleConsent(
        user_consent=status_map.get(
            consent_status.upper(), GearGuardConsentStatus.GEAR_GUARD_CONSENTED
        )
    )

    return ParallaxCommand.from_protobuf(RVMType.GEAR_GUARD_CONSENTS, consent)


def build_gear_guard_limits_query() -> ParallaxCommand:
    """Build a query for GearGuard daily usage limits.

    Returns:
        ParallaxCommand for RVM #8 (GEAR_GUARD_DAILY_LIMITS)

    Example:
        >>> cmd = build_gear_guard_limits_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.GEAR_GUARD_DAILY_LIMITS, b"")


def build_passive_entry_status_query() -> ParallaxCommand:
    """Build a query for passive entry status.

    Returns:
        ParallaxCommand for RVM #16 (PASSIVE_ENTRY_STATUS)

    Example:
        >>> cmd = build_passive_entry_status_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.PASSIVE_ENTRY_STATUS, b"")


def build_passive_entry_command(duration_seconds: int = 3600) -> ParallaxCommand:
    """Build a command to set passive entry duration.

    Args:
        duration_seconds: How long passive entry stays active (seconds)

    Returns:
        ParallaxCommand for RVM #15 (PASSIVE_ENTRY_SETTING)

    Note:
        Based on APK analysis (p979qj.C18913s), PassiveEntrySetting only has
        one field: hold_time_duration_seconds. This controls how long the
        passive entry feature remains active.

    Example:
        >>> cmd = build_passive_entry_command(duration_seconds=3600)  # 1 hour
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_security_pb2 import PassiveEntrySetting

    setting = PassiveEntrySetting(hold_time_duration_seconds=duration_seconds)

    return ParallaxCommand.from_protobuf(RVMType.PASSIVE_ENTRY_SETTING, setting)


# Phase 2 helper functions


def build_vehicle_wheels_query() -> ParallaxCommand:
    """Build a query for vehicle wheels configuration.

    Returns:
        ParallaxCommand for RVM #10 (VEHICLE_WHEELS)

    Example:
        >>> cmd = build_vehicle_wheels_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.VEHICLE_WHEELS, b"")


def build_trip_info_query() -> ParallaxCommand:
    """Build a query for detailed trip information.

    Returns:
        ParallaxCommand for RVM #44 (TRIP_INFO)

    Example:
        >>> cmd = build_trip_info_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.TRIP_INFO, b"")


def build_ventilation_command(
    enabled: bool,
    mode: str = "AUTO",
    windows_open_percent: int = 0,
    sunroof_open_percent: int = 0,
    duration_minutes: int = 30,
) -> ParallaxCommand:
    """Build a cabin ventilation command.

    Args:
        enabled: Whether to enable ventilation
        mode: Ventilation mode ("AUTO", "MANUAL", "OFF")
        windows_open_percent: Window opening percentage (0-100)
        sunroof_open_percent: Sunroof opening percentage (0-100)
        duration_minutes: Duration in minutes

    Returns:
        ParallaxCommand for RVM #49 (CABIN_VENTILATION_SETTING)

    Example:
        >>> # Open windows 50% and sunroof 100% for 30 minutes
        >>> cmd = build_ventilation_command(True, "MANUAL", 50, 100, 30)
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_climate_pb2 import CabinVentilationSetting

    setting = CabinVentilationSetting(
        enabled=enabled,
        mode=mode,
        windows_open_percent=windows_open_percent,
        sunroof_open_percent=sunroof_open_percent,
        duration_minutes=duration_minutes,
    )

    return ParallaxCommand.from_protobuf(RVMType.CABIN_VENTILATION_SETTING, setting)


def build_halloween_command(
    light_show_enabled: bool = True,
    motion_light_sound_enabled: bool = True,
    costume_theme: str = "",
    lights_color: str = "",
) -> ParallaxCommand:
    """Build a Halloween celebration settings command.

    Args:
        light_show_enabled: Whether to enable light show
        motion_light_sound_enabled: Enable motion-triggered lights/sounds
        costume_theme: Costume theme name (optional)
        lights_color: Light color scheme (optional)

    Returns:
        ParallaxCommand for RVM #18 (HALLOWEEN_SETTINGS)

    Note:
        Based on APK analysis (p1072vj.C21876n), Halloween settings have
        13 fields with many wrapper messages. This is a simplified version.
        The full message structure includes sound, music, and lighting configs.

    Example:
        >>> cmd = build_halloween_command(
        ...     light_show_enabled=True,
        ...     motion_light_sound_enabled=True,
        ...     costume_theme="SPOOKY",
        ... )
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from .proto.rivian_vehicle_pb2 import (
        BoolValue,
        HalloweenCelebrationSettings,
        HalloweenCostumeTheme,
        StringValue,
    )

    # Build costume theme if provided
    costume = HalloweenCostumeTheme(theme_name=costume_theme) if costume_theme else None

    # Build wrapper messages
    light_show = BoolValue(value=light_show_enabled)
    lights_color_msg = StringValue(value=lights_color) if lights_color else None

    setting = HalloweenCelebrationSettings(
        costume_theme=costume,
        light_show_enabled=light_show,
        motion_light_sound_enabled=motion_light_sound_enabled,
        lights_color=lights_color_msg,
    )

    return ParallaxCommand.from_protobuf(RVMType.HALLOWEEN_SETTINGS, setting)


# OTA Schedule Configuration helper functions


def build_ota_schedule_query() -> ParallaxCommand:
    """Build a query for OTA schedule configuration.

    Returns:
        ParallaxCommand for RVM #5 (OTA_SCHEDULE_CONFIGURATION)

    Example:
        >>> cmd = build_ota_schedule_query()
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    # Read operations use empty payload
    return ParallaxCommand(RVMType.OTA_SCHEDULE_CONFIGURATION, b"")


def build_ota_schedule_command(
    schedules: list[dict],
) -> ParallaxCommand:
    """Build a command to set OTA update schedules.

    Args:
        schedules: List of schedule definitions, each with:
            - id: Unique schedule ID
            - is_enabled: Whether schedule is active
            - type: "daily" or "once"
            - starts_at_min: (for daily) Minutes since midnight (0-1439)
            - starts_at_utc: (for once) ISO timestamp string
            - geofence_location: (optional) Location identifier

    Returns:
        ParallaxCommand for RVM #5 (OTA_SCHEDULE_CONFIGURATION)

    Example:
        >>> schedules = [
        ...     {
        ...         "id": "daily_home",
        ...         "is_enabled": True,
        ...         "type": "daily",
        ...         "starts_at_min": 120,  # 2:00 AM
        ...         "geofence_location": "home",
        ...     }
        ... ]
        >>> cmd = build_ota_schedule_command(schedules)
        >>> result = await client.send_parallax_command("VIN123", cmd)
    """
    from datetime import datetime

    from google.protobuf.timestamp_pb2 import Timestamp

    from .proto.rivian_vehicle_pb2 import (
        OtaConfig,
        OtaGeofence,
        OtaRepeatsDaily,
        OtaSchedule,
        OtaSingleOccurrence,
    )

    schedule_objects = []
    for s in schedules:
        schedule_id = s.get("id", "")
        is_enabled = s.get("is_enabled", True)
        schedule_type = s.get("type", "daily")

        if schedule_type == "daily":
            # Daily repeating schedule
            geofence = None
            if "geofence_location" in s:
                geofence = OtaGeofence(location=s["geofence_location"])

            repeats_daily = OtaRepeatsDaily(
                starts_at_min=s.get("starts_at_min", 0),
                geofence=geofence if geofence else OtaGeofence(),
            )
            schedule_objects.append(
                OtaSchedule(
                    id=schedule_id,
                    is_enabled=is_enabled,
                    repeats_daily=repeats_daily,
                )
            )
        else:
            # Single occurrence schedule
            starts_at_utc = s.get("starts_at_utc", "")
            if starts_at_utc:
                # Parse ISO timestamp
                dt = datetime.fromisoformat(starts_at_utc.replace("Z", "+00:00"))
                timestamp = Timestamp(seconds=int(dt.timestamp()))
            else:
                timestamp = Timestamp()

            single_occurrence = OtaSingleOccurrence(starts_at_utc=timestamp)
            schedule_objects.append(
                OtaSchedule(
                    id=schedule_id,
                    is_enabled=is_enabled,
                    single_occurrence=single_occurrence,
                )
            )

    config = OtaConfig(
        schedules=schedule_objects,
        timestamp=Timestamp(seconds=int(datetime.now(timezone.utc).timestamp())),
    )

    return ParallaxCommand.from_protobuf(RVMType.OTA_SCHEDULE_CONFIGURATION, config)
