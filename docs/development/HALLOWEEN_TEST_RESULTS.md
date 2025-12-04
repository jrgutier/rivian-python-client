# Halloween Settings Test Results

## Summary

Successfully implemented and tested Halloween celebration settings using the iOS `sendVehicleOperation` mutation!

## Test Results

✅ **Test 1: Enable Halloween mode (default sounds)**
- Payload size: 40 bytes
- Payload hex: `0a0208051202080d1a020801220208012a0030013a020801420208014a02080152005a0062020802`
- Result: SUCCESS ✅

✅ **Test 2: Enable with interior sound #1**
- Payload size: 44 bytes
- Payload hex: `0a0208051202080d1a020801220208012a02080130043a020801420208014a02080152005a02080a62020802`
- Result: SUCCESS ✅

✅ **Test 3: Disable Halloween mode**
- Payload size: 34 bytes
- Payload hex: `0a0012001a00220208012a02080630043a02080142004a0052005a02080a62020802`
- Result: SUCCESS ✅

## Payload Comparison

### Generated vs MITM Captured

**Test 1 (Halloween ON):**
- Generated: `0a0208051202080d1a020801220208012a0030013a020801420208014a02080152005a0062020802`
- MITM:      `0a0208051202080d1a020801220208012a0030013a020801420208014a02080152005a0062020802`
- ✅ **EXACT MATCH!**

**Test 2 (Interior Sound #1):**
- Generated: `0a0208051202080d1a020801220208012a02080130043a020801420208014a02080152005a02080a62020802`
- MITM:      `0a0208051202080d1a020801220208012a02080130043a020801420208014a02080152005a02080a62020802`
- ✅ **EXACT MATCH!**

**Test 3 (Halloween OFF):**
- Generated: `0a0012001a00220208012a02080630043a02080142004a0052005a02080a62020802`
- MITM:      `0a0012001a00220208012a02080630043a02080142004a0052005a02080a62020802`
- ✅ **EXACT MATCH!**

## Protobuf Structure

The Halloween settings protobuf has 12 fields with wrapper messages:

```
Field 1: BoolValue (5 when ON, empty when OFF)
Field 2: BoolValue (13 when ON, empty when OFF)
Field 3: BoolValue (light show enabled)
Field 4: BoolValue (motion detection)
Field 5: IntValue (interior sound: 0=default, 1-4=sounds, 6=off)
Field 6: int32 (mode: 1=normal, 4=custom/off)
Field 7: BoolValue (unknown feature)
Field 8: BoolValue (unknown feature)
Field 9: BoolValue (unknown feature)
Field 10: string (theme name, empty in tests)
Field 11: IntValue (sound setting: 10 when custom sounds)
Field 12: IntValue (always 2)
```

## Key Features

### Interior Sounds
- 0 = Default/no custom sound
- 1 = Interior sound option 1
- 2 = Interior sound option 2
- 3 = Interior sound option 3
- 4 = Interior sound option 4
- 6 = OFF

### Modes
- 1 = Normal Halloween mode (default sounds, all features enabled)
- 4 = Custom/Off mode (with custom sounds or disabled)

## Implementation

The test uses a `build_halloween_payload()` function that manually constructs the protobuf bytes:

```python
payload = build_halloween_payload(enabled=True, interior_sound=1)

result = await client.send_vehicle_operation(
    vehicle_id=vehicle_id,
    rvm_type="holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings",
    payload=payload,
    phone_id=phone_id,
)
```

## Vehicle Response

All commands returned:
```json
{
  "__typename": "SendVehicleOperationSuccess",
  "success": true
}
```

## Architecture Notes

This confirms that `sendVehicleOperation` works for:
- ✅ Climate control (`comfort.cabin.climate_hold_setting`)
- ✅ Vehicle configuration (`vehicle.wheels.vehicle_wheels`)
- ✅ OTA configuration (`ota.user_schedule.ota_config`)
- ✅ **Holiday celebrations** (`holiday_celebration.mobile_vehicle_settings.halloween_celebration_settings`)

## Next Steps

To add full Halloween support to the library:

1. **Create proper protobuf definitions** (`rivian_vehicle_pb2.py`):
   - HalloweenCelebrationSettings message
   - BoolValue/IntValue wrapper messages
   - Interior sound enum

2. **Add helper method** to `rivian.py`:
   ```python
   async def set_halloween_settings(
       self,
       vehicle_id: str,
       enabled: bool = True,
       interior_sound: int = 0,
       phone_id: bytes = None
   ) -> dict:
       """Set Halloween celebration settings."""
   ```

3. **Add tests** to validate all sound options (1-4)

4. **Document** the feature in README with usage examples

## Files

- `decode_halloween_payloads.py` - Script to decode MITM captures
- `test_halloween_ios.py` - Test script with working implementation
- `HALLOWEEN_ANALYSIS.md` - Detailed field analysis
- `HALLOWEEN_TEST_RESULTS.md` - This file
