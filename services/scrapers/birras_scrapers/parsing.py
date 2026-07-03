"""Funciones puras de parseo/derivación compartidas por los adapters.

Portadas de los scrapers originales (scraper_pedidosya.py / scraper_rappi.py),
unificadas acá para no duplicar. Son la base del schema unificado.
"""

from __future__ import annotations

import re
from typing import Optional


def to_ml(value, unit: str) -> Optional[int]:
    """Convierte (cantidad, unidad) a mililitros enteros. None si no se puede."""
    if not value:
        return None
    u = (unit or "").strip().lower()
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if u in ("ml", "cc", "cm3", "cm³"):
        return int(round(v))
    if u in ("l", "lt", "litro", "litros"):
        return int(round(v * 1000))
    if u in ("cl",):
        return int(round(v * 10))
    return int(round(v))


def parse_volumen_ml_from_name(name: str) -> Optional[int]:
    """Extrae el volumen en ml del nombre (fallback cuando no viene estructurado)."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(ml|cc|cm3|l|lt|cl)\b", name, flags=re.I)
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    return to_ml(value, m.group(2))


def parse_tipo(name: str, marca: str, color: str = "", style: str = "") -> str:
    """Deriva el 'tipo'/variante sacando 'Cerveza' + marca + volumen del nombre.

    Si tras limpiar queda vacío, cae a estilo o color (cuando existen).
    """
    t = name or ""
    t = re.sub(r"^Cerveza\s+", "", t, flags=re.I)
    if marca:
        t = re.sub(r"\b" + re.escape(marca) + r"\b", "", t, flags=re.I)
    t = re.sub(r"\bCerveza\b", "", t, flags=re.I)
    t = re.sub(r"\d+(?:[.,]\d+)?\s*(?:m[lL]|cc|cm3|L|lt|cl)\b", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" ,-")
    if not t and style:
        return style
    if not t and color:
        return color
    return t


def compute_descuento(price: float, before: float) -> float:
    """% de descuento redondeado a 2 decimales. 0 si no hay descuento."""
    if before and price and before > price:
        return round((1 - price / before) * 10000) / 100
    return 0.0


def precio_por_100ml(price: float, volumen_ml: Optional[int]) -> Optional[float]:
    if price and volumen_ml:
        return round(price / volumen_ml * 10000) / 100
    return None
