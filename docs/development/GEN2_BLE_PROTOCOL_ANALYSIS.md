# Gen 2 (PRE_CCC) BLE Pairing Protocol Analysis

## Overview

The Gen 2 (PRE_CCC) BLE pairing protocol is implemented in the Rivian Android app for secure vehicle-to-phone pairing over Bluetooth Low Energy. The protocol uses a challenge-response authentication scheme with HMAC-SHA256 cryptographic operations and encrypted message transmission.

## Key Components

### Files Involved

1. **C11162i.java** - Main protocol handler (InterfaceC11170q)
2. **C11173t.java** - Gen 2 session manager (extends AbstractC11179z)
3. **EnumC11122B.java** - Authentication state enum
4. **C11131K.java** - VAS request message builder
5. **AbstractC10637k.java** - Message builders (m13831L, m13829M, m13828N)
6. **AbstractC10829c.java** - Protobuf message processing
7. **AbstractC14833a.java** - Crypto manager
8. **C15277l.java** - HMAC-SHA256/AES-GCM crypto utilities
9. **RunnableC11129I.java** - Message encoding/transmission

### BLE Characteristics

- **UUID**: `52495649-414E-2052-4541-442043484152` (decoded: "RIVIAN READ CHAR")
- **PLAIN_DATA_IN_UUID** (f37409P) - Plaintext inbound messages
- **ENCRYPTED_DATA_IN_UUID** (f37411R) - Encrypted inbound messages
- **Other**: `f37410Q`, `f37412S`, `f37404K`, `f37405L`

## Authentication State Machine

The protocol progresses through 4 states:

```
INIT 
  ↓
PID_PNONCE_SENT      (Phone ID + Phone Nonce sent)
  ↓
SIGNED_PARAMS_SENT   (Signed parameters sent)
  ↓
AUTHENTICATED        (Authentication complete)
```

State is managed by: `EnumC11122B` enum
Stored in: `C11173t.f37492y` field

## Protocol Flow

### Phase 1: Initialization (INIT → PID_PNONCE_SENT)

**When**: Called from `m12543D()` in C11162i.java (line ~425)

1. **Generate Phone Nonce (pNonce)**
   - 16 random bytes generated via `SecureRandom.nextBytes()`
   - Stored in: `c11173t.f37503d` (session context field)
   - Code: `c11173t.f37503d = bArr;` (line 425)

2. **Build PID+PNONCE Message** 
   - Method: `AbstractC10637k.m13831L()` (line 434)
   - Inputs:
     - `phoneId`: UUID (16 bytes)
     - `sessionContext`: C11173t session manager
     - `num`: Optional integer (CSN/packet number)
   
   **Message Structure m13831L:**
   ```
   Protobuf Message:
   - field: CSN (int32) - Current sequence number
   - field: VehicleInfo
     - field: phoneId (bytes) - UUID in BIG_ENDIAN format (16 bytes)
   - field: QueryData
     - field: pNonce (bytes) - Phone nonce (16 bytes)
   ```

3. **Send Message**
   - Destination: `PLAIN_DATA_IN_UUID`
   - Message format: Protobuf serialized
   - State transition: `c11173t.m12511g(EnumC11122B.PID_PNONCE_SENT);`

### Phase 2: Vehicle Response Processing (PID_PNONCE_SENT)

**When**: Message received on `ENCRYPTED_DATA_IN_UUID` (line ~1270)

1. **Receive Vehicle Response**
   - Vehicle sends success/failure response
   - Response format: Protobuf with common field
   - Status check: `EnumC0828C.SUCCESS`

2. **Extract Vehicle Nonce (vNonce)**
   - Received in encrypted payload
   - Stored in: `c11173t.f37504e` (session context field)
   - Code: `c11173t.f37504e = m9153i;` (line 1226)
   - Size: Variable (extracted from protobuf)

### Phase 3: HMAC Computation (PID_PNONCE_SENT → SIGNED_PARAMS_SENT)

**When**: After receiving vNonce (line ~1792)

1. **Prepare HMAC Input**
   Method: `AbstractC10637k.m13827O()` (lines 968-1017)
   
   **HMAC-SHA256 Input Construction:**
   ```
   HMAC_Input = Concatenate(
       SerializedMessages,  // Protobuf serialized messages
       CSN (4 bytes, Big-Endian int),
       PhoneID (16 bytes, Big-Endian UUID),
       pNonce (16 bytes),
       vNonce (variable length),
   )
   ```

   **Exact Code Flow (line 1005):**
   ```java
   byte[] m12442p1 = AbstractC11199l.m12442p1(
       AbstractC11199l.m12442p1(
           m9153i,  // Serialized protobuf
           AbstractC15367g.m7363o(i)  // CSN as 4-byte Big-Endian
       ),
       AbstractC15367g.m7362p(abstractC11179z.f37501b, ByteOrder.BIG_ENDIAN)  // PhoneID
   );
   byte[] m12442p12 = AbstractC11199l.m12442p1(m12442p1, bArr);   // + pNonce
   byte[] m12442p13 = AbstractC11199l.m12442p1(m12442p12, bArr2); // + vNonce
   ```

