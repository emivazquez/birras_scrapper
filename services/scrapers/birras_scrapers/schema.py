"""Schema unificado de producto y envelope de resultado de scrapeo.

Todos los adapters emiten `Product` con los mismos campos, sin importar la
plataforma de origen. Los campos de cerveza (beer_color, abv, ...) son opcionales
y solo algunos adapters (Rappi, VTEX) los llenan.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class Product:
    """Un producto (cerveza) tal como lo emite un adapter. Schema unificado."""

    id: str  # id externo estable en la plataforma
    nombre: str
    marca: str
    tipo: str
    volumen_ml: Optional[int]
    precio_actual: float
    precio_anterior: float
    descuento_pct: float
    precio_por_100ml: Optional[float]
    stock: Optional[int]
    gtin: str = ""

    # Promoción multi-unidad (2x1, "2do al 50%"): el precio unitario NO la
    # refleja, la tienda la publica aparte. precio_efectivo = por unidad
    # llevando `promo_unidades`.
    promo_etiqueta: str = ""
    promo_texto: str = ""
    promo_tipo: str = ""  # "multi" | "tarjeta"
    promo_unidades: int = 0
    promo_precio_efectivo: Optional[float] = None

    # Atributos de cerveza opcionales (los llenan Rappi / VTEX cuando existen)
    beer_color: str = ""
    beer_style: str = ""
    abv: Optional[float] = None
    is_zero_alcohol: bool = False
    origen: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScrapeResult:
    """Envelope del resultado de una corrida de un adapter sobre una tienda."""

    platform: str  # code de plataforma: 'pedidosya', 'rappi', ...
    external_store_id: str
    store_name: str
    direccion: str
    scraped_at: str  # ISO-8601 UTC
    productos: list[Product]
    source: dict = field(default_factory=dict)  # metadata específica del adapter

    @property
    def total(self) -> int:
        return len(self.productos)

    @property
    def con_descuento(self) -> int:
        return sum(1 for p in self.productos if (p.descuento_pct or 0) > 0)

    def to_dict(self) -> dict:
        return {
            "plataforma": self.platform,
            "external_store_id": self.external_store_id,
            "tienda": self.store_name,
            "direccion": self.direccion,
            "fecha_scrapeo": self.scraped_at,
            "source": self.source,
            "total": self.total,
            "con_descuento": self.con_descuento,
            "productos": [p.to_dict() for p in self.productos],
        }


def now_iso() -> str:
    """Timestamp ISO-8601 en UTC, con sufijo Z."""
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
