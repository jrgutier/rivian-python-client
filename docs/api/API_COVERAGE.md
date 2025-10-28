# Rivian API Coverage Analysis

Comparison of iOS Rivian App functionality vs Python client implementation.

## Executive Summary

**Source**: iOS Rivian App v4400 traffic analysis via mitmproxy
**Date**: October 27, 2025

The rivian-python-client is **functionally complete** for core vehicle control and state management. However, several user account and service-related features from the iOS app are not yet implemented.

### Coverage Status

- ✅ **Vehicle Control**: Fully implemented
- ✅ **State Monitoring**: Fully implemented
- ✅ **Charging Management**: Fully implemented
- ⚠️ **User Account Features**: Partially implemented
- ❌ **Service Appointments**: Not implemented
- ❌ **Push Notifications**: Not implemented
- ❌ **Chat Support**: Not implemented

---

## API Endpoints

### Current Endpoints (Python Client)

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `https://rivian.com/api/gql/gateway/graphql` | Main gateway | ✅ Implemented |
| `https://rivian.com/api/gql/chrg/user/graphql` | Charging data | ✅ Implemented |
| `wss://api.rivian.com/gql-consumer-subscriptions/graphql` | WebSocket subscriptions | ✅ Implemented |

### New Endpoints (iOS App)

| Endpoint | Purpose | Status |
|----------|---------|--------|
| `https://rivian.com/api/vs/gql-gateway` | Vehicle services | ❌ Missing |
| `https://rivian.com/api/gql/content/graphql` | Content/chat services | ❌ Missing |

---

## Missing Operations

### High Priority

#### User & Account Management

| Operation | Type | Endpoint | Description | Use Case |
|-----------|------|----------|-------------|----------|
| `GetReferralCode` | Query | gateway | User's referral code | Referral program |
| `getInvitationsByUser` | Query | gateway | Vehicle share invitations | Vehicle sharing |
| `GetProvisionedUsersForVehicle` | Query | gateway | Vehicle user provisioning | Access management |

#### Vehicle Services

| Operation | Type | Endpoint | Description | Use Case |
|-----------|------|----------|-------------|----------|
| `getAppointments` | Query | **vs/gql-gateway** | Service appointments | Service scheduling |
| `GetActiveRequests` | Query | **vs/gql-gateway** | Active service requests | Service tracking |

### Medium Priority

#### Notifications

| Operation | Type | Endpoint | Description | Use Case |
|-----------|------|----------|-------------|----------|
| `RegisterNotificationTokens` | Mutation | gateway | Register push tokens | Push notifications |
| `RegisterPushNotificationToken` | Mutation | gateway | Register single token | Push notifications |
| `LiveNotificationRegisterStartToken` | Mutation | gateway | Live notifications | Real-time alerts |

### Low Priority

#### Content Services

| Operation | Type | Endpoint | Description | Use Case |
|-----------|------|----------|-------------|----------|
| `chatSession` | Query | **gql/content/graphql** | Chat support session | Customer support |

---

## Implemented Operations (v2.2)

### Authentication (v2.0+)
- ✅ `login()` - Simplified login with OTP support
- ✅ `login_with_otp()` - Complete OTP validation

### User & Vehicle Info
- ✅ `get_user_information()` - User profile, vehicles, phones
- ✅ `get_drivers_and_keys()` - Vehicle data, invited users/devices
- ✅ `get_vehicle_images()` - Mobile and pre-order images
- ✅ `get_registered_wallboxes()` - Wallbox management

### Vehicle Commands (v2.0+)
- ✅ `send_vehicle_command()` - Remote control (lock/unlock, climate, etc.)
- ✅ `subscribe_for_command_state()` - Command status monitoring

### Phone Enrollment (v2.0+)
- ✅ `enroll_phone()` - BLE phone enrollment
- ✅ `disenroll_phone()` - Remove phone enrollment

### Charging Management (v2.1+)
- ✅ `get_charging_schedules()` - Departure/charging schedules
- ✅ `update_departure_schedule()` - Configure schedules
- ✅ `enroll_in_smart_charging()` - Enable smart charging
- ✅ `unenroll_from_smart_charging()` - Disable smart charging

