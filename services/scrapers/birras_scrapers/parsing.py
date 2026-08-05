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


# --- Promociones multi-unidad (2x1, 3x2, "2do al 50%") ----------------------
# Las tiendas las publican como texto libre en campos aparte del precio, así que
# el precio unitario NO las refleja. Un "2do al 50%" es -25% por unidad llevando
# dos; un 2x1 es -50%. Son descuentos grandes que conviene mostrar.

# "2x1", "3x2" -> llevás n, pagás m
_RE_NXM = re.compile(r"\b(\d)\s*[xX×]\s*(\d)\b")
# "2do al 50%", "2da unidad al 70%", "segunda unidad 50% off"
_RE_SEGUNDA = re.compile(
    r"\b(?:2|2d[oa]|2[ªa]|segunda)\b[^%\d]{0,20}(\d{1,3})\s*%", re.I
)
# promos atadas a un medio de pago: no aplican a cualquiera, se marcan aparte
_RE_TARJETA = re.compile(r"tarjeta|banco|mi\s*crf|cuotas|visa|master|galicia|santander", re.I)


def parse_promo(texto: str, precio: float) -> Optional[dict]:
    """Interpreta el texto de una promo y calcula el precio efectivo por unidad.

    Devuelve None si no reconoce una promo multi-unidad aplicable.
    Los descuentos por medio de pago se devuelven con tipo='tarjeta' y sin
    precio efectivo (no aplican a todo el mundo).
    """
    if not texto:
        return None
    t = str(texto).strip()

    if _RE_TARJETA.search(t):
        return {"tipo": "tarjeta", "texto": t, "unidades": 0, "precio_efectivo": None}

    m = _RE_NXM.search(t)
    if m:
        n, pagas = int(m.group(1)), int(m.group(2))
        if 1 <= pagas < n <= 6:
            return {
                "tipo": "multi",
                "texto": t,
                "etiqueta": f"{n}x{pagas}",
                "unidades": n,
                "precio_efectivo": round(precio * pagas / n, 2) if precio else None,
            }

    m = _RE_SEGUNDA.search(t)
    if m:
        off = int(m.group(1))
        if 0 < off <= 100:
            # llevando 2: la 1ra full + la 2da con `off`% de descuento
            efectivo = precio * (2 - off / 100) / 2 if precio else None
            return {
                "tipo": "multi",
                "texto": t,
                "etiqueta": f"2do −{off}%",
                "unidades": 2,
                "precio_efectivo": round(efectivo, 2) if efectivo else None,
            }
    return None


def mejor_promo(textos, precio: float) -> Optional[dict]:
    """De varios textos de promo, la que deja el menor precio efectivo."""
    cands = [p for p in (parse_promo(t, precio) for t in textos or []) if p]
    multi = [p for p in cands if p["tipo"] == "multi" and p["precio_efectivo"]]
    if multi:
        return min(multi, key=lambda p: p["precio_efectivo"])
    return cands[0] if cands else None
