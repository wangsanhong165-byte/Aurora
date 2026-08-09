from app.bridge.server import _is_allowed_client_origin, parse_bind_address


def test_runtime_websocket_accepts_only_the_resolved_local_ui_origin(monkeypatch):
    monkeypatch.setenv("BRIDGE_PORT", "19306")
    monkeypatch.setenv("FRONTEND_PORT", "19573")

    assert _is_allowed_client_origin("") is True
    assert _is_allowed_client_origin("http://127.0.0.1:19306") is True
    assert _is_allowed_client_origin("http://localhost:19573") is True
    assert _is_allowed_client_origin("http://127.0.0.1:9528") is False
    assert _is_allowed_client_origin("https://malicious.example") is False


def test_bridge_accepts_the_explicit_endpoint_resolved_by_the_supervisor():
    assert parse_bind_address([
        "--host", "127.0.0.1", "--port", "19306",
    ]) == ("127.0.0.1", 19306)
