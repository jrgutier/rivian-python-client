# Rivian Key Fob V2 BLE Protocol

## Overview
Separate BLE service for Rivian key fob devices (not phone keys). Discovered in decompiled Android app.

## Service UUID
- **Service:** `A3450BC7-11C1-4D08-9DA3-E8C41EC8A191`
- **Source:** `/Users/jrgutier/src/rivian-python-client/com.rivian.android.consumer/java_src/dj/C14142b.java:85`

## Characteristics

### PLAIN_DATA_IN
- **UUID:** `0823DA14-040B-4914-BF7C-450AFA2850DA`
- **Properties:** Write
- **Purpose:** Unencrypted data input to key fob
- **Shared:** Same UUID as Gen 2 phone pairing

### PLAIN_DATA_OUT
- **UUID:** `29919A3C-A697-4A6F-BD3B-D14860CC9BCE`
- **Properties:** Read, Notify
- **Purpose:** Unencrypted data output from key fob
- **Shared:** Same UUID as Gen 2 phone pairing

### Base UUID
- **UUID:** `6F65732A-5F72-6976-3032-000000000000`
- **ASCII:** "oes*_riv02"
- **Source:** `/Users/jrgutier/src/rivian-python-client/com.rivian.android.consumer/java_src/dj/AbstractC14144d.java:9`

## Differences from Phone Key Gen 2

| Feature | Phone Key Gen 2 | Key Fob V2 |
|---------|----------------|------------|
| **Service UUID** | `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` | `A3450BC7-11C1-4D08-9DA3-E8C41EC8A191` |
| **PLAIN_DATA_IN** | ✓ Same UUID | ✓ Same UUID |
| **PLAIN_DATA_OUT** | ✓ Same UUID | ✓ Same UUID |
| **Encrypted Channels** | Yes (ENC_DATA_IN/OUT) | Unknown (likely none) |
| **Authentication** | 4-state machine with ECDH | Likely simpler |
| **Protocol Buffers** | Yes | Unknown |

## Implementation Notes

What's needed:
1. Add Key Fob V2 service UUID to scanner
2. Detect during BLE discovery
3. Implement pairing flow
4. Test with physical key fob

## Current Status
- ⚠️ Not implemented in rivian-python-client
- 📄 Documented for future work
- 🔬 Requires physical device testing

## Open Questions
- Does key fob use Protocol Buffers like Gen 2 phone pairing?
- Does key fob require ECDH key derivation?
- Are encrypted channels used at all?
- What authentication states exist for key fobs?
