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
