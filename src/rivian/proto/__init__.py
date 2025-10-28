"""Protocol Buffer message definitions for Parallax protocol.

This package contains protobuf message classes for Rivian's Parallax protocol,
which is a cloud-based GraphQL/HTTP protocol for vehicle commands and data retrieval.
"""

from .base import SessionCost, TimeOfDay
from .charging import (
    ChargingScheduleTimeWindow,
    ChargingSessionChartData,
    ChargingSessionLiveData,
)
from .climate import CabinVentilationSetting, ClimateHoldSetting, ClimateHoldStatus
from .energy import ParkedEnergyMonitor
from .navigation import TripInfo, TripProgress, Waypoint
from .ota import OTAState
from .security import (
    GearGuardConsents,
    GearGuardDailyLimits,
    GeoFence,
    PassiveEntrySetting,
    PassiveEntryStatus,
    VehicleGeoFences,
)
from .vehicle import HalloweenSettings, VehicleWheels, WheelInfo

__all__ = [
    "SessionCost",
    "TimeOfDay",
    "ChargingScheduleTimeWindow",
    "ChargingSessionChartData",
    "ChargingSessionLiveData",
    "CabinVentilationSetting",
    "ClimateHoldSetting",
    "ClimateHoldStatus",
    "ParkedEnergyMonitor",
    "TripInfo",
    "TripProgress",
    "Waypoint",
    "OTAState",
    "GearGuardConsents",
    "GearGuardDailyLimits",
    "GeoFence",
    "PassiveEntrySetting",
    "PassiveEntryStatus",
    "VehicleGeoFences",
    "HalloweenSettings",
    "VehicleWheels",
    "WheelInfo",
]
