#!/usr/bin/env python3
"""Decode Halloween settings payloads from MITM captures."""

import base64
import sys

# Add src to path
sys.path.insert(0, "src")


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
        if pos >= len(data):
            break

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
            value = data[pos : pos + length]
            pos += length

            # Try to parse as string
            try:
                str_value = value.decode("utf-8")
                if str_value.isprintable() and all(c.isprintable() or c == "\n" for c in str_value):
                    print(f'string = "{str_value}"')
                else:
                    print(f"bytes (len={length}, hex={value.hex()})")
                    if length > 0 and length < 1000:
                        try:
                            print(f"{prefix}  Nested message:")
                            parse_protobuf(value, indent + 2)
                        except:
                            pass
            except UnicodeDecodeError:
                print(f"bytes (len={length}, hex={value.hex()})")
                if length > 0 and length < 1000:
                    try:
                        print(f"{prefix}  Nested message:")
                        parse_protobuf(value, indent + 2)
                    except:
                        pass
        else:
            print(f"unknown wire type")
            break


# Payloads from MITM
payloads = {
    "Halloween ON": "ClgKJAgBEiDcPFXwPAiyTCWGxSFvwLr0E0FtetvOdXtnJhtcFAOEjhIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEpgBCkpob2xpZGF5X2NlbGVicmF0aW9uLm1vYmlsZV92ZWhpY2xlX3NldHRpbmdzLmhhbGxvd2Vlbl9jZWxlYnJhdGlvbl9zZXR0aW5ncxABGhBgZdSKW0VGvKeAm85ZSODxIigKAggFEgIIDRoCCAEiAggBKgAwAToCCAFCAggBSgIIAVIAWgBiAggCKgwIiZ6AyAYQ1enW5wI=",
    "Interior Sound 1": "ClgKJAgBEiAzg3Ikh4bmIFbIjOpCFOETG2mQP2RFXwGo9MEF+ELvshIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEpwBCkpob2xpZGF5X2NlbGVicmF0aW9uLm1vYmlsZV92ZWhpY2xlX3NldHRpbmdzLmhhbGxvd2Vlbl9jZWxlYnJhdGlvbl9zZXR0aW5ncxABGhDikD+pe4hML4mzwoHYdfVRIiwKAggFEgIIDRoCCAEiAggBKgIIATAEOgIIAUICCAFKAggBUgBaAggKYgIIAioMCLiegMgGEKyjgOIB",
    "Interior Sound 2": "ClgKJAgBEiAnVfFZRDN5KDZrrO+g6wEtto6R87qxDLtqXoJJ6qmXaBIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEpwBCkpob2xpZGF5X2NlbGVicmF0aW9uLm1vYmlsZV92ZWhpY2xlX3NldHRpbmdzLmhhbGxvd2Vlbl9jZWxlYnJhdGlvbl9zZXR0aW5ncxABGhAIIqBiF3ZH/73Fcvk2KJC5IiwKAggFEgIIDRoCCAEiAggBKgIIAjAEOgIIAUICCAFKAggBUgBaAggKYgIIAioMCLmegMgGEMKYvsYD",
    "Interior Sound 3": "ClgKJAgBEiAnJUuap7xO29P8C7Ozs08IKptftdkdWV4U4/rsK0M5vRIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEpwBCkpob2xpZGF5X2NlbGVicmF0aW9uLm1vYmlsZV92ZWhpY2xlX3NldHRpbmdzLmhhbGxvd2Vlbl9jZWxlYnJhdGlvbl9zZXR0aW5ncxABGhDKmkws4IdJt7Ll9IDL7Nc/IiwKAggFEgIIDRoCCAEiAggBKgIIAzAEOgIIAUICCAFKAggBUgBaAggKYgIIAioMCLuegMgGEPrLhqsB",
    "Interior Sound 4": "ClgKJAgBEiAh00yjJ3FVn0IldP/sTRYEeknJTqoX6v4ePvxSj/pyjhIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEpwBCkpob2xpZGF5X2NlbGVicmF0aW9uLm1vYmlsZV92ZWhpY2xlX3NldHRpbmdzLmhhbGxvd2Vlbl9jZWxlYnJhdGlvbl9zZXR0aW5ncxABGhD2WcUoYuhIUYmFAcgbCfLSIiwKAggFEgIIDRoCCAEiAggBKgIIBDAEOgIIAUICCAFKAggBUgBaAggKYgIIAioMCLyegMgGEPTts5AC",
    "Halloween OFF": "ClgKJAgBEiCap5vhwcZ7qY5RIkcjxE2y7ymEU8yVE6K0QvIKZvig5xIwMTctNDhjMDgwYzgtZjkwZi00NGQxLWIxOTQtZTNjZDJlMmY5YWFiLTVjMjk1NTkzEpIBCkpob2xpZGF5X2NlbGVicmF0aW9uLm1vYmlsZV92ZWhpY2xlX3NldHRpbmdzLmhhbGxvd2Vlbl9jZWxlYnJhdGlvbl9zZXR0aW5ncxABGhDGEsOv3HpFuoIGAPfXRbLVIiIKABIAGgAiAggBKgIIBjAEOgIIAUIASgBSAFoCCApiAggCKgwI756AyAYQvcqUqgM=",
}

for name, payload_b64 in payloads.items():
    print("=" * 80)
    print(f"{name}")
    print("=" * 80)

    # Decode base64
    outer_data = base64.b64decode(payload_b64)

    # Parse outer VehicleOperationRequest
    print("\nOuter VehicleOperationRequest:")
    parse_protobuf(outer_data)

    # Extract the inner payload (field 2, operation, field 4, payload)
    # This is a bit manual but let's extract it
    print("\n" + "-" * 80)
    print("Extracting inner Halloween settings payload...")
    print("-" * 80)

    # Skip to field 2 (operation)
    pos = 0
    while pos < len(outer_data):
        tag, pos = decode_varint(outer_data, pos)
        field_number = tag >> 3
        wire_type = tag & 0x7

        if field_number == 2 and wire_type == 2:
            # This is the operation message
            length, pos = decode_varint(outer_data, pos)
            operation_data = outer_data[pos : pos + length]

            # Now parse the operation to find field 4 (payload)
            op_pos = 0
            while op_pos < len(operation_data):
                op_tag, op_pos = decode_varint(operation_data, op_pos)
                op_field = op_tag >> 3
                op_wire = op_tag & 0x7

                if op_field == 4 and op_wire == 2:
                    # This is the Halloween settings payload!
                    payload_len, op_pos = decode_varint(operation_data, op_pos)
                    halloween_payload = operation_data[op_pos : op_pos + payload_len]

                    print(f"\nHalloween Settings Payload ({len(halloween_payload)} bytes):")
                    print(f"Hex: {halloween_payload.hex()}")
                    print("\nParsed structure:")
                    parse_protobuf(halloween_payload)
                    break
                elif op_wire == 0:
                    value, op_pos = decode_varint(operation_data, op_pos)
                elif op_wire == 2:
                    length, op_pos = decode_varint(operation_data, op_pos)
                    op_pos += length
            break
        elif wire_type == 0:
            value, pos = decode_varint(outer_data, pos)
        elif wire_type == 2:
            length, pos = decode_varint(outer_data, pos)
            pos += length

    print("\n")
