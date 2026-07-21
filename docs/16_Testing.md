# 16 — Testing

← [15 Configuración](15_Configuracion.md) | [Índice](README.md) | Siguiente: [17 Production Readiness](17_ProductionReadiness.md) →

---

## 1. Panorama

| Métrica | Backend | Frontend |
|---|---:|---:|
| Archivos de test | 40 | 6 |
| Tests | **305** | **51** |
| Framework | `unittest.TestCase` ejecutado por **pytest 9.0.2** | **Vitest 4.1.10** + Testing Library |
| Base de datos | SQLite en memoria | — |
| Cobertura medida | ❌ **No** | ❌ **No** |
| Tests E2E | ❌ No hay | ❌ No hay |
| Tests de componentes | — | ❌ **Ninguno** |
| Ratio test:código | ~0,55 (12.400 líneas de test / 22.700 de Python) | ~0,08 (~800 / ~10.600) |

> 📌 **El desequilibrio es el hallazgo principal:** el backend está bien cubierto, el frontend casi no lo está,
> y el panel admin —donde se mueve dinero manualmente— tiene un solo hook testeado de ocho.

---

## 2. Estrategia del backend

### 2.1 Dos niveles

```mermaid
flowchart TD
    A["backend/tests/"] --> B["tests/http/ — 13 archivos, 172 tests<br/>Integración sobre TestClient de FastAPI"]
    A --> C["tests/*.py — 26 archivos, 133 tests<br/>Unitarios de servicio"]
    A --> D["tests/factories/ — 7 archivos<br/>Builders de datos + helpers HTTP"]

    B --> B1["HttpFundamentalsBase<br/>SQLite en memoria (StaticPool)<br/>override de get_db y get_db_transactional<br/>drop_all + create_all en cada setUp"]
    C --> C1["Engine SQLite propio por clase<br/>Llamada directa al servicio"]
```

### 2.2 `tests/http/_base.py` — la base de integración

```python
class HttpFundamentalsBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://",
                                   connect_args={"check_same_thread": False},
                                   poolclass=StaticPool)          # ← una sola conexión compartida
        Base.metadata.create_all(bind=cls.engine)
        app.dependency_overrides[get_db] = _get_db_override
        app.dependency_overrides[get_db_transactional] = _get_db_transactional_override

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)                  # ← aislamiento total por test
        Base.metadata.create_all(bind=self.engine)
        self.client = TestClient(app)
```

🟢 **Aciertos:**
- `StaticPool` con `check_same_thread=False` para que `TestClient` y el test compartan la misma base en memoria.
- `drop_all`/`create_all` por test → aislamiento perfecto, sin fugas entre tests.
- Los overrides de dependencia replican la semántica real (uno commitea, el otro no).
- Env de test seteadas con `setdefault` **antes** de importar `main`, porque `db/session.py` evalúa
  `DATABASE_URL` al importarse.
- Helpers de fixture: `_create_user`, `_create_guest_user`, `_seed_variant`, `_login`,
  `_extract_token_from_mock`, `_origin_headers` (que añade el `Origin` para pasar el CSRF).

⚠️ **Costo:** `drop_all + create_all` en cada uno de los 172 tests HTTP recrea 17 tablas cada vez. Es lento pero
seguro. Con SQLite en memoria sigue siendo aceptable.

### 2.3 Nomenclatura

Convención muy consistente y legible:

```
test_<acción>_<condición>_<resultado esperado>_over_http
```

Ejemplos reales:
- `test_guest_checkout_conflict_for_same_key_different_payload_over_http`
- `test_admin_sale_cash_requires_amount_minus_change_equals_total_over_http`
- `test_update_order_status_rejects_paid_transition_over_http`
- `test_admin_register_manual_payment_rejects_order_without_pending_payment_over_http`

🟢 El nombre **es** la especificación. Se puede leer la lista de tests como documentación de reglas de negocio.

### 2.4 Cobertura por área

