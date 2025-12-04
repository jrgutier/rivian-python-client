# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Unofficial asynchronous Python client library for the Rivian API. Provides GraphQL-based access to vehicle state, commands, and charging data for Rivian vehicles (R1T/R1S).

## Development Commands

### Setup
```bash
# Install dependencies (uses Poetry for dependency management)
poetry install

# Install BLE extras for Bluetooth functionality (optional)
poetry install --extras ble

# Setup pre-commit hooks
pre-commit install
```

### Testing
```bash
# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/rivian_test.py

# Run specific test function
poetry run pytest tests/rivian_test.py::test_authentication
```

### Linting & Formatting
```bash
# Run ruff linter with auto-fix
poetry run ruff check --fix

# Run ruff formatter
poetry run ruff format

# Run type checking
poetry run mypy src/rivian
```

Pre-commit hooks automatically run `ruff` (linter with --fix) and `ruff-format` on staged files.

## Architecture

### Core Components

**`rivian.py`** - Main `Rivian` class providing async API client
- Handles authentication flow (username/password + OTP)
- GraphQL query execution with three endpoints:
  - `GRAPHQL_GATEWAY` - Main API for vehicle state/commands
  - `GRAPHQL_CHARGING` - Charging-specific data
  - `GRAPHQL_WEBSOCKET` - WebSocket subscriptions for real-time updates
- Session management (CSRF, app session, user session tokens)
- Vehicle command execution with HMAC signing
- WebSocket subscriptions for real-time vehicle state updates

### GraphQL Client Architecture

The client uses a **hybrid approach** combining two GraphQL execution methods:

1. **gql with DSL** (12 methods) - Type-safe queries using the `gql` library v3.5.3
   - Used for all new query/mutation methods
   - Static schema defined in `schema.py` (not introspected)
   - Type-safe query building via DSL (Domain Specific Language)
   - Better error handling and validation
   - Returns structured data (`dict`, `list[dict]`, `bool`, `str`, etc.)

2. **Legacy `__graphql_query()`** (8 methods) - Direct GraphQL string execution
   - Used for older methods returning `ClientResponse` objects
   - Maintains backward compatibility with existing API
   - Being gradually migrated to DSL approach

**Static Schema:** The GraphQL schema is statically defined in `src/rivian/schema.py` rather than fetched via introspection. This approach:
- Eliminates network overhead from schema introspection
- Makes testing easier (no need to mock schema fetch)
- Provides faster initialization
- Comprehensive schema covering all queries, mutations, and subscriptions

**Methods Using gql DSL (v2.0+):**

**Authentication (Mutations):**
- `login(username, password)` - Returns `str | None` (OTP token if MFA required)
- `login_with_otp(username, otp_code, otp_token)` - Returns `None` (void)
- `create_csrf_token()` - Returns `None` (void) - **Deprecated, use `login()` instead**
- `authenticate(username, password)` - Returns `None` (void) - **Deprecated, use `login()` instead**
- `validate_otp(username, otp_code)` - Returns `None` (void) - **Deprecated, use `login_with_otp()` instead**

**Query Methods:**
- `get_user_information(include_phones)` - Returns `dict` with user info, vehicles, and optionally phones
- `get_drivers_and_keys(vehicle_id)` - Returns `dict` with vehicle data and invited users/devices
- `get_registered_wallboxes()` - Returns `list[dict]` of wallboxes (empty list if none)
- `get_vehicle_images()` - Returns `dict[str, list[dict]]` with mobile and pre-order images

**Phone & Command Methods:**
- `enroll_phone()` - Returns `bool`
- `disenroll_phone()` - Returns `bool`
- `send_vehicle_command()` - Returns `str | None` (command ID)

**Methods Using Legacy `__graphql_query()`:**
- Methods still returning `ClientResponse`:
  - `get_vehicle_state(vin, properties)` - Use WebSocket subscriptions for real-time data
  - `get_vehicle_command_state(command_id)` - Use `subscribe_for_command_state()` instead
  - `get_live_charging_session(vin, properties)` - Use `subscribe_for_charging_session()` instead
  - `get_vehicle_ota_update_details(vehicle_id)`
  - Various subscription and mutation methods (not yet migrated)

