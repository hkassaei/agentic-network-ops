#!/bin/bash

# Tear down the operations layer:
#   1. Stop GUI server
#   2. Stop Neo4j + ontology loader containers
#   3. Optionally remove Neo4j data volume
#
# Usage:
#   ./scripts/teardown-ops.sh           # stop containers, keep data
#   ./scripts/teardown-ops.sh --purge   # stop containers, delete Neo4j data volume

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "Tearing down operations layer..."

# Stop GUI server
GUI_PIDS=$(pgrep -f "python.*gui/server.py" 2>/dev/null || true)
if [ -n "$GUI_PIDS" ]; then
    echo "  Stopping GUI server (PIDs: $GUI_PIDS)..."
    kill $GUI_PIDS 2>/dev/null || true
else
    echo "  GUI server not running."
fi

# Stop Neo4j + ontology loader
echo "  Stopping Neo4j and ontology loader..."
docker compose -f network-ops.yaml down

# Purge data volume if requested
if [ "$1" = "--purge" ]; then
    echo "  Removing Neo4j data volume (neo4j_ontology_data)..."
    docker volume rm neo4j_ontology_data 2>/dev/null || true
    echo "  Data purged. Next start will re-seed the ontology from YAML."
else
    echo "  Neo4j data volume retained. Use --purge to delete it."
fi

echo "Operations layer is down."
