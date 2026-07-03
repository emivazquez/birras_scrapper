"""Orquestación del reducer: raw -> ofertas normalizadas -> matching ->
matriz comparativa (JSON + CSV) + historial en DuckDB.
"""

from __future__ import annotations

import csv
import glob
import io
import json
import os
from pathlib import Path

from .match import assign_canonicals
from .normalize import normalize_offer

_OFFER_FIELDS = (
    "id",
    "nombre",
    "marca",
    "tipo",
    "volumen_ml",
    "precio_actual",
    "precio_anterior",
    "descuento_pct",
    "precio_por_100ml",
    "stock",
    "gtin",
    "beer_color",
    "beer_style",
    "abv",
    "is_zero_alcohol",
    "origen",
)


def load_latest_raw(raw_dir: Path) -> dict[str, dict]:
    """Toma el snapshot más reciente por plataforma desde raw/{plataforma}/*.json."""
    result: dict[str, dict] = {}
    for platform_dir in sorted(Path(raw_dir).glob("*")):
        if not platform_dir.is_dir():
            continue
        files = sorted(platform_dir.glob("*.json"))
        if not files:
            continue
        result[platform_dir.name] = json.loads(files[-1].read_text(encoding="utf-8"))
    return result


def build_offers(raw_by_platform: dict[str, dict]) -> list[dict]:
    offers: list[dict] = []
    for platform, res in raw_by_platform.items():
        scraped_at = res.get("fecha_scrapeo", "")
        store = res.get("external_store_id", "")
        for prod in res.get("productos", []):
            offer = {k: prod.get(k) for k in _OFFER_FIELDS}
            offer["external_product_id"] = str(prod.get("id", ""))
            offer["platform"] = platform
            offer["store"] = store
            offer["scraped_at"] = scraped_at
            offers.append(normalize_offer(offer))
    return offers


def _price_cell(offer: dict) -> dict:
    return {
        "nombre": offer["nombre"],
        "precio_actual": offer["precio_actual"],
        "precio_anterior": offer["precio_anterior"],
        "descuento_pct": offer["descuento_pct"],
        "precio_por_100ml": offer["precio_por_100ml"],
        "stock": offer["stock"],
        "disponible": bool(offer.get("stock")),
    }


def build_matrix(canonicals: list[dict], offers: list[dict]) -> list[dict]:
    by_canonical: dict[int, dict[str, dict]] = {}
    for o in offers:
        cid = o["canonical_id"]
        plat = o["platform"]
        cur = by_canonical.setdefault(cid, {})
        # si hay varias ofertas de la misma plataforma en el canónico, la más barata
        if plat not in cur or (o["precio_actual"] or 1e12) < (
            cur[plat]["precio_actual"] or 1e12
        ):
            cur[plat] = o

    rows: list[dict] = []
    for c in canonicals:
        cells = {plat: _price_cell(o) for plat, o in by_canonical.get(c["canonical_id"], {}).items()}
        disponibles = {
            plat: cell["precio_actual"]
            for plat, cell in cells.items()
            if cell["disponible"] and cell["precio_actual"]
        }
        mejor = min(disponibles, key=disponibles.get) if disponibles else None
        ahorro = (
            round(max(disponibles.values()) - min(disponibles.values()), 2)
            if len(disponibles) > 1
            else 0
        )
        rows.append(
            {
                **{
                    k: c[k]
                    for k in (
                        "canonical_id",
                        "brand_display",
                        "variant_slug",
                        "volume_ml",
                        "container",
                        "pack_qty",
                        "display_name",
                        "gtin",
                        "n_platforms",
                        "match_method",
                        "review_needed",
                    )
                },
                "precios": cells,
                "mejor": mejor,
                "ahorro_abs": ahorro,
            }
        )
    # ordenar: primero los comparables (>=2 plataformas), luego por marca
    rows.sort(key=lambda r: (-r["n_platforms"], r["brand_display"], r["volume_ml"] or 0))
    return rows


def write_matrix_json(matrix, platforms, ref_address, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "matrix_latest.json"
    path.write_text(
        json.dumps(
            {
                "reference_address": ref_address,
                "platforms": platforms,
                "total_canonicos": len(matrix),
                "comparables": sum(1 for r in matrix if r["n_platforms"] > 1),
                "products": matrix,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def write_matrix_csv(matrix, platforms, out_dir: Path) -> Path:
    path = out_dir / "matrix_latest.csv"
    base_cols = [
        "marca",
        "variante",
        "volumen_ml",
        "container",
        "pack_qty",
        "display_name",
        "gtin",
        "n_platforms",
        "mejor",
        "ahorro_abs",
    ]
    plat_cols = [f"{p}_{suf}" for p in platforms for suf in ("precio", "desc_pct", "stock")]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(base_cols + plat_cols)
    for r in matrix:
        row = [
            r["brand_display"],
            r["variant_slug"],
            r["volume_ml"],
            r["container"] or "",
            r["pack_qty"],
            r["display_name"],
            r["gtin"],
            r["n_platforms"],
            r["mejor"] or "",
            r["ahorro_abs"],
        ]
        for p in platforms:
            cell = r["precios"].get(p)
            if cell:
                row += [cell["precio_actual"], cell["descuento_pct"], cell["stock"]]
            else:
                row += ["", "", ""]
        w.writerow(row)
    # UTF-8 con BOM para Excel-AR
    path.write_text("﻿" + buf.getvalue(), encoding="utf-8")
    return path


def persist_history(offers, db_path: Path) -> int:
    try:
        import duckdb
    except ImportError:
        return 0
    con = duckdb.connect(str(db_path))
    con.execute(
        """CREATE TABLE IF NOT EXISTS price_observations(
             platform VARCHAR, external_product_id VARCHAR, canonical_id INTEGER,
             scraped_at VARCHAR, precio_actual DOUBLE, precio_anterior DOUBLE,
             descuento_pct DOUBLE, precio_por_100ml DOUBLE, stock INTEGER)"""
    )
    rows = [
        (
            o["platform"],
            o["external_product_id"],
            o["canonical_id"],
            o["scraped_at"],
            o["precio_actual"],
            o["precio_anterior"],
            o["descuento_pct"],
            o["precio_por_100ml"],
            o["stock"],
        )
        for o in offers
    ]
    con.executemany("INSERT INTO price_observations VALUES (?,?,?,?,?,?,?,?,?)", rows)
    con.close()
    return len(rows)


def reduce(raw_dir, out_dir, db_path=None, ref_address="Austria 2001, CABA") -> dict:
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    raw = load_latest_raw(raw_dir)
    if not raw:
        raise SystemExit(f"No hay snapshots en {raw_dir}")
    offers = build_offers(raw)
    canonicals = assign_canonicals(offers)
    platforms = sorted({o["platform"] for o in offers})
    matrix = build_matrix(canonicals, offers)

    json_path = write_matrix_json(matrix, platforms, ref_address, out_dir)
    csv_path = write_matrix_csv(matrix, platforms, out_dir)
    n_hist = persist_history(offers, Path(db_path)) if db_path else 0

    return {
        "platforms": platforms,
        "offers": len(offers),
        "canonicos": len(canonicals),
        "comparables": sum(1 for r in matrix if r["n_platforms"] > 1),
        "json": str(json_path),
        "csv": str(csv_path),
        "history_rows": n_hist,
        "matrix": matrix,
    }
