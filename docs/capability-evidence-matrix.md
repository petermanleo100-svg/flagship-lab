# Capability–evidence matrix

This file is the release truth source. A capability may be described as **implemented** only when the listed automated evidence passes on the release commit. Roadmap items must not be presented as current behavior.

| Capability | State | Runtime implementation | Verification evidence | Production boundary |
|---|---|---|---|---|
| Unified SQLAlchemy transaction path | Implemented | `core.py` and all four domain services | full test suite; raw-SQL audit | SQLite remains a local adapter; PostgreSQL is the production target |
| Exact monetary arithmetic | Implemented | `Numeric(20,4)`, `Numeric(9,6)`, Decimal rule evaluation | `test_decimal_values_round_trip_without_binary_float_drift` | Currency-specific minor-unit policy is not yet configurable |
| Tenant-scoped domain data | Implemented | tenant key on every operational table; request services bind JWT tenant | `test_api_enforces_tenant_isolation_for_tax_findings_and_audit` | Database row-level security is roadmap; isolation is application-enforced |
| Tamper-evident audit chain | Implemented | per-tenant SHA-256 chain; PostgreSQL advisory lock | audit-chain unit tests and tenant isolation test | Hash chaining detects mutation; it is not immutable storage |
| Four-eyes tax review and control closure | Implemented | independent actor validation and optimistic version updates | governance lifecycle tests | Identity proof depends on configured token verifier |
| Transactional outbox + publisher | Implemented with limitation | same-transaction persistence, ordered batches, PostgreSQL `SKIP LOCKED`, retry counter | `test_outbox.py` | At-least-once semantics; concrete Kafka/AMQP adapter and dead-letter operations remain roadmap |
| Signed evidence ZIP | Implemented with limitation | tenant-filtered manifest, file hashes, Ed25519 public-key verification; legacy HMAC compatibility | evidence tamper tests and `test_ed25519_evidence_signature_is_publicly_verifiable` | KMS custody and object-lock storage are roadmap |
| RBAC bearer authentication | Implemented with limitation | signed JWT claims, issuer/audience/expiry/role/tenant checks | API RBAC and token tests | Current verifier uses shared-secret HS256; OIDC/JWKS is roadmap |
| Regulation retrieval | Implemented | versioned corpus, lexical + char-TFIDF retrieval, refusal and citations | analytics evaluation tests | Distributed vector index and ingestion crawler are roadmap |
| Risk graph explainability | Implemented | tenant graph persistence, shared-account and 3-cycle rules | graph tests | Large-graph engine and analyst case workflow are roadmap |
| Liveness/readiness | Implemented | separate live and DB-backed ready endpoints | readiness test | Metrics/traces/alerts are roadmap |
| PostgreSQL runtime CI | Implemented | SQLAlchemy models, psycopg runtime and dedicated service job | `test_postgres_runtime_decimal_tenant_and_audit`; GitHub CI PostgreSQL 17 | Migration-chain execution on PostgreSQL is added in the next hardening batch |
| Idempotent tax writes | Implemented | transaction-scoped request hash and response record for ingest/rule-run endpoints | `test_tax_write_idempotency_replays_and_rejects_key_reuse` | Other write endpoints use natural keys or remain roadmap |
| OIDC/JWKS and resource ABAC | Roadmap | none | none | HS256 RBAC only |
| Object storage, KMS signatures | Roadmap | none | none | local filesystem + HMAC only |
| Broker-backed async workers | Roadmap | outbox persistence only | none | no publisher/consumer SLA |
| OpenTelemetry and SLO alerts | Roadmap | request ID and Server-Timing only | header test | no collector/dashboard/alert rules |

## Release audit rules

1. Every README feature statement must map to an **Implemented** or **Implemented with limitation** row.
2. A test name is evidence only when it runs in CI without skip or expected failure.
3. A schema model alone is not evidence of endpoint behavior.
4. “Enterprise-grade” describes a target architecture until the PostgreSQL, identity, observability, deployment and recovery rows are verified.
