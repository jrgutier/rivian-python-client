# Rivian Python Client Documentation

Complete documentation for the rivian-python-client library.

## Quick Links

- [Main README](../README.md) - Getting started, installation, basic usage
- [CHANGELOG](../CHANGELOG.md) - Version history and migration guides
- [Developer Guide](../CLAUDE.md) - Claude Code development instructions

---

## Documentation Structure

### 📡 Protocols

Detailed technical documentation for Rivian's communication protocols.

- **[BLE Protocols](protocols/BLE_PROTOCOLS.md)** - Bluetooth Low Energy pairing
  - Gen 1 (LEGACY) protocol for 2021-2023 vehicles
  - Gen 2 (PRE_CCC) protocol for late 2023+ vehicles
  - UUID reference and detection logic
  - Security considerations

- **[Parallax Protocol](protocols/PARALLAX_PROTOCOL.md)** - Cloud-based vehicle commands
  - GraphQL/HTTP protocol for remote access
  - 18 Remote Vehicle Module (RVM) types
  - Protocol Buffers message formats
  - Implementation examples

### 🔌 API Reference

API coverage and implementation status.

- **[API Coverage](api/API_COVERAGE.md)** - iOS app vs Python client comparison
  - Implemented operations (v2.0-v2.2)
  - Missing operations and recommendations
  - Endpoint reference
  - Implementation roadmap

### 🛠️ Development

Development guides and test results.

- **[Implementation Summary](development/IMPLEMENTATION_SUMMARY.md)** - Version history
  - v2.0: GraphQL DSL migration
  - v2.1: Charging, navigation, trailers
  - v2.2: Parallax protocol, iOS traffic analysis

- **[Test Results](development/TEST_RESULTS.md)** - Test coverage and results

---

## Protocol Overview

### BLE Phone Pairing

Rivian uses Bluetooth Low Energy for phone key enrollment:

```python
from rivian import Rivian
from rivian.ble import pair_phone
from rivian.utils import generate_key_pair

# 1. Enroll phone via API
async with Rivian() as client:
    await client.login(username, password)

    public_key, private_key = generate_key_pair()
    await client.enroll_phone(public_key, "My Phone")

# 2. Pair via BLE (auto-detects Gen1/Gen2)
await pair_phone(phone_id, private_key, vehicle_id)
```

**Documentation**: [BLE Protocols](protocols/BLE_PROTOCOLS.md)

### Parallax Cloud Commands

Cloud-based protocol for remote vehicle operations:

```python
# Real-time charging data
data = await client.get_charging_session_live_data(vehicle_id)

# Climate control
await client.set_climate_hold(
    vehicle_id=vehicle_id,
    enabled=True,
    temp_celsius=22.0,
    duration_minutes=120
)

# Charging schedule
await client.set_charging_schedule(
    vehicle_id=vehicle_id,
    start_hour=22,
    start_minute=0,
    end_hour=6,
    end_minute=0
)
```

**Documentation**: [Parallax Protocol](protocols/PARALLAX_PROTOCOL.md)

---

## Quick Reference

### Authentication

```python
from rivian import Rivian

async with Rivian() as client:
    # Simple login (returns OTP token if MFA enabled)
    otp_token = await client.login(username, password)

    # Complete OTP if required
    if otp_token:
        await client.login_with_otp(username, otp_code, otp_token)
```

### Vehicle Commands

```python
from rivian import VehicleCommand

# Send command
command_id = await client.send_vehicle_command(
    vehicle_id=vehicle_id,
    command=VehicleCommand.UNLOCK_ALL_CLOSURES
)

# Monitor status via WebSocket
async for state in client.subscribe_for_command_state(command_id):
    if state['state'] in ['COMPLETE', 'FAILED']:
        break
```

### Real-Time Updates

```python
from rivian.const import VEHICLE_STATE_PROPERTIES

# Subscribe to vehicle state updates
async for update in client.subscribe_for_vehicle_updates(
    vehicle_id=vehicle_id,
    properties=VEHICLE_STATE_PROPERTIES
):
    print(f"Battery: {update['batteryLevel']['value']}%")
    print(f"Range: {update['distanceToEmpty']['value']} miles")
```

