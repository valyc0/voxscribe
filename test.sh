#!/usr/bin/env bash
# test.sh — esempi di chiamate all'API di trascrizione
# Uso: ./test.sh [file_video]

set -e

API="http://localhost:8000"
VIDEO="${1:-videoplayback.mp4}"  # usa il primo argomento oppure il video di default

# Colori
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RESET="\033[0m"

sep() { echo -e "\n${CYAN}──────────────────────────────────────────${RESET}"; }

# ── Verifica prerequisiti ─────────────────────────────────────────────────────
if ! command -v curl &>/dev/null; then
    echo "ERRORE: curl non installato."
    exit 1
fi

if [ ! -f "$VIDEO" ]; then
    echo -e "${YELLOW}AVVISO: file '$VIDEO' non trovato.${RESET}"
    echo "Specifica un file video: ./test.sh /percorso/tuo_video.mp4"
    exit 1
fi

echo -e "${GREEN}=== Test API Trascrizione ===${RESET}"
echo "  Video  : $VIDEO"
echo "  API    : $API"

# ── 1. Health check ───────────────────────────────────────────────────────────
sep
echo -e "${CYAN}[1] Health check${RESET}"
curl -sf "$API/health" | python3 -m json.tool
echo ""

# ── 2. Trascrizione base (italiano, modello tiny — più veloce per test) ────────
sep
echo -e "${CYAN}[2] Trascrizione — italiano, modello 'small'${RESET}"
echo "Comando:"
echo "  curl -X POST $API/transcribe \\"
echo "       -F \"file=@$VIDEO\" \\"
echo "       -F \"language=it\" \\"
echo "       -F \"model_size=small\""
echo ""
curl -s -X POST "$API/transcribe" \
     -F "file=@$VIDEO" \
     -F "language=it" \
     -F "model_size=small" \
  | python3 -m json.tool
echo ""

# ── 3. Modello 'base' con rilevamento automatico della lingua ─────────────────
sep
echo -e "${CYAN}[3] Auto-detect lingua, modello 'small'${RESET}"
echo "Comando:"
echo "  curl -X POST $API/transcribe \\"
echo "       -F \"file=@$VIDEO\" \\"
echo "       -F \"language=auto\" \\"
echo "       -F \"model_size=small\""
echo ""
curl -s -X POST "$API/transcribe" \
     -F "file=@$VIDEO" \
     -F "language=auto" \
     -F "model_size=small" \
  | python3 -m json.tool
echo ""

# ── 4. Forza 2 speaker ────────────────────────────────────────────────────────
sep
echo -e "${CYAN}[4] Forza esattamente 2 interlocutori${RESET}"
echo "Comando:"
echo "  curl -X POST $API/transcribe \\"
echo "       -F \"file=@$VIDEO\" \\"
echo "       -F \"language=it\" \\"
echo "       -F \"model_size=tiny\" \\"
echo "       -F \"num_speakers=2\""
echo ""
curl -s -X POST "$API/transcribe" \
     -F "file=@$VIDEO" \
     -F "language=it" \
     -F "model_size=small" \
     -F "num_speakers=2" \
  | python3 -m json.tool
echo ""

# ── 5. Salva output su file JSON ─────────────────────────────────────────────
sep
echo -e "${CYAN}[5] Salva output in output.json${RESET}"
echo "Comando:"
echo "  curl -X POST $API/transcribe \\"
echo "       -F \"file=@$VIDEO\" \\"
echo "       -F \"language=it\" \\"
echo "       -o output.json"
echo ""
curl -s -X POST "$API/transcribe" \
     -F "file=@$VIDEO" \
     -F "language=it" \
     -o output.json
echo "File salvato: output.json"
python3 -m json.tool output.json
echo ""

sep
echo -e "${GREEN}Test completati.${RESET}"
