"""Asynchronous Python client for the Rivian API."""

from __future__ import annotations

import asyncio
import base64
import logging
import socket
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from warnings import warn

import aiohttp
from aiohttp import ClientResponse, ClientWebSocketResponse

from .const import (
    LIVE_SESSION_PROPERTIES,
    VEHICLE_STATE_PROPERTIES,
    VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES,
    VEHICLE_STATES_SUBSCRIPTION_PROPERTIES,
    VehicleCommand,
)
from .exceptions import (
    RivianApiException,
    RivianApiRateLimitError,
    RivianBadRequestError,
    RivianDataError,
    RivianInvalidCredentials,
    RivianInvalidOTP,
    RivianPhoneLimitReachedError,
    RivianTemporarilyLockedError,
    RivianUnauthenticated,
)
from .parallax import PARALLAX_RVMS, ParallaxCommand
from .proto.vehicle_operation import (
    Metadata,
    Operation,
    PhoneInfo,
    VehicleOperationRequest,
)
from .utils import generate_vehicle_command_hmac
from .ws_monitor import WebSocketMonitor

if sys.version_info >= (3, 11):
    import asyncio as async_timeout
    from typing import Self
else:
    import async_timeout
    from typing_extensions import Self


_LOGGER = logging.getLogger(__name__)

GRAPHQL_BASEPATH = "https://rivian.com/api/gql"
GRAPHQL_GATEWAY = GRAPHQL_BASEPATH + "/gateway/graphql"
GRAPHQL_CHARGING = GRAPHQL_BASEPATH + "/chrg/user/graphql"
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"

APOLLO_CLIENT_NAME = "com.rivian.ios.consumer-apollo-ios"

BASE_HEADERS = {
    "User-Agent": "RivianApp/707 CFNetwork/1237 Darwin/20.4.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Apollographql-Client-Name": APOLLO_CLIENT_NAME,
}

CLOUD_CONNECTION_TEMPLATE = "{ lastSync isOnline }"
LOCATION_TEMPLATE = "{ latitude longitude timeStamp isAuthorized }"
LOCATION_ERROR_TEMPLATE = (
    "{ timeStamp positionVertical positionHorizontal speed bearing }"
)
VALUE_TEMPLATE = "{ timeStamp value }"
TEMPLATE_MAP = {
    "cloudConnection": CLOUD_CONNECTION_TEMPLATE,
    "gnssLocation": LOCATION_TEMPLATE,
    "gnssError": LOCATION_ERROR_TEMPLATE,
}

LIVE_SESSION_VALUE_RECORD_KEYS = {
    "current",
    "currentMiles",
    "kilometersChargedPerHour",
    "power",
    "rangeAddedThisSession",
    "soc",
    "timeRemaining",
    "totalChargedEnergy",
    "vehicleChargerState",
}
VALUE_RECORD_TEMPLATE = "{ __typename value updatedAt }"

ERROR_CODE_CLASS_MAP: dict[str, type[RivianApiException]] = {
    "BAD_CURRENT_PASSWORD": RivianInvalidCredentials,
    "BAD_REQUEST_ERROR": RivianBadRequestError,
    "DATA_ERROR": RivianDataError,
    "INTERNAL_SERVER_ERROR": RivianApiException,
    "RATE_LIMIT": RivianApiRateLimitError,
    "SESSION_MANAGER_ERROR": RivianTemporarilyLockedError,
    "UNAUTHENTICATED": RivianUnauthenticated,
}


def send_deprecation_warning(old_name: str, new_name: str) -> None:  # pragma: no cover
    """Send a deprecation warning."""
    message = f"{old_name} has been deprecated in favor of {new_name}, the alias will be removed in the future"
    warn(
        message,
        DeprecationWarning,
        stacklevel=2,
    )
    _LOGGER.warning(message)


