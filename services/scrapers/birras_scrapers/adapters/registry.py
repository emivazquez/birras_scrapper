"""Registry de adapters: mapea code de plataforma -> instancia de Adapter.

Sumar un ecommerce nuevo = registrar su adapter acá. Los supermercados VTEX
comparten una sola instancia de VtexAdapter (se parametriza por store config).
"""

from __future__ import annotations

from .base import Adapter
from .coto import ConstructorIoAdapter
from .pedidosya import PedidosYaAdapter
from .rappi import RappiAdapter
from .vtex import VtexAdapter

_vtex = VtexAdapter()

_ADAPTERS: dict[str, Adapter] = {
    "pedidosya": PedidosYaAdapter(),
    "rappi": RappiAdapter(),
    # Supermercados sobre VTEX (mismo adapter, distinta config)
    "carrefour": _vtex,
    "jumbo": _vtex,
    "disco": _vtex,
    "vea": _vtex,
    "dia": _vtex,
    # Coto (Constructor.io)
    "coto": ConstructorIoAdapter(),
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
