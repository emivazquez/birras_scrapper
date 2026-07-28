#!/bin/bash
# Instala el scraper local de PedidosYa como agente de launchd.
#
# ¿Por qué una copia fuera del repo? macOS (TCC) no le da acceso a ~/Documents
# a los procesos que lanza launchd -> "Operation not permitted". En vez de pedir
# "Acceso total al disco" (permiso amplio), instalamos una copia autocontenida
# en ~/Library/Application Support/, que no está protegida por TCC.
#
# Uso:
#   scripts/install_local_scraper.sh            # instala/actualiza + carga el agente
#   scripts/install_local_scraper.sh --uninstall
#
# Volvé a correrlo después de cambiar el código de los adapters (la copia
# instalada no se actualiza sola).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$HOME/Library/Application Support/birras-scraper"
PLIST="$HOME/Library/LaunchAgents/com.birras.scraper.plist"
LABEL="com.birras.scraper"

# Config local (gitignoreada): el nombre del bucket lleva el account id y el
# repo es público. Copiá scripts/local.env.example a scripts/local.env.
[ -f "$REPO/scripts/local.env" ] && . "$REPO/scripts/local.env"

PLATFORM="${BIRRAS_LOCAL_PLATFORM:-pedidosya}"
BUCKET="${BIRRAS_RAW_BUCKET:-}"
PROFILE="${AWS_PROFILE:-production}"

if [ -z "$BUCKET" ] && [ "${1:-}" != "--uninstall" ]; then
  echo "ERROR: falta BIRRAS_RAW_BUCKET." >&2
  echo "  cp scripts/local.env.example scripts/local.env  # y completá el bucket" >&2
  exit 1
fi

if [ "${1:-}" = "--uninstall" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  rm -rf "$DEST"
  echo "desinstalado"
  exit 0
fi

echo "[1/4] copiando el scraper a $DEST"
mkdir -p "$DEST"
rsync -a --delete "$REPO/services/scrapers/birras_scrapers" "$DEST/"

echo "[2/4] venv + dependencias"
if [ ! -x "$DEST/venv/bin/python" ]; then
  python3 -m venv "$DEST/venv"
fi
"$DEST/venv/bin/pip" install -q --upgrade pip >/dev/null 2>&1 || true
"$DEST/venv/bin/pip" install -q -r "$REPO/services/scrapers/requirements.txt"

echo "[3/4] generando el runner"
cat > "$DEST/run.sh" <<EOF
#!/bin/bash
# Generado por install_local_scraper.sh — no editar a mano.
set -uo pipefail
DEST="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)"
PY="\$DEST/venv/bin/python"
LOG="\$DEST/scraper.log"
AWS="\$(command -v aws || echo /opt/homebrew/bin/aws)"
log() { echo "[\$(date -u +%Y-%m-%dT%H:%M:%SZ)] \$*" >> "\$LOG"; }

cd "\$DEST" || exit 1
OUT_DIR="\$DEST/out"
mkdir -p "\$OUT_DIR"

log "scrapeando $PLATFORM..."
PYTHONPATH="\$DEST" "\$PY" -m birras_scrapers.run_local "$PLATFORM" --out "\$OUT_DIR" >> "\$LOG" 2>&1

FILE=\$(ls -t "\$OUT_DIR/$PLATFORM"/*.json 2>/dev/null | head -1)
[ -z "\$FILE" ] && { log "ERROR: no se generó archivo"; exit 1; }

N=\$("\$PY" -c "import json,sys; print(len(json.load(open(sys.argv[1])).get('productos',[])))" "\$FILE")
if [ "\$N" -lt 5 ]; then
  log "ERROR: solo \$N productos — no subo (dejo el dato anterior)"
  exit 1
fi

STORE=\$("\$PY" -c "import json,sys; print(json.load(open(sys.argv[1]))['external_store_id'])" "\$FILE")
KEY="raw/$PLATFORM/\$STORE/local-\$(date -u +%Y%m%dT%H%M%SZ).json"

if "\$AWS" s3 cp "\$FILE" "s3://$BUCKET/\$KEY" --profile "$PROFILE" --only-show-errors >> "\$LOG" 2>&1; then
  log "OK: \$N productos -> \$KEY"
  find "\$OUT_DIR" -name '*.json' -mtime +2 -delete 2>/dev/null
else
  log "ERROR: falló la subida (¿SSO vencido? correr: aws sso login --profile $PROFILE)"
  exit 1
fi
EOF
chmod +x "$DEST/run.sh"

echo "[4/4] instalando el agente launchd (cada 2h)"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array><string>$DEST/run.sh</string></array>
    <key>StartInterval</key><integer>7200</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$DEST/launchd.out.log</string>
    <key>StandardErrorPath</key><string>$DEST/launchd.err.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "listo. log: $DEST/scraper.log"