**`schema.py`** - Static GraphQL schema definition
- Comprehensive schema covering all queries, mutations, and subscriptions
- Includes all types: User, Vehicle, Wallbox, VehicleImage, etc.
- Used to avoid schema introspection overhead
- Updated when new types or operations are needed

**`const.py`** - Constants and enums
- `VehicleCommand` enum - All supported vehicle commands
- `VEHICLE_STATE_PROPERTIES` - Properties available via REST API
- `VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES` - Properties only available via WebSocket
- `LIVE_SESSION_PROPERTIES` - Charging session properties

**`utils.py`** - Cryptographic utilities
- `generate_key_pair()` - Creates ECDSA key pairs for phone enrollment
- HMAC generation for vehicle commands using ECDH shared secret
- Key encoding/decoding helpers

**`ble.py`** - Bluetooth Low Energy phone pairing (Gen 1 & Gen 2 support)
- Unified BLE pairing interface with automatic generation detection
- Supports Gen 1 (LEGACY): Early production vehicles (2021-2023)
- Supports Gen 2 (PRE_CCC): Late 2023+ vehicles with enhanced security
- Auto-detects vehicle generation based on available BLE characteristics
- Routes to appropriate protocol implementation
- Optional dependency (requires `bleak` package)

**`ble_gen2.py`** - Gen 2 (PRE_CCC) BLE pairing protocol
- 4-state authentication state machine (INIT → PID_PNONCE_SENT → SIGNED_PARAMS_SENT → AUTHENTICATED)
- ECDH (P-256) key derivation for shared secret
- Enhanced HMAC-SHA256 with multi-component input
- Protocol Buffer message serialization
- Encrypted and unencrypted BLE characteristic channels

**`ble_gen2_proto.py`** - Protocol Buffer message builders for Gen 2
- Hand-crafted protobuf wire format construction (no .proto files needed)
- Phase 1: Phone ID + Phone Nonce message
- Phase 3: SIGNED_PARAMS with HMAC signature
- HMAC input buffer composition
- Vehicle nonce response parsing

**`ws_monitor.py`** - WebSocket connection manager
- Maintains persistent WebSocket connections
- Handles subscription lifecycle
- Auto-reconnection logic

**`exceptions.py`** - Custom exception hierarchy
- Maps GraphQL error codes to specific exceptions
- Rate limiting, authentication, and validation errors

### Authentication Flow

**Recommended (v2.0+):**
1. `login(username, password)` - Returns OTP token if MFA required, otherwise completes login
2. `login_with_otp(username, otp_code, otp_token)` if OTP token was returned
3. All subsequent requests use access/user session tokens

**Legacy (deprecated but functional):**
1. `create_csrf_token()` - Get CSRF and app session tokens
2. `authenticate(username, password)` - Login (may return OTP token)
3. `validate_otp(username, otp_code)` if OTP required
4. All subsequent requests use access/user session tokens

### Phone Enrollment & Vehicle Control

Vehicle commands require phone enrollment:
1. Generate key pair: `utils.generate_key_pair()`
2. Enroll phone: `enroll_phone()` with public key
3. Pair via BLE: `ble.pair_phone()` with private key
4. Send commands: `send_vehicle_command()` with HMAC signing

**Gen 1 vs Gen 2 BLE Pairing:**

| Feature | Gen 1 (LEGACY) | Gen 2 (PRE_CCC) |
|---------|----------------|-----------------|
| **Vehicles** | R1T/R1S early prod (2021-2023) | R1T/R1S late 2023+ |
| **States** | 2-3 simple states | 4 explicit states |
| **Serialization** | Simple binary | Protocol Buffers |
| **HMAC Input** | phone_nonce + hmac | protobuf + csn + phone_id + pnonce + vnonce |
| **Key Derivation** | Direct ECDSA | ECDH (P-256) |
| **Encryption** | Basic | AES-GCM derived |
| **CSN Counter** | +1 | +2 (even/odd) |
| **Detection** | Automatic via BLE characteristics |

The `ble.pair_phone()` function automatically detects the vehicle generation and uses the appropriate protocol.

### Vehicle State Access

Real-time vehicle state is primarily accessed via WebSocket subscriptions:
- **WebSocket** (recommended): `subscribe_for_vehicle_updates()` - Real-time push updates with property filtering
- **REST API** (legacy): `get_vehicle_state()` - On-demand queries (returns `ClientResponse`, not migrated to DSL)

