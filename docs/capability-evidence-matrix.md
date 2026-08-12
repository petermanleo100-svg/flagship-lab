# Capability–evidence matrix

This file is the release truth source. A capability may be described as **implemented** only when the listed automated evidence passes on the release commit. Roadmap items must not be presented as current behavior.

| Capability | State | Runtime implementation | Verification evidence | Production boundary |
|---|---|---|---|---|
| Unified SQLAlchemy transaction path | Implemented | `core.py` and all four domain services | full test suite; raw-SQL audit | SQLite remains a local adapter; PostgreSQL is the production target |
| Exact monetary arithmetic | Implemented | `Numeric(20,4)`, `Numeric(9,6)`, Decimal rule evaluation | `test_decimal_values_round_trip_without_binary_float_drift` | Currency-specific minor-unit policy is not yet configurable |
| Tenant-scoped domain data | Implemented | tenant key on every operational table; request services bind JWT tenant | `test_api_enforces_tenant_isolation_for_tax_findings_and_audit` | Database row-level security is roadmap; isolation is application-enforced |
| Tamper-evident audit chain | Implemented | per-tenant SHA-256 chain; PostgreSQL advisory lock | audit-chain unit tests and tenant isolation test | Hash chaining detects mutation; it is not immutable storage |
| Four-eyes tax review and control closure | Implemented | independent actor validation and optimistic version updates | governance lifecycle tests | Identity proof depends on configured token verifier |
| Reliable event delivery | Implemented with limitation | transactional outbox, PostgreSQL `SKIP LOCKED`, Kafka adapter, bounded retry, DLQ/replay and transactional consumer receipts | outbox and `test_messaging_reliability.py` | Live broker integration and operational replay authorization remain deployment work |
| Signed immutable evidence | Implemented with limitation | EvidenceService, Ed25519/KMS signer boundary, local create-only WORM and S3 Object Lock compliance adapter | evidence tamper, storage and adapter contract tests | Cloud integration credentials and retention governance are deployment responsibilities |
| OIDC/JWKS and RBAC authentication | Implemented with limitation | pluggable verifier; RS256/ES256 JWKS, issuer/audience/expiry/role/tenant validation; HS256 dev mode | API RBAC tests and `test_oidc_auth.py` | Provider discovery/group mapping and key-rotation integration test remain deployment work |
| Regulation retrieval | Implemented | versioned corpus, lexical + char-TFIDF retrieval, refusal and citations | analytics evaluation tests | Distributed vector index and ingestion crawler are roadmap |
| Risk graph explainability | Implemented | tenant graph persistence, shared-account and 3-cycle rules | graph tests | Large-graph engine and analyst case workflow are roadmap |
| Liveness/readiness/metrics | Implemented with limitation | separate probes, bounded-label Prometheus counters/durations, security headers | readiness and observability tests | Distributed traces, dashboards and SLO alerts are roadmap |
| PostgreSQL runtime CI | Implemented | SQLAlchemy models, psycopg runtime and dedicated service job | `test_postgres_runtime_decimal_tenant_and_audit`; GitHub CI PostgreSQL 17 | Migration-chain execution on PostgreSQL is added in the next hardening batch |
| Idempotent tax writes | Implemented | transaction-scoped request hash and response record for ingest/rule-run endpoints | `test_tax_write_idempotency_replays_and_rejects_key_reuse` | Other write endpoints use natural keys or remain roadmap |
| Resource-scoped authorization | Implemented with limitation | signed `type:id:action` scopes plus role and tenant enforcement | `test_resource_authorization.py` | Central policy administration and relationship-based grants remain roadmap |
| OpenTelemetry and SLO alerts | Roadmap | request ID, structured log formatter, metrics and Server-Timing only | observability test | no trace exporter, collector, dashboard or alert rules |
| Container deployment baseline | Implemented with limitation | non-root image, read-only API filesystem, dropped capabilities, migration gate, PostgreSQL health check | GitHub CI image build and non-root inspection | orchestration, backup/restore drill and secret manager integration remain deployment work |
| Enterprise operations workbench | Implemented with limitation | API readiness, tenant dev login, idempotent tax import/run, review, findings, control and audit views | Vite production build | Production OIDC redirect flow, pagination and full case/evidence workflows remain roadmap |

## Release audit rules

1. Every README feature statement must map to an **Implemented** or **Implemented with limitation** row.
2. A test name is evidence only when it runs in CI without skip or expected failure.
3. A schema model alone is not evidence of endpoint behavior.
4. “Enterprise-grade” describes a target architecture until the PostgreSQL, identity, observability, deployment and recovery rows are verified.
