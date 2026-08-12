# Environment acceptance record

This blank record is a template, not evidence of a completed drill. Store the completed copy outside the repository with immutable timestamps and approvals.

## Release identity

- Repository and commit SHA:
- Candidate artifact SHA-256 / image digest:
- Environment and region:
- Change ticket:
- Started / completed (UTC):
- Executor / independent reviewer:

## Admission evidence

- Preflight command and redacted JSON result:
- Runtime database role; NOSUPERUSER/NOBYPASSRLS/non-owner verified:
- Alembic expected/observed revision:
- Forced-RLS table count:
- OIDC issuer/audience and rotation test reference:
- Backup-key secret version (never the key):
- CI, CodeQL, SBOM, vulnerability and attestation run URLs:

## Recovery and isolation drill

- Backup/PITR recovery point and isolated target:
- Restore start/end, measured RPO/RTO and approved targets:
- Row-count/business readback and audit/evidence-chain result:
- Cross-tenant direct-SQL and API attack results:
- Synthetic post-restore transaction result:

## Alert and rollback drill

- Alert rule/test notification/recipient/acknowledgement time:
- Readiness dependency failure result:
- Rollback or forward-fix rehearsal and duration:
- Residual findings, owner and due date:

## Decision

- Decision: approved / rejected
- Business owner:
- Security owner:
- Operations owner:
- Signatures or approval-record links:

