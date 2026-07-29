from __future__ import annotations

from tests.support.options import session_cache_enabled


class FakeConfig:
    def __init__(self, value):
        self.value = value

    def getoption(self, _name):
        return self.value


def test_session_cache_mode_defaults_to_on_and_respects_explicit_off():
    assert session_cache_enabled(FakeConfig("on"))
    assert session_cache_enabled(FakeConfig("ON"))
    assert not session_cache_enabled(FakeConfig("off"))
    assert session_cache_enabled(FakeConfig(None))
