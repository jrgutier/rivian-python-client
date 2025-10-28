# Parallax Protocol Audit - Key Files

## Python Implementation (Our Code)

### GraphQL Mutation (rivian.py lines 1504-1528)

```python
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
# Note: Do NOT add Bearer token - session cookies are sufficient
result = await self._execute_async(client, mutation, "SendRemoteCommand")

# Return response data
return result.get("sendParallaxPayload", {})
```

### RVM Enum (parallax.py)

```python
class RVMType(StrEnum):
    # Energy & Charging
    PARKED_ENERGY_MONITOR = "energy_edge_compute.graphs.parked_energy_distributions"
    CHARGING_SESSION_CHART_DATA = "energy_edge_compute.graphs.charging_graph_global"
    CHARGING_SESSION_LIVE_DATA = "energy_edge_compute.graphs.charge_session_breakdown"
    CHARGING_SCHEDULE_TIME_WINDOW = "charging.schedule.time_window"

    # Geofence
    VEHICLE_GEO_FENCES = "geofence.geofence_service.favoriteGeofences"

    # OTA Updates
    OTA_SCHEDULE_CONFIGURATION = "ota.user_schedule.ota_config"
    OTA_STATE = "ota.ota_state.vehicle_ota_state"

    # GearGuard
    GEAR_GUARD_CONSENTS = "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent"
    GEAR_GUARD_DAILY_LIMITS = "gearguard_streaming.privacy.gearguard_streaming_daily_limit"

    # Vehicle
    VEHICLE_WHEELS = "vehicle.wheels.vehicle_wheels"

    # Navigation
    TRIP_INFO = "navigation.navigation_service.trip_info"
    TRIP_PROGRESS = "navigation.navigation_service.trip_progress"

    # Climate & Comfort
    CLIMATE_HOLD_SETTING = "comfort.cabin.climate_hold_setting"
    CABIN_VENTILATION_SETTING = "comfort.cabin.cabin_ventilation_setting"
    CLIMATE_HOLD_STATUS = "comfort.cabin.climate_hold_status"

    # Vehicle Access
    PASSIVE_ENTRY_SETTING = "vehicle_access.passive_entry.passive_entry"
    PASSIVE_ENTRY_STATUS = "vehicle_access.state.passive_entry"

    # Holiday Celebrations
    HALLOWEEN_SETTINGS = "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings"
```

### Protobuf Example (Climate Hold)

```python
def build_climate_hold_command(duration_minutes: int = 120) -> ParallaxCommand:
    from .proto.rivian_climate_pb2 import ClimateHoldSetting

    # Convert minutes to seconds
    setting = ClimateHoldSetting(hold_time_duration_seconds=duration_minutes * 60)

    return ParallaxCommand.from_protobuf(RVMType.CLIMATE_HOLD_SETTING, setting)
```

Protobuf serialization for 120 minutes (7200 seconds):
- Hex: `08a038`
- Base64: `CKA4`

## Android APK Reference

### GraphQL Mutation (C19629S8.java line 75)

```java
public final String mo83d() {
    return "mutation SendRemoteCommand($vehicleId: String!, $model: String!, $parallaxPayloadB64: String!) { sendParallaxPayload(payload: $parallaxPayloadB64, meta: { vehicleId: $vehicleId model: $model isVehicleModelOp: true requiresWakeup: true } ) { success sequenceNumber } }";
}
```

### RVM Enum (EnumC6207c.java lines 126-143)

