# Python: Rivian API Client

Unofficial asynchronous Python client library for the Rivian API. Provides GraphQL-based access to vehicle state, commands, and charging data for Rivian vehicles (R1T/R1S).

## Features

- **Authentication**: Username/password login with OTP support
- **Vehicle State**: Real-time vehicle data via WebSocket subscriptions
- **Vehicle Commands**: Remote control (lock/unlock, climate, charging, etc.)
- **Phone Enrollment**: BLE pairing for both Gen 1 and Gen 2 vehicles
- **Charging**: Live charging session data, wallbox management, and smart charging schedules (v2.1+)
- **User Management**: Access user info, shared drivers, and vehicle images
- **Location Sharing**: Send destinations to vehicle navigation (v2.1+)
- **Trip Planning**: Multi-stop trip planning with charging stops (v2.1+)
- **Trailer Management**: Manage trailer profiles for R1T (v2.1+)
- **Advanced Key Management**: CCC/WCC2 digital key support (v2.1+)
- **Type-Safe**: Built with gql DSL for GraphQL queries with comprehensive schema

## Installation

### Basic Installation

```bash
pip install rivian-python-client
```

### With BLE Support (for phone pairing)

```bash
pip install rivian-python-client[ble]
```

## Quick Start

### Authentication

```python
from rivian import Rivian

async with Rivian() as client:
    # Simple login (returns OTP token if MFA is enabled)
    otp_token = await client.login("user@example.com", "password")

    # If OTP required, validate it
    if otp_token:
        await client.login_with_otp("user@example.com", "123456", otp_token)
```

### Getting User Information

```python
# Get user info with vehicles (v2.0+ returns dict directly)
user_info = await client.get_user_information()
print(f"User ID: {user_info['id']}")
for vehicle in user_info['vehicles']:
    print(f"Vehicle: {vehicle['name']} ({vehicle['vin']})")

# Include enrolled phones
user_info = await client.get_user_information(include_phones=True)
for phone in user_info.get('enrolledPhones', []):
    print(f"Phone ID: {phone['vas']['vasPhoneId']}")
```

### Getting Vehicle Data

```python
# Get drivers and keys for a vehicle
drivers = await client.get_drivers_and_keys(vehicle_id)
print(f"VIN: {drivers['vin']}")
for user in drivers['invitedUsers']:
    print(f"User: {user.get('email')} - Devices: {len(user.get('devices', []))}")

# Get vehicle images
images = await client.get_vehicle_images(extension="png", resolution="@2x")
for img in images['getVehicleMobileImages']:
    print(f"Image: {img['url']}")
```

### Wallbox Management

```python
# Get registered wallboxes
wallboxes = await client.get_registered_wallboxes()
for wallbox in wallboxes:
    print(f"Wallbox: {wallbox['name']} - Status: {wallbox['chargingStatus']}")
```

### Real-Time Vehicle Updates (WebSocket)

```python
from rivian.const import VEHICLE_STATE_PROPERTIES

# Subscribe to vehicle state updates
async for update in client.subscribe_for_vehicle_updates(
    vehicle_id=vehicle_id,
    properties=VEHICLE_STATE_PROPERTIES
):
    print(f"Battery: {update['batteryLevel']['value']}%")
    print(f"Range: {update['distanceToEmpty']['value']} miles")
```

### Sending Vehicle Commands

```python
from rivian import VehicleCommand

# Unlock vehicle
command_id = await client.send_vehicle_command(
    vehicle_id=vehicle_id,
    command=VehicleCommand.UNLOCK_ALL_CLOSURES
)

# Monitor command status via WebSocket
async for state in client.subscribe_for_command_state(command_id):
    print(f"Command state: {state['state']}")
    if state['state'] in ['COMPLETE', 'FAILED']:
        break
```

## New in v2.1

### Charging Schedule Management

```python
# Get charging schedules
schedules = await client.get_charging_schedules(vehicle_id)
for schedule in schedules['schedules']:
    print(f"{schedule['name']}: {schedule['departureTime']} on {schedule['days']}")

# Create/update departure schedule
schedule = await client.update_departure_schedule(
    vehicle_id=vehicle_id,
    schedule={
        "name": "Weekday Commute",
        "enabled": True,
        "days": ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"],
        "departureTime": "08:00",
        "cabinPreconditioning": True,
        "cabinPreconditioningTemp": 21.0,
        "targetSOC": 80
    }
)

# Enable/disable smart charging
await client.enroll_in_smart_charging(vehicle_id)
await client.unenroll_from_smart_charging(vehicle_id)
```

### Location Sharing

