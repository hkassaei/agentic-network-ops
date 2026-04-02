#!/bin/bash

# Start the operations layer:
#   1. Neo4j + ontology loader (Docker)
#   2. GUI server (Python process on the host)
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

# Source env vars for the GUI
set -a
source "$REPO_ROOT/ops.env"
set +a

echo "Starting operations layer..."

# Start Neo4j + ontology loader
echo "  Starting Neo4j ontology database..."
docker compose -f network-ops.yaml up -d ontology ontology-loader

# Start GUI server
echo "  Starting GUI server..."
if [ -d "$REPO_ROOT/gui/.venv" ]; then
    PYTHON="$REPO_ROOT/gui/.venv/bin/python3"
elif [ -d "$REPO_ROOT/.venv" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
else
    PYTHON="python3"
fi

# Start GUI in background
$PYTHON "$REPO_ROOT/gui/server.py" &
GUI_PID=$!
echo "  GUI server started (PID: $GUI_PID)"

echo ""
echo "Operations layer is up:"
echo "  GUI:      http://localhost:8073  (PID: $GUI_PID)"
echo "  Neo4j:    http://localhost:7474  (neo4j / ontology)"
echo ""
echo "Deploy the network stack from the GUI (Deploy Full Stack button),"
echo "or manually:"
echo "  docker compose -p vonr -f network/sa-vonr-deploy.yaml -f grafana-dashboards.yaml up -d"
echo ""
echo "Grafana (http://localhost:3000) will be available after the network stack starts."
echo ""
echo "To stop the GUI: kill $GUI_PID"
