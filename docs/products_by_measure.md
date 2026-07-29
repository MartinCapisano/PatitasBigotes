# products_by_measure — Plan de implementación

Venta de **productos por cantidad / peso** (500 g de alimento, X ml de jabón, etc.), con confirmación de disponibilidad del encargado **antes** de cobrar, para no tener que devolver plata.

---

## 1. Contexto y problema

- Hoy el catálogo solo vende **unidades enteras discretas**: `ProductVariant.stock`, `price`, `OrderItem.quantity` y `StockReservation.quantity` son `Integer` con `CHECK > 0`. No existe unidad de medida en ninguna capa.
- Para estos productos la **disponibilidad real no es confiable** (peso variable, se fracciona a mano) y el negocio **cobra por transferencia al confirmar la orden**. Si el cliente transfiere y no hay stock, hay que **devolver dinero**. Esa fricción es la que se elimina.

## 2. Flujo objetivo (UX)

1. **Ficha del producto por cantidad:** el cliente elige la cantidad (en la medida, p. ej. gramos), ve el precio de esa cantidad ("500 g = $X") y aparece **"Agregar al carrito"** con un **aviso** breve: *"Este producto se vende por cantidad; tu pedido se confirmará con el local antes de abonar."*
2. El ítem **entra al carrito normal**, marcado como "por cantidad".
3. **En finalizar compra**, si la orden contiene algún ítem por cantidad, **no aparece la opción de pagar** (evita que el cliente pague algo que quizá no tenemos). En su lugar aparece **"Comprobar disponibilidad"**.
4. **"Comprobar disponibilidad"** abre WhatsApp con **toda la orden y sus detalles** (ítems normales + por cantidad, cantidades, precios, total estimado, datos de contacto del cliente).
5. El **admin de turno**, por WhatsApp: confirma tener el producto por cantidad, aprovecha a verificar los demás ítems, habla con el cliente si hace falta, y **crea la orden** con el flujo de venta admin que ya existe. A partir de ahí **retoma el flujo normal**: el cliente recibe el email con CBU/alias/detalles y abona.

## 3. Principios de diseño — qué NO se toca

- **El sistema de pagos y la máquina de estados de la orden no cambian.** La orden pagable la crea el admin y sigue el camino de siempre (transferencia → email de instrucciones → confirmación manual del pago). Sin gate de pago, sin estado nuevo de "revisión", sin bifurcación de pagos. En particular, **`payment_s` no se toca**.
- El motor de reservas (`stock_reservations_s`) recibe un ajuste **acotado**: reconocer que las líneas por medida **no son inventario finito** (ver §4.3). No cambia el comportamiento de los productos normales.

## 4. Modelo

### 4.1 "Pasos de una medida" (mantiene todo entero)
La variante por medida se vende en **pasos**: `quantity=1` = un paso. Ej. paso = 100 g ⇒ 500 g es `quantity=5`, `price` = precio por 100 g, `line_total = 5 × price`. Así `quantity`/`price` siguen enteros y no se decimaliza nada. Solo cambia la **presentación** ("500 g" en vez de "5") y la **carga en admin**.

### 4.2 Disponibilidad por `is_active` (sin stock numérico) — decisión del usuario
Estos productos **no manejan un stock numérico** (no se lleva "1 kg disponible"). La disponibilidad la administra el encargado con el flag **`is_active` que ya existe** en `ProductVariant`:
- `is_active = True` ⇒ **disponible**.
- `is_active = False` ⇒ **"sin stock"**, pero el producto **se sigue mostrando** en la página (no desaparece).

**Divergencia respecto de hoy (y por qué):** para un producto normal, una variante `is_active=False` queda oculta del storefront (`active_variant_count > 0`) y su detalle da 404 (RN-CAT-01/02). Para los productos **por medida** queremos lo contrario: mostrarlos igual, marcados "sin stock". Por eso la reutilización de `is_active` (que antes habíamos descartado por ser un flag de *visibilidad*) se acepta **acotada a `sold_by='measure'`**: solo estas variantes cambian su semántica de visibilidad; las normales siguen igual.

**Consecuencia:** para un producto por medida no hay estado "oculto"; el "off" es "sin stock". Para sacarlo del todo, se borra el producto.