| Área | Archivo(s) | Tests | Valoración |
|---|---|---:|---|
| **Pagos (HTTP)** | `http/test_payments_fundamentals.py` | 37 | 🟢 La mejor cubierta |
| **Checkout (HTTP)** | `http/test_checkout_fundamentals.py` | 24 | 🟢 Incluye idempotencia, replay, conflictos, guest vs registrado |
| **Catálogo CRUD (HTTP)** | `http/test_products_crud_fundamentals.py` | 21 | 🟢 |
| **Reprocesamiento de webhooks** | `test_reprocess_failed_webhooks_job.py` | 18 | 🟢 Backoff y dead letter |
| **Mapeo de errores de pago** | `test_payment_errors_mapping.py` | 15 | 🟢 Cada excepción → su status |
| **Webhooks admin (HTTP)** | `http/test_admin_webhook_fundamentals.py` | 13 | 🟢 |
| **Búsqueda de usuarios (HTTP)** | `http/test_users_search_resolve_fundamentals.py` | 10 | 🟢 |
| **Turnos (HTTP)** | `http/test_turns_fundamentals.py` | 10 | 🟢 |
| **Seguridad** | `test_security.py` | 9 | 🟢 |
| **Descuentos (HTTP)** | `http/test_discounts_fundamentals.py` | 9 | 🟢 |
| **Catálogo público (HTTP)** | `http/test_catalog_fundamentals.py` | 9 | 🟢 |
| **Auth (HTTP)** | `http/test_auth_fundamentals.py` | 9 | 🟡 Escaso para 11 endpoints |
| **Precio mínimo por variante** | `test_products_min_var_price.py` | 7 | 🟢 |
| **Consistencia monetaria de pagos** | `test_payments_money_consistency.py` | 7 | 🟢 ⭐ |
| **Máquina de estados de orden** | `test_order_status_state_machine.py` | 7 | 🟢 ⭐ |
| **Notificaciones (servicio)** | `test_notifications_service.py` | 7 | 🟢 |
| **Notificaciones (HTTP)** | `http/test_notifications_fundamentals.py` | 7 | 🟢 |
| **Eventos de dominio** | `test_domain_events_notifications.py` | 6 | 🟢 |
| **Usuarios admin (HTTP)** | `http/test_admin_users_fundamentals.py` | 6 | 🟢 |
| **Constraints de producto** | `test_product_schema_constraints.py` | 5 | 🟢 |
| **Aritmética monetaria** | `test_money_amounts.py` | 5 | 🟢 ⭐ |
| **Middleware CSRF** | `test_csrf_middleware.py` | 5 | 🟢 |
| **Rate limit de login** | `test_auth_login_rate_limit.py` | 5 | 🟢 |
| **Expiración de reservas** | `test_stock_reservations_expiration.py` | 4 | 🟡 Poco para su complejidad |
| **Rate limit de signup** | `test_signup_rate_limit.py` | 4 | 🟢 |
| **Job de reconciliación** | `test_reconcile_pending_payments_job.py` | 4 | 🟡 |
| **Poda de tokens** | `test_prune_auth_action_tokens.py` | 4 | 🟢 |
| **Sweeper de idempotencia** | `test_idempotency_sweeper_job.py` | 4 | 🟢 |
| **Job de expiración** | `test_expire_stock_reservations_job.py` | 4 | 🟢 |
| **Contenido de emails** | `test_email_content.py` | 4 | 🟢 |
| **`token_version`** | `test_auth_token_version.py` | 4 | 🟢 ⭐ |
| **Mantenimiento (HTTP)** | `http/test_maintenance_run.py` | 4 | 🟢 |
| **Flujo de turnos** | `test_turns_flow.py` | 3 | 🟡 |
| **Servicio de mantenimiento** | `test_maintenance_service.py` | 3 | 🟢 |
| **Descuentos por categoría** | `test_discounts_category_scope.py` | 3 | 🟡 |
| **Poda de throttles (job)** | `test_auth_login_throttles_prune_job.py` | 3 | 🟢 |
| **Reservas (HTTP)** | `http/test_stock_reservations_fundamentals.py` | 3 | 🟡 |
| **Idempotencia de checkout guest** | `test_guest_checkout_idempotency.py` | 1 | 🟡 |
| **Poda de throttles (servicio)** | `test_auth_login_throttles_prune.py` | 1 | 🟢 |
| **Fallo del proveedor en checkout** | `http/test_provider_failure_checkout.py` | 1 | 🟠 Escenario crítico con un solo test |

### 2.5 Factories

