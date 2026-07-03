"""Adapter Rappi Turbo.

Estrategia 100% HTTP (sin browser), vía curl_cffi impersonando Chrome:
  GET /tiendas/{store_id}-turbo/cervezas/{subaisle}
  -> el HTML embebe <script id="__NEXT_DATA__">{...}</script> con los productos
     del subaisle ya renderizados server-side.

Se parsea __NEXT_DATA__ directo del HTML. Antes se usaba el endpoint SSG
/_next/data/{buildId}/...json, pero hoy devuelve 404; el HTML trae los mismos
datos y es una request menos por subaisle. Dedup por product_id.

Limitación: como usuario anónimo hay soft-wall (~60-65 productos). El login para
catálogo completo se agrega en Fase 2.
"""

from __future__ import annotations

import json
import re

from ..constants import DEFAULT_ADDRESS
from ..http import new_session
from ..parsing import compute_descuento, parse_tipo, precio_por_100ml, to_ml
from ..schema import Product, ScrapeResult, now_iso
from .base import Adapter

BASE_URL = "https://www.rappi.com.ar"
DEFAULT_SUBAISLES = [
    "nuevos",
    "cervezas-rubias",
    "cervezas-rojas",
    "cervezas-negras",
    "packs",
]

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S
)
_BUILD_ID_RE = re.compile(r'"buildId":"([^"]+)"')


def _transform(prod: dict) -> Product:
    attrs = prod.get("attributes") or {}
    vol = to_ml(prod.get("quantity"), prod.get("unit_type", ""))
    price = prod.get("price") or 0
    real_price = prod.get("real_price") or price
    name = prod.get("name", "")
    marca = prod.get("trademark") or ""
    return Product(
        id=str(prod.get("product_id", "")),
        nombre=name,
        marca=marca,
        tipo=parse_tipo(
            name, marca, attrs.get("beer_color") or "", attrs.get("beer_style") or ""
        ),
        volumen_ml=vol,
        precio_actual=price,
        precio_anterior=real_price,
        descuento_pct=compute_descuento(price, real_price),
        precio_por_100ml=precio_por_100ml(price, vol),
        stock=prod.get("stock") or (1 if prod.get("in_stock") else 0),
        gtin=prod.get("ean") or "",
        beer_color=attrs.get("beer_color") or "",
        beer_style=attrs.get("beer_style") or "",
        abv=attrs.get("abv"),
        is_zero_alcohol=bool(attrs.get("is_zero_alcohol")),
        origen=attrs.get("beer_origin") or "",
    )


def _products_from_html(html: str, store_id: int, subaisle: str) -> list[dict]:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return []
    nd = json.loads(m.group(1))
    fallback = (
        ((nd.get("props") or {}).get("pageProps") or {}).get("fallback")
    ) or {}
    node = fallback.get(f"storefront/{store_id}-turbo/cervezas/{subaisle}") or {}
    components = (
        (node.get("aisle_detail_response") or {}).get("data", {}) or {}
    ).get("components", [])
    products: list[dict] = []
    for c in components:
        products.extend((c.get("resource") or {}).get("products") or [])
    return products


class RappiAdapter(Adapter):
    code = "rappi"
    display_name = "Rappi Turbo"

    def fetch(self, store: dict) -> ScrapeResult:
        cfg = store.get("config") or {}
        store_id = cfg["store_id"]
        subaisles = cfg.get("subaisles") or DEFAULT_SUBAISLES

        session = new_session()

        by_id: dict[str, Product] = {}
        build_id = None
        for sub in subaisles:
            url = f"{BASE_URL}/tiendas/{store_id}-turbo/cervezas/{sub}"
            r = session.get(url)
            if not r.ok:
                continue
            if build_id is None:
                bm = _BUILD_ID_RE.search(r.text)
                build_id = bm.group(1) if bm else None
            for prod in _products_from_html(r.text, store_id, sub):
                p = _transform(prod)
                if p.id:
                    by_id[p.id] = p

        return ScrapeResult(
            platform=self.code,
            external_store_id=str(store_id),
            store_name=store.get("store_name", self.display_name),
            direccion=store.get("direccion", DEFAULT_ADDRESS),
            scraped_at=now_iso(),
            productos=list(by_id.values()),
            source={
                "store_id": store_id,
                "subaisles": subaisles,
                "build_id": build_id,
                "method": "__NEXT_DATA__ (HTML SSR)",
            },
        )
