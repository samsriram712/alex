terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Using local backend - state will be stored in terraform.tfstate in this directory
  # This is automatically gitignored for security
}

provider "aws" {
  region = var.aws_region
}

# Data source for current caller identity
data "aws_caller_identity" "current" {}

# ========================================
# ECR Repository
# ========================================

# ECR repository for the researcher Docker image
resource "aws_ecr_repository" "researcher" {
  name                 = "alex-researcher"
  image_tag_mutability = "MUTABLE"
  force_delete         = true # Allow deletion even with images

  image_scanning_configuration {
    scan_on_push = false
  }

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# ========================================
# App Runner Service
# ========================================

# IAM role for App Runner
resource "aws_iam_role" "app_runner_role" {
  name = "alex-app-runner-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "build.apprunner.amazonaws.com"
        }
      },
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "tasks.apprunner.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# Policy for App Runner to access ECR
resource "aws_iam_role_policy_attachment" "app_runner_ecr_access" {
  role       = aws_iam_role.app_runner_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# IAM role for App Runner instance (runtime access to AWS services)
resource "aws_iam_role" "app_runner_instance_role" {
  name = "alex-app-runner-instance-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "tasks.apprunner.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# IAM policy granting RDS Data API access
resource "aws_iam_role_policy" "app_runner_rds_data_api" {
  name = "alex-app-runner-rds-data-api"
  role = aws_iam_role.app_runner_instance_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction",
          "rds-data:DescribeStatement"
        ],
        Resource = var.database_cluster_arn
      },
      {
        Effect = "Allow",
        Action = [
          "secretsmanager:GetSecretValue"
        ],
        Resource = var.database_secret_arn
      }
    ]
  })
}


# Policy for App Runner instance to access Bedrock
resource "aws_iam_role_policy" "app_runner_instance_bedrock_access" {
  name = "alex-app-runner-instance-bedrock-policy"
  role = aws_iam_role.app_runner_instance_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:ListFoundationModels"
        ]
        Resource = "*"
      }
    ]
  })
}

