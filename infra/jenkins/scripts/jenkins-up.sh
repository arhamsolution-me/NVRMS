#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JENKINS_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$(dirname "$JENKINS_DIR")")"

echo "=== Starting Local Jenkins Controller ==="

# Check environment file
if [ ! -f "$JENKINS_DIR/.env" ]; then
    echo "Creating .env from .env.example..."
    cp "$JENKINS_DIR/.env.example" "$JENKINS_DIR/.env"
fi

cd "$JENKINS_DIR"

# Build agent image first
echo "Building Jenkins build agent image (nvrsms-build-agent:1.0.0)..."
docker build -t nvrsms-build-agent:1.0.0 -t nvrsms-build-agent:latest -f Dockerfile .

# Start controller and DinD
echo "Starting Jenkins controller..."
docker compose -f docker-compose.jenkins.yml up -d --build

echo "Waiting for Jenkins controller to be healthy at http://127.0.0.1:8080..."
for i in {1..60}; do
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/login | grep -q "200"; then
        echo "Jenkins controller is UP and reachable at http://127.0.0.1:8080"
        exit 0
    fi
    sleep 2
done

echo "Jenkins did not respond within 120 seconds. Checking logs:"
docker compose -f docker-compose.jenkins.yml logs --tail=50
exit 1
