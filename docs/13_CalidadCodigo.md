# 13 — Calidad de Código

← [12 Performance](12_Performance.md) | [Índice](README.md) | Siguiente: [14 Dependencias](14_Dependencias.md) →

---

## 1. Score global

| Dimensión | Score | Comentario |
|---|---:|---|
| Arquitectura y separación de capas | **8,5** | Capas claras y respetadas; sin repositorios pero coherente |
| Nomenclatura y legibilidad | **7,0** | Buena en general; mezcla español/inglés y sufijos ambiguos |
| Cohesión de módulos | **7,5** | Bien delimitados, con 3 archivos que superan las 900 líneas |
| Acoplamiento | **6,5** | Servicios que se importan entre sí; 3 ciclos rotos con imports diferidos |
| DRY | **6,5** | Buen reuso en anti-abuso y jobs; duplicación clara en reintentos de pago y cliente MP |
| Comentarios y documentación en código | **9,0** | ⭐ Excepcional: los comentarios explican el *porqué*, no el *qué* |
| Manejo de errores | **8,0** | Punto único de traducción, jerarquía de excepciones bien pensada |
| Tests | **6,5** | 305 backend (buenos), 51 frontend (insuficientes) |
| Type safety | **7,0** | Backend con type hints; frontend con tipos duplicados y `api.generated` sin usar |
| Consistencia de patrones | **6,0** | 3 estrategias transaccionales conviviendo; 2 estilos de manejo de errores |
| Deuda técnica gestionada | **8,0** | La deuda está **documentada en el código**, no oculta |
| **GLOBAL** | **7,3 / 10** | **Sólido.** Por encima de la media de proyectos de este tamaño |

---

## 2. Score por módulo

### Backend

| Módulo | LOC | Cohesión | Acopl. | Compl. | Tests | Docs | **Score** | Comentario |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `money_s.py` | 86 | 10 | 10 | 9 | 9 | 7 | **9,0** | ⭐ Ejemplar: puro, testeable, una responsabilidad |
| `payment_errors.py` | 25 | 10 | 10 | 10 | 8 | 9 | **9,4** | ⭐ Jerarquía mínima y perfecta |
| `post_commit_actions_s.py` | 61 | 10 | 8 | 9 | 7 | 10 | **9,0** | ⭐ Patrón elegante, bien documentado |
| `auth_cookies_s.py` | 78 | 9 | 8 | 9 | 7 | 7 | **8,2** | Simple y correcto |
| `csrf_d.py` | 50 | 9 | 8 | 9 | 10 | 10 | **9,0** | ⭐ Con tests y comentarios que justifican las exenciones |
| `maintenance_s.py` | 139 | 9 | 6 | 8 | 8 | 10 | **8,4** | ⭐ Docstring de 20 líneas explicando el porqué |
| `security_headers_d.py` | 27 | 9 | 9 | 9 | 6 | 9 | **8,4** | — |
| `idempotency_s.py` | 186 | 9 | 9 | 8 | 8 | 6 | **8,2** | ⚠️ `save_completed_record` es código muerto |
| `auth_tokens_s.py` | 181 | 9 | 8 | 8 | 8 | 6 | **8,0** | Diseño de tokens correcto |
| `mercadopago_d.py` | 68 | 9 | 8 | 8 | 8 | 8 | **8,2** | ⚠️ Ubicado en `dependencies/` sin serlo |
| `notifications_s.py` | 177 | 9 | 9 | 9 | 8 | 5 | **8,2** | ⚠️ La mitad del modelo (`user_id`) sin usar |
| `turns_s.py` | 140 | 9 | 9 | 9 | 7 | 5 | **8,0** | ⚠️ Sin control de capacidad |
| `auth_rate_limit_s.py` | 128 | 9 | 8 | 8 | 8 | 6 | **7,8** | ⚠️ Bloqueo asimétrico entre lectura y escritura |
| `errors.py` | 67 | 9 | 7 | 8 | 8 | 5 | **7,6** | ⚠️ El orden de `isinstance` es frágil |
| `payment_admin_queries_s.py` | 135 | 9 | 6 | 9 | 7 | 8 | **7,8** | ⚠️ Importa `_payment_to_dict` privado |
| `auth_security_s.py` | 195 | 8 | 9 | 8 | 9 | 5 | **7,8** | ⚠️ Nombres mezclados ES/EN; sin caché de config |
| `anti_abuse_s.py` | 282 | 8 | 8 | 7 | 8 | 6 | **7,6** | 🟢 Buen DRY; ⚠️ reutiliza `failed_count` semánticamente |
| `webhook_events_s.py` | 386 | 8 | 6 | 7 | 8 | 8 | **7,6** | ⚠️ "Agnóstico" que solo soporta un proveedor |
| `discount_s.py` | 421 | 8 | 8 | 7 | 8 | 5 | **7,6** | 🟢 Motor puro; ✅ código muerto eliminado (2026-07-21) |
| `domain_events_s.py` | 151 | 8 | 7 | 8 | 8 | 5 | **7,4** | ⚠️ `if/elif` en vez de registro de handlers |
| `email_s.py` | 127 | 8 | 8 | 8 | 7 | 4 | **7,2** | ⚠️ SMTP síncrono; `_format_money` ilegible |
| `stock_reservations_s.py` | 393 | 7 | 7 | 5 | 8 | 6 | **6,8** | ⚠️ Reasignación de la variable de bucle |
| `refund_s.py` | 378 | 7 | 6 | 6 | 7 | 8 | **6,8** | ⚠️ `db.commit()` dentro del `except` |
| `users_s.py` | 314 | 7 | 5 | 7 | 8 | 5 | **6,6** | 🔴 Lanza `HTTPException` (fuga de capa) |
| `mercadopago_normalization_s.py` | 301 | 7 | 6 | 7 | 7 | 8 | **7,0** | ⚠️ `_build_mercadopago_payload` privada pero exportada |
| `auth_s.py` | 330 | 7 | 6 | 7 | 8 | 5 | **6,6** | 🔴 Lanza `HTTPException`; email dentro de la transacción |
| `mercadopago_client.py` | 439 | 7 | 6 | 5 | 7 | 7 | **6,4** | 🔴 Bucle de reintentos duplicado 4 veces |
| `orders_s.py` | 950 | 6 | 4 | 4 | 8 | 6 | **5,6** | 🔴 Demasiado grande; 7 dependencias salientes |
| `products_s.py` | 946 | 6 | 6 | 5 | 8 | 6 | **6,2** | 🔴 5 serializadores solapados; `db=None` opcional |
| `payment_s.py` | 1135 | 6 | 5 | 3 | 9 | 8 | **6,0** | 🔴 El archivo más complejo; duplicación en reintentos |
| `db/models.py` | 741 | 9 | 10 | 9 | 8 | 5 | **8,4** | Declarativo; ⚠️ sintaxis SQLAlchemy 1.x |
| `db/config.py` | 185 | 9 | 10 | 9 | 7 | 8 | **8,6** | 🟢 Fail-fast bien aplicado |
| `db/session.py` | 38 | 9 | 10 | 9 | 8 | 6 | **8,0** | 🔴 Sin configurar el pool |
| `auth_d.py` | 89 | 9 | 8 | 8 | 9 | 6 | **8,0** | ⚠️ Efecto lateral: muta `current_user` |
| `routes/orders_r.py` | 746 | 5 | 5 | 3 | 9 | 7 | **5,6** | 🔴 Lógica de idempotencia repetida inline |
| `routes/*` (los otros 11) | — | 8 | 8 | 8 | 8 | 5 | **7,6** | Consistentes y finos |
| `jobs/*` (6) | — | 9 | 8 | 7 | 9 | 6 | **8,0** | 🟢 Anatomía uniforme y bien pensada |

