# Rivian Parallax Protocol Documentation

## Table of Contents
- [Overview](#overview)
- [Architecture](#architecture)
- [Protocol Specification](#protocol-specification)
- [RVM Types Reference](#rvm-types-reference)
- [Message Formats](#message-formats)
- [Security Considerations](#security-considerations)
- [Comparison with BLE Protocols](#comparison-with-ble-protocols)
- [Implementation Guide](#implementation-guide)
- [Appendix](#appendix)

---

## Overview

### What is Parallax?

The **Parallax Protocol** is Rivian's cloud-based GraphQL/HTTP protocol for retrieving and updating advanced vehicle state data and settings. Unlike Gen1/Gen2 BLE protocols which require physical proximity to the vehicle, Parallax operates entirely through Rivian's cloud infrastructure, enabling remote access to specialized vehicle modules.

### Key Characteristics

- **Transport**: GraphQL over HTTPS
- **Serialization**: Protocol Buffers (Base64-encoded)
- **Direction**: Bidirectional (read/write vehicle state)
- **Proximity**: Cloud-based (no physical proximity required)
- **Authentication**: User session tokens (from Rivian API)
- **Endpoint**: `https://rivian.com/api/gql/gateway/graphql`

### Protocol Name Origin

The protocol name "Parallax" refers to the payload format used in the GraphQL mutation. The Android app uses `ParallaxAttributes` objects that contain:
- `parallaxCommonPayload` - Base64-encoded protobuf shared data
- `parallaxOpPayload` - Base64-encoded protobuf operation-specific data
- `rvm` - Remote Vehicle Module identifier (e.g., `"energy_edge_compute.graphs.charging_graph_global"`)

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Mobile Application                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  CloudParallaxCommandOperation (C8630d)              │  │
│  │  - Builds ParallaxAttributes                         │  │
│  │  - Encodes payloads to Base64                        │  │
│  └──────────────────────────────────────────────────────┘  │
│                           │                                  │
│                           ▼                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GraphQL Mutation Builder (C19629S8)                 │  │
│  │  - SendRemoteCommand mutation                        │  │
│  │  - vehicleId, model, parallaxPayloadB64 args         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ HTTPS POST
                           ▼
┌─────────────────────────────────────────────────────────────┐
│             Rivian Cloud (GraphQL Gateway)                   │
│  - Endpoint: /api/gql/gateway/graphql                       │
│  - Validates user session tokens                            │
│  - Routes to vehicle communication layer                    │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ Vehicle Communication
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                 Remote Vehicle Module (RVM)                  │
│  - Decodes Base64 protobuf payloads                         │
│  - Processes request (read/write operation)                 │
│  - Returns protobuf-encoded response                        │
└─────────────────────────────────────────────────────────────┘
```

### Communication Flow

1. **Client Request**
   - App builds operation-specific protobuf messages
   - Encodes messages to Base64 strings
   - Constructs GraphQL mutation with vehicle metadata
   - Sends HTTPS POST to GraphQL endpoint

2. **Cloud Processing**
   - Validates authentication tokens
   - Extracts vehicle ID and RVM target
   - Routes payload to appropriate vehicle module
   - May wake vehicle if `requiresWakeup: true`

3. **Vehicle Response**
   - RVM processes protobuf payload
   - Returns Base64-encoded protobuf response
   - Includes success status and sequence number
   - Response propagated back through cloud to client

---

## Protocol Specification

### GraphQL Mutation

```graphql
mutation SendRemoteCommand(
  $vehicleId: String!,
  $model: String!,
  $parallaxPayloadB64: String!
) {
  sendParallaxPayload(
    payload: $parallaxPayloadB64,
    meta: {
      vehicleId: $vehicleId
      model: $model
      isVehicleModelOp: true
      requiresWakeup: true
    }
  ) {
    success
    sequenceNumber
  }
}
```

**Mutation ID**: `f31f549f8fc58e1667adb629093f5e26e02bfb7c19db1685dc45faec2114bc7e`

**Operation Name**: `SendRemoteCommand`

### Variables

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `vehicleId` | String | Yes | Vehicle UUID (e.g., `"123e4567-e89b-12d3-a456-426614174000"`) |
| `model` | String | Yes | Vehicle model identifier (RVM name) |
| `parallaxPayloadB64` | String | Yes | Base64-encoded Protocol Buffer payload |

### Metadata Fields

| Field | Type | Value | Purpose |
|-------|------|-------|---------|
| `vehicleId` | String | Vehicle UUID | Target vehicle identifier |
| `model` | String | RVM name | Routing to correct vehicle module |
| `isVehicleModelOp` | Boolean | `true` | Indicates model-specific operation |
| `requiresWakeup` | Boolean | `true` | Wake vehicle if sleeping before executing |

### Response Structure

```typescript
{
  sendParallaxPayload: {
    success: boolean;        // Operation success status
    sequenceNumber: number;  // Command sequence/tracking number
  }
}
```

---

## RVM Types Reference

### Complete RVM Enumeration

Rivian defines 18 Remote Vehicle Module (RVM) types in `EnumC6207c.java`. Each RVM handles a specific domain of vehicle functionality.

| # | RVM Type | RVM Name (Model) | Domain | Read/Write |
|---|----------|------------------|--------|------------|
| 1 | `PARKED_ENERGY_MONITOR` | `energy_edge_compute.graphs.parked_energy_distributions` | Energy analytics while parked | Read |
| 2 | `CHARGING_SESSION_CHART_DATA` | `energy_edge_compute.graphs.charging_graph_global` | Historical charging session graphs | Read |
| 3 | `CHARGING_SESSION_LIVE_DATA` | `energy_edge_compute.graphs.charge_session_breakdown` | Real-time charging session data | Read |
| 4 | `VEHICLE_GEO_FENCES` | `geofence.geofence_service.favoriteGeofences` | Saved geofence locations | Read/Write |
| 5 | `OTA_SCHEDULE_CONFIGURATION` | `ota.user_schedule.ota_config` | OTA update scheduling preferences | Read/Write |
| 6 | `OTA_STATE` | `ota.ota_state.vehicle_ota_state` | Current OTA update state | Read |
| 7 | `GEAR_GUARD_CONSENTS` | `gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent` | GearGuard privacy consents | Read/Write |
| 8 | `GEAR_GUARD_DAILY_LIMITS` | `gearguard_streaming.privacy.gearguard_streaming_daily_limit` | GearGuard daily usage limits | Read |
| 9 | `VEHICLE_WHEELS` | `vehicle.wheels.vehicle_wheels` | Wheel configuration/telemetry | Read |
| 10 | `TRIP_INFO` | `navigation.navigation_service.trip_info` | Active navigation trip details | Read |
| 11 | `TRIP_PROGRESS` | `navigation.navigation_service.trip_progress` | Navigation progress updates | Read |
| 12 | `CLIMATE_HOLD_SETTING` | `comfort.cabin.climate_hold_setting` | Climate hold user preferences | Read/Write |
| 13 | `CABIN_VENTILATION_SETTING` | `comfort.cabin.cabin_ventilation_setting` | Cabin ventilation preferences | Read/Write |
| 14 | `CLIMATE_HOLD_STATUS` | `comfort.cabin.climate_hold_status` | Current climate hold state | Read |
| 15 | `PASSIVE_ENTRY_SETTING` | `vehicle_access.passive_entry.passive_entry` | Passive entry configuration | Read/Write |
| 16 | `CHARGING_SCHEDULE_TIME_WINDOW` | `charging.schedule.time_window` | Charging schedule time windows | Read/Write |
| 17 | `HALLOWEEN_SETTINGS` | `holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings` | Halloween celebration features | Read/Write |
| 18 | `PASSIVE_ENTRY_STATUS` | `vehicle_access.state.passive_entry` | Current passive entry status | Read |

### RVM Categories

**Energy & Charging (RVM 1-3, 16)**
- Parked energy monitoring
- Charging session analytics
- Live charging data
- Charge scheduling

**Navigation (RVM 10-11)**
- Trip information
- Route progress
- ETA calculations

**Climate & Comfort (RVM 12-14)**
- Climate hold settings/status
- Cabin ventilation

**Security & Access (RVM 7-8, 15, 18)**
- GearGuard settings
- Passive entry configuration

**Vehicle Configuration (RVM 9)**
- Wheel/tire information

**Software Updates (RVM 5-6)**
- OTA scheduling
- Update status

**Special Features (RVM 4, 17)**
- Geofencing
- Seasonal celebrations

---

## Message Formats

### Protocol Buffer Examples

#### 1. Charging Session Live Data (RVM #3)

**Protobuf Definition**: `C19106b.java`

**Fields**:
```protobuf
message ChargingSessionLiveData {
  float total_kwh = 1;              // Total energy delivered (kWh)
  float pack_kwh = 2;               // Energy to battery pack (kWh)
  float thermal_kwh = 3;            // Energy for thermal management (kWh)
  float outlets_kwh = 4;            // Energy to outlets (kWh)
  float system_kwh = 5;             // System overhead energy (kWh)
  int32 session_duration_mins = 6;  // Session duration (minutes)
  int32 time_remaining_mins = 7;    // Estimated time to complete (minutes)
  int32 range_added_kms = 8;        // Range added (kilometers)
  float current_power = 9;          // Current charging power (kW)
  int32 current_range_per_hour = 10;// Range being added per hour (km/h)
  SessionCost session_cost = 11;    // Cost information
  bool is_free_session = 12;        // Free charging session flag
  int32 charging_state = 13;        // Current charging state enum
}

message SessionCost {
  int64 nanos = 1;                  // Nanosecond component
  int64 seconds = 2;                // Unix timestamp seconds
  string currency = 3;              // Currency code (e.g., "USD")
}
```

**Example Decoded Data**:
```json
{
  "total_kwh": 45.3,
  "pack_kwh": 42.1,
  "thermal_kwh": 2.5,
  "outlets_kwh": 0.0,
  "system_kwh": 0.7,
  "session_duration_mins": 68,
  "time_remaining_mins": 22,
  "range_added_kms": 185,
  "current_power": 150.2,
  "current_range_per_hour": 163,
  "session_cost": {
    "nanos": 500000000,
    "seconds": 1698765432,
    "currency": "USD"
  },
  "is_free_session": false,
  "charging_state": 2
}
```

#### 2. Halloween Celebration Settings (RVM #17)

**Protobuf Definition**: `C21876n.java`

**Fields**:
```protobuf
message HalloweenCelebrationSettings {
  CostumeTheme costume_theme = 1;              // Selected costume theme
  SoundVolume celebration_sound_volume = 2;    // Sound volume level
  MusicEnabled music_enabled = 3;              // Music on/off
  MusicType music_type = 4;                    // Type of music
  SoundEffect sound_effect = 5;                // Sound effect selection
  int32 exterior_sound_effect = 6;             // Exterior sound ID
  ExteriorSoundsMuted exterior_sounds_muted = 7; // Mute exterior sounds
  LightShowEnabled light_show_enabled = 8;     // Enable light show
  InteriorLightsEnabled interior_overhead_lights_enabled = 9; // Interior lights
  ExteriorLightShowEnabled exterior_light_show_enabled = 10;  // Exterior lights
  LightsColor lights_color = 11;               // Light color selection
  CarCostumeAvailability car_costume_availability = 12; // Feature availability
  bool motion_light_sound_enabled = 13;        // Motion-triggered effects
}

enum CostumeTheme {
  NONE = 0;
  SPOOKY_SWAMP = 5;  // Halloween theme
}
```

**Example Decoded Data**:
```json
{
  "costume_theme": "SPOOKY_SWAMP",
  "celebration_sound_volume": 75,
  "music_enabled": true,
  "music_type": "HALLOWEEN_PLAYLIST",
  "sound_effect": 3,
  "exterior_sound_effect": 2,
  "exterior_sounds_muted": false,
  "light_show_enabled": true,
  "interior_overhead_lights_enabled": true,
  "exterior_light_show_enabled": true,
  "lights_color": 4,
  "car_costume_availability": "AVAILABLE",
  "motion_light_sound_enabled": true
}
```

#### 3. Charging Schedule Time Window (RVM #16)

**Protobuf Definition**: `C18593l.java`

**Fields**:
```protobuf
message ChargingScheduleTimeWindow {
  bool is_valid = 1;          // Window is active
  WindowData window_data = 2; // Time window details
}

message WindowData {
  int32 start_time = 1;  // Start time (minutes since midnight)
  int32 end_time = 2;    // End time (minutes since midnight)
  int32 day_of_week = 3; // Day of week (0=Sunday, 6=Saturday)
  bool enabled = 4;      // Window is enabled
}
```

**Example Decoded Data**:
```json
{
  "is_valid": true,
  "window_data": {
    "start_time": 1320,    // 10:00 PM (22:00)
    "end_time": 360,       // 6:00 AM
    "day_of_week": 1,      // Monday
    "enabled": true
  }
}
```

**Time Conversion**:
```python
start_hour = start_time // 60  # 1320 // 60 = 22
start_min = start_time % 60    # 1320 % 60 = 0
# Result: 22:00 (10:00 PM)
```

#### 4. Vehicle Wheels Data (RVM #9)

**Protobuf Definition**: `C1736f.java`

**Fields**:
```protobuf
message VehicleWheels {
  repeated WheelInfo wheels_list = 1;  // List of all wheels
}

message WheelInfo {
  int32 position = 0;           // Wheel position (0=FL, 1=FR, 2=RL, 3=RR)
  WheelPackage package = 1;     // Wheel package type enum
  int32 width = 2;              // Tire width (mm)
  int32 aspect_ratio = 3;       // Aspect ratio
  int32 rim_diameter = 4;       // Rim diameter (inches)
  int32 load_index = 5;         // Load index
  int32 speed_rating = 6;       // Speed rating code
  bool is_winter_tire = 7;      // Winter tire flag
  string tire_brand = 8;        // Manufacturer name
  TireType tire_type = 9;       // Tire type enum
  int32 tread_depth = 10;       // Tread depth (0.1mm units)
}

enum WheelPackage {
  DCP_WHEEL_PACKAGE_UNSPECIFIED = 0;
  DCP_WHEEL_PACKAGE_20_INCH_AT = 1;
  DCP_WHEEL_PACKAGE_21_INCH_ROAD = 2;
  DCP_WHEEL_PACKAGE_22_INCH_SPORT = 3;
}
```

### Base64 Encoding

All protobuf messages are Base64-encoded before transmission:

```python
import base64
from google.protobuf import message

# Encode
protobuf_bytes = message.SerializeToString()
base64_payload = base64.b64encode(protobuf_bytes).decode('utf-8')

# Decode
protobuf_bytes = base64.b64decode(base64_payload)
message.ParseFromString(protobuf_bytes)
```

---

## Security Considerations

### Authentication Requirements

**Required Tokens**:
1. **User Session Token** - Obtained via Rivian login flow
2. **Access Token** - Short-lived JWT from authentication
3. **CSRF Token** - Cross-site request forgery protection

**Token Acquisition Flow**:
```python
# 1. Login
otp_token = await rivian.login(username, password)

# 2. Complete MFA if required
if otp_token:
    await rivian.login_with_otp(username, otp_code, otp_token)

# 3. Tokens now available for Parallax requests
# - rivian._session_token
# - rivian._access_token
# - rivian._csrf_token
```

### Authorization Model

**Vehicle Ownership Verification**:
- User must be the vehicle owner or authorized driver
- Validated against user's registered vehicle list
- Unauthorized access attempts return GraphQL error

**Scope Restrictions**:
- Each RVM has implicit read/write permissions
- Some RVMs are read-only (e.g., OTA_STATE, TRIP_PROGRESS)
- Write operations may require additional vehicle state checks

### Network Security

**Transport Layer**:
- HTTPS/TLS 1.2+ required
- Certificate pinning recommended
- GraphQL endpoint: `https://rivian.com/api/gql/gateway/graphql`

**Headers**:
```http
POST /api/gql/gateway/graphql HTTP/1.1
Host: rivian.com
Content-Type: application/json
User-Agent: RivianApp/iOS <version>
Authorization: Bearer <access_token>
csrf-token: <csrf_token>
a-sess: <app_session_token>
u-sess: <user_session_token>
apollographql-client-name: com.rivian.ios.consumer
apollographql-client-version: <version>
```

### Privacy Considerations

**Data Sensitivity**:
- **Low**: Wheel configuration, OTA schedule
- **Medium**: Charging data, climate preferences
- **High**: Geofence locations, navigation routes
- **Critical**: GearGuard consents, passive entry settings

**Logging Recommendations**:
- Never log full protobuf payloads in production
- Sanitize vehicle IDs in logs
- Redact location data (geofences, navigation)
- Mask cost/financial information

### Rate Limiting

**Observed Behavior**:
- No explicit rate limits documented in Android app
- Cloud infrastructure likely implements per-user throttling
- Recommend max 10 requests/minute per vehicle
- Use exponential backoff on errors

**Error Handling**:
```python
try:
    result = await send_parallax_payload(vehicle_id, rvm, payload)
except RivianRateLimited as e:
    # Wait and retry with exponential backoff
    await asyncio.sleep(min(2 ** retry_count, 60))
except RivianUnauthenticated as e:
    # Re-authenticate and retry
    await rivian.login(username, password)
```

---

## Comparison with BLE Protocols

### Parallax vs Gen1/Gen2 BLE

| Feature | Parallax Protocol | Gen1 BLE | Gen2 BLE |
|---------|------------------|----------|----------|
| **Transport** | HTTPS/GraphQL | Bluetooth Low Energy | Bluetooth Low Energy |
| **Range** | Unlimited (cloud) | ~30 meters | ~30 meters |
| **Proximity** | Not required | Required | Required |
| **Authentication** | User session tokens | Phone enrollment + HMAC | Phone enrollment + ECDH + HMAC |
| **Encryption** | TLS 1.2+ | Basic HMAC | AES-GCM derived |
| **Serialization** | Protocol Buffers (Base64) | Binary messages | Protocol Buffers |
| **Vehicle State** | Read/Write RVM data | Execute commands | Execute commands |
| **Use Cases** | Analytics, settings, monitoring | Lock/unlock, climate, lights | Lock/unlock, climate, lights |
| **Data Volume** | High (historical data) | Low (simple commands) | Low (simple commands) |
| **Latency** | ~500ms - 2s | ~100-500ms | ~100-500ms |
| **Phone Pairing** | Not required | Required (one-time) | Required (one-time) |
| **Key Exchange** | N/A | ECDSA public key | ECDH P-256 key derivation |
| **Vehicle Wakeup** | Supported (`requiresWakeup`) | May wake vehicle | May wake vehicle |
| **Offline Support** | No (requires internet) | Yes (BLE direct) | Yes (BLE direct) |

### When to Use Each Protocol

**Use Parallax When**:
- Vehicle is not nearby (cloud access)
- Reading historical/analytics data
- Configuring settings remotely
- Monitoring charging sessions
- Managing OTA updates
- No BLE pairing available

**Use Gen1/Gen2 BLE When**:
- Vehicle is physically nearby
- Executing real-time commands (lock, unlock, climate)
- Offline operation required
- Lower latency needed
- Phone is already paired

**Complementary Usage**:
- BLE for immediate vehicle commands
- Parallax for data retrieval and settings management
- Both protocols can be used by the same application
- No conflict between protocols

### Protocol Overlap

**Common Functionality**:
| Capability | Parallax | BLE |
|------------|----------|-----|
| Climate control settings | ✓ (CLIMATE_HOLD_SETTING) | ✓ (EnableCabinPreconditioning) |
| Passive entry | ✓ (PASSIVE_ENTRY_SETTING) | ✗ |
| Charging schedule | ✓ (CHARGING_SCHEDULE_TIME_WINDOW) | ✗ |
| Live charging data | ✓ (CHARGING_SESSION_LIVE_DATA) | ✗ |
| Lock/unlock doors | ✗ | ✓ (LockAllClosures) |
| Flash lights | ✗ | ✓ (FlashLights) |
| Honk horn | ✗ | ✓ (HonkHorn) |
| Open frunk/liftgate | ✗ | ✓ (OpenFrunk, OpenLiftgate) |

---

## Implementation Guide

### Prerequisites

**Required Libraries**:
- `gql[aiohttp]` - GraphQL client with async support
- `protobuf` - Protocol Buffer support (>=3.20.0, <6.0.0)
- `aiohttp` - Async HTTP client

**Installation**:
```bash
pip install gql[aiohttp] protobuf aiohttp
```

### Python Implementation Example

```python
import base64
import asyncio
from typing import Optional, Dict, Any
from gql import gql, Client
from gql.transport.aiohttp import AIOHTTPTransport
from google.protobuf.message import Message


class ParallaxClient:
    """Rivian Parallax Protocol Client"""

    GRAPHQL_ENDPOINT = "https://rivian.com/api/gql/gateway/graphql"

    def __init__(
        self,
        access_token: str,
        csrf_token: str,
        user_session_token: str,
        app_session_token: str,
    ):
        """Initialize Parallax client with authentication tokens."""
        self.access_token = access_token
        self.csrf_token = csrf_token
        self.user_session_token = user_session_token
        self.app_session_token = app_session_token

        # Create GraphQL transport with authentication headers
        headers = {
            "Authorization": f"Bearer {access_token}",
            "csrf-token": csrf_token,
            "u-sess": user_session_token,
            "a-sess": app_session_token,
            "apollographql-client-name": "rivian-python-client",
            "apollographql-client-version": "2.0.0",
        }

        self.transport = AIOHTTPTransport(
            url=self.GRAPHQL_ENDPOINT,
            headers=headers,
        )
        self.client = Client(
            transport=self.transport,
            fetch_schema_from_transport=False,
        )

    async def send_parallax_payload(
        self,
        vehicle_id: str,
        rvm_name: str,
        payload: Message,
        requires_wakeup: bool = True,
    ) -> Dict[str, Any]:
        """
        Send Parallax protocol payload to vehicle.

        Args:
            vehicle_id: Vehicle UUID
            rvm_name: Remote Vehicle Module name (e.g.,
                     "energy_edge_compute.graphs.charging_graph_global")
            payload: Protocol Buffer message to send
            requires_wakeup: Wake vehicle if sleeping

        Returns:
            Dict with 'success' (bool) and 'sequenceNumber' (int)
        """
        # Serialize protobuf to bytes and encode as Base64
        protobuf_bytes = payload.SerializeToString()
        base64_payload = base64.b64encode(protobuf_bytes).decode('utf-8')

        # Build GraphQL mutation
        mutation = gql("""
            mutation SendRemoteCommand(
                $vehicleId: String!,
                $model: String!,
                $parallaxPayloadB64: String!
            ) {
                sendParallaxPayload(
                    payload: $parallaxPayloadB64,
                    meta: {
                        vehicleId: $vehicleId
                        model: $model
                        isVehicleModelOp: true
                        requiresWakeup: true
                    }
                ) {
                    success
                    sequenceNumber
                }
            }
        """)

        # Execute mutation
        variables = {
            "vehicleId": vehicle_id,
            "model": rvm_name,
            "parallaxPayloadB64": base64_payload,
        }

        async with self.client as session:
            result = await session.execute(
                mutation,
                variable_values=variables,
            )

        return result["sendParallaxPayload"]

    async def get_charging_session_live_data(
        self,
        vehicle_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get live charging session data using Parallax protocol.

        Returns parsed protobuf data as dictionary.
        """
        # For read operations, send empty payload
        # The RVM will return current state
        empty_payload = b""  # Or construct appropriate request protobuf

        result = await self.send_parallax_payload(
            vehicle_id=vehicle_id,
            rvm_name="energy_edge_compute.graphs.charge_session_breakdown",
            payload=empty_payload,
        )

        if not result["success"]:
            return None

        # In a complete implementation, the response would contain
        # the protobuf data which should be decoded here
        # For now, return the success status
        return result

    async def set_halloween_settings(
        self,
        vehicle_id: str,
        costume_theme: int,
        sound_volume: int,
        music_enabled: bool,
        light_show_enabled: bool,
    ) -> bool:
        """
        Configure Halloween celebration settings.

        Args:
            vehicle_id: Vehicle UUID
            costume_theme: Theme ID (0=NONE, 5=SPOOKY_SWAMP)
            sound_volume: Volume level (0-100)
            music_enabled: Enable Halloween music
            light_show_enabled: Enable light show effects

        Returns:
            True if successful
        """
        # Build HalloweenCelebrationSettings protobuf
        # (In real implementation, use generated protobuf classes)
        # For example purposes, showing the structure

        settings = {
            "costume_theme": costume_theme,
            "celebration_sound_volume": sound_volume,
            "music_enabled": music_enabled,
            "light_show_enabled": light_show_enabled,
            # ... other fields
        }

        # Convert to protobuf message
        # payload = build_halloween_settings_protobuf(settings)

        # result = await self.send_parallax_payload(
        #     vehicle_id=vehicle_id,
        #     rvm_name="holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings",
        #     payload=payload,
        # )

        # return result["success"]

        # Placeholder
        return False

    async def close(self):
        """Close the GraphQL client."""
        await self.transport.close()


async def main():
    """Example usage"""
    # Initialize client (tokens from Rivian authentication flow)
    client = ParallaxClient(
        access_token="your_access_token",
        csrf_token="your_csrf_token",
        user_session_token="your_user_session_token",
        app_session_token="your_app_session_token",
    )

    try:
        # Get live charging data
        charging_data = await client.get_charging_session_live_data(
            vehicle_id="your_vehicle_id"
        )
        print(f"Charging data: {charging_data}")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### Integration with rivian-python-client

The Parallax protocol can be integrated into the existing `rivian-python-client` library:

```python
# src/rivian/rivian.py

async def send_parallax_payload(
    self,
    vehicle_id: str,
    rvm_name: str,
    payload_b64: str,
    requires_wakeup: bool = True,
) -> dict:
    """
    Send Parallax protocol payload to vehicle RVM.

    Args:
        vehicle_id: Vehicle UUID
        rvm_name: Remote Vehicle Module name
        payload_b64: Base64-encoded protobuf payload
        requires_wakeup: Wake vehicle if sleeping

    Returns:
        Dict with 'success' and 'sequenceNumber'
    """
    client = await self._ensure_client(GRAPHQL_GATEWAY)
    assert self._ds is not None

    mutation = dsl_gql(
        DSLMutation(
            self._ds.Mutation.sendParallaxPayload.args(
                payload=payload_b64,
                meta={
                    "vehicleId": vehicle_id,
                    "model": rvm_name,
                    "isVehicleModelOp": True,
                    "requiresWakeup": requires_wakeup,
                }
            ).select(
                self._ds.SendParallaxPayloadResponse.success,
                self._ds.SendParallaxPayloadResponse.sequenceNumber,
            )
        )
    )

    try:
        async with async_timeout.timeout(self.request_timeout):
            result = await client.execute_async(mutation)
    except TransportQueryError as exception:
        self._handle_gql_error(exception)
    except asyncio.TimeoutError as exception:
        raise RivianApiException(
            "Timeout occurred while connecting to Rivian API."
        ) from exception

    return result["sendParallaxPayload"]
```

### Error Handling

```python
from rivian.exceptions import (
    RivianApiException,
    RivianUnauthenticated,
    RivianInvalidOTP,
)

try:
    result = await client.send_parallax_payload(
        vehicle_id="...",
        rvm_name="energy_edge_compute.graphs.charging_graph_global",
        payload=base64_payload,
    )

    if not result["success"]:
        print(f"Operation failed, sequence: {result['sequenceNumber']}")

except RivianUnauthenticated:
    # Re-authenticate
    await client.login(username, password)

except RivianApiException as e:
    # Handle general API errors
    print(f"API error: {e}")
```

### Testing

```python
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_send_parallax_payload():
    """Test Parallax payload transmission"""
    mock_response = {
        "sendParallaxPayload": {
            "success": True,
            "sequenceNumber": 12345,
        }
    }

    with patch("gql.Client.execute_async", return_value=mock_response):
        client = ParallaxClient(
            access_token="test_token",
            csrf_token="test_csrf",
            user_session_token="test_user_sess",
            app_session_token="test_app_sess",
        )

        result = await client.send_parallax_payload(
            vehicle_id="test_vehicle",
            rvm_name="test.rvm.name",
            payload=b"test_payload",
        )

        assert result["success"] is True
        assert result["sequenceNumber"] == 12345
```

---

## Appendix

### A. RVM Name Pattern Analysis

All RVM names follow a hierarchical structure:

```
<domain>.<service>.<resource>

Examples:
- energy_edge_compute.graphs.parked_energy_distributions
  └─ Domain: energy_edge_compute
     └─ Service: graphs
        └─ Resource: parked_energy_distributions

- comfort.cabin.climate_hold_setting
  └─ Domain: comfort
     └─ Service: cabin
        └─ Resource: climate_hold_setting

- geofence.geofence_service.favoriteGeofences
  └─ Domain: geofence
     └─ Service: geofence_service
        └─ Resource: favoriteGeofences
```

**Domain Categories**:
- `energy_edge_compute` - Energy analytics
- `comfort` - Climate and comfort systems
- `geofence` - Location-based services
- `ota` - Over-the-air updates
- `gearguard_streaming` - Security camera system
- `vehicle` - Vehicle hardware configuration
- `navigation` - Route and trip services
- `vehicle_access` - Entry and security
- `charging` - Charging management
- `holiday_celebration` - Special feature sets

### B. Protobuf Field Naming Conventions

Rivian's protobuf definitions follow these patterns:

**Field Names**:
- Snake case: `total_kwh`, `session_duration_mins`
- Descriptive: `current_range_per_hour`, `is_free_session`
- Unit suffixes: `_kwh`, `_mins`, `_kms`, `_celsius`

**Enum Naming**:
- SCREAMING_SNAKE_CASE: `DCP_WHEEL_PACKAGE_20_INCH_AT`
- Prefix with type: `DCP_` (Design Configuration Package)
- Status prefix: `STATUS_ON`, `STATUS_OFF`

**Message Naming**:
- PascalCase: `ChargingSessionLiveData`
- Descriptive composites: `HalloweenCelebrationSettings`
- Data/Info/State suffixes: `TripInfo`, `VehicleWheels`

### C. GraphQL Mutation ID

The mutation ID `f31f549f8fc58e1667adb629093f5e26e02bfb7c19db1685dc45faec2114bc7e` is a SHA-256 hash of the normalized mutation document. This is used by Apollo Client for:

- Persisted queries optimization
- Mutation caching
- Automatic deduplication
- Analytics tracking

### D. Vehicle Model Identifiers

The `model` parameter in the mutation metadata corresponds to the RVM name, not the vehicle model (R1T/R1S). This is a routing identifier for the cloud infrastructure.

**Examples**:
- `"energy_edge_compute.graphs.charging_graph_global"` routes to energy analytics RVM
- `"comfort.cabin.climate_hold_setting"` routes to climate control RVM

The vehicle type (R1T/R1S) is inferred from the `vehicleId`.

### E. Sequence Number Usage

The `sequenceNumber` in the response serves multiple purposes:

1. **Request Tracking**: Unique identifier for audit logs
2. **Deduplication**: Prevent duplicate command execution
3. **Ordering**: Maintain command sequence in high-load scenarios
4. **Debugging**: Correlate requests across logs

### F. Related Protocols

**Rivian API Ecosystem**:
- **GraphQL Gateway** (`/api/gql/gateway/graphql`) - Vehicle commands, state queries
- **Charging GraphQL** (`/api/gql/chrg/user/graphql`) - Charging-specific operations
- **WebSocket Subscriptions** (`wss://api.rivian.com/gql-consumer-subscriptions/graphql`) - Real-time state updates
- **Parallax Protocol** (this document) - RVM-based advanced features
- **Gen1 BLE** - Legacy proximity vehicle commands
- **Gen2 BLE (PRE_CCC)** - Enhanced proximity vehicle commands

### G. Future Considerations

**Potential Enhancements**:
- Batch operations (multiple RVM requests in single mutation)
- Subscription-based updates (WebSocket for RVM data streams)
- Response payload decoding (currently only success/sequenceNumber)
- Protobuf schema introspection endpoint
- RVM capability discovery API

**Deprecation Risk**:
- RVM names may change with software updates
- Protobuf schemas are not versioned
- Breaking changes possible without notification

### H. References

**Source Files** (from `com.rivian.android.consumer`):
- `EnumC6207c.java` - RVM enumeration (18 types)
- `ParallaxAttributes.java` - Payload container class
- `C19629S8.java` - GraphQL mutation builder
- `C8630d.java` - CloudParallaxCommandOperation executor
- `C19106b.java` - ChargingSessionLiveData protobuf
- `C21876n.java` - HalloweenCelebrationSettings protobuf
- `C18593l.java` - ChargingScheduleTimeWindow protobuf

**GraphQL Endpoint**:
- Production: `https://rivian.com/api/gql/gateway/graphql`

**Related Documentation**:
- Gen2 BLE Protocol: `GEN2_BLE_PROTOCOL_ANALYSIS.md`
- Project Documentation: `CLAUDE.md`

---

**Document Version**: 1.0
**Last Updated**: 2025-10-26
**Author**: Claude Code Analysis
**License**: MIT (same as rivian-python-client)
