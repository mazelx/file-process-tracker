#!/bin/bash

# Script de lancement simple pour Docker
# Usage: ./run.sh [OPTIONS]

set -e

# Charger les variables d'environnement si .env existe
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Vérifier que Docker est disponible
if ! command -v docker &> /dev/null; then
    echo "❌ Docker n'est pas installé ou n'est pas dans le PATH"
    exit 1
fi

# Build l'image si elle n'existe pas ou si --build est passé
if [ "$1" == "--build" ] || ! docker image inspect file-tracker:latest &> /dev/null; then
    echo "🔨 Building Docker image..."
    docker build -t file-tracker:latest .
    shift # Enlever --build des arguments
fi

# Lancer le container
echo "🚀 Lancement du traitement..."
docker run --rm \
    -v "${SOURCE_DIR:-/volume1/Photos}":/source:ro \
    -v "${TARGET_DIR:-/volume1/Backup}":/target \
    -v "${DATA_DIR:-$(pwd)/data}":/app/data \
    -v "${LOGS_DIR:-$(pwd)/logs}":/app/logs \
    -v "$(pwd)/config":/app/config:ro \
    -e LOG_LEVEL="${LOG_LEVEL:-INFO}" \
    file-tracker:latest "$@"

echo "✅ Terminé"
