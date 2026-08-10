"""Entrypoint Lambda del scraper.

Step Functions (Map) invoca esta función una vez por tienda con un evento:
    { "store": { "platform": "pedidosya", ... }, "run_id": "..." }

También la invoca directamente el schedule de reintento de PedidosYa (ver
infra/scheduler.tf), sin run_id: en ese caso se usa un timestamp.

Si BIRRAS_RAW_BUCKET está seteado, escribe el resultado crudo en
    s3://{bucket}/raw/{plataforma}/{external_store_id}/{run_id}.json
y devuelve un resumen liviano (para no inflar el payload de Step Functions).
Si no, devuelve el resultado completo inline (útil para tests).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time

from .adapters.registry import get_adapter

# Reintentos DENTRO de la Lambda, espaciados. Los reintentos de Step Functions
# son a los 3/6/12s y no le ganan a un bloqueo por reputación de IP; espaciarlos
# más da otra chance de caer en un momento en que Cloudflare deja pasar.
# (medido: PedidosYa entra ~7% de las veces desde AWS, 31% a las 22h UTC)
#
# Se configura POR PLATAFORMA: los VTEX/Coto entran al primer intento, así que
# no tiene sentido hacerlos esperar. PedidosYa es el que necesita insistir.
#   BIRRAS_SCRAPE_ATTEMPTS_PEDIDOSYA=25
DEFAULT_ATTEMPTS = int(os.environ.get("BIRRAS_SCRAPE_ATTEMPTS", "3"))
ATTEMPT_SLEEP_S = int(os.environ.get("BIRRAS_SCRAPE_SLEEP_S", "20"))
MIN_PRODUCTS = int(os.environ.get("BIRRAS_MIN_PRODUCTS", "5"))
# margen para cerrar prolijo antes de que Lambda mate la ejecución
RESERVE_MS = 20_000


def _attempts_for(platform: str) -> int:
    return int(
        os.environ.get(f"BIRRAS_SCRAPE_ATTEMPTS_{platform.upper()}", DEFAULT_ATTEMPTS)
    )


def _time_left_ms(context) -> float:
    try:
        return context.get_remaining_time_in_millis()
    except Exception:  # noqa: BLE001 — fuera de Lambda no hay context
        return float("inf")


def handler(event: dict, context=None) -> dict:
    store = event["store"]
    run_id = event.get("run_id") or dt.datetime.now(dt.timezone.utc).strftime(
        "auto-%Y%m%dT%H%M%SZ"
    )
    platform = store["platform"]
    adapter = get_adapter(platform)

    # el evento puede acotar los intentos (útil para probar rápido)
    attempts = int(event.get("attempts") or _attempts_for(platform))
    result = None
    last_error = None
    hechos = 0
    for i in range(attempts):
        hechos = i + 1
        try:
            candidate = adapter.fetch(store)
            if candidate.total >= MIN_PRODUCTS:
                result = candidate
                break
            last_error = f"solo {candidate.total} productos"
        except Exception as e:  # noqa: BLE001 — reintentamos ante cualquier fallo
            last_error = f"{type(e).__name__}: {e}"
        if i < attempts - 1:
            # cortar si no llegamos a hacer otro intento antes del timeout
            if _time_left_ms(context) < (ATTEMPT_SLEEP_S * 1000 + RESERVE_MS):
                last_error = f"{last_error} (sin tiempo para más intentos)"
                break
            time.sleep(ATTEMPT_SLEEP_S)

    if result is None:
        # Que falle: Step Functions lo aísla por item y el dashboard muestra la
        # tienda como caída. Nunca escribimos un raw vacío que pise al bueno.
        raise RuntimeError(f"{platform}: sin datos tras {hechos} intentos ({last_error})")

    payload = result.to_dict()
    bucket = os.environ.get("BIRRAS_RAW_BUCKET")
    if bucket:
        import boto3  # disponible en el runtime de Lambda

        key = f"raw/{platform}/{store['external_store_id']}/{run_id}.json"
        boto3.client("s3").put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
        return {
            "platform": platform,
            "external_store_id": store["external_store_id"],
            "total": result.total,
            "con_descuento": result.con_descuento,
            "s3_key": key,
            "run_id": run_id,
        }

    return payload
