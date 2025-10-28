# Gen 2 (PRE_CCC) BLE Pairing Protocol - Quick Reference

## Protocol Sequence Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    GEN 2 (PRE_CCC) BLE PAIRING FLOW                      │
└─────────────────────────────────────────────────────────────────────────┘

Phone                                                    Vehicle
  │                                                         │
  │ 1. Generate pNonce (16 bytes random)                   │
  │    State: INIT                                         │
  │    Storage: c11173t.f37503d                           │
  │                                                         │
  ├──── [PLAIN_DATA_IN] PID + pNonce ─────────────────────→ │ 2. Receive PID+pNonce
  │     Message: m13831L (Protobuf)                        │    Extract phone ID
  │     - CSN (sequence number)                           │
  │     - phoneId (UUID, 16 bytes, BIG_ENDIAN)           │
  │     - pNonce (16 bytes random)                        │
  │                                                         │
  │     State: PID_PNONCE_SENT                            │ 3. Generate vNonce (16 bytes)
  │                                                         │    Derive ECDH secret
  │                                                         │    Store: c11173t.f37504e
  │ 4. Receive vNonce ←───── [ENCRYPTED_DATA_IN] vNonce ──┤
  │    Storage: c11173t.f37504e                           │
  │    Status: SUCCESS check                              │
  │                                                         │
  │ 5. Compute HMAC-SHA256:                               │
  │    Input = Concat(                                    │
  │      Protobuf_Serialized,                             │
  │      CSN (4 bytes, BE),                               │
  │      phoneId (16 bytes, BE),                          │
  │      pNonce (16 bytes),                               │
  │      vNonce (variable)                                │
  │    )                                                   │
  │    Output = 32 bytes HMAC                             │
  │                                                         │
  ├──── [PLAIN_DATA_IN] SIGNED_PARAMS ───────────────────→ │ 6. Receive SIGNED_PARAMS
  │     Message: m13829M (Protobuf)                       │    Verify HMAC signature
  │     - CSN                                             │    (Match against vehicle's)
  │     - Empty SignedData.Messages                       │    
  │     - Signature (32-byte HMAC)                        │ 7. HMAC validation
  │                                                         │    SUCCESS ✓
  │     State: SIGNED_PARAMS_SENT                         │
  │                                                         │
  │ 8. Receive AUTH_SUCCESS ←──── [ENCRYPTED_DATA_IN] ───┤
  │    Status: SUCCESS                                    │
  │                                                         │
  │    State: AUTHENTICATED ✓                             │
  │    f37488u = true                                     │
  │    Session stored in secure storage                   │
  │                                                         │
  └─────────────────────────────────────────────────────────────────────────┘
```

## State Machine

```
    ┌──────────┐
    │   INIT   │
    └────┬─────┘
         │ m12543D() - startAuthenticationProcess()
         │ Generate 16-byte pNonce
         │ Build m13831L message
         │
         ▼
    ┌──────────────────────┐
    │ PID_PNONCE_SENT      │
    │                      │
    │ Waiting for vNonce   │
    └────┬─────────────────┘
         │ onReceiveMessage() - ENCRYPTED_DATA_IN
         │ Extract vNonce from response
         │
         ▼
    ┌──────────────────────┐
    │ SIGNED_PARAMS_SENT   │
    │                      │
    │ HMAC Verification    │
    │ Build m13829M msg    │
    └────┬─────────────────┘
         │ onReceiveMessage() - Final response
         │ Status check: SUCCESS
         │
         ▼
    ┌──────────────────────┐
    │  AUTHENTICATED ✓     │
    │                      │
    │ Session active       │
    │ Ready for commands   │
    └──────────────────────┘
```

## Message Byte Layout

### Message 1: PID + PNONCE (m13831L)

```
┌─────────────────────────────────────────────────────────────┐
│ Protobuf Message: C14685f0 (VASMessage)                    │
├─────────────────────────────────────────────────────────────┤
│ [Varint] CSN (variable length, typically 1-4 bytes)        │
│          Example: 0x01 (for first message)                  │
├─────────────────────────────────────────────────────────────┤
│ [Field: VehicleInfo]                                        │
│   ├─ [Bytes, Length-prefixed] phoneId                       │
│   │  └─ 16 bytes: UUID in BIG_ENDIAN format                │
│   │     Example: 550e8400-e29b-41d4-a716-446655440000 →    │
│   │     0x550e8400e29b41d4a716446655440000                │
│   └─ ...                                                     │
├─────────────────────────────────────────────────────────────┤
│ [Field: QueryData]                                          │
│   ├─ [Bytes, Length-prefixed] pNonce                        │
│   │  └─ 16 bytes: Random from SecureRandom()                │
│   │     Example: 0x1a2b3c4d5e6f70819a0b1c2d3e4f5061       │
│   └─ ...                                                     │
└─────────────────────────────────────────────────────────────┘
```

### HMAC-SHA256 Input Composition

```
┌──────────────────────────────────────────────────────────────┐
│ HMAC INPUT BUFFER (variable length)                          │
├──────────────────────────────────────────────────────────────┤
│ [Variable] Serialized Protobuf Messages                      │
│            (output of m9214k())                              │
├──────────────────────────────────────────────────────────────┤
│ [4 bytes]  CSN in BIG_ENDIAN format                          │
│            Example CSN=1: 0x00 0x00 0x00 0x01               │
├──────────────────────────────────────────────────────────────┤
│ [16 bytes] Phone UUID in BIG_ENDIAN                          │
│            Fixed 16-byte UUID                                │
├──────────────────────────────────────────────────────────────┤
│ [16 bytes] Phone Nonce (pNonce)                              │
│            Random 16 bytes from init                         │
├──────────────────────────────────────────────────────────────┤
│ [Variable] Vehicle Nonce (vNonce)                            │
│            Variable length, from vehicle response            │
├──────────────────────────────────────────────────────────────┤
│ [32 bytes] HMAC-SHA256(Input, SecretKey) ← OUTPUT            │
│            Fixed 256-bit (32-byte) output                    │
└──────────────────────────────────────────────────────────────┘
```

## Cryptographic Details

### HMAC-SHA256 Computation

```
┌────────────────────────────────────────────────────────────┐
│              HMAC-SHA256 PROCESSING                         │
├────────────────────────────────────────────────────────────┤
│ Input:                                                      │
│   - Message: [Composed buffer above]                       │
│   - Key: ECDH-derived 32-byte secret                       │
│                                                             │
│ Algorithm:                                                  │
│   1. Initialize HMAC with SHA-256 (Bouncy Castle)          │
│      └─ C8127e wrapper + C5017y (SHA256 digest)            │
│   2. Process key: 32 bytes                                  │
│   3. Update message: concatenated buffer                    │
│   4. Finalize: doFinal(bArr, 0)                            │
│                                                             │
│ Output:                                                     │
│   - 32-byte HMAC value                                      │
│   - Hex format: 6a4c2d8e... (64 hex chars)                 │
│   - Embedded in Signature field of message                  │
└────────────────────────────────────────────────────────────┘
```

### Key Derivation (ECDH)

```
┌────────────────────────────────────────────────────────────┐
│         ELLIPTIC CURVE DIFFIE-HELLMAN (ECDH)               │
├────────────────────────────────────────────────────────────┤
│ Phone Side:                                                 │
│   - Private Key: m (random)                                 │
│   - Public Key: P_phone = m * G                             │
│   - Vehicle Public: P_vehicle (130 hex chars)              │
│   - Shared Secret: S = m * P_vehicle                        │
│                                                             │
│ Vehicle Side:                                              │
│   - Private Key: n (random)                                │
│   - Public Key: P_vehicle = n * G                          │
│   - Phone Public: P_phone (sent in message)                │
│   - Shared Secret: S = n * P_phone                         │
│                                                             │
│ Both derive same S (256 bits = 32 bytes)                   │
│ Used as HMAC secret key                                    │
│                                                             │
│ Note: Vehicle public key validation:                       │
│   - Must be exactly 130 hex characters                     │
│   - Must start with "04" (uncompressed point)              │
│   - Uses standard EC curve (P-256 or equivalent)           │
└────────────────────────────────────────────────────────────┘
```

## BLE Characteristic Usage

```
┌─────────────────────────────────────────────────────────┐
│              BLE CHARACTERISTICS                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│ SERVICE UUID: 52495649-414E-2052-4541-442043484152     │
│              (ASCII: "RIVIAN READ CHAR")               │
│                                                          │
│ CHARACTERISTICS:                                        │
│                                                          │
│ 1. PLAIN_DATA_IN (Write)                               │
│    └─ Unencrypted outbound messages                    │
│    └─ Used for: PID+pNonce, SIGNED_PARAMS             │
│    └─ Max: BLE MTU (typically 20-512 bytes)            │
│                                                          │
│ 2. ENCRYPTED_DATA_IN (Read/Notify)                     │
│    └─ Encrypted inbound messages                       │
│    └─ Used for: vNonce response, auth completion       │
│    └─ Includes HMAC signature verification             │
│                                                          │
│ 3. Other characteristics:                               │
│    ├─ f37410Q                                           │
│    ├─ f37412S                                           │
│    ├─ f37404K                                           │
│    └─ f37405L (UUID used for capability check)         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

## Session Context Fields

```
┌──────────────────────────────────────────────────────────┐
│            C11173t SESSION CONTEXT (Gen 2)               │
├──────────────────────────────────────────────────────────┤
│ f37485r: UUID                  Vehicle ID                │
│ f37486s: Storage               Secure storage ref        │
│ f37488u: boolean (isAuthed)    Auth status flag         │
│ f37490w: boolean (isRanging)   Distance measurement     │
│ f37491x: boolean (2FD)         Second-factor device     │
│ f37492y: EnumC11122B           Current auth state       │
│ f37501b: UUID                  Phone ID                  │
│ f37503d: byte[] (pNonce)       Phone nonce (16 bytes)   │
│ f37504e: byte[] (vNonce)       Vehicle nonce (var len)  │
│ f37505f: List<C9482d>          Command queue            │
│ f37506g: int (CSN counter)     Sequence counter (±2)    │
│ f37508i: int                   Last received CSN        │
│ f37516q: int                   Message packet counter    │
│                                                          │
│ States (f37492y):                                       │
│   0: INIT                                               │
│   1: PID_PNONCE_SENT                                    │
│   2: SIGNED_PARAMS_SENT                                 │
│   3: AUTHENTICATED                                      │
└──────────────────────────────────────────────────────────┘
```

## Important Code Locations

```
File: C11162i.java (Main Protocol Handler)
├─ m12543D()              Line ~425  - Start auth, generate pNonce
├─ m13831L() [builder]    Line ~434  - Build PID+pNonce msg
├─ onReceiveMessage()     Line ~1270 - Process vNonce response
├─ m13829M() [builder]    Line ~1792 - Build SIGNED_PARAMS msg
└─ m12530v()              Line ~1824 - Complete authentication

File: AbstractC10637k.java (Message Builders)
├─ m13831L()              Line ~742  - PID + pNonce message
├─ m13829M()              Line ~846  - Empty SignedData
├─ m13828N()              Line ~875  - Encrypted wrapper
└─ m13827O()              Line ~968  - HMAC computation & wrapping

File: AbstractC14833a.java (Crypto Manager)
├─ m7875b()               Line ~60   - HMAC-SHA256 wrapper
├─ m7874c()               Line ~75   - Set secret key
├─ m7873d()               Line ~81   - ECDH key derivation
└─ m7876a()               Line ~45   - Per-session encryption

File: C15277l.java (HMAC Implementation)
└─ m7537F()               Line ~266  - HMAC-SHA256 core

File: C5017y.java (SHA-256 Digest)
└─ mo18075d()             Line ~80   - SHA256 block processing
```

## Key Differences: Gen 2 vs Gen 1

```
┌────────────────────┬──────────────────┬──────────────────────┐
│ Aspect             │ Gen 1 (LEGACY)   │ Gen 2 (PRE_CCC)      │
├────────────────────┼──────────────────┼──────────────────────┤
│ State Machine      │ Simpler (2-3)    │ 4 states             │
│ Nonce Exchange     │ Implicit/Simple  │ Explicit (pNonce,    │
│                    │                  │  vNonce)             │
│ HMAC Validation    │ Optional/Simple  │ Required on all msgs │
│ Serialization      │ Simple format    │ Google Protobuf      │
│ Encryption         │ Basic AES        │ AES-GCM derived      │
│ Key Derivation     │ Direct/Simple    │ ECDH + HMAC derived  │
│ Message Size       │ Smaller          │ Larger (protobufs)   │
│ CSN Counter        │ Simple +1        │ +2 (even/odd)        │
│ Timeout            │ 7000ms retry     │ 60s overall          │
│ Curve              │ Likely P-256     │ P-256 (ECDH)         │
└────────────────────┴──────────────────┴──────────────────────┘
```

## Message Flow with Sizes (Approximate)

```
Phase 1: PID + pNonce → Vehicle
  Message: ~40-60 bytes (protobuf)
    [CSN: 1-4 bytes]
    [phoneId: 16 bytes]
    [pNonce: 16 bytes]
    [overhead: 8-12 bytes]

Phase 2: Vehicle → vNonce Response
  Message: ~40-100+ bytes (encrypted)
    [vNonce: 16-32+ bytes]
    [status: 4-8 bytes]
    [overhead: 20+ bytes]
    [HMAC sig: 32 bytes]

Phase 3: SIGNED_PARAMS → Vehicle
  Message: ~60-80 bytes (protobuf)
    [CSN: 1-4 bytes]
    [HMAC signature: 32 bytes]
    [metadata: 20+ bytes]

Phase 4: Final Auth Success ← Vehicle
  Message: ~20-40 bytes
    [Status: SUCCESS]
    [optional data]
```

## Error Conditions

```
HMAC Mismatch
├─ Computed HMAC ≠ Vehicle HMAC
├─ Log: "error: hmac validation failed"
└─ State: Timeout/Retry

Missing Nonce
├─ pNonce or vNonce is null
├─ Log: "null pNonce while validating vid and vNonce"
└─ Validation: c11173t.f37503d != null && c11173t.f37504e != null

CSN Mismatch
├─ Received CSN ≠ Expected CSN
├─ CSN stored in: f37508i
└─ Validation: Integer.compare()

Connection Loss
├─ BLE device disconnects during auth
├─ Timeout: 60 seconds (line 421)
└─ Cleanup: m12534r()
```

