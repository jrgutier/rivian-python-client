# Halloween Settings Analysis

## Decoded Payloads

### Halloween ON (Basic Enable)
```
Field 1.1: 5
Field 2.1: 13
Field 3.1: 1
Field 4.1: 1
Field 5: "" (empty)
Field 6: 1
Field 7.1: 1
Field 8.1: 1
Field 9.1: 1
Field 10: ""
Field 11: ""
Field 12.1: 2
```

### Interior Sounds 1-4 (Custom Sounds)
```
Field 1.1: 5
Field 2.1: 13
Field 3.1: 1
Field 4.1: 1
Field 5.1: 1, 2, 3, or 4  ← Sound selection changes!
Field 6: 4                 ← Mode changes to 4
Field 7.1: 1
Field 8.1: 1
Field 9.1: 1
Field 10: ""
Field 11.1: 10             ← Changes from empty to 10
Field 12.1: 2
```

### Halloween OFF (Disable)
```
Field 1: "" (empty)
Field 2: "" (empty)
Field 3: "" (empty)
Field 4.1: 1
Field 5.1: 6               ← 6 = OFF
Field 6: 4
Field 7.1: 1
Field 8: ""
Field 9: ""
Field 10: ""
Field 11.1: 10
Field 12.1: 2
```

## Field Mapping

Based on the patterns observed:

### Field 1 - Wrapper (BoolValue?)
- Subfield 1: Int value (5 when ON, empty when OFF)
- Likely: Some ON/OFF or mode setting

### Field 2 - Wrapper (BoolValue?)
- Subfield 1: Int value (13 when ON, empty when OFF)
- Likely: Another ON/OFF or mode setting

### Field 3 - Wrapper (BoolValue)
- Subfield 1: 1 = enabled, empty = disabled
- Likely: Light show enabled?

### Field 4 - Wrapper (BoolValue)
- Subfield 1: Always 1 in all captures
- Likely: Motion/proximity detection enabled?

### Field 5 - Wrapper (IntValue or Enum)
- Subfield 1: Interior sound selection
  - 0 or empty = Default/no custom sound
  - 1 = Interior sound option 1
  - 2 = Interior sound option 2
  - 3 = Interior sound option 3
  - 4 = Interior sound option 4
  - 6 = OFF
- **This is the interior sound selector!**

### Field 6 - Int (no wrapper)
- Direct varint value
- 1 = Normal Halloween mode
- 4 = Custom/Off mode
- Likely: Overall Halloween mode enum

### Field 7 - Wrapper (BoolValue)
- Subfield 1: 1 = enabled
- Likely: Another feature toggle

### Field 8 - Wrapper (BoolValue)
- Subfield 1: 1 = enabled (when ON), empty when OFF
- Likely: Another feature toggle

### Field 9 - Wrapper (BoolValue)
- Subfield 1: 1 = enabled (when ON), empty when OFF
- Likely: Another feature toggle

### Field 10 - String
- Always empty in captures
- Likely: Optional text field (theme name?)

### Field 11 - Wrapper (IntValue or Enum)
- Subfield 1:
  - empty = default
  - 10 = when custom sounds enabled
- Likely: Sound-related setting

### Field 12 - Wrapper (IntValue or Enum)
- Subfield 1: Always 2 in all captures
- Likely: Some configuration value

## Protobuf Structure

Based on the analysis, the Halloween settings message has this structure:

```protobuf
message HalloweenCelebrationSettings {
  BoolValue field1 = 1;              // Some mode (5 when ON)
  BoolValue field2 = 2;              // Some mode (13 when ON)
  BoolValue light_show_enabled = 3;  // Enable light show
  BoolValue motion_detection = 4;    // Motion/proximity detection
  IntValue interior_sound = 5;       // Interior sound selection (0=default, 1-4=sounds, 6=off)
  int32 halloween_mode = 6;          // Overall mode (1=on, 4=custom/off)
  BoolValue field7 = 7;              // Unknown toggle
  BoolValue field8 = 8;              // Unknown toggle
  BoolValue field9 = 9;              // Unknown toggle
  string theme_name = 10;            // Optional theme name (empty in captures)
  IntValue sound_setting = 11;       // Sound-related (10 when custom sounds)
  IntValue field12 = 12;             // Unknown (always 2)
}

message BoolValue {
  bool value = 1;
}

message IntValue {
  int32 value = 1;
}
```

## Usage Examples

### Enable Halloween with default sounds
```python
settings = HalloweenCelebrationSettings(
    field1=BoolValue(value=True),  # Set to 5
    field2=BoolValue(value=True),  # Set to 13
    light_show_enabled=BoolValue(value=True),
    motion_detection=BoolValue(value=True),
    # interior_sound left empty for default
    halloween_mode=1,  # Normal mode
    field7=BoolValue(value=True),
    field8=BoolValue(value=True),
    field9=BoolValue(value=True),
    field12=IntValue(value=2),
)
```

### Enable Halloween with custom interior sound #1
```python
settings = HalloweenCelebrationSettings(
    field1=BoolValue(value=True),  # 5
    field2=BoolValue(value=True),  # 13
    light_show_enabled=BoolValue(value=True),
    motion_detection=BoolValue(value=True),
    interior_sound=IntValue(value=1),  # Sound #1
    halloween_mode=4,  # Custom mode
    field7=BoolValue(value=True),
    field8=BoolValue(value=True),
    field9=BoolValue(value=True),
    sound_setting=IntValue(value=10),
    field12=IntValue(value=2),
)
```

### Disable Halloween
```python
settings = HalloweenCelebrationSettings(
    motion_detection=BoolValue(value=True),  # Only this stays enabled
    interior_sound=IntValue(value=6),  # 6 = OFF
    halloween_mode=4,
    field7=BoolValue(value=True),
    sound_setting=IntValue(value=10),
    field12=IntValue(value=2),
)
```

## Key Insights

1. **Interior sound is controlled by field 5** with values 1-4 for different sounds
2. **Field 6 (halloween_mode)** switches between:
   - 1 = Normal Halloween mode (default sounds, all features)
   - 4 = Custom/Off mode
3. **Field 5 value of 6** combined with **mode 4** = Halloween OFF
4. Many fields use **wrapper messages** (BoolValue/IntValue) not direct values
5. Several fields (1, 2, 7-9, 12) have unclear purposes but consistent patterns

## Next Steps

To fully implement this, we need to:
1. Generate proper protobuf definitions for all wrapper types
2. Test different sound combinations to confirm field 5 mapping
3. Identify the purposes of fields 1, 2, 7, 8, 9, 12
4. Test edge cases (what happens with invalid sound numbers?)
