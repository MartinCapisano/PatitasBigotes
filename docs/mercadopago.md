# MercadoPago — EN PAUSA ('in progress')

← [Índice](README.md) | Método de pago online activo: **[banktransfer.md](banktransfer.md)** | Relacionados: [10 Flujos](10_Flujos.md) · [17 Production Readiness](17_ProductionReadiness.md)

---

## 0. Estado: pausado

> 🟡 **La integración de MercadoPago está pausada y marcada como *'in progress'*.** No es el método de pago del lanzamiento.

**Decisión de negocio:** para salir a producción, el **único método de pago online es la transferencia bancaria con verificación manual del admin** (ver **[banktransfer.md](banktransfer.md)**). Se mantienen además los pagos presenciales en el local y los pagos manuales que registra el admin. MercadoPago queda listo en el código pero **desactivado**, para retomarse más adelante sin tener que rearmar la integración.

**Motivo:** MercadoPago para dinero real arrastra un conjunto de requisitos que, para un comercio chico con pocos clientes, no se justifican todavía (ver §3). La transferencia manual esquiva **todos** esos requisitos: sin webhook, sin reconciliación, sin contracargos, sin timing de acreditación — un humano verifica cada pago contra la cuenta bancaria real.

Este documento cambió de rol: dejó de ser un *checklist de lanzamiento* y pasó a ser el **estado actual + la spec de reactivación**. Cuando se decida retomar MercadoPago, acá está lo que ya funciona (§2) y lo que faltaría cerrar (§3).

---

## 1. Cómo se pausa (mecanismo)

La pausa es un **candado reversible en el backend**, no una demolición. El objetivo es que reactivar MP el día de mañana sea cambiar un flag, no reconstruir nada.

| Pieza | Acción de pausa | Estado tras la pausa |
|---|---|---|
| Inicio de checkout MP | Flag `MERCADOPAGO_ENABLED=false`: el backend **rechaza** iniciar un pago con `method=mercadopago` (`payment_s.py:204`, camino de inicialización del proveedor) | Bloqueado en el servidor, no solo oculto en el frontend |
| Frontend | Ocultar MercadoPago como opción en el checkout | El cliente solo ve transferencia |
| Webhook (`POST /payments/webhook/mercadopago`) | Se deja **vivo pero pasivo** | Si nadie inicia pagos MP, no llegan webhooks; uno perdido hace no-op (no encuentra pago) |
| Jobs (`reconcile_pending_payments_job`, `reprocess_failed_webhooks_job`) | Quedan **inertes** | Sin pagos MP en `pending`, seleccionan cero y no hacen nada |

> 📌 **Reversibilidad:** reactivar MP = poner `MERCADOPAGO_ENABLED=true` y volver a mostrar la opción en el frontend. Nada se borra. **Hipótesis:** no hay pagos MP reales en vuelo (la integración se usó en sandbox/demo), por lo que dejar el webhook pasivo no orfana ningún pago; conviene confirmarlo contra la base antes de reactivar en el futuro.

> ⚠️ El flag `MERCADOPAGO_ENABLED` **todavía no existe en el código** — es parte de la próxima implementación de la pausa. Este documento especifica el *qué*; el *cómo* es trabajo posterior.

---

## 2. Lo que ya está terminado ✅ (base para reactivar)

La lógica de MercadoPago es sólida y quedó completa; se conserva intacta bajo la pausa. Verificado por lectura de código y respaldado por la suite (**121 passed** al momento de escribir este documento).

| Capacidad | Dónde |
|---|---|
| Creación de preferencia con idempotencia hacia el proveedor | `mercadopago_client.py:186` · clave `mp-preference-{idempotency_key}` en `mercadopago_normalization_s.py:242` |
| Validación de URL de checkout (solo `https`, host en allowlist) | `mercadopago_normalization_s.py:197` |
| Recuperación de fallo de setup de la preferencia (`provider_status='setup_failed'` + reintento que recupera solo ese paso) | `payment_provider_s.py:37` · `:99` |
| Webhook: firma HMAC-SHA256 con ventana anti-replay (300 s) | `mercadopago_d.py:38` · `config.py:88` |
| Webhook: deduplicación por `event_key UNIQUE` | `mercadopago_client.py:349` |
| Reintentos ante fallo transiente del proveedor (3 intentos, 0,2 → 0,4 s) | `mercadopago_client.py:140` |
| Normalización de estados del proveedor → estado interno | `mercadopago_normalization_s.py:22` · `:86` |
| Job de reconciliación (webhook que no llegó) | `reconcile_pending_payments_job.py` |
| Cola de reprocesamiento con backoff y dead-letter + replay admin | `reprocess_failed_webhooks_job.py` · `mercadopago_r.py:80` |
| Motor de reembolso (vía incidencia) | `refund_s.py:222` |
| Incidencias de pago tardío / duplicado | `payment_provider_s.py:252` |
| Reintento de pago para invitados | `usePaymentReturnStatus.ts` |
| Consistencia de monto y moneda contra el pago del proveedor | `payment_provider_s.py:207` |

