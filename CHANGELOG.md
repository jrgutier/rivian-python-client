# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
