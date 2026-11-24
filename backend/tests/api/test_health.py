def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_docs_available(client):
    assert client.get("/openapi.json").status_code == 200
