import os

from fastapi.testclient import TestClient

os.environ.setdefault("DEEPSEEK_BASE_URL", "https://example.invalid/v1")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

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


def test_deepseek_env_alias_mapping_visible_in_health():
    resp = client.get("/health")
    body = resp.json()
    llm = body["openharness"]["llm"]
    assert llm["llm"]["provider"] == "deepseek-openai-compatible"
    assert llm["llm"]["api_format"] == "openai"
    assert llm["llm"]["base_url_env"] == "DEEPSEEK_BASE_URL"
    assert llm["llm"]["api_key_env"] == "DEEPSEEK_API_KEY"
    assert llm["applied_aliases"]["OPENHARNESS_BASE_URL"] == "DEEPSEEK_BASE_URL"
    assert llm["applied_aliases"]["OPENAI_API_KEY"] == "DEEPSEEK_API_KEY"


def test_websocket_bootstrap_and_ping():
    with client.websocket_connect("/ws") as ws:
        msg = ws.receive_json()
        assert msg["event_type"] == "host.ready"
        ws.send_json({"type": "ping", "value": "hello"})
        pong = ws.receive_json()
        assert pong["event_type"] == "host.pong"
        assert pong["payload"]["echo"]["value"] == "hello"
