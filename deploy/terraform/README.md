# Terraform Infrastructure

Provisions the production platform. Last reviewed: 2026-10-15.

| File | Responsibility |
|------|----------------|
| `versions.tf` | Provider pins + remote S3/DynamoDB state backend |
| `variables.tf` | Every knob, with production validations (≥3 AZs) |
| `main.tf` | VPC, EKS cluster + node group, ElastiCache, RDS, Secrets Manager |
| `outputs.tf` | Cluster endpoint, store endpoints, secrets ARN for pipelines |

## First Run

```bash
# 1. Create the state backend (once, per account):
#    S3 bucket + DynamoDB lock table - see versions.tf comments

# 2. Configure: copy and edit a tfvars file
cp deploy/terraform/variables.tf deploy/terraform/production.tfvars
# edit: domain_name, eks_node_min/max for your scale phase

# 3. Plan - review EVERY line
terraform -chdir=deploy/terraform init
terraform -chdir=deploy/terraform plan -var-file=production.tfvars -out=tfplan

# 4. Apply
terraform -chdir=deploy/terraform apply tfplan
```

## Guardrails Already Wired

- `deletion_protection` on RDS (destroying prod data needs a deliberate unlock)
- 3-AZ validation refuses single-region-footprint plans
- Multi-AZ RDS + ElastiCache automatic failover
- Everything tagged for cost attribution (Project/Environment/Owner)

## What This Intentionally Does NOT Manage

- Kubernetes manifests (Kustomize owns those - see `../kubernetes/`)
- Secrets *values* (Secrets Manager stores them; terraform creates the container)
- DNS records (owned by the domain's zone management, not the app stack)
