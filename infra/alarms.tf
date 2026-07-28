# Alarma de salud de scrapers: si un adapter falla (p.ej. Cloudflare 403 a
# PedidosYa desde la IP de AWS), avisar por email en vez de que la tienda
# desaparezca del dashboard en silencio.

variable "alert_email" {
  description = "Email para alertas de scrapers caídos. Vacío = sin notificación."
  type        = string
  sensitive   = true
  # El repo es público: el valor NO va acá. Viene de infra/terraform.tfvars
  # (gitignoreado) en local, y del secret ALERT_EMAIL de GitHub en CI.
  default = ""
}

resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alert_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# La Lambda de scrapers loguea [ERROR] cuando un adapter falla (el Catch por
# item de Step Functions lo aísla, así que la corrida sigue "SUCCEEDED").
# Este metric filter + alarma es lo que hace visible esa falla.
resource "aws_cloudwatch_log_metric_filter" "scraper_errors" {
  name           = "${var.project}-scraper-errors"
  log_group_name = "/aws/lambda/${module.scrapers_lambda.lambda_function_name}"
  pattern        = "[ERROR]"

  metric_transformation {
    name          = "ScraperErrors"
    namespace     = "Birras"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "scraper_errors" {
  alarm_name          = "${var.project}-scraper-caido"
  alarm_description   = "Un adapter de scraping viene fallando (revisar si una tienda desapareció del dashboard)."
  namespace           = "Birras"
  metric_name         = "ScraperErrors"
  statistic           = "Sum"
  period              = 7200 # una ventana de cron (2h)
  evaluation_periods  = 2    # dos corridas seguidas con errores
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

output "alerts_topic" {
  value = aws_sns_topic.alerts.arn
}
