"""Response tests data."""

from __future__ import annotations

import json
import os
from typing import Any

AUTHENTICATION_RESPONSE = {
    "data": {
        "login": {
            "__typename": "MobileLoginResponse",
            "accessToken": "valid_access_token",
            "refreshToken": "valid_refresh_token",
            "userSessionToken": "valid_user_session_token",
        }
    }
}
AUTHENTICATION_OTP_RESPONSE = {
    "data": {
        "loginWithOTP": {
            "__typename": "MobileLoginResponse",
            "accessToken": "token",
            "refreshToken": "token",
            "userSessionToken": "token",
        }
    }
}
CSRF_TOKEN_RESPONSE = {
    "data": {
        "createCsrfToken": {
            "__typename": "CreateCsrfTokenResponse",
            "csrfToken": "valid_csrf_token",
            "appSessionToken": "valid_app_session_token",
        }
    }
}
OTP_TOKEN_RESPONSE = {
    "data": {
        "login": {
            "__typename": "MobileMFALoginResponse",
            "otpToken": "token",
        }
    }
}
USER_INFORMATION_RESPONSE = {
    "data": {
        "currentUser": {
            "__typename": "User",
            "id": "id",
            "firstName": "firstName",
            "lastName": "lastName",
            "email": "email",
            "vehicles": [
                {
                    "__typename": "UserVehicle",
                    "id": "id",
                    "owner": None,
                    "roles": ["primary-owner"],
                    "name": "R1T",
                    "vin": "vin",
                    "vas": {
                        "__typename": "UserVehicleAccess",
                        "vasVehicleId": "vasVehicleId",
                        "vehiclePublicKey": "vehiclePublicKey",
                    },
                    "vehicle": {
                        "__typename": "Vehicle",
                        "model": "R1T",
                        "mobileConfiguration": {
                            "__typename": "VehicleMobileConfiguration",
                            "trimOption": {
                                "__typename": "VehicleMobileConfigurationOption",
                                "optionId": "PKG-ADV",
                                "optionName": "Adventure Package",
                            },
                            "exteriorColorOption": {
                                "__typename": "VehicleMobileConfigurationOption",
                                "optionId": "EXP-LST",
                                "optionName": "Limestone",
                            },
                            "interiorColorOption": {
                                "__typename": "VehicleMobileConfigurationOption",
                                "optionId": "INT-GYP",
                                "optionName": "Ocean Coast + Dark Ash Wood",
                            },
                        },
                        "vehicleState": {
                            "__typename": "VehicleState",
                            "supportedFeatures": [
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "ADDR_SHR",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "ADDR_SHR_YLP",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "CHARG_CMD",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "CHARG_SCHED",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "CHARG_SLIDER",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "DEFROST_DEFOG",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "FRUNK_NXT_ACT",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "GEAR_GUARD_VIDEO_SETTING",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "SIDE_BIN_NXT_ACT",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "HEATED_SEATS",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "HEATED_WHEEL",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "RENAME_VEHICLE",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "PET_MODE",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "PRECON_CMD_RESP",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "PRECON_SCRN_PROT",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "SET_TEMP_CMD",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "TAILGATE_CMD",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "TAILGATE_NXT_ACT",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "VENTED_SEATS",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "WIN_CALIB_STS",
                                    "status": "AVAILABLE",
                                },
                                {
                                    "__typename": "SupportedFeature",
                                    "name": "TRIP_PLANNER",
                                    "status": "AVAILABLE",
                                },
                            ],
                        },
                    },
                    "settings": {
                        "__typename": "UserVehicleSettingsMap",
                        "name": {
                            "__typename": "NameSetting",
                            "value": "R1T",
                        },
                    },
                }
            ],
            "enrolledPhones": [
                {
                    "__typename": "UserEnrolledPhone",
                    "vas": {
                        "__typename": "UserEnrolledPhoneAccess",
                        "vasPhoneId": "vasPhoneId",
                        "publicKey": "publicKey",
                    },
                    "enrolled": [
                        {
                            "__typename": "UserEnrolledPhoneEntry",
                            "deviceType": "phone/rivian",
                            "deviceName": "deviceName",
                            "vehicleId": "vehicleId",
                            "identityId": "identityId",
                        }
                    ],
                }
            ],
            "pendingInvites": [],
            "address": {"__typename": "UserAddress", "country": "US"},
        }
    }
}
WALLBOXES_RESPONSE = {
    "data": {
        "getRegisteredWallboxes": [
            {
                "__typename": "WallboxRecord",
                "wallboxId": "W1-1113-3RV7-1-1234-00012",
                "userId": "01-2a3259ba-0be3-42a7-bf82-69adea27dcdd-2b4532cd",
                "wifiId": "Network",
                "name": "Wall Charger",
                "linked": True,
                "latitude": "42.3601866",
                "longitude": "-71.0589682",
                "chargingStatus": "AVAILABLE",
                "power": None,
                "currentVoltage": None,
                "currentAmps": None,
                "softwareVersion": "V03.01.47",
                "model": "W1-1113-3RV7",
                "serialNumber": "W1-1113-3RV7-1-1234-00012",
                "maxAmps": None,
                "maxVoltage": "224.0",
                "maxPower": "11000",
            }
        ]
    }
}

