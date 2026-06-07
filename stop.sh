#!/bin/sh
# Forkmark — macOS / Linux stop script
set -e

COMPOSE_FILE="docker-compose.simple.yml"
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"

printf "\n  Stopping Forkmark...\n\n"

if docker compose version >/dev/null 2>&1; then
    docker compose -f "$COMPOSE_FILE" down
elif command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f "$COMPOSE_FILE" down
else
    printf "  Docker Compose not found.\n"
    printf "  If Forkmark is running in a terminal, press Ctrl+C there.\n\n"
    exit 1
fi

printf "\n  ✓  Forkmark stopped. Your data is preserved.\n"
printf "     Run ./start.sh to restart.\n\n"