`tests/factories/` con 7 módulos:

| Módulo | Provee |
|---|---|
| `users.py` | `create_user` — usuarios de test |
| `orders.py` | `create_order_graph` — orden completa con ítems y reservas |
| `http_auth.py` | Helpers de login y cookies |
| `http_catalog.py` | Creación de catálogo vía HTTP |
| `http_checkout.py` | Flujos de checkout vía HTTP |
| `http_payments.py` | Creación y manipulación de pagos |
| `http_webhooks.py` | Construcción de payloads y firmas de webhook |

🟢 Buena separación entre builders de datos (nivel modelo) y helpers HTTP (nivel API).

---

## 3. Estrategia del frontend

### 3.1 Qué se testea

| Archivo | Tests | Qué cubre |
|---|---:|---|
| `lib/cart-storage.test.ts` | 13 | ⭐ Add, update, increment (tope 10), decrement (mínimo 1), remove, count, clear, suscripción |
| `features/admin/hooks/useAdminCategories.test.tsx` | 10 | Crear, renombrar, borrar categorías; validaciones |
| `features/checkout/hooks/useCheckoutPage.test.tsx` | 10 | Checkout guest y autenticado, redirect a MP, conflicto de cuenta registrada |
| `features/checkout/hooks/usePaymentReturnStatus.test.tsx` | 8 | Snapshot, continuar, reintentar, reutilización de la clave de idempotencia |
| `lib/useModalA11y.test.tsx` | 5 | Cierre con Escape, focus trap |
| `features/auth/hooks/useLoginPage.test.tsx` | 5 | Login, mensajes según `location.state.reason`, redirect por rol |

### 3.2 Enfoque

🟢 **Testea hooks, no componentes.** Es coherente con el patrón "hook de página": toda la lógica está en el
hook, así que testearlo cubre el comportamiento sin renderizar árboles enormes.

🟢 **`useLoginPage(login)` recibe la función de login por parámetro** — inversión de dependencias que permite
testear sin montar el `AuthProvider`.

⚠️ **Ningún test de componente.** Nada verifica que un componente renderice lo que debe, que un botón esté
deshabilitado, que un mensaje de error se muestre o que la accesibilidad funcione (más allá de `useModalA11y`).

### 3.3 Setup

```ts
// src/test/setup.ts
import "@testing-library/jest-dom/vitest";
```

```ts
// vitest.config.ts
{ environment: "jsdom", setupFiles: ["./src/test/setup.ts"], globals: true }
```

Mínimo y suficiente.

---

## 4. Huecos críticos {#huecos-críticos}

### 🔴 H-01 — Ningún test verifica la corrección concurrente

**El más importante.** Todo el diseño de concurrencia del sistema depende de `SELECT … FOR UPDATE` e índices
únicos parciales. **En SQLite, `with_for_update()` es un no-op silencioso.**

Escenarios sin cubrir:

| Escenario | Riesgo |
|---|---|
| Dos requests crean un pago para la misma orden simultáneamente | Doble pago pendiente |
| Dos clientes compran la última unidad a la vez | Sobreventa |
| El webhook y el job de reconciliación procesan el mismo pago | Doble consumo de stock |
| Dos admins reembolsan la misma incidencia | Doble reembolso |
| Dos requests de refresh con el mismo token | Sesión inconsistente |

> **Recomendación:** un job de CI adicional con `services: postgres:16` que ejecute un subconjunto de tests de
> concurrencia con hilos reales. Es la mejora de testing con mayor retorno.

### 🔴 H-02 — El panel admin está prácticamente sin tests

7 de 8 hooks sin cobertura, incluidos:

| Hook | Líneas | Riesgo |
|---|---:|---|
| `useAdminSales` | 362 | 🔴 Crea órdenes y cobra dinero |
| `useAdminRegisterPayment` | 300 | 🔴 Contiene la **heurística de unidad monetaria** (§4.8 de [06](06_PanelAdmin.md)) |
| `useAdminCatalog` | 504 | 🟠 Cambia precios y stock |
| `useAdminDiscounts` | 241 | 🟠 Cambia precios efectivos |
| `useAdminPaymentIncidents` | 83 | 🔴 Ejecuta reembolsos |
| `useAdminOrdersPayments` | 119 | 🟡 Solo lectura |
| `useAdminTurns` | 38 | 🟡 Solo lectura |

