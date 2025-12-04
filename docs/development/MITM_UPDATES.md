# Rivian Python Client - mitmproxy Analysis Updates

**Date:** October 27, 2025
**Analysis Source:** iOS Rivian App v4400 traffic capture

## Changes Made

### 1. Added New API Endpoint Constants

Updated `src/rivian/rivian.py` to include newly discovered GraphQL endpoints:

```python
# Before
GRAPHQL_GATEWAY = GRAPHQL_BASEPATH + "/gateway/graphql"
GRAPHQL_CHARGING = GRAPHQL_BASEPATH + "/chrg/user/graphql"
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"

# After
GRAPHQL_GATEWAY = GRAPHQL_BASEPATH + "/gateway/graphql"
GRAPHQL_CHARGING = GRAPHQL_BASEPATH + "/chrg/user/graphql"
GRAPHQL_VEHICLE_SERVICES = "https://rivian.com/api/vs/gql-gateway"  # NEW
GRAPHQL_CONTENT = GRAPHQL_BASEPATH + "/content/graphql"  # NEW
GRAPHQL_WEBSOCKET = "wss://api.rivian.com/gql-consumer-subscriptions/graphql"
```

**Purpose:**
- `GRAPHQL_VEHICLE_SERVICES` - Used for service appointments and active service requests
- `GRAPHQL_CONTENT` - Used for chat support sessions

### 2. Created Comprehensive Audit Document

Created `MITM_API_AUDIT.md` with complete traffic analysis including:

- ✅ Comparison of iOS app operations vs Python client
- ✅ Missing GraphQL operations identified
- ✅ New endpoint discovery and documentation
- ✅ Header differences analysis
- ✅ Priority recommendations for future implementation
- ✅ GraphQL schema additions needed

## What Was NOT Changed

The following were intentionally **not modified** based on analysis:

### Client Version Headers
```python
APOLLO_CLIENT_NAME = "com.rivian.android.consumer"  # Kept as Android
APOLLO_CLIENT_VERSION = "3.6.0-3989"  # Kept as 3989 (vs iOS 4400)
```

**Reason:** Android client headers work fine. No compatibility issues observed.

### Request Headers
Did not add:
- `u-sess` header (already handled via `_app_session_token`)
- `dc-cid` correlation ID (optional, for debugging only)
- Enhanced `accept` header with defer support (optional feature)

**Reason:** Current headers are sufficient. These are enhancements, not requirements.

### GraphQL Operations
Did not implement missing operations yet:
- `CurrentUser`, `GetReferralCode`, `getInvitationsByUser`
- Notification registration mutations
- Service appointment queries
- Chat session queries

**Reason:** Requires careful implementation with proper schema updates and testing. See `MITM_API_AUDIT.md` for roadmap.

## Files Modified

1. ✅ `src/rivian/rivian.py` - Added endpoint constants
2. ✅ `MITM_API_AUDIT.md` - Created comprehensive audit
3. ✅ `MITM_UPDATES.md` - This file

## Files Created

1. `MITM_API_AUDIT.md` - Full traffic analysis and recommendations
2. `MITM_UPDATES.md` - Summary of changes made

## Next Steps (Recommended)

Based on the audit, future PRs should:

### Phase 1: Vehicle Services Support
1. Create `_ensure_vehicle_services_client()` method
2. Implement `get_service_appointments(vehicle_id)`
3. Implement `get_active_service_requests(vehicle_id)`

### Phase 2: Enhanced User Queries
1. Expand schema.py with missing user types
2. Implement `get_current_user_extended()`
3. Implement `get_vehicle_provisioned_users(vehicle_id)`

### Phase 3: Notifications (Optional)
1. Add notification schema types
2. Implement `register_notification_token()`
3. Implement `register_push_notification()`

See `MITM_API_AUDIT.md` section "Priority Recommendations" for full details.

## Testing Notes

When testing new endpoints:

1. Use mitmproxy to capture actual payloads first
2. Compare response structures with schema
3. Test error cases (auth failures, invalid IDs, etc.)
4. Verify rate limiting behavior
5. Check if CSRF token is required for new endpoints

## WebSocket Logging Tool

Also created `websocket_logger.py` in the root directory for mitmproxy WebSocket message capture. This tool logs:
- WebSocket message contents (client→server and server→client)
- Timestamps and endpoints
- Both console output and file logging (`mitmproxy_websocket.log`)

**Usage:**
```bash
mitmdump --set websocket=true -s websocket_logger.py
```

---

**Summary:** The Python client is functionally complete for core vehicle operations. New endpoints and operations discovered are primarily for service management, user account features, and push notifications - all nice-to-have features for future enhancement.
