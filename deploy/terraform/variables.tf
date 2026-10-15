# Input variables - every knob of the production stack, with safe defaults.

variable "aws_region" {
  description = "AWS region for the serving stack"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (staging | production)"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production."
  }
}

variable "project_name" {
  description = "Resource naming prefix"
  type        = string
  default     = "chatbot"
}

variable "vpc_cidr" {
  description = "VPC CIDR - must not collide with the EKS/service CIDRs"
  type        = string
  default     = "10.40.0.0/16"
}

variable "az_count" {
  description = "Number of availability zones - production minimum is 3"
  type        = number
  default     = 3

  validation {
    condition     = var.az_count >= 3
    error_message = "Production requires >= 3 AZs for zonal-failure tolerance."
  }
}

variable "eks_node_min" {
  description = "Minimum worker nodes - floor sized for one-AZ loss at baseline"
  type        = number
  default     = 6
}

variable "eks_node_max" {
  description = "Maximum worker nodes - bounded by quota requests + budget"
  type        = number
  default     = 300
}

variable "eks_node_instance_types" {
  description = "Mixed instance types for spot/on-demand cost optimization"
  type        = list(string)
  default     = ["m6i.2xlarge", "m5.2xlarge", "m6a.2xlarge"]
}

variable "redis_node_type" {
  description = "ElastiCache node class - memory-bound workload"
  type        = string
  default     = "cache.r6g.xlarge"
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.2xlarge"
}

variable "db_allocated_storage" {
  description = "RDS storage in GiB (autoscaling enabled)"
  type        = number
  default     = 200
}

variable "domain_name" {
  description = "Public domain for the API endpoint"
  type        = string
  default     = "api.ragchatbot.example.com"
}

variable "deletion_protection" {
  description = "Guard against destroying the production database"
  type        = bool
  default     = true
}
