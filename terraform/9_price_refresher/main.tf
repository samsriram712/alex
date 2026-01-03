terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  required_version = ">= 1.5.0"
}

provider "aws" {
  region = var.aws_region
}

# Data source for current caller identity
data "aws_caller_identity" "current" {}

# --- IAM role for the Lambda ---------------------------------------------

resource "aws_iam_role" "lambda_exec" {
  name               = "alex-price-refresher-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "lambda.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "alex-price-refresher-policy"
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # Aurora Data API
      {
        Effect   = "Allow"
        Action   = ["rds-data:*"]
        Resource = "*"
      },
      # Secrets Manager (for Aurora credentials)
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"],
        Resource = var.database_secret_arn
      },
      # CloudWatch logs
      {
        Effect   = "Allow"
        Action   = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      }
    ]
  })
}

# ========================================
# S3 Bucket for Lambda Deployments
# ========================================

# S3 bucket for Lambda packages (packages > 50MB must use S3)
data "aws_s3_bucket" "lambda_packages" {
  bucket = "alex-lambda-packages-${data.aws_caller_identity.current.account_id}"
}

# Upload Lambda packages to S3
resource "aws_s3_object" "lambda_packages" {
  for_each = toset(["price_refresher"])
  
  bucket = data.aws_s3_bucket.lambda_packages.id
  key    = "${each.key}/${each.key}_lambda.zip"
  source = "${path.module}/../../backend/${each.key}/${each.key}_lambda.zip"
  etag   = fileexists("${path.module}/../../backend/${each.key}/${each.key}_lambda.zip") ? filemd5("${path.module}/../../backend/${each.key}/${each.key}_lambda.zip") : null
  
  tags = {
    Project = "alex"
    Component = each.key
  }
}

# --- Lambda function -----------------------------------------------------

resource "aws_lambda_function" "price_refresher" {
  function_name = "alex-price-refresher"
  handler       = "lambda_handler.lambda_handler"
  runtime       = "python3.12"
  role          = aws_iam_role.lambda_exec.arn
  timeout       = 120

  s3_bucket        = data.aws_s3_bucket.lambda_packages.id
  s3_key           = aws_s3_object.lambda_packages["price_refresher"].key
  source_code_hash = fileexists("${path.module}/../../backend/price_refresher/price_refresher_lambda.zip") ? filebase64sha256("${path.module}/../../backend/price_refresher/price_refresher_lambda.zip") : null


  environment {
    variables = {
      DATABASE_NAME      = "alex"
      VECTOR_BUCKET      = var.vector_bucket
      BEDROCK_MODEL_ID   = var.bedrock_model_id
      BEDROCK_REGION     = var.bedrock_region
      DEFAULT_AWS_REGION = var.aws_region
      SAGEMAKER_ENDPOINT = var.sagemaker_endpoint
      POLYGON_API_KEY    = var.polygon_api_key
      POLYGON_PLAN       = var.polygon_plan
      # LangFuse observability (optional)
      LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
      LANGFUSE_SECRET_KEY = var.langfuse_secret_key
      LANGFUSE_HOST       = var.langfuse_host
      OPENAI_API_KEY      = var.openai_api_key
      AURORA_CLUSTER_ARN = var.database_cluster_arn
      AURORA_SECRET_ARN  = var.database_secret_arn
    }
  }
}

# --- EventBridge daily trigger ------------------------------------------

resource "aws_cloudwatch_event_rule" "daily" {
  name                = "alex-price-refresher-daily"
  description         = "Run once daily to refresh instrument prices"
  schedule_expression = "cron(0 5 * * ? *)" # 5 AM UTC
  state               = var.enable_price_refresher_schedule ? "ENABLED" : "DISABLED"
}

resource "aws_cloudwatch_event_target" "target" {
  rule      = aws_cloudwatch_event_rule.daily.name
  target_id = "price_refresher_lambda"
  arn       = aws_lambda_function.price_refresher.arn
}

resource "aws_lambda_permission" "allow_events" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.price_refresher.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily.arn
}

output "lambda_function_name" {
  value = aws_lambda_function.price_refresher.function_name
}

