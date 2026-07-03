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
from statistics import median

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
        # Guard anti-outlier: con >=3 precios, un valor <45% de la mediana es casi
        # seguro data corrupta (p.ej. productos rotos de Coto/VTEX). Se marca
        # 'sospechoso' y se excluye del cálculo de "mejor"/ahorro (pero se muestra).
        if len(disponibles) >= 3:
            med = median(disponibles.values())
            floor = 0.45 * med
            suspect = {p for p, v in disponibles.items() if v < floor}
            for p in suspect:
                cells[p]["suspect"] = True
            disponibles = {p: v for p, v in disponibles.items() if p not in suspect}
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
                        "canonical_key",
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


def run_timestamp() -> str:
    import datetime as _dt

    return (
        _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def write_matrix_json(matrix, platforms, ref_address, out_dir: Path, generated_at=None) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "matrix_latest.json"
    generated_at = generated_at or run_timestamp()
    path.write_text(
        json.dumps(
            {
                "reference_address": ref_address,
                "generated_at": generated_at,
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


def persist_history(offers, db_path: Path, run_ts: str) -> int:
    """Guarda las observaciones de precio de esta corrida (append-only).

    Se indexa por canonical_key (identidad ESTABLE) + run_ts, para poder unir
    el historial entre corridas y armar sparklines.
    """
    try:
        import duckdb
    except ImportError:
        return 0
    con = duckdb.connect(str(db_path))
    con.execute(
        """CREATE TABLE IF NOT EXISTS price_observations(
             canonical_key VARCHAR, platform VARCHAR, external_product_id VARCHAR,
             run_ts VARCHAR, precio_actual DOUBLE, descuento_pct DOUBLE,
             precio_por_100ml DOUBLE, stock INTEGER)"""
    )
    rows = [
        (
            o.get("canonical_key", ""),
            o["platform"],
            o["external_product_id"],
            run_ts,
            o["precio_actual"],
            o["descuento_pct"],
            o["precio_por_100ml"],
            o["stock"],
        )
        for o in offers
    ]
    con.executemany("INSERT INTO price_observations VALUES (?,?,?,?,?,?,?,?)", rows)
    con.close()
    return len(rows)


def build_history_json(db_path: Path, out_dir: Path, max_points: int = 60) -> Path | None:
    """Publica history.json: por canonical_key, la serie del precio MÍNIMO
    disponible en cada corrida (para las sparklines de la SPA).
    """
    try:
        import duckdb
    except ImportError:
        return None
    con = duckdb.connect(str(db_path))
    q = """
        SELECT canonical_key, run_ts, MIN(precio_actual) AS p
        FROM price_observations
        WHERE precio_actual > 0 AND stock > 0 AND canonical_key <> ''
        GROUP BY canonical_key, run_ts
        ORDER BY canonical_key, run_ts
    """
    series: dict[str, list] = {}
    for ckey, run_ts, p in con.execute(q).fetchall():
        series.setdefault(ckey, []).append([run_ts, round(p, 2)])
    con.close()
    # limitar a las últimas N corridas por cerveza
    series = {k: v[-max_points:] for k, v in series.items() if len(v) >= 2}
    path = out_dir / "history.json"
    path.write_text(json.dumps(series, ensure_ascii=False), encoding="utf-8")
    return path


def build_history_detail_json(db_path: Path, out_dir: Path, max_runs: int = 48) -> Path | None:
    """Publica history_detail.json: por canonical_key, una serie de precio POR
    PLATAFORMA (para el gráfico de detalle, una línea por ecommerce).
    Capado a las últimas `max_runs` corridas por plataforma.
    """
    try:
        import duckdb
    except ImportError:
        return None
    con = duckdb.connect(str(db_path))
    q = """
        SELECT canonical_key, platform, run_ts, MIN(precio_actual) AS p
        FROM price_observations
        WHERE precio_actual > 0 AND stock > 0 AND canonical_key <> ''
        GROUP BY canonical_key, platform, run_ts
        ORDER BY canonical_key, platform, run_ts
    """
    detail: dict[str, dict[str, list]] = {}
    for ckey, platform, run_ts, p in con.execute(q).fetchall():
        detail.setdefault(ckey, {}).setdefault(platform, []).append([run_ts, round(p, 2)])
    con.close()
    out = {}
    for ckey, plats in detail.items():
        trimmed = {pl: pts[-max_runs:] for pl, pts in plats.items()}
        if sum(len(v) for v in trimmed.values()) >= 2:
            out[ckey] = trimmed
    path = out_dir / "history_detail.json"
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return path


def reduce(raw_dir, out_dir, db_path=None, ref_address="Austria 2001, CABA") -> dict:
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    raw = load_latest_raw(raw_dir)
    if not raw:
        raise SystemExit(f"No hay snapshots en {raw_dir}")
    offers = build_offers(raw)
    canonicals = assign_canonicals(offers)
    platforms = sorted({o["platform"] for o in offers})
    matrix = build_matrix(canonicals, offers)
    generated_at = run_timestamp()

    json_path = write_matrix_json(matrix, platforms, ref_address, out_dir, generated_at)
    csv_path = write_matrix_csv(matrix, platforms, out_dir)
    n_hist = 0
    hist_path = None
    if db_path:
        n_hist = persist_history(offers, Path(db_path), generated_at)
        hist_path = build_history_json(Path(db_path), out_dir)
        build_history_detail_json(Path(db_path), out_dir)

    return {
        "platforms": platforms,
        "offers": len(offers),
        "canonicos": len(canonicals),
        "comparables": sum(1 for r in matrix if r["n_platforms"] > 1),
        "json": str(json_path),
        "csv": str(csv_path),
        "history": str(hist_path) if hist_path else None,
        "history_rows": n_hist,
        "matrix": matrix,
    }
