from __future__ import annotations

from dataclasses import dataclass

from services.alarm import AlarmService
from services.auth_matrix import AuthMatrixService
from services.invalid_params import InvalidParamsService
from services.inventory import InventoryService
from services.profile import ProfileService
from services.provision import ProvisionService
from services.remote import RemoteService
from services.session import UserSessionService


@dataclass(frozen=True)
class ServiceBundle:
    alarm: AlarmService
    auth_matrix: AuthMatrixService
    invalid_params: InvalidParamsService
    inventory: InventoryService
    profile: ProfileService
    provision: ProvisionService
    remote: RemoteService
    user_session: UserSessionService


def build_service_bundle(api_client, env_config) -> ServiceBundle:
    return ServiceBundle(
        alarm=AlarmService(api_client, env_config),
        auth_matrix=AuthMatrixService(api_client),
        invalid_params=InvalidParamsService(api_client, env_config),
        inventory=InventoryService(api_client, env_config),
        profile=ProfileService(api_client),
        provision=ProvisionService(api_client, env_config),
        remote=RemoteService(api_client, env_config),
        user_session=UserSessionService(api_client, env_config),
    )