class Rivian:
    """Main class for the Rivian API Client"""

    def __init__(
        self,
        request_timeout: int = 10,
        session: aiohttp.client.ClientSession | None = None,
        *,
        access_token: str = "",
        refresh_token: str = "",
        csrf_token: str = "",
        app_session_token: str = "",
        user_session_token: str = "",
    ) -> None:
        self._session = session
        self._close_session = False

        self._access_token = access_token
        self._refresh_token = refresh_token
        self._csrf_token = csrf_token
        self._app_session_token = app_session_token
        self._user_session_token = user_session_token

        self.request_timeout = request_timeout

        self._otp_needed = False
        self._otp_token = ""

        self._ws_monitor: WebSocketMonitor | None = None
        self._subscriptions: dict[str, str] = {}

    async def create_csrf_token(self) -> None:
        """Create cross-site-request-forgery (csrf) token."""
        url = GRAPHQL_GATEWAY

        headers = {**BASE_HEADERS}

        graphql_json = {
            "operationName": "CreateCSRFToken",
            "query": "mutation CreateCSRFToken {\n  createCsrfToken {\n    __typename\n    csrfToken\n    appSessionToken\n  }\n}",
            "variables": None,
        }

        response = await self.__graphql_query(headers, url, graphql_json)

        response_json = await response.json()

        csrf_data = response_json["data"]["createCsrfToken"]
        self._csrf_token = csrf_data["csrfToken"]
        self._app_session_token = csrf_data["appSessionToken"]

    async def authenticate(self, username: str, password: str) -> None:
        """Authenticate against the Rivian GraphQL API with Username and Password"""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "Apollographql-Client-Name": APOLLO_CLIENT_NAME,
        }

        graphql_json = {
            "operationName": "Login",
            "query": "mutation Login($email: String!, $password: String!) {\n  login(email: $email, password: $password) {\n    __typename\n    ... on MobileLoginResponse {\n      __typename\n      accessToken\n      refreshToken\n      userSessionToken\n    }\n    ... on MobileMFALoginResponse {\n      __typename\n      otpToken\n    }\n  }\n}",
            "variables": {"email": username, "password": password},
        }

        response = await self.__graphql_query(headers, url, graphql_json)

        response_json = await response.json()

        login_data = response_json["data"]["login"]

        if "otpToken" in login_data:
            self._otp_needed = True
            self._otp_token = login_data["otpToken"]
        else:
            self._access_token = login_data["accessToken"]
            self._refresh_token = login_data["refreshToken"]
            self._user_session_token = login_data["userSessionToken"]

    async def authenticate_graphql(
        self, username: str, password: str
    ) -> None:  # pragma: no cover
        """### DEPRECATED (use `authenticate` instead)

        Authenticate against the Rivian GraphQL API with Username and Password.
        """
        send_deprecation_warning("authenticate_graphql", "authenticate")
        return await self.authenticate(username=username, password=password)

    async def validate_otp(self, username: str, otp_code: str) -> None:
        """Validates OTP against the Rivian GraphQL API with Username, OTP Code, and OTP Token"""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "Apollographql-Client-Name": APOLLO_CLIENT_NAME,
        }

        graphql_json = {
            "operationName": "LoginWithOTP",
            "query": "mutation LoginWithOTP($email: String!, $otpCode: String!, $otpToken: String!) {\n  loginWithOTP(email: $email, otpCode: $otpCode, otpToken: $otpToken) {\n    __typename\n    ... on MobileLoginResponse {\n      __typename\n      accessToken\n      refreshToken\n      userSessionToken\n    }\n  }\n}",
            "variables": {
                "email": username,
                "otpCode": otp_code,
                "otpToken": self._otp_token,
            },
        }

        response = await self.__graphql_query(headers, url, graphql_json)

        response_json = await response.json()

        login_data = response_json["data"]["loginWithOTP"]

        self._access_token = login_data["accessToken"]
        self._refresh_token = login_data["refreshToken"]
        self._user_session_token = login_data["userSessionToken"]

    async def validate_otp_graphql(
        self, username: str, otpCode: str
    ) -> None:  # pragma: no cover
        """### DEPRECATED (use `validate_otp` instead)

        Validates OTP against the Rivian GraphQL API with Username, OTP Code, and OTP Token.
        """
        send_deprecation_warning("validate_otp_graphql", "validate_otp")
        return await self.validate_otp(username=username, otp_code=otpCode)

    async def disenroll_phone(self, identity_id: str) -> bool:
        """Disenroll a phone."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "DisenrollPhone",
            "variables": {"attrs": {"enrollmentId": identity_id}},
            "query": "mutation DisenrollPhone($attrs: DisenrollPhoneAttributes!) { disenrollPhone(attrs: $attrs) { __typename success } }",
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            return data.get("data", {}).get("disenrollPhone", {}).get("success")
        return False

    async def enroll_phone(
        self,
        user_id: str,
        vehicle_id: str,
        device_type: str,
        device_name: str,
        public_key: str,
    ) -> bool:
        """Enroll a phone.

        To generate a public/private key for enrollment, use the `utils.generate_key_pair` function.
        The private key will need to be retained to sign commands sent via the `send_vehicle_command` method.
        To enable vehicle control, the phone will then also need to be paired locally via BLE,
        which can be done via `ble.pair_phone`.
        """
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "EnrollPhone",
            "variables": {
                "attrs": {
                    "userId": user_id,
                    "vehicleId": vehicle_id,
                    "publicKey": public_key,
                    "type": device_type,
                    "name": device_name,
                }
            },
            "query": "mutation EnrollPhone($attrs: EnrollPhoneAttributes!) { enrollPhone(attrs: $attrs) { __typename success } }",
        }
        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            if data.get("data", {}).get("enrollPhone", {}).get("success"):
                return True
        return False

    async def get_drivers_and_keys(self, vehicle_id: str) -> ClientResponse:
        """Get drivers and keys."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_json = {
            "operationName": "DriversAndKeys",
            "query": "query DriversAndKeys($vehicleId:String){getVehicle(id:$vehicleId){__typename id vin invitedUsers{__typename...on ProvisionedUser{firstName lastName email roles userId devices{type mappedIdentityId id hrid deviceName isPaired isEnabled}}...on UnprovisionedUser{email inviteId status}}}}",
            "variables": {"vehicleId": vehicle_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_user_information(
        self, include_phones: bool = False
    ) -> ClientResponse:
        """Get user information."""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        vehicles_fragment = "vehicles { id vin name vas { __typename vasVehicleId vehiclePublicKey } roles state createdAt updatedAt vehicle { __typename id vin modelYear make model expectedBuildDate plannedBuildDate expectedGeneralAssemblyStartDate actualGeneralAssemblyDate vehicleState { supportedFeatures { __typename name status } } } }"
        phones_fragment = "enrolledPhones { __typename vas { __typename vasPhoneId publicKey } enrolled { __typename deviceType deviceName vehicleId identityId shortName } }"
        _2fa_fragment = "registrationChannels { type }"

        graphql_json = {
            "operationName": "getUserInfo",
            "query": f"query getUserInfo {{ currentUser {{ __typename id {vehicles_fragment} {_2fa_fragment} {phones_fragment if include_phones else ''} }} }}",
            "variables": None,
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_registered_wallboxes(self) -> ClientResponse:
        """Get registered wallboxes."""
        url = GRAPHQL_CHARGING

        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_json = {
            "operationName": "getRegisteredWallboxes",
            "query": "query getRegisteredWallboxes {\n  getRegisteredWallboxes {\n    __typename\n    wallboxId\n    userId\n    wifiId\n    name\n    linked\n    latitude\n    longitude\n    chargingStatus\n    power\n    currentVoltage\n    currentAmps\n    softwareVersion\n    model\n    serialNumber\n    maxAmps\n    maxVoltage\n    maxPower\n  }\n}",
            "variables": None,
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_command_state(self, command_id: str) -> ClientResponse:
        """Get vehicle command state."""
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query getVehicleCommand($id: String!) { getVehicleCommand(id: $id) { __typename id command createdAt state responseCode statusCode } }"

        graphql_json = {
            "operationName": "getVehicleCommand",
            "query": graphql_query,
            "variables": {"id": command_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_images(
        self,
        *,
        extension: str | None = None,
        resolution: str | None = None,
        vehicle_version: str | None = None,
        preorder_version: str | None = None,
    ) -> ClientResponse:
        """Get vehicle images.

        Known parameter values:
          - extension: `png`, `webp`
          - resolution: `@1x`, `@2x`, `@3x` (for png); `hdpi`, `xhdpi`, `xxhdpi`, `xxxhdpi` (for webp)
          - vehicle_version/preorder_version: `1`, `2` (all other values return v1 images)
        """
        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query getVehicleImages( $extension: String $resolution: String $versionForVehicle: String $versionForPreOrder: String ) { getVehicleOrderMobileImages( resolution: $resolution extension: $extension version: $versionForPreOrder ) { ...image } getVehicleMobileImages( resolution: $resolution extension: $extension version: $versionForVehicle ) { ...image } } fragment image on VehicleMobileImage { orderId vehicleId url extension resolution size design placement overlays { url overlay zIndex } }"

        graphql_json = {
            "operationName": "getVehicleImages",
            "query": graphql_query,
            "variables": {
                "extension": extension,
                "resolution": resolution,
                "versionForVehicle": vehicle_version,
                "versionForPreOrder": preorder_version,
            },
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_state(
        self, vin: str, properties: set[str] | None = None
    ) -> ClientResponse:
        """Get vehicle state."""
        if not properties:
            properties = VEHICLE_STATE_PROPERTIES
        elif (
            subscription_properties
            := VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES.intersection(properties)
        ):
            _LOGGER.warning(
                "Subscription only properties have been identified and removed: %s",
                ", ".join(subscription_properties),
            )
            properties.difference_update(subscription_properties)

        url = GRAPHQL_GATEWAY

        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query GetVehicleState($vehicleID: String!) {\n  vehicleState(id: $vehicleID) "
        graphql_query += self._build_vehicle_state_fragment(properties)
        graphql_query += "}"

        graphql_json = {
            "operationName": "GetVehicleState",
            "query": graphql_query,
            "variables": {"vehicleID": vin},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_charging_schedules(self, vehicle_id: str) -> ClientResponse:
        """Get charging schedules for a vehicle."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "getVehicleChargingSchedules",
            "query": "query getVehicleChargingSchedules($vehicleId: String!) {\n  getVehicle(id: $vehicleId) {\n    chargingSchedules {\n      weekDays\n      startTime\n      duration\n      location {\n        latitude\n        longitude\n      }\n      amperage\n      enabled\n    }\n  }\n}",
            "variables": {"vehicleId": vehicle_id},
        }
        return await self.__graphql_query(headers, url, graphql_json)

    async def set_charging_schedules(
        self, vehicle_id: str, schedules: list[dict[str, Any]]
    ) -> ClientResponse:
        """Set charging schedules for a vehicle."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "setChargingSchedules",
            "query": "mutation setChargingSchedules($vehicleId: String!, $chargingSchedules: [InputChargingSchedule!]!) {\n  setChargingSchedules(vehicleId: $vehicleId, chargingSchedules: $chargingSchedules) {\n    __typename\n    success\n  }\n}",
            "variables": {
                "vehicleId": vehicle_id,
                "chargingSchedules": schedules,
            },
        }
        return await self.__graphql_query(headers, url, graphql_json)

    async def get_vehicle_ota_update_details(self, vehicle_id: str) -> ClientResponse:
        """Get vehicle OTA update details."""
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }

        graphql_query = "query getOTAUpdateDetails($vehicleId:String!){getVehicle(id:$vehicleId){availableOTAUpdateDetails{url version locale}currentOTAUpdateDetails{url version locale}}}"

        graphql_json = {
            "operationName": "getOTAUpdateDetails",
            "query": graphql_query,
            "variables": {"vehicleId": vehicle_id},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    async def get_live_charging_session(
        self, vin: str, properties: set[str] | None = None
    ) -> ClientResponse:
        """Get live charging session data."""
        if not properties:
            properties = LIVE_SESSION_PROPERTIES

        url = GRAPHQL_CHARGING
        headers = BASE_HEADERS | {"U-Sess": self._user_session_token}

        fragment = " ".join(
            f"{p} {VALUE_RECORD_TEMPLATE if p in LIVE_SESSION_VALUE_RECORD_KEYS else ''}"
            for p in properties
        )
        graphql_query = f"""
            query getLiveSessionData($vehicleId: ID!) {{
                getLiveSessionData(vehicleId: $vehicleId) {{
                    __typename
                    {fragment}
                }}
            }}"""

        graphql_json = {
            "operationName": "getLiveSessionData",
            "query": graphql_query,
            "variables": {"vehicleId": vin},
        }

        return await self.__graphql_query(headers, url, graphql_json)

    def _validate_vehicle_command(
        self, command: VehicleCommand | str, params: dict[str, Any] | None = None
    ) -> None:
        """Validate certian vehicle command/param combos."""
        if command == VehicleCommand.CHARGING_LIMITS and not (
            params
            and isinstance((limit := params.get("SOC_limit")), int)
            and 50 <= limit <= 100
        ):
            raise RivianBadRequestError(
                "Charging limit must include parameter `SOC_limit` with a valid value between 50 and 100"
            )
        if command in (
            VehicleCommand.CABIN_HVAC_DEFROST_DEFOG,
            VehicleCommand.CABIN_HVAC_LEFT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_LEFT_SEAT_VENT,
            VehicleCommand.CABIN_HVAC_REAR_LEFT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_REAR_RIGHT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_RIGHT_SEAT_HEAT,
            VehicleCommand.CABIN_HVAC_RIGHT_SEAT_VENT,
            VehicleCommand.CABIN_HVAC_STEERING_HEAT,
        ) and not (
            params
            and isinstance((level := params.get("level")), int)
            and 0 <= level <= 4
        ):
            raise RivianBadRequestError(
                "HVAC setting must include parameter `level` with a valid value between 0 and 4"
            )
        if command == VehicleCommand.CABIN_PRECONDITIONING_SET_TEMP:
            if not (
                params
                and isinstance((temp := params.get("HVAC_set_temp")), (float, int))
                and (16 <= temp <= 29 or temp in (0, 63.5))
            ):
                raise RivianBadRequestError(
                    "HVAC setting must include parameter `HVAC_set_temp` with a valid value between 16 and 29 or 0/63.5 for LO/HI, respectively"
                )
            params["HVAC_set_temp"] = str(params["HVAC_set_temp"])

    async def send_vehicle_command(
        self,
        command: VehicleCommand | str,
        vehicle_id: str,
        phone_id: str,
        identity_id: str,
        vehicle_key: str,
        private_key: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> str | None:
        """Send a command to the vehicle.

        To generate a public/private key for commands, use the `utils.generate_key_pair` function.
        The public key will first need to be enrolled via the `enroll_phone` method, otherwise commands will fail.

        Certain commands may require additional details via the `params` mapping.
        Some known examples include:
          - `CABIN_HVAC_*`: params = {"level": 0..4} where 0 is off, 1 is on, 2 is low/level_1, 3 is medium/level_2 and 4 is high/level_3
          - `CABIN_PRECONDITIONING_SET_TEMP`: params = {"HVAC_set_temp": "deg_C"} where `deg_C` is a string value between 16 and 29 or 0/63.5 for LO/HI, respectively
          - `CHARGING_LIMITS`: params = {"SOC_limit": 50..100}
        """
        self._validate_vehicle_command(command, params)

        command = str(command)
        timestamp = str(int(time.time()))
        hmac = generate_vehicle_command_hmac(
            command, timestamp, vehicle_key, private_key
        )

        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "Csrf-Token": self._csrf_token,
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_json = {
            "operationName": "sendVehicleCommand",
            "variables": {
                "attrs": {
                    "command": command,
                    "hmac": hmac,
                    "timestamp": str(timestamp),
                    "vasPhoneId": phone_id,
                    "deviceId": identity_id,
                    "vehicleId": vehicle_id,
                }
                | ({"params": params} if params else {})
            },
            "query": "mutation sendVehicleCommand($attrs: VehicleCommandAttributes!) { sendVehicleCommand(attrs: $attrs) { __typename id command state } }",
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        if response.status == 200:
            data = await response.json()
            if status := data.get("data", {}).get("sendVehicleCommand", {}):
                return status.get("id")
        return None

    async def subscribe_for_vehicle_updates(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        properties: set[str] | None = None,
    ) -> Callable | None:
        """Open a web socket connection to receive updates."""
        if not properties:
            properties = VEHICLE_STATES_SUBSCRIPTION_PROPERTIES

        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            payload = {
                "operationName": "VehicleState",
                "query": f"subscription VehicleState($vehicleID: String!) {{ vehicleState(id: $vehicleID) {self._build_vehicle_state_fragment(properties)} }}",
                "variables": {"vehicleID": vehicle_id},
            }
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug("%s subscribed to updates", vehicle_id)
            return unsubscribe
        except Exception as ex:  # pylint: disable=broad-except # noqa: BLE001
            _LOGGER.error(ex)
            return None

    async def subscribe_for_parallax_messages(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
        rvms: list[str] | None = None,
    ) -> Callable[[], Awaitable[None]] | None:
        """Open a web socket connection to receive Parallax message updates."""
        if not rvms:
            rvms = PARALLAX_RVMS

        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            payload = {
                "operationName": "ParallaxMessages",
                "query": "subscription ParallaxMessages($vehicleId: String!, $rvms: [String!]) { parallaxMessages(vehicleId: $vehicleId, rvms: $rvms) { payload timestamp rvm } }",
                "variables": {
                    "vehicleId": vehicle_id,
                    "rvms": rvms,
                },
            }
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug("%s subscribed to %d Parallax RVMs", vehicle_id, len(rvms))
            return unsubscribe
        except Exception as ex:  # pylint: disable=broad-except # noqa: BLE001
            _LOGGER.error(ex)
            return None

    async def _ws_connect(self) -> ClientWebSocketResponse[bool]:
        """Initiate a websocket connection."""

        async def connection_init(websocket: ClientWebSocketResponse[bool]) -> None:
            await websocket.send_json(
                {
                    "payload": {
                        "client-name": APOLLO_CLIENT_NAME,
                        "client-version": "1.13.0-1494",
                        "dc-cid": f"m-ios-{uuid.uuid4()}",
                        "u-sess": self._user_session_token,
                    },
                    "type": "connection_init",
                }
            )

        if not self._ws_monitor:
            self._ws_monitor = WebSocketMonitor(
                self, GRAPHQL_WEBSOCKET, connection_init
            )
        ws_monitor = self._ws_monitor
        if ws_monitor.websocket is None or ws_monitor.websocket.closed:
            await ws_monitor.new_connection(True)
            assert ws_monitor.websocket
        if ws_monitor.monitor is None or ws_monitor.monitor.done():
            await ws_monitor.start_monitor()
        return ws_monitor.websocket

    async def __graphql_query(
        self, headers: dict[str, str], url: str, body: dict[str, Any]
    ) -> ClientResponse:
        """Execute and return arbitrary graphql query."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True

        if "dc-cid" not in headers:
            headers["dc-cid"] = f"m-ios-{uuid.uuid4()}"

        try:
            async with async_timeout.timeout(self.request_timeout):
                response = await self._session.request(
                    "POST",
                    url,
                    json=body,
                    headers=headers,
                )
        except asyncio.TimeoutError as exception:
            raise RivianApiException(
                "Timeout occurred while connecting to Rivian API."
            ) from exception
        except (aiohttp.ClientError, socket.gaierror) as exception:
            raise RivianApiException(
                "Error occurred while communicating with Rivian."
            ) from exception

        response_json = await response.json()
        if errors := response_json.get("errors"):
            for error in errors:
                if extensions := error.get("extensions"):
                    code = extensions["code"]
                    if (code, extensions.get("reason")) in (
                        ("BAD_USER_INPUT", "INVALID_OTP"),
                        ("UNAUTHENTICATED", "OTP_TOKEN_EXPIRED"),
                    ):
                        raise RivianInvalidOTP(
                            response.status, response_json, headers, body
                        )
                    if (code, extensions.get("reason")) == (
                        "CONFLICT",
                        "ENROLL_PHONE_LIMIT_REACHED",
                    ):
                        raise RivianPhoneLimitReachedError(
                            response.status, response_json, headers, body
                        )
                    if err_cls := ERROR_CODE_CLASS_MAP.get(code):
                        raise err_cls(response.status, response_json, headers, body)
            raise RivianApiException(
                "Error occurred while reading the graphql response from Rivian.",
                response.status,
                response_json,
                headers,
                body,
            )

        return response

    # ------------------------------------------------------------------
    # Parallax write path and subscriptions carried over from this fork.
    #
    # Upstream 2.1.0 is Parallax read-only: it decodes telemetry but has no way
    # to send an operation, and it lacks the charging/cloud/command-state
    # subscriptions and the navigation share. Everything below is the half
    # upstream does not have, ported onto its plain-string transport.
    #
    # The gql DSL is gone. Of the 13 methods carried over, 11 never touched it
    # (the subscriptions already spoke raw aiohttp, and the Parallax setters just
    # delegate to send_parallax_command); only send_vehicle_operation and
    # send_location_to_vehicle were DSL and are rewritten as plain queries here.
    # ------------------------------------------------------------------

    async def send_vehicle_operation(
        self,
        vehicle_id: str,
        rvm_type: str,
        payload: bytes,
        phone_id: bytes,
        request_id: str | None = None,
    ) -> dict:
        """Send a vehicle operation via sendVehicleOperation mutation.

        This is the newer mutation used by the iOS app for climate hold and other
        RVM (Remote Vehicle Module) operations. It requires phone enrollment.

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            rvm_type: RVM type string (e.g., "comfort.cabin.climate_hold_setting")
            payload: Serialized protobuf payload for the operation
            phone_id: 16-byte phone identifier from enrollment (UUID bytes)
            request_id: Optional request UUID (generated if not provided)
            operation_type: Operation type (1 = SET/write, 0 = GET/read)

        Returns:
            dict with 'success' (bool) key

        Raises:
            RivianApiException: For network or API errors
            RivianUnauthenticated: If authentication is invalid

        Example:
            >>> from rivian.proto.rivian_climate_pb2 import ClimateHoldSetting
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_str = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> import uuid
            >>> phone_id = uuid.UUID(phone_id_str).bytes
            >>> # Build payload
            >>> setting = ClimateHoldSetting(hold_time_duration_seconds=7200)  # 2 hours
            >>> payload = setting.SerializeToString()
            >>> # Send operation
            >>> result = await client.send_vehicle_operation(
            ...     vehicle_id="01-276948064",
            ...     rvm_type="comfort.cabin.climate_hold_setting",
            ...     payload=payload,
            ...     phone_id=phone_id
            ... )
            >>> print(f"Success: {result['success']}")
        """
        # Determine operation type based on payload - empty payload = GET, otherwise SET
        op_type = 0 if not payload else 1

        # Build VehicleOperationRequest
        phone_info = PhoneInfo(version=1, phone_id=phone_id)
        metadata = Metadata(
            phone_info=phone_info,
            request_id=request_id or str(uuid.uuid4()),
        )
        operation = Operation(
            rvm_type=rvm_type,
            operation_type=op_type,  # 0 = GET, 1 = SET
            payload=payload,
        )
        request = VehicleOperationRequest(metadata=metadata, operation=operation)
        request_b64 = base64.b64encode(request.SerializeToString()).decode("utf-8")

        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_query = (
            "mutation SendVehicleOperation($vehicleId:String!,$payload:String!){"
            "sendVehicleOperation(vehicleId:$vehicleId,payload:$payload){"
            "__typename ... on SendVehicleOperationSuccess{success}}}"
        )
        graphql_json = {
            "operationName": "SendVehicleOperation",
            "query": graphql_query,
            "variables": {"vehicleId": vehicle_id, "payload": request_b64},
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        data = await response.json()
        return data.get("data", {}).get("sendVehicleOperation", {}) or {}

    async def send_parallax_command(
        self,
        vehicle_id: str,
        parallax_cmd: ParallaxCommand,
        phone_id: bytes,
    ) -> dict:
        """Send a Parallax command to a vehicle via sendVehicleOperation.

        Parallax commands use the sendVehicleOperation mutation which wraps
        the protobuf payload with phone enrollment info. This requires
        Bluetooth pairing to have been completed.

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            parallax_cmd: ParallaxCommand instance with RVM type and payload
            phone_id: 32-byte phone identifier from enrollment

        Returns:
            dict with 'success' (bool) key

        Raises:
            RivianApiException: For network or API errors
            RivianUnauthenticated: If authentication is invalid

        Example:
            >>> from rivian.parallax import build_climate_hold_command
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> phone_id = bytes.fromhex(phone_id_hex)
            >>> # Send command
            >>> cmd = build_climate_hold_command(duration_minutes=120)
            >>> result = await client.send_parallax_command("01-276948064", cmd, phone_id)
            >>> print(f"Success: {result['success']}")
        """
        import base64

        # Decode the base64 payload from ParallaxCommand
        payload = (
            base64.b64decode(parallax_cmd.payload_b64)
            if parallax_cmd.payload_b64
            else b""
        )

        # Use sendVehicleOperation which wraps payload with phone info
        return await self.send_vehicle_operation(
            vehicle_id=vehicle_id,
            rvm_type=str(parallax_cmd.rvm),
            payload=payload,
            phone_id=phone_id,
        )

    async def set_climate_hold(
        self,
        vehicle_id: str,
        phone_id: bytes,
        enabled: bool = True,
        temp_celsius: float = 22.0,
        duration_minutes: int = 120,
    ) -> dict:
        """Set climate hold via sendVehicleOperation.

        RVM: comfort.cabin.climate_hold_setting

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            enabled: Whether to enable climate hold (kept for API compatibility,
                    but not sent in protobuf - may be controlled elsewhere)
            temp_celsius: Target temperature in Celsius (kept for API compatibility,
                         but not sent in protobuf - may be controlled elsewhere)
            duration_minutes: Hold duration in minutes (sent in protobuf)

        Returns:
            dict with success status

        Note:
            Based on APK analysis, the ClimateHoldSetting protobuf only contains
            hold_time_duration_seconds. The enabled state and target temperature
            may be controlled via separate GraphQL mutations or vehicle commands.

        Example:
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> phone_id = bytes.fromhex(phone_id_hex)
            >>> # Set climate hold for 8 hours
            >>> result = await client.set_climate_hold(
            ...     vehicle_id="01-276948064",
            ...     phone_id=phone_id,
            ...     duration_minutes=480,
            ... )
            >>> print(f"Success: {result['success']}")
        """
        # Note: Temperature validation kept for API compatibility, but temp
        # is not actually sent in the protobuf based on APK analysis
        if not 16.0 <= temp_celsius <= 29.0:
            raise RivianBadRequestError("Temperature must be between 16°C and 29°C")

        from .parallax import build_climate_hold_command

        cmd = build_climate_hold_command(duration_minutes=duration_minutes)
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def set_charging_schedule(
        self,
        vehicle_id: str,
        phone_id: bytes,
        start_hour: int,
        start_minute: int,
        end_hour: int,
        end_minute: int,
        start_day: int = 0,
        end_day: int = 6,
    ) -> dict:
        """Set charging schedule time window via Parallax protocol.

        RVM: charging.schedule.time_window

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            start_hour: Start hour (0-23)
            start_minute: Start minute (0-59)
            end_hour: End hour (0-23)
            end_minute: End minute (0-59)
            start_day: Start day of week (0=Sunday, 6=Saturday)
            end_day: End day of week (0=Sunday, 6=Saturday)

        Returns:
            dict with success status

        Example:
            >>> # Charge only between 10 PM and 6 AM
            >>> result = await client.set_charging_schedule("01-276948064", phone_id, 22, 0, 6, 0)
            >>> print(f"Success: {result['success']}")
        """
        # Validate time ranges
        if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
            raise RivianBadRequestError("Hours must be between 0 and 23")
        if not (0 <= start_minute <= 59 and 0 <= end_minute <= 59):
            raise RivianBadRequestError("Minutes must be between 0 and 59")
        if not (0 <= start_day <= 6 and 0 <= end_day <= 6):
            raise RivianBadRequestError(
                "Days must be between 0 (Sunday) and 6 (Saturday)"
            )

        from .parallax import build_charging_schedule_command

        cmd = build_charging_schedule_command(
            start_hour, start_minute, end_hour, end_minute, start_day, end_day
        )
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def set_cabin_ventilation(
        self,
        vehicle_id: str,
        phone_id: bytes,
        enabled: bool,
        mode: str = "AUTO",
        windows_open_percent: int = 0,
        sunroof_open_percent: int = 0,
        duration_minutes: int = 30,
    ) -> dict:
        """Set cabin ventilation via Parallax protocol.

        RVM: comfort.cabin.cabin_ventilation_setting

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            enabled: Whether to enable ventilation
            mode: Ventilation mode ("AUTO", "MANUAL", "OFF")
            windows_open_percent: Window opening percentage (0-100)
            sunroof_open_percent: Sunroof opening percentage (0-100)
            duration_minutes: Duration in minutes

        Returns:
            dict with success status

        Raises:
            RivianBadRequestError: If parameters are invalid

        Example:
            >>> # Open windows 50% and sunroof 100% for 30 minutes
            >>> result = await client.set_cabin_ventilation("01-276948064", phone_id, True, "MANUAL", 50, 100, 30)
            >>> print(f"Success: {result['success']}")
        """
        # Validate parameters
        if mode not in ["AUTO", "MANUAL", "OFF"]:
            raise RivianBadRequestError("Mode must be AUTO, MANUAL, or OFF")
        if not 0 <= windows_open_percent <= 100:
            raise RivianBadRequestError(
                "Windows open percent must be between 0 and 100"
            )
        if not 0 <= sunroof_open_percent <= 100:
            raise RivianBadRequestError(
                "Sunroof open percent must be between 0 and 100"
            )

        from .parallax import build_ventilation_command

        cmd = build_ventilation_command(
            enabled, mode, windows_open_percent, sunroof_open_percent, duration_minutes
        )
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def set_halloween_settings(
        self,
        vehicle_id: str,
        phone_id: bytes,
        enabled: bool,
        animation_mode: str = "SPOOKY",
        brightness: int = 100,
        repeat_count: int = 1,
        schedule_enabled: bool = False,
        schedule_time: str = "",
    ) -> dict:
        """Set Halloween light show settings via Parallax protocol.

        RVM: holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            enabled: Whether to enable Halloween light show
            animation_mode: Animation mode ("SPOOKY", "FESTIVE", "OFF")
            brightness: Brightness level (0-100)
            repeat_count: Number of times to repeat animation
            schedule_enabled: Whether to enable scheduled activation
            schedule_time: Schedule time in "HH:MM" format

        Returns:
            dict with success status

        Raises:
            RivianBadRequestError: If parameters are invalid

        Example:
            >>> # Enable spooky animation at 50% brightness, repeat 3 times
            >>> result = await client.set_halloween_settings("01-276948064", phone_id, True, "SPOOKY", 50, 3)
            >>> print(f"Success: {result['success']}")
        """
        # Validate parameters
        if animation_mode not in ["SPOOKY", "FESTIVE", "OFF"]:
            raise RivianBadRequestError(
                "Animation mode must be SPOOKY, FESTIVE, or OFF"
            )
        if not 0 <= brightness <= 100:
            raise RivianBadRequestError("Brightness must be between 0 and 100")

        from .parallax import build_halloween_command

        cmd = build_halloween_command(
            light_show_enabled=enabled,
            motion_light_sound_enabled=enabled,
            costume_theme=animation_mode if animation_mode != "OFF" else "",
        )
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def set_vehicle_geofences(
        self, vehicle_id: str, phone_id: bytes, fences: list[dict]
    ) -> dict:
        """Set vehicle geofences via Parallax protocol.

        RVM: location.geofence.vehicle_geo_fences

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            fences: List of geofence definitions, each with:
                - fence_id: Unique identifier (required)
                - name: Human-readable name (required)
                - latitude: Center latitude -90 to 90 (required)
                - longitude: Center longitude -180 to 180 (required)
                - radius_meters: Radius in meters (required)
                - enabled: Whether active (default: True)

        Returns:
            dict with success status

        Raises:
            RivianBadRequestError: If fence parameters are invalid

        Example:
            >>> fences = [
            ...     {
            ...         "fence_id": "home",
            ...         "name": "Home",
            ...         "latitude": 37.7749,
            ...         "longitude": -122.4194,
            ...         "radius_meters": 500.0,
            ...         "enabled": True,
            ...     }
            ... ]
            >>> result = await client.set_vehicle_geofences("01-276948064", phone_id, fences)
            >>> print(f"Success: {result['success']}")
        """
        # Validate fences
        if not fences or not isinstance(fences, list):
            raise RivianBadRequestError("Fences must be a non-empty list")

        for fence in fences:
            if not isinstance(fence, dict):
                raise RivianBadRequestError("Each fence must be a dictionary")

            # Validate required fields
            if not fence.get("fence_id"):
                raise RivianBadRequestError("Each fence must have a fence_id")
            if not fence.get("name"):
                raise RivianBadRequestError("Each fence must have a name")

            # Validate coordinates
            lat = fence.get("latitude")
            lon = fence.get("longitude")
            if lat is None or lon is None:
                raise RivianBadRequestError(
                    "Each fence must have latitude and longitude"
                )

            self._validate_coordinates(lat, lon)

            # Validate radius
            radius = fence.get("radius_meters")
            if radius is None or not isinstance(radius, (int, float)) or radius <= 0:
                raise RivianBadRequestError(
                    "Each fence must have a positive radius_meters"
                )

        from .parallax import build_geofences_command

        cmd = build_geofences_command(fences)
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def set_gear_guard_consents(
        self,
        vehicle_id: str,
        phone_id: bytes,
        video_enabled: bool,
        audio_enabled: bool,
        cloud_storage_enabled: bool,
        local_storage_enabled: bool,
        consent_timestamp: str = "",
    ) -> dict:
        """Set GearGuard consent settings via Parallax protocol.

        RVM: security.gear_guard.consents

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            video_enabled: Whether video recording is enabled
            audio_enabled: Whether audio recording is enabled
            cloud_storage_enabled: Whether cloud storage is enabled
            local_storage_enabled: Whether local storage is enabled
            consent_timestamp: ISO timestamp of consent (optional)

        Returns:
            dict with success status

        Example:
            >>> result = await client.set_gear_guard_consents(
            ...     "01-276948064",
            ...     phone_id,
            ...     video_enabled=True,
            ...     audio_enabled=False,
            ...     cloud_storage_enabled=True,
            ...     local_storage_enabled=True,
            ... )
            >>> print(f"Success: {result['success']}")
        """
        from .parallax import build_gear_guard_consents_command

        # build_gear_guard_consents_command only accepts consent_status
        # If all are enabled, use CONSENTED; otherwise NOT_CONSENTED
        all_enabled = (
            video_enabled
            and audio_enabled
            and cloud_storage_enabled
            and local_storage_enabled
        )
        consent_status = "CONSENTED" if all_enabled else "NOT_CONSENTED"
        cmd = build_gear_guard_consents_command(consent_status=consent_status)
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def set_passive_entry_settings(
        self,
        vehicle_id: str,
        phone_id: bytes,
        enabled: bool,
        unlock_on_approach: bool = True,
        lock_on_walk_away: bool = True,
        approach_distance_meters: float = 3.0,
    ) -> dict:
        """Set passive entry settings via Parallax protocol.

        RVM: access.passive_entry.setting

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX")
            phone_id: 32-byte phone identifier from enrollment
            enabled: Whether passive entry is enabled
            unlock_on_approach: Whether to unlock when phone approaches (default: True)
            lock_on_walk_away: Whether to lock when phone walks away (default: True)
            approach_distance_meters: Distance threshold for approach in meters (default: 3.0)

        Returns:
            dict with success status

        Raises:
            RivianBadRequestError: If approach_distance_meters is invalid

        Example:
            >>> result = await client.set_passive_entry_settings(
            ...     "01-276948064",
            ...     phone_id,
            ...     enabled=True,
            ...     unlock_on_approach=True,
            ...     lock_on_walk_away=True,
            ...     approach_distance_meters=3.0,
            ... )
            >>> print(f"Success: {result['success']}")
        """
        # Validate approach distance
        if (
            not isinstance(approach_distance_meters, (int, float))
            or approach_distance_meters < 0
        ):
            raise RivianBadRequestError(
                "approach_distance_meters must be a non-negative number"
            )

        from .parallax import build_passive_entry_command

        # build_passive_entry_command only accepts duration_seconds
        # If enabled, use a long duration; if disabled, use 0
        duration_seconds = 3600 if enabled else 0
        cmd = build_passive_entry_command(duration_seconds=duration_seconds)
        return await self.send_parallax_command(vehicle_id, cmd, phone_id)

    async def subscribe_for_charging_session(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Open a web socket connection to receive real-time charging session updates.

        Args:
            vehicle_id: The vehicle ID to subscribe to
            callback: Function called when subscription data is received

        Returns:
            Unsubscribe function or None if connection fails
        """
        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            payload = {
                "operationName": "ChargingSession",
                "query": "subscription ChargingSession($vehicleID: String!) { chargingSession(vehicleId: $vehicleID) { chartData { soc powerKW startTime endTime timeEstimationValidityStatus vehicleChargerState } liveData { powerKW kilometersChargedPerHour rangeAddedThisSession totalChargedEnergy timeElapsed timeRemaining price currency isFreeSession vehicleChargerState startTime } } }",
                "variables": {"vehicleID": vehicle_id},
            }
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug(
                "Vehicle %s subscribed to charging session updates", vehicle_id
            )
            return unsubscribe
        except Exception as ex:  # noqa: BLE001  # pylint: disable=broad-except
            # Deliberately broad, and deliberately unchanged here. Narrowing this
            # is a behavioural change -- auth and transport errors should reach the
            # coordinator instead of becoming a silent None -- and it is scoped to
            # the client-cleanup story alongside the same fix in
            # subscribe_for_parallax_messages. Not a drive-by edit inside a merge.
            _LOGGER.error(ex)
            return None

    async def subscribe_for_cloud_connection(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Open a web socket connection to receive vehicle cloud connectivity updates.

        Args:
            vehicle_id: The vehicle ID to subscribe to
            callback: Function called when subscription data is received

        Returns:
            Unsubscribe function or None if connection fails
        """
        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            payload = {
                "operationName": "VehicleCloudConnection",
                "query": "subscription VehicleCloudConnection($vehicleID: String!) { vehicleCloudConnection(id: $vehicleID) { isOnline lastSync } }",
                "variables": {"vehicleID": vehicle_id},
            }
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug(
                "Vehicle %s subscribed to cloud connection updates", vehicle_id
            )
            return unsubscribe
        except Exception as ex:  # noqa: BLE001  # pylint: disable=broad-except
            # Deliberately broad, and deliberately unchanged here. Narrowing this
            # is a behavioural change -- auth and transport errors should reach the
            # coordinator instead of becoming a silent None -- and it is scoped to
            # the client-cleanup story alongside the same fix in
            # subscribe_for_parallax_messages. Not a drive-by edit inside a merge.
            _LOGGER.error(ex)
            return None

    async def subscribe_for_command_state(
        self,
        command_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Open a web socket connection to receive real-time vehicle command state updates.

        Args:
            command_id: The command ID to subscribe to
            callback: Function called when subscription data is received

        Returns:
            Unsubscribe function or None if connection fails
        """
        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            payload = {
                "operationName": "VehicleCommandState",
                "query": "subscription VehicleCommandState($id: String!) { vehicleCommandState(id: $id) { __typename id command createdAt state responseCode statusCode } }",
                "variables": {"id": command_id},
            }
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug("Command %s subscribed to state updates", command_id)
            return unsubscribe
        except Exception as ex:  # noqa: BLE001  # pylint: disable=broad-except
            # Deliberately broad, and deliberately unchanged here. Narrowing this
            # is a behavioural change -- auth and transport errors should reach the
            # coordinator instead of becoming a silent None -- and it is scoped to
            # the client-cleanup story alongside the same fix in
            # subscribe_for_parallax_messages. Not a drive-by edit inside a merge.
            _LOGGER.error(ex)
            return None

    async def send_location_to_vehicle(
        self,
        location_str: str,
        vehicle_id: str,
    ) -> dict[str, Any]:
        """Send a location or address to the vehicle's navigation system.

        Requires neither phone enrollment nor HMAC signing -- it is cloud-only and
        fire-and-forget. Success means Rivian's cloud accepted the message, not
        that the vehicle received it; the vehicle picks the destination up when it
        next connects.

        Args:
            location_str: Address ("123 Main St, Springfield, IL") or
                "latitude,longitude" ("40.7128,-74.0060").
            vehicle_id: Vehicle to send the location to.

        Returns:
            The parseAndShareLocationToVehicle payload; publishResponse.result is
            0 on success.
        """
        url = GRAPHQL_GATEWAY
        headers = BASE_HEADERS | {
            "A-Sess": self._app_session_token,
            "U-Sess": self._user_session_token,
        }
        graphql_query = (
            "mutation parseAndShareLocationToVehicle($str:String!,$vehicleId:String!){"
            "parseAndShareLocationToVehicle(str:$str,vehicleId:$vehicleId){"
            "publishResponse{result}}}"
        )
        graphql_json = {
            "operationName": "parseAndShareLocationToVehicle",
            "query": graphql_query,
            "variables": {"str": location_str, "vehicleId": vehicle_id},
        }

        response = await self.__graphql_query(headers, url, graphql_json)
        data = await response.json()
        return data.get("data", {}).get("parseAndShareLocationToVehicle", {}) or {}

    async def close(self) -> None:
        """Close open client session."""
        if self._ws_monitor:
            await self._ws_monitor.close()
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> Self:
        """Async enter.
        Returns:
            The Rivian object.
        """
        return self

    async def __aexit__(self, *_exc_info) -> None:
        """Async exit.
        Args:
            _exc_info: Exec type.
        """
        await self.close()

    def _build_vehicle_state_fragment(self, properties: set[str]) -> str:
        """Build GraphQL vehicle state fragment from properties."""
        frag = " ".join(
            f"{p} {TEMPLATE_MAP.get(p, VALUE_TEMPLATE)}" for p in properties
        )
        return f"{{ {frag} }}"