```java
public static final EnumC6207c PARKED_ENERGY_MONITOR = new EnumC6207c("PARKED_ENERGY_MONITOR", 0, "energy_edge_compute.graphs.parked_energy_distributions");
public static final EnumC6207c CHARGING_SESSION_CHART_DATA = new EnumC6207c("CHARGING_SESSION_CHART_DATA", 1, "energy_edge_compute.graphs.charging_graph_global");
public static final EnumC6207c CHARGING_SESSION_LIVE_DATA = new EnumC6207c("CHARGING_SESSION_LIVE_DATA", 2, "energy_edge_compute.graphs.charge_session_breakdown");
public static final EnumC6207c VEHICLE_GEO_FENCES = new EnumC6207c("VEHICLE_GEO_FENCES", 3, "geofence.geofence_service.favoriteGeofences");
public static final EnumC6207c OTA_SCHEDULE_CONFIGURATION = new EnumC6207c("OTA_SCHEDULE_CONFIGURATION", 4, "ota.user_schedule.ota_config");
public static final EnumC6207c OTA_STATE = new EnumC6207c("OTA_STATE", 5, "ota.ota_state.vehicle_ota_state");
public static final EnumC6207c GEAR_GUARD_CONSENTS = new EnumC6207c("GEAR_GUARD_CONSENTS", 6, "gearguard_streaming.privacy.gearguard_streaming_in_vehicle_consent");
public static final EnumC6207c GEAR_GUARD_DAILY_LIMITS = new EnumC6207c("GEAR_GUARD_DAILY_LIMITS", 7, "gearguard_streaming.privacy.gearguard_streaming_daily_limit");
public static final EnumC6207c VEHICLE_WHEELS = new EnumC6207c("VEHICLE_WHEELS", 8, "vehicle.wheels.vehicle_wheels");
public static final EnumC6207c TRIP_INFO = new EnumC6207c("TRIP_INFO", 9, "navigation.navigation_service.trip_info");
public static final EnumC6207c TRIP_PROGRESS = new EnumC6207c("TRIP_PROGRESS", 10, "navigation.navigation_service.trip_progress");
public static final EnumC6207c CLIMATE_HOLD_SETTING = new EnumC6207c("CLIMATE_HOLD_SETTING", 11, "comfort.cabin.climate_hold_setting");
public static final EnumC6207c CABIN_VENTILATION_SETTING = new EnumC6207c("CABIN_VENTILATION_SETTING", 12, "comfort.cabin.cabin_ventilation_setting");
public static final EnumC6207c CLIMATE_HOLD_STATUS = new EnumC6207c("CLIMATE_HOLD_STATUS", 13, "comfort.cabin.climate_hold_status");
public static final EnumC6207c PASSIVE_ENTRY_SETTING = new EnumC6207c("PASSIVE_ENTRY_SETTING", 14, "vehicle_access.passive_entry.passive_entry");
public static final EnumC6207c CHARGING_SCHEDULE_TIME_WINDOW = new EnumC6207c("CHARGING_SCHEDULE_TIME_WINDOW", 15, "charging.schedule.time_window");
public static final EnumC6207c HALLOWEEN_SETTINGS = new EnumC6207c("HALLOWEEN_SETTINGS", 16, "holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings");
public static final EnumC6207c PASSIVE_ENTRY_STATUS = new EnumC6207c("PASSIVE_ENTRY_STATUS", 17, "vehicle_access.state.passive_entry");
```

## Test Results

Vehicle: `cc41fc6c8fafd6e0030cfed1d04666e3`

### Climate Hold Status (Query) - DIFFERENT ERROR

```
RVM: comfort.cabin.climate_hold_status
Payload: "" (empty, read operation)
Error: OMS_ERROR
Message: "See server logs for error details"
Analysis: ✓ Request reaches Rivian backend
```

### All Other 20 RVM Types - SAME ERROR

```
Examples:
- energy_edge_compute.graphs.parked_energy_distributions
- energy_edge_compute.graphs.charging_graph_global
- ota.ota_state.vehicle_ota_state
- vehicle.wheels.vehicle_wheels

Error: INTERNAL_SERVER_ERROR
Reason: INTERNAL_SERVER_ERROR
Message: "Unexpected error occurred"
Analysis: ❌ Request rejected before reaching Parallax service
```

## What We've Verified ✓

1. **GraphQL mutation matches exactly** (Python DSL generates same query as Android)
2. **RVM type strings match exactly** (all 18 verified)
3. **Protobuf serialization matches** (verified with hex dumps)
4. **Authentication approach is correct** (session cookies, NOT Bearer tokens)

## Key Questions

1. **Why does Climate Hold Status get OMS_ERROR while others get INTERNAL_SERVER_ERROR?**
   - What makes Climate Hold Status different?
   - Is it the only enabled/available RVM type?

2. **What are we missing that causes INTERNAL_SERVER_ERROR?**
   - Hidden request parameters?
   - Additional headers?
   - Vehicle state checks before sending?
   - Feature flags or permissions?

3. **Does the Android app do anything before calling sendParallaxPayload?**
   - Token refresh?
   - Vehicle state query?
   - Feature availability check?

## Analysis Request

Compare the Python implementation to the Android APK code and identify:

1. Any discrepancies in the GraphQL mutation structure
2. Missing parameters or metadata
3. Required preconditions or checks
4. Why different RVM types return different errors
5. Specific recommendations to fix the implementation
