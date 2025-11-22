#!/bin/bash
# Validate dependencies against Home Assistant's package constraints
# Usage: ./scripts/validate_ha_deps.sh [branch]
# Example: ./scripts/validate_ha_deps.sh dev

set -e

BRANCH="${1:-dev}"
CONSTRAINTS_URL="https://raw.githubusercontent.com/home-assistant/core/${BRANCH}/homeassistant/package_constraints.txt"

echo "Fetching Home Assistant constraints from branch: ${BRANCH}"
CONSTRAINTS=$(curl -s "${CONSTRAINTS_URL}")

if [ -z "$CONSTRAINTS" ]; then
    echo "Error: Failed to fetch constraints from ${CONSTRAINTS_URL}"
    exit 1
fi

echo "Checking key dependencies..."
echo ""

# Extract our dependencies from pyproject.toml
DEPS=(aiohttp attrs propcache yarl cryptography protobuf bleak websockets gql)

for dep in "${DEPS[@]}"; do
    # Get HA's version
    ha_version=$(echo "$CONSTRAINTS" | grep "^${dep}==" | cut -d'=' -f3 || echo "not pinned")

    if [ "$ha_version" = "not pinned" ]; then
        ha_version=$(echo "$CONSTRAINTS" | grep "^${dep}>" | head -1 || echo "not found")
    fi

    # Get our constraint from pyproject.toml
    our_constraint=$(grep "^${dep} =" pyproject.toml | sed 's/.*"\(.*\)".*/\1/' || echo "not found")

    if [ "$our_constraint" = "not found" ]; then
        our_constraint=$(grep "${dep} = {" pyproject.toml || echo "not found")
    fi

    printf "%-15s HA: %-20s  Ours: %s\n" "${dep}" "${ha_version}" "${our_constraint}"
done

echo ""
echo "To test installation with HA constraints:"
echo "  pip install -c <(curl -s ${CONSTRAINTS_URL}) '.[ble]'"