> 🔴 **`normalizePaymentAmountsForOrder` (`useAdminRegisterPayment.ts:15-45`) es pura y trivial de testear**, y
> decide si un cobro se interpreta en pesos o en centavos. Debería ser el primer test que se escriba.

### 🟠 H-03 — Sin medición de cobertura

Ni `pytest --cov` ni `vitest --coverage`. No se sabe qué porcentaje del código se ejecuta, ni qué ramas quedan
sin tocar. La estimación de este documento es **cualitativa**, por inspección de nombres de test.

### 🟠 H-04 — Sin tests E2E

Nada verifica el flujo completo navegador → frontend → backend → base. Los flujos con más piezas móviles
(checkout con redirect a Mercado Pago y retorno) solo se testean por partes.

### 🟠 H-05 — Servicios críticos sin tests unitarios directos

| Servicio | LOC | Estado |
|---|---:|---|
| `products_s.list_storefront_products` | ~100 | 🟠 Cubierto indirectamente vía HTTP; sin test del camino lento con filtros de precio |
| `orders_s.get_public_order_snapshot_by_payment_token` | 140 | 🟠 Los 4 flags y las 6 razones de bloqueo no tienen matriz de casos |
| `stock_reservations_s._expire_active_reservations_internal` | ~100 | 🟠 Solo 4 tests para reactivación, cancelación y política de máximo |
| `refund_s.create_mercadopago_refund` | ~155 | 🟠 Sin test del camino de fallo con commit dentro del `except` |
| `mercadopago_client` (bucles de reintento) | ~180 | 🟠 Sin test de timeout, 5xx ni respuesta inválida |

### 🟡 H-06 — Sin tests de contrato con el proveedor

Todas las interacciones con Mercado Pago están mockeadas. Nada detecta un cambio en el formato de respuesta del
proveedor hasta que falla en producción.

### 🟡 H-07 — Sin tests de migraciones

Ninguna prueba verifica que `alembic upgrade head` desde cero produzca el mismo esquema que `Base.metadata`, ni
que los `downgrade` funcionen.

### 🟡 H-08 — Sin tests de rendimiento ni de carga

