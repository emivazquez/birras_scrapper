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

resource "aws_scheduler_schedule" "refresh_2h" {
  name = "${var.project}-refresh-2h"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "rate(2 hours)"
  schedule_expression_timezone = "America/Argentina/Buenos_Aires"

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode(local.pipeline_input)
  }
}
