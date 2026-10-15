# Production infrastructure: VPC (3 AZ), EKS cluster, ElastiCache Redis,
# RDS Postgres, and the secret store.
#
# The full module graph is intentionally thin here - this is the reference
# wiring. Each block maps to a decision recorded in docs/architecture/adr/.

# ── Networking: 3 AZs, public/private split ─────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project_name}-vpc" }
}

resource "aws_subnet" "private" {
  count             = var.az_count
  vpc_id            = aws_vpc.main.id
  availability_zone = data.aws_availability_zones.available.names[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 4, count.index)

  tags = {
    Name                                     = "${var.project_name}-private-${count.index}"
    "kubernetes.io/role/internal-elb"        = "1"
    "kubernetes.io/role/elb"                 = "1"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ── EKS: the serving plane (HPA-driven, spot-friendly) ──────────────────────

resource "aws_eks_cluster" "main" {
  name     = "${var.project_name}-${var.environment}"
  role_arn = aws_iam_role.eks_cluster.arn
  version  = "1.30"

  vpc_config {
    subnet_ids              = aws_subnet.private[*].id
    endpoint_public_access  = true
    endpoint_private_access = true
  }

  # Control-plane logs: security audits + API throttling forensics
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
}

resource "aws_iam_role" "eks_cluster" {
  name = "${var.project_name}-eks-cluster"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_node_group" "serving" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "serving"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = aws_subnet.private[*].id

  scaling_config {
    min_size     = var.eks_node_min
    max_size     = var.eks_node_max
    desired_size = var.eks_node_min
  }

  instance_types = var.eks_node_instance_types

  # Rolling node replacement without capacity gaps
  update_config {
    max_unavailable_percentage = 25
  }

  labels = {
    workload = "serving"
  }
}

resource "aws_iam_role" "eks_node" {
  name = "${var.project_name}-eks-node"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

# ── Redis (ElastiCache): conversation memory + rate limits + cache ──────────

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.project_name}-redis"
  description                = "Chatbot conversation memory and rate limiting"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = var.redis_node_type
  num_cache_clusters         = 2          # primary + replica, multi-AZ
  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  # Snapshot daily 03:00 UTC, retain 7 days - conversation history is
  # rebuildable but snapshots make incident recovery minutes not hours.
  snapshot_window    = "03:00-05:00"
  snapshot_retention_limit = 7

  subnet_group_name = aws_elasticache_subnet_group.redis.name
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project_name}-redis-subnets"
  subnet_ids = aws_subnet.private[*].id
}

# ── Postgres (RDS): the durable feedback/evaluation store ───────────────────

resource "aws_db_instance" "postgres" {
  identifier     = "${var.project_name}-postgres"
  engine         = "postgres"
  engine_version = "16.3"
  instance_class = var.db_instance_class

  allocated_storage     = var.db_allocated_storage
  max_allocated_storage = var.db_allocated_storage * 4  # storage autoscaling
  storage_encrypted     = true

  db_name  = "chatbot_db"
  username = "chatbot"
  password = random_password.db_password.result

  multi_az                        = true     # synchronous standby, other AZ
  backup_retention_period         = 30      # PITR window
  backup_window                   = "01:00-03:00"
  deletion_protection             = var.deletion_protection
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]
  performance_insights_enabled    = true

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.db.id]

  skip_final_snapshot = false
  final_snapshot_identifier = "${var.project_name}-postgres-final"
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "postgres" {
  name       = "${var.project_name}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_security_group" "db" {
  name   = "${var.project_name}-db"
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]   # VPC-only; no public DB, ever
  }
}

# ── Secrets: LLM API keys live in Secrets Manager, not env files ────────────

resource "aws_secretsmanager_secret" "llm_keys" {
  name                    = "${var.project_name}/llm-providers"
  description             = "Provider API keys for the chatbot serving tier"
  recovery_window_in_days = 30
}
