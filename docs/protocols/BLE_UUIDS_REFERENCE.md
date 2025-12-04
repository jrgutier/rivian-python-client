# Rivian BLE UUIDs Reference

Complete catalog of Bluetooth Low Energy (BLE) UUIDs used in Rivian vehicle pairing protocols.

## Main Service UUID

**Primary BLE Service for Phone Key Pairing**

- **UUID**: `52495356-454E-534F-5253-455256494345`
- **ASCII Decoded**: `RISVENSORSERVICE` (likely "RIVIAN SENSOR SERVICE" with truncation)
- **Android Location**: `/com.rivian.android.consumer/java_src/p638aj/C11162i.java:248` (field `f37404K`)
- **Python Location**: `/src/rivian/ble_gen2.py:33` (constant `RIVIAN_SERVICE_UUID`)
- **Purpose**: Main GATT service UUID for all Rivian phone key operations
- **Applies To**: Both Gen 1 (LEGACY) and Gen 2 (PRE_CCC) vehicles

---

## Complete UUID Catalog

### Gen 1 (LEGACY) - Early Production Vehicles (2021-2023)

| UUID | ASCII Decoded | Purpose | Type | Android File | Python File | Status |
|------|---------------|---------|------|--------------|-------------|--------|
| `5249565F-4D4F-424B-4559-5F5752495445` | `RIV_MOBKEY_WRITE` | Active entry characteristic for triggering bonding | Characteristic (Protected) | `C11162i.java:254` (f37406M) | `ble.py:31` (GEN1_ACTIVE_ENTRY) | ✅ Implemented |
| `AA49565A-4D4F-424B-4559-5F5752495445` | *(binary)* | Phone ID ↔ Vehicle ID exchange | Characteristic (Read/Write) | `C12140c.java:49` | `ble.py:32` (GEN1_PHONE_ID_VEHICLE_ID) | ✅ Implemented |
| `E020A15D-E730-4B2C-908B-51DAF9D41E19` | *(binary)* | Phone nonce ↔ Vehicle nonce exchange + HMAC | Characteristic (Read/Write) | `C12140c.java:52` | `ble.py:33` (GEN1_PHONE_NONCE_VEHICLE_NONCE) | ✅ Implemented |

**Gen 1 Protocol Summary:**
- Simple 2-3 state authentication flow
- Direct ECDSA key usage (no ECDH derivation)
- HMAC format: `phone_nonce + hmac`
- CSN increments by +1
- No Protocol Buffer serialization

---

### Gen 2 (PRE_CCC) - Late 2023+ Vehicles

| UUID | ASCII Decoded | Purpose | Type | Android File | Python File | Status |
|------|---------------|---------|------|--------------|-------------|--------|
| `72CDDCA3-AB00-4E94-BAE5-868F93F8C6C0` | *(binary)* | CCC Management characteristic | Characteristic | `C11162i.java:251` (f37405L) | *(not used)* | ⚠️ Reserved |
| `AFB2E704-842B-4E6A-9BD2-B1B305828F24` | *(binary)* | Mobile key write (Gen 2) | Characteristic | `C11162i.java:255` (f37407N) | *(not used)* | ⚠️ Reserved |
| `5AE32B92-EAFB-471B-AFE8-E88EEC4A4774` | *(binary)* | Unknown purpose (field O) | Characteristic | `C11162i.java:256` (f37408O) | *(not used)* | ❌ Unknown |
| `0823DA14-040B-4914-BF7C-450AFA2850DA` | *(binary)* | **Plain data input** - unencrypted inbound messages | Characteristic (Write) | `C11162i.java:257` (f37409P) | `ble_gen2.py:36` (PLAIN_DATA_IN) | ✅ Implemented |
| `29919A3C-A697-4A6F-BD3B-D14860CC9BCE` | *(binary)* | **Plain data output** - unencrypted outbound messages | Characteristic (Read/Notify) | `C11162i.java:258` (f37410Q) | `ble_gen2.py:37` (PLAIN_DATA_OUT) | ✅ Implemented |
| `9A69AEFF-E3FE-4E79-BB7D-5AE12272FD14` | *(binary)* | **Encrypted data input** - encrypted inbound messages | Characteristic (Write) | `C11162i.java:259` (f37411R) | `ble_gen2.py:38` (ENCRYPTED_DATA_IN) | ✅ Implemented |
| `5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B` | *(binary)* | **Encrypted data output** - encrypted outbound messages | Characteristic (Read/Notify) | `C11162i.java:260` (f37412S) | `ble_gen2.py:39` (ENCRYPTED_DATA_OUT) | ✅ Implemented |
| `52495649-414E-2052-4541-442043484152` | `RIVIAN READ CHAR` | Read characteristic (general purpose) | Characteristic (Read) | `C11130J.java:66` | *(not used)* | ⚠️ Reserved |

