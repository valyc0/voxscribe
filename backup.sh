#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_NAME="../backup_${TIMESTAMP}.tar.gz"

# File da includere nel backup
FILES=(
    app.py
    transcriber.py
    diarizer.py
    audio_utils.py
    requirements.txt
    Dockerfile
    docker-compose.yml
    start.sh
    test.sh
    backup.sh
)

# Filtra solo i file che esistono
EXISTING=()
for f in "${FILES[@]}"; do
    [ -f "$f" ] && EXISTING+=("$f") || echo "  AVVISO: $f non trovato, saltato"
done

echo "=== Backup — $TIMESTAMP ==="
echo "File inclusi: ${#EXISTING[@]}"
for f in "${EXISTING[@]}"; do
    printf "  + %s (%s)\n" "$f" "$(du -sh "$f" | cut -f1)"
done

tar -czf "$BACKUP_NAME" "${EXISTING[@]}"

echo ""
echo "✓  Backup creato: $BACKUP_NAME ($(du -sh "$BACKUP_NAME" | cut -f1))"
