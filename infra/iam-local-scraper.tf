# Usuario para el scraper local (la Mac que scrapea PedidosYa desde una IP
# residencial, porque Cloudflare bloquea el ASN de AWS).
#
# Existe para no depender de la sesión SSO, que vence y deja al agente sin poder
# subir. Es una credencial de larga duración, así que está acotada al mínimo:
# solo puede PONER objetos bajo raw/pedidosya/ en el bucket de raws. No puede
# leer, ni borrar, ni tocar nada más de la cuenta.
#
# La access key NO se crea acá a propósito: iría al state de Terraform. Se crea
# con `aws iam create-access-key` y se guarda en ~/.aws/credentials.
resource "aws_iam_user" "local_scraper" {
  name = "${var.project}-local-scraper"
}

data "aws_iam_policy_document" "local_scraper" {
  statement {
    sid       = "SubirRawsDePedidosya"
    effect    = "Allow"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.raw.arn}/raw/pedidosya/*"]
  }
}

resource "aws_iam_user_policy" "local_scraper" {
  name   = "${var.project}-local-scraper"
  user   = aws_iam_user.local_scraper.name
  policy = data.aws_iam_policy_document.local_scraper.json
}
