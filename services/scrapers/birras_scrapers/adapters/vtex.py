"""Adapter VTEX — cubre los supermercados AR que corren sobre VTEX
(Carrefour, Jumbo, Disco, Vea, Día) con UN solo adapter parametrizable.

API pública de catálogo (sin login):
    GET {base}/api/catalog_system/pub/products/search/{category_path}?_from=N&_to=M

- Los 5 usan el path de categoría `bebidas/cervezas`.
- Paginación de a 50 (límite de VTEX); total en el header `resources: a-b/TOTAL`.
- EAN poblado (ancla determinística para el matching con PedidosYa).

PRECIO CABA (verificado 2026-07-03): el precio del catálogo es por BANNER
(nacional), no por sucursal. Confirmado en Carrefour: el precio con el regionId
de CABA (CP 1425) es idéntico al default. Cada banner tiene su propio precio
(Jumbo != Disco) pero dentro del banner es el estándar -> el default que traemos
ES el precio que vería un comprador en CABA. No hace falta setear región/sc.

El code de plataforma (carrefour/jumbo/...) viene de store["platform"]; la misma
instancia de VtexAdapter se registra bajo los 5 codes.
"""

from __future__ import annotations

from ..constants import DEFAULT_ADDRESS
from ..http import new_session
from ..parsing import (
    compute_descuento,
    parse_tipo,
    parse_volumen_ml_from_name,
    precio_por_100ml,
)
from ..schema import Product, ScrapeResult, now_iso
from .base import Adapter

DEFAULT_CATEGORY_PATH = "bebidas/cervezas"
PAGE_SIZE = 50  # máximo de VTEX por request
DEFAULT_MAX_PRODUCTS = 500


def _parse_total(resources_header: str | None) -> int | None:
    # formato "0-49/467"
    if not resources_header or "/" not in resources_header:
        return None
    try:
        return int(resources_header.split("/")[-1])
    except ValueError:
        return None


def _transform(p: dict) -> Product | None:
    items = p.get("items") or []
    if not items:
        return None
    item = items[0]
    sellers = item.get("sellers") or []
    offer = (sellers[0].get("commertialOffer") if sellers else {}) or {}

    name = p.get("productName") or item.get("nameComplete") or ""
    marca = p.get("brand") or ""
    ean = item.get("ean") or ""
    price = offer.get("Price") or 0
    list_price = offer.get("ListPrice") or price
    # Cencosud (Disco/Jumbo/Vea) a veces devuelve un ListPrice basura (enorme),
    # que daría un descuento imposible (~99%). Si el descuento implícito es
    # absurdo (>85%), ignoramos el ListPrice: sin descuento.
    if list_price and price and list_price > price * 6:
        list_price = price
    avail = offer.get("AvailableQuantity") or 0
    vol = parse_volumen_ml_from_name(name)

    return Product(
        id=str(p.get("productId") or item.get("itemId") or ean or name),
        nombre=name,
        marca=marca,
        tipo=parse_tipo(name, marca),
        volumen_ml=vol,
        precio_actual=price,
        precio_anterior=list_price,
        descuento_pct=compute_descuento(price, list_price),
        precio_por_100ml=precio_por_100ml(price, vol),
        stock=avail,
        gtin=ean,
    )


class VtexAdapter(Adapter):
    code = "vtex"
    display_name = "VTEX"

    def fetch(self, store: dict) -> ScrapeResult:
        cfg = store.get("config") or {}
        base = cfg["base_url"].rstrip("/")
        cat_path = cfg.get("category_path", DEFAULT_CATEGORY_PATH)
        max_products = cfg.get("max_products", DEFAULT_MAX_PRODUCTS)

        session = new_session({"Accept": "application/json"})
        by_id: dict[str, Product] = {}
        frm = 0
        total = None
        while frm < max_products:
            to = frm + PAGE_SIZE - 1
            url = f"{base}/api/catalog_system/pub/products/search/{cat_path}?_from={frm}&_to={to}"
            r = session.get(url)
            if r.status_code not in (200, 206):
                break
            batch = r.json()
            if not batch:
                break
            if total is None:
                total = _parse_total(r.headers.get("resources"))
            for p in batch:
                prod = _transform(p)
                if prod and prod.id:
                    by_id[prod.id] = prod
            frm += PAGE_SIZE
            if total is not None and frm >= total:
                break

        return ScrapeResult(
            platform=store.get("platform", self.code),
            external_store_id=str(store.get("external_store_id", cat_path)),
            store_name=store.get("store_name", self.display_name),
            direccion=store.get("direccion", DEFAULT_ADDRESS),
            scraped_at=now_iso(),
            productos=list(by_id.values()),
            source={
                "base_url": base,
                "category_path": cat_path,
                "total_disponible": total,
                "max_products": max_products,
            },
        )
