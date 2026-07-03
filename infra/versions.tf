terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.40, < 7.0"
    }
  }

  # State local por ahora (deploy manual). Al sumar GitHub Actions se migra a:
  # backend "s3" {
  #   bucket         = "birras-tfstate-<account_id>"
  #   key            = "infra/terraform.tfstate"
  #   region         = "us-east-1"
  #   dynamodb_table = "birras-tflock"
  #   encrypt        = true
  # }
}