Properties are defined in `const.py`:
- `VEHICLE_STATE_PROPERTIES` - Available via REST API
- `VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES` - Only available via WebSocket

### Parallax Protocol (Cloud-Based Commands)

**Overview:**
Parallax is a cloud-based GraphQL protocol for remote vehicle commands and data retrieval. Unlike BLE commands that require proximity, Parallax operates through Rivian's cloud infrastructure and works from anywhere with internet connectivity.

**Use Cases:**
- Remote monitoring and control via Home Assistant integration
- Cloud-based data retrieval (charging sessions, trip progress, energy analytics)
- Vehicle operations that don't require physical proximity
- Features requiring internet connectivity

**Architecture Components:**

**`parallax.py`** - Core Parallax module
- `RVMType` enum - 18 Remote Vehicle Module types covering all vehicle domains
- `ParallaxCommand` class - Command wrapper with Base64 encoding
- Helper functions for Phase 1 RVM types (6 implemented):
  - `build_charging_session_query()` - Live charging data
  - `build_climate_status_query()` - Climate hold status
  - `build_climate_hold_command()` - Enable/disable climate hold
  - `build_charging_schedule_command()` - Set charging time windows
  - `build_ota_status_query()` - OTA update status
  - `build_trip_progress_query()` - Navigation trip progress

**`proto/`** - Protocol Buffer message definitions
- `base.py` - Common types (`TimeOfDay`, `SessionCost`)
- `charging.py` - Charging structures (`ChargingSessionLiveData`, `ChargingScheduleTimeWindow`)
- `climate.py` - Climate control structures (`ClimateHoldSetting`, `ClimateHoldStatus`)
- `ota.py` - OTA update structures
- `navigation.py` - Navigation structures

**Key Concepts:**

1. **RVM Types**: 18 Remote Vehicle Module domains organized by function:
   - Energy & Charging (4 types): Energy monitoring, charging sessions, schedules
   - Navigation (2 types): Trip info, trip progress
   - Climate & Comfort (3 types): Climate hold, cabin ventilation
   - OTA Updates (2 types): Update status, schedule configuration
   - GearGuard (2 types): Streaming consents, daily limits
   - Geofence (1 type): Favorite geofences
   - Vehicle (1 type): Wheels configuration
   - Vehicle Access (2 types): Passive entry settings/status
   - Holiday Celebrations (1 type): Halloween settings

2. **Protocol Buffers**: Wire format serialization using `google.protobuf.message.Message`
   - Messages inherit from `_message.Message` base class
   - Each message implements `to_dict()` for debugging/logging
   - Serialization via `SerializeToString()` method

3. **Base64 Encoding**: All protobuf payloads are Base64-encoded before GraphQL transmission
   - Handled automatically by `ParallaxCommand` class
   - Empty payloads for read operations (queries)
   - Encoded protobuf messages for write operations (commands)

4. **GraphQL Mutation**: Commands sent via `sendParallaxPayload` mutation
   - Requires vehicle ID and RVM type
   - Accepts Base64-encoded payload
   - Returns success status, sequence number, and response payload

**Implementation Patterns:**

```python
# Read operation (query with empty payload)
async def get_something(vehicle_id: str) -> dict:
    """Query vehicle data."""
    cmd = ParallaxCommand(RVMType.SOMETHING, b"")
    return await self.send_parallax_command(vehicle_id, cmd)

# Write operation (command with protobuf message)
async def set_something(vehicle_id: str, value: Any) -> dict:
    """Send command to vehicle."""
    from .proto.module import SomeMessage

    message = SomeMessage(value=value)
    cmd = ParallaxCommand.from_protobuf(RVMType.SOMETHING, message)
    return await self.send_parallax_command(vehicle_id, cmd)
```

**Adding New RVM Types:**

1. **Add RVM Type to Enum** (`src/rivian/parallax.py`):
   ```python
   class RVMType(StrEnum):
       # ... existing types
       NEW_FEATURE_SETTING = "domain.service.new_feature_setting"
   ```

2. **Create Protobuf Message** (`src/rivian/proto/new_module.py`):
   ```python
   from google.protobuf import message as _message

   class NewFeatureSetting(_message.Message):
       """New feature setting.

       Attributes:
           param1: Description of param1
           param2: Description of param2
       """

       def __init__(self, param1: str = "", param2: int = 0):
           super().__init__()
           self.param1 = param1
           self.param2 = param2

       def to_dict(self) -> dict:
           """Convert message to dictionary."""
           return {"param1": self.param1, "param2": self.param2}
   ```

