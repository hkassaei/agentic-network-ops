FROM python:3.12-slim

# Install Docker CLI (needed for docker exec, docker logs, docker ps)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg iputils-ping && \
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
        https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
        > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends docker-ce-cli docker-compose-plugin && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
# GUI deps + agent deps + ontology deps
COPY gui/requirements.txt /app/gui/requirements.txt
COPY network_ontology/requirements.txt /app/network_ontology/requirements.txt
RUN pip install --no-cache-dir \
    -r /app/gui/requirements.txt \
    -r /app/network_ontology/requirements.txt

# Copy application code
COPY gui/ /app/gui/
COPY agentic_ops/ /app/agentic_ops/
COPY agentic_ops_v3/ /app/agentic_ops_v3/
COPY agentic_ops_v4/ /app/agentic_ops_v4/
COPY network_ontology/ /app/network_ontology/
COPY e2e.env /app/e2e.env
COPY scripts/ /app/scripts/

# The network .env is mounted at runtime (from submodule)
# Docker socket is mounted at runtime

EXPOSE 8073

CMD ["python3", "gui/server.py"]
