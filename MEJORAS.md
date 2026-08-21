# Mejoras pendientes

Backlog derivado de las notas del 5-ago-2026, **con verificación contra los datos
reales** (11-ago). Cada punto dice si se confirmó, qué se midió y qué implica.

Orden: primero lo que hace que el dashboard muestre datos incorrectos o
incompletos; después las features.

---

## A. Bugs de datos (confirmados)

### A1. Cencosud no trae ningún descuento — Jumbo, Disco y Vea 🔴
**Confirmado y es el más grave: 1.500 productos (3 de 8 tiendas) sin promociones.**

| Tienda | Productos | Desc. directo | Promo multi | Tarjeta |
|---|---|---|---|---|
| carrefour | 467 | 21 | 81 | 121 |
| **jumbo** | 500 | **0** | **0** | **0** |
| **disco** | 500 | **0** | **0** | **0** |
| **vea** | 500 | **0** | **0** | **0** |
| dia | 79 | 44 | 0 | 0 |
| pedidosya | 105 | 69 | 0 | 0 |

La API que usamos (`/api/catalog_system/pub/products/search`) devuelve **0 teasers**
para los tres banners, y su `ListPrice` es basura (ej. `Price=7368` vs
`ListPrice=608926`, por eso lo sanitizamos). La nota menciona que Jumbo los
cataloga como *"Exclusivo Online"* → la promo existe en la web pero llega por
otro mecanismo.

**A investigar:** endpoint de Intelligent Search (`/api/io/_v/api/intelligent-search/...`),
`sc`/`regionId`, o el simulador de checkout (`/api/checkout/pub/orderForms/simulation`),
que es el que aplica promociones de verdad.
**Impacto:** alto — hoy esas 3 tiendas parecen más caras de lo que son.

### A2. Andes Origen de DIA se scrapea pero no matchea 🟠
La nota dice "no trae Andes Origen para DIA". **Se trae, pero no entra en la
comparación** — que es un problema distinto (matching, no scraping).

DIA devuelve `Cerveza Andes Origen IPA Andina Lata 473 Ml.`, pero las 6 filas de
Andes Origen de la matriz muestran `dia ✗`.

**Causa probable:** GTIN distinto al de las otras tiendas + el nombre
("IPA Andina") no cae en la clave estructural.
**Impacto:** medio — hay que revisar cuántos casos así hay en general.

### A3. La marca 1890 pierde su identidad 🟠
Confirmado. PedidosYa devuelve `nombre="Cerveza 1890 Quilmes 473 ml"`,
`marca="1890"`, `tipo="Quilmes"`. Nuestro alias `1890 → quilmes` la absorbe y la
fila queda como **"Quilmes 473ml"**, indistinguible de la regular.

**No están mal fusionadas** (tienen GTIN distinto, así que son filas separadas),
pero **no se puede saber cuál es cuál** mirando el dashboard.
**Fix:** usar `sub_brand` en el `display_name` ("Quilmes 1890 473ml"). El campo
ya existe en el modelo, no se está mostrando.

### A4. El 2x1 de Carrefour no está en la API 🟡
La nota dice "Revisar descuentos 2x1 de Carrefour. Ejemplo Pampa". Verificado en
crudo: para los 7 productos Pampa, Carrefour publica **solo promos de tarjeta**
(`Tarjeta Carrefour 15%`, `Cuenta Digital Carrefour 15% Off Viernes`). Ningún 2x1.

De hecho **en todo el catálogo de Carrefour no detectamos ni un 2x1**: solo
`2do −50%` (67) y `2do −70%` (14).

**A investigar:** si el 2x1 que se ve en la web se aplica en el carrito
(simulación) y no en el catálogo.

### A5. Productos con precio $0 🟡
*(No estaba en la lista — apareció al verificar.)* Ej.:
`Cerveza Pampa Brewing Belcian Lager 473 ml → Price=0.0` en Carrefour.
Un precio 0 no debería publicarse: ensucia el "más barato".
**Fix:** descartar precio ≤ 0 en el adapter VTEX (ya hay un piso similar en Coto).

---

## B. Features

### B1. Mostrar promos (2x1 / 2da al 70%) en la evolución de precio 🟠
Hoy la promo se ve en la matriz pero **no en las vistas por día**: la tabla
`price_observations` guarda `precio_actual`, `descuento_pct`, `precio_por_100ml`
y `stock` — **no la promo**.
**Fix:** agregar la promo al historial y mostrarla como badge en las celdas por día.

### B2. Filtro de fecha / rango en las vistas por día 🟡
Hoy están fijas en las últimas 14 (por tienda) y 21 (por cerveza) corridas.
**Fix:** selector de rango (7 días / 1 mes / todo).

### B3. Buscar en otras tiendas cuando no hay stock 🟡
Si la tienda más barata está sin stock, sugerir la mejor alternativa **con** stock
(hoy la celda dice "sin stock" y el usuario tiene que buscar a ojo).

### B4. Sumar cadenas: Mercado Libre 🟡
Tiendas oficiales **CMQ** y **La Barra**. Sería un `MercadoLibreAdapter` nuevo
(4º tipo de adapter). A evaluar: ML tiene su propia API pública y anti-bot.

---

## Orden sugerido

1. **A1 (Cencosud)** — el de mayor impacto: 3 tiendas mostrando precios sin sus descuentos.
2. **A5 + A3** — baratos y mejoran la calidad visible ya.
3. **B1** — completa la historia de las promos que ya capturamos.
4. **A2** — requiere análisis del matching en general, no solo del caso Andes/DIA.
5. **A4** — depende de descubrir el mecanismo del carrito.
6. **B2, B3, B4** — features nuevas, cuando lo anterior esté sano.
