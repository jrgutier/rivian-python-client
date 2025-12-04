# Parallax Protocol Implementation Audit Request

## Context

I've implemented Rivian's Parallax cloud-based vehicle command protocol in Python by reverse-engineering the official Android APK (`com.rivian.android.consumer` v3.6.0). The implementation appears technically correct but returns server errors.

## Current Error Status

Testing with live credentials on vehicle `cc41fc6c8fafd6e0030cfed1d04666e3`:

- **1 RVM type** (Climate Hold Status): `OMS_ERROR` - reaches backend
- **20 RVM types**: `INTERNAL_SERVER_ERROR` - feature not available

## What I've Verified ✓

1. **Protobuf Serialization**: Matches Android app exactly
   - Example: 7200 seconds → `08a038` (hex) → `CKA4` (Base64)

2. **GraphQL Mutation Structure**: Identical to Android app
   - Matches `C19629S8.java` line 75 exactly

3. **RVM Type Strings**: All 18 match `EnumC6207c.java` lines 126-143

4. **Authentication**: Session-based (cookies), NOT Bearer tokens
   - Adding Bearer token makes errors worse

## Question for Analysis

**Why are we getting these errors when the implementation matches the Android app exactly?**

Please audit the following files and identify any discrepancies:

### Files to Analyze

1. **Python Implementation**:
   - `src/rivian/parallax.py` - Helper functions and RVM enum
   - `src/rivian/rivian.py` (send_parallax_command method, ~line 1466)
   - `src/rivian/proto/rivian_climate_pb2.py` - Generated protobuf

2. **Android APK Reference**:
   - `com.rivian.android.consumer/java_src/sh/C19629S8.java` - Mutation class
   - `com.rivian.android.consumer/java_src/p355O9/EnumC6207c.java` - RVM enum
   - `com.rivian.android.consumer/java_src/p979qj/*` - Climate protobuf classes

3. **Test Results**:
   - `PARALLAX_TEST_RESULTS.md` - Detailed error analysis
   - `BEARER_TOKEN_TEST_RESULTS.md` - Auth testing

## Specific Areas to Check

1. **Missing Request Parameters**
   - Are there hidden/undocumented parameters in the Android app?
   - Does the Android app send additional metadata/context?
   - Are there required headers we're missing?

2. **Protobuf Message Structure**
   - Are we using the correct protobuf message types?
   - Are there wrapper messages or nested structures we missed?
   - Field numbers, types, and encoding correct?

3. **GraphQL Request Format**
   - Operation name correct? (`SendRemoteCommand`)
   - Variable names match? (`vehicleId`, `model`, `parallaxPayloadB64`)
   - Meta object structure complete?

4. **Vehicle State Requirements**
   - Does the Android app check vehicle state before sending?
   - Are there preconditions (awake, parked, charging, etc.)?
   - Context-dependent RVM availability?

5. **Session/Authentication**
   - Are we using the correct session tokens?
   - Does the Android app refresh tokens before Parallax calls?
   - Any special authentication flow for Parallax?

## Expected Output

Please provide:

1. **Identified Discrepancies**: Concrete differences between our implementation and the Android app
2. **Missing Elements**: Parameters, headers, checks, or context we may have overlooked
3. **Root Cause Analysis**: Why `OMS_ERROR` vs `INTERNAL_SERVER_ERROR` for different RVM types
4. **Recommendations**: Specific changes to fix the implementation

## Files Attached

I'll provide the key files in the next messages.
