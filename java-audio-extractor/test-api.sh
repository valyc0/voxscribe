#!/usr/bin/env bash
set -e

BASE_URL="http://localhost:8081/api/audio"

usage() {
    echo "Uso: $0 <comando> [opzioni]"
    echo ""
    echo "Comandi:"
    echo "  list                    Elenca i file video nella directory configurata"
    echo "  extract <filename>      Estrae l'audio MP3 dal video e lo scarica"
    echo ""
    echo "Esempi:"
    echo "  $0 list"
    echo "  $0 extract film.mp4"
    exit 1
}

cmd="${1:-}"

case "$cmd" in
    list)
        echo ">>> File video disponibili:"
        curl -s "${BASE_URL}/files" | python3 -m json.tool
        ;;

    extract)
        filename="${2:-}"
        if [[ -z "$filename" ]]; then
            echo "Errore: specifica il nome del file video."
            echo "Uso: $0 extract <filename>"
            exit 1
        fi
        echo ">>> Estrazione audio da '${filename}' ..."
        curl -s -X POST "${BASE_URL}/extract?filename=${filename}" | python3 -m json.tool
        ;;

    *)
        usage
        ;;
esac
