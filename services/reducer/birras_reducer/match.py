"""Resolución de identidad: asigna canonical_id a cada oferta.

Cascada (precisión > recall), implementada con union-find:
  0. GTIN/EAN igual  -> misma identidad
  2. Clave estructural igual (marca, variante, volumen, pack)  -> misma identidad
  3. Fuzzy sobre nombre, bloqueado por (marca, volumen, pack) y con variantes
     compatibles (iguales o alguna 'unknown'), umbral token_set_ratio >= 90.

El Nivel 1 (overrides manuales) se enchufa acá cuando exista la tabla; hoy no
hay overrides. Devuelve la lista de productos canónicos.
"""

from __future__ import annotations

from rapidfuzz import fuzz

FUZZY_THRESHOLD = 90.0
# precedencia de plataforma para elegir el representante canónico (nombre limpio + GTIN)
_PLATFORM_PRIORITY = {"pedidosya": 0, "rappi": 1}


class _UnionFind:
    """Union-find que además lleva el GTIN de cada componente.

    El GTIN es la señal más confiable que tenemos (6 de 8 plataformas lo traen
    al 100% y el 100% de los dígitos verificadores valida), así que manda: dos
    componentes con GTIN DISTINTO nunca se unen, por más que la clave
    estructural o el fuzzy digan que sí.

    Sin esta regla, un error de parseo encadena productos distintos en cascada:
    si "Noire Dark Lager" se clasifica como 'rubia', su clave estructural la une
    con la Rubia, y de ahí la transitividad arrastra Pure Gold, Blanche, 0.0 y
    los packs a una sola fila (medido: 109 filas mezcladas, 48% de las ofertas).
    """

    def __init__(self, gtins: list[str]):
        n = len(gtins)
        self.parent = list(range(n))
        # cada componente arranca con el gtin de su oferta (o vacío)
        self.gtin = list(gtins)

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def can_union(self, a: int, b: int) -> bool:
        ga, gb = self.gtin[self.find(a)], self.gtin[self.find(b)]
        return not (ga and gb and ga != gb)

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return True
        if not self.can_union(ra, rb):
            return False
        keep, drop = (ra, rb) if ra < rb else (rb, ra)
        self.parent[drop] = keep
        # el componente conserva el gtin conocido (si alguno lo tenía)
        self.gtin[keep] = self.gtin[keep] or self.gtin[drop]
        return True


def _majority(values):
    """Valor más frecuente de un iterable (None si viene vacío). Determinístico:
    ante empate gana el que ordena primero, para que la clave canónica sea estable."""
    from collections import Counter

    c = Counter(v for v in values if v not in (None, ""))
    if not c:
        return None
    top = max(c.values())
    return sorted(k for k, v in c.items() if v == top)[0]


def _variants_compatible(a: str, b: str) -> bool:
    return a == b or a == "unknown" or b == "unknown"


def _canonical_key(rep: dict, container: str | None) -> str:
    """Clave de identidad ESTABLE entre corridas (para unir historial de precios).

    Determinística a partir de la identidad normalizada, no del índice de corrida.
    """
    # el sub_brand se pega al slug de marca (quilmes -> quilmes-1890) en vez de
    # sumar un campo nuevo: así solo cambian las claves de los productos que
    # tienen sub_brand y no se resetea el historial de todo el catálogo
    marca = rep["brand_slug"] + (f"-{rep['sub_brand']}" if rep.get("sub_brand") else "")
    return "|".join(
        [
            marca,
            rep["variant_slug"],
            str(rep["volume_ml_canon"] or ""),
            container or "",
            str(rep["pack_qty"]),
            "z" if rep.get("is_zero") else "",
        ]
    )


