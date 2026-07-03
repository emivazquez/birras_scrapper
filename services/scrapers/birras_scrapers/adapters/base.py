"""Interfaz común de los adapters.

Sumar un ecommerce nuevo = implementar `Adapter.fetch()` devolviendo el schema
unificado. Ni el reducer ni el frontend cambian.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..schema import ScrapeResult


class Adapter(ABC):
    #: code corto y estable de la plataforma (p.ej. "pedidosya", "rappi")
    code: str = ""
    #: nombre para mostrar
    display_name: str = ""

    @abstractmethod
    def fetch(self, store: dict) -> ScrapeResult:
        """Scrapea una tienda y devuelve el resultado en el schema unificado.

        `store` es una entrada de config con al menos:
          - external_store_id: str
          - store_name: str
          - direccion: str
          - config: dict  (parámetros específicos del adapter)
        """
        raise NotImplementedError
