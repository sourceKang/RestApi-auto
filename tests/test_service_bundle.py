from __future__ import annotations

from automation.domains.alarm import AlarmService
from automation.domains.auth_matrix import AuthMatrixService
from automation.domains.invalid_params import InvalidParamsService
from automation.domains.inventory import InventoryService
from automation.domains.profile import ProfileService
from automation.domains.provision import ProvisionService
from automation.domains.remote import RemoteService
from automation.domains.session import UserSessionService
from automation.pytest_plugin.service_bundle import build_service_bundle


def test_build_service_bundle_groups_domain_services():
    api_client = object()
    env_config = object()

    services = build_service_bundle(api_client, env_config)

    assert isinstance(services.alarm, AlarmService)
    assert isinstance(services.auth_matrix, AuthMatrixService)
    assert isinstance(services.invalid_params, InvalidParamsService)
    assert isinstance(services.inventory, InventoryService)
    assert isinstance(services.profile, ProfileService)
    assert isinstance(services.provision, ProvisionService)
    assert isinstance(services.remote, RemoteService)
    assert isinstance(services.user_session, UserSessionService)
