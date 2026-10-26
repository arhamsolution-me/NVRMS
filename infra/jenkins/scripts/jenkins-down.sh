#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JENKINS_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== Tearing Down Local Jenkins Controller ==="
cd "$JENKINS_DIR"
docker compose -f docker-compose.jenkins.yml down -v
echo "Jenkins controller and volumes removed."
