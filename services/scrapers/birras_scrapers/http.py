"""Cliente HTTP compartido.

Usa curl_cffi impersonando el fingerprint TLS/JA3 de Chrome real. Necesario
porque varias plataformas (p.ej. PedidosYa) están detrás de Cloudflare Bot
Management, que bloquea el fingerprint TLS de `requests`/urllib con un challenge.
Impersonando Chrome se pasa sin necesidad de un browser headless.
"""

from __future__ import annotations

from curl_cffi import requests as cffi

from .constants import HTTP_TIMEOUT

# Perfil de impersonación de curl_cffi. "chrome" apunta a la última versión estable.
IMPERSONATE = "chrome"


def new_session(extra_headers: dict | None = None, cookies: dict | None = None):
    """Devuelve una Session de curl_cffi con impersonación de Chrome.

    No seteamos User-Agent a mano: la impersonación ya envía uno coherente con
    el fingerprint TLS (mezclarlos volvería a disparar el challenge).

    `cookies` permite reusar una sesión ya establecida (p.ej. exportada de un
    browser logueado). OJO: las cookies de anti-bot suelen estar atadas a la IP
    que las obtuvo, así que no necesariamente sirven desde otra máquina.
    Si alguna vez se usan cookies reales de un usuario, van en Secrets Manager,
    nunca en el repo.
    """
    session = cffi.Session(impersonate=IMPERSONATE, timeout=HTTP_TIMEOUT)
    headers = {"Accept-Language": "es-AR,es;q=0.9"}
    if extra_headers:
        headers.update(extra_headers)
    session.headers.update(headers)
    for k, v in (cookies or {}).items():
        session.cookies.set(k, v)
    return session
