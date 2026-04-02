#!/bin/bash

# Deploy the Neo4j ontology database:
#   1. Starts Neo4j (graph database)
#   2. Runs the ontology loader (seeds Neo4j from YAML data files)
#
# The loader waits for Neo4j to be healthy, imports all data from
# network_ontology/data/*.yaml, then exits.
#
# Usage: ./scripts/deploy-ontology-db.sh
#
# To tear down: ./scripts/teardown-ops.sh
# To tear down and wipe data: ./scripts/teardown-ops.sh --purge

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "Deploying ontology database..."

echo "  Starting Neo4j + ontology loader..."
docker compose -f network-ops.yaml up -d ontology ontology-loader

echo "  Waiting for ontology loader to finish seeding..."
docker wait ontology_loader 2>/dev/null || true

echo ""
echo "Ontology database is up:"
echo "  Neo4j browser: http://localhost:7474  (neo4j / ontology)"
echo "  Bolt endpoint: bolt://localhost:7687"
echo ""
echo "To re-seed after editing YAML files:"
echo "  docker compose -f network-ops.yaml up --build ontology-loader"