---

## 3. Requisitos para reactivar MP (no bloquean el lanzamiento actual)

Estos tres huecos eran, cuando MP iba a ser el método de lanzamiento, **bloqueantes de dinero real**. Con el pivote a transferencia **dejan de bloquear el lanzamiento** y quedan como *deuda a saldar el día que se reactive MercadoPago*. Se dejan documentados para no perderlos.

### 3.1 Aviso cuando el cron de mantenimiento se cae + visibilidad del dead-letter
Con MP activo, la confirmación de un pago cuyo webhook falló depende del cron de mantenimiento (dispara reconciliación y reprocesamiento). Si el cron se cae y nadie lo nota, hay pagos que nunca se confirman: **pérdida silenciosa**. Para reactivar MP hace falta una alerta si el cron falla y visibilidad del dead-letter para el admin. Ver [17_ProductionReadiness.md §4.5](17_ProductionReadiness.md).

> Con transferencia manual este riesgo **no aplica**: no hay webhook ni reconciliación; el admin confirma cada pago mirando su cuenta.

### 3.2 Medios de pago offline: vencimiento de preferencia + ventana de reconciliación
La preferencia no restringe medios (`mercadopago_normalization_s.py:232`), así que quedan habilitados Rapipago / Pago Fácil / efectivo, que acreditan en días. Pero el vencimiento de la preferencia es de 60 min (`payment_s.py:67`, tope `le=1440`) y la ventana de reconciliación es de 24 h (`reconcile_pending_payments_job.py:20`). Para reactivar MP **con** medios offline hay que mover los tres valores de forma coherente (vencimiento de preferencia → días, subir el tope del schema, ampliar `PAYMENTS_RECONCILE_MAX_AGE_HOURS`), o bien **excluir** los medios offline y quedarse solo con tarjeta / dinero en cuenta.

### 3.3 Estados `refunded` / `partially_refunded` / `charged_back` no mapeados
El mapa `MERCADOPAGO_PROVIDER_TO_INTERNAL_STATUS` (`mercadopago_normalization_s.py:22`) no cubre reembolsos ni contracargos. Con MP activo, un reembolso desde el panel o una disputa caería en dead-letter mientras el pago sigue figurando `paid`. Para reactivar MP: tratamiento defensivo reusando `PaymentIncident` (nuevo tipo `provider_refund_detected` / `chargeback_detected`), marcando el webhook como procesado. **Hipótesis:** conviene confirmar contra la doc de MP si estos estados llegan como `topic=payment` o en un topic aparte.

---

## 4. Configuración de MP (solo relevante al reactivar)

No hace falta setear nada de esto mientras MP esté en pausa. Para reactivar: credenciales productivas, `MERCADOPAGO_ENV=production`, webhook secret real, URLs reales, cuenta MP habilitada, y `MERCADOPAGO_ENABLED=true`. Plantilla: `backend/.env.production.example:57`.

---

## 5. Checklist de reactivación (futuro)

- [ ] Flag `MERCADOPAGO_ENABLED=true`
- [ ] Mostrar MercadoPago como opción en el checkout del frontend
- [ ] Confirmar que no hay pagos MP en vuelo antes de reactivar
- [ ] Aviso de cron caído + visibilidad de dead-letter (§3.1)
- [ ] Decidir medios offline sí/no y ajustar vencimiento + ventana en consecuencia (§3.2)
- [ ] Manejo defensivo de `refunded` / `partially_refunded` / `charged_back` (§3.3)
- [ ] Credenciales productivas, webhook secret, URLs reales (§4)

---

## 6. Referencias

- **[banktransfer.md](banktransfer.md)** — el método de pago online **activo**.
- [10_Flujos.md](10_Flujos.md) — flujos de checkout, webhook, reconciliación, incidencia y reembolso.
- [17_ProductionReadiness.md](17_ProductionReadiness.md) — capa operativa; origen del requisito §3.1.
- [19_Glosario.md](19_Glosario.md#relojes-del-pago-los-tres) — *Relojes del pago (los tres)*.
