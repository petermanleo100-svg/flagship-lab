# Phase 3 governance evidence

## Scope

This phase strengthens governance and validation without claiming production deployment or real-world fraud performance.

## TaxFlow review and signed evidence

- A rule run created through FastAPI enters `PENDING_REVIEW`.
- The requester cannot approve or reject their own run.
- A decision is final and is appended to the cross-module SHA-256 audit chain.
- Evidence export is blocked until approval.
- The ZIP includes `run.json`, `findings.json`, `review.json`, `audit_events.json`, per-file SHA-256 hashes, a manifest hash, and an HMAC-SHA256 signature with key identifier.
- Verification uses constant-time signature comparison and reports missing, mismatched, or tampered content separately.

## ControlPulse case lifecycle

- Allowed transitions are `OPEN → IN_REVIEW → REMEDIATED → CLOSED`; a closed case may be reopened.
- Every transition requires an actor and reason.
- The actor responsible for the source event cannot independently close the resulting case.
- Transition history is immutable and each transition is also written to the audit hash chain.

## RiskGraph entity-disjoint validation

Fixed command:

```powershell
$env:PYTHONPATH="src"
python -m flagship_lab.cli risk-benchmark --entities 400 --months 12 --train-through 8 --output-dir work/risk-model-phase3
```

Observed fixed-seed results:

- Standard temporal holdout: PR-AUC `0.862674`, ROC-AUC `0.922464`, Recall@Top5% `0.837209`.
- Entity-disjoint temporal holdout: 299 train entities, 101 test entities, entity leakage count `0`.
- Entity-disjoint result: PR-AUC `0.869943`, ROC-AUC `0.894092`.
- Maximum feature PSI: `0.054440`; no feature crossed the documented `0.25` high-drift threshold.

All data are synthetic. These figures verify implementation and evaluation discipline; they are not estimates of real business performance.

## Automated verification

`pytest -q` result: `20 passed`.

Coverage includes independent review, final decisions, signed-package verification, wrong-key rejection, tamper detection, valid/invalid case transitions, independent closure, entity leakage, PSI output, RBAC, event replay, and Alembic roundtrip.
