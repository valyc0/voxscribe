#!/usr/bin/env bash
# test.sh — test dell'API di trascrizione con salvataggio JSON e misurazione del tempo
# Uso: ./test.sh [file_video] [modello] [lingua]
#   es: ./test.sh videoplayback.mp4 small it

set -e

API="http://localhost:8000"
VIDEO="${1:-videoplayback.mp4}"
MODEL="${2:-small}"
LANG="${3:-it}"
BASENAME=$(basename "$VIDEO" | sed 's/\.[^.]*$//')
OUTPUT="${BASENAME}_result.json"

# Colori
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
BOLD="\033[1m"
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

GLOBAL_START=$(date +%s%3N)

echo -e "${GREEN}${BOLD}=== Test API Trascrizione ===${RESET}"
echo "  Video   : $VIDEO"
echo "  Modello : $MODEL"
echo "  Lingua  : $LANG"
echo "  Output  : $OUTPUT"
echo "  API     : $API"

# ── 1. Health check ───────────────────────────────────────────────────────────
sep
echo -e "${CYAN}[1] Health check${RESET}"
t0=$(date +%s%3N)
curl -sf "$API/health" | python3 -c "import sys,json; json.dump(json.load(sys.stdin), sys.stdout, ensure_ascii=False, indent=2); print()"
echo -e "${YELLOW}  ⏱  $(( $(date +%s%3N) - t0 )) ms${RESET}"

# ── 2. Trascrizione ───────────────────────────────────────────────────────────
sep
echo -e "${CYAN}[2] Trascrizione (modello='$MODEL', lingua='$LANG', auto-detect speaker)${RESET}"
echo ""

t0=$(date +%s%3N)

# Salva la risposta raw su file (l'API restituisce già UTF-8 corretto)
curl -s -X POST "$API/transcribe" \
     -F "file=@$VIDEO" \
     -F "language=$LANG" \
     -F "model_size=$MODEL" \
     -o "$OUTPUT"

ELAPSED=$(( $(date +%s%3N) - t0 ))

# Ri-serializza con ensure_ascii=False per avere il file con caratteri leggibili
python3 - "$OUTPUT" <<'PYEOF'
import sys, json
path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
PYEOF

echo -e "${GREEN}File salvato: $OUTPUT${RESET}"
echo ""

# Stampa a schermo (solo dialogue + speakers per non intasare il terminale)
python3 - "$OUTPUT" <<'PYEOF'
import sys, json
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"  Speaker trovati : {', '.join(data.get('speakers', []))}")
for sp, info in data.get("speaker_details", {}).items():
    print(f"    {sp}: {info['total_segments']} segmenti, {info['total_duration_sec']:.1f}s")
print()
print("  --- Dialogo ---")
for line in data.get("dialogue", "").split("\n\n"):
    if line.strip():
        print(f"  {line.strip()}")
PYEOF

echo ""
echo -e "${YELLOW}  ⏱  Tempo trascrizione: ${ELAPSED} ms ($(( ELAPSED / 1000 )).$(( ELAPSED % 1000 / 10 )) s)${RESET}"

# ── Tempo totale ──────────────────────────────────────────────────────────────
GLOBAL_ELAPSED=$(( $(date +%s%3N) - GLOBAL_START ))
sep
echo -e "${GREEN}${BOLD}Test completati.${RESET}"
echo -e "${GREEN}${BOLD}⏱  Tempo totale: ${GLOBAL_ELAPSED} ms ($(( GLOBAL_ELAPSED / 1000 )).$(( GLOBAL_ELAPSED % 1000 / 10 )) s)${RESET}"
echo -e "${GREEN}${BOLD}📄 JSON completo: $OUTPUT${RESET}"