No hay línea base. Los límites de escalabilidad de [12_Performance.md](12_Performance.md#13-escalabilidad-dónde-se-rompe)
son estimaciones, no mediciones.

---

## 5. Lo que está bien testeado 🟢

Vale la pena reconocerlo:

| Área | Por qué está bien |
|---|---|
| **Aritmética monetaria** | `test_money_amounts.py` cubre redondeo half-up, tope del descuento y precio no negativo |
| **Consistencia monetaria de pagos** | `test_payments_money_consistency.py` verifica que el importe cobrado coincide con el total |
| **Máquina de estados de orden** | `test_order_status_state_machine.py` cubre las transiciones válidas e inválidas |
| **Idempotencia de checkout** | Replay con misma clave, conflicto con payload distinto, request en curso |
| **Rate limiting** | Login y signup, con verificación de que el contador persiste tras el error |
| **`token_version`** | Verifica que el refresh invalida el access token anterior |
| **CSRF** | 5 tests sobre orígenes válidos, inválidos y ausentes |
| **Mapeo de errores** | Cada excepción de proveedor a su status HTTP |
| **Backoff de webhooks** | Progresión de delays y dead letter |
| **Carrito (frontend)** | 13 tests sobre todas las operaciones, incluidos los topes |

---

## 6. Prioridades {#prioridades}

| ID | Test faltante | Riesgo que cubre | Esfuerzo | Prioridad |
|---|---|---|---|---|
| <a id="T-01"></a>**T-01** | `normalizePaymentAmountsForOrder` (unitario puro) | 🔴 Cobro con unidad monetaria mal interpretada | 2 h | **P0** |
| <a id="T-02"></a>**T-02** | Job de CI con PostgreSQL real | 🔴 Toda la concurrencia sin verificar | 1 día | **P0** |
| <a id="T-03"></a>**T-03** | Concurrencia: dos pagos simultáneos sobre la misma orden | 🔴 Doble cobro | 4 h | **P0** |
| <a id="T-04"></a>**T-04** | Concurrencia: dos compras de la última unidad | 🔴 Sobreventa | 4 h | **P0** |
| <a id="T-05"></a>**T-05** | `useAdminSales.onSubmit` | 🔴 Venta presencial mal registrada | 1 día | **P1** |
| <a id="T-06"></a>**T-06** | `useAdminPaymentIncidents.resolveWithRefund` | 🔴 Reembolso incorrecto | 4 h | **P1** |
| <a id="T-07"></a>**T-07** | Cobertura en CI con umbral mínimo (60%) | 🟠 Visibilidad | 2 h | **P1** |
| <a id="T-08"></a>**T-08** | Matriz de flags de `get_public_order_snapshot…` | 🟠 UI que muestra el botón equivocado | 1 día | **P1** |
| <a id="T-09"></a>**T-09** | `create_mercadopago_refund` camino de fallo | 🟠 Refund fallido sin registrar | 4 h | **P1** |
| <a id="T-10"></a>**T-10** | Reintentos de `mercadopago_client` (timeout, 5xx, payload inválido) | 🟠 Comportamiento ante proveedor degradado | 1 día | **P2** |
| <a id="T-11"></a>**T-11** | `useAdminCatalog` — cambio de precio de variante | 🟠 Precio mal aplicado | 1 día | **P2** |
| <a id="T-12"></a>**T-12** | Camino lento de `list_storefront_products` | 🟡 Filtros de precio incorrectos | 4 h | **P2** |
| <a id="T-13"></a>**T-13** | E2E con Playwright del checkout completo | 🟠 Flujo end-to-end | 3 días | **P2** |
| <a id="T-14"></a>**T-14** | Tests de componentes de las secciones críticas | 🟡 Regresiones de UI | 3 días | **P3** |
| <a id="T-15"></a>**T-15** | Test de migraciones desde cero | 🟡 Drift de esquema | 4 h | **P3** |
| <a id="T-16"></a>**T-16** | Tests de contrato con Mercado Pago | 🟡 Cambio de formato del proveedor | 2 días | **P3** |
| <a id="T-17"></a>**T-17** | Tests de carga con Locust o k6 | 🟡 Línea base de rendimiento | 3 días | **P3** |

---

## 7. Cómo ejecutar los tests

### Backend
```bash
# desde la raíz del repo, con la venv activa
python -m pytest backend/tests -q                     # todos
python -m pytest backend/tests/http -q                # solo integración
python -m pytest backend/tests/test_money_amounts.py -v
python -m pytest backend/tests -k "idempotency" -v     # por palabra clave
```

🟢 **No requieren PostgreSQL ni un `.env` real**: usan SQLite en memoria y setean las env necesarias con
`setdefault`.

### Frontend
```bash
cd frontend
npm test                          # vitest run (sin watch)
npx vitest                        # modo watch
npx vitest run cart-storage       # por nombre de archivo
npm run build                     # type check + build
npm run lint
```

### CI
`.github/workflows/ci.yml` ejecuta, en cada push a `main` y en cada PR:
1. `ruff check backend` + `python -m pytest backend/tests -q`
2. `python backend/scripts/export_openapi.py` → artifact
3. `npm ci` → `npm run gen:api-types` → **`git diff --exit-code`** → `npm run lint` → `npm run build` →
   `npm test`

---

## 8. Propuesta de job de CI con PostgreSQL

Para cerrar el hueco H-01, sin tocar los tests existentes:

```yaml
  backend-tests-postgres:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: patitas_test
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - run: alembic -c backend/alembic.ini upgrade head
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/patitas_test
      - run: python -m pytest backend/tests -q -m concurrency
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/patitas_test
          JWT_SECRET: ci-test-secret
          ACCESS_TOKEN_EXPIRE_MINUTES: "120"
          MERCADOPAGO_WEBHOOK_SECRET: ci-webhook-secret
```

Los nuevos tests se marcarían con `@pytest.mark.concurrency` para que solo corran en este job.
**Bonus:** este job también verificaría que las migraciones aplican limpias desde cero (cubre H-07).

---

← [15 Configuración](15_Configuracion.md) | [Índice](README.md) | Siguiente: [17 Production Readiness](17_ProductionReadiness.md) →
