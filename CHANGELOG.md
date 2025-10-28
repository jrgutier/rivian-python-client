# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2025-10-27

### Added

**iOS App Traffic Analysis Implementation**
Based on comprehensive mitmproxy analysis of iOS Rivian App v4400, implemented missing GraphQL operations discovered in live traffic.

**New API Endpoints (3 total)**
- `GRAPHQL_VEHICLE_SERVICES` - Vehicle services endpoint (`https://rivian.com/api/vs/gql-gateway`)
- `GRAPHQL_CONTENT` - Content/chat services endpoint (`https://rivian.com/api/gql/content/graphql`)
- Updated `GRAPHQL_GATEWAY` - Main gateway (existing)

**User & Account Methods (2 operations)**
- `get_referral_code()` - Get user's referral code and shareable URL
- `get_invitations_by_user()` - Get vehicle share invitations received by user

**Vehicle Services Methods (3 operations)** *(uses vs/gql-gateway endpoint)*
- `get_service_appointments(vehicle_id)` - Get scheduled service appointments for vehicle
- `get_active_service_requests(vehicle_id)` - Get active service requests and their status
- `get_vehicle_provisioned_users(vehicle_id)` - Get all users provisioned for vehicle access

**Notification Methods (3 operations)**
- `register_notification_tokens(tokens)` - Register multiple push notification tokens
- `register_push_notification_token(token, platform, vehicle_id)` - Register single push notification
- `register_live_notification_token(vehicle_id, token)` - Register live notification start token

**Content/Chat Methods (1 operation)** *(uses gql/content/graphql endpoint)*
- `get_chat_session(vehicle_id)` - Get customer support chat session information

### Changed

**Client Headers Updated to iOS**
- Changed from Android to iOS user agent: `RivianApp/4400 CFNetwork/1498.700.2 Darwin/23.6.0`
- Updated client name: `com.rivian.ios.consumer` (was `com.rivian.android.consumer`)
- Updated client version: `3.6.0-4400` (was `3.6.0-3989`)
- Added iOS-specific headers: `Accept-Language`, `Accept-Encoding`
- Enhanced `Accept` header with GraphQL defer/stream support

**GraphQL Schema Expanded**
- Added 9 new query operations
- Added 3 new mutation operations
- Added 14 new response types for services, users, notifications, and chat
- Added comprehensive service appointment and request types
- Added notification error handling types

### Documentation

- Created `MITM_API_AUDIT.md` - Comprehensive analysis of iOS app traffic vs Python client
- Created `MITM_UPDATES.md` - Summary of changes made from traffic analysis
- Created `websocket_logger.py` - mitmproxy addon for WebSocket message capture

## [2.1.0] - 2025-10-26

### Added

**Charging Management (4 operations)**
- `get_charging_schedules(vehicle_id)` - Retrieve configured departure/charging schedules
- `update_departure_schedule(vehicle_id, schedule)` - Create or update departure schedules with cabin preconditioning and charging targets
- `enroll_in_smart_charging(vehicle_id)` - Enable Rivian's smart charging for optimal charging times
- `unenroll_from_smart_charging(vehicle_id)` - Disable smart charging

**Location Sharing (2 operations)**
- `share_location_to_vehicle(vehicle_id, latitude, longitude)` - Send GPS coordinates to vehicle navigation
- `share_place_id_to_vehicle(vehicle_id, place_id)` - Send Google Place ID to vehicle navigation

**Trailer Management (2 operations)**
- `get_trailer_profiles(vehicle_id)` - Get configured trailer profiles for R1T
- `update_pin_to_gear(vehicle_id, trailer_id, pinned)` - Pin/unpin trailer to Gear Guard

**Trip Planning (4 operations)**
- `plan_trip_with_multi_stop(vehicle_id, waypoints, options)` - Plan multi-stop trips with automatic charging stop insertion
- `save_trip_plan(trip_id, name)` - Save planned trips for future reference
- `update_trip(trip_id, updates)` - Update saved trip plans
- `delete_trip(trip_id)` - Delete saved trips

**Advanced Key Management (4 operations)**
- `create_signing_challenge(vehicle_id, device_id)` - Create cryptographic challenges for CCC digital key authentication
- `verify_signing_challenge(vehicle_id, device_id, challenge_id, signature)` - Verify CCC challenge responses
- `enable_ccc(vehicle_id, device_id)` - Enable Car Connectivity Consortium digital key support
- `upgrade_key_to_wcc2(vehicle_id, device_id)` - Upgrade to WCC 2.0 (Wireless Car Connectivity) standard

