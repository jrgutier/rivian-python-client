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

1. **gql with DSL** (6 methods) - Type-safe queries using the `gql` library v4.0.0
   - Used for methods with simple return types (void, bool, str)
   - Static schema defined in `schema.py` (not introspected)
   - Type-safe query building via DSL (Domain Specific Language)
   - Better error handling and validation

2. **Legacy `__graphql_query()`** (15+ methods) - Direct GraphQL string execution
   - Used for methods returning `ClientResponse` objects
   - Maintains backward compatibility with existing API
   - Used for most query methods (get_vehicle_state, get_user_information, etc.)

**Static Schema:** The GraphQL schema is statically defined in `src/rivian/schema.py` rather than fetched via introspection. This approach:
- Eliminates network overhead from schema introspection
- Makes testing easier (no need to mock schema fetch)
- Provides faster initialization
- Only includes types/mutations actually used by DSL methods

**Methods Using DSL:**
- `create_csrf_token()` - Returns None (void)
- `authenticate()` - Returns None (void)
- `validate_otp()` - Returns None (void)
- `disenroll_phone()` - Returns bool
- `enroll_phone()` - Returns bool
- `send_vehicle_command()` - Returns str | None

**Methods Using Legacy `__graphql_query()`:**
- All methods returning `ClientResponse` (queries and some mutations)
- Examples: `get_vehicle_state()`, `get_user_information()`, `get_registered_wallboxes()`, etc.

**`schema.py`** - Static GraphQL schema definition
- Minimal schema containing only types used by DSL methods
- Includes mutations: createCsrfToken, login, loginWithOTP, enrollPhone, disenrollPhone, sendVehicleCommand
- Used to avoid schema introspection overhead
- Updated when new DSL methods are added

**`const.py`** - Constants and enums
- `VehicleCommand` enum - All supported vehicle commands
- `VEHICLE_STATE_PROPERTIES` - Properties available via REST API
- `VEHICLE_STATES_SUBSCRIPTION_ONLY_PROPERTIES` - Properties only available via WebSocket
- `LIVE_SESSION_PROPERTIES` - Charging session properties

**`utils.py`** - Cryptographic utilities
- `generate_key_pair()` - Creates ECDSA key pairs for phone enrollment
- HMAC generation for vehicle commands using ECDH shared secret
- Key encoding/decoding helpers

**`ble.py`** - Bluetooth Low Energy phone pairing
- Pairs enrolled phones with vehicle locally via BLE
- Required for vehicle control after phone enrollment
- Optional dependency (requires `bleak` package)

**`ws_monitor.py`** - WebSocket connection manager
- Maintains persistent WebSocket connections
- Handles subscription lifecycle
- Auto-reconnection logic

**`exceptions.py`** - Custom exception hierarchy
- Maps GraphQL error codes to specific exceptions
- Rate limiting, authentication, and validation errors

### Authentication Flow

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

### Vehicle State Access

Two methods for retrieving state:
- **REST API**: `get_vehicle_state()` - On-demand queries with property filtering
- **WebSocket**: `subscribe_for_vehicle_updates()` - Real-time push updates

Properties are defined in `const.py` - some are subscription-only and will be filtered out from REST queries.

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
- `bleak` (>=0.21,<2.0.0) - BLE phone pairing support
- `dbus-fast` (^2.11.0) - Linux-only, required for BLE

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

## Important Notes

- All API methods are async (use `async`/`await`)
- Session tokens expire - handle `RivianUnauthenticated` exceptions
- Vehicle commands return command ID - use `get_vehicle_command_state()` to check execution status
- BLE functionality is optional - wrapped in try/except for import
- GraphQL queries use operation names and Apollo client headers for compatibility
- The gql library v4.0.0 is used for DSL-based methods with a static schema
- Static schema eliminates introspection overhead and simplifies testing
- Dependencies are pinned to be compatible with Home Assistant 2025.10.4
- gql v4 requires websockets >=14 which satisfies other Home Assistant integrations
