variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

# Clerk validation happens in Lambda, not at API Gateway level
variable "clerk_jwks_url" {
  description = "Clerk JWKS URL for JWT validation in Lambda"
  type        = string
}

variable "clerk_issuer" {
  description = "Clerk issuer URL (kept for Lambda environment)"
  type        = string
  default     = ""  # Not actually used but kept for backwards compatibility
}


# Development mode execution
variable "dev_mode" {
  description = "Ability to override to Development user and bypass Clerk credential check"
  type        = bool
  default     = false
}

variable "dev_user_id" {
  description = "Development user ID"
  type        = string
  default     = "test_user_001" 
}