2. **Compute HMAC-SHA256**
   Method: `AbstractC14833a.m7875b()` (line 1013)
   
   **Implementation (C15277l.java line 266):**
   ```java
   // Using Bouncy Castle HMAC-SHA256
   C8127e c8127e = new C8127e(new C5017y());  // SHA256 + HMAC wrapper
   byte[] bArr = new byte[c8127e.f26004b];    // 32-byte output
   c8127e.init(new C10062Q(secretKey, 0, secretKey.length));  // Secret key
   c8127e.update(message, 0, message.length);
   c8127e.doFinal(bArr, 0);
   ```
   
   **Crypto Details:**
   - Algorithm: HMAC-SHA256
   - Hash: SHA-256 (C5017y.java - Bouncy Castle implementation)
   - Output: 32 bytes (256 bits)
   - Secret Key: Derived from ECDH shared secret (via AbstractC14833a.m7873d())

3. **Build SIGNED_PARAMS Message**
   Method: `AbstractC10637k.m13829M()` (line 1792)
   
   **Message Structure m13829M:**
   ```
   Protobuf Message:
   - field: CSN (int32)
   - field: SignedData
     - field: Messages (repeated bytes) - Empty list
   - field: EncryptedData (encrypted)
   ```

4. **Send Message**
   - Destination: `PLAIN_DATA_IN_UUID`
   - State transition: `c11173t.m12511g(EnumC11122B.SIGNED_PARAMS_SENT);`

### Phase 4: Final Authentication (SIGNED_PARAMS_SENT → AUTHENTICATED)

**When**: Final response received (line ~1286)

1. **Receive Final Response**
   - Vehicle confirms HMAC validation
   - Status check: `EnumC0828C.SUCCESS`

2. **Authentication Complete**
   - State transition: `c11173t.m12511g(EnumC11122B.AUTHENTICATED);`
   - Flag set: `c11173t.f37488u = true;`
   - Session stored in secure storage

## Message Formats

### Message Structure Overview

All messages use Google Protocol Buffers (protobuf) serialization.

#### Message Type 1: PID+PNONCE (m13831L)

```
Message: C14685f0 (VASMessage)
├── field: CSN (int32)
│   └── Current sequence number
├── field: VehicleInfo (C16487k)
│   └── field: phoneId (bytes)
│       └── UUID in BIG_ENDIAN (16 bytes)
└── field: QueryData (C18631q)
    └── field: pNonce (bytes)
        └── 16-byte random nonce from SecureRandom
```

#### Message Type 2: SIGNED_PARAMS (m13829M)

```
Message: C14685f0 (VASMessage)
├── field: CSN (int32)
├── field: QueryData (C18631q)
│   └── Empty payload
├── field: SignedData (C16297j0)
│   ├── field: Messages (repeated)
│   │   └── Empty list
│   └── field: Serialized (bytes)
│       └── Serialized protobuf (m9214k())
└── field: EncryptedData (C23135y0)
    ├── field: Payload (bytes)
    │   └── Encrypted message
    ├── field: PacketNumber (int32)
    │   └── Sequence number
    ├── field: IsPayloadEncrypted (bool)
    ├── field: IsDataMissing (bool)
    └── field: Signature (C21983w0)
        ├── field: algorithm (EnumC21553v0)
        │   └── HMAC_SHA256
        └── field: signature (bytes)
            └── 32-byte HMAC output
```

#### Message Type 3: ENCRYPTED_DATA_IN (vNonce Response)

```
Message: C15224h0 (EncryptedMessage)
├── field: EncryptedPayload (C23135y0)
│   ├── field: Payload (bytes)
│   │   └── Encrypted data
│   ├── field: PacketNumber (int32)
│   ├── field: Signature (C21983w0)
│   │   └── HMAC-SHA256 signature
│   └── ... (other fields)
└── field: Common (C0335B)
    └── field: status (EnumC0828C)
        └── SUCCESS or error code
```

## Cryptographic Operations

### HMAC-SHA256 Implementation

**Location**: C15277l.java::m7537F() (line 266)

```java
public static byte[] m7537F(byte[] message, byte[] secretKey) {
    // Bouncy Castle HMAC wrapper with SHA-256
    C8127e c8127e = new C8127e(new C5017y());  // C5017y = SHA256 digest
    byte[] bArr = new byte[c8127e.f26004b];     // 32 bytes output
    c8127e.init(new C10062Q(secretKey, 0, secretKey.length));
    c8127e.update(message, 0, message.length);
    c8127e.doFinal(bArr, 0);
    return bArr;
}
```

**Components:**
- **C8127e** - HMAC processor (Bouncy Castle wrapper)
- **C5017y** - SHA-256 digest (Bouncy Castle SHA256 implementation)
- **Output Size**: 32 bytes
- **Key Size**: Variable (typically 32 bytes from ECDH)
- **Message Size**: Variable

