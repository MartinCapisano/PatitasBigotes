# ADR 0001 — Organización de servicios por vista de consumidor

- **Estado:** Aceptada
- **Fecha:** 2026-07-21
- **Alcance:** `backend/source/services/` — dominios `products`, `orders`, `payments`

---

## Contexto

Tres archivos de servicio concentraban la mayor parte de la lógica de negocio del backend:

| Archivo | Líneas | Funciones |
|---|---|---|
| `payment_s.py` | 1132 | 27 |
| `products_s.py` | 954 | 43 |
| `orders_s.py` | 950 | 27 |

El problema no era el tamaño en sí — el promedio es de ~22 líneas por función, no hay funciones
monstruosas. El problema era la **densidad de responsabilidades sin fronteras visibles**: cada archivo
mezclaba varias vistas del negocio en un solo namespace plano, sin ninguna señal de dónde empieza y
termina un flujo ni qué función es entrada pública.

La consecuencia concreta era la imposibilidad de auditar duplicación. Ejemplo real de `products_s.py`:

- `_compute_min_var_price()` (línea 46) calculaba el precio mínimo **sin descuentos**.
- `_build_storefront_product_pricing()` (línea 175) calculaba el precio mínimo **con descuentos**.

Dos respuestas distintas a "¿cuánto sale este producto?", separadas por 130 líneas, con nombres que no
se parecen. Para responder "¿el storefront y el admin cotizan igual?" había que leer las 43 funciones.

`users_s.py` (314 líneas, 6 funciones públicas, un solo tema) se dejó explícitamente fuera del alcance.

## Decisión

Partir los tres dominios **por vista de consumidor**, no por sub-entidad, y solo donde el código
presenta una costura real.

| Dominio | Archivos | Costura |
|---|---|---|
| products | `products_s.py` + `products_storefront_s.py` | storefront público vs catálogo administrado |
| orders | `orders_s.py` + `orders_public_s.py` | público anónimo vs autenticado |
| payments | `payment_s.py` + `payment_core_s.py` + `payment_provider_s.py` | kernel vs proveedor vs ciclo de vida |

Convención de nombres: **dominio primero** (`products_storefront_s`, no `storefront_products_s`), para
que `ls services/` deje los archivos de un mismo dominio adyacentes. Se conserva el sufijo `_s`.

Además, `read_session_scope` / `write_session_scope` — que solo existían en `products_s.py` pero son
manejo de ciclo de vida de sesión, no lógica de producto — se movieron a `source/db/session.py`.

### Por qué cada dominio se parte distinto

Esta es la parte que sorprende al leer el resultado, y la razón principal de este ADR.

**products** — el corte lo dictaron los propios routers: `storefront_r.py` importa exactamente 3
funciones, las 3 storefront; `products_r.py` no importa ninguna de ellas. El bloque storefront tiene
serialización y cálculo de precios propios y no toca ningún helper del bloque admin. La costura ya
existía en el código, solo no estaba en el filesystem.

El remanente de ~550 líneas **no se partió**. No tiene una costura real: `create_variant` toca stock,
`update_product` toca catálogo, `decrement_stock` lo llama `orders_s`. Cortarlo obligaría a inventar
una frontera y a cruzar imports entre los pedazos.

**orders** — se partió por *público anónimo vs autenticado*, **no** por *usuario vs admin*, aunque el
eje lo sugeriría. El código dice que usuario y admin no son dos vistas sino una:
`create_admin_sale` y `create_manual_submitted_order` llaman ambos a `_create_submitted_order_for_user`;
`change_order_status` valida transiciones que aplican a los dos. Separarlos habría producido un archivo
"admin" importando media docena de privados del archivo "usuario" — un archivo partido al medio, no una
frontera.

En cambio `get_public_order_snapshot_by_payment_token` construye su propio dict completo sin usar
`_order_to_dict`: un bloque autocontenido de ~180 líneas. Ese sí es un corte limpio.

**payments** — no tenía ningún bloque autocontenido. Todo lo contrario: `_payment_to_dict` se usaba en
18 lugares de todos los grupos, `_serialize_provider_payload` en 6. Existía un núcleo compartido por
todo, y `payment_admin_queries_s.py` ya importaba `_payment_to_dict` — el repo ya había empezado a
partir payments y ya pagaba el precio de exportar un privado.

Por eso el kernel se extrajo **primero y deliberadamente**, no como sobra. El caso central es
`apply_order_paid_transition`: la función donde una orden pasa a pagada, es decir el punto por el que
entra la plata, estaba escondida como privada en la línea 138 de un archivo de 1132, con dos llamadores
(webhook en la línea 488, confirmación manual en la 1041) invisibles entre sí. Ahora tiene nombre
público, archivo propio y sus dos llamadores son evidentes.

## Alternativas consideradas

**Partir por sub-entidad** (producto | variante | categoría | stock). Descartada: habría dejado
`_compute_min_var_price` y `_build_storefront_product_pricing` **en el mismo archivo** — ambas son
"producto" — sin resolver nada. La divergencia que motivaba el refactor corre sobre el eje de
consumidor, no sobre el de entidad.

**Paquetes con fachada** (`services/products/__init__.py` re-exportando todo). Descartada por dos
razones: reconstruye exactamente el namespace plano del que se quería escapar — si el call-site sigue
diciendo `from ...products import list_storefront_products`, sigue sin saberse en qué mitad del dominio
está parado — y crea un segundo lugar que mantener sincronizado. Con solo 16 call-sites en total entre
los tres dominios, el ahorro no compensaba. Se espera 2–3 archivos por dominio, no 6.

**No tocar payments.** Descartada: es el archivo más grande y el que esconde la lógica más crítica.

## Consecuencias

**A favor:**

- La divergencia legítima se vuelve visible y auto-explicativa. "¿Por qué hay dos precios mínimos?"
  ahora tiene una respuesta obvia: son dos vistas del negocio, y están en dos archivos que lo dicen.
- `webhook_events_s.py` y `payment_admin_queries_s.py` dejan de importar privados con guion bajo; pasan
  a consumir API legítima de `payment_core_s`.
- El punto de entrada del dinero (`apply_order_paid_transition`) es nombrable y rastreable.

**En contra:**

- La lógica de variantes queda repartida entre `products_s.py` y `products_storefront_s.py`. Un cambio
  al modelo de variantes toca dos archivos.
- Los tres dominios se parten con criterios distintos. Sin este ADR, la organización parece arbitraria.
- `payment_core_s.py` lleva un nombre de advertencia: un archivo "core" es la señal clásica de que no se
  encontró la frontera real y se agrupó "lo que sobra compartido". **Si crece más allá de ~350 líneas,
  este ADR debe revisarse** — sería evidencia de que el corte de payments falló.

**Deuda explícitamente no tocada** (para no violar la disciplina de puro movimiento):

- CS-15 — sufijo `_s` ambiguo entre `schemas/` y `services/`.
- Plural inconsistente: `payment_s` (singular) vs `orders_s` / `products_s` (plural).
- CS-03 — `HTTPException` filtrándose desde los servicios.

## Notas de implementación

El refactor se ejecutó como **puro movimiento de código**: ningún bug arreglado, ninguna simplificación
aplicada durante los commits de movimiento. Esa disciplina es lo que hace verificable la garantía de
"no se perdió ninguna función", mediante comparación de inventario AST antes/después.

El plan de ejecución detallado está en [`../refactor-servicios-plan.md`](../refactor-servicios-plan.md).
