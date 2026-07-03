provider "aws" {
  region = var.region
  # Local usa el profile SSO; en CI (OIDC) va vacío -> cadena de credenciales por env.
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Project   = var.project
      Env       = var.env
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}
