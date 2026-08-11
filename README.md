# birras_scrapper

Dashboard de comparación de precios de cerveza en CABA (Austria 2001), scrapeando
múltiples ecommerces (PedidosYa, Rappi, y supermercados online de Capital).

Ver el diseño completo en [PLAN.md](PLAN.md).

## Estructura

```
services/
  scrapers/        # Lambda de scraping: adapters por ecommerce (deps livianas: requests)
    birras_scrapers/
      adapters/    # un adapter por plataforma, interfaz común
      schema.py    # schema unificado de producto
      run_local.py # correr scrapers localmente
      handler.py   # entrypoint Lambda
infra/             # Terraform (más adelante)
web/               # SPA del dashboard (más adelante)
```

## Correr los scrapers localmente

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r services/scrapers/requirements.txt
python -m birras_scrapers.run_local --all          # corre todos los adapters
python -m birras_scrapers.run_local pedidosya      # uno solo
```
(desde `services/scrapers/`, o con `PYTHONPATH=services/scrapers`)

Los resultados crudos se escriben en `data/raw/{plataforma}/{timestamp}.json`.

## Scraper local (PedidosYa)

Cloudflare bloquea las IPs de datacenter de AWS para PedidosYa (403), pero desde
una IP residencial argentina funciona. Por eso ese adapter corre en la Mac y sube
el raw a S3; el reducer en la nube lo incorpora si es reciente
(`BIRRAS_RAW_MAX_AGE_H`, default 6h) y lo marca como `stale` en el dashboard.

```bash
cp scripts/local.env.example scripts/local.env   # completar BIRRAS_RAW_BUCKET
scripts/install_local_scraper.sh
```

Instala una copia autocontenida en `~/Library/Application Support/birras-scraper`
(fuera de `~/Documents`, que macOS/TCC le bloquea a `launchd`) + un agente que
corre cada 2 h. Log en `~/Library/Application Support/birras-scraper/scraper.log`.
Volvé a correrlo después de tocar el código de los adapters. Para sacarlo:
`scripts/install_local_scraper.sh --uninstall`.

Sube con el perfil `birras-scraper` (usuario IAM `birras-local-scraper`, ver
`infra/iam-local-scraper.tf`): credencial de larga duración para no depender de
la sesión SSO, acotada a `s3:PutObject` sobre `raw/pedidosya/*` y nada más.

La access key **no** la crea Terraform (iría al state). Se genera una vez con:

```bash
aws iam create-access-key --user-name birras-local-scraper
```

y se guarda como perfil `[birras-scraper]` en `~/.aws/credentials` (chmod 600).
Para rotarla: crear una nueva, actualizar el archivo y borrar la vieja con
`aws iam delete-access-key`.

## Deploy

Automático: cada push a `main` dispara [.github/workflows/deploy.yml](.github/workflows/deploy.yml),
que corre `terraform apply` (infra + Lambdas) + build/sync de la SPA, autenticando
por OIDC (sin llaves). State de Terraform en S3.

Manual (local, con sesión SSO `production`):
```bash
cd infra && terraform apply
```

## Estado

**En producción, 7 ecommerces** (PedidosYa, Rappi, Carrefour, Jumbo, Disco, Vea, Día),
scraping automático cada 2h, matriz comparativa con historial, refresh on-demand y
export CSV/JSON. Ver el roadmap por fases en [PLAN.md](PLAN.md#11-roadmap-por-fases).
