from app.bridge.server import _is_allowed_client_origin


def test_runtime_websocket_accepts_only_the_local_ui_origin():
    assert _is_allowed_client_origin("") is True
    assert _is_allowed_client_origin("http://127.0.0.1:9528") is True
    assert _is_allowed_client_origin("http://localhost:5173") is True
    assert _is_allowed_client_origin("https://malicious.example") is False
