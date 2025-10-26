"""Asynchronous Python client for the Rivian API."""

from __future__ import annotations

import asyncio
import logging
import socket
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any, Type, TypedDict
from warnings import warn

import aiohttp
from aiohttp import ClientResponse, ClientWebSocketResponse
from gql import Client
from gql.dsl import DSLMutation, DSLSchema, dsl_gql, DSLInlineFragment
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError
from graphql import build_schema

from .const import (
    LIVE_SESSION_PROPERTIES,
    VEHICLE_STATE_PROPERTIES,
    VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES,
    VEHICLE_STATES_SUBSCRIPTION_PROPERTIES,
    VehicleCommand,
)
from .schema import RIVIAN_SCHEMA
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
from .utils import generate_vehicle_command_hmac
from .ws_monitor import WebSocketMonitor

if sys.version_info >= (3, 11):
    import asyncio as async_timeout
else:
    import async_timeout

_LOGGER = logging.getLogger(__name__)

GRAPHQL_BASEPATH = "https://rivian.com/api/gql"
GRAPHQL_GATEWAY = GRAPHQL_BASEPATH + "/gateway/graphql"
GRAPHQL_CHARGING = GRAPHQL_BASEPATH + "/chrg/user/graphql"
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"

APOLLO_CLIENT_NAME = "com.rivian.android.consumer"
APOLLO_CLIENT_VERSION = "3.6.0-3989"

BASE_HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "apollographql-client-name": APOLLO_CLIENT_NAME,
    "apollographql-client-version": APOLLO_CLIENT_VERSION,
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

