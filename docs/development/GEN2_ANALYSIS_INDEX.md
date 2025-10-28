# Gen 2 (PRE_CCC) BLE Pairing Protocol - Analysis Documentation Index

This directory contains comprehensive analysis of the Gen 2 (PRE_CCC) BLE pairing protocol used by Rivian vehicles for secure Bluetooth Low Energy communication.

## Documentation Files

### 1. GEN2_BLE_PROTOCOL_ANALYSIS.md (12 KB)
**Purpose**: Complete technical deep-dive into the protocol

**Contents**:
- Overview of protocol architecture
- Key components and file references
- Authentication state machine (4 states)
- Detailed protocol flow for all 4 phases
- Complete message format specifications
- Cryptographic operations (HMAC-SHA256, ECDH)
- Session context field definitions
- Differences from Gen 1 (LEGACY) protocol
- Passive Entry (Smart Key) extension
- Security considerations
- Error handling mechanisms

**Best for**: 
- Understanding complete protocol mechanics
- Implementation reference
- Security analysis
- Debugging protocol issues

**Line count**: ~800 lines

---

### 2. GEN2_PROTOCOL_SUMMARY.md (21 KB)
**Purpose**: Quick reference guide with visual diagrams

**Contents**:
- Sequence diagram showing message flow
- State machine visual representation
- Message byte layout specifications
- HMAC-SHA256 computation flow
- ECDH key derivation process
- BLE characteristic usage
- Session context field table
- Code location reference guide
- Comparison table: Gen 1 vs Gen 2
- Message size approximations
- Error condition reference

**Best for**:
- Quick lookups during implementation
- Visual understanding of flow
- Finding specific code locations
- Understanding message formats

**Special Features**:
- ASCII diagrams for visual learners
- Code cross-references
- Byte layout diagrams

---

### 3. PROTOCOL_ANALYSIS_SUMMARY.txt (18 KB)
**Purpose**: Comprehensive text summary suitable for all readers

**Contents**:
- Executive summary of protocol
- State definitions and transitions
- Detailed message structure descriptions
- Cryptographic algorithms and implementations
- HMAC-SHA256 step-by-step breakdown
- ECDH algorithm details
- Session context field reference
- BLE characteristics reference
- Code reference locations with line numbers
- Gen 1 vs Gen 2 comparison table
- Security analysis (strengths and considerations)
- Error handling guide
- Protocol timing and flow control
- Passive Entry extension details
- Files analyzed list
- Implementation notes for Python client

**Best for**:
- Comprehensive reference
- Print-friendly format
- Non-visual learners
- Implementation planning

**Line count**: ~550 lines

---

### 4. GEN2_ANALYSIS_INDEX.md
**Purpose**: This file - navigation guide for all analysis documents

---

## Quick Navigation

### I need to understand...

**...how the protocol works overall**
→ Read: GEN2_BLE_PROTOCOL_ANALYSIS.md (Overview section)

**...the 4-state authentication flow**
→ Read: GEN2_PROTOCOL_SUMMARY.md (Sequence Diagram & State Machine)

**...the exact message formats**
→ Read: GEN2_BLE_PROTOCOL_ANALYSIS.md (Message Formats section)
→ Also: GEN2_PROTOCOL_SUMMARY.md (Message Byte Layout)

**...how HMAC-SHA256 is computed**
→ Read: GEN2_BLE_PROTOCOL_ANALYSIS.md (Cryptographic Operations section)
→ Also: PROTOCOL_ANALYSIS_SUMMARY.txt (HMAC-SHA256 COMPUTATION)

**...how ECDH key derivation works**
→ Read: PROTOCOL_ANALYSIS_SUMMARY.txt (KEY DERIVATION section)
→ Also: GEN2_PROTOCOL_SUMMARY.md (Key Derivation diagram)

**...which Java files contain the implementation**
→ Read: GEN2_PROTOCOL_SUMMARY.md (Important Code Locations)
→ Also: PROTOCOL_ANALYSIS_SUMMARY.txt (CODE REFERENCE LOCATIONS)

**...how Gen 2 differs from Gen 1**
→ Read: GEN2_BLE_PROTOCOL_ANALYSIS.md (Key Differences from Gen 1 section)
→ Also: GEN2_PROTOCOL_SUMMARY.md (Key Differences table)
→ Also: PROTOCOL_ANALYSIS_SUMMARY.txt (GEN 1 vs GEN 2 COMPARISON)

**...how to implement this in Python**
→ Read: PROTOCOL_ANALYSIS_SUMMARY.txt (IMPLEMENTATION NOTES FOR PYTHON CLIENT)

**...error conditions and handling**
→ Read: GEN2_BLE_PROTOCOL_ANALYSIS.md (Error Handling section)
→ Also: PROTOCOL_ANALYSIS_SUMMARY.txt (ERROR HANDLING section)

**...the complete state machine**
→ Read: GEN2_PROTOCOL_SUMMARY.md (State Machine diagram)

**...session context fields**
→ Read: GEN2_PROTOCOL_SUMMARY.md (Session Context Fields)
→ Also: PROTOCOL_ANALYSIS_SUMMARY.txt (SESSION CONTEXT FIELDS (C11173t))

**...BLE characteristics**
→ Read: GEN2_PROTOCOL_SUMMARY.md (BLE Characteristic Usage)
→ Also: PROTOCOL_ANALYSIS_SUMMARY.txt (BLE CHARACTERISTICS)

---

## Key Findings Summary

### Protocol Overview
- **Type**: 4-state authentication protocol
- **Crypto**: HMAC-SHA256 + ECDH (P-256)
- **Security Level**: 256-bit (HMAC output, ECDH shared secret)
- **Message Format**: Google Protocol Buffers
- **Transport**: Bluetooth Low Energy (BLE)