---

## Version History

### v2.2.0 (2025-10-27)
- **New**: iOS app traffic analysis implementation
- **Added**: 9 new operations (referrals, notifications, services, chat)
- **Added**: 3 new API endpoints (vehicle services, content)
- **Changed**: Client headers updated to iOS

### v2.1.0 (2025-10-26)
- **Added**: 20 new GraphQL operations
- **Added**: Charging management (4 operations)
- **Added**: Location sharing (2 operations)
- **Added**: Trailer management (2 operations)
- **Added**: Trip planning (4 operations)
- **Added**: Advanced key management (4 operations)
- **Added**: Gear Guard monitoring

### v2.0.0 (2025-10-26)
- **Breaking**: Query methods return `dict`/`list[dict]` instead of `ClientResponse`
- **Added**: New authentication methods (`login()`, `login_with_otp()`)
- **Changed**: Migrated to gql DSL for type-safe queries
- **Added**: Static GraphQL schema in `schema.py`

### v1.x (Previous)
- Legacy implementation with basic GraphQL support

---

## Architecture

### Core Components

**`rivian.py`** - Main async API client
- Authentication flow (username/password + OTP)
- GraphQL query execution (3 endpoints)
- Session management
- Vehicle command execution with HMAC signing
- WebSocket subscriptions

**`schema.py`** - Static GraphQL schema
- Comprehensive schema covering all operations
- Type definitions for DSL queries
- No introspection overhead

**`const.py`** - Constants and enums
- `VehicleCommand` enum
- Vehicle state properties
- Charging session properties

**`parallax.py`** - Parallax protocol
- 18 RVM types enumeration
- Protocol Buffer message helpers
- Cloud-based vehicle commands

**`ble.py`** / **`ble_gen2.py`** - BLE phone pairing
- Auto-detection of vehicle generation
- Gen 1 and Gen 2 protocol support
- Cryptographic key operations

---

## Python Version Support

- **Supported**: Python 3.9 - 3.13
- **Dependencies**:
  - `aiohttp` - Async HTTP client
  - `gql[aiohttp,websockets]` - GraphQL client with DSL
  - `cryptography` - Key generation and HMAC
  - `protobuf` - Protocol Buffers (Parallax & Gen2 BLE)
- **Optional**:
  - `bleak` - BLE support (install with `[ble]` extra)

---

## Contributing

When contributing to documentation:

1. **Protocol docs** → `docs/protocols/`
2. **API coverage** → `docs/api/`
3. **Development notes** → `docs/development/`
4. **Root docs** → Keep minimal (README, CHANGELOG, CLAUDE.md)

### Documentation Standards

- Use GitHub-flavored Markdown
- Include code examples with syntax highlighting
- Add tables for structured data
- Link to related documentation
- Keep examples concise and tested

---

## Additional Resources

### External Documentation

- [Rivian Official Site](https://rivian.com)
- [Home Assistant Integration](https://www.home-assistant.io/integrations/rivian/)
- [Python asyncio docs](https://docs.python.org/3/library/asyncio.html)
- [GraphQL Documentation](https://graphql.org/learn/)
- [Protocol Buffers Guide](https://developers.google.com/protocol-buffers)

### Repository

- **GitHub**: [rivian-python-client](https://github.com/bretterer/rivian-python-client)
- **PyPI**: [rivian-python-client](https://pypi.org/project/rivian-python-client/)
- **Issues**: [GitHub Issues](https://github.com/bretterer/rivian-python-client/issues)

---

## License

MIT License - See [LICENSE](../LICENSE) file for details.

## Disclaimer

This is an unofficial client library and is not affiliated with, endorsed by, or connected to Rivian Automotive, LLC. Use at your own risk.

---

**Documentation Version**: 1.0
**Last Updated**: 2025-10-27
**Python Client Version**: 2.2.0
