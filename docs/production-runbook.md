# Production operations runbook

This runbook describes the verified application controls. Cloud account provisioning, PostgreSQL WAL archiving, DNS, certificates and regional failover remain infrastructure responsibilities.

## Identity and database roles

- API workload: OIDC/JWKS enabled; development token endpoint disabled; PostgreSQL `NOSUPERUSER NOBYPASSRLS` role.
- Migration owner: schema DDL only; never used by the API.
- Backup and Outbox worker: separately credentialed and audited operational roles. Cross-tenant work requires explicit `BYPASSRLS` approval.
- Every API token requires `tenant_id`, roles and resource scopes in `type:id:action` form.

## Evidence custody

Production uses `S3ObjectLockStore` with bucket versioning and Object Lock enabled in compliance mode. Configure an asymmetric KMS key through `AwsKmsSigner`; do not mount private key material. Verify retention policy and KMS key rotation in the cloud change record before release.

## Backup and restore drill

Set a 32-byte backup key through a secret manager and expose it only for the operation:

```bash
export FLAGSHIP_BACKUP_KEY_BASE64='<base64 secret>'
export FLAGSHIP_DATABASE_URL='<audited backup role URL>'
export FLAGSHIP_OPERATIONS_STORE='/retained/backup/store'
flagship-operations backup-create nightly-2026-08-12 --retention-days 30
flagship-operations backup-restore /retained/backup/store/backup-nightly-2026-08-12.restore.json --target-url '<clean restore database URL>'
```

Success requires `valid: true`, exact per-table counts and valid audit chains for every tenant. Execute a synthetic post-restore transaction before recording the drill as passed. Logical backup complements PostgreSQL WAL/PITR; test both at least quarterly.

## Outbox and dead letters

Run `flagship-worker` with Kafka idempotence and `acks=all`. Alert on unpublished events approaching `max_attempts` and any new dead letter. Inspect and replay only after resolving the cause:

```bash
flagship-operations dlq-list
flagship-operations dlq-replay 42
```

Replayed events retain the original stable event ID. Consumers must use `IdempotentConsumer` receipts in the same transaction as business effects.

## Observability and incident response

The API exports OTLP traces and Prometheus metrics. Deploy `deploy/otel-collector.yaml`, route the collector to the approved backend, and load `deploy/prometheus/flagship-alerts.yml`. A database failure must make `/health/ready` return 503 while `/health/live` remains available. Do not restart-loop a healthy process when only a dependency is unavailable.

## Release gates

1. Alembic upgrade, downgrade of the latest revision and re-upgrade pass.
2. Backend, frontend, non-root container and PostgreSQL jobs pass on the release commit.
3. PostgreSQL concurrent idempotency/audit, RLS attack and clean restore tests pass without skip.
4. [`capability-evidence-matrix.md`](capability-evidence-matrix.md) contains no claim without executable evidence.
5. CodeQL passes for Python and JavaScript/TypeScript; dependency and security-sensitive CODEOWNERS reviews are resolved.
6. Complete [`release-checklist.md`](release-checklist.md) on the exact release commit and attach environment-specific approvals separately.