**Gen 2 Protocol Summary:**
- Complex 4-state authentication state machine (INIT → PID_PNONCE_SENT → SIGNED_PARAMS_SENT → AUTHENTICATED)
- ECDH (P-256) key derivation for shared secret
- HMAC format: `protobuf || csn || phone_id || pnonce || vnonce`
- Protocol Buffer message serialization
- CSN increments by +2 (even/odd)
- Encryption: AES-GCM derived from HMAC-SHA256

---

### Key Fob V2

| UUID | ASCII Decoded | Purpose | Type | Android File | Status |
|------|---------------|---------|------|--------------|--------|
| `A3450BC7-11C1-4D08-9DA3-E8C41EC8A191` | *(binary)* | Key Fob V2 service UUID | Service | `C14142b.java:85` (f48359o) | ❌ Not implemented |
| `6F65732A-5F72-6976-3032-000000000000` | `oes*_riv02` + 6×00 | Key Fob V2 base UUID | Characteristic | `AbstractC14144d.java:9` (f48379a) | ❌ Not implemented |

**Note:** Key Fob V2 appears to be a separate BLE interface for physical key fobs, not phone-based keys.

---

### Standard GATT Descriptor

| UUID | Purpose | Type | Source |
|------|---------|------|--------|
| `00002902-0000-1000-8000-00805F9B34FB` | Client Characteristic Configuration Descriptor (CCCD) | Descriptor | Bluetooth SIG Standard |

This is the standard Bluetooth GATT descriptor for enabling/disabling notifications/indications.

---

## GATT Structure Diagram

### Gen 1 (LEGACY) GATT Hierarchy

```
Service: 52495356-454E-534F-5253-455256494345 (RIVIAN SENSOR SERVICE)
├── Characteristic: AA49565A-4D4F-424B-4559-5F5752495445
│   ├── Properties: Read, Write, Notify
│   ├── Purpose: Phone ID → Vehicle ID validation
│   └── Descriptor: 00002902... (CCCD)
├── Characteristic: E020A15D-E730-4B2C-908B-51DAF9D41E19
│   ├── Properties: Read, Write, Notify
│   ├── Purpose: Nonce exchange + HMAC signature
│   └── Descriptor: 00002902... (CCCD)
└── Characteristic: 5249565F-4D4F-424B-4559-5F5752495445 (RIV_MOBKEY_WRITE)
    ├── Properties: Notify (Protected - requires bonding)
    └── Purpose: Trigger OS-level Bluetooth pairing
```

### Gen 2 (PRE_CCC) GATT Hierarchy

