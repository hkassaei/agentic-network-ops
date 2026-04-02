#!/bin/bash

# Re-seed the Neo4j ontology database from YAML files.
# Rebuilds the loader image (picks up YAML changes) and re-runs it.
#
# Usage: ./scripts/reseed-ontology.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "Re-seeding ontology database..."

echo "  Rebuilding ontology loader (picks up YAML changes)..."
docker compose -f network-ops.yaml build ontology-loader

echo "  Running ontology loader..."
docker compose -f network-ops.yaml up --force-recreate ontology-loader

echo ""
echo "Ontology re-seeded from network_ontology/data/*.yaml"