### Location & Navigation (v2.1+)
- ✅ `share_location_to_vehicle()` - Send GPS coordinates
- ✅ `share_place_id_to_vehicle()` - Send Google Place
- ✅ `plan_trip_with_multi_stop()` - Multi-stop trip planning
- ✅ `save_trip_plan()` - Save trips
- ✅ `update_trip()` - Update saved trips
- ✅ `delete_trip()` - Delete trips

### Trailer Management (v2.1+)
- ✅ `get_trailer_profiles()` - R1T trailer profiles
- ✅ `update_pin_to_gear()` - Pin/unpin trailer

### Advanced Keys (v2.1+)
- ✅ `create_signing_challenge()` - CCC digital key
- ✅ `verify_signing_challenge()` - Verify CCC challenge
- ✅ `enable_ccc()` - Enable CCC support
- ✅ `upgrade_key_to_wcc2()` - Upgrade to WCC 2.0

### Gear Guard (v2.1+)
- ✅ `subscribe_for_gear_guard_config()` - GearGuard config updates

### Parallax Protocol (v2.2+)
- ✅ `get_charging_session_live_data()` - Real-time charging
- ✅ `get_climate_hold_status()` - Climate hold state
- ✅ `get_ota_status()` - OTA update status
- ✅ `get_trip_progress()` - Navigation progress
- ✅ `set_climate_hold()` - Configure climate
- ✅ `set_charging_schedule()` - Set charging windows
- ✅ `send_parallax_command()` - Low-level RVM access

---

## Implementation Recommendations

### Phase 1: Vehicle Services Endpoint

**Priority**: High
**Effort**: Medium

Add support for the `vs/gql-gateway` endpoint:

```python
GRAPHQL_VEHICLE_SERVICES = "https://rivian.com/api/vs/gql-gateway"

async def get_service_appointments(self, vehicle_id: str) -> list[dict]:
    """Get scheduled service appointments for vehicle."""
    # Implementation using vehicle services endpoint

async def get_active_service_requests(self, vehicle_id: str) -> list[dict]:
    """Get active service requests and their status."""
    # Implementation using vehicle services endpoint
```

**Schema Updates Needed**:
```graphql
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
  category: String
  createdAt: String
}
```

### Phase 2: User Account Features

**Priority**: High
**Effort**: Low

Implement missing user queries:

```python
async def get_referral_code(self) -> dict:
    """Get user's referral code and shareable URL."""
    # Returns: {"code": "ABC123", "url": "https://..."}

async def get_invitations_by_user(self) -> list[dict]:
    """Get vehicle share invitations received by user."""
    # Returns list of vehicle invitations

async def get_vehicle_provisioned_users(self, vehicle_id: str) -> list[dict]:
    """Get all users provisioned for vehicle access."""
    # Returns list of users with roles
```

**Schema Updates Needed**:
```graphql
type Query {
  getReferralCode: ReferralCodeResponse
  getInvitationsByUser: [UserInvitation]
  getProvisionedUsersForVehicle(vehicleId: String!): [ProvisionedUser]
}

type ReferralCodeResponse {
  code: String
  url: String
}

type UserInvitation {
  vehicleId: String
  vehicleModel: String
  invitedByFirstName: String
  status: String
}

type ProvisionedUser {
  userId: String
  firstName: String
  lastName: String
  email: String
  roles: [String]
}
```

### Phase 3: Push Notifications

**Priority**: Medium
**Effort**: Low

Add notification registration mutations:

```python
async def register_notification_tokens(self, tokens: list[dict]) -> dict:
    """Register multiple push notification tokens."""
    # tokens: [{"token": "...", "platform": "ios", "deviceId": "..."}]

async def register_push_notification_token(
    self, token: str, platform: str, vehicle_id: str
) -> dict:
    """Register single push notification token."""

async def register_live_notification_token(
    self, vehicle_id: str, token: str
) -> dict:
    """Register live notification start token."""
```