### 4.3 Reservas de stock para productos por medida (el punto delicado)
El motor de reservas asume **stock numérico finito**, y estos productos no lo tienen. Sin cuidado, rompe en dos lugares:
1. **Al reservar:** `_available_stock_for_variant` calcula `disponible = stock − reservas`; con `stock = 0` da `insufficient stock` y el alta de la orden falla.
2. **Al vencer/reactivar:** el job de expiración vuelve a llamar `_available_stock_for_variant`, que filtra `is_active = True`; si el admin marcó el producto "sin stock" (`is_active=False`) con una orden impaga, tira `variant not found` y **rompe la expiración** (que procesa en lote).

**Solución — tratar las líneas por medida como "no limitadas por stock"**, con un check `sold_by='measure'` en las tres funciones de `stock_reservations_s.py` (sin inventar un stock centinela):
1. `_available_stock_for_variant`: para variantes por medida, **retorno temprano** "sin límite" (no depende del número ni de `is_active`). ⇒ la reserva siempre se crea y la reactivación nunca bloquea ni rompe.
2. `consume_reservations_for_paid_order`: para líneas por medida, marcar la reserva `consumed` **sin** el compare-and-swap de descuento (no hay número que bajar).
3. `reserve_stock_for_submitted_order`: a las reservas por medida darles un `expires_at` **sin vencimiento** (fecha centinela lejana) ⇒ el job de expiración **nunca las procesa**.

Con esto se mantiene **RN-PAY-02 intacto** (la línea por medida igual tiene una reserva *activa*, así que el pago se permite) **sin tocar `payment_s`**. En **órdenes mixtas**, las líneas normales conservan su reserva real de 42 h y gobiernan el auto-cancel; las por medida quedan exentas. Una orden **100% por medida** no se auto-cancela por vencimiento (la cancela el admin a mano) — ver punto abierto en §8.

---

## 5. Fase 1 — Backend: modelo, migración, DTOs, serializers y reservas

### 5.1 Modelo (`backend/source/db/models.py`, `ProductVariant` ~línea 76)
Agregar columnas:
- `sold_by` (String, NOT NULL, default `'unit'`, server_default `'unit'`; valores `unit | measure`).
- `measure_unit` (String, nullable — p. ej. `"g"`, `"ml"`).
- `step` (Integer, NOT NULL, default 1, server_default `1` — unidades de `measure_unit` por paso).

En `__table_args__`, sumar (doble defensa, patrón de los `CHECK` existentes):
- `CHECK (step > 0)` — `ck_product_variants_step_positive`
- `CHECK (sold_by IN ('unit','measure'))` — `ck_product_variants_sold_by_valid`
- `CHECK (sold_by = 'unit' OR measure_unit IS NOT NULL)` — `ck_product_variants_measure_unit_present`

`is_active` y `stock` ya existen; no se agregan. Para variantes por medida `stock` queda sin uso (0); la disponibilidad es `is_active` (§4.2) y la exención de reservas (§4.3) evita que el `0` moleste.

### 5.2 Migración
- Nueva revisión `backend/alembic/versions/20260727_01_add_variant_measure_fields.py`, `down_revision = "20260718_01"` (head actual). `op.add_column` de las 3 columnas (con `server_default`) + `op.create_check_constraint` de los 3 checks; `downgrade` inverso.
- **No tocar `backend/alembic/schema_snapshot.py`** (congelado por diseño; los cambios van en revisiones nuevas).
- Los tests construyen el esquema con `Base.metadata.create_all` (no con Alembic), así que los campos del modelo ya los cubren; la migración es para producción.

### 5.3 DTOs (`backend/source/schemas/products_s.py`)
`CreateVariantRequest` / `UpdateVariantRequest` / `PatchVariantRequest`: agregar `sold_by: Literal["unit","measure"]` (default `"unit"`), `measure_unit: str | None` (default None, `max_length` ~16), `step: int` (default 1, `gt=0`). `model_validator(mode="after")`: si `sold_by == "measure"` ⇒ `measure_unit` no vacío. El `stock` de la request se ignora para measure.

