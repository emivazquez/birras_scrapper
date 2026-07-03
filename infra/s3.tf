locals {
  account_id = data.aws_caller_identity.current.account_id
  raw_bucket = "${var.project}-raw-${local.account_id}"
  pub_bucket = "${var.project}-published-${local.account_id}"
}

# --- Bucket de snapshots crudos por scraper (append-only, fuente de verdad) ---
resource "aws_s3_bucket" "raw" {
  bucket = local.raw_bucket
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Historial infinito no hace falta en crudo: expira a los 90 días (el precio ya
# quedó en DuckDB). Ajustable.
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "expire-raw"
    status = "Enabled"
    filter {
      prefix = "raw/"
    }
    expiration {
      days = 90
    }
  }
}

# --- Bucket publicado: matriz + exports + catalog.duckdb (lo lee el dashboard vía CloudFront) ---
resource "aws_s3_bucket" "published" {
  bucket = local.pub_bucket
}

resource "aws_s3_bucket_public_access_block" "published" {
  bucket                  = aws_s3_bucket.published.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "published" {
  bucket = aws_s3_bucket.published.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "published" {
  bucket = aws_s3_bucket.published.id
  versioning_configuration {
    status = "Enabled"
  }
}