```python
# Share GPS coordinates
result = await client.share_location_to_vehicle(
    vehicle_id=vehicle_id,
    latitude=37.7749,
    longitude=-122.4194
)

# Share Google Place
result = await client.share_place_id_to_vehicle(
    vehicle_id=vehicle_id,
    place_id="ChIJN1t_tDeuEmsRUsoyG83frY4"
)
```

### Trip Planning

```python
# Plan multi-stop trip with charging
trip = await client.plan_trip_with_multi_stop(
    vehicle_id=vehicle_id,
    waypoints=[
        {"latitude": 37.7749, "longitude": -122.4194, "name": "San Francisco"},
        {"latitude": 34.0522, "longitude": -118.2437, "name": "Los Angeles"}
    ],
    options={
        "avoidTolls": False,
        "targetArrivalSOC": 20
    }
)
print(f"Trip: {trip['totalDistance']} miles, {trip['totalDuration']} minutes")
for stop in trip['chargingStops']:
    print(f"Charging stop: {stop['location']['name']}")
```

### Trailer Management (R1T)

```python
# Get trailer profiles
trailers = await client.get_trailer_profiles(vehicle_id)
for trailer in trailers:
    print(f"{trailer['name']}: {trailer['length']}m, pinned={trailer['pinnedToGear']}")

# Pin/unpin trailer to gear
await client.update_pin_to_gear(vehicle_id, trailer_id, pinned=True)
```

### Gear Guard Monitoring

```python
# Subscribe to Gear Guard config updates
def on_config_update(config):
    print(f"Gear Guard: {config['videoMode']}, storage={config['storageRemaining']}%")

unsubscribe = await client.subscribe_for_gear_guard_config(vehicle_id, on_config_update)
```

## Migration from v1.x to v2.0

### Breaking Changes

#### 1. Query Methods Return Types Changed

Query methods now return `dict`/`list[dict]` directly instead of `ClientResponse`. No need to call `.json()`.

**Before (v1.x):**
```python
response = await client.get_user_information()
data = await response.json()
user = data["data"]["currentUser"]
vehicles = user["vehicles"]
```

**After (v2.0):**
```python
user = await client.get_user_information()
# Returns dict directly - no .json() needed
vehicles = user["vehicles"]
```

**Affected Methods:**
- `get_user_information()` - Returns `dict`
- `get_drivers_and_keys(vehicle_id)` - Returns `dict`
- `get_registered_wallboxes()` - Returns `list[dict]`
- `get_vehicle_images()` - Returns `dict[str, list[dict]]`

#### 2. New Authentication Methods (Recommended)

The new `login()` and `login_with_otp()` methods provide a simpler authentication flow.

**Before (v1.x):**
```python
await client.create_csrf_token()
await client.authenticate(username, password)
if client._otp_needed:
    await client.validate_otp(username, otp_code)
```

**After (v2.0 - Recommended):**
```python
otp_token = await client.login(username, password)
if otp_token:
    await client.login_with_otp(username, otp_code, otp_token)
```

**Note:** Legacy auth methods (`create_csrf_token()`, `authenticate()`, `validate_otp()`) still work but are deprecated.

### Non-Breaking Changes

Methods that still return `ClientResponse` (unchanged):
- `get_vehicle_state(vin)` - Use WebSocket subscriptions for real-time data
- `get_vehicle_command_state(command_id)` - Use `subscribe_for_command_state()` instead
- `get_live_charging_session(vin)` - Use `subscribe_for_charging_session()` instead
- `get_vehicle_ota_update_details(vehicle_id)`

## Dependencies

[Poetry](https://python-poetry.org/docs/) is used for dependency management.

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

## Development Setup

Install project dependencies into the poetry virtual environment and setup pre-commit hooks:

```bash
poetry install
pre-commit install
```

### With BLE Support

```bash
poetry install --extras ble
```

## Running Tests

```bash
poetry run pytest
```

### Run Specific Tests

```bash
# Specific test file
poetry run pytest tests/rivian_test.py

# Specific test function
poetry run pytest tests/rivian_test.py::test_authentication
```

## Linting & Formatting

```bash
# Run ruff linter with auto-fix
poetry run ruff check --fix

# Run ruff formatter
poetry run ruff format

# Run type checking
poetry run mypy src/rivian
```

Pre-commit hooks automatically run `ruff` (linter with --fix) and `ruff-format` on staged files.

## Python Version Support

- Python 3.9+
- Full support for Python 3.9 - 3.13
- Uses conditional imports for version-specific features

## License

MIT License - See LICENSE file for details

## Disclaimer

This is an unofficial client library and is not affiliated with, endorsed by, or connected to Rivian Automotive, LLC. Use at your own risk.

## Contributing

Contributions are welcome! Please open an issue or pull request for bug fixes, features, or documentation improvements.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history and migration guides.
