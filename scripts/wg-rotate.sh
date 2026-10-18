#!/usr/bin/env bash
# Rotate the Mullvad WireGuard egress to a new random exit.
#
# The wg-gateway container picks a random .conf on start when WG_GATEWAY_CONF is
# empty, so a restart selects a fresh exit. Pass a filename to pin a specific one.
#
# Usage:
#   ./scripts/wg-rotate.sh                 # random exit
#   ./scripts/wg-rotate.sh us-lax-wg-12.conf   # specific exit
set -euo pipefail

cd "$(dirname "$0")/.."

CONF="${1:-}"
if [ -n "$CONF" ]; then
  export WG_GATEWAY_CONF="$CONF"
  echo "Rotating wg-gateway to pinned exit: $CONF"
else
  export WG_GATEWAY_CONF=""
  echo "Rotating wg-gateway to a random exit"
fi

docker compose --profile mullvad up -d --force-recreate wg-gateway

echo "Waiting for tunnel to come up…"
for _ in $(seq 1 20); do
  if docker compose exec -T wg-gateway wg show wg0 >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Report the new exit IP as seen from inside the tunnel.
IP="$(docker compose exec -T wg-gateway curl -s --max-time 15 https://api.ipify.org 2>/dev/null || true)"
echo "New egress IP: ${IP:-unknown}"