def assign_canonicals(offers: list[dict]) -> list[dict]:
    """Setea offer['canonical_id'] y devuelve la lista de canónicos."""
    n = len(offers)
    uf = _UnionFind([o.get("gtin_norm") or "" for o in offers])

    # Nivel 0 — GTIN
    by_gtin: dict[str, int] = {}
    for i, o in enumerate(offers):
        g = o.get("gtin_norm")
        if g:
            if g in by_gtin:
                uf.union(by_gtin[g], i)
            else:
                by_gtin[g] = i

    # Nivel 2 — clave estructural
    by_key: dict[tuple, int] = {}
    for i, o in enumerate(offers):
        k = o.get("structural_key")
        if k:
            if k in by_key:
                uf.union(by_key[k], i)
            else:
                by_key[k] = i

    # Nivel 3 — fuzzy, bloqueado por (marca, volumen, pack)
    blocks: dict[tuple, list[int]] = {}
    for i, o in enumerate(offers):
        blocks.setdefault((o["brand_slug"], o["volume_ml_canon"], o["pack_qty"]), []).append(i)
    for idxs in blocks.values():
        for a_pos in range(len(idxs)):
            for b_pos in range(a_pos + 1, len(idxs)):
                i, j = idxs[a_pos], idxs[b_pos]
                oi, oj = offers[i], offers[j]
                if oi["platform"] == oj["platform"]:
                    continue  # el fuzzy es para cruzar plataformas
                if uf.find(i) == uf.find(j):
                    continue
                if oi.get("is_zero") != oj.get("is_zero"):
                    continue  # una 0% nunca es la misma cerveza que la regular
                if not _variants_compatible(oi["variant_slug"], oj["variant_slug"]):
                    continue
                score = fuzz.token_set_ratio(oi["nombre_norm"], oj["nombre_norm"])
                if score >= FUZZY_THRESHOLD:
                    uf.union(i, j)

    # Agrupar por componente -> canonical_id
    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(uf.find(i), []).append(i)

    canonicals: list[dict] = []
    for cid, (root, members) in enumerate(sorted(groups.items())):
        member_offers = [offers[m] for m in members]
        rep = _pick_representative(member_offers)
        gtin = next((o["gtin_norm"] for o in member_offers if o["gtin_norm"]), "")
        # El grupo (unido por GTIN) sabe más que cualquier oferta suelta: si una
        # tienda nombra el tipo y otra no, lo tomamos del grupo por mayoría.
        # Ej: Disco dice "Ultra Lager 275 Ml Michelob" (rubia) y Carrefour
        # "Michelob Ultra porrón" (unknown) -> el canónico queda 'rubia'.
        variant = _majority(o["variant_slug"] for o in member_offers if o["variant_slug"] != "unknown")
        container = _majority(o["container"] for o in member_offers if o["container"])
        is_zero = _majority(o.get("is_zero") for o in member_offers)
        sub_brand = _majority(o.get("sub_brand") for o in member_offers) or ""
        rep = {**rep, "variant_slug": variant or "unknown", "is_zero": bool(is_zero),
               "sub_brand": sub_brand}
        ckey = _canonical_key(rep, container)
        for m in members:
            offers[m]["canonical_id"] = cid
            offers[m]["canonical_key"] = ckey
        method, review = _link_method(member_offers)
        canonicals.append(
            {
                "canonical_id": cid,
                "canonical_key": ckey,
                "brand_slug": rep["brand_slug"],
                "brand_display": rep["brand_display"],
                "sub_brand": sub_brand,
                "variant_slug": rep["variant_slug"],
                "volume_ml": rep["volume_ml_canon"],
                "container": container,
                "pack_qty": rep["pack_qty"],
                "gtin": gtin,
                "display_name": _display_name(rep, container),
                "n_platforms": len({o["platform"] for o in member_offers}),
                "match_method": method,
                "review_needed": review,
            }
        )
    return canonicals


def _link_method(member_offers: list[dict]) -> tuple[str, bool]:
    """Cómo se unieron ofertas de DISTINTAS plataformas en este canónico.

    Devuelve (method, review_needed). Un match cross-plataforma es 'confiable'
    si dos plataformas comparten GTIN o clave estructural; si solo se unieron por
    fuzzy, es 'tentativo' y va a revisión (precisión > recall).
    """
    from collections import defaultdict

    platforms = {o["platform"] for o in member_offers}
    if len(platforms) < 2:
        return ("single", False)

    gtin_plats: dict[str, set] = defaultdict(set)
    key_plats: dict[tuple, set] = defaultdict(set)
    for o in member_offers:
        if o["gtin_norm"]:
            gtin_plats[o["gtin_norm"]].add(o["platform"])
        if o["structural_key"]:
            key_plats[o["structural_key"]].add(o["platform"])

    if any(len(v) > 1 for v in gtin_plats.values()):
        return ("gtin", False)
    if any(len(v) > 1 for v in key_plats.values()):
        return ("structural", False)
    return ("fuzzy", True)


def _pick_representative(members: list[dict]) -> dict:
    # preferir con GTIN, luego menor prioridad de plataforma (pedidosya primero)
    return sorted(
        members,
        key=lambda o: (
            0 if o["gtin_norm"] else 1,
            _PLATFORM_PRIORITY.get(o["platform"], 9),
            len(o["nombre"]),
        ),
    )[0]


def _variant_title(slug: str) -> str:
    return "" if slug in ("unknown", "") else slug.replace("-", " ").title()


def _display_name(rep: dict, container: str | None) -> str:
    # "Quilmes 1890 473ml lata" en vez de "Quilmes 473ml lata"
    marca = rep["brand_display"]
    if rep.get("sub_brand"):
        marca = f"{marca} {rep['sub_brand']}"
    parts = [marca]
    vt = _variant_title(rep["variant_slug"])
    if vt:
        parts.append(vt)
    if rep["volume_ml_canon"]:
        parts.append(f"{rep['volume_ml_canon']}ml")
    if container:
        parts.append(container)
    if rep["pack_qty"] > 1:
        parts.append(f"x{rep['pack_qty']}")
    return " ".join(parts)


