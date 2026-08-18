#!/usr/bin/env bash
# Verify the checked-in .proto files still describe what we actually encode.
#
# The generated *_pb2 modules NO LONGER SHIP. The package encodes exactly one
# message (ClimateHoldSetting, a single int32) plus one envelope, all hand-rolled,
# because carrying the protobuf runtime for that was never proportionate -- and
# because generated code refuses to load when its gencode is newer than the
# runtime, which took the whole integration down during vendoring when a dev
# environment resolved protobuf 6.33 against Home Assistant's pinned 6.32.
#
# So this script no longer writes into the package. It regenerates into a TEMP
# directory and re-asserts the golden bytes, which is what keeps the .proto files
# from drifting into fiction: they remain the documented source of truth for the
# wire format, and this proves the hand-rolled encoders still agree with them.
#
# Dev-only. Needs grpcio-tools and protobuf, neither of which the package depends
# on any more.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROTO_DIR="src/rivian/proto"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

echo "Regenerating from ${PROTO_DIR}/*.proto into a temporary directory"
uv run --with grpcio-tools --with protobuf python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$OUT" \
    "$PROTO_DIR"/*.proto

echo "Re-asserting the golden bytes against freshly generated code"
uv run --with protobuf python - "$OUT" <<'PY'
import json, pathlib, sys

sys.path.insert(0, sys.argv[1])
from rivian_climate_pb2 import ClimateHoldSetting  # noqa: E402

golden = json.loads(
    pathlib.Path("tests/fixtures/golden/climate_hold_setting.json").read_text()
)["ClimateHoldSetting.hold_time_duration_seconds"]

bad = []
for seconds, expected in golden.items():
    actual = ClimateHoldSetting(
        hold_time_duration_seconds=int(seconds)
    ).SerializeToString().hex()
    if actual != expected:
        bad.append(f"  {seconds}s: golden {expected!r} but .proto now yields {actual!r}")

if bad:
    raise SystemExit(
        "The .proto no longer produces the bytes we encode:\n" + "\n".join(bad)
    )
print(f"OK - all {len(golden)} golden encodings still match the .proto")
PY
