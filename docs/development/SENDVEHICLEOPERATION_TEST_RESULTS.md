# sendVehicleOperation Test Results

## Overview
Testing which Parallax RVM (Remote Vehicle Module) operations work with the iOS `sendVehicleOperation` mutation vs the Android `sendParallaxPayload` mutation.

## Test Date
2025-10-27

## Results Summary
- **Total RVM types tested:** 14
- **Working with sendVehicleOperation:** 4 (28.6%)
- **Failing with sendVehicleOperation:** 10 (71.4%)

## Working RVM Types ✅

### 1. Climate Control
- ✅ **`comfort.cabin.climate_hold_status`** (Query)
  - Returns climate hold status
  - Empty payload for query

- ✅ **`comfort.cabin.climate_hold_setting`** (Command)
  - Sets climate hold duration
  - Requires ClimateHoldSetting protobuf payload
  - Payload example (2 hours): `08a038` (7200 seconds)

### 2. Vehicle Configuration
- ✅ **`vehicle.wheels.vehicle_wheels`** (Query)
  - Returns vehicle wheel configuration
  - Empty payload for query

### 3. OTA Updates
- ✅ **`ota.user_schedule.ota_config`** (Query)
  - Returns OTA schedule configuration
  - Empty payload for query

## Failing RVM Types ❌

All return `INTERNAL_SERVER_ERROR` from the API:

### Energy & Charging
- ❌ `energy_edge_compute.graphs.charge_session_breakdown`
- ❌ `energy_edge_compute.graphs.parked_energy_distributions`
- ❌ `energy_edge_compute.graphs.charging_graph_global`

### OTA Updates
- ❌ `ota.ota_state.vehicle_ota_state`

### Navigation
- ❌ `navigation.navigation_service.trip_progress`
- ❌ `navigation.navigation_service.trip_info`

### Geofencing
- ❌ `geofence.geofence_service.favoriteGeofences`

### Gear Guard
- ❌ `gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent`
- ❌ `gearguard_streaming.privacy.gearguard_streaming_daily_limit`

### Vehicle Access
- ❌ `vehicle_access.state.passive_entry`

## Key Findings

### 1. Not All RVM Types Work
The `sendVehicleOperation` mutation appears to be **domain-specific** and only supports certain RVM types. This suggests:
- iOS app uses `sendVehicleOperation` for **vehicle control operations** (climate, wheels, OTA config)
- iOS app likely uses `sendParallaxPayload` for **data queries** (energy, navigation, geofencing)

### 2. Supported Domains
Based on successful operations, `sendVehicleOperation` seems to work for:
- ✅ Comfort/Climate control (`comfort.cabin.*`)
- ✅ Vehicle configuration (`vehicle.*`)
- ✅ OTA configuration (`ota.user_schedule.*`)

### 3. Unsupported Domains
Operations that fail appear to be **analytics/monitoring** focused:
- ❌ Energy monitoring (`energy_edge_compute.*`)
- ❌ Navigation tracking (`navigation.*`)
- ❌ Security/Privacy settings (`gearguard_streaming.*`)
- ❌ Geofencing (`geofence.*`)

### 4. Query vs Command Pattern
For supported RVM types:
- **Query operations**: Empty payload (`b""`)
- **Command operations**: Serialized protobuf message

## Implementation Recommendation

The Python client should use a **hybrid approach**:

1. **For climate hold commands**: Use `sendVehicleOperation` (iOS method)
   - Requires phone enrollment
   - Faster/more reliable for vehicle control
   - Matches iOS app behavior

2. **For data queries**: Continue using `sendParallaxPayload` (Android method)
   - Works without phone enrollment requirement
   - Supports all analytics/monitoring RVM types
   - More flexible for data retrieval

## Current Implementation

The `set_climate_hold()` method now supports both approaches:

```python
# iOS method (with phone_id)
result = await client.set_climate_hold(
    vehicle_id="01-276948064",
    duration_minutes=480,
    phone_id=phone_id  # Triggers sendVehicleOperation
)

# Android method (without phone_id)
result = await client.set_climate_hold(
    vehicle_id="VIN123",
    duration_minutes=480  # Uses sendParallaxPayload
)
```

## Protobuf Payload Examples

### Climate Hold Setting (2 hours)
```
Hex: 08a038
Decoded: field 1 (varint) = 7200 (seconds)
```

### Climate Hold Setting (8 hours)
```
Hex: 0880e101
Decoded: field 1 (varint) = 28800 (seconds)
```

## Architecture Notes

### VehicleOperationRequest Structure
```
VehicleOperationRequest {
  metadata {
    phone_info {
      version: 1
      phone_id: <32-byte hex>
    }
    request_id: <UUID>
  }
  operation {
    rvm_type: "comfort.cabin.climate_hold_setting"
    operation_type: 1  (1=SET, 0=GET?)
    operation_id: <16-byte UUID>
    payload: <serialized protobuf>
    timestamp: <protobuf Timestamp>
  }
}
```

The entire request is base64-encoded and sent as the `payload` parameter to `sendVehicleOperation(vehicleId, payload)`.

## Conclusion

The `sendVehicleOperation` mutation is **not a universal replacement** for `sendParallaxPayload`. It's designed for specific vehicle control operations that require phone authentication. The client library should intelligently route requests based on the operation type.