3. **Add Helper Function** (`src/rivian/parallax.py`):
   ```python
   def build_new_feature_command(param1: str, param2: int = 0) -> ParallaxCommand:
       """Build new feature command.

       Args:
           param1: Description
           param2: Description

       Returns:
           ParallaxCommand ready to send
       """
       from .proto.new_module import NewFeatureSetting

       setting = NewFeatureSetting(param1=param1, param2=param2)
       return ParallaxCommand.from_protobuf(RVMType.NEW_FEATURE_SETTING, setting)
   ```

4. **Add Method to Rivian Class** (`src/rivian/rivian.py`):
   ```python
   async def set_new_feature(self, vehicle_id: str, param1: str, param2: int = 0) -> dict:
       """Set new feature on vehicle.

       Args:
           vehicle_id: Vehicle VIN
           param1: Description
           param2: Description

       Returns:
           dict with success status and response payload
       """
       cmd = build_new_feature_command(param1, param2)
       return await self.send_parallax_command(vehicle_id, cmd)
   ```

5. **Add Tests** (`tests/test_parallax.py`):
   ```python
   def test_build_new_feature_command(self):
       """Test building new feature command."""
       cmd = build_new_feature_command("test", 123)
       assert cmd.rvm == RVMType.NEW_FEATURE_SETTING
       assert isinstance(cmd.payload_b64, str)

   async def test_set_new_feature(self, aresponses: ResponsesMockServer):
       """Test setting new feature."""
       aresponses.add("rivian.com", "/api/gql/gateway/graphql", "POST",
                      response=PARALLAX_SUCCESS_RESPONSE)

       async with aiohttp.ClientSession():
           rivian = Rivian(csrf_token="token", app_session_token="token",
                          user_session_token="token")
           result = await rivian.set_new_feature("VIN123", "test", 123)
           assert result["success"] is True
           await rivian.close()
   ```

6. **Update Documentation** - Add usage example to README.md

**Testing:**

- **Unit Tests**: `tests/test_parallax.py` (55+ tests)
  - RVMType enum validation
  - ParallaxCommand creation and encoding
  - Helper function behavior
  - Protobuf message serialization
  - Error handling

- **Live Testing**: `examples/parallax_live_data.py`
  - Real vehicle testing with actual credentials
  - Demonstrates all Phase 1 RVM types
  - Shows response payload decoding

- **Mock Pattern**:
  ```python
  PARALLAX_SUCCESS_RESPONSE = {
      "data": {
          "sendParallaxPayload": {
              "__typename": "ParallaxResponse",
              "success": True,
              "sequenceNumber": 42,
              "payload": "CgQIARAB",  # Base64-encoded protobuf response
          }
      }
  }
  ```

**Phase 1 vs Phase 2:**