### Secret Key Derivation

**Location**: AbstractC14833a.java::m7873d() (line 81)

The secret key is derived from ECDH key agreement:

```java
byte[] m7523j = c15277l.m7523j(userId, vehiclePublicKey);
```

**Process:**
1. Takes user ID and vehicle's ECDH public key (130 hex chars = 65 bytes uncompressed point)
2. Performs ECDH key agreement to generate shared secret
3. Returns 32-byte secret key for HMAC

**Validation:**
- Vehicle public key must be exactly 130 characters (hex)
- Must start with "04" (uncompressed EC point indicator)
- Uses EC curve parameters (implied P-256 or similar)

### Byte Concatenation

**Location**: AbstractC11199l.java::m12442p1() (line 369)

```java
public static byte[] m12442p1(byte[] bArr, byte[] bArr2) {
    int length = bArr.length;
    int length2 = bArr2.length;
    byte[] copyOf = Arrays.copyOf(bArr, length + length2);
    System.arraycopy(bArr2, 0, copyOf, length, length2);
    return copyOf;
}
```

Simple byte array concatenation with no encoding or padding.

### Integer Encoding

**Location**: AbstractC15367g.java (utilities)

- `m7363o(int i)` - Converts int to 4-byte Big-Endian
- `m7362p(UUID uuid, ByteOrder order)` - Converts UUID to 16-byte array with specified byte order

## Data Fields in Session Context (C11173t)

```
f37485r (UUID)      - Vehicle ID
f37486s             - Secured storage reference
f37487t (boolean)   - Flag 1
f37488u (boolean)   - isAuthed flag
f37489v (boolean)   - Flag 2
f37490w (boolean)   - isRanging flag
f37491x (boolean)   - 2FD flag
f37492y (EnumC11122B) - Authentication state
f37503d (byte[])    - pNonce (Phone Nonce, 16 bytes)
f37504e (byte[])    - vNonce (Vehicle Nonce, variable)
f37505f (List)      - Command queue
f37506g (int)       - CSN counter (incremented by 2)
f37508i (Integer)   - Last received CSN
```

## Key Differences from Gen 1 (LEGACY)

### Gen 1 (LEGACY) Protocol
- Uses different message structure
- Different state machine
- May use different cryptographic parameters
- Simpler authentication flow

### Gen 2 (PRE_CCC) Protocol
1. **More Complex State Management**: 4-state machine vs simpler Gen 1
2. **HMAC Validation**: Requires HMAC-SHA256 signature on all messages
3. **Nonce Exchange**: Explicit pNonce and vNonce exchange
4. **Message Encryption**: Uses encrypted payload with AES (derived from HMAC key)
5. **CSN Counter**: Packet sequence numbering with even/odd increments
6. **Protobuf Serialization**: Uses complex nested protobuf structures
7. **ECDH Key Agreement**: Derives encryption key from EC key agreement

### Protocol Determination
Detected via `EnumC11140U` enum:
- `PRE_CCC` = Gen 2 (this analysis)
- `LEGACY` = Gen 1

Code checks: `if (c11173t.f37500a != EnumC11140U.PRE_CCC)` to differentiate

## Passive Entry (Smart Key) Usage

### RunnableC11129I.java Usage
The protocol also supports "Passive Entry" for keyless entry:

```java
C11131K c11131k = new C11131K(
    EnumC11133M.PASSIVE_ENTRY,  // Message type
    c11130j.f37293k,            // Packet number
    this.f37276c,               // Phone ID
    this.f37277d,               // Vehicle ID
    bArr2,                       // pNonce
    bArr,                        // vNonce
    new byte[]{(byte) this.f37275b}  // RSSI value
);
byte[] m14019f0 = AbstractC10624g.m14019f0(c11131k);  // Serialize
c11169p.m12517i(uuid, C11130J.f37282m, m14019f0, 
    (c11169p.f37482o || c11130j.f37283a) ? 2 : 1, 
    this.f37278e, "PASSIVE_ENTRY");
```

This is a separate usage path for vehicle control after authentication is complete.

## Security Considerations

1. **Random Number Generation**: Uses `SecureRandom` for nonce generation
2. **HMAC Verification**: All messages validated with HMAC-SHA256
3. **Key Agreement**: Uses EC (Elliptic Curve) cryptography
4. **Byte Order**: BIG_ENDIAN consistently used for multi-byte fields
5. **Encryption**: AES-GCM derived from HMAC-SHA256 output (line 77 in AbstractC14833a)

## Error Handling

**Main error codes** (EnumC0828C):
- SUCCESS - Authentication successful
- Various error codes for protocol failures

**Failure paths**:
- Invalid HMAC signature
- Missing nonces (null checks on line 1727, 1776)
- CSN mismatch
- Connection loss

## Timeouts and Retries

- Main authentication timeout: 60 seconds (line 421)
- Message retry: Different for Gen1 vs Gen2
  - Gen2: Immediate (null) if using PRE_CCC
  - Gen1: 7000ms delay

