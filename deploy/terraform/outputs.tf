# Outputs - everything a deploy runbook or CI pipeline needs to consume.

output "cluster_name" {
  description = "EKS cluster name for kubectl/CI kubeconfig"
  value       = aws_eks_cluster.main.name
}

output "cluster_endpoint" {
  description = "Kubernetes API server endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache primary endpoint for REDIS_URL"
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "postgres_endpoint" {
  description = "RDS endpoint for DATABASE_URL"
  value       = aws_db_instance.postgres.address
}

output "database_url" {
  description = "Full asyncpg connection string (handle as a secret)"
  value       = "postgresql+asyncpg://chatbot:${random_password.db_password.result}@${aws_db_instance.postgres.address}:5432/chatbot_db"
  sensitive   = true
}

output "llm_secrets_arn" {
  description = "Secrets Manager ARN for provider API keys"
  value       = aws_secretsmanager_secret.llm_keys.arn
}
