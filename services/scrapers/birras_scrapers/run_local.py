"""Runner local de los adapters.

Uso (desde services/scrapers/, con el venv activado):
    python -m birras_scrapers.run_local --all
    python -m birras_scrapers.run_local pedidosya
    python -m birras_scrapers.run_local rappi --out ../../data/raw

Escribe el JSON crudo de cada tienda en {out}/{plataforma}/{timestamp}.json y
muestra un resumen por consola.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .adapters.registry import available_adapters, get_adapter

_HERE = Path(__file__).resolve().parent
_DEFAULT_STORES = _HERE / "config" / "stores.json"
# repo_root/data/raw  (services/scrapers/birras_scrapers -> subir 3)
_DEFAULT_OUT = _HERE.parents[2] / "data" / "raw"


def _load_stores(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("stores", [])


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Correr adapters de scraping localmente")
    parser.add_argument(
        "adapters",
        nargs="*",
        help=f"plataformas a correr (default: todas activas). Disponibles: {available_adapters()}",
    )
    parser.add_argument("--all", action="store_true", help="correr todas las tiendas activas")
    parser.add_argument("--stores", type=Path, default=_DEFAULT_STORES, help="path a stores.json")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUT, help="directorio de salida")
    parser.add_argument("--no-write", action="store_true", help="no escribir archivos, solo resumen")
    args = parser.parse_args(argv)

    stores = _load_stores(args.stores)
    wanted = set(args.adapters)
    selected = [
        s
        for s in stores
        if s.get("active", True) and (args.all or not wanted or s["platform"] in wanted)
    ]
    if not selected:
        print(f"[!] No hay tiendas que matcheen {sorted(wanted) or 'activas'}", file=sys.stderr)
        return 1

    exit_code = 0
    for store in selected:
        platform = store["platform"]
        label = f"{platform}/{store.get('store_name', store['external_store_id'])}"
        try:
            adapter = get_adapter(platform)
        except KeyError as e:
            print(f"[!] {label}: {e}", file=sys.stderr)
            exit_code = 1
            continue

        t0 = time.time()
        try:
            result = adapter.fetch(store)
        except Exception as e:  # noqa: BLE001 — aislar fallo por adapter
            print(f"[!] {label}: FALLÓ ({type(e).__name__}: {e})", file=sys.stderr)
            exit_code = 1
            continue
        dt = time.time() - t0

        print(
            f"[+] {label}: {result.total} productos "
            f"({result.con_descuento} con descuento) en {dt:.1f}s"
        )
        if result.total == 0:
            print(f"    [!] 0 productos — revisar endpoint/anti-bot de {platform}", file=sys.stderr)
            exit_code = exit_code or 2

        if not args.no_write:
            out_dir = args.out / platform
            out_dir.mkdir(parents=True, exist_ok=True)
            ts = result.scraped_at.replace(":", "").replace("-", "")
            out_file = out_dir / f"{store['external_store_id']}_{ts}.json"
            out_file.write_text(
                json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"    -> {out_file}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