### Frontend

| Módulo | LOC | Cohesión | Acopl. | Compl. | Tests | **Score** | Comentario |
|---|---:|---:|---:|---:|---:|---:|---|
| `lib/cart-storage.ts` | 94 | 10 | 10 | 9 | 10 | **9,6** | ⭐ Puro, testeable, 13 tests |
| `lib/useModalA11y.ts` | ~40 | 9 | 9 | 8 | 10 | **9,0** | ⭐ Con tests de accesibilidad |
| `lib/useAsyncResource.ts` | 43 | 9 | 10 | 8 | 0 | **7,0** | 🟢 Buen diseño; ❌ **sin tests** |
| `services/idempotency.ts` | 7 | 10 | 10 | 10 | 0 | **8,0** | Trivial |
| `services/http.ts` | 68 | 9 | 8 | 7 | 0 | **7,2** | 🟢 Deduplicación de refresh; ❌ sin tests |
| `guards/*` | ~15 c/u | 10 | 8 | 10 | 0 | **8,0** | Simples y correctos |
| `services/*-api.ts` (10) | — | 9 | 9 | 9 | 0 | **7,8** | Consistentes; ❌ sin tests |
| `features/auth/context` | 117 | 8 | 7 | 8 | 5 | **7,2** | Cubierto indirectamente |
| `features/checkout/hooks` | 310 | 8 | 6 | 6 | 9 | **7,4** | 🟢 18 tests |
| `features/storefront/hooks` | ~200 | 8 | 8 | 7 | 0 | **6,6** | ❌ Sin tests |
| `features/profile/hooks` | 310 | 6 | 5 | 5 | 0 | **5,4** | 🔴 Hook de 310 líneas sin tests |
| `services/http-errors.ts` | 318 | 6 | 3 | 5 | 0 | **4,8** | 🔴 Acoplado por strings al backend, sin tests |
| `components/Layout.tsx` | 246 | 5 | 6 | 6 | 0 | **5,4** | 🔴 4 responsabilidades |
| `features/admin/hooks` | ~1.750 | 6 | 6 | 5 | 2 | **5,2** | 🔴 Solo 1 de 8 hooks tiene tests |
| `features/admin/components` | ~2.550 | 4 | 5 | 4 | 0 | **4,2** | 🔴 `CatalogSection` 821 líneas, ~95 props |
| `pages/*` | ~1.400 | 8 | 8 | 8 | 0 | **7,0** | 🟢 Casi sin lógica |