```
Service: 52495356-454E-534F-5253-455256494345 (RIVIAN SENSOR SERVICE)
├── Characteristic: 72CDDCA3-AB00-4E94-BAE5-868F93F8C6C0 (CCC Management)
│   └── Status: Reserved for future CCC protocol
├── Characteristic: 0823DA14-040B-4914-BF7C-450AFA2850DA (PLAIN_DATA_IN)
│   ├── Properties: Write
│   ├── Purpose: Receive unencrypted protobuf messages
│   └── Usage: Phase 1 (PID+PNONCE), Phase 3 (SIGNED_PARAMS)
├── Characteristic: 29919A3C-A697-4A6F-BD3B-D14860CC9BCE (PLAIN_DATA_OUT)
│   ├── Properties: Read, Notify
│   ├── Purpose: Send unencrypted protobuf responses
│   └── Descriptor: 00002902... (CCCD)
├── Characteristic: 9A69AEFF-E3FE-4E79-BB7D-5AE12272FD14 (ENCRYPTED_DATA_IN)
│   ├── Properties: Write
│   ├── Purpose: Receive encrypted messages
│   └── Usage: Post-authentication secure commands
├── Characteristic: 5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B (ENCRYPTED_DATA_OUT)
│   ├── Properties: Read, Notify
│   ├── Purpose: Send encrypted responses
│   ├── Usage: Phase 2 (VNONCE), Phase 4 (AUTH_CONFIRM)
│   └── Descriptor: 00002902... (CCCD)
└── Characteristic: 52495649-414E-2052-4541-442043484152 (RIVIAN READ CHAR)
    ├── Properties: Read
    └── Purpose: General-purpose read characteristic
```

---

## Protocol Detection Logic

The Python client automatically detects vehicle generation based on available BLE characteristics:

### Detection Algorithm (`ble.py:detect_vehicle_generation()`)

```python
async def detect_vehicle_generation(device: BLEDevice) -> int:
    """Returns: 1 for Gen 1, 2 for Gen 2, 0 if unknown"""

    # Connect and scan all characteristics
    services = client.services
    char_uuids = {char.uuid.upper() for char in all_chars}

    # Check for Gen 2 (PRE_CCC) - takes precedence
    gen2_chars = {
        "0823DA14-040B-4914-BF7C-450AFA2850DA",  # PLAIN_DATA_IN
        "5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B",  # ENCRYPTED_DATA_OUT
    }
    if gen2_chars.issubset(char_uuids):
        return 2  # Gen 2 (PRE_CCC)

    # Check for Gen 1 (LEGACY)
    gen1_chars = {
        "AA49565A-4D4F-424B-4559-5F5752495445",  # PHONE_ID_VEHICLE_ID
        "E020A15D-E730-4B2C-908B-51DAF9D41E19",  # PHONE_NONCE_VEHICLE_NONCE
    }
    if gen1_chars.issubset(char_uuids):
        return 1  # Gen 1 (LEGACY)

    return 0  # Unknown
```

### Detection Strategy

1. **Gen 2 Detection (Priority)**: Checks for `PLAIN_DATA_IN` + `ENCRYPTED_DATA_OUT`
2. **Gen 1 Detection (Fallback)**: Checks for `PHONE_ID_VEHICLE_ID` + `PHONE_NONCE_VEHICLE_NONCE`
3. **Unknown**: Returns 0 if neither pattern matches

This allows the `pair_phone()` function to automatically route to the correct protocol implementation.

---

## Implementation Status

### Python Client Implementation

| Generation | Module | Implementation Status | Functions |
|------------|--------|----------------------|-----------|
| **Gen 1** | `src/rivian/ble.py` | ✅ **Fully Implemented** | `_pair_phone_gen1()` |
| **Gen 2** | `src/rivian/ble_gen2.py` | ✅ **Fully Implemented** | `pair_phone_gen2()` |
| **Auto-detect** | `src/rivian/ble.py` | ✅ **Fully Implemented** | `detect_vehicle_generation()`, `pair_phone()` |
| **Key Fob V2** | *(none)* | ❌ **Not Implemented** | N/A |

### Characteristic Usage in Python

**Gen 1 (`ble.py`):**
- ✅ `GEN1_PHONE_ID_VEHICLE_ID_UUID` - Phone ID validation
- ✅ `GEN1_PHONE_NONCE_VEHICLE_NONCE_UUID` - Nonce exchange + HMAC
- ✅ `GEN1_ACTIVE_ENTRY_CHARACTERISTIC_UUID` - Bonding trigger (macOS only)

