# Tabla de corridas + lock anti-concurrencia del refresh.
# - Item de corrida:  PK = "RUN#<run_id>"   -> estado, stats, timestamps
# - Item de lock:     PK = "LOCK#refresh"    -> lo toma el starter con PutItem
#                     condicional (attribute_not_exists) + TTL; libera el reducer.
resource "aws_dynamodb_table" "jobs" {
  name         = "${var.project}-jobs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"

  attribute {
    name = "pk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  point_in_time_recovery {
    enabled = true
  }
}
