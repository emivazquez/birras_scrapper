"""Runner local del reducer.

Uso (desde services/reducer/, con el venv):
    python -m birras_reducer.run_local
    python -m birras_reducer.run_local --raw ../../data/raw --out ../../data/published

Lee el último snapshot por plataforma, resuelve identidad, y escribe la matriz
comparativa (JSON + CSV) + historial en DuckDB. Muestra un resumen y ejemplos
de cervezas matcheadas entre plataformas.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .reduce import reduce

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]  # repo root


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Reducer local: matriz comparativa de precios")
    ap.add_argument("--raw", type=Path, default=_ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=_ROOT / "data" / "published")
    ap.add_argument("--db", type=Path, default=_ROOT / "data" / "catalog.duckdb")
    ap.add_argument("--examples", type=int, default=8, help="cuántas cervezas comparadas mostrar")
    args = ap.parse_args(argv)

    r = reduce(args.raw, args.out, db_path=args.db)

    print(
        f"[+] {r['offers']} ofertas ({'+'.join(r['platforms'])}) "
        f"-> {r['canonicos']} cervezas canónicas, {r['comparables']} comparables (>=2 plataformas)"
    )
    print(f"    JSON: {r['json']}")
    print(f"    CSV : {r['csv']}")
    if r["history_rows"]:
        print(f"    historial: +{r['history_rows']} filas en DuckDB")

    comparables = [row for row in r["matrix"] if row["n_platforms"] > 1]
    confiables = [row for row in comparables if not row["review_needed"]]
    tentativos = [row for row in comparables if row["review_needed"]]
    print(
        f"    matches cross-plataforma: {len(confiables)} confiables (gtin/estructural)"
        f" + {len(tentativos)} tentativos (fuzzy → revisión)"
    )

    print(f"\n=== Cervezas comparadas confiables ({len(confiables)}) ===")
    for row in confiables[: args.examples]:
        precios = " | ".join(
            f"{p}: ${c['precio_actual']}" + ("" if c["disponible"] else " (s/stock)")
            for p, c in row["precios"].items()
        )
        best = f"  -> mejor: {row['mejor']} (ahorrás ${row['ahorro_abs']})" if row["mejor"] else ""
        print(f"  {row['display_name'][:40]:40s} [{row['match_method']}]  {precios}{best}")

    if tentativos:
        print(f"\n=== Tentativos (fuzzy) — irían a la cola de revisión ({len(tentativos)}) ===")
        for row in tentativos:
            names = " vs ".join(f"{p}:{c['nombre'][:30]}" for p, c in row["precios"].items())
            print(f"  ? {row['display_name'][:34]:34s} | {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