**Gear Guard**
- `subscribe_for_gear_guard_config(vehicle_id, callback)` - Subscribe to Gear Guard remote configuration updates

**Vehicle State Properties**
- Added 6 new connectivity properties to `VEHICLE_STATE_PROPERTIES`:
  - `wifiSsid`, `wifiSignalStrength`, `wifiAntennaBars`
  - `cellularSignalStrength`, `cellularAntennaBars`, `cellularCarrier`

### Changed

- **Expanded GraphQL schema** with 17 new operations and 27 new types
- **All new methods use gql DSL pattern** for consistency with v2.0 architecture
- Added comprehensive validation for departure schedules and GPS coordinates

### Technical Details

- Added 20 new GraphQL operations across all 3 phases (charging, features, advanced)
- Comprehensive schema expansion (430+ new lines)
- All operations follow established DSL pattern with proper error handling
- Full type safety with mypy-validated type hints
- 100% test coverage for all new operations

---

## [2.2.0] - 2025-10-26

### Added

**Parallax Protocol - Cloud-Based Vehicle Commands**

The Parallax Protocol provides direct access to vehicle Remote Vehicle Module (RVM) commands through cloud GraphQL, complementing the existing BLE-based control. This enables remote vehicle operations without requiring Bluetooth proximity.

**6 Phase 1 Parallax Methods:**
- `get_charging_session_live_data(vehicle_id)` - Real-time charging metrics (power, current, voltage, energy added, SOC, time remaining)
- `get_climate_hold_status(vehicle_id)` - Current cabin climate hold state (temperature, duration, defrost settings)
- `get_ota_status(vehicle_id)` - Software update status (installed version, available updates, download progress)
- `get_trip_progress(vehicle_id)` - Active navigation progress (destination, ETA, distance, traffic alerts)
- `set_climate_hold(vehicle_id, temperature_celsius, duration_minutes, defrost_defog)` - Configure cabin climate (16-29°C, up to 30 minutes)
- `set_charging_schedule(vehicle_id, schedules)` - Set up to 5 charging time windows with days of week
- `send_parallax_command(vehicle_id, command, payload)` - Low-level RVM command access for advanced use cases

**18 Enumerated RVM Types:**
- Phase 1 (implemented): `CHARGING_SESSION_LIVE_DATA`, `CLIMATE_HOLD_STATUS`, `OTA_STATUS`, `TRIP_PROGRESS`, `SET_CLIMATE_HOLD`, `SET_CHARGING_SCHEDULE`
- Phase 2 (ready): `GET_CHARGING_SCHEDULE`, `GET_VEHICLE_DATA`, `REMOTE_CHARGING_START`, `REMOTE_CHARGING_STOP`, `REMOTE_CLIMATE_START`, `REMOTE_CLIMATE_STOP`, `REMOTE_DOOR_LOCK`, `REMOTE_DOOR_UNLOCK`, `REMOTE_TRUNK_OPEN`, `REMOTE_FRUNK_OPEN`, `REMOTE_HONK_LIGHTS`, `REMOTE_PANIC_ON`

**Protocol Buffer Infrastructure:**
- 13 Protocol Buffer message classes for Parallax data structures:
  - `ChargingSessionLiveData`, `ChargingSchedule`, `ChargingWindow`
  - `ClimateHoldStatus`, `SetClimateHold`
  - `OTAStatus`, `OTAUpdate`
  - `TripProgress`, `Waypoint`, `TrafficAlert`
  - `SetChargingSchedule`, `TimeWindow`, `DayOfWeek`
- Hand-crafted wire format serialization (no .proto files required)
- Base64 payload encoding for GraphQL transport
- Bidirectional: encode commands for sending, decode responses from vehicle

**New Exports:**
- `ParallaxCommand` enum - Type-safe command identifiers
- `RVMType` enum - Remote Vehicle Module type identifiers
- Both available via `from rivian import ParallaxCommand, RVMType`

**Documentation:**
- `PARALLAX_PROTOCOL.md` - Complete protocol specification with implementation guide
- `BLE_UUIDS_REFERENCE.md` - Comprehensive BLE UUID catalog (Gen 1 & Gen 2)
- `KEY_FOB_V2.md` - Key fob integration protocol documentation
- `examples/parallax_live_data.py` - Live data retrieval script

**Testing:**
- 55 comprehensive tests covering all Parallax operations
- Protocol Buffer encoding/decoding validation
- Error handling and edge case coverage
- Mock GraphQL responses for all RVM types

### Changed

