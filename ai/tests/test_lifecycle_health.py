from app.lifecycle.health import HealthProbe
from app.lifecycle.manifest import Service


class _Response:
    def __init__(self, status: int, body: bytes = b"{}"):
        self.status = status
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self._body


def _service(*, readiness: bool = False) -> Service:
    return Service(
        name="voice",
        host="127.0.0.1",
        port=19205,
        health="/ready",
        readiness=readiness,
        command={"module": "voice"},
    )


def test_configured_health_endpoint_must_return_200(monkeypatch):
    monkeypatch.setattr(
        "app.lifecycle.health.request.urlopen",
        lambda *_args, **_kwargs: _Response(404),
    )

    assert HealthProbe().ready(_service()) is False


def test_readiness_endpoint_must_confirm_model_is_ready(monkeypatch):
    monkeypatch.setattr(
        "app.lifecycle.health.request.urlopen",
        lambda *_args, **_kwargs: _Response(200, b'{"ready": false}'),
    )

    assert HealthProbe().ready(_service(readiness=True)) is False
