# Enterprise pilot release checklist

- [ ] CI backend, PostgreSQL, frontend and container jobs pass on the exact release commit.
- [ ] CodeQL passes for Python and JavaScript/TypeScript on the exact release commit.
- [ ] Dependency update findings are reviewed; critical/high vulnerabilities have no unapproved exception.
- [ ] CODEOWNERS review covers migrations, identity/authorization, signing, evidence and recovery changes.
- [ ] OIDC issuer, audience, tenant, roles, resource scopes and signing-key rotation are tested with the customer IdP.
- [ ] Request-serving database role is non-owner and `NOBYPASSRLS`; direct SQL tenant attacks pass.
- [ ] Alembic upgrade, latest downgrade and re-upgrade pass against a production-like database copy.
- [ ] Concurrent idempotency/audit-chain tests and clean PostgreSQL restore pass without skip.
- [ ] Object Lock retention and KMS signer verification pass with deployment credentials.
- [ ] Kafka delivery, consumer receipts, dead-letter authorization and replay are exercised with the deployment broker.
- [ ] OTLP traces and SLO alerts reach named operational owners; readiness failure pages the correct team.
- [ ] Logical restore and managed PostgreSQL PITR meet customer-approved RPO/RTO in a recorded drill.
- [ ] Synthetic end-to-end tax, regulation, control and evidence workflows pass before real data admission.
- [ ] Capability matrix, README and applicant materials contain no claim beyond release evidence.
