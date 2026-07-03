"""Entrypoint Lambda del scraper.

Step Functions (Map) invoca esta función una vez por tienda con un evento:
    { "store": { "platform": "pedidosya", "external_store_id": "356102", ... } }

Si BIRRAS_RAW_BUCKET está seteado, escribe el resultado crudo en
    s3://{bucket}/raw/{plataforma}/{external_store_id}/{run_id}.json
y devuelve un resumen liviano (para no inflar el payload de Step Functions).
Si no, devuelve el resultado completo inline (útil para tests).
"""

from __future__ import annotations

import json
import os

from .adapters.registry import get_adapter


def handler(event: dict, context=None) -> dict:
    store = event["store"]
    run_id = event.get("run_id", "adhoc")
    platform = store["platform"]

    adapter = get_adapter(platform)
    result = adapter.fetch(store)
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
