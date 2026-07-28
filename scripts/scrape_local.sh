#!/bin/bash
# Scrapea una plataforma desde ESTA máquina y sube el raw a S3.
#
# Existe porque Cloudflare bloquea las IPs de datacenter de AWS para PedidosYa:
# desde una IP residencial argentina funciona, desde Lambda da 403. El reducer
# en la nube levanta el raw más reciente de cada plataforma (ver
# BIRRAS_RAW_MAX_AGE_H), así que este scraper "fuera del pipeline" se integra solo.
#
# Uso:
#   scripts/scrape_local.sh [plataforma]      # default: pedidosya
#
# Instalar el schedule (cada 2h):
#   cp scripts/com.birras.scraper.plist ~/Library/LaunchAgents/
#   launchctl load ~/Library/LaunchAgents/com.birras.scraper.plist

set -uo pipefail

PLATFORM="${1:-pedidosya}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Config local gitignoreada (ver scripts/local.env.example)
[ -f "$REPO/scripts/local.env" ] && . "$REPO/scripts/local.env"

BUCKET="${BIRRAS_RAW_BUCKET:-}"
PROFILE="${AWS_PROFILE:-production}"

if [ -z "$BUCKET" ]; then
  echo "ERROR: falta BIRRAS_RAW_BUCKET (cp scripts/local.env.example scripts/local.env)" >&2
  exit 1
fi
PY="$REPO/.venv/bin/python"
LOG="$REPO/data/scrape_local.log"

mkdir -p "$(dirname "$LOG")"
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

cd "$REPO" || exit 1

log "scrapeando $PLATFORM desde IP local..."
OUT=$(PYTHONPATH="$REPO/services/scrapers" "$PY" -m birras_scrapers.run_local "$PLATFORM" 2>&1)
echo "$OUT" | tee -a "$LOG"

# El runner escribe data/raw/{plataforma}/{store}_{ts}.json — tomamos el más nuevo
FILE=$(ls -t "$REPO/data/raw/$PLATFORM"/*.json 2>/dev/null | head -1)
if [ -z "$FILE" ]; then
  log "ERROR: no se generó ningún archivo para $PLATFORM"
  exit 1
fi

# No subir corridas vacías (si el scraper falló, mejor dejar el dato anterior)
N=$("$PY" -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('productos',[])))" "$FILE")
if [ "$N" -lt 5 ]; then
  log "ERROR: solo $N productos en $FILE — no lo subo"
  exit 1
fi

STORE=$("$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['external_store_id'])" "$FILE")
KEY="raw/$PLATFORM/$STORE/local-$(date -u +%Y%m%dT%H%M%SZ).json"

if aws s3 cp "$FILE" "s3://$BUCKET/$KEY" --profile "$PROFILE" --only-show-errors 2>>"$LOG"; then
  log "OK: $N productos -> s3://$BUCKET/$KEY"
else
  log "ERROR: falló la subida a S3 (¿sesión SSO vencida? corré: aws sso login --profile $PROFILE)"
  exit 1
fi
