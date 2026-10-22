from __future__ import annotations

import pytest


@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.readwrite
@pytest.mark.testlink_case("EMS1-6652", "test_post_remote_console")
def test_remote_console_read_command(services, readwrite_session):
    services.remote.verify_read_command(readwrite_session)


@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.noaccess
@pytest.mark.testlink_case("EMS1-7022", "test_post_remote_console_invalid_param_should_return_error")
def test_remote_console_noaccess_rejected(services, noaccess_session):
    services.remote.verify_noaccess_rejected(noaccess_session)
