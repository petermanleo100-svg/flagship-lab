from fastapi.testclient import TestClient

from flagship_lab.fastapi_app import create_app


SECRET = "resource-authorization-secret-at-least-32-characters"


def token(client, subject, roles, scopes):
    response = client.post("/auth/dev-token", json={"subject": subject, "tenant_id": "alpha",
                           "roles": roles, "resource_scopes": scopes})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_same_tenant_subject_cannot_read_ungranted_tax_run(tmp_path):
    client = TestClient(create_app(str(tmp_path / "abac.db"), SECRET, allow_dev_tokens=True))
    analyst = token(client, "owner", ["analyst"], ["*:*:*"])
    client.post("/tax/transactions", json=[{"invoice_id": "A", "seller_tax_id": None,
                "buyer_tax_id": "B", "invoice_date": "2026-01-01", "amount": "100",
                "tax_rate": "0.13", "tax_amount": "13", "currency": "CNY"}], headers=analyst)
    run_id = client.post("/tax/runs", json={}, headers=analyst).json()["run_id"]
    restricted = token(client, "limited-reviewer", ["reviewer"], ["tax_run:another-run:read"])
    denied = client.get(f"/tax/findings?run_id={run_id}", headers=restricted)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "resource_access_denied"
    granted = token(client, "assigned-reviewer", ["reviewer"], [f"tax_run:{run_id}:read"])
    assert client.get(f"/tax/findings?run_id={run_id}", headers=granted).status_code == 200
