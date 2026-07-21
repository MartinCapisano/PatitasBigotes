# Plan de refactor — Organización de servicios por vista

> Documento de trabajo. Se consulta y se actualiza durante toda la implementación.
> La decisión y su justificación viven en [ADR 0001](adr/0001-organizacion-de-servicios-por-vista.md).
> **Estado: commits 0-3 hechos. Kernel de pago extraido.**

---

## Regla que gobierna todo el refactor

**Puro movimiento de código.** Ningún bug se arregla, ninguna simplificación se aplica, ningún nombre se
mejora durante los commits 0–4, salvo los renombres listados explícitamente en este documento.

Lo que se encuentre en el camino se anota en [Hallazgos](#hallazgos-para-después) y se atiende en commits
posteriores al refactor. Esta disciplina no es estética: es la condición que hace verificable la garantía
de "no se perdió ninguna función".

---

## Resultado esperado

| Dominio | Archivo | Líneas aprox. | Contenido |
|---|---|---|---|
| infra | `source/db/session.py` | +18 | `read_session_scope`, `write_session_scope` |
| products | `services/products_s.py` | ~550 | CRUD producto/variante/categoría, stock, queries admin |
| products | `services/products_storefront_s.py` | ~400 | Vitrina pública, precios con descuento, opciones |
| orders | `services/orders_s.py` | ~770 | Draft, checkout, admin, transiciones de estado |
| orders | `services/orders_public_s.py` | ~180 | Snapshot público por token de pago |
| payments | `services/payment_s.py` | ~600 | Creación, reintentos, confirmación manual, consultas |
| payments | `services/payment_core_s.py` | ~250 | Kernel: serialización, transiciones, idempotencia |
| payments | `services/payment_provider_s.py` | ~230 | Todo lo que habla con MercadoPago |

`users_s.py` queda **fuera del alcance** (314 líneas, 6 funciones públicas, un solo tema).

---

## Puerta de aceptación (los 4 checks, en cada commit)

Ningún commit se considera terminado sin los cuatro. Los tests prueban "no agregué errores";
**no prueban "no perdí funciones"** — si se borra una función que ningún test cubre, el suite queda
verde igual. Por eso el check 1 es el importante y es el que suele saltearse.

### 1. Inventario AST — partición exacta

Antes del commit, extraer de los archivos origen el conjunto de funciones top-level y el cuerpo
normalizado de cada una. Después, lo mismo sobre los archivos resultantes. La aserción es:

- **Mismo conjunto de nombres de función**, ni uno más ni uno menos.
- **Cuerpos byte-idénticos**, salvo los renombres de la tabla de cada commit.

Si un cuerpo cambió y el renombre no está en la lista, el commit está mal.

### 2. `ruff check` limpio

Las reglas `F` están activas (ver `backend/ruff.toml`): detectan nombres indefinidos e imports sin usar,
que son exactamente los errores que produce un move mal hecho.

### 3. `pytest` verde, con el mismo conteo de tests que antes

### 4. `openapi.json` byte-idéntico tras regenerarlo

Prueba que la superficie de API pública no se movió ni un carácter.

---

## Secuencia de commits

Orden ascendente de riesgo, deliberadamente. El arnés de inventario AST del check 1 **también es código
nuevo y también puede estar mal**: conviene que falle o pase por primera vez sobre el caso donde el
resultado se verifica a ojo en dos minutos, no sobre las 1132 líneas donde vive la plata.

### Commit 0 — `session_scope` a `db/session.py`

- [x] Mover `_read_session_scope` y `_write_session_scope` de `products_s.py` (líneas 22–37) a `source/db/session.py`
- [x] Renombrar sin guion bajo: `read_session_scope`, `write_session_scope` (pasan a ser API entre módulos)
- [x] Actualizar los usos en `products_s.py` (15 de lectura, 13 de escritura)
- [x] Los 4 checks

**Riesgo: trivial.** Único commit que toca un archivo fuera de `services/`. Corrige un misplacement
preexistente: no es lógica de producto, es ciclo de vida de sesión.

### Commit 1 — `products_storefront_s.py`

Mover a `products_storefront_s.py`:

| Símbolo | Origen |
|---|---|
| `_variant_to_storefront_dict` | `products_s.py:82` |
| `_storefront_option_axis` | `products_s.py:96` |
| `_storefront_option_label` | `products_s.py:104` |
| `_variant_to_storefront_option` | `products_s.py:120` |
| `_product_to_storefront_dict` | `products_s.py:141` |
| `_calculate_variant_pricing_for_storefront` | `products_s.py:164` |
| `_build_storefront_product_pricing` | `products_s.py:175` |
| `list_storefront_products` | `products_s.py:548` |
| `get_storefront_product_by_id` | `products_s.py:658` |
| `list_storefront_categories` | `products_s.py:544` |

- [x] Verificado: el bloque **no** usa `_compute_min_var_price` ni `_product_inventory` — corte limpio
- [x] Actualizar `routes/storefront_r.py:8` (importa exactamente las 3 públicas, ninguna otra ruta las usa)
- [x] ⚠️ **Actualizar `tests/test_products_min_var_price.py`** — es el **único importador por módulo de todo el repo** (`from source.services import products_s`) y llama `products_s.list_storefront_products`. Se rompe con el split.
- [x] Los 4 checks

⚠️ **El corte no quedó sin imports cruzados** (ver hallazgo H-01): `list_storefront_categories` es
`return list_categories(db=db)`, así que el módulo de vitrina importa `list_categories` del catálogo
administrado. Se resolvió **importando, no duplicando**, por el mismo criterio que `_variant_label` en el
commit 2: el listado de categorías debe ser consistente entre vistas. El import queda acíclico
(vitrina → administrado, nunca al revés).

Beneficio lateral confirmado: `products_s.py` perdió **por completo** su import de `discount_s`. El
catálogo administrado no cotiza — la divergencia de precio ahora es estructural, no una convención.

**Riesgo: bajo.** Renombres esperados: ninguno.

### Commit 2 — `orders_public_s.py`

Mover a `orders_public_s.py`:

| Símbolo | Origen |
|---|---|
| `_deserialize_public_checkout_payload` | `orders_s.py:136` |
| `_extract_public_checkout_url` | `orders_s.py:148` |
| `get_public_order_snapshot_by_payment_token` | `orders_s.py:172` |

- [x] Verificado: construye su propio dict completo, **no** usa `_order_to_dict`
- [x] `_variant_label` se **importa** de `orders_s.py`, no se duplica — es lógica de dominio ("cómo se le nombra una variante a un humano") y debe ser consistente entre las dos vistas, a diferencia del precio, que diverge legítimamente. El import queda acíclico: público → core, nunca al revés.
- [x] Actualizar `routes/orders_r.py:28`
- [x] Los 4 checks
- [x] Verificado acíclico: `orders_s.py` no menciona `orders_public_s`

`_utc_now` también cruzaba y el plan no lo había listado (ver hallazgo H-03). Se importa junto con
`_variant_label`, por el mismo criterio: duplicarlo habría sido crear una definición nueva, que es
justo lo que el check de inventario existe para detectar.

Resultado: 769 + 201 líneas, contra las ~770 + ~180 estimadas.

**Riesgo: bajo.**

### ⏸ CHECKPOINT

**Parar acá.** Revisión del usuario antes de tocar payments — es donde hay menos margen de error y menos
confianza en el corte.

### Commit 3 — `payment_core_s.py` ⚠️ EL PELIGROSO

Mover a `payment_core_s.py` **promoviendo a público** (sin guion bajo):

| Origen | Destino | Línea |
|---|---|---|
| `_payment_to_dict` | `payment_to_dict` | `payment_s.py:56` |
| `_serialize_provider_payload` | `serialize_provider_payload` | `:80` |
| `_deserialize_provider_payload` | `deserialize_provider_payload` | `:86` |
| `_normalize_optional_str` | `normalize_optional_str` | `:98` |
| `_build_order_paid_event_payload` | `build_order_paid_event_payload` | `:107` |
| `_apply_order_paid_transition` | `apply_order_paid_transition` | `:138` |
| `_assert_valid_payment_transition` | `assert_valid_payment_transition` | `:164` |
| `_find_active_pending_payment` | `find_active_pending_payment` | `:170` |
| `_validate_active_pending_compatibility` | `validate_active_pending_compatibility` | `:190` |
| `_resolve_payment_by_idempotency_key` | `resolve_payment_by_idempotency_key` | `:207` |
| `_build_bank_transfer_payload` | `build_bank_transfer_payload` | `:237` |

Estos 11 renombres son la **lista completa de excepciones** al check 1 de este commit. Cualquier otro
cambio de cuerpo es un error.

- [x] Actualizar los 18 usos internos de `_payment_to_dict` y los 6 de `_serialize_provider_payload`
- [x] Actualizar `services/payment_admin_queries_s.py:11` (importaba `_payment_to_dict`)
- [x] Actualizar `services/webhook_events_s.py:16` (importaba `_serialize_/_deserialize_provider_payload`)
- [x] Verificar que `apply_order_paid_transition` conserve sus **dos** llamadores: webhook y confirmación manual
- [x] Los 4 checks

Notas de ejecución:
- `ALLOWED_PAYMENT_TRANSITIONS` (constante, único usuario `assert_valid_payment_transition`) viajó al kernel
  junto con su función. No es una función, así que no lo cubre el check de inventario, pero moverlo mantiene
  el cuerpo de la función byte-idéntico (referencia al mismo nombre a nivel módulo).
- `build_order_paid_event_payload` quedó kernel-interno: solo lo llama `apply_order_paid_transition`, así que
  no se importa en `payment_s`.
- `mercadopago_normalization_s._normalize_optional_str` es una **copia propia deliberada** (comentada en el
  código para evitar un import circular), no un consumidor del privado. Se dejó intacta.
- Kernel resultante: **230 líneas**, holgadamente bajo el umbral de alarma de ~350. El corte es una frontera
  real, no un cajón.

**Riesgo: alto.** Es el único commit del plan con superficie de cambio fuera de su propio dominio.
Por eso va solo: si sale mal, `git revert` de uno y products/orders sobreviven intactos.

### Commit 4 — `payment_provider_s.py`

Mover a `payment_provider_s.py`:

| Símbolo | Origen |
|---|---|
| `_mark_payment_checkout_setup_failed` | `payment_s.py:254` |
| `initialize_mercadopago_checkout_for_payment` | `:270` |
| `mark_payment_checkout_setup_failed` | `:316` |
| `find_payment_for_mercadopago_event` | `:336` |
| `apply_mercadopago_normalized_state` | `:376` |
| `list_reconcilable_pending_mercadopago_payments` | `:865` |

- [ ] Actualizar `routes/payments_r.py`, `jobs/reconcile_pending_payments_job.py`, `services/mercadopago_client.py`
- [ ] `_latest_attempt_query` **se queda** en `payment_s.py` (grupo de reintentos) — `tests/test_payment_retry_locking.py:14` lo importa y no debe romperse
- [ ] Los 4 checks

**Riesgo: medio.**

### Commit 5 — Documentación

Hay **149 referencias a los 3 archivos repartidas en 15 documentos**. Muchas están ancladas a número de
línea, y **todas las líneas se corren** con este refactor, incluso en los archivos que conservan el nombre.

| Doc | Refs | Doc | Refs |
|---|---|---|---|
| `09_ReglasNegocio.md` | 29 | `13_CalidadCodigo.md` | 23 |
| `07_API.md` | 20 | `04_Backend.md` | 15 |
| `08_BaseDatos.md` | 14 | `22_IndiceLectura.md` | 10 |
| `03_ArbolProyecto.md` | 8 | `12_Performance.md` | 8 |
| `11_Seguridad.md` | 7 | `18_Roadmap.md` | 7 |
| resto | 8 | | |

- [ ] **Re-anclar por símbolo, no por línea.** `payment_s.py:138` → `payment_core_s.py::apply_order_paid_transition`. Re-pinnear números de línea compra documentación correcta hasta el próximo commit que toque el archivo; una referencia por símbolo sobrevive a cualquier movimiento.
- [ ] Actualizar `03_ArbolProyecto.md` con los 5 archivos nuevos
- [ ] Actualizar `21_MapaDependencias.md` con las nuevas aristas
- [ ] Agregar entrada del ADR 0001 al índice `docs/README.md`

#### Glosario — extender `19_Glosario.md`, **no** crear `CONTEXT.md`

El repo ya tiene glosario con 26 entradas y el mismo formato. Crear un `CONTEXT.md` fundaría un segundo
glosario compitiendo con el primero.

- [ ] Corregir entradas existentes cuyo puntero se mueve: `bank_transfer` (apunta a `payment_s._build_bank_transfer_payload`) y `blocking_reason` (apunta a `orders_s.get_public_order_snapshot_by_payment_token`)
- [ ] Agregar los términos que esta sesión fijó:
  - **Vista storefront** vs **catálogo administrado** — dos vistas del mismo producto, con reglas de precio distintas por diseño
  - **Snapshot público de orden** — la proyección anónima accesible por token de pago, con serialización propia
  - **Kernel de pago** — el conjunto mínimo compartido por todos los caminos de pago; incluye el punto de entrada del dinero
  - **Divergencia legítima** vs **duplicación accidental** — la distinción que hizo posible este refactor: dos cálculos de precio mínimo son divergencia (dos vistas del negocio); dos copias del session scope son duplicación (infraestructura). Solo la segunda se elimina.

---

## Hallazgos para después

Bugs, simplificaciones y rarezas encontradas durante el movimiento. **No se tocan durante los commits 0–4.**

| # | Hallazgo | Archivo | Notas |
|---|---|---|---|
| H-01 | `list_storefront_categories` es un alias de una línea de `list_categories` — no tiene lógica de vitrina propia | `products_storefront_s.py` | Obliga a la única arista cruzada del split. Evaluar si la vitrina necesita el símbolo o si el router puede llamar `list_categories` directo. No se toca acá: sería cambiar comportamiento de la API. |
| H-02 | `tests/test_products_min_var_price.py` importa servicios **por módulo** y alcanza símbolos privados; es el único del repo que lo hace | `tests/` | Seam demasiado bajo. Se actualizó el import y nada más, según el ticket 03. Subirlo de seam es trabajo aparte. |
| H-03 | `orders_public_s` importa dos privados de `orders_s` (`_variant_label` y `_utc_now`), no uno solo | `orders_public_s.py` | El plan solo había previsto `_variant_label`. `_utc_now` es un `datetime.now(UTC)` de una línea: candidato a subir a un helper de tiempo compartido en vez de quedar como privado importado. |

---

## Deuda conocida que este refactor NO toca

| Ref | Deuda |
|---|---|
| CS-15 | Sufijo `_s` ambiguo entre `schemas/` y `services/`. Arreglarlo implica renombrar los 26 archivos de `services/` y sus imports: es otro refactor, con su propio riesgo. |
| — | Plural inconsistente: `payment_s` (singular) vs `orders_s` / `products_s` (plural). Decisión explícita de no unificar. |
| CS-03 | `HTTPException` filtrándose desde los servicios (`users_s.py`, `auth_s.py:306`). |

---

## Señal de alarma a futuro

Si `payment_core_s.py` supera las ~350 líneas, el corte de payments falló: significa que "core" era
un cajón para lo que sobra compartido y no una frontera real. Revisar el ADR 0001 en ese caso.
