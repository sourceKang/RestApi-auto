from __future__ import annotations

import pytest


@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.readwrite
def test_remote_console_read_command(services, readwrite_session):
    services.remote.verify_read_command(readwrite_session)


@pytest.mark.remoteconsole
@pytest.mark.destructive
@pytest.mark.noaccess
def test_remote_console_noaccess_rejected(services, noaccess_session):
    services.remote.verify_noaccess_rejected(noaccess_session)
