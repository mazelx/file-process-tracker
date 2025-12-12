#!/bin/bash

# Script de packaging pour déploiement sur NAS
# Crée une archive ZIP prête à être transférée

set -e

OUTPUT_FILE="file-tracker-deploy.zip"

echo "📦 Création du package de déploiement..."

# Supprimer l'ancien zip s'il existe
if [ -f "$OUTPUT_FILE" ]; then
    rm "$OUTPUT_FILE"
    echo "🗑️  Ancien package supprimé"
fi

# Créer le zip en excluant les fichiers inutiles
zip -r "$OUTPUT_FILE" . \
    -x "*.pyc" \
    -x "*__pycache__*" \
    -x "*.pyo" \
    -x "*\$py.class" \
    -x ".venv/*" \
    -x "venv/*" \
    -x "env/*" \
    -x "test_env/*" \
    -x "tests/*" \
    -x ".git/*" \
    -x ".gitignore" \
    -x ".gitattributes" \
    -x "*.db" \
    -x "*.test.db" \
    -x "logs/*" \
    -x "data/*" \
    -x ".pytest_cache/*" \
    -x "htmlcov/*" \
    -x ".coverage*" \
    -x "*.egg-info/*" \
    -x "build/*" \
    -x "dist/*" \
    -x ".DS_Store" \
    -x "*.swp" \
    -x "*.swo" \
    -x ".vscode/*" \
    -x ".idea/*" \
    -x "*.md" \
    -x "package.sh" \
    -x "$OUTPUT_FILE" \
    > /dev/null

echo "✅ Package créé : $OUTPUT_FILE"

# Afficher la taille du fichier
SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo "📊 Taille : $SIZE"

echo ""
echo "📋 Prochaines étapes :"
echo "1. Transférer $OUTPUT_FILE sur votre NAS"
echo "2. Dézipper le fichier"
echo "3. Copier .env.nas.example vers .env et l'éditer"
echo "4. Lancer: ./run.sh --build"