### 5.4 Servicios de catálogo (`backend/source/services/products_s.py`)
- `_variant_to_dict`: exponer `sold_by`, `measure_unit`, `step`, e `in_stock` derivado (`= is_active` para measure).
- `create_variant` / `update_variant`: persistir/validar los campos nuevos (sumarlos a `allowed_fields`); para measure, no gestionar `stock` numérico (queda 0).

### 5.5 Serializer storefront (`backend/source/services/products_storefront_s.py`) — la divergencia de §4.2
- `_variant_to_storefront_dict` / `_variant_to_storefront_option`: exponer `sold_by`/`measure_unit`/`step`; para measure, `in_stock = is_active` (no `stock > 0`).
- `list_storefront_products`: hoy el subquery filtra `is_active.is_(True)` y exige `active_variant_count > 0`. Ampliar para que una variante cuente como "listable" si `is_active = True` **o** `sold_by = 'measure'`, de modo que los productos por medida aparezcan aunque estén "sin stock". Los normales no cambian.
- `get_storefront_product_by_id` + `_build_storefront_product_pricing`: incluir las variantes por medida **aunque estén inactivas** (no 404, y calcular el precio para mostrar "500 g = $X" con la marca "sin stock"). Productos normales, intactos.

### 5.6 Línea de orden (para que la orden/comprobante muestre "500 g")
- `backend/source/services/orders_s.py::_order_to_dict` (ítem): incluir `sold_by`/`measure_unit`/`step` desde `item.variant`.
- `backend/source/schemas/orders_s.py::OrderItemResponse`: sumar los mismos campos (el DTO es `extra="forbid"` y espeja `_order_to_dict`; deben quedar en sync o rompe la serialización).

### 5.7 Guarda de seguridad en el checkout del cliente
En los caminos de **checkout self-service** (`POST /checkout` y `POST /checkout/guest`), rechazar ítems cuya variante sea `sold_by='measure'` con un error de negocio estable (p. ej. `"measure products require availability confirmation"`). Defensa en profundidad: aunque la UI no ofrezca pagar, un request armado a mano no debe cobrar un producto por medida. **`create_admin_sale` SÍ debe permitirlos.**

### 5.8 Reservas de stock (`backend/source/services/stock_reservations_s.py`) — ver §4.3
Los tres ajustes acotados a `sold_by='measure'`:
1. `_available_stock_for_variant`: retorno temprano "sin límite" para measure.
2. `consume_reservations_for_paid_order`: marcar `consumed` sin el compare-and-swap para líneas measure.
3. `reserve_stock_for_submitted_order`: `expires_at` sin vencimiento (centinela lejano) para reservas measure.

Definir la constante del centinela de vencimiento (p. ej. `NON_EXPIRING_RESERVATION_AT`) junto a las demás constantes del módulo.

---

## 6. Fase 2 — Frontend: storefront + carrito + checkout

### 6.1 Carrito (`frontend/src/lib/cart-storage.ts`)
- `CartItem`: agregar `sold_by`/`measure_unit`/`step` (y guardar `quantity` en pasos). Helpers `hasMeasureItems(cart)` y `formatQuantity(item)` → `"500 g"` vs `"2 u."`.
- `incrementCartItem`/`updateCartItemQuantity`: para ítems por medida, moverse de a `step` y **sin el tope de 10**.

### 6.2 Ficha de producto (`frontend/src/features/storefront/hooks/useProductDetailPage.ts` + `pages/ProductDetailPage.tsx`)
- Tipo de `option` (`frontend/src/features/storefront/types.ts` / tipos de `StorefrontProductDetail`): agregar `sold_by`/`measure_unit`/`step` (`in_stock` ya viene, ahora derivado de `is_active` para measure).
- Si la opción es `sold_by='measure'` y está **disponible** (`in_stock`): **selector de cantidad en la medida** (input con `step`), **precio en vivo** ("500 g = $X", más "$X / 100 g"), y botón **"Agregar al carrito" con el aviso**. `onBuy` agrega con la cantidad elegida (en pasos), no fija en 1.
- Si `sold_by='measure'` y **sin stock** (`is_active=False`): mostrar el producto marcado **"Sin stock"**, con el botón de agregar **deshabilitado**.

