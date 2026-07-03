# Máquina de estados: lock -> fan-out scrapers (Map) -> reducer -> release lock.
# El lock y el release son integraciones nativas DynamoDB (sin Lambda extra).

resource "aws_iam_role" "sfn" {
  name = "${var.project}-sfn"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sfn" {
  name = "${var.project}-sfn"
  role = aws_iam_role.sfn.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = [module.scrapers_lambda.lambda_function_arn, module.reducer_lambda.lambda_function_arn]
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"]
        Resource = [aws_dynamodb_table.jobs.arn]
      },
    ]
  })
}

resource "aws_sfn_state_machine" "pipeline" {
  name     = "${var.project}-pipeline"
  role_arn = aws_iam_role.sfn.arn

  definition = jsonencode({
    Comment = "birras: lock -> scrape (map) -> reduce -> release"
    StartAt = "AcquireLock"
    States = {
      AcquireLock = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:putItem"
        Parameters = {
          TableName = aws_dynamodb_table.jobs.name
          Item = {
            pk         = { "S" = "LOCK#refresh" }
            run_id     = { "S.$" = "$$.Execution.Name" }
            started_at = { "S.$" = "$$.Execution.StartTime" }
          }
          ConditionExpression = "attribute_not_exists(pk)"
        }
        ResultPath = null
        Catch = [{
          ErrorEquals = ["DynamoDB.ConditionalCheckFailedException"]
          Next        = "AlreadyRunning"
        }]
        Next = "Prepare"
      }

      AlreadyRunning = { Type = "Succeed" }

      Prepare = {
        Type = "Pass"
        Parameters = {
          "run_id.$"            = "$$.Execution.Name"
          "stores.$"            = "$.stores"
          "reference_address.$" = "$.reference_address"
        }
        Next = "ScrapeAll"
      }

      ScrapeAll = {
        Type      = "Map"
        ItemsPath = "$.stores"
        ItemSelector = {
          "store.$"  = "$$.Map.Item.Value"
          "run_id.$" = "$.run_id"
        }
        ToleratedFailurePercentage = 100
        ItemProcessor = {
          ProcessorConfig = { Mode = "INLINE" }
          StartAt         = "ScrapeOne"
          States = {
            ScrapeOne = {
              Type     = "Task"
              Resource = "arn:aws:states:::lambda:invoke"
              Parameters = {
                FunctionName = module.scrapers_lambda.lambda_function_arn
                "Payload.$"  = "$"
              }
              Retry = [{
                ErrorEquals     = ["States.ALL"]
                MaxAttempts     = 1
                IntervalSeconds = 5
              }]
              End = true
            }
          }
        }
        ResultPath = "$.scrape_results"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "ReleaseLockFail"
        }]
        Next = "Reduce"
      }

      Reduce = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = module.reducer_lambda.lambda_function_arn
          Payload = {
            "run_id.$"            = "$.run_id"
            "reference_address.$" = "$.reference_address"
          }
        }
        ResultPath = "$.reduce_result"
        Catch = [{
          ErrorEquals = ["States.ALL"]
          ResultPath  = "$.error"
          Next        = "ReleaseLockFail"
        }]
        Next = "ReleaseLock"
      }

      ReleaseLock = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:deleteItem"
        Parameters = {
          TableName = aws_dynamodb_table.jobs.name
          Key       = { pk = { "S" = "LOCK#refresh" } }
        }
        End = true
      }

      ReleaseLockFail = {
        Type     = "Task"
        Resource = "arn:aws:states:::dynamodb:deleteItem"
        Parameters = {
          TableName = aws_dynamodb_table.jobs.name
          Key       = { pk = { "S" = "LOCK#refresh" } }
        }
        Next = "Failed"
      }

      Failed = {
        Type  = "Fail"
        Error = "PipelineFailed"
      }
    }
  })
}
