from app.modules.tts.engines import gsvi_v2


def test_local_gsvi_transport_ignores_inherited_proxy_environment():
    assert gsvi_v2._local_session.trust_env is False

