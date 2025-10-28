# Rivian BLE Pairing Protocols

Complete documentation for Rivian's Bluetooth Low Energy (BLE) phone pairing protocols.

## Table of Contents

- [Overview](#overview)
- [Gen 1 (LEGACY) Protocol](#gen-1-legacy-protocol)
- [Gen 2 (PRE_CCC) Protocol](#gen-2-pre_ccc-protocol)
- [BLE UUIDs Reference](#ble-uuids-reference)
- [Implementation Guide](#implementation-guide)
- [Security Considerations](#security-considerations)

---

## Overview

Rivian vehicles use Bluetooth Low Energy (BLE) for phone key pairing, enabling features like:
- Passive entry (walk-up unlock)
- Push-button start
- Remote vehicle commands via Bluetooth

Two protocol generations exist:
- **Gen 1 (LEGACY)**: Early production vehicles (2021-2023)
- **Gen 2 (PRE_CCC)**: Late 2023+ vehicles with enhanced security

The Python client automatically detects and uses the appropriate protocol.

---

## Gen 1 (LEGACY) Protocol

### Characteristics

- **Vehicles**: R1T/R1S early production (2021-2023)
- **Authentication**: 2-3 simple states
- **Serialization**: Simple binary messages
- **HMAC Format**: `phone_nonce + hmac`
- **Key Derivation**: Direct ECDSA usage
- **CSN Counter**: Increments by +1
- **Encryption**: Basic BLE security

### BLE Characteristics

| UUID | Purpose | Properties |
|------|---------|------------|
| `AA49565A-4D4F-424B-4559-5F5752495445` | Phone ID ↔ Vehicle ID exchange | Read/Write/Notify |
| `E020A15D-E730-4B2C-908B-51DAF9D41E19` | Phone nonce ↔ Vehicle nonce + HMAC | Read/Write/Notify |
| `5249565F-4D4F-424B-4559-5F5752495445` | Active entry (bonding trigger) | Notify (Protected) |

### Protocol Flow

```
Phone                                 Vehicle
  |                                      |
  | (1) Write Phone ID                   |
  |------------------------------------->|
  |                                      |
  | (2) Read Vehicle ID & Validate       |
  |<-------------------------------------|
  |                                      |
  | (3) Write Phone Nonce + HMAC         |
  |------------------------------------->|
  |     [16-byte nonce + 32-byte HMAC]   |
  |                                      |
  | (4) Read Vehicle Nonce               |
  |<-------------------------------------|
  |                                      |
  | (5) Enable Notify (Triggers Pairing) |
  |------------------------------------->|
  |                                      |
  | (6) OS Bluetooth Pairing Dialog      |
  |<------------------------------------>|
  |                                      |
```

### Python Implementation

Located in `src/rivian/ble.py`:
- Function: `_pair_phone_gen1()`
- Auto-detection: `detect_vehicle_generation()`

---

## Gen 2 (PRE_CCC) Protocol

### Characteristics

- **Vehicles**: R1T/R1S late 2023+
- **Authentication**: 4-state explicit state machine
- **Serialization**: Protocol Buffers
- **HMAC Format**: `protobuf || csn || phone_id || pnonce || vnonce`
- **Key Derivation**: ECDH (P-256)
- **CSN Counter**: Increments by +2 (even/odd)
- **Encryption**: AES-GCM derived

### BLE Characteristics

| UUID | Purpose | Properties |
|------|---------|------------|
| `0823DA14-040B-4914-BF7C-450AFA2850DA` | Plain data input (unencrypted) | Write |
| `29919A3C-A697-4A6F-BD3B-D14860CC9BCE` | Plain data output (unencrypted) | Read/Notify |
| `9A69AEFF-E3FE-4E79-BB7D-5AE12272FD14` | Encrypted data input | Write |
| `5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B` | Encrypted data output | Read/Notify |

### Authentication States

1. **INIT (0)** - Initial state, ready to start authentication
2. **PID_PNONCE_SENT (1)** - Sent Phone ID + Phone Nonce
3. **SIGNED_PARAMS_SENT (2)** - Sent HMAC signature
4. **AUTHENTICATED (3)** - Authentication complete ✓

### Protocol Flow

```
Phone                                 Vehicle
  |                                      |
  | Phase 1: PID + PNONCE                |
  | (1) Generate 16-byte phone nonce     |
  | (2) Build protobuf message           |
  |     - CSN: 1                         |
  |     - PhoneID (UUID, big-endian)     |
  |     - pNonce (16 bytes)              |
  | (3) Write via PLAIN_DATA_IN          |
  |------------------------------------->|
  |     [State: PID_PNONCE_SENT]         |
  |                                      |
  | Phase 2: Receive VNONCE              |
  | (4) Read from ENCRYPTED_DATA_OUT     |
  |<-------------------------------------|
  |     [Extract vNonce from protobuf]   |
  |                                      |
  | Phase 3: HMAC Signature              |
  | (5) Derive ECDH shared secret        |
  | (6) Compute HMAC-SHA256              |
  |     Input: protobuf||CSN||phoneID||  |
  |            pNonce||vNonce            |
  |     Key: 32-byte shared secret       |
  | (7) Build SIGNED_PARAMS protobuf     |
  |     - CSN: 3                         |
  |     - HMAC signature (32 bytes)      |
  | (8) Write via PLAIN_DATA_IN          |
  |------------------------------------->|
  |     [State: SIGNED_PARAMS_SENT]      |
  |                                      |
  | Phase 4: Authentication Complete     |
  | (9) Read from ENCRYPTED_DATA_OUT     |
  |<-------------------------------------|
  |     [Status: SUCCESS]                |
  |     [State: AUTHENTICATED]           |
  |                                      |
```

### Cryptographic Operations

#### HMAC-SHA256 Computation

```python
# HMAC Input Buffer Composition:
hmac_input = (
    protobuf_bytes +           # Serialized protobuf message
    csn_bytes +                # 4-byte Command Sequence Number (big-endian)
    phone_id_bytes +           # 16-byte phone UUID (big-endian)
    phone_nonce_bytes +        # 16-byte phone nonce
    vehicle_nonce_bytes        # 16-byte vehicle nonce
)

# HMAC Key: 32-byte ECDH shared secret
hmac_key = ecdh_shared_secret  # From P-256 key agreement

# Compute HMAC-SHA256
hmac_signature = hmac.new(hmac_key, hmac_input, hashlib.sha256).digest()
# Output: 32 bytes
```

#### ECDH Key Derivation

```python
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

# Phone's private key (ECDSA from enrollment)
private_key = ec.derive_private_key(...)

# Vehicle's public key (from BLE characteristic)
vehicle_public_key = ec.EllipticCurvePublicKey.from_encoded_point(...)

# ECDH Key Agreement
ecdh = ec.ECDH()
shared_secret = private_key.exchange(ecdh, vehicle_public_key)
# Output: 32 bytes
```

### Session Context Fields

| Field | Type | Size | Purpose |
|-------|------|------|---------|
| `phone_id` | UUID | 16 bytes | Phone identifier (big-endian) |
| `pNonce` | bytes | 16 bytes | Phone-generated random nonce |
| `vNonce` | bytes | 16 bytes | Vehicle-generated random nonce |
| `CSN` | uint32 | 4 bytes | Command Sequence Number (big-endian) |
| `vasVehicleId` | UUID | 16 bytes | VAS vehicle identifier |
| `vehiclePublicKey` | hex string | 130 chars | Vehicle's ECDH public key |

### Python Implementation

Located in:
- `src/rivian/ble_gen2.py` - Main Gen 2 protocol handler
- `src/rivian/ble_gen2_proto.py` - Protocol Buffer message builders

Functions:
- `pair_phone_gen2()` - Main pairing function
- `build_pid_pnonce_message()` - Phase 1 message
- `build_signed_params_message()` - Phase 3 message

---

## BLE UUIDs Reference

### Main Service UUID

**Primary BLE Service** (both Gen 1 and Gen 2):
```
52495356-454E-534F-5253-455256494345
ASCII: "RISVENSORSERVICE" (likely "RIVIAN SENSOR SERVICE")
```

### Gen 1 UUIDs

| UUID | ASCII | Purpose |
|------|-------|---------|
| `5249565F-4D4F-424B-4559-5F5752495445` | `RIV_MOBKEY_WRITE` | Active entry bonding |
| `AA49565A-4D4F-424B-4559-5F5752495445` | *(binary)* | Phone/Vehicle ID exchange |
| `E020A15D-E730-4B2C-908B-51DAF9D41E19` | *(binary)* | Nonce exchange + HMAC |

### Gen 2 UUIDs

| UUID | Purpose |
|------|---------|
| `0823DA14-040B-4914-BF7C-450AFA2850DA` | Plain data input |
| `29919A3C-A697-4A6F-BD3B-D14860CC9BCE` | Plain data output |
| `9A69AEFF-E3FE-4E79-BB7D-5AE12272FD14` | Encrypted data input |
| `5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B` | Encrypted data output |
| `72CDDCA3-AB00-4E94-BAE5-868F93F8C6C0` | CCC Management (reserved) |
| `52495649-414E-2052-4541-442043484152` | `RIVIAN READ CHAR` (general read) |

### Detection Logic

```python
# Check for Gen 2 (takes precedence)
gen2_chars = {
    "0823DA14-040B-4914-BF7C-450AFA2850DA",  # PLAIN_DATA_IN
    "5EAA65C0-57EE-4CF4-A3D5-A4AAE20CBB0B",  # ENCRYPTED_DATA_OUT
}
if gen2_chars.issubset(available_uuids):
    return 2  # Gen 2 (PRE_CCC)

# Check for Gen 1 (fallback)
gen1_chars = {
    "AA49565A-4D4F-424B-4559-5F5752495445",  # PHONE_ID_VEHICLE_ID
    "E020A15D-E730-4B2C-908B-51DAF9D41E19",  # PHONE_NONCE_VEHICLE_NONCE
}
if gen1_chars.issubset(available_uuids):
    return 1  # Gen 1 (LEGACY)
```

---

## Implementation Guide

### Prerequisites

```bash
# Install BLE support
pip install rivian-python-client[ble]

# Or with Poetry
poetry install --extras ble
```

### Basic Usage

```python
from rivian import Rivian
from rivian.ble import pair_phone

# 1. Enroll phone via API
async with Rivian() as client:
    await client.login(username, password)

    # Generate key pair
    from rivian.utils import generate_key_pair
    public_key_pem, private_key_pem = generate_key_pair()

    # Enroll phone
    success = await client.enroll_phone(
        public_key=public_key_pem,
        device_name="My Phone"
    )

# 2. Pair via BLE (automatic generation detection)
success = await pair_phone(
    phone_id="your-phone-uuid",
    private_key_pem=private_key_pem,
    vehicle_id="your-vehicle-uuid"
)
```

### Manual Generation Selection

```python
from rivian.ble import pair_phone_gen1, pair_phone_gen2

# Force Gen 1
await pair_phone_gen1(phone_id, private_key_pem, vehicle_id)

# Force Gen 2
await pair_phone_gen2(phone_id, private_key_pem, vehicle_id)
```

---

## Security Considerations

### Gen 1 Security

**Strengths:**
- ECDSA key-based authentication
- 32-byte HMAC signatures
- Vehicle ID validation

**Considerations:**
- Simpler protocol may be more vulnerable
- No explicit key derivation
- Basic encryption

### Gen 2 Security

**Strengths:**
- ECDH with P-256 curve (256-bit security)
- HMAC-SHA256 with multi-component input
- Explicit nonce exchange (prevents replay)
- Protocol Buffer serialization (type safety)
- 4-state authentication state machine
- CSN sequence numbering (prevents replay)
- AES-GCM encryption post-authentication

**Considerations:**
- More complex = larger attack surface
- Protobuf complexity may hide logic
- Key caching (potential side-channel)
- No explicit rate limiting observed

### Best Practices

1. **Key Storage**: Store private keys securely (OS keychain)
2. **Nonce Generation**: Use `secrets.token_bytes(16)` (cryptographically secure)
3. **Key Validation**: Always validate vehicle public key format
4. **Timeout Handling**: Implement reasonable timeouts (60s recommended)
5. **Error Logging**: Never log private keys or HMACs
6. **Pairing Frequency**: Only pair when necessary (not on every connection)

---

## Comparison Table

| Feature | Gen 1 (LEGACY) | Gen 2 (PRE_CCC) |
|---------|----------------|-----------------|
| **Vehicles** | 2021-2023 | Late 2023+ |
| **States** | 2-3 | 4 explicit |
| **Serialization** | Binary | Protocol Buffers |
| **HMAC Input** | `phone_nonce + hmac` | `protobuf || csn || phone_id || pnonce || vnonce` |
| **Key Derivation** | Direct ECDSA | ECDH (P-256) |
| **Encryption** | Basic | AES-GCM |
| **CSN Counter** | +1 | +2 (even/odd) |
| **Detection** | Automatic via BLE characteristics |
| **Complexity** | Low | Higher |
| **Security Level** | Good | Enhanced |
| **Message Size** | Small (~50 bytes) | Medium (~60-80 bytes) |
| **Timeout** | 7s retry | 60s overall |

---

## Related Documentation

- **Python Implementation**: `src/rivian/ble.py`, `src/rivian/ble_gen2.py`
- **Protocol Buffers**: `src/rivian/ble_gen2_proto.py`
- **Utilities**: `src/rivian/utils.py` (key generation)
- **Tests**: `tests/test_ble.py` (if available)

---

## Source References

**Android App Analysis**:
- Main handler: `p638aj/C11162i.java`
- Gen 2 session: `p638aj/C11173t.java`
- Gen 1 UUIDs: `bj/C12140c.java`
- Message builders: `p617Zf/AbstractC10637k.java`
- Crypto: `p784h4/C15277l.java`

**Document Version**: 1.0
**Last Updated**: 2025-10-27
**License**: MIT
