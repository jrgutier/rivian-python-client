"""Rivian constants."""
from __future__ import annotations

from typing import Final

LIVE_SESSION_PROPERTIES: Final[set[str]] = {
    "chargerId",
    "currentCurrency",
    "currentPrice",
    "isFreeSession",
    "isRivianCharger",
    "kilometersChargedPerHour",
    "locationId",
    "power",
    "rangeAddedThisSession",
    "startTime",
    "timeElapsed",
    "timeRemaining",
    "totalChargedEnergy",
    "vehicleChargerState",
}

VEHICLE_STATE_PROPERTIES: Final[set[str]] = {
    # VehicleLocation
    "gnssLocation",
    # TimeStamped(String|Float|Int)
    "alarmSoundStatus",
    "batteryHvThermalEvent",
    "batteryHvThermalEventPropagation",
    "batteryLevel",
    "batteryLimit",
    "brakeFluidLow",
    "cabinClimateDriverTemperature",
    "cabinClimateInteriorTemperature",
    "cabinPreconditioningStatus",
    "cabinPreconditioningType",
    "chargerDerateStatus",
    "chargerState",
    "chargerStatus",
    "closureFrunkClosed",
    "closureFrunkLocked",
    "closureFrunkNextAction",
    "closureLiftgateClosed",
    "closureLiftgateLocked",
    "closureLiftgateNextAction",
    "closureSideBinLeftClosed",
    "closureSideBinLeftLocked",
    "closureSideBinRightClosed",
    "closureSideBinRightLocked",
    "closureTailgateClosed",
    "closureTailgateLocked",
    "closureTonneauClosed",
    "closureTonneauLocked",
    "defrostDefogStatus",
    "distanceToEmpty",
    "doorFrontLeftClosed",
    "doorFrontLeftLocked",
    "doorFrontRightClosed",
    "doorFrontRightLocked",
    "doorRearLeftClosed",
    "doorRearLeftLocked",
    "doorRearRightClosed",
    "doorRearRightLocked",
    "driveMode",
    "gearGuardLocked",
    "gearGuardVideoMode",
    "gearGuardVideoStatus",
    "gearGuardVideoTermsAccepted",
    "gearStatus",
    "otaAvailableVersion",
    "otaAvailableVersionGitHash",
    "otaAvailableVersionNumber",
    "otaAvailableVersionWeek",
    "otaAvailableVersionYear",
    "otaCurrentStatus",
    "otaCurrentVersion",
    "otaCurrentVersionGitHash",
    "otaCurrentVersionNumber",
    "otaCurrentVersionWeek",
    "otaCurrentVersionYear",
    "otaDownloadProgress",
    "otaInstallDuration",
    "otaInstallProgress",
    "otaInstallReady",
    "otaInstallTime",
    "otaInstallType",
    "otaStatus",
    "petModeStatus",
    "petModeTemperatureStatus",
    "powerState",
    "rangeThreshold",
    "remoteChargingAvailable",
    "seatFrontLeftHeat",
    "seatFrontLeftVent",
    "seatFrontRightHeat",
    "seatFrontRightVent",
    "seatRearLeftHeat",
    "seatRearRightHeat",
    "seatThirdRowLeftHeat",
    "seatThirdRowRightHeat",
    "serviceMode",
    "steeringWheelHeat",
    "timeToEndOfCharge",
    "tirePressureStatusFrontLeft",
    "tirePressureStatusFrontRight",
    "tirePressureStatusRearLeft",
    "tirePressureStatusRearRight",
    "tirePressureStatusValidFrontLeft",
    "tirePressureStatusValidFrontRight",
    "tirePressureStatusValidRearLeft",
    "tirePressureStatusValidRearRight",
    "vehicleMileage",
    "windowFrontLeftCalibrated",
    "windowFrontLeftClosed",
    "windowFrontRightCalibrated",
    "windowFrontRightClosed",
    "windowRearLeftCalibrated",
    "windowRearLeftClosed",
    "windowRearRightCalibrated",
    "windowRearRightClosed",
    "wiperFluidState",
}