### 6.3 Checkout (`frontend/src/features/checkout/hooks/useCheckoutPage.ts` + `pages/CheckoutPage.tsx`)
- Si `hasMeasureItems(cart)`: **ocultar el pago** y mostrar **"Comprobar disponibilidad"**. Banner explicando que el pedido se confirma con el local antes de abonar.
- El botón abre `wa.me` con un mensaje que incluye **toda la orden**: cada ítem (nombre, cantidad formateada, precio), total estimado y datos de contacto del cliente.

### 6.4 Util WhatsApp (`frontend/src/lib/whatsapp.ts`, nuevo)
- `buildWhatsappUrl(number, message)` (espejo del patrón backend `bank_transfer_s.py::build_whatsapp_receipt_url`).
- `buildAvailabilityMessage(cart, customer?)` que arma el texto de la orden completa.

### 6.5 Config del número
El número vive en backend (`db/config.py::get_whatsapp_number`). Exponerlo al front con `VITE_WHATSAPP_NUMBER` (usada por `lib/whatsapp.ts`) y documentarlo en el `.env.example` del frontend.

---

## 7. Fase 3 — Admin

- **Editor de catálogo** (`CatalogSection.tsx` y el flujo de variantes): al crear/editar una variante permitir setear `sold_by`/`measure_unit`/`step` + precio por paso. Para `sold_by='measure'`, **ocultar el campo de stock numérico** y mostrar un toggle **"Disponible / Sin stock"** mapeado a `is_active`. Para productos normales, el editor no cambia.
- **Armado de la orden** (`useAdminSales` / `POST /admin/sales`): ya recibe `variant_id` + `quantity` (en pasos) y calcula `line_total` solo; agregar el **formateo** de la línea por medida ("500 g", precio por unidad). Tras crear la orden con transferencia, el cliente recibe el email de instrucciones (`email_s.py::send_bank_transfer_instructions_email`) y abona — flujo normal.

---

## 8. Puntos abiertos (decidir al implementar)

- **Auto-cancelación de órdenes 100% por medida:** con la exención de reservas (§4.3) no se auto-cancelan por vencimiento. ¿Se deja así (el admin cancela a mano) o se agrega una expiración propia para limpiar impagas viejas? Recomendado: dejarla abierta.
- **Categoría "Productos por cantidad":** opcional, solo para navegación; el comportamiento lo maneja el flag `sold_by`, no el nombre de la categoría.
- **Variante mixta a nivel producto:** se asume que un producto por medida tiene variantes por medida (no se mezcla `unit` y `measure` en el mismo producto). Confirmar antes de implementar la UI de opciones. (Distinto de las **órdenes** mixtas, que sí se soportan.)

## 9. Verificación

- **Backend (pytest, `backend/tests/`):**
  - (a) crear/editar variante `sold_by='measure'` con validación de `measure_unit`/`step`.
  - (b) `create_admin_sale` con línea por medida: calcula `line_total = pasos × precio_por_paso`, la reserva se crea sin vencimiento, y al pagar la reserva pasa a `consumed` **sin** tocar `stock`.
  - (c) **expiración robusta:** una orden con línea por medida cuya variante se marcó `is_active=False` **no rompe** `expire_active_reservations`; una orden mixta expira/cancela por sus líneas normales sin afectar la línea por medida.
  - (d) el checkout self-service **rechaza** variantes por medida.
  - (e) **storefront:** un producto por medida con `is_active=False` **aparece** en listado/detalle marcado sin stock (no 404), y con `is_active=True` aparece disponible; un producto normal con variante inactiva **sigue oculto**.
  - Correr toda la suite de órdenes/stock/pagos para confirmar que el flujo existente no cambió.
- **Frontend (preview + vitest):** ficha de un producto por medida disponible (selector + precio en vivo + aviso + agregar) y uno "sin stock" (agregar deshabilitado); en checkout con ítem por medida **no** aparece pagar sino "Comprobar disponibilidad", y el `wa.me` lleva toda la orden; formateo "500 g" en carrito y checkout.
- **Migración:** aplicar `20260727_01` sobre una copia y confirmar arranque (el deploy corre `alembic upgrade` en el `buildCommand`).

## 10. Orden sugerido de trabajo
Fase 1 (backend, base de todo) → Fase 2 (storefront + carrito + checkout, la experiencia visible) → Fase 3 (admin: carga y armado de orden).
