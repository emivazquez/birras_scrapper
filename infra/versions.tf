terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40, < 7.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0"
    }
  }

  # State remoto en S3 con lock nativo (use_lockfile, sin DynamoDB).
  #
  # Backend PARCIAL: el nombre del bucket no va en el repo (es público y el
  # bucket lleva el account id). Se pasa en el init:
  #   local: terraform init -backend-config=backend.hcl   (backend.hcl gitignoreado)
  #   CI:    terraform init -backend-config="bucket=$TFSTATE_BUCKET"  (secret)
  backend "s3" {
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
