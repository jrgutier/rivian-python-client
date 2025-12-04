#!/usr/bin/env python3
"""Decode MITM payloads from sendVehicleOperation mutation."""

import base64

# MITM payloads from the user
payload_8hrs = "ClgKJAgBEiBG5Z+fjzUUWimeTc7I9XKXSkV8HuSqaqrVKnsSCgSluBIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEkwKImNvbWZvcnQuY2FiaW4uY2xpbWF0ZV9ob2xkX3NldHRpbmcQARoQzeLp8BZLQuCXBcu8VluMPSIECIDhASoMCPOagMgGEKuNvsUC"

payload_2hrs = "ClgKJAgBEiD9mr2L2wfP1YkbWV+HqWxdhKdKIrCd0DTKTX7UqtGo8BIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEksKImNvbWZvcnQuY2FiaW4uY2xpbWF0ZV9ob2xkX3NldHRpbmcQARoQ12lxp4pkQ86zps15iFqSpiIDCKA4KgwI8puAyAYQqK2wmQI="

def decode_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Decode a protobuf varint from data at position pos."""
    result = 0
    shift = 0
    while True:
        byte = data[pos]
        result |= (byte & 0x7F) << shift
        pos += 1
        if (byte & 0x80) == 0:
            break
        shift += 7
    return result, pos

def parse_protobuf(data: bytes, indent: int = 0) -> None:
    """Parse and print protobuf wire format."""
    prefix = "  " * indent
    pos = 0

    while pos < len(data):
        # Read tag
        tag, pos = decode_varint(data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x7

        print(f"{prefix}Field {field_number} (wire type {wire_type}):", end=" ")

        if wire_type == 0:  # Varint
            value, pos = decode_varint(data, pos)
            print(f"varint = {value}")
        elif wire_type == 2:  # Length-delimited
            length, pos = decode_varint(data, pos)
            value = data[pos:pos + length]
            pos += length

            # Try to parse as string
            try:
                str_value = value.decode('utf-8')
                if str_value.isprintable():
                    print(f"string = '{str_value}'")
                else:
                    print(f"bytes (len={length})")
                    print(f"{prefix}  (hex: {value.hex()})")
                    # Try to parse as nested message
                    if length > 0:
                        print(f"{prefix}  Nested message:")
                        parse_protobuf(value, indent + 2)
            except UnicodeDecodeError:
                print(f"bytes (len={length})")
                print(f"{prefix}  (hex: {value.hex()})")
                # Try to parse as nested message
                if length > 0:
                    print(f"{prefix}  Nested message:")
                    parse_protobuf(value, indent + 2)
        else:
            print(f"unknown wire type")
            break

print("=" * 80)
print("8 HOUR CLIMATE HOLD PAYLOAD")
print("=" * 80)
decoded_8hrs = base64.b64decode(payload_8hrs)
print(f"Raw hex: {decoded_8hrs.hex()}")
print(f"Length: {len(decoded_8hrs)} bytes")
print("\nParsed structure:")
parse_protobuf(decoded_8hrs)

print("\n" + "=" * 80)
print("2 HOUR CLIMATE HOLD PAYLOAD")
print("=" * 80)
decoded_2hrs = base64.b64decode(payload_2hrs)
print(f"Raw hex: {decoded_2hrs.hex()}")
print(f"Length: {len(decoded_2hrs)} bytes")
print("\nParsed structure:")
parse_protobuf(decoded_2hrs)

# Look for the key differences
print("\n" + "=" * 80)
print("KEY DIFFERENCES")
print("=" * 80)
print("Looking for duration fields...")

# Search for 480 minutes (8 hours) = 28800 seconds = 0x7080 as varint
# Search for 120 minutes (2 hours) = 7200 seconds = 0x2820 as varint

# 480 minutes = 28800 seconds
# In protobuf varint: 28800 = 0x7080 = 10000000 11100001 = 0x80 0xE1
print(f"\n480 minutes = 28800 seconds")
print(f"2 hours = 120 minutes = 7200 seconds")

# Find varint encoding
def encode_varint(value: int) -> bytes:
    """Encode an integer as protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)

print(f"\nVarint encoding of 28800 (480 min): {encode_varint(28800).hex()}")
print(f"Varint encoding of 7200 (120 min): {encode_varint(7200).hex()}")

# Search in payloads
print(f"\nSearching in 8 hour payload: {decoded_8hrs.hex()}")
if encode_varint(28800) in decoded_8hrs:
    print(f"  ✓ Found 28800 (480 minutes) encoding!")

print(f"\nSearching in 2 hour payload: {decoded_2hrs.hex()}")
if encode_varint(7200) in decoded_2hrs:
    print(f"  ✓ Found 7200 (120 minutes) encoding!")
