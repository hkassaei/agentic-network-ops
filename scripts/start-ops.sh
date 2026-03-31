#!/bin/bash

# Start only the operations layer (GUI, ontology).
# The network stack can then be deployed from the GUI.
#
# Usage: ./scripts/start-ops.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

if [ ! -f ops.env ]; then
    echo "ERROR: ops.env not found. Copy from template:"
    echo "  cp ops.env.example ops.env"
    echo "  # Edit ops.env with your GCP project and API keys"
    exit 1
fi

# Set HOST_REPO_PATH so the GUI container can run docker compose
# with paths that resolve correctly on the host filesystem.
export HOST_REPO_PATH="$REPO_ROOT"

echo "Starting operations layer..."
echo "  Repo path: $REPO_ROOT"
docker compose -f network-ops.yaml up -d

echo ""
echo "Operations layer is up:"
echo "  GUI:      http://localhost:8073"
echo "  Neo4j:    http://localhost:7474  (neo4j / ontology)"
echo ""
echo "Deploy the network stack from the GUI (Deploy Full Stack button),"
echo "or manually:"
echo "  docker compose -p vonr -f network/sa-vonr-deploy.yaml -f grafana-dashboards.yaml up -d"
echo ""
echo "Grafana (http://localhost:3000) will be available after the network stack starts."
