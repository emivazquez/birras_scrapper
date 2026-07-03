variable "project" {
  description = "Prefijo de nombres y tag Project"
  type        = string
  default     = "birras"
}

variable "region" {
  description = "Región AWS"
  type        = string
  default     = "us-east-1"
}

variable "aws_profile" {
  description = "Profile SSO local (se ignora en CI con OIDC)"
  type        = string
  default     = "production"
}

variable "env" {
  description = "Entorno"
  type        = string
  default     = "prod"
}

variable "lambda_architecture" {
  description = "arm64 (Graviton, más barato) o x86_64"
  type        = string
  default     = "arm64"
}

variable "python_runtime" {
  description = "Runtime Python de Lambda"
  type        = string
  default     = "python3.13"
}

variable "github_repo" {
  description = "owner/repo habilitado para asumir el rol de deploy vía OIDC"
  type        = string
  default     = "emivazquez/birras_scrapper"
}
