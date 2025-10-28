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
from gql.dsl import DSLMutation, DSLQuery, DSLSchema, dsl_gql, DSLInlineFragment
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
from .parallax import ParallaxCommand
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
GRAPHQL_VEHICLE_SERVICES = "https://rivian.com/api/vs/gql-gateway"  # Vehicle services endpoint
GRAPHQL_CONTENT = GRAPHQL_BASEPATH + "/content/graphql"  # Content/chat endpoint
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"

APOLLO_CLIENT_NAME = "com.rivian.ios.consumer"
APOLLO_CLIENT_VERSION = "3.6.0-4400"

BASE_HEADERS = {
    "User-Agent": "RivianApp/4400 CFNetwork/1498.700.2 Darwin/23.6.0",
    "Accept": "multipart/mixed;deferSpec=20220824,application/graphql-response+json,application/json",
    "Content-Type": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
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
            # Update headers and URL on existing transport
            if self._gql_transport:
                self._gql_transport.headers = headers
                self._gql_transport.url = url

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
        self,
        client: Client,
        query,
        operation_name: str = "operation",
        extra_args: dict | None = None,
    ):
        """Execute a GraphQL query asynchronously.

        Args:
            client: The GQL client to use
            query: The DSL query to execute
            operation_name: Name of the operation for logging
            extra_args: Optional extra arguments (e.g., headers) for the request

        Returns:
            The query result

        Raises:
            Various RivianApiException subclasses based on error type
        """
        try:
            async with async_timeout.timeout(self.request_timeout):
                if extra_args:
                    result = await client.execute_async(query, extra_args=extra_args)
                else:
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

    async def login(self, username: str, password: str) -> str | None:
        """Authenticate using the simplified Android app flow.

        This is the primary authentication method matching the Android app's Login mutation.
        Unlike the legacy flow, this does not require calling create_csrf_token() first.

        Args:
            username: User's email address
            password: User's password

        Returns:
            OTP token if MFA is required, None if login succeeded without MFA

        Raises:
            RivianInvalidCredentials: If username/password are incorrect
            RivianApiException: For other API errors
        """
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
        result = await self._execute_async(client, query, "login")

        # Parse response
        login_data = result["login"]

        if "otpToken" in login_data:
            # MFA required
            self._otp_needed = True
            self._otp_token = login_data["otpToken"]
            return self._otp_token
        else:
            # Login successful without MFA
            self._access_token = login_data["accessToken"]
            self._refresh_token = login_data["refreshToken"]
            self._user_session_token = login_data["userSessionToken"]
            self._token_refreshed_at = time.time()
            self._otp_needed = False
            return None

    async def login_with_otp(
        self, username: str, otp_code: str, otp_token: str | None = None
    ) -> None:
        """Complete authentication with OTP code.

        This is the primary OTP validation method matching the Android app's LoginWithOTP mutation.

        Args:
            username: User's email address
            otp_code: OTP code from email/SMS
            otp_token: OTP token from login() response (optional, uses stored token if not provided)

        Raises:
            RivianInvalidOTP: If OTP code is incorrect or expired
            RivianApiException: For other API errors
        """
        # Use provided token or fall back to stored token
        token = otp_token or self._otp_token
        if not token:
            raise RivianApiException(
                "OTP token not provided and no stored token available. Call login() first."
            )

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        query = dsl_gql(
            DSLMutation(
                self._ds.Mutation.loginWithOTP.args(
                    email=username, otpCode=otp_code, otpToken=token
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
        result = await self._execute_async(client, query, "loginWithOTP")

        # Parse response
        login_data = result["loginWithOTP"]

        self._access_token = login_data["accessToken"]
        self._refresh_token = login_data["refreshToken"]
        self._user_session_token = login_data["userSessionToken"]
        self._token_refreshed_at = time.time()
        self._otp_needed = False

    async def create_csrf_token(self) -> None:
        """### DEPRECATED (optional with new login flow)

        Create cross-site-request-forgery (csrf) token.

        Note: The new login() method does not require CSRF tokens.
        This method is maintained for backward compatibility and legacy integrations.
        """
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
        """### DEPRECATED (use `login` instead)

        Authenticate against the Rivian GraphQL API with Username and Password.

        This method is maintained for backward compatibility. New code should use
        the login() method which follows the Android app's simpler authentication flow.
        """
        # Call new login method
        otp_token = await self.login(username, password)
        # Store in legacy flag for compatibility
        if otp_token:
            self._otp_needed = True

    async def authenticate_graphql(
        self, username: str, password: str
    ) -> None:  # pragma: no cover
        """### DEPRECATED (use `authenticate` instead)

        Authenticate against the Rivian GraphQL API with Username and Password.
        """
        send_deprecation_warning("authenticate_graphql", "authenticate")
        return await self.authenticate(username=username, password=password)

    async def validate_otp(self, username: str, otp_code: str) -> None:
        """### DEPRECATED (use `login_with_otp` instead)

        Validates OTP against the Rivian GraphQL API with Username, OTP Code, and OTP Token.

        This method is maintained for backward compatibility. New code should use
        the login_with_otp() method which follows the Android app's simpler authentication flow.
        """
        # Call new login_with_otp method
        await self.login_with_otp(username, otp_code)

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

    async def get_drivers_and_keys(self, vehicle_id: str) -> dict:
        """Get drivers and keys.

        Returns vehicle information including invited users and their devices.

        Args:
            vehicle_id: The vehicle ID to query

        Returns:
            Dict containing vehicle data with id, vin, and invitedUsers list
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL query with union type fragments for InvitedUser
        query = dsl_gql(
            DSLQuery(
                self._ds.Query.getVehicle.args(id=vehicle_id).select(
                    self._ds.Vehicle.id,
                    self._ds.Vehicle.vin,
                    self._ds.Vehicle.invitedUsers.select(
                        # Handle ProvisionedUser type
                        DSLInlineFragment()
                        .on(self._ds.ProvisionedUser)
                        .select(
                            self._ds.ProvisionedUser.firstName,
                            self._ds.ProvisionedUser.lastName,
                            self._ds.ProvisionedUser.email,
                            self._ds.ProvisionedUser.roles,
                            self._ds.ProvisionedUser.userId,
                            self._ds.ProvisionedUser.devices.select(
                                self._ds.UserDevice.type,
                                self._ds.UserDevice.mappedIdentityId,
                                self._ds.UserDevice.id,
                                self._ds.UserDevice.hrid,
                                self._ds.UserDevice.deviceName,
                                self._ds.UserDevice.isPaired,
                                self._ds.UserDevice.isEnabled,
                            ),
                        ),
                        # Handle UnprovisionedUser type
                        DSLInlineFragment()
                        .on(self._ds.UnprovisionedUser)
                        .select(
                            self._ds.UnprovisionedUser.email,
                            self._ds.UnprovisionedUser.inviteId,
                            self._ds.UnprovisionedUser.status,
                        ),
                    ),
                )
            )
        )

        # Execute query with error handling
        result = await self._execute_async(client, query, "getDriversAndKeys")

        # Return the getVehicle response
        return result.get("getVehicle", {})

    async def get_user_information(self, include_phones: bool = False) -> dict:
        """Get user information.

        Args:
            include_phones: Whether to include enrolled phones in the response

        Returns:
            Dictionary containing user information with structure:
            {
                "id": str,
                "vehicles": [{
                    "id": str,
                    "vin": str,
                    "name": str,
                    "state": str,
                    "createdAt": str,
                    "updatedAt": str,
                    "roles": [str],
                    "vas": {
                        "vasVehicleId": str,
                        "vehiclePublicKey": str
                    },
                    "vehicle": {
                        "id": str,
                        "vin": str,
                        "modelYear": int,
                        "make": str,
                        "model": str,
                        "expectedBuildDate": str,
                        "plannedBuildDate": str,
                        "expectedGeneralAssemblyStartDate": str,
                        "actualGeneralAssemblyDate": str,
                        "vehicleState": {
                            "supportedFeatures": [{
                                "name": str,
                                "status": str
                            }]
                        }
                    }
                }],
                "registrationChannels": [{"type": str}],
                "enrolledPhones": [{  # Only if include_phones=True
                    "vas": {
                        "vasPhoneId": str,
                        "publicKey": str
                    },
                    "enrolled": [{
                        "deviceType": str,
                        "deviceName": str,
                        "vehicleId": str,
                        "identityId": str,
                        "shortName": str
                    }]
                }]
            }

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build base query selection matching the original query structure
        user_selection = [
            self._ds.User.id,
            self._ds.User.vehicles.select(
                self._ds.UserVehicle.id,
                self._ds.UserVehicle.vin,
                self._ds.UserVehicle.name,
                self._ds.UserVehicle.state,
                self._ds.UserVehicle.createdAt,
                self._ds.UserVehicle.updatedAt,
                self._ds.UserVehicle.roles,
                self._ds.UserVehicle.vas.select(
                    self._ds.UserVehicleAccess.vasVehicleId,
                    self._ds.UserVehicleAccess.vehiclePublicKey,
                ),
                self._ds.UserVehicle.vehicle.select(
                    self._ds.VehicleDetails.id,
                    self._ds.VehicleDetails.vin,
                    self._ds.VehicleDetails.modelYear,
                    self._ds.VehicleDetails.make,
                    self._ds.VehicleDetails.model,
                    self._ds.VehicleDetails.expectedBuildDate,
                    self._ds.VehicleDetails.plannedBuildDate,
                    self._ds.VehicleDetails.expectedGeneralAssemblyStartDate,
                    self._ds.VehicleDetails.actualGeneralAssemblyDate,
                    self._ds.VehicleDetails.vehicleState.select(
                        self._ds.VehicleState.supportedFeatures.select(
                            self._ds.SupportedFeature.name,
                            self._ds.SupportedFeature.status,
                        )
                    ),
                ),
            ),
            self._ds.User.registrationChannels.select(
                self._ds.RegistrationChannel.type,
            ),
        ]

        # Conditionally add enrolledPhones if requested
        if include_phones:
            user_selection.append(
                self._ds.User.enrolledPhones.select(
                    self._ds.UserEnrolledPhone.vas.select(
                        self._ds.UserEnrolledPhoneAccess.vasPhoneId,
                        self._ds.UserEnrolledPhoneAccess.publicKey,
                    ),
                    self._ds.UserEnrolledPhone.enrolled.select(
                        self._ds.UserEnrolledPhoneEntry.deviceType,
                        self._ds.UserEnrolledPhoneEntry.deviceName,
                        self._ds.UserEnrolledPhoneEntry.vehicleId,
                        self._ds.UserEnrolledPhoneEntry.identityId,
                        self._ds.UserEnrolledPhoneEntry.shortName,
                    ),
                )
            )

        # Build DSL query
        query = dsl_gql(DSLQuery(self._ds.Query.currentUser.select(*user_selection)))

        # Execute query
        result = await self._execute_async(client, query, "getUserInfo")

        # Return currentUser data
        return result.get("currentUser", {})

    async def get_registered_wallboxes(self) -> list[dict]:
        """Get registered wallboxes.

        Returns:
            List of wallbox dictionaries, each containing wallbox details.
            Returns empty list if no wallboxes are registered.
        """
        client = await self._ensure_client(GRAPHQL_CHARGING)
        assert self._ds is not None

        # Build DSL query
        query = dsl_gql(
            DSLQuery(
                self._ds.Query.getRegisteredWallboxes.select(
                    self._ds.Wallbox.wallboxId,
                    self._ds.Wallbox.userId,
                    self._ds.Wallbox.wifiId,
                    self._ds.Wallbox.name,
                    self._ds.Wallbox.linked,
                    self._ds.Wallbox.latitude,
                    self._ds.Wallbox.longitude,
                    self._ds.Wallbox.chargingStatus,
                    self._ds.Wallbox.power,
                    self._ds.Wallbox.currentVoltage,
                    self._ds.Wallbox.currentAmps,
                    self._ds.Wallbox.softwareVersion,
                    self._ds.Wallbox.model,
                    self._ds.Wallbox.serialNumber,
                    self._ds.Wallbox.maxAmps,
                    self._ds.Wallbox.maxVoltage,
                    self._ds.Wallbox.maxPower,
                )
            )
        )

        # Execute query with error handling
        result = await self._execute_async(client, query, "getRegisteredWallboxes")

        # Parse response - return list (may be empty)
        wallboxes = result.get("getRegisteredWallboxes")
        return wallboxes if wallboxes is not None else []

    async def get_trailer_profiles(self, vehicle_id: str) -> list[dict]:
        """Get trailer profiles for a vehicle.

        Args:
            vehicle_id: The vehicle ID to query

        Returns:
            List of trailer profile dictionaries, each containing trailer details.
            Returns empty list if no trailers are configured (e.g., R1S vehicles).
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL query
        query = dsl_gql(
            DSLQuery(
                self._ds.Query.getTrailerProfiles.args(vehicleId=vehicle_id).select(
                    self._ds.TrailerProfile.id,
                    self._ds.TrailerProfile.name,
                    self._ds.TrailerProfile.length,
                    self._ds.TrailerProfile.width,
                    self._ds.TrailerProfile.height,
                    self._ds.TrailerProfile.weight,
                    self._ds.TrailerProfile.trailerType,
                    self._ds.TrailerProfile.pinnedToGear,
                    self._ds.TrailerProfile.createdAt,
                    self._ds.TrailerProfile.updatedAt,
                )
            )
        )

        # Execute query with error handling
        result = await self._execute_async(client, query, "getTrailerProfiles")

        # Parse response - return list (may be empty)
        profiles = result.get("getTrailerProfiles")
        return profiles if profiles is not None else []

    async def update_pin_to_gear(
        self, vehicle_id: str, trailer_id: str, pinned: bool
    ) -> bool:
        """Update the pin-to-gear status for a trailer profile.

        Args:
            vehicle_id: The vehicle ID
            trailer_id: The trailer profile ID
            pinned: Whether the trailer should be pinned to gear

        Returns:
            True if the operation succeeded, False otherwise
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.updatePinToGear.args(
                    vehicleId=vehicle_id, trailerId=trailer_id, pinned=pinned
                ).select(
                    self._ds.UpdatePinToGearResponse.success,
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "updatePinToGear")

        # Parse response
        update_data = result.get("updatePinToGear", {})
        return update_data.get("success", False)

    async def get_charging_schedules(self, vehicle_id: str) -> list[dict]:
        """Get configured departure/charging schedules for a vehicle.

        Args:
            vehicle_id: The vehicle ID to query schedules for

        Returns:
            List of charging schedule dictionaries with structure:
            [
                {
                    "startTime": str,
                    "duration": int,
                    "location": {"latitude": float, "longitude": float},
                    "amperage": int,
                    "enabled": bool,
                    "weekDays": [str]
                },
                ...
            ]

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL query
        query = dsl_gql(
            DSLQuery(
                self._ds.Query.getChargingSchedules.args(vehicleId=vehicle_id).select(
                    self._ds.ChargingSchedulesResponse.vehicleId,
                    self._ds.ChargingSchedulesResponse.smartChargingEnabled,
                    self._ds.ChargingSchedulesResponse.schedules.select(
                        self._ds.DepartureSchedule.id,
                        self._ds.DepartureSchedule.name,
                        self._ds.DepartureSchedule.enabled,
                        self._ds.DepartureSchedule.days,
                        self._ds.DepartureSchedule.departureTime,
                        self._ds.DepartureSchedule.cabinPreconditioning,
                        self._ds.DepartureSchedule.cabinPreconditioningTemp,
                        self._ds.DepartureSchedule.targetSOC,
                        self._ds.DepartureSchedule.offPeakHoursOnly,
                        self._ds.DepartureSchedule.location.select(
                            self._ds.ScheduleLocation.latitude,
                            self._ds.ScheduleLocation.longitude,
                            self._ds.ScheduleLocation.radius,
                        ),
                    ),
                )
            )
        )

        # Execute query with error handling
        result = await self._execute_async(client, query, "getChargingSchedules")

        # Return the schedules data
        return result.get("getChargingSchedules", {})

    async def update_departure_schedule(self, vehicle_id: str, schedule: dict) -> dict:
        """Create or update a departure schedule with charging/preconditioning settings.

        Args:
            vehicle_id: Vehicle ID
            schedule: Schedule configuration dict with fields:
                - scheduleId (str, optional): Existing schedule ID (omit for new)
                - name (str): Schedule name
                - enabled (bool): Whether schedule is active
                - days (list[str]): Days of week (e.g., ["MONDAY", "FRIDAY"])
                - departureTime (str): Time in HH:MM format
                - cabinPreconditioning (bool, optional): Enable cabin preconditioning
                - cabinPreconditioningTemp (float, optional): Target temp in Celsius (16-29)
                - targetSOC (int, optional): Target state of charge (50-100)
                - offPeakHoursOnly (bool, optional): Charge only during off-peak
                - location (dict, optional): Geofence location with latitude, longitude, radius

        Returns:
            Dict with success and schedule fields

        Raises:
            RivianBadRequestError: If schedule parameters are invalid
        """
        # Validate schedule
        self._validate_departure_schedule(schedule)

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build input dictionary
        schedule_input = {"vehicleId": vehicle_id, **schedule}

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.updateDepartureSchedule.args(
                    input=schedule_input
                ).select(
                    self._ds.UpdateDepartureScheduleResponse.success,
                    self._ds.UpdateDepartureScheduleResponse.schedule.select(
                        self._ds.DepartureSchedule.id,
                        self._ds.DepartureSchedule.name,
                        self._ds.DepartureSchedule.enabled,
                        self._ds.DepartureSchedule.days,
                        self._ds.DepartureSchedule.departureTime,
                    ),
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "updateDepartureSchedule")

        return result.get("updateDepartureSchedule", {})

    async def enroll_in_smart_charging(
        self,
        vehicle_id: str,
        utility_id: str,
        location: dict[str, float],
        tariff_id: str | None = None,
    ) -> dict:
        """Enable Rivian's smart charging feature for optimal charging times.

        Args:
            vehicle_id: Vehicle ID
            utility_id: Electric utility provider ID
            location: Home location as {"latitude": float, "longitude": float}
            tariff_id: Optional tariff/rate plan ID from the utility

        Returns:
            Dictionary with enrollment response:
            {
                "enabled": bool,
                "schedules": [...],
                "source": str
            }

        Raises:
            RivianBadRequestError: If location coordinates are invalid
        """
        # Validate location coordinates
        self._validate_coordinates(location["latitude"], location["longitude"])

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build args dict
        args: dict[str, Any] = {
            "vehicleId": vehicle_id,
            "utilityId": utility_id,
            "location": location,
        }
        if tariff_id:
            args["tariffId"] = tariff_id

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.enrollInSmartCharging.args(**args).select(
                    self._ds.SmartChargingEnrollmentResponse.enabled,
                    self._ds.SmartChargingEnrollmentResponse.schedules,
                    self._ds.SmartChargingEnrollmentResponse.source,
                )
            )
        )

        result = await self._execute_async(client, mutation, "EnrollInSmartCharging")

        return result.get("enrollInSmartCharging", {})

    async def unenroll_from_smart_charging(self, vehicle_id: str) -> bool:
        """Disable Rivian's smart charging feature.

        Args:
            vehicle_id: Vehicle ID

        Returns:
            True if unenrollment succeeded
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.unenrollFromSmartCharging.args(
                    vehicleId=vehicle_id
                ).select(
                    self._ds.SmartChargingEnrollmentResponse.success,
                )
            )
        )

        result = await self._execute_async(
            client, mutation, "unenrollFromSmartCharging"
        )

        unenroll_data = result.get("unenrollFromSmartCharging", {})
        return unenroll_data.get("success", False)

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
    ) -> dict[str, list[dict[str, Any]]]:
        """Get vehicle images.

        Returns a dict with two keys:
          - getVehicleMobileImages: List of vehicle images
          - getVehicleOrderMobileImages: List of pre-order images

        Known parameter values:
          - extension: `png`, `webp`
          - resolution: `@1x`, `@2x`, `@3x` (for png); `hdpi`, `xhdpi`, `xxhdpi`, `xxxhdpi` (for webp)
          - vehicle_version/preorder_version: `1`, `2` (all other values return v1 images)
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build image field selection
        image_fields = [
            self._ds.VehicleImage.orderId,
            self._ds.VehicleImage.vehicleId,
            self._ds.VehicleImage.url,
            self._ds.VehicleImage.extension,
            self._ds.VehicleImage.resolution,
            self._ds.VehicleImage.size,
            self._ds.VehicleImage.design,
            self._ds.VehicleImage.placement,
            self._ds.VehicleImage.overlays.select(
                self._ds.VehicleImageOverlay.url,
                self._ds.VehicleImageOverlay.overlay,
                self._ds.VehicleImageOverlay.zIndex,
            ),
        ]

        # Build DSL query with both operations
        query = dsl_gql(
            DSLQuery(
                self._ds.Query.getVehicleMobileImages.args(
                    resolution=resolution,
                    extension=extension,
                    version=vehicle_version,
                ).select(*image_fields),
                self._ds.Query.getVehicleOrderMobileImages.args(
                    resolution=resolution,
                    extension=extension,
                    version=preorder_version,
                ).select(*image_fields),
            )
        )

        # Execute query with error handling
        result = await self._execute_async(client, query, "getVehicleImages")

        return result

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

    def _validate_coordinates(self, latitude: float, longitude: float) -> None:
        """Validate GPS coordinates.

        Args:
            latitude: Latitude value to validate
            longitude: Longitude value to validate

        Raises:
            RivianBadRequestError: If coordinates are out of valid range
        """
        if not -90 <= latitude <= 90:
            raise RivianBadRequestError(
                f"Invalid latitude: {latitude}. Must be -90 to 90."
            )
        if not -180 <= longitude <= 180:
            raise RivianBadRequestError(
                f"Invalid longitude: {longitude}. Must be -180 to 180."
            )

    def _validate_departure_schedule(self, schedule: dict[str, Any]) -> None:
        """Validate departure schedule parameters.

        Args:
            schedule: Schedule configuration dict

        Raises:
            RivianBadRequestError: If validation fails
        """
        # Validate target_soc (50-100 if provided)
        if "target_soc" in schedule or "targetSOC" in schedule:
            target_soc = schedule.get("target_soc") or schedule.get("targetSOC")
            if not isinstance(target_soc, int) or not (50 <= target_soc <= 100):
                raise RivianBadRequestError(
                    "target_soc must be an integer between 50 and 100"
                )

        # Validate days (valid day names)
        if "days" in schedule:
            valid_days = {
                "MONDAY",
                "TUESDAY",
                "WEDNESDAY",
                "THURSDAY",
                "FRIDAY",
                "SATURDAY",
                "SUNDAY",
            }
            days = schedule["days"]
            if not isinstance(days, list) or not days:
                raise RivianBadRequestError("days must be a non-empty list")
            for day in days:
                if not isinstance(day, str) or day.upper() not in valid_days:
                    raise RivianBadRequestError(
                        f"Invalid day: {day}. Must be one of {valid_days}"
                    )

        # Validate departure_time (HH:MM format)
        if "departure_time" in schedule or "departureTime" in schedule:
            departure_time = schedule.get("departure_time") or schedule.get(
                "departureTime"
            )
            if not isinstance(departure_time, str):
                raise RivianBadRequestError("departure_time must be a string")
            parts = departure_time.split(":")
            if len(parts) != 2:
                raise RivianBadRequestError("departure_time must be in HH:MM format")
            try:
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError:
                raise RivianBadRequestError(
                    "departure_time must be valid HH:MM format (00:00-23:59)"
                )

        # Validate cabin_preconditioning_temp (16-29°C if provided)
        if (
            "cabin_preconditioning_temp" in schedule
            or "cabinPreconditioningTemp" in schedule
        ):
            temp = schedule.get("cabin_preconditioning_temp") or schedule.get(
                "cabinPreconditioningTemp"
            )
            if not isinstance(temp, (int, float)) or not (16 <= temp <= 29):
                raise RivianBadRequestError(
                    "cabin_preconditioning_temp must be between 16 and 29 degrees Celsius"
                )

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
            phone_id: 32-byte phone identifier from enrollment
            request_id: Optional request UUID (generated if not provided)

        Returns:
            dict with 'success' (bool) key

        Raises:
            RivianApiException: For network or API errors
            RivianUnauthenticated: If authentication is invalid

        Example:
            >>> from rivian.proto.rivian_climate_pb2 import ClimateHoldSetting
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> phone_id = bytes.fromhex(phone_id_hex)
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
        import base64
        import uuid

        from .proto.vehicle_operation import (
            Metadata,
            Operation,
            PhoneInfo,
            VehicleOperationRequest,
        )

        # Ensure client is initialized
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build VehicleOperationRequest
        phone_info = PhoneInfo(version=1, phone_id=phone_id)
        metadata = Metadata(
            phone_info=phone_info,
            request_id=request_id or str(uuid.uuid4()),
        )
        operation = Operation(
            rvm_type=rvm_type,
            operation_type=1,  # 1 = SET operation
            payload=payload,
        )
        request = VehicleOperationRequest(metadata=metadata, operation=operation)

        # Serialize and encode to base64
        request_bytes = request.SerializeToString()
        request_b64 = base64.b64encode(request_bytes).decode("utf-8")

        # Build DSL mutation - match iOS app structure
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.sendVehicleOperation.args(
                    vehicleId=vehicle_id,
                    payload=request_b64,
                ).select(
                    DSLInlineFragment()
                    .on(self._ds.SendVehicleOperationSuccess)
                    .select(
                        self._ds.SendVehicleOperationSuccess.success,
                    )
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "SendVehicleOperation")

        # Return response data
        return result.get("sendVehicleOperation", {})

    async def send_parallax_command(
        self, vehicle_id: str, parallax_cmd: ParallaxCommand
    ) -> dict:
        """Send a Parallax command to a vehicle via cloud.

        Parallax is a cloud-based protocol for remote vehicle commands and
        data retrieval. Unlike BLE commands, Parallax operates through
        Rivian's cloud infrastructure and does not require proximity.

        Args:
            vehicle_id: Vehicle VIN
            parallax_cmd: ParallaxCommand instance with encoded payload

        Returns:
            dict with 'success' (bool), 'sequenceNumber' (int), and 'payload' (str) keys

        Raises:
            RivianApiException: For network or API errors
            RivianUnauthenticated: If authentication is invalid

        Example:
            >>> from rivian.parallax import build_climate_hold_command
            >>> cmd = build_climate_hold_command(enabled=True, temp_celsius=22.0)
            >>> result = await client.send_parallax_command("VIN123", cmd)
            >>> print(f"Success: {result['success']}")
        """
        # Ensure client is initialized
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation - match Android app structure exactly
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.sendParallaxPayload.args(
                    payload=parallax_cmd.payload_b64,
                    meta={
                        "vehicleId": vehicle_id,
                        "model": str(parallax_cmd.rvm),
                        "isVehicleModelOp": True,
                        "requiresWakeup": True,
                    },
                ).select(
                    self._ds.ParallaxResponse.success,
                    self._ds.ParallaxResponse.sequenceNumber,
                )
            )
        )

        # Execute mutation
        # Note: Do NOT add Bearer token for Parallax calls - it causes INTERNAL_SERVER_ERROR
        # The session-based cookies are sufficient for authentication
        result = await self._execute_async(client, mutation, "SendRemoteCommand")

        # Return response data
        return result.get("sendParallaxPayload", {})

    async def get_charging_session_live_data(self, vehicle_id: str) -> dict:
        """Get live charging session data via Parallax protocol.

        RVM: energy_edge_compute.graphs.charge_session_breakdown

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with charging metrics (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_charging_session_live_data("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_charging_session_query

        cmd = build_charging_session_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_parked_energy_data(self, vehicle_id: str) -> dict:
        """Get energy consumption data while vehicle is parked.

        RVM: energy_edge_compute.graphs.parked_energy_distributions

        Args:
            vehicle_id: Vehicle ID or VIN

        Returns:
            dict with success, sequenceNumber, and Base64-encoded payload

        Example:
            >>> data = await client.get_parked_energy_data("VIN123")
            >>> print(f"Total kWh consumed: {data['payload']}")
        """
        from .parallax import build_parked_energy_query

        cmd = build_parked_energy_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_charging_session_chart_data(self, vehicle_id: str) -> dict:
        """Get historical charging session chart data.

        RVM: energy_edge_compute.graphs.charging_graph_global

        Args:
            vehicle_id: Vehicle ID or VIN

        Returns:
            dict with success, sequenceNumber, and Base64-encoded payload

        Example:
            >>> data = await client.get_charging_session_chart_data("VIN123")
            >>> print(f"Chart data: {data['payload']}")
        """
        from .parallax import build_charging_chart_query

        cmd = build_charging_chart_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_climate_hold_status(self, vehicle_id: str) -> dict:
        """Get climate hold status via Parallax protocol.

        RVM: comfort.cabin.climate_hold_status

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with climate status (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_climate_hold_status("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_climate_status_query

        cmd = build_climate_status_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def set_climate_hold(
        self,
        vehicle_id: str,
        enabled: bool = True,
        temp_celsius: float = 22.0,
        duration_minutes: int = 120,
        phone_id: bytes | None = None,
    ) -> dict:
        """Set climate hold via sendVehicleOperation (if phone_id provided) or Parallax.

        RVM: comfort.cabin.climate_hold_setting

        Args:
            vehicle_id: Vehicle ID (format: "01-XXXXXXXX" for sendVehicleOperation)
            enabled: Whether to enable climate hold (kept for API compatibility,
                    but not sent in protobuf - may be controlled elsewhere)
            temp_celsius: Target temperature in Celsius (kept for API compatibility,
                         but not sent in protobuf - may be controlled elsewhere)
            duration_minutes: Hold duration in minutes (sent in protobuf)
            phone_id: Optional 32-byte phone ID from enrollment. If provided,
                     uses sendVehicleOperation mutation (iOS app method).
                     If not provided, uses sendParallaxPayload mutation (Android app method).

        Returns:
            dict with success status

        Note:
            Based on APK analysis, the ClimateHoldSetting protobuf only contains
            hold_time_duration_seconds. The enabled state and target temperature
            may be controlled via separate GraphQL mutations or vehicle commands.

        Example (sendVehicleOperation - iOS method):
            >>> # Get phone_id from enrollment
            >>> user_info = await client.get_user_information(include_phones=True)
            >>> phone_id_hex = user_info["enrolledPhones"][0]["vas"]["vasPhoneId"]
            >>> phone_id = bytes.fromhex(phone_id_hex)
            >>> # Set climate hold for 8 hours
            >>> result = await client.set_climate_hold(
            ...     vehicle_id="01-276948064",
            ...     duration_minutes=480,
            ...     phone_id=phone_id
            ... )
            >>> print(f"Success: {result['success']}")

        Example (sendParallaxPayload - Android method):
            >>> result = await client.set_climate_hold("VIN123", True, 22.0, 120)
            >>> print(f"Success: {result['success']}")
        """
        # Note: Temperature validation kept for API compatibility, but temp
        # is not actually sent in the protobuf based on APK analysis
        if not 16.0 <= temp_celsius <= 29.0:
            raise RivianBadRequestError("Temperature must be between 16°C and 29°C")

        # Convert duration to seconds for protobuf
        duration_seconds = duration_minutes * 60

        if phone_id is not None:
            # Use sendVehicleOperation mutation (iOS app method)
            from .proto.rivian_climate_pb2 import ClimateHoldSetting

            setting = ClimateHoldSetting(hold_time_duration_seconds=duration_seconds)
            payload = setting.SerializeToString()

            return await self.send_vehicle_operation(
                vehicle_id=vehicle_id,
                rvm_type="comfort.cabin.climate_hold_setting",
                payload=payload,
                phone_id=phone_id,
            )
        else:
            # Use sendParallaxPayload mutation (Android app method)
            from .parallax import build_climate_hold_command

            cmd = build_climate_hold_command(duration_minutes=duration_minutes)
            return await self.send_parallax_command(vehicle_id, cmd)

    async def set_charging_schedule(
        self,
        vehicle_id: str,
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
            vehicle_id: Vehicle VIN
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
            >>> result = await client.set_charging_schedule("VIN123", 22, 0, 6, 0)
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
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_ota_status(self, vehicle_id: str) -> dict:
        """Get OTA update status via Parallax protocol.

        RVM: ota.ota_state.vehicle_ota_state

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with OTA status (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_ota_status("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_ota_status_query

        cmd = build_ota_status_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_trip_progress(self, vehicle_id: str) -> dict:
        """Get trip progress via Parallax protocol.

        RVM: navigation.navigation_service.trip_progress

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with trip progress (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_trip_progress("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_trip_progress_query

        cmd = build_trip_progress_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_trip_info(self, vehicle_id: str) -> dict:
        """Get detailed trip information via Parallax protocol.

        RVM: navigation.navigation_service.trip_info

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with trip info including waypoints (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_trip_info("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_trip_info_query

        cmd = build_trip_info_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_vehicle_wheels(self, vehicle_id: str) -> dict:
        """Get vehicle wheels configuration via Parallax protocol.

        RVM: vehicle.wheels.vehicle_wheels

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with wheel configuration and tire info (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_vehicle_wheels("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_vehicle_wheels_query

        cmd = build_vehicle_wheels_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def set_cabin_ventilation(
        self,
        vehicle_id: str,
        enabled: bool,
        mode: str = "AUTO",
        windows_open_percent: int = 0,
        sunroof_open_percent: int = 0,
        duration_minutes: int = 30,
    ) -> dict:
        """Set cabin ventilation via Parallax protocol.

        RVM: comfort.cabin.cabin_ventilation_setting

        Args:
            vehicle_id: Vehicle VIN
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
            >>> result = await client.set_cabin_ventilation("VIN123", True, "MANUAL", 50, 100, 30)
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
        return await self.send_parallax_command(vehicle_id, cmd)

    async def set_halloween_settings(
        self,
        vehicle_id: str,
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
            vehicle_id: Vehicle VIN
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
            >>> result = await client.set_halloween_settings("VIN123", True, "SPOOKY", 50, 3)
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
            enabled,
            animation_mode,
            brightness,
            repeat_count,
            schedule_enabled,
            schedule_time,
        )
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_vehicle_geofences(self, vehicle_id: str) -> dict:
        """Get vehicle geofences via Parallax protocol.

        RVM: location.geofence.vehicle_geo_fences

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with geofence data (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_vehicle_geofences("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_geofences_query

        cmd = build_geofences_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def set_vehicle_geofences(self, vehicle_id: str, fences: list[dict]) -> dict:
        """Set vehicle geofences via Parallax protocol.

        RVM: location.geofence.vehicle_geo_fences

        Args:
            vehicle_id: Vehicle VIN
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
            >>> result = await client.set_vehicle_geofences("VIN123", fences)
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
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_gear_guard_consents(self, vehicle_id: str) -> dict:
        """Get GearGuard consent settings via Parallax protocol.

        RVM: security.gear_guard.consents

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with GearGuard consent settings (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_gear_guard_consents("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_gear_guard_consents_query

        cmd = build_gear_guard_consents_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def set_gear_guard_consents(
        self,
        vehicle_id: str,
        video_enabled: bool,
        audio_enabled: bool,
        cloud_storage_enabled: bool,
        local_storage_enabled: bool,
        consent_timestamp: str = "",
    ) -> dict:
        """Set GearGuard consent settings via Parallax protocol.

        RVM: security.gear_guard.consents

        Args:
            vehicle_id: Vehicle VIN
            video_enabled: Whether video recording is enabled
            audio_enabled: Whether audio recording is enabled
            cloud_storage_enabled: Whether cloud storage is enabled
            local_storage_enabled: Whether local storage is enabled
            consent_timestamp: ISO timestamp of consent (optional)

        Returns:
            dict with success status

        Example:
            >>> result = await client.set_gear_guard_consents(
            ...     "VIN123",
            ...     video_enabled=True,
            ...     audio_enabled=False,
            ...     cloud_storage_enabled=True,
            ...     local_storage_enabled=True,
            ... )
            >>> print(f"Success: {result['success']}")
        """
        from .parallax import build_gear_guard_consents_command

        cmd = build_gear_guard_consents_command(
            video_enabled,
            audio_enabled,
            cloud_storage_enabled,
            local_storage_enabled,
            consent_timestamp,
        )
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_gear_guard_daily_limits(self, vehicle_id: str) -> dict:
        """Get GearGuard daily usage limits via Parallax protocol.

        RVM: security.gear_guard.daily_limits

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with GearGuard daily limits (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_gear_guard_daily_limits("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_gear_guard_limits_query

        cmd = build_gear_guard_limits_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def get_passive_entry_status(self, vehicle_id: str) -> dict:
        """Get passive entry status via Parallax protocol.

        RVM: access.passive_entry.status

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            dict with passive entry status (Base64 payload - needs protobuf parsing)

        Example:
            >>> data = await client.get_passive_entry_status("VIN123")
            >>> print(f"Success: {data['success']}")
        """
        from .parallax import build_passive_entry_status_query

        cmd = build_passive_entry_status_query()
        return await self.send_parallax_command(vehicle_id, cmd)

    async def set_passive_entry_settings(
        self,
        vehicle_id: str,
        enabled: bool,
        unlock_on_approach: bool = True,
        lock_on_walk_away: bool = True,
        approach_distance_meters: float = 3.0,
    ) -> dict:
        """Set passive entry settings via Parallax protocol.

        RVM: access.passive_entry.setting

        Args:
            vehicle_id: Vehicle VIN
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
            ...     "VIN123",
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

        cmd = build_passive_entry_command(
            enabled, unlock_on_approach, lock_on_walk_away, approach_distance_meters
        )
        return await self.send_parallax_command(vehicle_id, cmd)

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

    async def share_location_to_vehicle(
        self,
        vehicle_id: str,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> dict:
        """Send a location (coordinates, address, or landmark) to vehicle navigation.

        The Rivian API can parse various location formats including coordinates,
        street addresses, landmarks, and place names.

        Args:
            vehicle_id: Target vehicle ID
            location: Location string to parse (address, landmark, coordinates, etc.)
                     Examples:
                     - "1600 Amphitheatre Parkway, Mountain View, CA"
                     - "Golden Gate Bridge"
                     - "37.7749,-122.4194"
            latitude: Latitude (-90 to 90) - alternative to location string
            longitude: Longitude (-180 to 180) - must be provided with latitude

        Returns:
            Dict with publishResponse.result field (0 = success)

        Raises:
            RivianBadRequestError: If neither location nor coordinates provided,
                                  or if coordinates are invalid

        Examples:
            >>> # Send address
            >>> await client.share_location_to_vehicle(
            ...     vehicle_id, location="Rivian Headquarters, Irvine CA"
            ... )

            >>> # Send landmark
            >>> await client.share_location_to_vehicle(
            ...     vehicle_id, location="Statue of Liberty"
            ... )

            >>> # Send coordinates
            >>> await client.share_location_to_vehicle(
            ...     vehicle_id, latitude=37.7749, longitude=-122.4194
            ... )
        """
        # Determine location string format
        if location is not None:
            location_str = location
        elif latitude is not None and longitude is not None:
            # Validate coordinates
            self._validate_coordinates(latitude, longitude)
            location_str = f"{latitude},{longitude}"
        else:
            raise RivianBadRequestError(
                "Must provide either 'location' string or both 'latitude' and 'longitude'"
            )

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Android app uses parseAndShareLocationToVehicle with string format
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.parseAndShareLocationToVehicle.args(
                    str=location_str, vehicleId=vehicle_id
                ).select(
                    self._ds.ShareLocationResponse.publishResponse.select(
                        self._ds.PublishResponse.result
                    )
                )
            )
        )

        result = await self._execute_async(
            client, mutation, "ParseAndShareLocationToVehicle"
        )

        return result.get("parseAndShareLocationToVehicle", {})

    async def share_place_id_to_vehicle(self, vehicle_id: str, place_id: str) -> dict:
        """Send Google Place ID to vehicle navigation.

        Args:
            vehicle_id: Target vehicle ID
            place_id: Google Place ID (e.g., "ChIJN1t_tDeuEmsRUsoyG83frY4")

        Returns:
            Dict with publishResponse.result field (0 = success)
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.sharePlaceIdToVehicle.args(
                    placeId=place_id, vehicleId=vehicle_id
                ).select(
                    self._ds.ShareLocationResponse.publishResponse.select(
                        self._ds.PublishResponse.result
                    )
                )
            )
        )

        result = await self._execute_async(client, mutation, "sharePlaceIdToVehicle")

        return result.get("sharePlaceIdToVehicle", {})

    async def plan_trip_with_multi_stop(
        self,
        vehicle_id: str,
        waypoints: list[dict],
        starting_soc: float | None = None,
        starting_range_meters: float | None = None,
        target_arrival_soc_percent: float | None = None,
        drive_mode: str | None = None,
        network_preferences: list[dict] | None = None,
        trailer_profile: str | None = None,
        has_adapter: bool | None = None,
    ) -> dict:
        """Plan a multi-stop trip with charging stops using Rivian's trip planner.

        This query calculates optimal routes with charging stops based on
        vehicle battery state and range calculations. Results include estimated
        arrival times, charging durations, and SOC at each waypoint.

        Args:
            vehicle_id: The vehicle ID to plan the trip for
            waypoints: List of waypoint locations
                      Each waypoint: {"latitude": float, "longitude": float}
            starting_soc: Current state of charge (0-100), optional
            starting_range_meters: Current estimated range in meters, optional
            target_arrival_soc_percent: Desired SOC at final destination (0-100), optional
            drive_mode: Drive mode ("CONSERVE", "SPORT", "ALL_PURPOSE"), optional
            network_preferences: List of charging network preferences, optional
                                [{"networkId": str, "preference": str}, ...]
            trailer_profile: Trailer configuration profile, optional
            has_adapter: Whether vehicle has charging adapter, optional

        Returns:
            Dict with trip plan details from planTrip2 response:
            {
                "plans": [
                    {
                        "planIdentifierMetadata": {...},
                        "driveLegs": [...],
                        "waypoints": [...],
                        "batteryEmptyLocation": {...},
                        "summary": {
                            "destinationReachable": bool,
                            "totalChargeDurationSeconds": int,
                            "totalDriveDurationSeconds": int,
                            "totalDriveDistanceMeters": float,
                            ...
                        }
                    }
                ],
                "status": str
            }

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
            RivianBadRequestError: If waypoints are invalid
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build args dict (only include provided parameters)
        args: dict[str, Any] = {
            "waypoints": waypoints,
            "vehicle": vehicle_id,
        }
        if starting_soc is not None:
            args["startingSoc"] = starting_soc
        if starting_range_meters is not None:
            args["startingRangeMeters"] = starting_range_meters
        if target_arrival_soc_percent is not None:
            args["targetArrivalSocPercent"] = target_arrival_soc_percent
        if drive_mode is not None:
            args["driveMode"] = drive_mode
        if network_preferences is not None:
            args["networkPreferences"] = network_preferences
        if trailer_profile is not None:
            args["trailerProfile"] = trailer_profile
        if has_adapter is not None:
            args["hasAdapter"] = has_adapter

        # Build DSL query (not mutation!)
        query = dsl_gql(
            DSLQuery(
                self._ds.Query.planTrip2.args(**args).select(
                    self._ds.PlanTrip2Response.plans.select(
                        self._ds.TripPlan.summary.select(
                            self._ds.TripSummary.destinationReachable,
                            self._ds.TripSummary.socBelowLimitAtDestination,
                            self._ds.TripSummary.totalChargeDurationSeconds,
                            self._ds.TripSummary.totalDriveDurationSeconds,
                            self._ds.TripSummary.totalDriveDistanceMeters,
                            self._ds.TripSummary.totalTripDurationSeconds,
                            self._ds.TripSummary.arrivalSOCPercent,
                            self._ds.TripSummary.arrivalRangeMeters,
                            self._ds.TripSummary.arrivalEnergyKwh,
                        ),
                        self._ds.TripPlan.waypoints.select(
                            self._ds.TripWaypoint.waypointType,
                            self._ds.TripWaypoint.latitude,
                            self._ds.TripWaypoint.longitude,
                            self._ds.TripWaypoint.arrivalSOCPercent,
                            self._ds.TripWaypoint.departureSOCPercent,
                            self._ds.TripWaypoint.arrivalRangeMeters,
                            self._ds.TripWaypoint.departureRangeMeters,
                        ),
                    ),
                    self._ds.PlanTrip2Response.status,
                )
            )
        )

        # Execute query
        result = await self._execute_async(client, query, "planTripWithMultiStopV2")

        return result.get("planTrip2", {})

    async def save_trip_plan(self, trip_id: str, name: str) -> dict:
        """Save a planned trip for future reference.

        Args:
            trip_id: Trip ID from plan_trip_with_multi_stop()
            name: Name for the saved trip

        Returns:
            Dict with success status and saved trip info:
            {
                "success": bool,
                "savedTrip": {
                    "id": str,
                    "name": str,
                    "createdAt": str,
                    "updatedAt": str,
                    "vehicleId": str
                }
            }

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.saveTrip.args(tripId=trip_id, name=name).select(
                    self._ds.SaveTripResponse.success,
                    self._ds.SaveTripResponse.savedTrip.select(
                        self._ds.SavedTrip.id,
                        self._ds.SavedTrip.name,
                        self._ds.SavedTrip.createdAt,
                        self._ds.SavedTrip.updatedAt,
                        self._ds.SavedTrip.vehicleId,
                    ),
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "saveTrip")

        return result.get("saveTrip", {})

    async def update_trip(self, trip_id: str, updates: dict) -> dict:
        """Update a saved trip plan.

        Args:
            trip_id: Saved trip ID
            updates: Fields to update
                    - name (str, optional): New trip name
                    - waypoints (list[dict], optional): Updated waypoints

        Returns:
            Dict with success status and updated trip info:
            {
                "success": bool,
                "trip": {
                    "id": str,
                    "name": str,
                    "updatedAt": str
                }
            }

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.updateTrip.args(tripId=trip_id, input=updates).select(
                    self._ds.UpdateTripResponse.success,
                    self._ds.UpdateTripResponse.trip.select(
                        self._ds.SavedTrip.id,
                        self._ds.SavedTrip.name,
                        self._ds.SavedTrip.updatedAt,
                    ),
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "updateTrip")

        return result.get("updateTrip", {})

    async def delete_trip(self, trip_id: str) -> bool:
        """Delete a saved trip plan.

        Args:
            trip_id: Trip ID to delete

        Returns:
            True if deletion succeeded, False otherwise

        Raises:
            RivianApiException: If the request fails
            RivianUnauthenticated: If authentication is invalid
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        # Build DSL mutation
        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.deleteTrip.args(tripId=trip_id).select(
                    self._ds.DeleteTripResponse.success,
                )
            )
        )

        # Execute mutation
        result = await self._execute_async(client, mutation, "deleteTrip")

        # Extract and return success boolean
        delete_data = result.get("deleteTrip", {})
        return delete_data.get("success", False)

    async def create_signing_challenge(self, vehicle_id: str, device_id: str) -> dict:
        """Create cryptographic challenge for CCC digital key authentication.

        CCC (Car Connectivity Consortium) digital keys are next-generation
        vehicle access credentials that work with Apple CarKey and similar platforms.

        Args:
            vehicle_id: Vehicle ID
            device_id: Device/phone ID

        Returns:
            Dict with challenge data:
            {
                "challenge": "base64_encoded_challenge",
                "challengeId": "challenge_123",
                "expiresAt": "2024-10-26T15:00:00Z"
            }
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.createSigningChallenge.args(
                    vehicleId=vehicle_id, deviceId=device_id
                ).select(
                    self._ds.SigningChallengeResponse.challenge,
                    self._ds.SigningChallengeResponse.challengeId,
                    self._ds.SigningChallengeResponse.expiresAt,
                )
            )
        )

        result = await self._execute_async(client, mutation, "createSigningChallenge")

        return result.get("createSigningChallenge", {})

    async def verify_signing_challenge(
        self, vehicle_id: str, device_id: str, challenge_id: str, signature: str
    ) -> bool:
        """Verify signed challenge response for CCC authentication.

        Args:
            vehicle_id: Vehicle ID
            device_id: Device/phone ID
            challenge_id: Challenge ID from create_signing_challenge()
            signature: Base64-encoded signature

        Returns:
            True if verification succeeded
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.verifySigningChallenge.args(
                    vehicleId=vehicle_id,
                    deviceId=device_id,
                    challengeId=challenge_id,
                    signature=signature,
                ).select(
                    self._ds.VerifyChallengeResponse.verified,
                )
            )
        )

        result = await self._execute_async(client, mutation, "verifySigningChallenge")

        verify_data = result.get("verifySigningChallenge", {})
        return verify_data.get("verified", False)

    async def enable_ccc(self, vehicle_id: str, device_id: str) -> bool:
        """Enable Car Connectivity Consortium digital key support.

        Args:
            vehicle_id: Vehicle ID
            device_id: Device/phone ID

        Returns:
            True if CCC was enabled
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.enableCcc.args(
                    vehicleId=vehicle_id, deviceId=device_id
                ).select(
                    self._ds.EnableCccResponse.enabled,
                )
            )
        )

        result = await self._execute_async(client, mutation, "enableCcc")

        enable_data = result.get("enableCcc", {})
        return enable_data.get("enabled", False)

    async def upgrade_key_to_wcc2(self, vehicle_id: str, device_id: str) -> bool:
        """Upgrade digital key to WCC 2.0 (Wireless Car Connectivity) standard.

        Args:
            vehicle_id: Vehicle ID
            device_id: Device/phone ID

        Returns:
            True if upgrade succeeded
        """
        client = await self._ensure_client(GRAPHQL_GATEWAY)
        assert self._ds is not None

        mutation = dsl_gql(
            DSLMutation(
                self._ds.Mutation.upgradeKeyToWCC2.args(
                    vehicleId=vehicle_id, deviceId=device_id
                ).select(
                    self._ds.UpgradeKeyResponse.upgraded,
                )
            )
        )

        result = await self._execute_async(client, mutation, "upgradeKeyToWCC2")

        upgrade_data = result.get("upgradeKeyToWCC2", {})
        return upgrade_data.get("upgraded", False)

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

    async def subscribe_for_gear_guard_config(
        self,
        vehicle_id: str,
        callback: Callable[[dict[str, Any]], None],
    ) -> Callable | None:
        """Subscribe to Gear Guard remote configuration updates.

        Args:
            vehicle_id: Vehicle ID to subscribe to
            callback: Function called when config updates

        Returns:
            Unsubscribe function or None if connection fails
        """
        try:
            await self._ws_connect()
            assert self._ws_monitor
            async with async_timeout.timeout(self.request_timeout):
                await self._ws_monitor.connection_ack.wait()
            payload = {
                "operationName": "GearGuardRemoteConfig",
                "query": "subscription GearGuardRemoteConfig($vehicleID: String!) { gearGuardRemoteConfig(vehicleId: $vehicleID) { enabled videoMode recordingQuality streamingAvailable storageRemaining lastEventTimestamp } }",
                "variables": {"vehicleID": vehicle_id},
            }
            unsubscribe = await self._ws_monitor.start_subscription(payload, callback)
            _LOGGER.debug(
                "Vehicle %s subscribed to Gear Guard config updates", vehicle_id
            )
            return unsubscribe
        except Exception as ex:  # pylint: disable=broad-except
            _LOGGER.error(ex)
            return None

    # User & Account Methods (from iOS app traffic analysis)

    async def get_referral_code(self) -> dict:
        """Get user's referral code.

        Returns:
            dict with referral code information including:
                - code: Referral code string
                - url: Shareable referral URL
                - referralCode: Alias for code field

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> referral = await client.get_referral_code()
            >>> print(f"Referral code: {referral['code']}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        ds = DSLSchema(client.schema)

        query = dsl_gql(
            DSLQuery(ds.Query.getReferralCode.select(ds.ReferralCodeResponse.code, ds.ReferralCodeResponse.url, ds.ReferralCodeResponse.referralCode))
        )

        data = await self._execute_async(client, query)
        return data.get("getReferralCode", {})

    async def get_invitations_by_user(self) -> list[dict]:
        """Get vehicle invitations for the current user.

        Returns:
            list of invitation dictionaries, each containing:
                - id: Invitation ID
                - invitedByFirstName: First name of person who sent invite
                - role: Role granted by invitation
                - status: Invitation status
                - vehicleId: Vehicle VIN
                - vehicleModel: Model of vehicle
                - email: Invited user's email

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> invites = await client.get_invitations_by_user()
            >>> for inv in invites:
            ...     print(f"Invited to {inv['vehicleModel']} by {inv['invitedByFirstName']}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        ds = DSLSchema(client.schema)

        query = dsl_gql(
            DSLQuery(ds.Query.getInvitationsByUser.select(ds.UserInvitation.id, ds.UserInvitation.invitedByFirstName, ds.UserInvitation.role, ds.UserInvitation.status, ds.UserInvitation.vehicleId, ds.UserInvitation.vehicleModel, ds.UserInvitation.email))
        )

        data = await self._execute_async(client, query)
        return data.get("getInvitationsByUser", [])

    # Vehicle Services Methods (vs/gql-gateway endpoint)

    async def get_service_appointments(self, vehicle_id: str) -> list[dict]:
        """Get service appointments for a vehicle.

        This uses the vehicle services endpoint (vs/gql-gateway).

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            list of appointment dictionaries, each containing:
                - id: Appointment ID
                - vehicleId: Vehicle VIN
                - status: Appointment status
                - scheduledTime: Scheduled date/time
                - serviceType: Type of service
                - location: Service location details
                - notes: Appointment notes

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> appointments = await client.get_service_appointments("VIN123")
            >>> for appt in appointments:
            ...     print(f"{appt['serviceType']} on {appt['scheduledTime']}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_VEHICLE_SERVICES)
        ds = DSLSchema(client.schema)

        query = dsl_gql(
            DSLQuery(
                ds.Query.getAppointments(vehicleId=vehicle_id).select(
                    ds.ServiceAppointmentsResponse.appointments.select(
                        ds.ServiceAppointment.id,
                        ds.ServiceAppointment.vehicleId,
                        ds.ServiceAppointment.status,
                        ds.ServiceAppointment.scheduledTime,
                        ds.ServiceAppointment.serviceType,
                        ds.ServiceAppointment.notes,
                        ds.ServiceAppointment.createdAt,
                        ds.ServiceAppointment.updatedAt,
                    )
                )
            )
        )

        data = await self._execute_async(client, query)
        response = data.get("getAppointments", {})
        return response.get("appointments", [])

    async def get_active_service_requests(self, vehicle_id: str) -> list[dict]:
        """Get active service requests for a vehicle.

        This uses the vehicle services endpoint (vs/gql-gateway).

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            list of service request dictionaries, each containing:
                - id: Request ID
                - vehicleId: Vehicle VIN
                - status: Request status
                - description: Request description
                - category: Service category
                - priority: Request priority
                - createdAt: Creation timestamp
                - assignedTo: Assigned technician

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> requests = await client.get_active_service_requests("VIN123")
            >>> for req in requests:
            ...     print(f"{req['category']}: {req['description']} [{req['status']}]")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_VEHICLE_SERVICES)
        ds = DSLSchema(client.schema)

        query = dsl_gql(
            DSLQuery(
                ds.Query.getActiveRequests(vehicleId=vehicle_id).select(
                    ds.ServiceRequestsResponse.requests.select(
                        ds.ServiceRequest.id,
                        ds.ServiceRequest.vehicleId,
                        ds.ServiceRequest.status,
                        ds.ServiceRequest.description,
                        ds.ServiceRequest.category,
                        ds.ServiceRequest.priority,
                        ds.ServiceRequest.createdAt,
                        ds.ServiceRequest.updatedAt,
                        ds.ServiceRequest.assignedTo,
                    )
                )
            )
        )

        data = await self._execute_async(client, query)
        response = data.get("getActiveRequests", {})
        return response.get("requests", [])

    async def get_vehicle_provisioned_users(self, vehicle_id: str) -> list[dict]:
        """Get provisioned users for a vehicle.

        Args:
            vehicle_id: Vehicle VIN

        Returns:
            list of provisioned user dictionaries, each containing:
                - userId: User ID
                - firstName: User's first name
                - lastName: User's last name
                - email: User's email
                - roles: List of roles
                - status: User status
                - devices: List of paired devices

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> users = await client.get_vehicle_provisioned_users("VIN123")
            >>> for user in users:
            ...     print(f"{user['firstName']} {user['lastName']} - {', '.join(user['roles'])}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        ds = DSLSchema(client.schema)

        query = dsl_gql(
            DSLQuery(
                ds.Query.getProvisionedUsersForVehicle(vehicleId=vehicle_id).select(
                    ds.ProvisionedUsersResponse.users.select(
                        ds.ProvisionedVehicleUser.userId,
                        ds.ProvisionedVehicleUser.firstName,
                        ds.ProvisionedVehicleUser.lastName,
                        ds.ProvisionedVehicleUser.email,
                        ds.ProvisionedVehicleUser.roles,
                        ds.ProvisionedVehicleUser.status,
                        ds.ProvisionedVehicleUser.createdAt,
                        ds.ProvisionedVehicleUser.acceptedAt,
                    )
                )
            )
        )

        data = await self._execute_async(client, query)
        response = data.get("getProvisionedUsersForVehicle", {})
        return response.get("users", [])

    # Notification Methods

    async def register_notification_tokens(
        self, tokens: list[dict[str, str]]
    ) -> dict:
        """Register multiple notification tokens.

        Args:
            tokens: List of token dictionaries, each containing:
                - token: Notification token string (required)
                - platform: Platform name like "ios" or "android" (required)
                - deviceId: Device identifier (optional)
                - appVersion: App version string (optional)

        Returns:
            dict with:
                - success: Boolean indicating success
                - message: Status message
                - registeredTokens: List of successfully registered tokens
                - errors: List of errors for failed registrations

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> tokens = [
            ...     {"token": "abc123", "platform": "ios", "deviceId": "device1"},
            ...     {"token": "def456", "platform": "android", "deviceId": "device2"}
            ... ]
            >>> result = await client.register_notification_tokens(tokens)
            >>> print(f"Registered {len(result['registeredTokens'])} tokens")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        ds = DSLSchema(client.schema)

        token_inputs = [
            ds.NotificationTokenInput(
                token=t["token"],
                platform=t["platform"],
                deviceId=t.get("deviceId"),
                appVersion=t.get("appVersion"),
            )
            for t in tokens
        ]

        mutation = dsl_gql(
            DSLMutation(
                ds.Mutation.registerNotificationTokens(tokens=token_inputs).select(
                    ds.NotificationResponse.success,
                    ds.NotificationResponse.message,
                    ds.NotificationResponse.registeredTokens,
                )
            )
        )

        data = await self._execute_async(client, mutation)
        return data.get("registerNotificationTokens", {})

    async def register_push_notification_token(
        self, token: str, platform: str, vehicle_id: str | None = None
    ) -> dict:
        """Register a single push notification token.

        Args:
            token: Notification token string
            platform: Platform name like "ios" or "android"
            vehicle_id: Optional vehicle VIN to associate token with

        Returns:
            dict with:
                - success: Boolean indicating success
                - message: Status message

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> result = await client.register_push_notification_token(
            ...     "my_token_string", "ios", "VIN123"
            ... )
            >>> print(f"Success: {result['success']}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        ds = DSLSchema(client.schema)

        mutation = dsl_gql(
            DSLMutation(
                ds.Mutation.registerPushNotificationToken(
                    token=token, platform=platform, vehicleId=vehicle_id
                ).select(ds.NotificationResponse.success, ds.NotificationResponse.message)
            )
        )

        data = await self._execute_async(client, mutation)
        return data.get("registerPushNotificationToken", {})

    async def register_live_notification_token(
        self, vehicle_id: str, token: str
    ) -> dict:
        """Register a live notification start token for a vehicle.

        Args:
            vehicle_id: Vehicle VIN
            token: Notification token string

        Returns:
            dict with:
                - success: Boolean indicating success
                - message: Status message

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> result = await client.register_live_notification_token("VIN123", "token")
            >>> print(f"Success: {result['success']}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_GATEWAY)
        ds = DSLSchema(client.schema)

        mutation = dsl_gql(
            DSLMutation(
                ds.Mutation.liveNotificationRegisterStartToken(
                    vehicleId=vehicle_id, token=token
                ).select(ds.NotificationResponse.success, ds.NotificationResponse.message)
            )
        )

        data = await self._execute_async(client, mutation)
        return data.get("liveNotificationRegisterStartToken", {})

    # Content/Chat Methods

    async def get_chat_session(self, vehicle_id: str | None = None) -> dict:
        """Get chat support session information.

        This uses the content endpoint (gql/content/graphql).

        Args:
            vehicle_id: Optional vehicle VIN to associate with chat

        Returns:
            dict with:
                - sessionId: Chat session ID
                - active: Whether session is active
                - status: Session status
                - createdAt: Creation timestamp

        Raises:
            RivianApiException: If API call fails

        Example:
            >>> session = await client.get_chat_session("VIN123")
            >>> print(f"Session {session['sessionId']}: {session['status']}")
        """
        await self.ensure_fresh_tokens()

        client = await self._ensure_client(GRAPHQL_CONTENT)
        ds = DSLSchema(client.schema)

        query = dsl_gql(
            DSLQuery(
                ds.Query.chatSession(vehicleId=vehicle_id).select(
                    ds.ChatSession.sessionId,
                    ds.ChatSession.active,
                    ds.ChatSession.status,
                    ds.ChatSession.createdAt,
                )
            )
        )

        data = await self._execute_async(client, query)
        return data.get("chatSession", {})

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