**Schema Updates Needed**:
```graphql
type Mutation {
  registerNotificationTokens(tokens: [NotificationTokenInput!]!): NotificationResponse
  registerPushNotificationToken(token: String!, platform: String!, vehicleId: String): NotificationResponse
  liveNotificationRegisterStartToken(vehicleId: String!, token: String!): NotificationResponse
}

input NotificationTokenInput {
  token: String!
  platform: String!  # "ios" or "android"
  deviceId: String
}

type NotificationResponse {
  success: Boolean!
  registeredTokens: [String]
  message: String
}
```

### Phase 4: Content/Chat Endpoint

**Priority**: Low
**Effort**: Low

Add support for chat/support features:

```python
GRAPHQL_CONTENT = "https://rivian.com/api/gql/content/graphql"

async def get_chat_session(self, vehicle_id: str) -> dict:
    """Get customer support chat session information."""
    # Returns: {"sessionId": "...", "status": "active", ...}
```

**Schema Updates Needed**:
```graphql
type Query {
  chatSession(vehicleId: String): ChatSession
}

type ChatSession {
  sessionId: String
  active: Boolean
  status: String
  messages: [ChatMessage]
}

type ChatMessage {
  id: String
  timestamp: String
  sender: String
  content: String
}
```

---

## Client Version Differences

### Current (Android-based)

```python
APOLLO_CLIENT_NAME = "com.rivian.android.consumer"
APOLLO_CLIENT_VERSION = "3.6.0-3989"
```

### iOS App Observed

```
apollographql-client-name: com.rivian.ios.consumer
apollographql-client-version: 3.6.0-4400
```

**Recommendation**: Keep Android headers for now. Update only if Android-specific issues arise.

---

## Header Enhancements (Optional)

### Current Headers

```python
BASE_HEADERS = {
    "User-Agent": "okhttp/4.12.0",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "apollographql-client-name": APOLLO_CLIENT_NAME,
    "apollographql-client-version": APOLLO_CLIENT_VERSION,
}
```

### iOS App Additional Headers

```http
u-sess: 294a50a0-f519-4e7d-8a9a-2342fb48d1a6
dc-cid: m-ios-7D473461-5265-4D41-852F-C160E4BCE480
accept: multipart/mixed;deferSpec=20220824,application/graphql-response+json,application/json
```

**Analysis**:
- `u-sess`: Likely app session token (already handled via `_app_session_token`)
- `dc-cid`: Distributed correlation ID (improves tracing, optional)
- `accept`: Enables GraphQL `@defer` directive (optional feature)

---

## Testing Strategy

When implementing new operations:

1. **Use mitmproxy** to capture actual request/response payloads
2. **Compare structures** with schema definitions
3. **Test error cases**: Invalid vehicle ID, missing auth, rate limits
4. **Verify rate limiting** behavior
5. **Check authorization** scope (owner vs authorized driver)

---

## Traffic Pattern Observations

### Request Volume
- Multiple concurrent GraphQL requests on app startup
- Batch operations NOT used (each query is separate)
- High frequency polling not observed (likely WebSocket subscriptions)

### Authentication Flow
1. Client includes `u-sess` (session ID) in all requests
2. `access_token` provided via standard auth headers
3. No OAuth refresh observed during capture window

### Error Handling
- Some requests show `stream reset by client (CANCEL)` - normal behavior
- Client cancels operations when no longer needed
- Python client should handle timeouts gracefully

---

## Summary

The Python client provides **complete coverage** of vehicle control, state monitoring, and charging features. Missing functionality is primarily:

1. **Service-related**: Appointments, service requests
2. **Account management**: Referrals, invitations, user provisioning
3. **Notifications**: Push notification registration
4. **Support**: Chat/support features

These features are **optional** for core vehicle control but useful for comprehensive integrations (e.g., Home Assistant, mobile apps).

---

## Related Documentation

- **Implementation Summary**: `docs/development/IMPLEMENTATION_SUMMARY.md`
- **MITM Analysis**: `docs/development/MITM_ANALYSIS.md`
- **Protocol Docs**: `docs/protocols/`

---

**Document Version**: 1.0
**Last Updated**: 2025-10-27
**Source**: iOS App v4400 mitmproxy analysis
**License**: MIT
