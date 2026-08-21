"""Normalización de ofertas: marca, variante, volumen, container, pack.

Las tablas de curación (brand/variant/volume) viven en config/*.csv (dato
editable, no ifs en código). Deriva la clave canónica de cada oferta.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

_CONFIG = Path(__file__).resolve().parent / "config"


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def norm_text(s: str) -> str:
    """lower, sin tildes, solo [a-z0-9 ], espacios colapsados."""
    s = strip_accents((s or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _load_csv(name: str) -> list[dict]:
    path = _CONFIG / name
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# --- tablas de curación cargadas una vez ---
_BRAND_ROWS = _load_csv("brand_aliases.csv")
_BRAND_ALIAS: dict[str, tuple[str, str, str]] = {
    norm_text(r["alias_norm"]): (r["brand_slug"], r["brand_display"], (r.get("sub_brand") or "").strip())
    for r in _BRAND_ROWS
}
# marcas conocidas ordenadas por longitud de alias desc (para match del alias más largo primero)
_BRAND_ALIASES_SORTED = sorted(_BRAND_ALIAS, key=len, reverse=True)

_VARIANT_ALIAS: dict[str, str] = {
    norm_text(r["alias_norm"]): r["variant_slug"] for r in _load_csv("variant_aliases.csv")
}
_VARIANT_ALIASES_SORTED = sorted(_VARIANT_ALIAS, key=lambda a: len(a.split()), reverse=True)

_VOLUME_ALIAS: dict[int, int] = {
    int(r["raw_ml"]): int(r["canonical_ml"]) for r in _load_csv("volume_aliases.csv")
}

_PACK_RE = re.compile(r"(?:^|\b)(?:pack\s*(?:de|x)?\s*)?(\d{1,2})\s*[x×]\s*", re.I)
_PACK_RE2 = re.compile(r"\bx\s*(\d{1,2})\b", re.I)
_ZERO_RE = re.compile(r"0[.,]0|\bcero\b|sin alcohol|\bzero\b|\b0\s*0\b|0\s*%", re.I)


def resolve_brand(marca_raw: str, nombre_raw: str) -> tuple[str, str, str]:
    """(brand_slug, brand_display, sub_brand).

    El sub_brand mantiene visible una línea propia dentro de la marca madre
    (ej. 1890 es Quilmes, pero NO es la Quilmes regular: sin esto la fila
    quedaba como "Quilmes 473ml" y no se distinguía de la común).
    """
    marca_norm = norm_text(marca_raw)
    if marca_norm in _BRAND_ALIAS:
        return _BRAND_ALIAS[marca_norm]
    nombre_norm = norm_text(nombre_raw)
    # alias más largo que aparezca como substring de palabra en el nombre
    for alias in _BRAND_ALIASES_SORTED:
        if re.search(rf"\b{re.escape(alias)}\b", nombre_norm):
            return _BRAND_ALIAS[alias]
    # fallback: marca cruda slugificada (marca desconocida, pero se conserva)
    if marca_norm:
        return (marca_norm.replace(" ", "-"), marca_raw.strip(), "")
    # última chance: primer token del nombre
    first = nombre_norm.split(" ")[0] if nombre_norm else "desconocida"
    return (first, first.title(), "")


def resolve_variant(nombre_raw: str, tipo_raw: str) -> str:
    """variant_slug del vocabulario controlado, o 'unknown'."""
    hay = f"{norm_text(tipo_raw)} {norm_text(nombre_raw)}"
    if _ZERO_RE.search(f"{tipo_raw} {nombre_raw}"):
        return "zero"
    for alias in _VARIANT_ALIASES_SORTED:
        if re.search(rf"\b{re.escape(alias)}\b", hay):
            return _VARIANT_ALIAS[alias]
    return "unknown"


def resolve_volume(volumen_ml) -> int | None:
    if not volumen_ml:
        return None
    v = int(volumen_ml)
    return _VOLUME_ALIAS.get(v, v)


def extract_container(nombre_raw: str) -> str | None:
    n = norm_text(nombre_raw)
    if re.search(r"\blata\b|\bcc\b", n):
        return "lata"
    if re.search(r"\bbotella\b|\bporron\b|\blong neck\b", n):
        return "botella"
    return None


def extract_pack_qty(nombre_raw: str) -> int:
    n = norm_text(nombre_raw)
    m = _PACK_RE.search(n) or _PACK_RE2.search(n)
    if m:
        q = int(m.group(1))
        if 2 <= q <= 48:
            return q
    return 1


def normalize_offer(offer: dict) -> dict:
    """Agrega campos normalizados + clave canónica a una oferta (in-place)."""
    brand_slug, brand_display, sub_brand = resolve_brand(offer.get("marca", ""), offer.get("nombre", ""))
    variant = resolve_variant(offer.get("nombre", ""), offer.get("tipo", ""))
    volume = resolve_volume(offer.get("volumen_ml"))
    container = extract_container(offer.get("nombre", ""))
    pack = extract_pack_qty(offer.get("nombre", ""))
    gtin = (offer.get("gtin") or "").strip().lstrip("0")
    # sin alcohol: flag autoritativo (Rappi) o marcadores en el nombre/tipo
    is_zero = bool(offer.get("is_zero_alcohol")) or variant == "zero" or bool(
        _ZERO_RE.search(f"{offer.get('tipo', '')} {offer.get('nombre', '')}")
    )

    offer.update(
        brand_slug=brand_slug,
        brand_display=brand_display,
        sub_brand=sub_brand,
        variant_slug=variant,
        volume_ml_canon=volume,
        container=container,
        pack_qty=pack,
        is_zero=is_zero,
        nombre_norm=norm_text(offer.get("nombre", "")),
        gtin_norm=gtin,
    )
    # clave estructural: solo válida si la variante es conocida y hay volumen.
    # is_zero entra en la clave: una 0% nunca comparte identidad con la regular.
    if variant != "unknown" and volume:
        offer["structural_key"] = (brand_slug, variant, volume, pack, is_zero)
    else:
        offer["structural_key"] = None
    return offer
