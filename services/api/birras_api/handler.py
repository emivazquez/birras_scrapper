"""API HTTP del dashboard (detrás de API Gateway HTTP + CloudFront /api/*).

Rutas:
  POST /api/refresh -> dispara la corrida (StartExecution). Si ya hay una en
                       curso, la devuelve sin arrancar otra (el lock igual la
                       frenaría, pero evitamos la ejecución de más).
  GET  /api/status  -> estado de la última corrida (para el polling del botón).

El input del pipeline (lista de tiendas activas) viene del env BIRRAS_PIPELINE_INPUT,
inyectado por Terraform (mismo que usa el scheduler).
"""

from __future__ import annotations

import json
import os

import boto3

_sfn = boto3.client("stepfunctions")
_SM = os.environ["BIRRAS_STATE_MACHINE_ARN"]
_INPUT = os.environ.get("BIRRAS_PIPELINE_INPUT", "{}")
# El endpoint es público (el dashboard no tiene login). Sin esto, cualquiera
# podría encadenar refreshes y hacer que scrapeemos las tiendas sin parar.
_COOLDOWN_S = int(os.environ.get("BIRRAS_REFRESH_COOLDOWN_S", "600"))


def _resp(code: int, body: dict) -> dict:
    return {
        "statusCode": code,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": json.dumps(body, ensure_ascii=False),
    }


def _seconds_since(iso_ts: str) -> float:
    import datetime as dt

    try:
        t = dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    except ValueError:
        return float("inf")
    return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()


def _latest_execution():
    r = _sfn.list_executions(stateMachineArn=_SM, maxResults=1)
    execs = r.get("executions", [])
    if not execs:
        return None
    e = execs[0]
    return {
        "run_id": e["name"],
        "status": e["status"],
        "started_at": e["startDate"].isoformat(),
    }


def handler(event: dict, context=None) -> dict:
    http = (event.get("requestContext") or {}).get("http") or {}
    method = http.get("method", "GET")
    path = event.get("rawPath", "")

    if method == "POST" and path.endswith("/refresh"):
        latest = _latest_execution()
        if latest and latest["status"] == "RUNNING":
            return _resp(200, {"started": False, "reason": "running", **latest})
        # cooldown: si la última corrida arrancó hace poco, no disparar otra
        if latest and _seconds_since(latest["started_at"]) < _COOLDOWN_S:
            espera = int(_COOLDOWN_S - _seconds_since(latest["started_at"]))
            return _resp(
                200,
                {"started": False, "reason": "cooldown", "retry_after_s": espera, **latest},
            )
        r = _sfn.start_execution(stateMachineArn=_SM, input=_INPUT)
        return _resp(202, {
            "started": True,
            "run_id": r["executionArn"].rsplit(":", 1)[-1],
            "status": "RUNNING",
        })

    if method == "GET" and path.endswith("/status"):
        return _resp(200, _latest_execution() or {"status": "NONE"})

    return _resp(404, {"error": "not found", "path": path})