**Gen 2 (`ble_gen2.py`):**
- ✅ `PLAIN_DATA_IN_UUID` - Send protobuf messages (Phase 1 & 3)
- ✅ `ENCRYPTED_DATA_OUT_UUID` - Receive encrypted responses (Phase 2 & 4)
- ⚠️ `PLAIN_DATA_OUT_UUID` - Reserved (not currently used)
- ⚠️ `ENCRYPTED_DATA_IN_UUID` - Reserved (not currently used for pairing)

**Not Yet Used:**
- ❌ `CCC_MANAGEMENT` (72CDDCA3...) - Future CCC protocol support
- ❌ `MOBKEY_WRITE` Gen 2 (AFB2E704...) - Alternative write characteristic
- ❌ `RIVIAN READ CHAR` (52495649...) - General read operations
- ❌ Key Fob V2 UUIDs - Separate physical key fob protocol

---

## Message Flow Summary

### Gen 1 (LEGACY) Flow

```
Phone                                 Vehicle
  |                                      |
  |  (1) Write Phone ID                  |
  |------------------------------------->|
  |      PHONE_ID_VEHICLE_ID_UUID        |
  |                                      |
  |  (2) Read Vehicle ID                 |
  |<-------------------------------------|
  |      PHONE_ID_VEHICLE_ID_UUID        |
  |      [Validate VAS Vehicle ID]       |
  |                                      |
  |  (3) Write Phone Nonce + HMAC        |
  |------------------------------------->|
  |      PHONE_NONCE_VEHICLE_NONCE_UUID  |
  |      [16-byte nonce + 32-byte HMAC]  |
  |                                      |
  |  (4) Read Vehicle Nonce              |
  |<-------------------------------------|
  |      PHONE_NONCE_VEHICLE_NONCE_UUID  |
  |                                      |
  |  (5) Enable Notify on Protected Char|
  |------------------------------------->|
  |      ACTIVE_ENTRY_CHARACTERISTIC     |
  |      [Triggers OS bonding]           |
  |                                      |
  |  (6) OS Bluetooth Pairing Dialog     |
  |<------------------------------------>|
  |      [System-level pairing]          |
  |                                      |
```

### Gen 2 (PRE_CCC) Flow

```
Phone                                 Vehicle
  |                                      |
  |  Phase 1: PID + PNONCE               |
  |  (1) Generate 16-byte phone nonce    |
  |  (2) Build protobuf message          |
  |      - CSN: 1                        |
  |      - PhoneID (UUID, big-endian)    |
  |      - pNonce (16 bytes)             |
  |                                      |
  |  (3) Write via PLAIN_DATA_IN         |
  |------------------------------------->|
  |      [State: PID_PNONCE_SENT]        |
  |                                      |
  |  Phase 2: Receive VNONCE             |
  |  (4) Read from ENCRYPTED_DATA_OUT    |
  |<-------------------------------------|
  |      [Extract vNonce from protobuf]  |
  |                                      |
  |  Phase 3: HMAC Signature             |
  |  (5) Derive ECDH shared secret       |
  |      - ECDH(private_key, veh_pubkey) |
  |  (6) Compute HMAC-SHA256             |
  |      Input: protobuf||CSN||phoneID|| |
  |             pNonce||vNonce           |
  |      Key: 32-byte shared secret      |
  |  (7) Build SIGNED_PARAMS protobuf    |
  |      - CSN: 3                        |
  |      - HMAC signature (32 bytes)     |
  |                                      |
  |  (8) Write via PLAIN_DATA_IN         |
  |------------------------------------->|
  |      [State: SIGNED_PARAMS_SENT]     |
  |                                      |
  |  Phase 4: Authentication Complete    |
  |  (9) Read from ENCRYPTED_DATA_OUT    |
  |<-------------------------------------|
  |      [Status: SUCCESS]               |
  |      [State: AUTHENTICATED]          |
  |                                      |
```

---

## Security Notes

### Gen 1 Security
- **Key Type**: ECDSA (direct usage)
- **HMAC**: Simple format (`phone_nonce + hmac`)
- **Encryption**: Basic BLE security
- **Validation**: Vehicle ID matching

