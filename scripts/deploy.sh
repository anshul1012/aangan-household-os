#!/usr/bin/env bash
# Run on the VPS by .github/workflows/deploy.yml over SSH after a push to main.
set -euo pipefail

cd ~/aangan-household-os
git fetch origin main
git reset --hard origin/main
docker compose -f docker-compose.prod.yml up --build -d --remove-orphans
docker image prune -f
