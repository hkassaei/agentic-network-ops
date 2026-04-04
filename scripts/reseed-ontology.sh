#!/bin/bash

# Re-seed the Neo4j ontology database from YAML files.
# The ontology-loader container mounts ./network_ontology as a volume,
# so it always reads the latest YAML files — no image rebuild needed.
#
# Usage: ./scripts/reseed-ontology.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "Re-seeding ontology database..."
docker compose -f network-ops.yaml run --rm -T ontology-loader
echo ""
echo "Ontology re-seeded from network_ontology/data/*.yaml"