# App Runner service
resource "aws_apprunner_service" "researcher" {
  service_name = "alex-researcher"

  source_configuration {
    auto_deployments_enabled = false

    # Configure authentication for private ECR repository
    authentication_configuration {
      access_role_arn = aws_iam_role.app_runner_role.arn
    }

    image_repository {
      image_identifier = "${aws_ecr_repository.researcher.repository_url}:latest"
      image_configuration {
        port = "8000"
        runtime_environment_variables = {
          OPENAI_API_KEY     = var.openai_api_key
          ALEX_API_ENDPOINT  = var.alex_api_endpoint
          ALEX_API_KEY       = var.alex_api_key
          DATABASE_NAME      = "alex"
          AURORA_CLUSTER_ARN = var.database_cluster_arn
          AURORA_SECRET_ARN  = var.database_secret_arn
          DEFAULT_AWS_REGION = var.aws_region
          BRAVE_API_KEY      = var.brave_api_key
        }
      }
      image_repository_type = "ECR"
    }
  }

  instance_configuration {
    cpu               = "1 vCPU"
    memory            = "2 GB"
    instance_role_arn = aws_iam_role.app_runner_instance_role.arn
  }

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# ========================================
# EventBridge Scheduler (Optional)
# ========================================

# IAM role for EventBridge
resource "aws_iam_role" "eventbridge_role" {
  count = var.scheduler_enabled ? 1 : 0
  name  = "alex-eventbridge-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# Lambda function for invoking researcher
resource "aws_lambda_function" "scheduler_lambda" {
  count         = var.scheduler_enabled ? 1 : 0
  function_name = "alex-researcher-scheduler"
  role          = aws_iam_role.lambda_scheduler_role[0].arn

  # Note: The deployment package will be created by the guide instructions
  filename         = "${path.module}/../../backend/scheduler/lambda_function.zip"
  source_code_hash = fileexists("${path.module}/../../backend/scheduler/lambda_function.zip") ? filebase64sha256("${path.module}/../../backend/scheduler/lambda_function.zip") : null

  handler     = "lambda_function.handler"
  runtime     = "python3.12"
  timeout     = 180 # 3 minutes to handle App Runner response time
  memory_size = 256

  environment {
    variables = {
      APP_RUNNER_URL = aws_apprunner_service.researcher.service_url
    }
  }

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# IAM role for scheduler Lambda
resource "aws_iam_role" "lambda_scheduler_role" {
  count = var.scheduler_enabled ? 1 : 0
  name  = "alex-scheduler-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# Lambda basic execution policy
resource "aws_iam_role_policy_attachment" "lambda_scheduler_basic" {
  count      = var.scheduler_enabled ? 1 : 0
  role       = aws_iam_role.lambda_scheduler_role[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# EventBridge schedule
resource "aws_scheduler_schedule" "research_schedule" {
  count = var.scheduler_enabled ? 1 : 0
  name  = "alex-research-schedule"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression = "rate(2 hours)"

  target {
    arn      = aws_lambda_function.scheduler_lambda[0].arn
    role_arn = aws_iam_role.eventbridge_role[0].arn
  }
}

# Permission for EventBridge to invoke Lambda
resource "aws_lambda_permission" "allow_eventbridge" {
  count         = var.scheduler_enabled ? 1 : 0
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scheduler_lambda[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.research_schedule[0].arn
}

# Policy for EventBridge to invoke Lambda
resource "aws_iam_role_policy" "eventbridge_invoke_lambda" {
  count = var.scheduler_enabled ? 1 : 0
  name  = "InvokeLambdaPolicy"
  role  = aws_iam_role.eventbridge_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.scheduler_lambda[0].arn
      }
    ]
  })
}

# ========================================
# SQS Queue for Symbol Research Jobs
# ========================================

resource "aws_sqs_queue" "symbol_research_dlq" {
  name = "alex-symbol-research-dlq"

  message_retention_seconds = 345600 # 4 days

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

resource "aws_sqs_queue" "symbol_research" {
  name                       = "alex-symbol-research"
  delay_seconds              = 0
  max_message_size           = 262144
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 10
  visibility_timeout_seconds = 920  # Worker timeout + buffer

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.symbol_research_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Project = "alex"
    Part    = "4"
  }
}


resource "aws_lambda_function" "symbol_worker" {
  function_name = "alex-symbol-research-worker"
  role          = aws_iam_role.lambda_symbol_worker_role.arn

  # NOTE: lambda_function.zip will be produced by the symbol_research packaging script
  filename         = "${path.module}/../../backend/symbol_research/lambda_function.zip"
  source_code_hash = fileexists("${path.module}/../../backend/symbol_research/lambda_function.zip") ? filebase64sha256("${path.module}/../../backend/symbol_research/lambda_function.zip") : null

  handler     = "worker.handler"
  runtime     = "python3.12"
  timeout     = 900  # allow long-running symbol research
  memory_size = 256

  environment {
    variables = {
      # Same pattern as scheduler Lambda
      APP_RUNNER_URL = aws_apprunner_service.researcher.service_url

      # For Database() / JobTracker
      DATABASE_NAME      = "alex"
      AURORA_CLUSTER_ARN = var.database_cluster_arn
      AURORA_SECRET_ARN  = var.database_secret_arn
      DEFAULT_AWS_REGION = var.aws_region
    }
  }

  tags = {
    Project = "alex"
    Part    = "4"
  }
}

# ========================================
# SQS Trigger for Symbol Research Worker Lambda
# ========================================

resource "aws_lambda_event_source_mapping" "symbol_research_worker_sqs" {
  event_source_arn = aws_sqs_queue.symbol_research.arn
  function_name    = "alex-symbol-research-worker"
  batch_size       = 1
  enabled          = true
}

# ========================================
# IAM Role for Symbol Worker Lambda
# ========================================

resource "aws_iam_role" "lambda_symbol_worker_role" {
  name = "alex-symbol-worker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_symbol_worker_basic" {
  role       = aws_iam_role.lambda_symbol_worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_symbol_worker_policy" {
  name = "alex-symbol-worker-policy"
  role = aws_iam_role.lambda_symbol_worker_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # SQS Receive/Delete permissions
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.symbol_research.arn
      },

      # Database access
      {
        Effect = "Allow"
        Action = [
          "rds-data:ExecuteStatement",
          "rds-data:BatchExecuteStatement",
          "rds-data:BeginTransaction",
          "rds-data:CommitTransaction",
          "rds-data:RollbackTransaction",
          "rds-data:DescribeStatement"
        ]
        Resource = var.database_cluster_arn
      },

      # Secrets Manager for DB credentials
      {
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = var.database_secret_arn
      }
    ]
  })
}


output "symbol_worker_lambda_arn" {
  value = aws_lambda_function.symbol_worker.arn
}

output "symbol_research_queue_arn" {
  value = aws_sqs_queue.symbol_research.arn
}

output "symbol_research_queue_url" {
  value = aws_sqs_queue.symbol_research.url
}

output "symbol_research_dlq_arn" {
  value = aws_sqs_queue.symbol_research_dlq.arn
}
