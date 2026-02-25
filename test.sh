#!/usr/bin/env bash
# test.sh -- test dell'API asincrona VoxScribe
# Uso: ./test.sh [file_video] [modello] [lingua] [poll_interval_sec]
#   es: ./test.sh videoplayback.mp4 small it 5

set -e

API="http://localhost:8000"
VIDEO="${1:-videoplayback.mp4}"
MODEL="${2:-small}"
LANG="${3:-it}"
POLL="${4:-5}"
BASENAME=$(basename "$VIDEO" | sed 's/\.[^.]*$//')
OUTPUT="${BASENAME}_result.json"

# Colori
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
RESET="\033[0m"

sep() { echo -e "\n${CYAN}------------------------------------------${RESET}"; }

# Verifica prerequisiti
if ! command -v curl &>/dev/null; then
    echo "ERRORE: curl non installato."
    exit 1
fi
if ! command -v jq &>/dev/null; then
    echo "ERRORE: jq non installato. Installa con: apt-get install jq"
    exit 1
fi

if [ ! -f "$VIDEO" ]; then
    echo -e "${YELLOW}AVVISO: file '$VIDEO' non trovato.${RESET}"
    echo "Specifica un file video: ./test.sh /percorso/tuo_video.mp4"
    exit 1
fi

GLOBAL_START=$(date +%s%3N)

echo -e "${GREEN}${BOLD}=== Test API VoxScribe (async) ===${RESET}"
echo "  Video         : $VIDEO"
echo "  Modello       : $MODEL"
echo "  Lingua        : $LANG"
echo "  Output        : $OUTPUT"
echo "  API           : $API"
echo "  Poll interval : ${POLL}s"

# 1. Health check
sep
echo -e "${CYAN}[1] Health check${RESET}"
t0=$(date +%s%3N)
curl -sf "$API/health" | jq .
echo -e "${YELLOW}  ($(( $(date +%s%3N) - t0 )) ms)${RESET}"

# 2. Upload file
sep
echo -e "${CYAN}[2] Upload file (POST /transcribe)${RESET}"
t0=$(date +%s%3N)

UPLOAD_RESP=$(curl -s -X POST "$API/transcribe" \
     -F "file=@$VIDEO" \
     -F "language=$LANG" \
     -F "model_size=$MODEL")

echo "$UPLOAD_RESP" | jq .
ELAPSED_UPLOAD=$(( $(date +%s%3N) - t0 ))
echo -e "${YELLOW}  upload + risposta: ${ELAPSED_UPLOAD} ms${RESET}"

JOB_ID=$(echo "$UPLOAD_RESP" | jq -r '.job_id')
STATUS=$(echo  "$UPLOAD_RESP" | jq -r '.status')

if [ -z "$JOB_ID" ] || [ "$JOB_ID" = "null" ]; then
    echo -e "${RED}ERRORE: nessun job_id nella risposta.${RESET}"
    exit 1
fi

echo ""
echo -e "  job_id : ${BOLD}$JOB_ID${RESET}"
echo -e "  status : $STATUS"

# 3. Polling status (salta se gia' done)
if [ "$STATUS" != "done" ]; then
    sep
    echo -e "${CYAN}[3] Polling GET /status/$JOB_ID (ogni ${POLL}s)${RESET}"
    POLL_START=$(date +%s%3N)
    ATTEMPT=0

    while true; do
        sleep "$POLL"
        ATTEMPT=$(( ATTEMPT + 1 ))
        STATUS_RESP=$(curl -s "$API/status/$JOB_ID")
        STATUS=$(echo "$STATUS_RESP" | jq -r '.status')
        ELAPSED_POLL=$(( $(date +%s%3N) - POLL_START ))
        echo -e "  [${ATTEMPT}] status=${BOLD}$STATUS${RESET}  (${ELAPSED_POLL} ms)"

        if [ "$STATUS" = "done" ]; then
            break
        fi
        if [ "$STATUS" = "error" ]; then
            ERR=$(echo "$STATUS_RESP" | jq -r '.error')
            echo -e "${RED}ERRORE dal server: $ERR${RESET}"
            exit 1
        fi
    done
else
    echo -e "${GREEN}  File gia' elaborato -- salto polling.${RESET}"
fi

# 4. Download risultato
sep
echo -e "${CYAN}[4] Download risultato (GET /result/$JOB_ID)${RESET}"
t0=$(date +%s%3N)

curl -s "$API/result/$JOB_ID" | \
    python3 -c "
import sys, json
data = json.load(sys.stdin)
with open('$OUTPUT', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write('\n')
preview = json.dumps(data, ensure_ascii=False, indent=2)
print(preview[:300] + ('...' if len(preview) > 300 else ''))
"

echo -e "${GREEN}  File salvato: $OUTPUT${RESET}"
echo -e "${YELLOW}  download: $(( $(date +%s%3N) - t0 )) ms${RESET}"

# 5. Riepilogo
sep
python3 - "$OUTPUT" <<'PYEOF'
import sys, json
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"  job_id          : {data.get('job_id', '?')}")
print(f"  Speaker trovati : {', '.join(data.get('speakers', []))}")
for sp, info in data.get("speaker_details", {}).items():
    print(f"    {sp}: {info['total_segments']} segmenti, {info['total_duration_sec']:.1f}s")
print()
print("  --- Dialogo (prime 20 righe) ---")
for i, line in enumerate(data.get("dialogue", "").split("\n\n")):
    if line.strip():
        print(f"  {line.strip()}")
    if i >= 19:
        print("  ...")
        break
PYEOF

# 6. Lista job in memoria
sep
echo -e "${CYAN}[5] Ultimi job in memoria (GET /jobs?limit=5)${RESET}"
curl -s "$API/jobs?limit=5" | jq '{total_in_memory: .total_in_memory, ultimi: [.jobs[] | {job_id: .job_id[:12], status, created_at}]}'

# Tempo totale
GLOBAL_ELAPSED=$(( $(date +%s%3N) - GLOBAL_START ))
sep
echo -e "${GREEN}${BOLD}Test completati.${RESET}"
echo -e "${GREEN}${BOLD}Tempo totale: ${GLOBAL_ELAPSED} ms ($(( GLOBAL_ELAPSED / 1000 )).$(( GLOBAL_ELAPSED % 1000 / 10 )) s)${RESET}"
echo -e "${GREEN}${BOLD}JSON completo: $OUTPUT${RESET}"
