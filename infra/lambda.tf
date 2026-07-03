# --- Lambda de scrapers (un invoke por tienda; deps: curl_cffi) ---
module "scrapers_lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.0"

  function_name = "${var.project}-scrapers"
  description   = "Scrapea una tienda y escribe el raw en S3"
  handler       = "birras_scrapers.handler.handler"
  runtime       = var.python_runtime
  architectures = [var.lambda_architecture]
  timeout       = 120
  memory_size   = 512

  source_path = [{
    path             = "${path.module}/../services/scrapers"
    pip_requirements = true
  }]
  build_in_docker = true

  environment_variables = {
    BIRRAS_RAW_BUCKET = aws_s3_bucket.raw.bucket
  }

  attach_policy_statements = true
  policy_statements = {
    s3_put = {
      effect    = "Allow"
      actions   = ["s3:PutObject"]
      resources = ["${aws_s3_bucket.raw.arn}/*"]
    }
  }

  cloudwatch_logs_retention_in_days = 14
}

# --- Lambda del reducer (matching + matriz; deps: duckdb, rapidfuzz) ---
module "reducer_lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.0"

  function_name = "${var.project}-reducer"
  description   = "Resuelve identidad y publica la matriz comparativa"
  handler       = "birras_reducer.handler.handler"
  runtime       = var.python_runtime
  architectures = [var.lambda_architecture]
  timeout       = 120
  memory_size   = 1024

  source_path = [{
    path             = "${path.module}/../services/reducer"
    pip_requirements = true
  }]
  build_in_docker = true

  environment_variables = {
    BIRRAS_RAW_BUCKET       = aws_s3_bucket.raw.bucket
    BIRRAS_PUBLISHED_BUCKET = aws_s3_bucket.published.bucket
  }

  attach_policy_statements = true
  policy_statements = {
    s3_raw = {
      effect    = "Allow"
      actions   = ["s3:GetObject", "s3:ListBucket"]
      resources = [aws_s3_bucket.raw.arn, "${aws_s3_bucket.raw.arn}/*"]
    }
    s3_pub = {
      effect    = "Allow"
      actions   = ["s3:GetObject", "s3:PutObject"]
      resources = ["${aws_s3_bucket.published.arn}/*"]
    }
  }

  cloudwatch_logs_retention_in_days = 14
}
