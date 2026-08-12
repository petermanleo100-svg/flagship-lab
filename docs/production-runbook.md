# Production operations runbook

This runbook describes the verified application controls. Cloud account provisioning, PostgreSQL WAL archiving, DNS, certificates and regional failover remain infrastructure responsibilities.

## Identity and database roles

- API workload: OIDC/JWKS enabled; development token endpoint disabled; PostgreSQL `NOSUPERUSER NOBYPASSRLS` role.
- Migration owner: schema DDL only; never used by the API.
- Backup and Outbox worker: separately credentialed and audited operational roles. Cross-tenant work requires explicit `BYPASSRLS` approval.
- Every API token requires `tenant_id`, roles and resource scopes in `type:id:action` form.

For local Compose, set distinct `POSTGRES_OWNER_PASSWORD` and `POSTGRES_APP_PASSWORD` values and use a fresh database volume; role bootstrap runs only on initial database creation. In managed PostgreSQL, the DBA must create equivalent identities and grants. Run `flagship-operations preflight` as the runtime identity and require secret-free `valid: true` output before traffic admission. Compose runs Alembic as the owner, then repeats this preflight before starting the API.

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

CI validates Prometheus rule syntax with `promtool`. Notification routing and a test page to each named owner remain deployment acceptance gates. Container CI retains an SPDX JSON SBOM for 30 days and blocks vulnerabilities that are both Critical and have a known fix. Review unfixed Critical findings explicitly; do not describe them as remediated. Provenance attestation is reserved for a tagged image publication workflow because ordinary CI images are not release artifacts.

The `release-image` workflow separates proof from publication. Manual dispatch creates a 14-day candidate archive, SHA-256 checksum and SBOM, then records GitHub provenance and SBOM attestations without creating a registry image. Only a `vX.Y.Z` tag publishes the exact commit to `ghcr.io/<owner>/flagship-lab`, captures its immutable digest, and attaches provenance plus SBOM attestations. Complete the release checklist before tagging; verify with `gh attestation verify oci://ghcr.io/<owner>/flagship-lab:vX.Y.Z -R <owner>/flagship-lab`.

## Release gates

1. Alembic upgrade, downgrade of the latest revision and re-upgrade pass.
2. Backend, frontend, non-root container, PostgreSQL and full Compose smoke jobs pass on the release commit.
3. PostgreSQL concurrent idempotency/audit, RLS attack and clean restore tests pass without skip.
4. [`capability-evidence-matrix.md`](capability-evidence-matrix.md) contains no claim without executable evidence.
5. CodeQL passes for Python and JavaScript/TypeScript; dependency and security-sensitive CODEOWNERS reviews are resolved.
6. Complete [`release-checklist.md`](release-checklist.md) on the exact release commit and attach environment-specific approvals separately.
