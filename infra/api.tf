# --- Lambda de la API (refresh + status). Sin deps nativas -> zip simple ---
module "api_lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "~> 7.0"

  function_name = "${var.project}-api"
  description   = "API del dashboard: dispara refresh y reporta estado"
  handler       = "birras_api.handler.handler"
  runtime       = var.python_runtime
  architectures = [var.lambda_architecture]
  timeout       = 30
  memory_size   = 128

  source_path = "${path.module}/../services/api"

  environment_variables = {
    BIRRAS_STATE_MACHINE_ARN = aws_sfn_state_machine.pipeline.arn
    BIRRAS_PIPELINE_INPUT    = jsonencode(local.pipeline_input)
  }

  attach_policy_statements = true
  policy_statements = {
    sfn = {
      effect  = "Allow"
      actions = ["states:StartExecution", "states:ListExecutions", "states:DescribeExecution"]
      resources = [
        aws_sfn_state_machine.pipeline.arn,
        "${replace(aws_sfn_state_machine.pipeline.arn, ":stateMachine:", ":execution:")}:*",
      ]
    }
  }

  cloudwatch_logs_retention_in_days = 14
}

# --- API Gateway HTTP API ---
resource "aws_apigatewayv2_api" "api" {
  name          = "${var.project}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "api" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = module.api_lambda.lambda_function_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "refresh" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /api/refresh"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_route" "status" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /api/status"
  target    = "integrations/${aws_apigatewayv2_integration.api.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "api_gw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = module.api_lambda.lambda_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
