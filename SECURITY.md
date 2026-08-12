# Security and data handling

Flagship Lab is a portfolio project that uses synthetic data. Do not upload
real invoices, employee records, credentials, client documents, or other
sensitive information.

For local use, replace `FLAGSHIP_JWT_SECRET` with a random value of at least 32
characters. Development tokens must remain disabled outside local demos.

Production identity uses OIDC/JWKS and separately managed workload identities.
The request-serving PostgreSQL role must be a non-owner with `NOBYPASSRLS`.
Secrets, evidence signing keys and backup keys must be supplied by the deployment
secret manager; they must never be committed or baked into container images.

Dependency update automation and CodeQL are release evidence, not a substitute
for customer threat modelling, penetration testing, infrastructure hardening or
incident-response approval. Security-sensitive paths have explicit CODEOWNERS;
protect `main` so those reviews and required checks cannot be bypassed.

If you discover a vulnerability, report it privately to the repository owner
instead of opening a public issue containing exploit details or sensitive data.