### Gen 2 Security
- **Key Derivation**: ECDH with P-256 curve
- **HMAC Algorithm**: HMAC-SHA256 (32-byte output)
- **HMAC Input**: Multi-component (`protobuf || csn || phone_id || pnonce || vnonce`)
- **Encryption**: AES-GCM (derived from HMAC key)
- **Nonce**: 16-byte random nonce from `secrets.token_bytes(16)`
- **Serialization**: Google Protocol Buffers
- **State Machine**: 4-state authentication flow
- **CSN**: Command Sequence Number (prevents replay attacks)

---

## Related Documentation

- **`GEN2_BLE_PROTOCOL_ANALYSIS.md`** - Detailed Gen 2 protocol analysis with code locations
- **`GEN2_PROTOCOL_SUMMARY.md`** - Gen 2 protocol summary with diagrams
- **`PROTOCOL_ANALYSIS_SUMMARY.txt`** - Combined protocol analysis notes
- **`src/rivian/ble.py`** - Python Gen 1 implementation + auto-detection
- **`src/rivian/ble_gen2.py`** - Python Gen 2 implementation
- **`src/rivian/ble_gen2_proto.py`** - Protocol Buffer message builders

---

## Android App References

### Key Source Files

| File | Purpose | Key UUIDs |
|------|---------|-----------|
| `p638aj/C11162i.java` | Main BLE protocol handler | All Gen 1/Gen 2 UUIDs |
| `p638aj/C11173t.java` | Gen 2 session manager | - |
| `bj/C12140c.java` | Gen 1 UUID definitions | Gen 1 characteristics |
| `dj/C14142b.java` | Key Fob V2 handler | Key Fob UUIDs |
| `dj/AbstractC14144d.java` | Key Fob V2 constants | Key Fob base UUID |

### Field Naming Convention (Android)

```java
// C11162i.java static fields
f37404K = RIVIAN_SERVICE_UUID          // Main service
f37405L = CCC_MANAGEMENT_UUID           // Gen 2 CCC
f37406M = GEN1_ACTIVE_ENTRY_UUID        // Gen 1 bonding
f37407N = GEN2_MOBKEY_WRITE_UUID        // Gen 2 alt write
f37408O = UNKNOWN_UUID                  // Unknown purpose
f37409P = PLAIN_DATA_IN_UUID            // Gen 2 plain in
f37410Q = PLAIN_DATA_OUT_UUID           // Gen 2 plain out
f37411R = ENCRYPTED_DATA_IN_UUID        // Gen 2 encrypted in
f37412S = ENCRYPTED_DATA_OUT_UUID       // Gen 2 encrypted out
```

---

## Appendix: UUID Decoding Examples

### ASCII-Decodable UUIDs

Some UUIDs encode human-readable strings:

```python
# Main Service
"52495356-454E-534F-5253-455256494345" → "RISVENSORSERVICE"
# Likely truncated from "RIVIAN SENSOR SERVICE"

# Gen 1 Active Entry
"5249565F-4D4F-424B-4559-5F5752495445" → "RIV_MOBKEY_WRITE"

# Gen 2 Read Characteristic
"52495649-414E-2052-4541-442043484152" → "RIVIAN READ CHAR"

# Key Fob V2 Base (partial)
"6F65732A-5F72-6976-3032-000000000000" → "oes*_riv02" + 6×00
```

### Binary UUIDs

Other UUIDs are randomly generated and contain no ASCII meaning:

```
AA49565A-4D4F-424B-4559-5F5752495445  (Gen 1 Phone ID)
E020A15D-E730-4B2C-908B-51DAF9D41E19  (Gen 1 Nonce)
72CDDCA3-AB00-4E94-BAE5-868F93F8C6C0  (Gen 2 CCC)
... (all Gen 2 data characteristics)
```

---

## Changelog

| Date | Version | Changes |
|------|---------|---------|
| 2025-10-26 | 1.0 | Initial comprehensive reference document |

---

**End of BLE UUIDs Reference**
