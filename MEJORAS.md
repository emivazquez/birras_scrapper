# Mejoras pendientes

Backlog derivado de las notas del 5-ago-2026, **con verificación contra los datos
reales** (11-ago). Cada punto dice si se confirmó, qué se midió y qué implica.

Orden: primero lo que hace que el dashboard muestre datos incorrectos o
incompletos; después las features.

---

## A. Bugs de datos (confirmados)

### A1. Cencosud no trae ningún descuento — Jumbo, Disco y Vea 🔴
**Confirmado, y es peor de lo anotado: no es que "falten descuentos", es que
publicamos el precio SIN descuento, o sea más caro que el real.**

Caso probado (11-ago, Disco, `Cerveza Rubia 330ml Corona`, sku 22487):

| Fuente | Precio |
|---|---|
| Lo que **muestra el sitio** | **$3.411** (−25%) |
| Lo que devuelve la API de catálogo (y publicamos) | **$4.548** |

O sea: mostramos Disco un 25% más caro en los productos en oferta.

| Tienda | Productos | Desc. directo | Promo multi | Tarjeta |
|---|---|---|---|---|
| carrefour | 467 | 21 | 81 | 121 |
| **jumbo / disco / vea** | **1.500** | **0** | **0** | **0** |
| dia | 79 | 44 | 0 | 0 |
| pedidosya | 105 | 69 | 0 | 0 |

**Lo investigado (11-ago):**
- `commertialOffer` trae `Price` = precio REGULAR, `PriceWithoutDiscount` = igual
  a Price, `teasers: []` y `discountHighlights: []`. El `ListPrice` es basura
  (factor constante ~82x respecto de Price) — por eso lo sanitizamos.
- **Encontrado el endpoint de promociones de Cencosud**:
  `POST /_v/search-promotions` con body `{"seller":"1","skus":["<skuId>"]}`.
  Responde promos reales con los campos que necesitamos:
  `code` ("3x2"), `categoryType` ("nxm"), `effectiveDiscount` ("0.33"),
  `name`, `start`, `end`, agrupadas en buckets (`generic`, `jumbo_prime`, `sgc`).
- **Pero** para los SKUs de cerveza probados (50 vía API + 20 desde el navegador
  con sesión completa) devuelve vacío, incluida la Corona que en pantalla tiene
  −25%. El valor 3.411 no aparece ni en `__STATE__` ni en el catálogo.
- `POST /api/checkout/pub/orderForms/simulation` responde
  *"Ítem no encontrado o no disponible"*: exige región/sucursal en la sesión.

**Próximo paso:** setear dirección/sucursal (el flujo que hace la web) para
obtener el `vtex_segment` con `regionId`, y reintentar catálogo + simulación con
esa sesión. Es probable que el precio con descuento aparezca recién ahí.
**Impacto:** alto — 3 de 8 tiendas con precios inflados en los productos en oferta.

### A2. Andes Origen de DIA se scrapea pero no matchea 🟠
La nota dice "no trae Andes Origen para DIA". **Se trae, pero no entra en la
comparación** — que es un problema distinto (matching, no scraping).

DIA devuelve `Cerveza Andes Origen IPA Andina Lata 473 Ml.`, pero las 6 filas de
Andes Origen de la matriz muestran `dia ✗`.

**Causa probable:** GTIN distinto al de las otras tiendas + el nombre
("IPA Andina") no cae en la clave estructural.
**Impacto:** medio — hay que revisar cuántos casos así hay en general.

### A3. La marca 1890 pierde su identidad ✅ HECHO (11-ago)
Confirmado. PedidosYa devuelve `nombre="Cerveza 1890 Quilmes 473 ml"`,
`marca="1890"`, `tipo="Quilmes"`. Nuestro alias `1890 → quilmes` la absorbe y la
fila queda como **"Quilmes 473ml"**, indistinguible de la regular.

**No están mal fusionadas** (tienen GTIN distinto, así que son filas separadas),
pero **no se puede saber cuál es cuál** mirando el dashboard.
**Resuelto:** se agregó la columna `sub_brand` a `brand_aliases.csv` y se resuelve
por mayoría dentro del grupo. Ahora la fila dice **"Quilmes 1890 Rubia 473ml lata"**.
El sub_brand se pega al slug de marca (`quilmes-1890`) en vez de sumar un campo
nuevo a la clave canónica, así **solo cambian las claves de 1890** y no se
resetea el historial de todo el catálogo.

### A4. El 2x1 de Carrefour no está en la API 🟡
La nota dice "Revisar descuentos 2x1 de Carrefour. Ejemplo Pampa". Verificado en
crudo: para los 7 productos Pampa, Carrefour publica **solo promos de tarjeta**
(`Tarjeta Carrefour 15%`, `Cuenta Digital Carrefour 15% Off Viernes`). Ningún 2x1.

De hecho **en todo el catálogo de Carrefour no detectamos ni un 2x1**: solo
`2do −50%` (67) y `2do −70%` (14).

**A investigar:** si el 2x1 que se ve en la web se aplica en el carrito
(simulación) y no en el catálogo.

### A5. Productos con precio $0 ✅ HECHO (11-ago)
*(No estaba en la lista — apareció al verificar.)* Ej.:
`Cerveza Pampa Brewing Belcian Lager 473 ml → Price=0.0` en Carrefour.
Un precio 0 no debería publicarse: ensucia el "más barato".
**Resuelto, pero NO como parecía.** Al medirlo: **155 de los 467 productos de
Carrefour (33%) tienen `Price=0`… y todos con `stock=0`**. No son un bug de
precio: son productos que la tienda no está vendiendo, y ya se mostraban como
"sin stock". Descartarlos (primer intento) borraba información útil —saber que
Carrefour lo tiene en catálogo—, que además hace falta para B3.
**Fix aplicado:** se conserva el producto y en el reducer un precio ≤ 0 nunca
cuenta como disponible, así jamás compite por el "más barato".

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