ERROR_CODE_CLASS_MAP: dict[str, Type[RivianApiException]] = {
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


class PublishResponse(TypedDict):
    """Response from a publish operation.

    The result field is an integer where 0 indicates success.
    """

    result: int  # 0 = success


class ParseAndShareLocationResponse(TypedDict):
    """Response from parseAndShareLocationToVehicle mutation."""

    publishResponse: PublishResponse


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

        # Token expiration tracking (timestamp when tokens were last refreshed)
        self._token_refreshed_at = time.time() if access_token else 0
        self._csrf_refreshed_at = time.time() if csrf_token else 0

        self.request_timeout = request_timeout

        self._otp_needed = False
        self._otp_token = ""

        self._ws_monitor: WebSocketMonitor | None = None
        self._subscriptions: dict[str, str] = {}

        # GQL client infrastructure (initialized lazily on first use)
        self._gql_client: Client | None = None
        self._gql_transport: AIOHTTPTransport | None = None
        self._ds: DSLSchema | None = None

    async def _ensure_client(self, url: str = GRAPHQL_GATEWAY) -> Client:
        """Ensure gql client is initialized and return it.

        Creates the client on first call with schema introspection.
        Updates headers on subsequent calls to reflect current auth state.
        """
        # Build current headers based on auth state
        # NOTE: Following the official Android app (com.rivian.android.consumer),
        # we do NOT send Authorization: Bearer tokens. The Android app uses only
        # session tokens (U-Sess) for authentication. Session tokens remain valid
        # much longer than access tokens and prevent authorization loss.
        headers = {**BASE_HEADERS, "dc-cid": f"m-android-{uuid.uuid4()}"}
        if self._csrf_token:
            headers["Csrf-Token"] = self._csrf_token
        if self._app_session_token:
            headers["A-Sess"] = self._app_session_token
        if self._user_session_token:
            headers["U-Sess"] = self._user_session_token

        # Initialize client on first use
        if self._gql_client is None:
            # Create session if needed (for non-gql methods)
            if self._session is None:
                self._session = aiohttp.ClientSession()
                self._close_session = True

            # AIOHTTPTransport will create its own session when connect() is called
            # Note: We use a static schema definition instead of introspection
            # to make testing easier and avoid extra network calls
            self._gql_transport = AIOHTTPTransport(
                url=url,
                headers=headers,
            )

            # Build schema from our schema definition
            schema = build_schema(RIVIAN_SCHEMA)

            self._gql_client = Client(
                transport=self._gql_transport,
                fetch_schema_from_transport=False,  # Use our static schema instead
                execute_timeout=self.request_timeout,
                schema=schema,
            )

            # Build DSL schema for method usage
            self._ds = DSLSchema(schema)
        else:
            # Update headers on existing transport
            if self._gql_transport:
                self._gql_transport.headers = headers

        return self._gql_client

    def _handle_gql_error(self, exception: TransportQueryError) -> None:
        """Handle GQL transport errors and convert to Rivian exceptions.

        Args:
            exception: The TransportQueryError from gql

        Raises:
            Appropriate RivianApiException subclass based on error code
        """
        errors = exception.errors if hasattr(exception, "errors") else []

        for error in errors or []:
            if isinstance(error, dict) and (extensions := error.get("extensions")):
                code = extensions.get("code")
                reason = extensions.get("reason")

                # Check for specific error combinations
                if (code, reason) in (
                    ("BAD_USER_INPUT", "INVALID_OTP"),
                    ("UNAUTHENTICATED", "OTP_TOKEN_EXPIRED"),
                ):
                    raise RivianInvalidOTP(str(exception))

                if (code, reason) == ("CONFLICT", "ENROLL_PHONE_LIMIT_REACHED"):
                    raise RivianPhoneLimitReachedError(str(exception))

                # Check for generic error codes
                if code and (err_cls := ERROR_CODE_CLASS_MAP.get(code)):
                    raise err_cls(str(exception))

        # If no specific error found, raise generic exception
        raise RivianApiException(
            f"Error occurred while communicating with Rivian: {exception}"
        )

    async def _execute_async(
        self, client: Client, query, operation_name: str = "operation"
    ):
        """Execute a GraphQL query asynchronously.

        Args:
            client: The GQL client to use
            query: The DSL query to execute
            operation_name: Name of the operation for logging

        Returns:
            The query result

        Raises:
            Various RivianApiException subclasses based on error type
        """
        try:
            async with async_timeout.timeout(self.request_timeout):
                result = await client.execute_async(query)
            return result

        except TransportQueryError as exception:
            self._handle_gql_error(exception)

        except asyncio.TimeoutError as exception:
            raise RivianApiException(
                f"Timeout occurred while executing {operation_name}."
            ) from exception
        except Exception as exception:
            raise RivianApiException(
                f"Error occurred during {operation_name}."
            ) from exception

    async def create_csrf_token(self) -> None:
        """Create cross-site-request-forgery (csrf) token."""
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        query = dsl_gql(
            DSLMutation(
                self._ds.Mutation.createCsrfToken.select(
                    self._ds.CreateCSRFTokenResponse.csrfToken,
                    self._ds.CreateCSRFTokenResponse.appSessionToken,
                )
            )
        )

        # Execute query with error handling
        try:
            async with async_timeout.timeout(self.request_timeout):
                result = await client.execute_async(query)
        except TransportQueryError as exception:
            self._handle_gql_error(exception)
        except asyncio.TimeoutError as exception:
            raise RivianApiException(
                "Timeout occurred while connecting to Rivian API."
            ) from exception
        except Exception as exception:
            raise RivianApiException(
                "Error occurred while communicating with Rivian."
            ) from exception

        # Parse response
        csrf_data = result["createCsrfToken"]
        self._csrf_token = csrf_data["csrfToken"]
        self._app_session_token = csrf_data["appSessionToken"]
        self._csrf_refreshed_at = time.time()

    async def authenticate(self, username: str, password: str) -> None:
        """Authenticate against the Rivian GraphQL API with Username and Password"""
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation with union type fragments
        query = dsl_gql(
            DSLMutation(
                self._ds.Mutation.login.args(email=username, password=password).select(
                    DSLInlineFragment()
                    .on(self._ds.MobileLoginResponse)
                    .select(
                        self._ds.MobileLoginResponse.accessToken,
                        self._ds.MobileLoginResponse.refreshToken,
                        self._ds.MobileLoginResponse.userSessionToken,
                    ),
                    DSLInlineFragment()
                    .on(self._ds.MobileMFALoginResponse)
                    .select(
                        self._ds.MobileMFALoginResponse.otpToken,
                    ),
                )
            )
        )

        # Execute query with error handling
        try:
            async with async_timeout.timeout(self.request_timeout):
                result = await client.execute_async(query)
        except TransportQueryError as exception:
            self._handle_gql_error(exception)
        except asyncio.TimeoutError as exception:
            raise RivianApiException(
                "Timeout occurred while connecting to Rivian API."
            ) from exception
        except Exception as exception:
            raise RivianApiException(
                "Error occurred while communicating with Rivian."
            ) from exception

        # Parse response
        login_data = result["login"]

        if "otpToken" in login_data:
            self._otp_needed = True
            self._otp_token = login_data["otpToken"]
        else:
            self._access_token = login_data["accessToken"]
            self._refresh_token = login_data["refreshToken"]
            self._user_session_token = login_data["userSessionToken"]
            self._token_refreshed_at = time.time()

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
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        query = dsl_gql(
            DSLMutation(
                self._ds.Mutation.loginWithOTP.args(
                    email=username, otpCode=otp_code, otpToken=self._otp_token
                ).select(
                    DSLInlineFragment()
                    .on(self._ds.MobileLoginResponse)
                    .select(
                        self._ds.MobileLoginResponse.accessToken,
                        self._ds.MobileLoginResponse.refreshToken,
                        self._ds.MobileLoginResponse.userSessionToken,
                    ),
                )
            )
        )

        # Execute query with error handling
        try:
            async with async_timeout.timeout(self.request_timeout):
                result = await client.execute_async(query)
        except TransportQueryError as exception:
            self._handle_gql_error(exception)
        except asyncio.TimeoutError as exception:
            raise RivianApiException(
                "Timeout occurred while connecting to Rivian API."
            ) from exception
        except Exception as exception:
            raise RivianApiException(
                "Error occurred while communicating with Rivian."
            ) from exception

        # Parse response
        login_data = result["loginWithOTP"]

        self._access_token = login_data["accessToken"]
        self._refresh_token = login_data["refreshToken"]
        self._user_session_token = login_data["userSessionToken"]
        self._token_refreshed_at = time.time()

    async def validate_otp_graphql(
        self, username: str, otpCode: str
    ) -> None:  # pragma: no cover
        """### DEPRECATED (use `validate_otp` instead)

        Validates OTP against the Rivian GraphQL API with Username, OTP Code, and OTP Token.
        """
        send_deprecation_warning("validate_otp_graphql", "validate_otp")
        return await self.validate_otp(username=username, otp_code=otpCode)

    async def refresh_csrf_token(self) -> None:
        """Refresh CSRF and app session tokens.

        This should be called periodically (e.g., every 2-4 hours) to maintain
        session validity. The Android app calls this to keep sessions alive.

        This is a lighter-weight refresh than refresh_access_token and can be
        done more frequently.
        """
        await self.create_csrf_token()
        _LOGGER.debug("CSRF and app session tokens refreshed successfully")

    def needs_token_refresh(self, max_age_seconds: int = 3600) -> bool:
        """Check if access token needs refresh based on age.

        Args:
            max_age_seconds: Maximum token age before refresh (default: 1 hour)

        Returns:
            True if token is older than max_age_seconds or if no token exists
        """
        if not self._access_token or not self._token_refreshed_at:
            return True
        age = time.time() - self._token_refreshed_at
        return age >= max_age_seconds

    def needs_csrf_refresh(self, max_age_seconds: int = 7200) -> bool:
        """Check if CSRF token needs refresh based on age.

        Args:
            max_age_seconds: Maximum CSRF age before refresh (default: 2 hours)

        Returns:
            True if CSRF is older than max_age_seconds or if no CSRF exists
        """
        if not self._csrf_token or not self._csrf_refreshed_at:
            return True
        age = time.time() - self._csrf_refreshed_at
        return age >= max_age_seconds

    async def ensure_fresh_tokens(self) -> None:
        """Ensure CSRF tokens are fresh, refreshing them if necessary.

        This is a convenience method that checks token age and automatically
        refreshes CSRF/app session tokens if needed.

        Note: Access token refresh is not supported by Rivian's API.
        However, the client no longer sends Bearer tokens, so access token
        expiration does not cause authentication failures.
        """
        # Refresh CSRF if needed
        if self.needs_csrf_refresh():
            _LOGGER.debug("CSRF token is stale, refreshing...")
            await self.refresh_csrf_token()

    async def disenroll_phone(self, identity_id: str) -> bool:
        """Disenroll a phone."""
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.disenrollPhone.args(
                    attrs={"enrollmentId": identity_id}
                ).select(
                    self._ds.DisenrollPhoneResponse.success,
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "disenrollPhone")

        # Parse response
        disenroll_data = result.get("disenrollPhone", {})
        return disenroll_data.get("success", False)

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
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.enrollPhone.args(
                    attrs={
                        "userId": user_id,
                        "vehicleId": vehicle_id,
                        "publicKey": public_key,
                        "type": device_type,
                        "name": device_name,
                    }
                ).select(
                    self._ds.EnrollPhoneResponse.success,
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "enrollPhone")

        # Parse response
        enroll_data = result.get("enrollPhone", {})
        return enroll_data.get("success", False)

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
        """Validate certain vehicle command/param combos."""
        if command == VehicleCommand.CHARGING_LIMITS:
            if not (
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
        ):
            if not (
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
        # Validate command and params
        self._validate_vehicle_command(command, params)

        # Convert command to string and generate HMAC
        command = str(command)
        timestamp = str(int(time.time()))
        hmac = generate_vehicle_command_hmac(
            command, timestamp, vehicle_key, private_key
        )

        # Prepare client
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build attrs dictionary
        attrs = {
            "command": command,
            "hmac": hmac,
            "timestamp": str(timestamp),
            "vasPhoneId": phone_id,
            "deviceId": identity_id,
            "vehicleId": vehicle_id,
        }
        if params:
            attrs["params"] = params

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.sendVehicleCommand.args(attrs=attrs).select(
                    self._ds.SendVehicleCommandResponse.id,
                    self._ds.SendVehicleCommandResponse.command,
                    self._ds.SendVehicleCommandResponse.state,
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "sendVehicleCommand")

        # Parse response and return command ID
        command_data = result.get("sendVehicleCommand", {})
        return command_data.get("id")

    async def send_location_to_vehicle(
        self,
        location_str: str,
        vehicle_id: str,
    ) -> ParseAndShareLocationResponse:
        """Send a location/address to the vehicle's navigation system.

        This mutation does not require phone enrollment or HMAC signing.
        It works via cloud API only and is a "fire-and-forget" operation.
        The mutation returns success when the Rivian cloud receives the message,
        not when the vehicle actually receives it. The vehicle will pick up the
        destination when it next connects to the cloud.

        Args:
            location_str: Address string or coordinates
                         Examples: "123 Main St, Springfield, IL 62701"
                                  "40.7128,-74.0060" (latitude,longitude)
            vehicle_id: The vehicle ID to send the location to

        Returns:
            Response dict with publishResponse.result field (int, where 0 = success)

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
            RivianBadRequestError: If the location string cannot be parsed
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.parseAndShareLocationToVehicle.args(
                    str=location_str, vehicleId=vehicle_id
                ).select(
                    self._ds.ParseAndShareLocationToVehicleResponse.publishResponse.select(
                        self._ds.PublishResponse.result
                    )
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(
            client, mutation, "parseAndShareLocationToVehicle"
        )

        return result.get("parseAndShareLocationToVehicle", {})

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
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error(ex)
            return None

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
        except Exception as ex:  # pylint: disable=broad-except
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
        except Exception as ex:  # pylint: disable=broad-except
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
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error(ex)
            return None

    async def _ws_connect(self) -> ClientWebSocketResponse:
        """Initiate a websocket connection."""

        async def connection_init(websocket: ClientWebSocketResponse) -> None:
            await websocket.send_json(
                {
                    "payload": {
                        "client-name": APOLLO_CLIENT_NAME,
                        "client-version": APOLLO_CLIENT_VERSION,
                        "dc-cid": f"m-android-{uuid.uuid4()}",
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
            headers["dc-cid"] = f"m-android-{uuid.uuid4()}"

        # Add Apollo operation headers if operation name is present
        if operation_name := body.get("operationName"):
            headers["X-APOLLO-OPERATION-NAME"] = operation_name
            headers["X-APOLLO-OPERATION-ID"] = str(uuid.uuid4())

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

        try:
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
        except Exception as exception:
            raise exception

        return response

    async def close(self) -> None:
        """Close open client session."""
        if self._ws_monitor:
            await self._ws_monitor.close()
        if self._session and self._close_session:
            await self._session.close()

    async def __aenter__(self) -> Rivian:
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
