# RiskGraph model artifact

`riskgraph-baseline.joblib` is a reproducible generated binary and is intentionally not tracked in Git. The committed model card and manifest preserve the measured configuration, metrics, byte size, and SHA-256 digest.

Regenerate the artifact from the repository root:

```powershell
$env:PYTHONPATH="src"
python -m flagship_lab.cli risk-benchmark --entities 400 --months 12 --train-through 8 --output-dir artifacts/risk-model-v1
```

The fixed seed is `20260811`. Compare the regenerated file with the SHA-256 value in `manifest.json` before treating it as the documented baseline.
