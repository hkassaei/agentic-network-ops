FROM python:3.12-slim

WORKDIR /app

COPY network_ontology/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY network_ontology/ /app/network_ontology/

# The loader runs once, seeds Neo4j, then exits.
# Docker Compose restart: "no" means it won't restart after success.
CMD ["python3", "-m", "network_ontology", "--uri", "bolt://ontology:7687", "--reset", "-v"]
