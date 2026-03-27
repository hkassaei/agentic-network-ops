#!/bin/bash

# Tear down the core + IMS stack and gNB.
# Does NOT tear down UEs — use teardown-ues.sh for that,
# or teardown.sh for everything.
#
# Usage: ./scripts/teardown-stack.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Docker Compose project names — must match what deploy scripts use
COMPOSE_CORE="-p vonr -f network/sa-vonr-deploy.yaml -f docker-compose.grafana.yml"
COMPOSE_GNB="-p vonr-gnb -f network/nr-gnb.yaml"

echo "============================================"
echo "  Core + IMS Stack Teardown"
echo "============================================"

cd "$REPO_ROOT"

# Stop gNB
echo ""
echo "--- Stopping gNB ---"
if docker ps --format '{{.Names}}' | grep -q "^nr_gnb$"; then
    docker compose $COMPOSE_GNB down
    echo "  gNB stopped."
else
    echo "  gNB not running, skipping."
fi

# Stop core + IMS stack
echo ""
echo "--- Stopping core + IMS stack ---"
docker compose $COMPOSE_CORE down
echo "  Core stack stopped."

echo ""
echo "============================================"
echo "  Core + IMS stack teardown complete."
echo "============================================"
