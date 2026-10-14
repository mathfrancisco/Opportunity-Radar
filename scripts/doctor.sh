#!/bin/sh
set -eu

docker compose ps
docker compose exec -T api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=5); print('API liveness: process responds; database and migration status are not checked here')"
docker compose exec -T api python scripts/doctor.py
