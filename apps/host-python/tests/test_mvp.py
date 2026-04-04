from fastapi.testclient import TestClient

from host_mvp.server import app


client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "host-mvp"
    assert "openharness" in body
    assert "status" in body


def test_protocol_version():
    resp = client.get("/protocol/version")
    assert resp.status_code == 200
    assert resp.json()["protocol_version"] == "1"


def test_websocket_bootstrap_and_ping():
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["event_type"] == "host.ready"
        ws.send_json({"type": "ping", "value": "hello"})
        pong = ws.receive_json()
        assert pong["event_type"] == "host.pong"
        assert pong["payload"]["echo"]["value"] == "hello"
