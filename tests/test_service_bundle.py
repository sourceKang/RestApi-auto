from __future__ import annotations

from services.alarm import AlarmService
from services.auth_matrix import AuthMatrixService
from services.invalid_params import InvalidParamsService
from services.inventory import InventoryService
from services.neox_config import NeoXConfigService
from services.profile import ProfileService
from services.provision import ProvisionService
from services.remote import RemoteService
from services.session import UserSessionService
from tests.support.service_bundle import build_service_bundle


def test_build_service_bundle_groups_domain_services():
    api_client = object()
    env_config = object()

    services = build_service_bundle(api_client, env_config)

    assert isinstance(services.alarm, AlarmService)
    assert isinstance(services.auth_matrix, AuthMatrixService)
    assert isinstance(services.invalid_params, InvalidParamsService)
    assert isinstance(services.inventory, InventoryService)
    assert isinstance(services.neox_config, NeoXConfigService)
    assert isinstance(services.profile, ProfileService)
    assert isinstance(services.provision, ProvisionService)
    assert isinstance(services.remote, RemoteService)
    assert isinstance(services.user_session, UserSessionService)