---

## 3. Principios SOLID

### S — Single Responsibility

| Estado | Ejemplos |
|---|---|
| 🟢 **Se cumple** | `money_s` (aritmética), `auth_cookies_s` (cookies), `idempotency_s` (idempotencia), `post_commit_actions_s` (diferir efectos), `payment_errors` (excepciones) |
| 🟠 **Se viola** | `orders_s` (estados + carrito + ventas admin + snapshot público), `payment_s` (creación + reintentos + confirmación manual + estado del proveedor + consultas), `products_s` (CRUD + storefront + stock), `orders_r.create_guest_checkout_order` (idempotencia + anti-abuso + orquestación + manejo de fallo del proveedor), `Layout.tsx` (shell + notificaciones + carrito + banner) |

**Evidencia de que el equipo lo tiene presente:** el docstring de `payment_s.py` documenta que ese archivo
**ya se dividió** una vez, de ~1900 líneas a 1135, extrayendo `mercadopago_normalization_s`,
`webhook_events_s` y `payment_admin_queries_s`. La refactorización quedó a medio camino, pero la conciencia
está.

### O — Open/Closed

| Estado | Ejemplos |
|---|---|
| 🟢 | `anti_abuse_s`: agregar un nuevo límite público es definir 3 scopes y llamar al helper genérico |
| 🟢 | Jobs: agregar uno es crear el archivo con `run_once()` y sumarlo a la lista `JOBS` |
| 🟠 | `domain_events_s.publish_domain_event`: un `if/elif` que hay que **modificar** para cada evento nuevo |
| 🟠 | `errors.raise_http_error_from_exception`: cadena de `isinstance` que hay que modificar |
| 🟠 | `http-errors.toUserMessage`: 9 bloques `if (context === ...)` |

### L — Liskov

No aplica prácticamente: no hay jerarquías de clases más allá de las excepciones, y ahí se respeta
(cualquier `PaymentProviderError` es intercambiable).

⚠️ Matiz: las 4 excepciones de dominio heredan de `ValueError`, lo que es correcto por Liskov pero **hace que el
orden de los `isinstance` en `errors.py` importe**. Un reordenamiento accidental degradaría 409 a 400 sin que
ningún test lo detecte (no hay test que verifique el orden).

### I — Interface Segregation

🟠 **Se viola en el frontend.** Los hooks del panel admin devuelven objetos de 40–70 propiedades, y los
componentes reciben todas como props individuales. `CatalogSection` recibe ~95 props: interfaz enorme donde
cada consumidor usa un subconjunto.

🟢 En el backend no aplica (no hay interfaces).

### D — Dependency Inversion

| Estado | Ejemplos |
|---|---|
| 🟢 | `Session` inyectada por FastAPI (`Depends`) — los servicios no la crean |
| 🟢 | `useLoginPage(login)` recibe la función de login como parámetro → testeable sin Context |
| 🟢 | Jobs invocables como función (`run_once`) o proceso (`main`) |
| 🟠 | Los servicios importan modelos SQLAlchemy directamente: **no** hay abstracción de persistencia |
| 🟠 | `refund_s` importa `mercadopago_client` concreto, no una interfaz `PaymentProvider` |
| 🟠 | `products_s._read_session_scope(db=None)` **crea** su propia sesión si no se la pasan |

> 📌 La ausencia de repositorios es una decisión coherente para el tamaño del proyecto (evita 27 clases de
> abstracción que solo delegarían), pero tiene un costo concreto: **no se puede testear un servicio sin base de
> datos**.

---

## 4. Otros principios

### DRY

**🟢 Buen reuso:**
- `anti_abuse_s._enforce_public_email_ip_limits` — 4 casos de uso sobre un helper.
- Anatomía uniforme de los 6 jobs.
- `products_r` y `discounts_r` con estructura idéntica.
- `AdminUserSearchModal` reutilizado por 2 secciones del panel.

**🔴 Duplicación relevante:**