- **GraphQL schema expanded** with `sendParallaxPayload` mutation and supporting types
- **Architecture now supports three command paths**:
  1. Traditional REST API commands (legacy)
  2. BLE direct vehicle commands (Gen 1 & Gen 2)
  3. Parallax cloud-based RVM commands (new)

### Technical Details

**Protocol Implementation:**
- GraphQL mutation: `sendParallaxPayload(vehicleId, commandType, payload)`
- Payload format: Base64-encoded Protocol Buffer messages
- Response handling: Automatic protobuf deserialization
- Error codes: `VEHICLE_NOT_FOUND`, `INVALID_PAYLOAD`, `COMMAND_FAILED`, `TIMEOUT`

**Parallax Command Pipeline:**
1. Build Protocol Buffer message (e.g., `SetClimateHold`)
2. Serialize to wire format bytes
3. Base64 encode for GraphQL transport
4. Send via `sendParallaxPayload` mutation
5. Receive and decode response payload
6. Parse Protocol Buffer response structure

**Phase 2 Roadmap (12 RVM types ready):**
- Charging control: Start/stop, schedules retrieval
- Climate control: Start/stop remote conditioning
- Lock/unlock: Door, trunk, frunk operations
- Alert commands: Honk/lights, panic mode
- Vehicle data: Comprehensive state retrieval

### Dependencies

**New Required Dependency:**
- `protobuf` (>=3.20.0,<6.0.0) - Protocol Buffer support for Parallax message serialization

**Installation:**
```bash
poetry install  # Includes protobuf automatically
```

### Migration Notes

**Importing New Types:**
```python
from rivian import Rivian, ParallaxCommand, RVMType

# Phase 1 example: Set cabin climate via cloud
await client.set_climate_hold(
    vehicle_id="...",
    temperature_celsius=21.0,
    duration_minutes=15,
    defrost_defog=False
)

# Low-level access
from rivian.parallax_proto import SetClimateHold
command = SetClimateHold(temperature_celsius=21.0, duration_minutes=15)
await client.send_parallax_command(vehicle_id, RVMType.SET_CLIMATE_HOLD, command)
```

**Parallax vs BLE Commands:**
- **Parallax**: Cloud-based, works from anywhere, requires internet, ~1-3s latency
- **BLE**: Direct vehicle connection, requires proximity (<30ft), <500ms latency
- Use Parallax for remote operations, BLE for local/instant commands

---

## [2.0.0] - 2025-10-26

### Breaking Changes

- **Changed return types for query methods** (now return `dict`/`list[dict]` instead of `ClientResponse`):
  - `get_user_information()` - Returns `dict` with user info, vehicles, and optionally enrolled phones
  - `get_drivers_and_keys(vehicle_id)` - Returns `dict` with vehicle data including invited users/devices
  - `get_registered_wallboxes()` - Returns `list[dict]` of wallbox details (empty list if none registered)
  - `get_vehicle_images()` - Returns `dict[str, list[dict]]` with mobile and pre-order images

  **Migration:** Remove `.json()` calls and access data directly:
  ```python
  # Before (v1.x)
  response = await client.get_user_information()
  data = await response.json()
  user = data["data"]["currentUser"]

  # After (v2.0)
  user = await client.get_user_information()
  # Access user dict directly, no .json() needed
  ```

### Added

- **New authentication methods** matching Rivian Android app flow:
  - `login(username, password)` - Simplified login, returns OTP token if MFA required
  - `login_with_otp(username, otp_code, otp_token)` - Complete OTP validation

  These provide a cleaner API than the legacy `create_csrf_token()` → `authenticate()` → `validate_otp()` flow.

- **Comprehensive GraphQL schema** in `schema.py`:
  - All query types (`Query`, `Mutation`, `Subscription`)
  - Full type definitions for user info, vehicles, wallboxes, images, etc.
  - Enables type-safe DSL query building for all migrated methods

### Changed

- **All query methods now use gql DSL** for better type safety and error handling
- **Legacy auth methods deprecated** (but still functional):
  - `create_csrf_token()` - Use `login()` instead
  - `authenticate()` - Use `login()` instead
  - `validate_otp()` - Use `login_with_otp()` instead

### Technical Details

- Migrated from legacy `__graphql_query()` to gql v3.5.3 with DSL
- Static schema eliminates introspection overhead
- Better error handling through `TransportQueryError` conversion
- Maintains backward compatibility for non-migrated methods

### Migration Guide

See README.md for detailed migration examples and patterns for updating from v1.x to v2.0.

---

## [1.x.x] - Previous Versions

See git history for changes in 1.x releases.
