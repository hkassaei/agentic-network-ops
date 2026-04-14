#!/bin/bash

# Tear down the core + IMS stack and gNB.
# Does NOT tear down UEs — use teardown-ues.sh for that,
# or teardown.sh for everything.
#
# Usage: ./scripts/teardown-stack.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect the compose project name from running containers.
# The GUI deploys with -p vonr (via e2e-vonr-test.sh), but manual
# deployment from network/ dir uses project name "network".
# We detect which project the containers belong to and tear down accordingly.

echo "============================================"
echo "  Core + IMS Stack Teardown"
echo "============================================"

cd "$REPO_ROOT"

# Detect project name from a known container
CORE_PROJECT=$(docker inspect amf --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || echo "")
GNB_PROJECT=$(docker inspect nr_gnb --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || echo "")

# Stop UEs first (separate compose file)
echo ""
echo "--- Stopping UEs ---"
if docker ps --format '{{.Names}}' | grep -q "^e2e_ue"; then
    docker compose -f e2e-vonr.yaml down 2>/dev/null || true
    echo "  UEs stopped."
else
    echo "  UEs not running, skipping."
fi

# Stop gNB
echo ""
echo "--- Stopping gNB ---"
if [ -n "$GNB_PROJECT" ]; then
    docker compose -p "$GNB_PROJECT" -f network/nr-gnb.yaml down 2>/dev/null || true
    echo "  gNB stopped (project: $GNB_PROJECT)."
elif docker ps --format '{{.Names}}' | grep -q "^nr_gnb$"; then
    docker rm -f nr_gnb 2>/dev/null || true
    echo "  gNB force-removed."
else
    echo "  gNB not running, skipping."
fi

# Stop core + IMS stack
echo ""
echo "--- Stopping core + IMS stack ---"
if [ -n "$CORE_PROJECT" ]; then
    docker compose -p "$CORE_PROJECT" -f network/sa-vonr-deploy.yaml down 2>/dev/null || true
    # Also try with grafana overlay if it was used
    docker compose -p "$CORE_PROJECT" -f network/sa-vonr-deploy.yaml -f grafana-dashboards.yaml down 2>/dev/null || true
    echo "  Core stack stopped (project: $CORE_PROJECT)."
else
    echo "  No core containers detected, skipping."
fi

# Safety net: force-remove any stragglers
STRAGGLERS=$(docker ps --format '{{.Names}}' | grep -E "^(amf|smf|upf|nrf|scp|ausf|udm|udr|pcf|nssf|bsf|pcscf|icscf|scscf|pyhss|rtpengine|smsc|dns|mysql|mongo|webui|metrics|grafana|nr_gnb)$" || true)
if [ -n "$STRAGGLERS" ]; then
    echo ""
    echo "--- Removing straggler containers ---"
    echo "$STRAGGLERS" | xargs docker rm -f 2>/dev/null || true
    echo "  Stragglers removed."
fi

echo ""
echo "============================================"
echo "  Core + IMS stack teardown complete."
echo "============================================"
