Idempotency Sweeper — Runbook (staging -> production)

⚠️ PENDING DECISIONS — BLOCKING PRODUCTION DEPLOY ⚠️
This runbook is intentionally incomplete below (placeholders <REGISTRY_URL>/<TAG> etc.) until
someone with production infra authority confirms these. Do not deploy to production before
every item here is answered and the placeholders further down are replaced:
- [ ] Registry URL and image tag to use for production.
- [ ] Production namespace name (manifests currently default to `staging`).
- [ ] Desired schedule frequency for prod (cron expression).
- [ ] Production IDEMPOTENCY_PROCESSING_TIMEOUT_MINUTES and IDEMPOTENCY_SWEEPER_LIMIT.
- [ ] Where secrets live in production (K8s Secret, ExternalSecrets, Vault) — see
      backend/k8s_idempotency_sweeper_secret.yaml / _externalsecret.yaml for the current templates.
- [ ] Whether Prometheus scraping / alerting should be added (omitted so far — no
      monitoring integration exists yet for this job).

Once these are answered, replace the placeholders in this file and in
backend/k8s_idempotency_sweeper_cronjob.yaml, then delete this section.

Purpose
- Periodically mark idempotency records stuck in 'processing' past timeout as 'failed'.
- Prune expired completed/failed records.

Artifacts included
- backend/Dockerfile.sweeper  (image build)
- backend/k8s_idempotency_sweeper_secret.yaml  (Secret template)
- backend/k8s_idempotency_sweeper_sa.yaml      (ServiceAccount; sin Role/RoleBinding — el pod recibe
  los secrets via envFrom en el CronJob, no via RBAC de la API de Secrets)
- backend/k8s_idempotency_sweeper_cronjob.yaml (CronJob manifest)

Pre-deploy checklist
1) Confirm production registry and tag: <REGISTRY_URL> and <TAG>.
2) Decide production namespace (default: staging -> change to production)
3) Confirm DATABASE_URL and other envs (MERCADOPAGO_*, etc.). Do NOT store prod secrets in repo — use your secret manager and replace the Secret manifest with extracted values or ExternalSecrets.
4) Backup DB snapshot prior to first prod run.

Build & push image
- cd backend
- docker build -f Dockerfile.sweeper -t <REGISTRY_URL>/patitas/idempotency-sweeper:<TAG> .
- docker push <REGISTRY_URL>/patitas/idempotency-sweeper:<TAG>

Staging run (one-shot)
- kubectl apply -f backend/k8s_idempotency_sweeper_sa.yaml
- kubectl apply -f backend/k8s_idempotency_sweeper_secret.yaml  # or create via secret manager
- kubectl apply -f backend/k8s_idempotency_sweeper_cronjob.yaml
- Create immediate job to test:
  kubectl create job --from=cronjob/idempotency-sweeper idempotency-sweeper-once -n staging
  kubectl logs -f job/idempotency-sweeper-once -n staging

Validation (must pass before promoting)
- Verify only records with created_at <= now - timeout were marked failed.
- Verify response_payloads are sanitized (no tokens/secrets)
- Verify referenced payments/orders still present and consistent
- Confirm logs have no unexpected exceptions
- Metrics: marked_failed/pruned counts within expected baseline

Production rollout
- After 48–168h of stable staging results, schedule production cronjob with conservative limits (--limit 200, timeout 30m) and monitor closely for first 24–72h.
- Keep ability to pause CronJob (kubectl patch cronjob ... suspend=true) and a DB backup to restore if needed.

Monitoring & alerts (recommended)
- Record metrics: sweeper_runs_total, sweeper_run_failure_total, sweeper_marked_failed_total, sweeper_pruned_total.
- Alerts: run failure (critical), marked_failed rate spike (warning), pruned spike.

Rollback and remediation
- If sweeper over-marks: stop CronJob, inspect records, and (if safe) revert using DB snapshot or manually set record.status back to processing/completed as per runbook. Prefer manual fixes for small numbers.

Questions required to finalize production deployment
- See the "PENDING DECISIONS" checklist at the top of this file — kept in one place to avoid drift.
