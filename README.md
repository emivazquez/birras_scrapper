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

## Estado

Fase 0 — cimientos. Ver el roadmap por fases en [PLAN.md](PLAN.md#11-roadmap-por-fases).
