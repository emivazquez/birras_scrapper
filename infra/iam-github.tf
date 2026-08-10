# OIDC: GitHub Actions asume este rol sin llaves de larga vida.

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    # Solo el repo y la rama main pueden asumirlo.
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

# Política de deploy con menor privilegio (el repo es público, así que el ARN del
# rol se conoce; la confianza OIDC ya lo acota a main de este repo, pero además
# limitamos qué puede tocar).
#
# Lo clave: IAM está acotado a los roles/políticas `birras-*` y al OIDC provider.
# Sin eso, iam:* sería equivalente a AdministratorAccess (podría auto-escalar).
data "aws_iam_policy_document" "github_deploy" {
  # Servicios donde el scoping por recurso es práctico
  statement {
    sid    = "RecursosDelProyecto"
    effect = "Allow"
    actions = [
      "s3:*", "dynamodb:*", "lambda:*", "states:*",
      "scheduler:*", "sns:*", "sqs:*",
    ]
    resources = [
      "arn:aws:s3:::${var.project}-*",
      "arn:aws:s3:::${var.project}-*/*",
      "arn:aws:dynamodb:*:${local.account_id}:table/${var.project}-*",
      "arn:aws:lambda:*:${local.account_id}:function:${var.project}-*",
      "arn:aws:lambda:*:${local.account_id}:layer:${var.project}-*",
      "arn:aws:states:*:${local.account_id}:stateMachine:${var.project}-*",
      "arn:aws:states:*:${local.account_id}:execution:${var.project}-*:*",
      "arn:aws:scheduler:*:${local.account_id}:schedule/default/${var.project}-*",
      "arn:aws:sns:*:${local.account_id}:${var.project}-*",
    ]
  }

  # IAM: SOLO los roles/políticas del proyecto + el OIDC provider.
  statement {
    sid    = "IamAcotadoAlProyecto"
    effect = "Allow"
    actions = [
      "iam:GetRole", "iam:CreateRole", "iam:DeleteRole", "iam:UpdateRole",
      "iam:TagRole", "iam:UntagRole", "iam:ListRoleTags",
      "iam:PassRole", "iam:ListRolePolicies", "iam:GetRolePolicy",
      "iam:PutRolePolicy", "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy", "iam:DetachRolePolicy",
      "iam:ListAttachedRolePolicies", "iam:ListInstanceProfilesForRole",
      "iam:CreatePolicy", "iam:DeletePolicy", "iam:GetPolicy",
      "iam:GetPolicyVersion", "iam:ListPolicyVersions",
      "iam:CreatePolicyVersion", "iam:DeletePolicyVersion", "iam:ListEntitiesForPolicy",
    ]
    resources = [
      "arn:aws:iam::${local.account_id}:role/${var.project}-*",
      "arn:aws:iam::${local.account_id}:policy/${var.project}-*",
    ]
  }
  statement {
    sid       = "OidcProvider"
    effect    = "Allow"
    actions   = ["iam:GetOpenIDConnectProvider", "iam:CreateOpenIDConnectProvider", "iam:DeleteOpenIDConnectProvider", "iam:UpdateOpenIDConnectProviderThumbprint", "iam:TagOpenIDConnectProvider"]
    resources = ["arn:aws:iam::${local.account_id}:oidc-provider/token.actions.githubusercontent.com"]
  }

  # Servicios donde el scoping por recurso no es práctico (o son globales).
  # Ninguno permite escalar privilegios por sí solo.
  statement {
    sid    = "ServiciosSinScopePractico"
    effect = "Allow"
    actions = [
      "cloudfront:*", # distribución + OAC son globales, sin nombre-ARN útil
      "apigateway:*", # los ARNs son /apis/<id>, no predecibles en el plan
      "logs:*",       # log groups de las Lambdas + metric filters
      "cloudwatch:*", # alarmas
      "sts:GetCallerIdentity",
      "ec2:DescribeRegions",
      # valida una definición suelta (no un recurso), así que exige stateMachine:*
      "states:ValidateStateMachineDefinition",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "github_deploy" {
  name        = "${var.project}-github-deploy"
  description = "Permisos de deploy para GitHub Actions (menor privilegio que AdministratorAccess)"
  policy      = data.aws_iam_policy_document.github_deploy.json
}

resource "aws_iam_role_policy_attachment" "github_deploy" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_deploy.arn
}

output "github_actions_role_arn" {
  description = "Rol a poner en el workflow (role-to-assume)"
  value       = aws_iam_role.github_actions.arn
}