| # | Duplicación | Líneas | Dónde |
|---|---|---:|---|
| D-01 | ✅ ~~Bucle de reintentos del cliente MP, 4 veces~~ — **resuelto** con `tenacity` *(= R-07, D-11)* | 0 | `mercadopago_client.py:_request` |
| D-02 | ✅ ~~`create_retry_payment_for_order` vs `create_retry_payment_for_payment_token`~~ — **resuelto**, ver nota abajo | ~20 | `payment_s.py:768` y `:807` |
| D-03 | Bloque de idempotencia en 2 endpoints — **refactor, no bugfix** (ver [§5 bis](#5-bis-️-los-caminos-de-fallo-de-idempotencia-no-son-verificables-por-la-suite)) | ~60 | `orders_r.py:157-229` y `:321-347` |
| D-04 | 5 serializadores de producto/variante solapados | ~80 | `products_s.py:52-160` |
| D-05 | Allowlist de hosts de MP en Python y TypeScript | ~15 | `mercadopago_normalization_s.py:34` y `checkout-api.ts:6` |
| D-06 | `_normalize_optional_str` duplicada **a propósito** | 8 | `payment_s.py:98` y `mercadopago_normalization_s.py:44` (con comentario que lo justifica) |
| D-07 | `formatArs` en 3 features distintas | ~10 | `admin/utils/format.ts`, `checkout/utils/format.ts`, `storefront/utils/format.ts` |
| D-08 | `isRetryableMercadoPagoPayment` en cliente duplica reglas del backend | ~10 | `useProfilePage.ts:195-203` |

> ✅ **D-02 está resuelto.** Los dos entrypoints comparten `_guard_order_retryable` (`payment_s.py:681`),
> `_guard_retryable_latest_attempt` (`:745`) y `_latest_attempt_query` (`:722`). Las ~20 líneas que quedan en
> paralelo son el esqueleto (normalizar la key, replay por idempotencia, guards, delegación a
> `create_payment_for_order`) con argumentos distintos en cada paso: la identidad se resuelve por sesión en un
> caso y por `public_status_token` en el otro. Colapsarlas más pediría un parámetro de "modo" que empeoraría
> la legibilidad.
>
> 📌 **D-06 es un caso interesante de duplicación *correcta*:** el comentario explica que importar desde
> `payment_s` crearía un ciclo, y que es un helper puro trivial. Duplicar 8 líneas es preferible a un import
> circular. Bien razonado.

### KISS

🟢 **Se respeta ampliamente.** Ejemplos:
- Frontend con 4 dependencias de runtime.
- Servicios como funciones, no clases.
- Notificaciones con polling simple en vez de WebSockets.
- Jobs con `time.sleep()` en vez de un scheduler.
- Un solo `styles.css`.

🟠 **Complejidad esencial mal contenida:** el flujo de idempotencia del checkout guest tiene 4 caminos distintos
en 70 líneas dentro de un handler. La complejidad es necesaria; la ubicación no.

### YAGNI

🟠 **Varias violaciones — código construido y no usado:**

| Elemento | Estado |
|---|---|
| `k8s_idempotency_sweeper_*.yaml` (4 archivos) | ⚠️ El `README.md:15` reconoce que no se usan |
| `Dockerfile.sweeper` | ⚠️ Ídem |
| `notifications.user_id` y `role_target` genérico | ⚠️ Solo se crean notificaciones de admin |
| `orders.currency` / `payments.currency` | ⚠️ Todo forzado a `ARS` |
| `idempotency_s.save_completed_record` | ⚠️ Nadie la llama |
| `schemas/stock_reservations_s.py` (2 modelos) | ⚠️ Definidos, nunca usados |
| `products_s.decrement_stock` / `add_stock` | ⚠️ Solo desde tests |
| `services/payments-api.fetchPublicPaymentStatus` | ⚠️ Reemplazado por el snapshot |
| `frontend/src/types/api.generated.ts` | 🔴 3.992 líneas generadas y validadas en CI, casi sin importar |
| `run_forever()` en los 6 jobs | 🟡 Solo se usa en local (Task Scheduler llama `--once`) |

### Clean Code

| Aspecto | Valoración |
|---|---|
| Nombres descriptivos | 🟢 8/10 — `create_late_paid_incident_if_needed`, `_expire_active_reservations_internal` son autoexplicativos |
| Funciones pequeñas | 🟡 6/10 — muchas de 100+ líneas |
| Un nivel de abstracción por función | 🟡 6/10 — `create_guest_checkout_order` mezcla niveles |
| Sin efectos secundarios ocultos | 🟠 5/10 — ver §5 |
| Comentarios que explican el porqué | 🟢 **10/10** — ver §6 |
| Sin código muerto | 🟠 5/10 — ver YAGNI |
| Manejo de errores separado | 🟢 8/10 — `errors.py` centraliza |

---

## 5. Code smells {#acoplamiento}

### 🔴 Críticos

| # | Smell | Dónde | Por qué importa |
|---|---|---|---|
| CS-01 | **Efectos secundarios ocultos en lecturas** | `create_payment_for_order` expira reservas (y puede **cancelar la orden**); `GET /public/orders/by-payment-token` y `GET /orders/{id}/reservations` mutan estado | Viola CQS. Un `GET` que cambia datos sorprende a cualquiera |
| CS-02 | **Reasignación de la variable de bucle sobre un parámetro** | `stock_reservations_s.py:149` — `for order_id, reservations in ...` donde `order_id` también es parámetro | Funciona hoy; cualquier refactor que use el parámetro después rompe silenciosamente |
| CS-03 | **Fuga de capa: `HTTPException` en servicios** | `users_s.py:46,78,111,120,164,199,212`; `auth_s.py:306` | Impide reutilizar esos servicios desde jobs o CLI |
| CS-04 | **`db.commit()` dentro de un `except`** | `refund_s.py:364`, `orders_r.py:114` | Rompe el contrato de `get_db_transactional`. Justificado y comentado, pero frágil — ver [§5 bis](#5-bis-️-los-caminos-de-fallo-de-idempotencia-no-son-verificables-por-la-suite) |
| CS-05 | **God object en el frontend** | `CatalogSection.tsx` 821 líneas, ~95 props | Imposible de testear; cualquier cambio re-renderiza todo |
| CS-06 | **Acoplamiento por strings entre capas** | `http-errors.ts` compara `detail` con literales de `payment_s.py` | Cambiar un mensaje rompe la UI sin que nada lo detecte |

### 🟠 Importantes

| # | Smell | Dónde |
|---|---|---|
| CS-07 | Long method | `create_guest_checkout_order` (157), `get_public_order_snapshot_by_payment_token` (140), `apply_mercadopago_normalized_state` (135), `create_payment_for_order` (186) |
| CS-08 | Long parameter list | `create_payment_for_order` (8 params), `_enforce_public_email_ip_limits` (9), `confirm_manual_payment_for_order` (8) |
| CS-09 | Feature envy | `payment_admin_queries_s` y `webhook_events_s` importan funciones **privadas** (`_payment_to_dict`, `_serialize_provider_payload`) de `payment_s` |
| CS-10 | Primitive obsession | Todos los estados son `str` libres; los importes son `int` sin tipo `Money` |
| CS-11 | Shotgun surgery | Agregar un método de pago exige tocar `payment_s`, 2 schemas, el frontend y los tests |
| CS-12 | Inconsistencia transaccional | 3 estrategias de sesión conviviendo en `orders_r.py` |
| CS-13 | Boolean trap | `initialize_provider=False`, `allow_create_if_missing=True`, `force=True` — flags que cambian el comportamiento sustancialmente |
| CS-14 | Naming inconsistente | `calcular_amount`, `firmar_jwt`, `obtener_config_jwt`, `parsear_sub_a_user_id`, `resolver_evento_webhook_mercadopago` junto a nombres en inglés |
| CS-15 | Sufijo `_s` ambiguo | `schemas/orders_s.py` y `services/orders_s.py` |

### 🟡 Menores

| # | Smell | Dónde |
|---|---|---|
| CS-16 | Números mágicos sin nombre | `[:16]` y `[:24]` en los hashes de idempotencia, `[:2000]` en `last_error`, `255` en la longitud del token |
| CS-17 | Comparación por string en lugar de enum | `str(payment.status) == "pending"` en todo `payment_s` |
| CS-18 | `except Exception: pass` | `refund_s.py:370-371`, `orders_r.py:120-121` (justificados, pero silencian todo) |
| CS-19 | Estilos inline mezclados con clases | `Layout.tsx:214`, `:215` |
| CS-20 | `eslint-disable` sin explicación completa | `useAsyncResource.ts:39` |

---

## 5 bis. ⚠️ Los caminos de fallo de idempotencia no son verificables por la suite

**Los tests corren sobre SQLite** (`DATABASE_URL=sqlite://`, [_base.py:16](../backend/tests/http/_base.py)) y **producción es
PostgreSQL**. En el punto exacto que la idempotencia necesita —el `SAVEPOINT` que abre `acquire_record`
([idempotency_s.py:103](../backend/source/services/idempotency_s.py))— los dos motores no se comportan igual.

Medido con un cluster PostgreSQL 18 temporal, mismo `INSERT` dentro de `begin_nested()` seguido de un rollback
de la transacción externa:

| Motor | Filas tras el rollback externo |
|---|---|
| SQLite (tests) | `[('INSERT-en-savepoint',)]` — el insert **se escapa** |
| PostgreSQL 18 (producción) | `[]` — el insert revierte, correcto |

Es el bug conocido de `pysqlite` con SAVEPOINT. Consecuencias verificadas end-to-end sobre `POST /admin/sales`
con un fallo forzado:

| Comportamiento | SQLite | PostgreSQL 18 |
|---|---|---|
| Registro tras el fallo | trabado en `processing` | no queda ninguno |
| Reintento con la misma key | `409` permanente hasta el sweeper | `200 OK`, la venta se procesa |

**Lo importante: en producción el diseño es correcto.** La protección contra requests concurrentes no depende
de que el registro sobreviva, sino del **índice único**: una segunda request se bloquea esperando el insert de
la primera (medido: 1,3 s) y recién resuelve cuando esa decide. Si la primera commitea, la segunda hace replay;
si revierte, la segunda toma el trabajo.

> 📌 **Por qué importa igual.** Quien toque estos caminos los va a validar contra una semántica que no es la de
> producción, y va a leer código defensivo escrito contra un comportamiento que su entorno le muestra distinto.
> Ya pasó una vez: el bloque de recuperación de `create_admin_sale_endpoint` (20 líneas con doble `try`, dos
> `logger.exception` y un `db.delete` de último recurso) fue escrito como si el registro persistiera. Se eliminó
> tras comprobar que la transacción lo descarta entero.
>
> Mitigación real: correr al menos los tests de idempotencia contra PostgreSQL en CI. Hasta entonces, cualquier
> aserción sobre estos caminos vale sólo para SQLite.

---

## 6. ⭐ Lo mejor del código: los comentarios

**Esta es la mayor fortaleza del repositorio y merece una sección propia.** Los comentarios **explican
decisiones**, no describen código. Es infrecuente y muy valioso.

**Ejemplos:**

```python
# db/config.py:120-123
# Browsers reject `SameSite=None` cookies that are not also `Secure`, which
# would silently drop the auth cookie in the cross-origin production setup.
# Fail fast instead of shipping a login that appears to work but never
# persists the session.
```

```python
# products_s.py:600-604
# min_price/max_price and sort_by="price" need the discount-aware final price,
# which is only computable in Python (see _build_storefront_product_pricing) —
# those paths must fetch every matching row before filtering/sorting/paging.
# Without them, name-sorted browsing (the common case) can page in SQL directly.
```

```python
# refund_s.py:352-354
# Commit the failed status now instead of leaving it to the caller's
# transactional session wrapper, so that re-raising below doesn't trigger
# a rollback that discards this refund request and its failed status.
```

```python
# mercadopago_normalization_s.py:45-47
# Intentionally duplicated from payment_s._normalize_optional_str: payment_s
# imports from this module (for checkout payload building), so importing back
# from payment_s here would create a circular import. It's a trivial pure helper.
```

```python
# maintenance_s.py:9-19  (docstring de 20 líneas)
# Design notes:
# - The ping cadence IS the interval. Each underlying job already guards its own
#   work (min-age windows for reconcile, older-than for prunes, exponential
#   backoff for webhook reprocess), so running them on every ping is safe and
#   idempotent; there is no separate per-job "last run" bookkeeping to maintain.
```

```python
# auth_r.py:64-69
# request.client.host is trustworthy as-is: Uvicorn's ProxyHeadersMiddleware
# (proxy_headers=True by default) already rewrites it from X-Forwarded-For,
# but only when the connection comes from an IP listed in FORWARDED_ALLOW_IPS...
```

```ts
// http.ts:4-6
// Render's free tier sleeps after ~15 min idle and takes 30-60s to answer the
// first request on wake, so the timeout must tolerate that cold start in
// production.
```

```
# .gitignore:24-27
# NOTE: src/types/api.generated.ts is committed (not ignored) so the frontend
# builds hermetically on Vercel/Cloudflare, which have no Python to regenerate
# it from the backend. CI regenerates it and fails on drift (see ci.yml).
```

> 🟢 **Estos comentarios documentan trade-offs conscientes.** Quien llegue nuevo entiende *por qué* el código es
> como es, no solo qué hace. Esta documentación (`docs/`) se apoya fuertemente en ellos.

---

## 7. Patrones de diseño detectados

| Patrón | Dónde | Calidad |
|---|---|---|
| **Layered Architecture** | Routes → Services → Models | 🟢 Consistente |
| **Service Layer** (funcional) | `source/services/` | 🟢 |
| **Unit of Work** (implícito) | `get_db_transactional` | 🟢 |
| **Dependency Injection** | `Depends()` de FastAPI | 🟢 |
| **Chain of Responsibility** | Middlewares ASGI | 🟢 |
| **Strategy** (implícito) | Método de pago determina el payload del proveedor | 🟡 Implementado con `if/elif` |
| **Template Method** | Anatomía de los jobs (`_param`, `run_once`, `run_forever`, `main`) | 🟢 |
| **Facade** | `mercadopago_client` sobre el SDK | 🟢 |
| **Adapter** | `mercadopago_normalization_s` traduce proveedor ↔ dominio | 🟢 |
| **Command Queue** (diferido) | `post_commit_actions_s` | 🟢 ⭐ |
| **Observer** (simulado) | `domain_events_s` — síncrono, sin registro | 🟡 |
| **Observer** (navegador) | `CustomEvent` `pb-auth-unauthorized`, `pb-cart-updated` | 🟢 |
| **Retry with backoff** | `mercadopago_client` (lineal), `reprocess_failed_webhooks_job` (exponencial) | 🟡 El del cliente debería ser exponencial con jitter |
| **Idempotency Key** | `idempotency_s` + `payments.idempotency_key` | 🟢 ⭐ |
| **Dead Letter Queue** | `webhook_events.dead_letter_at` | 🟢 |
| **Capability Token** | `public_status_token` | 🟢 |
| **Optimistic UI** | `deriveProductFromVariants`, marcar notificación leída | 🟢 |
| **Compare-and-Swap** | Descuento de stock | 🟢 ⭐ |
| **Custom Hook** | Todo el frontend | 🟢 |
| **Barrel exports** | `features/*/index.ts` | 🟢 |
| **Guard / Route protection** | `ProtectedRoute`, `AdminRoute` | 🟢 |
| **Singleton promise** | `refreshPromise` en `http.ts` | 🟢 ⭐ |

### Patrones **ausentes** que aportarían

| Patrón | Dónde ayudaría |
|---|---|
| **Repository** | Testear servicios sin base de datos |
| **Outbox** | Eliminar llamadas externas dentro de transacciones |
| **Event Store** | Persistir los eventos de dominio; hoy son efímeros |
| **Circuit Breaker** | Dejar de golpear a Mercado Pago cuando está caído |
| **Specification** | Componer los filtros de descuento de forma declarativa |
| **State pattern** | Reemplazar los diccionarios de transiciones |
| **Result / Either** | Evitar que las reglas de negocio sean excepciones |

---

## 8. Complejidad ciclomática estimada

### Las 15 funciones más complejas

| # | Función | Archivo | CC est. | Nivel |
|---:|---|---|---:|---|
| 1 | `create_guest_checkout_order` | `orders_r.py:151` | ~28 | 🔴 |
| 2 | `create_payment_for_order` | `payment_s.py:457` | ~26 | 🔴 |
| 3 | `apply_mercadopago_normalized_state` | `payment_s.py:320` | ~24 | 🔴 |
| 4 | `_expire_active_reservations_internal` | `stock_reservations_s.py:120` | ~22 | 🔴 |
| 5 | `get_public_order_snapshot_by_payment_token` | `orders_s.py:172` | ~21 | 🔴 |
| 6 | `toUserMessage` | `http-errors.ts:148` | ~20 | 🔴 |
| 7 | `confirm_manual_payment_for_order` | `payment_s.py:892` | ~19 | 🟠 |
| 8 | `create_admin_sale` | `orders_s.py:819` | ~18 | 🟠 |
| 9 | `list_storefront_products` | `products_s.py:547` | ~17 | 🟠 |
| 10 | `create_mercadopago_refund` | `refund_s.py:222` | ~17 | 🟠 |
| 11 | `run_once` (reprocess webhooks) | `reprocess_failed_webhooks_job.py:115` | ~17 | 🟠 |
| 12 | `create_retry_payment_for_payment_token` | `payment_s.py:745` | ~16 | 🟠 |
| 13 | `onRetryMercadoPago` | `useProfilePage.ts:205` | ~15 | 🟠 |
| 14 | `_validate_discount_payload` | `discount_s.py:206` | ~15 | 🟠 |
| 15 | `change_order_status` | `orders_s.py:584` | ~14 | 🟠 |

> 📌 **Metodología:** estimación manual contando ramas (`if`, `elif`, `and`/`or`, `for`, `except`, ternarios).
> No se ejecutó ninguna herramienta (`radon`, `mccabe`). Los valores son orientativos.
> **Umbral recomendado:** CC > 10 merece refactor; CC > 20 es riesgo alto de bug.

---

## 9. Deuda técnica

### Inventario priorizado

| ID | Deuda | Tipo | Interés¹ | Esfuerzo | Prioridad |
|---|---|---|---|---|---|
| DT-01 | `payment_s.py` (1135 líneas) sigue siendo demasiado grande | Diseño | Alto | 3 días | P1 |
| DT-02 | Lógica de idempotencia repetida inline en 2 endpoints | Diseño | Alto | 1 día | P1 |
| DT-03 | `http-errors.ts` acoplado por strings al backend | Contrato | Alto | 2 días | P1 |
| DT-04 | `api.generated.ts` sin usar (falta `response_model`) | Contrato | Alto | 3 días | P1 |
| DT-05 | 3 estrategias transaccionales conviviendo | Consistencia | Medio | 2 días | P2 |
| DT-06 | `HTTPException` en servicios | Capas | Medio | 4 h | P2 |
| DT-07 | ✅ ~~Bucle de reintentos duplicado 4× en `mercadopago_client`~~ *(= D-01, R-07)* — **saldada**; queda la costura `_retry_sleep` en los tests | DRY | Bajo | 2 h | P3 |
| DT-08 | ✅ ~~Duplicación en `create_retry_payment_*`~~ *(= D-02, R-08)* — **saldada** | DRY | — | 4 h | — |
| DT-09 | `CatalogSection` de 821 líneas con ~95 props | Diseño | Alto | 3 días | P2 |
| DT-10 | Código muerto (≈10 elementos, ver YAGNI) | Limpieza | Bajo | 4 h | P2 |
| DT-11 | Sin abstracción de persistencia → tests requieren DB | Testabilidad | Medio | 1 semana | P3 |
| DT-12 | Estados como `str` en vez de `Enum` | Type safety | Medio | 1 día | P3 |
| DT-13 | Nombres mezclados español/inglés | Legibilidad | Bajo | 4 h | P3 |
| DT-14 | Sufijo `_s` ambiguo (schema vs service) | Legibilidad | Bajo | 2 h | P3 |
| DT-15 | Manifiestos K8s y Dockerfile sin uso | Limpieza | Bajo | 30 min | P3 |
| DT-16 | Reglas de negocio duplicadas en el cliente | Consistencia | Medio | 1 día | P3 |

¹ *Interés = costo de mantener esta deuda sin pagarla (frecuencia con que estorba).*

### Deuda técnica **documentada** 🟢

Un indicador de madurez: buena parte de la deuda está reconocida en el propio código.

| Dónde | Qué reconoce |
|---|---|
| `payment_s.py:1-6` | "split out of what used to be a single ~1900-line file" |
| `webhook_events_s.py:2-5` | "Split out of payment_s.py, which had grown into a god file" |
| `payment_admin_queries_s.py:2-5` | Ídem |
| `mercadopago_normalization_s.py:2-6` | Ídem |
| `README.md:15` | Los manifiestos K8s son referencia, no se usan |
| `README.md:41` | El envío de emails "no implementado al 100%" |
| `db-backup.yml:9-12` | "best-effort free backup, not a managed DR solution" |
| `ruff.toml:1-5` | Justifica el alcance reducido del linting |

---

## 10. Herramientas de calidad

| Herramienta | Backend | Frontend |
|---|---|---|
| Linter | 🟢 Ruff 0.15.22 (F + E + W) | 🟢 ESLint 9 flat config + typescript-eslint + react-hooks |
| Formateador | ❌ Ninguno | ❌ Ninguno (sin Prettier) |
| Type checker | 🟡 Type hints presentes, **sin mypy/pyright en CI** | 🟢 `tsc -b` en el build |
| Tests | 🟢 pytest, 305 tests | 🟢 Vitest, 51 tests |
| Cobertura | ❌ Sin medición | ❌ Sin medición |
| Complejidad | ❌ Sin `radon`/`mccabe` | ❌ Sin `eslint-plugin-complexity` |
| Seguridad | ❌ Sin `bandit`/`pip-audit` | ❌ Sin `npm audit` |
| Pre-commit hooks | ❌ | ❌ |

**Configuración de Ruff** (`ruff.toml`): alcance deliberadamente acotado a `F` (pyflakes) + subconjunto de `E`
(pycodestyle) + `W`, con el razonamiento escrito en el archivo:

> *"Scope kept intentionally close to Ruff's curated default (pyflakes `F` plus the high-signal pycodestyle `E`
> subset) so linting catches real problems -- unused imports/vars, undefined names, syntax issues -- without
> imposing large style-only churn on the existing codebase."*

🟢 Decisión razonable y bien argumentada.
🟡 Faltan reglas de alto valor: `B` (bugbear), `S` (bandit), `C90` (complejidad), `I` (orden de imports).

> **Recomendaciones de tooling:**
> 1. `ruff format` (ya viene con Ruff) → un formateador sin dependencia nueva.
> 2. Prettier para el frontend.
> 3. `pytest --cov` y `vitest --coverage` con umbral mínimo.
> 4. Extender Ruff con `B`, `S`, `I`, `C90` gradualmente.
> 5. `mypy` en modo permisivo, solo sobre `source/services/`.

---

## 11. Conclusión

### Lo que este código hace bien

1. ⭐ **Comentarios que explican decisiones** — la mejor cualidad del repositorio.
2. ⭐ **Invariantes concurrentes en la base**, no en Python.
3. ⭐ **`post_commit_actions_s`** — patrón elegante y correcto.
4. ⭐ **Idempotencia con recuperación**, no solo replay.
5. **Separación de capas** consistente.
6. **Manejo de errores centralizado** con jerarquía coherente.
7. **305 tests de backend** cubriendo los caminos críticos.
8. **Refactorización activa** documentada (el god file ya se dividió una vez).
9. **Deuda reconocida** en el código, no oculta.
10. **Sin sobre-ingeniería**: 14 dependencias de runtime en total.

### Lo que hay que atacar primero

1. 🔴 **`payment_s.py` y `orders_r.py`** — terminar la refactorización que ya empezó.
2. 🔴 **Extraer la idempotencia a un decorador/dependencia** reutilizable.
3. 🔴 **Declarar `response_model`** para que `api.generated.ts` sirva de algo.
4. 🔴 **Códigos de error estables** en lugar de comparar mensajes.
5. 🔴 **Tests del panel admin**, especialmente de las secciones que mueven dinero.
6. 🟠 **Dividir `CatalogSection`** y reducir el prop drilling.
7. 🟠 **Eliminar `HTTPException` de los servicios.**
8. 🟠 **Unificar la estrategia transaccional.**

---

← [12 Performance](12_Performance.md) | [Índice](README.md) | Siguiente: [14 Dependencias](14_Dependencias.md) →
