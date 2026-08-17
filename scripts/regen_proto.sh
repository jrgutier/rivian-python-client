#!/usr/bin/env bash
# Regenerate src/rivian/proto/*_pb2.py{,i} from the checked-in .proto files.
#
# The .proto files are the source of truth; the generated modules must never be
# hand-edited. The previously checked-in ones had been, and it caused two real
# defects that only surfaced when a module was imported first rather than
# incidentally:
#
#   1. Missing well-known-type imports. rivian_climate.proto declares
#      `import "google/protobuf/timestamp.proto"` and the serialized descriptor
#      references it, but the generated module never imported timestamp_pb2, so
#      the dependency was never registered:
#        TypeError: Couldn't build proto file into descriptor pool:
#        Depends on file 'google/protobuf/timestamp.proto', but it has not been loaded
#      Affected rivian_base, rivian_climate, rivian_navigation, rivian_vehicle.
#
#   2. Stripped cross-module imports. rivian_charging_pb2 needs rivian_base_pb2
#      and had no import for it at all, working only when something else happened
#      to load it first.
#
# protoc emits flat `import rivian_base_pb2`, which cannot resolve inside the
# rivian.proto package, so imports are rewritten to package-relative form below.
#
# Dev-only: protobuf does not ship in the integration. Run after editing any
# .proto, and commit the regenerated output alongside it.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
PROTO_DIR="src/rivian/proto"

echo "Regenerating from ${PROTO_DIR}/*.proto"
uv run python -m grpc_tools.protoc \
    --proto_path="$PROTO_DIR" \
    --python_out="$PROTO_DIR" \
    --pyi_out="$PROTO_DIR" \
    "$PROTO_DIR"/*.proto

# protoc emits `import rivian_foo_pb2 as rivian__foo__pb2` (proto_path-relative).
# Rewrite to `from . import ...` so the modules resolve inside the package
# regardless of import order.
echo "Rewriting cross-module imports to package-relative form"
python3 - "$PROTO_DIR" <<'PY'
import pathlib, re, sys

proto_dir = pathlib.Path(sys.argv[1])
pattern = re.compile(r'^import (rivian_\w+_pb2) as (\w+)$', re.MULTILINE)
changed = 0
for path in sorted(proto_dir.glob("*_pb2.py")):
    src = path.read_text()
    new, n = pattern.subn(r'from . import \1 as \2', src)
    if n:
        path.write_text(new)
        changed += n
        print(f"  {path.name}: {n} import(s)")
print(f"rewrote {changed} import(s)")
PY

echo "Verifying every generated module imports standalone"
for module in "$PROTO_DIR"/*_pb2.py; do
    name="$(basename "$module" .py)"
    uv run python -c "import rivian.proto.${name}" \
        || { echo "FAILED: rivian.proto.${name}"; exit 1; }
done
echo "OK — all modules import cleanly"