**Phase 1 (6 RVM types implemented):**
- Charging session live data (RVM #3)
- Charging schedule time window (RVM #16)
- Climate hold setting (RVM #12)
- Climate hold status (RVM #14)
- OTA state (RVM #6)
- Trip progress (RVM #11)

**Phase 2 (12 RVM types pending):**
- Parked energy monitor (RVM #1)
- Charging session chart data (RVM #2)
- Vehicle geofences (RVM #4)
- OTA schedule configuration (RVM #5)
- GearGuard consents (RVM #7)
- GearGuard daily limits (RVM #8)
- Vehicle wheels (RVM #9)
- Trip info (RVM #10)
- Cabin ventilation setting (RVM #13)
- Passive entry setting (RVM #15)
- Passive entry status (RVM #17)
- Halloween settings (RVM #18)

**Key Implementation Notes:**

- RVM type format: `"domain.service.operation"` (e.g., `"comfort.cabin.climate_hold_setting"`)
- Read operations use empty payload (`b""`), write operations use serialized protobuf
- All commands return `dict` with `success`, `sequenceNumber`, and `payload` fields
- Helper functions use `ParallaxCommand.from_protobuf()` for consistency
- Protobuf messages must implement `to_dict()` for debugging
- Test both successful and error responses for each RVM type

**Cross-References:**
- Related to GraphQL Client Architecture (uses DSL for `sendParallaxPayload` mutation)
- Complements BLE commands (cloud vs. proximity-based)
- Uses Protocol Buffers (same library as Gen 2 BLE pairing)
- Error handling via `_handle_gql_error()` (see Error Handling with gql section)

## Code Patterns

### Adding New DSL Mutations

When converting a method to use gql with DSL, follow this pattern:

1. **Update Schema** - Add the mutation/query to `src/rivian/schema.py`:
   ```graphql
   type Mutation {
     yourMutation(arg: String!): YourMutationResponse
   }

   type YourMutationResponse {
     field1: String!
     field2: Boolean
   }
   ```

2. **Update Method** - Follow the standard DSL pattern:
   ```python
   async def your_method(self, arg: str) -> ReturnType:
       """Your method description."""
       # 1. Ensure client is initialized
       client = await self._ensure_client(GRAPHQL_GATEWAY)
       assert self._ds is not None

       # 2. Build DSL mutation
       mutation = dsl_gql(
           DSLMutation(
               self._ds.Mutation.yourMutation.args(arg=arg).select(
                   self._ds.YourMutationResponse.field1,
                   self._ds.YourMutationResponse.field2,
               )
           )
       )

       # 3. Execute with error handling
       try:
           async with async_timeout.timeout(self.request_timeout):
               result = await client.execute_async(mutation)
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

       # 4. Parse and return response
       data = result["yourMutation"]
       return data["field1"]
   ```

3. **Key Points:**
   - Always use `execute_async()` not `execute()` (async context)
   - Use `TransportQueryError` for gql-specific errors
   - `_handle_gql_error()` converts gql exceptions to Rivian exceptions
   - Don't include `__typename` in `.select()` - it's auto-available

### Handling Union Types with DSL

For GraphQL union types (like `LoginResponse`), use `DSLInlineFragment`:

```python
mutation = dsl_gql(
    DSLMutation(
        self._ds.Mutation.login.args(email=username, password=password).select(
            # Use inline fragments for each union member
            DSLInlineFragment().on(self._ds.MobileLoginResponse).select(
                self._ds.MobileLoginResponse.accessToken,
                self._ds.MobileLoginResponse.refreshToken,
            ),
            DSLInlineFragment().on(self._ds.MobileMFALoginResponse).select(
                self._ds.MobileMFALoginResponse.otpToken,
            ),
        )
    )
)
```

**Important:** Don't access union types directly via `self._ds.UnionType` - use `DSLInlineFragment().on(concrete_type)` instead.

### Error Handling with gql

The `_handle_gql_error()` method converts gql `TransportQueryError` exceptions to appropriate Rivian exceptions:

```python
def _handle_gql_error(self, exception: TransportQueryError) -> None:
    """Convert gql errors to Rivian exceptions."""
    errors = exception.errors if hasattr(exception, 'errors') else []

    for error in errors:
        if isinstance(error, dict) and (extensions := error.get("extensions")):
            code = extensions.get("code")
            reason = extensions.get("reason")

            # Check specific combinations (code + reason)
            if (code, reason) == ("BAD_USER_INPUT", "INVALID_OTP"):
                raise RivianInvalidOTP(str(exception))

            # Check generic codes
            if code and (err_cls := ERROR_CODE_CLASS_MAP.get(code)):
                raise err_cls(str(exception))

    # Fallback
    raise RivianApiException(f"Error: {exception}")
```

**When to use DSL vs Legacy:**
- Use **DSL** for new methods with simple return types (void, bool, str, dict)
- Use **Legacy `__graphql_query()`** for methods that must return `ClientResponse`
- The hybrid approach maintains backward compatibility while improving new code

### Adding New Vehicle Commands

1. Add command to `VehicleCommand` enum in `const.py`
2. If command requires parameters, add validation to `_validate_vehicle_command()` in `rivian.py`
3. Commands are sent via `send_vehicle_command()` with automatic HMAC signing

### Adding New State Properties

1. Add to `VEHICLE_STATE_PROPERTIES` (REST API) or `VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES` (WebSocket only) in `const.py`
2. Properties are automatically included in GraphQL fragments via `_build_vehicle_state_fragment()`

### Testing

Tests use `aresponses` to mock HTTP responses. Mock responses are defined in `tests/responses.py`. Pattern:
```python
aresponses.add("rivian.com", "/api/gql/gateway/graphql", "POST", response=MOCK_RESPONSE)
```

**Testing with Static Schema:**
- The static schema in `schema.py` is used for all tests
- No schema introspection occurs during testing
- aresponses mocks work seamlessly with gql's `AIOHTTPTransport`
- The transport creates its own session which aresponses intercepts
- No test modifications needed for DSL vs legacy methods

## Dependencies

### Core Dependencies

**Required:**
- `aiohttp` (>=3.0.0,<=3.12.15) - Async HTTP client (pinned for Home Assistant 2025.10.4 compatibility)
- `attrs` (>=20.3.0,<=25.3.0) - Classes without boilerplate (pinned for Home Assistant 2025.10.4)
- `propcache` (>=0.1.0,<=0.3.2) - Property caching (pinned for Home Assistant 2025.10.4)
- `yarl` (>=1.6.0,<=1.20.1) - URL parsing library (pinned for Home Assistant 2025.10.4)
- `cryptography` (>=41.0.1,<46.0) - Key generation and HMAC signing
- `gql` (^4.0.0) with `[aiohttp, websockets]` extras - GraphQL client with DSL support
  - Provides type-safe query building via DSL
  - AIOHTTPTransport for async HTTP
  - WebSocket support for subscriptions
  - gql v4 is compatible with HA's aiohttp 3.12.15 and provides websockets >=14 for other integrations

**Python Version Compatibility:**
- `backports-strenum` (^1.2.4) - Python <3.11 only (StrEnum backport)
- `async_timeout` - Python <3.11 only (builtin in 3.11+)

**Optional:**
- `bleak` (>=0.21,<2.0.0) - BLE phone pairing support (Gen 1 & Gen 2)
- `dbus-fast` (^2.11.0) - Linux-only, required for BLE

**Core (new):**
- `protobuf` (>=3.20.0,<6.0.0) - Protocol Buffer support for Gen 2 BLE pairing and Parallax cloud protocol

Install with BLE support:
```bash
poetry install --extras ble
```

### Dev Dependencies

- `pytest` + `pytest-asyncio` - Testing framework
- `aresponses` - HTTP response mocking for tests
- `mypy` - Type checking
- `ruff` - Linting and formatting
- `pre-commit` - Git hooks

## Python Version Support

Supports Python 3.9-3.13. Uses conditional imports for compatibility:
- `StrEnum` - stdlib in 3.11+, backport for <3.11
- `async_timeout` - stdlib in 3.11+, package for <3.11

## Breaking Changes in v2.0

### Query Methods Return Types Changed

Four query methods now return structured data (`dict`/`list[dict]`) instead of `ClientResponse`:
- `get_user_information()` → `dict`
- `get_drivers_and_keys(vehicle_id)` → `dict`
- `get_registered_wallboxes()` → `list[dict]`
- `get_vehicle_images()` → `dict[str, list[dict]]`

**Migration:** Remove `.json()` calls and access data directly from the returned dict/list.

### New Authentication Methods

New methods `login()` and `login_with_otp()` replace the legacy flow:
- **Old:** `create_csrf_token()` → `authenticate()` → `validate_otp()`
- **New:** `login()` → `login_with_otp()` (if OTP token returned)

Legacy methods still work but are deprecated.

## Important Notes

- All API methods are async (use `async`/`await`)
- Session tokens expire - handle `RivianUnauthenticated` exceptions
- Vehicle commands return command ID - use `subscribe_for_command_state()` to monitor execution status
- BLE functionality is optional - wrapped in try/except for import
- **BLE pairing supports both Gen 1 and Gen 2 vehicles** with automatic detection
- Gen 2 BLE uses Protocol Buffers, ECDH key derivation, and enhanced HMAC-SHA256
- **Parallax protocol provides cloud-based vehicle commands** - works from anywhere with internet (see [PARALLAX_PROTOCOL.md](PARALLAX_PROTOCOL.md))
- Parallax uses Base64-encoded Protocol Buffers for 18+ RVM (Remote Vehicle Module) types
- GraphQL queries use operation names and Apollo client headers for compatibility
- The gql library v4.0.0 is used for DSL-based methods with a static schema
- Static schema eliminates introspection overhead and simplifies testing
- Dependencies are pinned to be compatible with Home Assistant 2025.10.4
- gql v4 with websockets >=14 is compatible with Home Assistant integrations
