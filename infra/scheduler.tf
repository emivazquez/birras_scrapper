# Cron cada 2h -> arranca la máquina de estados con la lista de tiendas activas.
# La misma máquina la disparará el botón Refresh (API) más adelante, con el mismo
# input; el lock en AcquireLock evita corridas solapadas.

locals {
  stores_config = jsondecode(file("${path.module}/../services/scrapers/birras_scrapers/config/stores.json"))
  active_stores = [for s in local.stores_config.stores : s if lookup(s, "active", true)]
  pipeline_input = {
    stores            = local.active_stores
    reference_address = local.stores_config.reference_address
    trigger           = "schedule"
  }
}

resource "aws_iam_role" "scheduler" {
  name = "${var.project}-scheduler"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "${var.project}-scheduler"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["states:StartExecution"]
      Resource = [aws_sfn_state_machine.pipeline.arn]
    }]
  })
}

# NOTA: existió un schedule `birras-pedidosya-retry` que invocaba solo ese
# scraper cada 30 min para pescar alguna ventana en que Cloudflare dejara pasar.
# Se eliminó el 2026-08-10: medido, 25 reintentos seguidos (8 min) fallan 25/25
# y hacía 5 días que no entraba, así que solo quemaba ~US$6/mes de cómputo.
# PedidosYa se intenta ahora únicamente en las 3 corridas diarias, con sus 25
# reintentos internos (BIRRAS_SCRAPE_ATTEMPTS_PEDIDOSYA).
# El fix real es un egress que no sea de datacenter (proxy residencial AR) o
# volver a correr ese adapter desde una máquina con IP residencial.

resource "aws_scheduler_schedule" "refresh_2h" {
  name = "${var.project}-refresh-2h"

  flexible_time_window {
    mode = "OFF"
  }

  # 3 corridas por día, hora de Buenos Aires: 10:00, 14:00 y 20:00.
  schedule_expression          = "cron(0 10,14,20 * * ? *)"
  schedule_expression_timezone = "America/Argentina/Buenos_Aires"

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(local.pipeline_input)
  }
}