### Authentication States
1. **INIT** (0) → Send Phone ID + Phone Nonce
2. **PID_PNONCE_SENT** (1) → Receive Vehicle Nonce
3. **SIGNED_PARAMS_SENT** (2) → Send HMAC Signature
4. **AUTHENTICATED** (3) → Authentication Complete ✓

### Core Cryptographic Operations

**Phase 1**: Generate 16-byte random nonce (pNonce)
- Source: `SecureRandom.nextBytes()`
- Storage: `c11173t.f37503d`

**Phase 2**: Receive vehicle nonce (vNonce)
- Received: Vehicle response message
- Storage: `c11173t.f37504e`

**Phase 3**: Compute HMAC-SHA256
- Input: Protobuf || CSN || phoneId || pNonce || vNonce
- Key: ECDH-derived 32-byte shared secret
- Output: 32-byte HMAC value
- Algorithm: Bouncy Castle (C8127e + C5017y)

**Phase 4**: Transmit SIGNED_PARAMS with HMAC
- Vehicle validates HMAC
- Success → AUTHENTICATED state

### Key Cryptographic Details

**HMAC Algorithm**: HMAC-SHA256
- Hash: SHA-256 (256-bit output)
- Key: 32 bytes (from ECDH)
- Implementation: Bouncy Castle library

**Key Derivation**: ECDH (Elliptic Curve Diffie-Hellman)
- Curve: P-256 (NIST/secp256r1)
- Key Agreement: m * V (private key × public key)
- Output: 32-byte shared secret
- Validation: Vehicle public key must be 130 hex chars, start with "04"

**Byte Ordering**: BIG_ENDIAN (network byte order)
- UUID: 16 bytes
- CSN: 4 bytes
- All multi-byte fields use BIG_ENDIAN

### Message Sizes (Approximate)
- PID + pNonce: ~40-60 bytes
- vNonce Response: ~40-100 bytes
- SIGNED_PARAMS: ~60-80 bytes
- Final Auth: ~20-40 bytes

### Important Code Locations

**Main handler**: `/java_src/p638aj/C11162i.java`
- Line 425: Start authentication (pNonce generation)
- Line 1270: Receive vNonce response
- Line 1792: Compute HMAC and send SIGNED_PARAMS
- Line 1824: Complete authentication

**Message builders**: `/java_src/p617Zf/AbstractC10637k.java`
- Line 742: m13831L() - PID + pNonce
- Line 846: m13829M() - Empty SignedData
- Line 968: m13827O() - HMAC computation

**Crypto**: `/java_src/p784h4/C15277l.java`
- Line 266: m7537F() - HMAC-SHA256 core

---

## Comparison: Gen 1 vs Gen 2

| Feature | Gen 1 (LEGACY) | Gen 2 (PRE_CCC) |
|---------|---|---|
| States | 2-3 | 4 |
| Nonces | Implicit | Explicit (pNonce + vNonce) |
| HMAC | Optional | Required on all |
| Format | Binary | Protobuf |
| Encryption | Basic AES | AES-GCM |
| Key Derivation | Simple | ECDH + HMAC |
| CSN Counter | +1 | +2 |
| Timeout | 7000ms retry | 60s overall |
| Complexity | Low | Higher |

---

## Security Notes

### Strengths ✓
- HMAC-SHA256 for message authentication
- ECDH for key agreement
- SecureRandom for nonce generation
- BIG_ENDIAN consistency
- 32-byte secret keys
- Session-based tracking
- CSN sequence numbering

### Considerations ⚠
- Nonce validation not explicitly shown
- Protobuf complexity may hide logic
- Key caching (potential side-channel)
- No visible rate limiting
- Error messages may leak info

---

## Files Analyzed

**Main Protocol Implementation**:
- `C11162i.java` - Main protocol handler
- `C11173t.java` - Gen 2 session manager
- `EnumC11122B.java` - Authentication states
- `AbstractC11179z.java` - Base session class

**Message Building**:
- `AbstractC10637k.java` - Message builders
- `C11131K.java` - VAS request message
- `AbstractC10829c.java` - Protobuf utilities

**Cryptography**:
- `AbstractC14833a.java` - Crypto manager
- `C15277l.java` - HMAC implementation
- `C5017y.java` - SHA-256 digest
- `C8127e.java` - HMAC wrapper
- `AbstractC11199l.java` - Byte utilities

---

## Document Versions

All documents generated on: 2025-10-25

**Analysis Source**: 
- Rivian Android App (com.rivian.android.consumer)
- Decompiled Java source code
- Protocol reverse engineering

**Scope**: 
- Gen 2 (PRE_CCC) BLE pairing protocol only
- Complete cryptographic analysis
- Message format specification
- Implementation reference

---

## How to Use These Documents

1. **First Time**: Start with GEN2_PROTOCOL_SUMMARY.md for visual overview
2. **Implementation**: Use PROTOCOL_ANALYSIS_SUMMARY.txt as reference
3. **Deep Dive**: Consult GEN2_BLE_PROTOCOL_ANALYSIS.md for details
4. **Navigation**: Use this index to find information quickly

---

## Next Steps

To implement this protocol in Python:

1. Study the message formats (HMAC-SHA256 input composition)
2. Understand the state machine (4 states)
3. Implement protobuf message deserialization
4. Set up ECDH key agreement (use `cryptography` library)
5. Implement HMAC-SHA256 (use `hmac` and `hashlib`)
6. Handle BLE communication (use `bleak`)
7. Manage session state and timeouts

Refer to "IMPLEMENTATION NOTES FOR PYTHON CLIENT" section in PROTOCOL_ANALYSIS_SUMMARY.txt for detailed guidance.

---

**For questions or clarifications, refer to the detailed analysis documents above.**

