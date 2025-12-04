# Rivian API Audit - mitmproxy Traffic Analysis
**Date:** October 27, 2025
**Source:** iOS Rivian App v4400 traffic via mitmproxy
**Compared Against:** rivian-python-client codebase

## Executive Summary

This audit compares live Rivian iOS app (v4400) traffic captured via mitmproxy against the current rivian-python-client implementation. The analysis reveals several missing GraphQL operations, new API endpoints, and updated client version headers.

## Key Findings

### 1. New API Endpoints Discovered

The iOS app uses **three separate GraphQL endpoints**:

| Endpoint | Purpose | Status in Client |
|----------|---------|------------------|
| `https://rivian.com/api/gql/gateway/graphql` | Main gateway | ✅ **Implemented** |
| `https://rivian.com/api/vs/gql-gateway` | Vehicle services | ❌ **Missing** |
| `https://rivian.com/api/gql/content/graphql` | Content/chat services | ❌ **Missing** |

**Recommendation:** Add constants for the new endpoints:
```python
GRAPHQL_VEHICLE_SERVICES = "https://rivian.com/api/vs/gql-gateway"
GRAPHQL_CONTENT = "https://rivian.com/api/gql/content/graphql"
```

### 2. Missing GraphQL Operations

The following operations were observed in the iOS app but are **not** implemented in the Python client:

#### User & Account Management
| Operation | Type | Endpoint | Description |
|-----------|------|----------|-------------|
| `CurrentUser` | Query | gateway | Extended user profile query |
| `GetReferralCode` | Query | gateway | User's referral code |
| `getInvitationsByUser` | Query | gateway | Vehicle share invitations |

#### Notifications & Push
| Operation | Type | Endpoint | Description |
|-----------|------|----------|-------------|
| `RegisterNotificationTokens` | Mutation | gateway | Register push notification tokens |
| `RegisterPushNotificationToken` | Mutation | gateway | Register individual push token |
| `LiveNotificationRegisterStartToken` | Mutation | gateway | Live notification registration |

#### Vehicle Services
| Operation | Type | Endpoint | Description |
|-----------|------|----------|-------------|
| `getAppointments` | Query | **vs/gql-gateway** | Service appointments |
| `GetActiveRequests` | Query | **vs/gql-gateway** | Active service requests |
| `GetProvisionedUsersForVehicle` | Query | gateway | Vehicle user provisioning |

#### Content Services
| Operation | Type | Endpoint | Description |
|-----------|------|----------|-------------|
| `chatSession` | Query | **gql/content/graphql** | Chat support session |

### 3. Client Version Differences

**Current Implementation (Android-based):**
```python
APOLLO_CLIENT_NAME = "com.rivian.android.consumer"
APOLLO_CLIENT_VERSION = "3.6.0-3989"
```

**Observed in iOS App:**
```
apollographql-client-name: com.rivian.ios.consumer
apollographql-client-version: 3.6.0-4400
```

**Status:** Python client uses Android headers, which is fine for compatibility. No change required unless Android-specific issues arise.

### 4. Request Headers Analysis

The iOS app includes headers not currently sent by the Python client:

| Header | Example Value | Purpose |
|--------|---------------|---------|
| `u-sess` | `294a50a0-f519-4e7d-8a9a-2342fb48d1a6` | Session identifier (UUID) |
| `dc-cid` | `m-ios-7D473461-5265-4D41-852F-C160E4BCE480` | Distributed correlation ID |
| `accept` | `multipart/mixed;deferSpec=20220824,application/graphql-response+json,application/json` | GraphQL defer/stream support |

**Current Client Headers:**
```python
BASE_HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "apollographql-client-name": APOLLO_CLIENT_NAME,
    "apollographql-client-version": APOLLO_CLIENT_VERSION,
}
```

**Recommendations:**
1. The `u-sess` header may be the app session token (already handled via `_app_session_token`)
2. The `dc-cid` header could improve request tracing but is likely optional
3. The enhanced `accept` header enables GraphQL `@defer` directive but is optional

### 5. Operations Already Implemented

The following operations from the traffic **are already implemented**:

✅ `getRegisteredWallboxes` → `get_registered_wallboxes()`
✅ `GetVehicleImages` → `get_vehicle_images()`
✅ `ChargingSchedule` → `get_charging_schedules()` (similar operation)

### 6. GraphQL Schema Updates Needed

The current `schema.py` needs these additions:

