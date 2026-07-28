# infra — Terraform

Infra serverless en AWS (us-east-1). State **local** por ahora (deploy manual);
se migra a backend S3+DynamoDB al sumar GitHub Actions.

## Requisitos
- Terraform >= 1.5
- Sesión SSO activa con el profile `production` (`aws sso login --profile production`)

## Uso

El backend es **parcial**: el nombre del bucket de state no vive en el repo
(es público y el bucket lleva el account id). Creá `infra/backend.hcl`
(gitignoreado) con `bucket = "<tu-bucket-de-state>"` y `infra/terraform.tfvars`
con `alert_email = "<tu-email>"`.

```bash
cd infra
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

En CI esos valores vienen de los secrets `TFSTATE_BUCKET`, `AWS_ROLE_ARN` y
`ALERT_EMAIL`.

## Estado actual (base)
- `s3.tf` — buckets `raw` (crudos, expiran 90d) y `published` (matriz/exports/duckdb, versionado)
- `dynamodb.tf` — tabla `jobs` (corridas + lock del refresh)

## Pendiente (próximo)
- Lambdas (scrapers + reducer) vía `terraform-aws-modules/lambda` (build en Docker
  por las deps nativas: curl_cffi, duckdb, rapidfuzz; arm64/py3.13)
- Step Functions (Map fan-out) + EventBridge Scheduler (cron 2h)
- API Gateway (HTTP) + CloudFront + SPA
- Backend S3 de state + OIDC role para GitHub Actions
