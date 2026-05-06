#!/usr/bin/env bash
# Stop the demo stack and remove volumes (full reset).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "[teardown] docker compose -f docker-compose.demo.yml down -v"
docker compose -f docker-compose.demo.yml down -v "$@"
echo "[teardown] done."
