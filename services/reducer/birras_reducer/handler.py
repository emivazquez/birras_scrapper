"""Entrypoint Lambda del reducer.

Se invoca al final del fan-out de scrapers (Step Functions). Evento:
    { "run_id": "2026-07-03T14:00Z" }

Flujo:
  1. baja de S3 los raw de esta corrida (raw/{plataforma}/{store}/{run_id}.json)
  2. resuelve identidad y arma la matriz (birras_reducer.reduce)
  3. sube a S3 published/matrix_latest.json + .csv (lo que sirve el dashboard)
  4. acumula historial en catalog.duckdb (baja/sube el archivo desde S3)

Buckets vía env: BIRRAS_RAW_BUCKET, BIRRAS_PUBLISHED_BUCKET.
Localmente (sin buckets) no se usa: para eso está run_local.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .reduce import (
    assign_canonicals,
    build_history_detail_json,
    build_history_json,
    build_matrix,
    build_offers,
    persist_history,
    platform_health,
    run_timestamp,
    write_matrix_csv,
    write_matrix_json,
)

_TMP = Path("/tmp/birras")
_RAW = _TMP / "raw"
_PUB = _TMP / "published"


def _s3():
    import boto3

    return boto3.client("s3")


def _download_run_raw(bucket: str, run_id: str) -> dict[str, dict]:
    """Baja los raw de esta corrida y los agrupa por plataforma (último por plataforma)."""
    s3 = _s3()
    raw_by_platform: dict[str, dict] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix="raw/"):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(f"{run_id}.json"):
                continue
            body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
            res = json.loads(body)
            raw_by_platform[res.get("plataforma", key.split("/")[1])] = res
    return raw_by_platform


def handler(event: dict, context=None) -> dict:
    run_id = event["run_id"]
    raw_bucket = os.environ["BIRRAS_RAW_BUCKET"]
    pub_bucket = os.environ["BIRRAS_PUBLISHED_BUCKET"]
    ref_address = event.get("reference_address", "Austria 2001, CABA")

    _PUB.mkdir(parents=True, exist_ok=True)

    raw = _download_run_raw(raw_bucket, run_id)
    if not raw:
        return {"run_id": run_id, "error": "no raw snapshots for run"}

    offers = build_offers(raw)
    platforms = sorted({o["platform"] for o in offers})
    # plataformas que SE ESPERABAN en esta corrida (vienen del input del pipeline)
    expected = sorted({s["platform"] for s in (event.get("stores") or [])}) or platforms

    # Guard anti-degradación: si un adapter cayó (p.ej. Cloudflare 403 a PedidosYa
    # desde la IP de AWS) y quedó una sola plataforma, NO republicar — dejamos la
    # última matriz buena. El próximo run (o el cron) la recupera.
    min_platforms = int(os.environ.get("BIRRAS_MIN_PLATFORMS", "2"))
    if len(platforms) < min_platforms:
        return {
            "run_id": run_id,
            "published": False,
            "reason": "partial",
            "platforms": platforms,
            "faltantes": sorted(set(expected) - set(platforms)),
            "offers": len(offers),
        }

    canonicals = assign_canonicals(offers)
    matrix = build_matrix(canonicals, offers)
    generated_at = run_timestamp()

    # historial en DuckDB (baja/sube el archivo del bucket) + history.json
    s3 = _s3()
    db_local = _TMP / "catalog.duckdb"
    try:
        s3.download_file(pub_bucket, "catalog.duckdb", str(db_local))
    except Exception:  # noqa: BLE001 — primera corrida: no existe aún
        pass

    # health ANTES de persistir esta corrida (para que last_seen de una plataforma
    # caída sea la última vez que realmente trajo datos)
    health = platform_health(expected, platforms, db_local)

    json_path = write_matrix_json(matrix, platforms, ref_address, _PUB, generated_at, health)
    csv_path = write_matrix_csv(matrix, platforms, _PUB)

    n_hist = persist_history(offers, db_local, generated_at)
    history_path = build_history_json(db_local, _PUB)
    history_detail_path = build_history_detail_json(db_local, _PUB)
    if db_local.exists():
        s3.upload_file(str(db_local), pub_bucket, "catalog.duckdb")

    # publicar artefactos que sirve el dashboard
    artifacts = [(json_path, "application/json"), (csv_path, "text/csv")]
    for extra in (history_path, history_detail_path):
        if extra:
            artifacts.append((extra, "application/json"))
    for path, ct in artifacts:
        s3.upload_file(
            str(path),
            pub_bucket,
            f"published/{path.name}",
            ExtraArgs={"ContentType": ct},
        )

    comparables = sum(1 for r in matrix if r["n_platforms"] > 1)
    review = sum(1 for r in matrix if r.get("review_needed"))
    return {
        "run_id": run_id,
        "platforms": platforms,
        "faltantes": sorted(set(expected) - set(platforms)),
        "offers": len(offers),
        "canonicos": len(canonicals),
        "comparables": comparables,
        "en_revision": review,
        "history_rows": n_hist,
    }
