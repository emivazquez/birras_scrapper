#!/bin/bash
# Scrapea una plataforma desde ESTA máquina y sube el raw a S3.
#
# Existe porque Cloudflare bloquea las IPs de datacenter de AWS para PedidosYa:
# desde una IP residencial argentina funciona (aunque de forma intermitente, de
# ahí los reintentos). El reducer en la nube levanta el raw más reciente de cada
# plataforma (ver BIRRAS_RAW_MAX_AGE_H), así que este scraper "fuera del
# pipeline" se integra solo.
#
# Uso:
#   scripts/scrape_local.sh [plataforma]      # default: pedidosya
#
# Instalar el schedule (cada 2h): scripts/install_local_scraper.sh

set -uo pipefail

PLATFORM="${1:-pedidosya}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Config local gitignoreada (ver scripts/local.env.example)
[ -f "$REPO/scripts/local.env" ] && . "$REPO/scripts/local.env"

BUCKET="${BIRRAS_RAW_BUCKET:-}"
PROFILE="${AWS_PROFILE:-production}"
ATTEMPTS="${BIRRAS_SCRAPE_ATTEMPTS:-5}"
PY="$REPO/.venv/bin/python"
LOG="$REPO/data/scrape_local.log"

if [ -z "$BUCKET" ]; then
  echo "ERROR: falta BIRRAS_RAW_BUCKET (cp scripts/local.env.example scripts/local.env)" >&2
  exit 1
fi

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

cd "$REPO" || exit 1

# Directorio temporal POR CORRIDA: garantiza que solo subimos lo que produjo
# ESTA ejecución (si el scrapeo falla, no hay archivo y no se sube nada viejo).
RUN_DIR=$(mktemp -d)
trap 'rm -rf "$RUN_DIR"' EXIT

FILE=""
for i in $(seq 1 "$ATTEMPTS"); do
  log "scrapeando $PLATFORM (intento $i/$ATTEMPTS)..."
  PYTHONPATH="$REPO/services/scrapers" "$PY" -m birras_scrapers.run_local "$PLATFORM" \
    --out "$RUN_DIR" >>"$LOG" 2>&1
  CAND=$(ls -t "$RUN_DIR/$PLATFORM"/*.json 2>/dev/null | head -1)
  if [ -n "$CAND" ]; then
    N=$("$PY" -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('productos',[])))" "$CAND")
    if [ "$N" -ge 5 ]; then FILE="$CAND"; break; fi
    log "  solo $N productos, reintentando..."
    rm -f "$CAND"
  fi
  [ "$i" -lt "$ATTEMPTS" ] && sleep $((i * 5))
done

if [ -z "$FILE" ]; then
  log "ERROR: $PLATFORM no devolvió datos en $ATTEMPTS intentos — no subo nada (queda el dato anterior)"
  exit 1
fi

STORE=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['external_store_id'])" "$FILE")
KEY="raw/$PLATFORM/$STORE/local-$(date -u +%Y%m%dT%H%M%SZ).json"

if aws s3 cp "$FILE" "s3://$BUCKET/$KEY" --profile "$PROFILE" --only-show-errors 2>>"$LOG"; then
  log "OK: $N productos -> s3://$BUCKET/$KEY"
else
  log "ERROR: falló la subida a S3 (¿sesión SSO vencida? correr: aws sso login --profile $PROFILE)"
  exit 1
fi