```python
# Add to Query type
type Query {
  # ... existing queries ...

  # User & Referrals
  getCurrentUser: ExtendedUser  # More detailed than currentUser
  getReferralCode: ReferralCodeResponse
  getInvitationsByUser: [UserInvitation]

  # Vehicle Services (vs/gql-gateway endpoint)
  getAppointments(vehicleId: String!): [ServiceAppointment]
  getActiveRequests(vehicleId: String!): [ServiceRequest]
  getProvisionedUsersForVehicle(vehicleId: String!): [ProvisionedUser]

  # Content Services (gql/content/graphql endpoint)
  chatSession(vehicleId: String): ChatSession
}

type Mutation {
  # ... existing mutations ...

  # Notifications
  registerNotificationTokens(tokens: [NotificationTokenInput!]!): NotificationResponse
  registerPushNotificationToken(token: String!, platform: String!): NotificationResponse
  liveNotificationRegisterStartToken(vehicleId: String!, token: String!): NotificationResponse
}

# New Types
type ReferralCodeResponse {
  code: String
  url: String
}

type ServiceAppointment {
  id: String
  vehicleId: String
  status: String
  scheduledTime: String
  serviceType: String
}

type ServiceRequest {
  id: String
  vehicleId: String
  status: String
  description: String
  createdAt: String
}

type ChatSession {
  sessionId: String
  active: Boolean
}

input NotificationTokenInput {
  token: String!
  platform: String!
  deviceId: String
}

type NotificationResponse {
  success: Boolean!
  message: String
}
```

## Priority Recommendations

### High Priority
1. **Add vehicle services endpoint support** - Required for service appointments/requests
2. **Implement `CurrentUser` query** - Core user functionality in iOS app
3. **Add `GetProvisionedUsersForVehicle`** - Key for vehicle sharing features

### Medium Priority
1. **Implement notification registration mutations** - Useful for push notification apps
2. **Add `getInvitationsByUser` query** - Vehicle invitation management
3. **Add `getReferralCode` query** - Referral program support

### Low Priority
1. **Add content/chat endpoint** - Chat support feature
2. **Implement service appointment queries** - Nice-to-have for service management
3. **Add correlation ID header** - Improves debugging but not required

## Implementation Notes

### For Vehicle Services Endpoint

The `vs/gql-gateway` endpoint likely requires similar authentication but may have different response structures. When implementing:

1. Create a new `_ensure_vehicle_services_client()` method
2. Use the same auth headers (access token, app session token)
3. Test error handling - may have different error codes
4. Check if CSRF token is required

### For Content Endpoint

The `gql/content/graphql` endpoint appears to be for chat/support features:

1. May require different authentication scope
2. Likely read-only for end users
3. Consider if this is needed for core functionality

### Testing Strategy

When implementing new operations:

1. Use mitmproxy to capture actual request/response payloads
2. Compare response structures with schema definitions
3. Test error cases (invalid vehicle ID, missing auth, etc.)
4. Verify rate limiting behavior

## Traffic Pattern Observations

### Request Volume
- Multiple concurrent GraphQL requests on app startup
- Batch operations are NOT used (each query is separate)
- High frequency polling not observed (app likely uses WebSocket subscriptions)

### Authentication Flow
1. Client includes `u-sess` (session ID) in all requests
2. `access_token` provided via standard auth headers
3. No OAuth refresh observed during capture window

### Error Handling
Some requests showed `stream reset by client (CANCEL)` - this is normal:
- Client cancels operations when no longer needed (e.g., user navigates away)
- Python client should handle timeouts gracefully

## Conclusion

The rivian-python-client is **functionally complete** for core vehicle control and state management. However, several **user account and service-related features** from the iOS app are missing:

- ✅ **Vehicle control:** Fully implemented
- ✅ **State monitoring:** Fully implemented
- ✅ **Charging management:** Fully implemented
- ⚠️ **User account features:** Partially implemented
- ❌ **Service appointments:** Not implemented
- ❌ **Push notifications:** Not implemented
- ❌ **Chat support:** Not implemented

### Recommended Next Steps

1. **Phase 1:** Add vehicle services endpoint + `getAppointments`/`GetActiveRequests`
2. **Phase 2:** Implement missing user queries (`CurrentUser`, `GetProvisionedUsersForVehicle`)
3. **Phase 3:** Add notification registration mutations (if building notification app)
4. **Phase 4:** Content endpoint + chat (low priority)

---

**Generated by:** Claude Code via mitmproxy traffic analysis
**iOS App Version:** 4400 (3.6.0-4400)
**Current Client Version:** 3989 (3.6.0-3989)
