"""Adapter Coto (cotodigital.com.ar) — vía Constructor.io.

    GET https://ac.cnstrc.com/search/{query}?key={key}&num_results_per_page=50&page=N

Cuidados (validados en recon 2026-07-03):
- **Precio real = MEDIANA del `listPrice` por sucursal**, NO `product_list_price`
  (ese es el precio de lista, ~50-80% más alto → inflaría los precios de Coto).
  La mediana = el precio que cobra la mayoría de las sucursales (incl. CABA); no
  se puede fijar la sucursal CABA exacta porque Coto no expone las sucursales por
  API pública (el listado es un SPA Angular sin datos server-side) y el orden de
  stores no es consistente. La mediana es el mejor proxy CABA disponible.
- Coto **no trae EAN** → matchea solo por estructura/fuzzy (como Rappi).
- La búsqueda por texto "cerveza" incluye accesorios (tarros, vasos): se filtran.
- Precios corruptos ocasionales (una 970cc a $153): se filtran por piso de $/100ml.
- La key de Constructor.io puede rotar; si falla, re-extraer del bundle JS.
"""

from __future__ import annotations

import re
from statistics import median

from ..constants import DEFAULT_ADDRESS
from ..http import new_session
from ..parsing import (
    compute_descuento,
    mejor_promo,
    parse_tipo,
    parse_volumen_ml_from_name,
    precio_por_100ml,
)
from ..schema import Product, ScrapeResult, now_iso
from .base import Adapter

SEARCH_URL = "https://ac.cnstrc.com/search"
DEFAULT_KEY = "key_41VWjhgxyQGjBiyf"
PAGE_SIZE = 50

# Accesorios que aparecen en la búsqueda "cerveza" pero no son cerveza.
_NON_BEER = re.compile(
    r"\b(tarro|vaso|copa|chopera|choperas|heladera|conservadora|kit|combo|"
    r"regalo|sifon|sif[oó]n|dispenser|apertura|destapador|posavaso)\b",
    re.I,
)
# Pisos de sanidad: nada de cerveza real por debajo de esto.
MIN_PRICE = 300
MIN_PRICE_PER_100ML = 60


def _median_store_price(data: dict) -> float | None:
    prices = [x.get("listPrice") for x in (data.get("price") or []) if x.get("listPrice")]
    return float(median(prices)) if prices else None


def _transform(item: dict) -> Product | None:
    d = item.get("data") or {}
    name = str(d.get("sku_display_name") or item.get("value") or "")
    if not name or _NON_BEER.search(name):
        return None
    price = _median_store_price(d)
    if not price or price < MIN_PRICE:
        return None
    vol = parse_volumen_ml_from_name(name)
    ppc = precio_por_100ml(price, vol)
    if ppc is not None and ppc < MIN_PRICE_PER_100ML:
        return None  # precio corrupto (implausiblemente barato para el volumen)

    marca = str(d.get("product_brand") or "")
    # product_list_price como "precio anterior" solo si es un descuento plausible
    list_price = d.get("product_list_price") or price
    if not (price < list_price <= price * 2.2):
        list_price = price  # no confiamos el tachado si es absurdo

    # Coto publica las promos en `discounts` (ej. "2x1", "25%Dto"), aparte del precio
    textos = [
        (x.get("discountText") or "") for x in (d.get("discounts") or []) if isinstance(x, dict)
    ]
    promo = mejor_promo(textos, price) or {}

    return Product(
        id=str(d.get("id") or d.get("sku_plu") or item.get("value")),
        nombre=name,
        marca=marca,
        tipo=parse_tipo(name, marca),
        volumen_ml=vol,
        precio_actual=price,
        precio_anterior=list_price,
        descuento_pct=compute_descuento(price, list_price),
        precio_por_100ml=ppc,
        stock=1,  # Coto no da stock claro; asumimos disponible
        gtin="",
        promo_etiqueta=promo.get("etiqueta", ""),
        promo_texto=promo.get("texto", ""),
        promo_tipo=promo.get("tipo", ""),
        promo_unidades=promo.get("unidades", 0),
        promo_precio_efectivo=promo.get("precio_efectivo"),
    )


class ConstructorIoAdapter(Adapter):
    code = "coto"
    display_name = "Coto"

    def fetch(self, store: dict) -> ScrapeResult:
        cfg = store.get("config") or {}
        key = cfg.get("cnstrc_key", DEFAULT_KEY)
        query = cfg.get("query", "cerveza")
        max_products = cfg.get("max_products", 400)

        session = new_session({"Accept": "application/json"})
        by_id: dict[str, Product] = {}
        page = 1
        total = None
        while len(by_id) < max_products:
            r = session.get(
                f"{SEARCH_URL}/{query}",
                params={"key": key, "num_results_per_page": PAGE_SIZE, "page": page},
            )
            if not r.ok:
                break
            resp = (r.json() or {}).get("response") or {}
            results = resp.get("results") or []
            if not results:
                break
            if total is None:
                total = resp.get("total_num_results") or 0
            for it in results:
                prod = _transform(it)
                if prod and prod.id:
                    by_id[prod.id] = prod
            page += 1
            if total and (page - 1) * PAGE_SIZE >= total:
                break

        return ScrapeResult(
            platform=store.get("platform", self.code),
            external_store_id=str(store.get("external_store_id", "coto")),
            store_name=store.get("store_name", self.display_name),
            direccion=store.get("direccion", DEFAULT_ADDRESS),
            scraped_at=now_iso(),
            productos=list(by_id.values()),
            source={"query": query, "total_disponible": total, "precio": "mediana por sucursal"},
        )
