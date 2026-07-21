# Diagramas

53 diagramas Mermaid extraídos de la documentación, disponibles como archivos `.mmd` independientes para
reutilizar, editar o renderizar por separado.

Cada diagrama vive **también** embebido en su documento de origen. Estos archivos son la copia suelta.

---

## Cómo renderizarlos

| Método | Comando / acción |
|---|---|
| **VS Code** | Extensión *Markdown Preview Mermaid Support* o *Mermaid Editor* |
| **Web** | Pegar el contenido en [mermaid.live](https://mermaid.live) |
| **CLI a SVG** | `npx -p @mermaid-js/mermaid-cli mmdc -i er-diagram.mmd -o er-diagram.svg` |
| **CLI a PNG** | `npx -p @mermaid-js/mermaid-cli mmdc -i er-diagram.mmd -o er-diagram.png -w 2400` |
| **Todos a SVG** | `for f in *.mmd; do npx -p @mermaid-js/mermaid-cli mmdc -i "$f" -o "${f%.mmd}.svg"; done` |

---

## Catálogo

### Arquitectura

| Archivo | Tipo | Documento | Qué muestra |
|---|---|---|---|
| `arquitectura-general.mmd` | flowchart | [01](../01_Resumen.md) | Vista de una pantalla: cliente → SPA → API → servicios → DB + externos |
| `capas-completas.mmd` | flowchart | [02](../02_Arquitectura.md) | Las 8 capas con todos sus módulos |
| `vista-por-capas.mmd` | flowchart | [21](../21_MapaDependencias.md) | Las capas en pila, con los jobs entrando transversalmente |
| `decision-sesion-transaccional.mmd` | flowchart | [02](../02_Arquitectura.md) | Árbol de decisión: ¿qué dependencia de sesión usar en un endpoint nuevo? |
| `despliegue-produccion.mmd` | flowchart | [02](../02_Arquitectura.md) | GitHub + Vercel + Render + Supabase + Mercado Pago |
| `contrato-openapi.mmd` | flowchart | [02](../02_Arquitectura.md) | Cómo el backend genera los tipos del frontend y CI valida el drift |
| `arquitectura-frontend.mmd` | flowchart | [02](../02_Arquitectura.md) | main → App → Layout → páginas → hooks → servicios |
| `arbol-componentes-frontend.mmd` | flowchart | [05](../05_Frontend.md) | Árbol de componentes con guards y rutas |

### Dependencias

| Archivo | Tipo | Documento | Qué muestra |
|---|---|---|---|
| `grafo-dependencias-backend.mmd` | flowchart | [21](../21_MapaDependencias.md) | Grafo completo: 12 routers, 27 servicios, 6 jobs, núcleo |
| `dependencias-servicios.mmd` | flowchart | [02](../02_Arquitectura.md) | Solo los servicios, con los imports diferidos punteados |
| `grafo-dependencias-frontend.mmd` | flowchart | [21](../21_MapaDependencias.md) | Módulos del frontend + eventos `CustomEvent` |
| `dependencias-transitivas.mmd` | flowchart | [14](../14_Dependencias.md) | Dependencias transitivas de los paquetes de Python |
| `throttle-multiproposito.mmd` | flowchart | [20](../20_DiccionarioObjetos.md) | Los 15 usos de `auth_login_throttles` |

### Base de datos y estados

| Archivo | Tipo | Documento | Qué muestra |
|---|---|---|---|
| `er-diagram.mmd` | erDiagram | [08](../08_BaseDatos.md) | ⭐ Las 17 tablas con columnas, tipos, relaciones y restricciones |
| `estados-orden.mmd` | stateDiagram | [08](../08_BaseDatos.md) | `draft → submitted → paid \| cancelled` |
| `estados-orden-reglas.mmd` | stateDiagram | [09](../09_ReglasNegocio.md) | Igual, anotado con las reglas de cada transición |
| `estados-pago.mmd` | stateDiagram | [08](../08_BaseDatos.md) | Estados del pago, incluida la excepción *paid revival* |
| `estados-reserva-stock.mmd` | stateDiagram | [08](../08_BaseDatos.md) | Reserva: activa → consumida / liberada / expirada / reactivada |
| `ciclo-reserva-stock.mmd` | stateDiagram | [09](../09_ReglasNegocio.md) | Ídem con la política de reactivación única |
| `ciclo-idempotency-record.mmd` | stateDiagram | [20](../20_DiccionarioObjetos.md) | `processing → completed \| failed` + recuperación |
| `jerarquia-excepciones.mmd` | classDiagram | [04](../04_Backend.md) | Las 10 excepciones y su status HTTP |
| `mapa-conceptual-objetos.mmd` | flowchart | [20](../20_DiccionarioObjetos.md) | Objetos persistidos, en memoria, del frontend y conceptuales |

### Flujos de negocio

| Archivo | Tipo | Documento | Qué muestra |
|---|---|---|---|
| `flujo-registro.mmd` | sequence | [10](../10_Flujos.md) | Alta de cuenta, incluido el *upgrade* de invitado |
| `flujo-verificacion-email.mmd` | sequence | [10](../10_Flujos.md) | Consumo del token de un solo uso |
| `flujo-login.mmd` | sequence | [10](../10_Flujos.md) | Rate limit → autenticación → par de tokens → cookies |
| `flujo-refresh-sesion.mmd` | sequence | [10](../10_Flujos.md) | Refresh automático con rotación de `token_version` |
| `flujo-catalogo.mmd` | sequence | [10](../10_Flujos.md) | Storefront con los dos caminos de paginación |
| `flujo-agregar-carrito.mmd` | sequence | [10](../10_Flujos.md) | Todo en el cliente, sin tocar el servidor |
| `flujo-checkout-guest.mmd` | sequence | [10](../10_Flujos.md) | ⭐ El flujo más complejo, de punta a punta |
| `flujo-checkout-guest-idempotencia.mmd` | flowchart | [07](../07_API.md) | ⭐ Los 4 caminos de idempotencia del checkout guest |
| `flujo-checkout-autenticado.mmd` | sequence | [10](../10_Flujos.md) | Los 3 requests secuenciales y sus puntos de fallo |
| `flujo-webhook-pago.mmd` | sequence | [10](../10_Flujos.md) | ⭐ Confirmación del pago de punta a punta |
| `secuencia-webhook-mercadopago.mmd` | sequence | [07](../07_API.md) | Versión centrada en la validación de firma y deduplicación |
| `secuencia-crear-pago.mmd` | sequence | [02](../02_Arquitectura.md) | Crear un pago desde el frontend hasta Mercado Pago |
| `flujo-retorno-mercadopago.mmd` | sequence | [10](../10_Flujos.md) | Snapshot público, continuar y reintentar |
| `flujo-reconciliacion-pagos.mmd` | sequence | [10](../10_Flujos.md) | El job que cierra el círculo si el webhook no llegó |
| `flujo-expiracion-reservas.mmd` | sequence | [10](../10_Flujos.md) | Expiración, reactivación y cancelación automática |
| `flujo-reembolso.mmd` | sequence | [10](../10_Flujos.md) | Incidencia → decisión del admin → refund en el proveedor |
| `flujo-venta-admin.mmd` | sequence | [10](../10_Flujos.md) | Venta de mostrador con supresión de email |
| `flujo-registro-pago-admin.mmd` | sequence | [10](../10_Flujos.md) | Confirmación manual de una transferencia |
| `flujo-administracion-catalogo.mmd` | sequence | [10](../10_Flujos.md) | CRUD de productos y variantes desde el panel |

### Panel admin

| Archivo | Tipo | Documento | Qué muestra |
|---|---|---|---|
| `panel-admin-secciones.mmd` | flowchart | [06](../06_PanelAdmin.md) | Los 2 modos y las 9 secciones |
| `panel-admin-hooks.mmd` | flowchart | [06](../06_PanelAdmin.md) | `AdminPage` → 7 hooks → servicios |
| `flujo-venta-mostrador.mmd` | flowchart | [06](../06_PanelAdmin.md) | Pasos del operador al registrar una venta |
| `flujo-incidencia-pago.mmd` | flowchart | [06](../06_PanelAdmin.md) | Decisión de reembolsar o no |
| `interceptor-refresh-401.mmd` | flowchart | [05](../05_Frontend.md) | Lógica del interceptor de axios ante un 401 |

### Operación y calidad

| Archivo | Tipo | Documento | Qué muestra |
|---|---|---|---|
| `pipeline-ci.mmd` | flowchart | [15](../15_Configuracion.md) | Los 3 jobs de GitHub Actions |
| `pipeline-deploy.mmd` | flowchart | [17](../17_ProductionReadiness.md) | Push → CI / Render / Vercel (en paralelo) |
| `estrategia-testing.mmd` | flowchart | [16](../16_Testing.md) | Integración HTTP vs unitarios + factories |
| `cold-start-render.mmd` | gantt | [12](../12_Performance.md) | Los 30–60 s del despertar, con y sin ping |
| `camino-escalado.mmd` | flowchart | [17](../17_ProductionReadiness.md) | Los 5 pasos para salir del free tier |
| `plan-remediacion-seguridad.mmd` | gantt | [11](../11_Seguridad.md) | Los 15 hallazgos ordenados por prioridad |
| `sprint-0-p0.mmd` | gantt | [18](../18_Roadmap.md) | Los 9 ítems P0 en ~3 días |
| `matriz-impacto-esfuerzo.mmd` | quadrantChart | [18](../18_Roadmap.md) | ⭐ Priorización visual de las 25 acciones principales |
| `ruta-onboarding-5-dias.mmd` | flowchart | [22](../22_IndiceLectura.md) | El plan de lectura de 5 días |

---

## Los 5 diagramas imprescindibles

Si solo mirás cinco:

1. **`er-diagram.mmd`** — el modelo de datos completo
2. **`flujo-checkout-guest.mmd`** — el camino crítico del negocio
3. **`flujo-webhook-pago.mmd`** — cómo se confirma el dinero
4. **`estados-reserva-stock.mmd`** — el subsistema más sutil
5. **`grafo-dependencias-backend.mmd`** — cómo encaja todo

---

← [Volver al índice de la documentación](../README.md)
