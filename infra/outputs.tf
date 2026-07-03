output "raw_bucket" {
  description = "Bucket de snapshots crudos"
  value       = aws_s3_bucket.raw.bucket
}

output "published_bucket" {
  description = "Bucket publicado (matriz + exports + duckdb)"
  value       = aws_s3_bucket.published.bucket
}

output "jobs_table" {
  description = "Tabla DynamoDB de corridas + lock"
  value       = aws_dynamodb_table.jobs.name
}

output "account_id" {
  value = local.account_id
}

output "state_machine_arn" {
  description = "Máquina de estados del pipeline"
  value       = aws_sfn_state_machine.pipeline.arn
}

output "scrapers_lambda" {
  value = module.scrapers_lambda.lambda_function_name
}

output "reducer_lambda" {
  value = module.reducer_lambda.lambda_function_name
}
