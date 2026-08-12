from fastapi.testclient import TestClient

from flagship_lab.fastapi_app import create_app


def test_metrics_security_headers_and_bounded_route_labels(tmp_path):
    app = create_app(str(tmp_path / "metrics.db"), "observability-test-secret-at-least-32-characters")
    client = TestClient(app)
    response = client.get("/health/live", headers={"X-Request-ID": "trace-1"})
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"
    metrics = client.get("/metrics").text
    assert 'flagship_http_requests_total{method="GET",route="/health/live",status="200"} 1' in metrics
