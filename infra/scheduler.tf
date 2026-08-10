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

# --- Reintento dedicado de PedidosYa ---------------------------------------
# Cloudflare bloquea las IPs de AWS de forma intermitente: medido, PedidosYa
# entra ~7% de las veces (31% a las 22h UTC). En vez de correr todo el pipeline
# más seguido, reintentamos SOLO este scraper cada 30 min: son centavos de
# Lambda y multiplica las chances de tener un raw fresco. El reducer levanta el
# más reciente que esté dentro de BIRRAS_RAW_MAX_AGE_H.
locals {
  pedidosya_store = [for s in local.active_stores : s if s.platform == "pedidosya"]
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  count = length(local.pedidosya_store) > 0 ? 1 : 0
  name  = "${var.project}-scheduler-lambda"
  role  = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = [module.scrapers_lambda.lambda_function_arn]
    }]
  })
}

resource "aws_scheduler_schedule" "pedidosya_retry" {
  count = length(local.pedidosya_store) > 0 ? 1 : 0
  name  = "${var.project}-pedidosya-retry"

  flexible_time_window {
    mode = "OFF"
  }
  schedule_expression          = "rate(30 minutes)"
  schedule_expression_timezone = "America/Argentina/Buenos_Aires"

  target {
    arn      = module.scrapers_lambda.lambda_function_arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ store = local.pedidosya_store[0] })

    retry_policy {
      maximum_retry_attempts = 0 # la Lambda ya reintenta internamente
    }
  }
}

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
