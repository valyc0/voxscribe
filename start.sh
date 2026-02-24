#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "=== Transcription API — Avvio Docker ==="

# ── Verifica Docker ───────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "ERRORE: docker non trovato. Installa Docker: https://docs.docker.com/engine/install/"
    exit 1
fi

# Determina il comando compose disponibile
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "ERRORE: né 'docker compose' né 'docker-compose' trovati."
    exit 1
fi

echo "Compose: $COMPOSE"

# ── Ferma eventuale istanza precedente ───────────────────────────────────────
echo "[1/3] Pulizia istanza precedente (se presente)..."
$COMPOSE down --remove-orphans 2>/dev/null || true

# Libera la porta 8000 se occupata da un altro container
BLOCKING=$(docker ps -q --filter "publish=8000" 2>/dev/null)
if [ -n "$BLOCKING" ]; then
    echo "    Porta 8000 occupata dal container $BLOCKING — lo fermo..."
    docker stop "$BLOCKING" >/dev/null
fi

# ── Build + avvio ─────────────────────────────────────────────────────────────
echo "[2/3] Build immagine e avvio container..."
$COMPOSE up --build -d

# ── Poll health ───────────────────────────────────────────────────────────────
echo "[3/3] Attendo che l'API sia pronta..."
for i in $(seq 1 60); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        echo ""
        echo "✓  API pronta su http://localhost:8000"
        echo ""
        echo "   Trascrivi un video:"
        echo "   curl -X POST http://localhost:8000/transcribe \\"
        echo "        -F 'file=@videoplayback.mp4' -F 'language=it'"
        echo ""
        echo "   Log live:  $COMPOSE logs -f"
        echo "   Stop:      $COMPOSE down"
        exit 0
    fi
    printf "."
    sleep 3
done

echo ""
echo "✗  Timeout — controlla i log:"
$COMPOSE logs --tail=40
exit 1