DISENROLL_PHONE_BAD_REQUEST_RESPONSE = {
    "errors": [
        {
            "extensions": {
                "code": "BAD_REQUEST_ERROR",
                "reason": "DISENROLL_PHONE_BAD_REQUEST",
            },
            "message": "Bad request error",
            "path": ["disenrollPhone"],
        }
    ],
    "data": None,
}

ENROLL_PHONE_RESPONSE = {
    "data": {
        "enrollPhone": {
            "__typename": "EnrollPhoneResponse",
            "success": True,
        }
    }
}

DISENROLL_PHONE_RESPONSE = {
    "data": {
        "disenrollPhone": {
            "__typename": "DisenrollPhoneResponse",
            "success": True,
        }
    }
}

SEND_VEHICLE_COMMAND_RESPONSE = {
    "data": {
        "sendVehicleCommand": {
            "__typename": "SendVehicleCommandResponse",
            "id": "command-id-123",
            "command": "WAKE_VEHICLE",
            "state": "sent",
        }
    }
}

SEND_LOCATION_TO_VEHICLE_RESPONSE = {
    "data": {
        "parseAndShareLocationToVehicle": {
            "__typename": "ParseAndShareLocationToVehicleResponse",
            "publishResponse": {
                "__typename": "PublishResponse",
                "result": 0,
            },
        }
    }
}

MOCK_GET_CHARGING_SCHEDULES_RESPONSE = {
    "data": {
        "getChargingSchedules": {
            "__typename": "ChargingSchedulesResponse",
            "schedules": [
                {
                    "__typename": "DepartureSchedule",
                    "id": "schedule_123",
                    "name": "Weekday Commute",
                    "enabled": True,
                    "days": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
                    "departureTime": "08:00",
                    "cabinPreconditioning": True,
                    "cabinPreconditioningTemp": 21.0,
                    "targetSOC": 80,
                    "offPeakHoursOnly": False,
                    "location": {
                        "__typename": "ScheduleLocation",
                        "latitude": 37.7749,
                        "longitude": -122.4194,
                        "radius": 100.0,
                    },
                },
                {
                    "__typename": "DepartureSchedule",
                    "id": "schedule_456",
                    "name": "Weekend Trip",
                    "enabled": False,
                    "days": ["SATURDAY", "SUNDAY"],
                    "departureTime": "10:00",
                    "cabinPreconditioning": False,
                    "cabinPreconditioningTemp": None,
                    "targetSOC": 100,
                    "offPeakHoursOnly": True,
                    "location": None,
                },
            ],
            "smartChargingEnabled": True,
            "vehicleId": "vehicle_abc",
        }
    }
}

def error_response(
    code: str | None = None, reason: str | None = None
) -> dict[str, Any]:
    """Return an error response."""
    error = {"extensions": {"code": code, "reason": reason or code}} if code else {}
    return {"errors": [error]}


def load_response(response_name: str) -> dict[str, Any]:
    """Load a response."""
    with open(f"{os.path.dirname(__file__)}/fixtures/{response_name}.json") as file:
        return json.load(file)
