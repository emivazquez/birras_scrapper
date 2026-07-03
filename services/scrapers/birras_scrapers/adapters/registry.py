"""Registry de adapters: mapea code de plataforma -> instancia de Adapter.

Sumar un ecommerce nuevo = registrar su adapter acá.
"""

from __future__ import annotations

from .base import Adapter
from .pedidosya import PedidosYaAdapter
from .rappi import RappiAdapter

_ADAPTERS: dict[str, Adapter] = {
    a.code: a
    for a in (
        PedidosYaAdapter(),
        RappiAdapter(),
    )
}


def get_adapter(code: str) -> Adapter:
    try:
        return _ADAPTERS[code]
    except KeyError:
        raise KeyError(
            f"Adapter desconocido: {code!r}. Disponibles: {sorted(_ADAPTERS)}"
        ) from None


def available_adapters() -> list[str]:
    return sorted(_ADAPTERS)
