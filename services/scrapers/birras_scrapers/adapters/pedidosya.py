"""Adapter PedidosYa Market.

API REST pública:
    GET /groceries/web/v1/vendors/{vendor_id}/products?categoryId={uuid}&limit=50&page=N

El endpoint está detrás de Cloudflare Bot Management (challenge), así que se
accede vía curl_cffi impersonando Chrome (ver ..http). Soporta múltiples
category_ids, deduplicando productos por id.
"""

from __future__ import annotations

from ..constants import DEFAULT_ADDRESS, HTTP_TIMEOUT
from ..http import new_session
from ..parsing import compute_descuento, parse_tipo, precio_por_100ml, to_ml
from ..schema import Product, ScrapeResult, now_iso
from .base import Adapter

BASE_API = "https://www.pedidosya.com.ar/groceries/web/v1"
# Categoría "Cervezas" (con alcohol) para la tienda Barrio Norte.
DEFAULT_CATEGORY_IDS = ["a63c106c-83de-4c01-909e-d30d24d8da85"]


def _transform(prod: dict) -> Product:
    name = prod.get("name", "")
    marca = prod.get("defaultBrandName") or ""
    size = prod.get("size") or {}
    vol_ml = to_ml(size.get("content"), size.get("unit") or "")
    pricing = prod.get("pricing") or {}
    price = pricing.get("price") or 0
    before = pricing.get("beforePrice") or price
    return Product(
        id=str(prod.get("id", "")),
        nombre=name,
        marca=marca,
        tipo=parse_tipo(name, marca),
        volumen_ml=vol_ml,
        precio_actual=price,
        precio_anterior=before,
        descuento_pct=compute_descuento(price, before),
        precio_por_100ml=precio_por_100ml(price, vol_ml),
        stock=prod.get("stock"),
        gtin=prod.get("gtin") or "",
    )


class PedidosYaAdapter(Adapter):
    code = "pedidosya"
    display_name = "PedidosYa Market"

    def _fetch_category(
        self,
        session,
        vendor_id: int,
        category_id: str,
        *,
        page_size: int = 50,
        max_pages: int = 20,
    ) -> list[dict]:
        items: list[dict] = []
        for page in range(max_pages):
            url = f"{BASE_API}/vendors/{vendor_id}/products"
            params = {"categoryId": category_id, "limit": page_size, "page": page}
            r = session.get(url, params=params, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            page_items = data.get("items", [])
            items.extend(page_items)
            if data.get("lastPage") or not page_items:
                break
        return items

    def fetch(self, store: dict) -> ScrapeResult:
        cfg = store.get("config") or {}
        vendor_id = cfg["vendor_id"]
        category_ids = cfg.get("category_ids") or DEFAULT_CATEGORY_IDS

        # cookies opcionales (sesión exportada de un browser). Ver http.new_session.
        session = new_session({"Accept": "application/json"}, cfg.get("cookies"))

        by_id: dict[str, Product] = {}
        for cat in category_ids:
            for prod in self._fetch_category(session, vendor_id, cat):
                p = _transform(prod)
                if p.id:
                    by_id[p.id] = p

        return ScrapeResult(
            platform=self.code,
            external_store_id=str(vendor_id),
            store_name=store.get("store_name", self.display_name),
            direccion=store.get("direccion", DEFAULT_ADDRESS),
            scraped_at=now_iso(),
            productos=list(by_id.values()),
            source={
                "vendor_id": vendor_id,
                "category_ids": category_ids,
                "url_api": f"{BASE_API}/vendors/{vendor_id}/products?categoryId=<uuid>",
            },
        )
