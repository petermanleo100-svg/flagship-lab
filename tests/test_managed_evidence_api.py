from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from flagship_lab.fastapi_app import create_app
from flagship_lab.object_store import LocalWormObjectStore
from flagship_lab.signing import Ed25519Signer


SECRET = "managed-evidence-api-secret-at-least-32-characters"


def get_token(client, subject, roles, scopes):
    response = client.post("/auth/dev-token", json={"subject": subject, "tenant_id": "alpha",
                           "roles": roles, "resource_scopes": scopes})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_managed_evidence_api_returns_immutable_object_version_headers(tmp_path):
    private = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    app = create_app(str(tmp_path / "api.db"), SECRET, allow_dev_tokens=True,
                     object_store=LocalWormObjectStore(tmp_path / "objects"),
                     evidence_signer=Ed25519Signer(private, "test-key"))
    client = TestClient(app)
    analyst = get_token(client, "alice", ["analyst"], ["*:*:*"])
    client.post("/tax/transactions", json=[{"invoice_id": "E", "seller_tax_id": "S", "buyer_tax_id": "B",
        "invoice_date": "2026-01-01", "amount": "100", "tax_rate": "0.13", "tax_amount": "13", "currency": "CNY"}], headers=analyst)
    run_id = client.post("/tax/runs", json={}, headers=analyst).json()["run_id"]
    reviewer = get_token(client, "bob", ["reviewer"], [f"tax_run:{run_id}:review", f"tax_run:{run_id}:evidence"])
    assert client.post(f"/tax/runs/{run_id}/review", json={"decision": "APPROVE", "comment": "verified evidence"}, headers=reviewer).status_code == 200
    response = client.get(f"/evidence/tax/{run_id}", headers=reviewer)
    assert response.status_code == 200
    assert response.headers["x-evidence-version"] == response.headers["x-evidence-sha256"]
    assert response.content.startswith(b"PK")
