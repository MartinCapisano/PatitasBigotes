# Runbook — Restaurar la base de datos desde un backup

← [17 Production Readiness](../17_ProductionReadiness.md) · Hogar de runbooks: `docs/runbooks/`

---

## Cuándo usar esto

La base de Supabase se corrompió, se borró, o el proyecto se perdió, y hay que
reconstruirla desde el último backup. Los backups los toma
[`.github/workflows/db-backup.yml`](../../.github/workflows/db-backup.yml): un
`pg_dump` lógico diario (`--format=custom`) que se sube como artifact de GitHub y
**se verifica restaurándolo en cada corrida** (paso *Verify restore*). Que la
verificación esté en verde es la garantía de que el dump de hoy es restaurable.

## Objetivos (RPO / RTO)

| Métrica | Valor | Por qué |
|---|---|---|
| **RPO** (pérdida máxima de datos) | **24 h** | El dump corre 1×/día (04:00 UTC). Se pierde lo escrito desde el último dump. |
| **RTO** (tiempo de recuperación) | **~15–30 min** (estimado) | Provisionar/ vaciar Supabase + `pg_restore` + cambiar `DATABASE_URL` + redeploy. El **`pg_restore` en sí** se mide en cada corrida del workflow (`restore_duration_seconds` en los logs). |

> Reducir el RPO por debajo de 24 h requiere PITR → paso a **Supabase Pro** (docs/17 §6). No está en el free tier.

## Precondiciones

- `pg_restore`/`psql` v17 (mismo cliente que usa el workflow: `postgresql-client-17` del repo PGDG).
- La `DATABASE_URL` del destino, con las dos particularidades del proyecto:
  - Esquema **`postgresql+psycopg://`** para la app (psycopg 3). Para `pg_restore` a mano usás
    la URI Postgres normal (`postgresql://…`), sin el `+psycopg`.
  - **Session pooler** de Supabase (host `*.pooler.supabase.com`, puerto **5432**, user
    `postgres.<ref>`). Render free no tiene salida IPv6 y la conexión directa de Supabase es IPv6;
    el Transaction pooler (6543) rompe `pg_restore`/prepared statements. Ver docs/17 §11.1.

## Procedimiento

```bash
# 1. Bajar el último dump desde el run del workflow "Supabase DB backup":
#    GitHub → Actions → Supabase DB backup → run más reciente en verde →
#    Artifacts → "supabase-backup" (diario) o "supabase-backup-monthly" (día 01).
#    Descomprimir el .zip del artifact para obtener patitas_backup_YYYYMMDDTHHMMSSZ.dump

# 2. Preparar el destino: un proyecto Supabase nuevo, o vaciar el existente.
#    Tener a mano su connection string (Session pooler, ver Precondiciones).
DEST_URL="postgresql://postgres.<ref>:<password>@<host>.pooler.supabase.com:5432/postgres"

# 3. Restaurar. --clean --if-exists deja el destino en el estado del dump aunque
#    tuviera objetos previos. --no-owner --no-privileges evita depender de roles.
pg_restore --no-owner --no-privileges --clean --if-exists \
           -d "$DEST_URL" patitas_backup_YYYYMMDDTHHMMSSZ.dump

# 4. Verificar (mismos checks que hace el workflow, más un vistazo a los datos):
psql "$DEST_URL" -c "SELECT version_num FROM alembic_version;"   # 1 fila, la migración head
psql "$DEST_URL" -c "SELECT count(*) FROM orders;"               # datos presentes
psql "$DEST_URL" -c "SELECT count(*) FROM users;"

# 5. Apuntar la app al destino y redeployar:
#    Render → Environment → DATABASE_URL = postgresql+psycopg://<misma URI, con +psycopg>
#    → Manual Deploy (o esperar el próximo deploy). Confirmar /health/ready en verde.
```

## Notas y riesgos aceptados

- **Restore verificado, no manual.** Cada backup se prueba restaurando en el propio workflow;
  no dependemos de una prueba manual única que envejece. Si esa verificación falla, el workflow
  abre un issue (`backup-failure`).
- **Riesgo aceptado: un solo lugar.** Los dumps viven únicamente en artifacts de GitHub (privados,
  cifrados at-rest por GitHub). **Perder la cuenta/repositorio de GitHub = perder los backups.**
  El offsite a otro proveedor y el PITR se difieren a Supabase Pro (docs/17 §5/§6).
- **Retención**: diario 30 días + copia mensual (día 01) 90 días. Un incidente descubierto tarde
  se puede recuperar hasta ~90 días atrás solo si cae dentro de una copia mensual.
