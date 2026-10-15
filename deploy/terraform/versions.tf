# Terraform provider version pins.
# Unpinned providers are the #1 source of "works Tuesday, breaks Wednesday"
# infrastructure drift.
terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state: S3 + DynamoDB locking - mandatory for team workflows.
  # Replace ORG/ENV before use; local state is forbidden in production.
  backend "s3" {
    bucket         = "chatbot-tfstate-REPLACE-ME"
    key            = "support-platform/production.tfstate"
    region         = "us-east-1"
    dynamodb_table = "tfstate-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "customer-support-chatbot"
      Environment = var.environment
      ManagedBy   = "terraform"
      Repo        = "Customer-Support-Chatbot-102"
      Owner       = "AdilShamim8"
    }
  }
}
