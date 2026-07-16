from __future__ import annotations

from typing import Any


def ont_service_payload(env: Any, unique_name: str, ont_template: str | None = None) -> dict[str, Any]:
    dut = env.dut
    template_profile = str(ont_template or dut.ont_template)
    bandwidth_profile = str(getattr(ont_template, "bandwidth_name", "#RestApi_1G"))
    data = {
        "ontdisable": "no",
        "ont_active_checkbox": 1,
        "description": unique_name,
        "templateprof": template_profile,
        "dspir": "",
        "qoss": [{"qostcont": "service1", "qosds": bandwidth_profile, "qosus": bandwidth_profile}],
        "hostvlan": "",
        "hostmode": "1",
        "hostip": "",
        "hostmask": "",
        "hostgateway": "",
        "hostpridns": "",
        "hostsecdns": "",
        "hostpbit": "",
    }
    for index in range(1, 9):
        data.update(
            {
                f"waninactive{index}": "no",
                f"wan_active_{index}": 2,
                f"wanip{index}": "",
                f"wanmask{index}": "",
                f"wangateway{index}": "",
                f"wanprimarydns{index}": "",
                f"wansecondarydns{index}": "",
                f"wanuser{index}": "",
                f"wanpass{index}": "",
            }
        )
    for index in range(1, 5):
        data.update(
            {
                f"wifi2inactive{index}": "no",
                f"wify2_active_{index}": 2,
                f"wifi2ssid{index}": "",
                f"wifi2pass{index}": "",
                f"wifi5inactive{index}": "no",
                f"wify5_active_{index}": 2,
                f"wifi5ssid{index}": "",
                f"wifi5pass{index}": "",
            }
        )
    data.update({"wify5_active_1": 1, "wifi5ssid1": unique_name[:31], "wifi5pass1": "musk1234"})
    for index in range(1, 3):
        data.update(
            {
                f"voipuniport{index}": str(index),
                f"voipactive{index}": "",
                f"voip_active_{index}": 2,
                f"voipuser{index}": "",
                f"voippass{index}": "",
                f"voipaor{index}": "",
            }
        )
    return {
        "ontservice": {
            "password": dut.ont_password,
            "data": data,
        }
    }


def ont_service_modified_payload(
    env: Any,
    unique_name: str,
    ont_template: str | None = None,
) -> dict[str, Any]:
    payload = ont_service_payload(env, unique_name, ont_template=ont_template)
    payload["ontservice"]["data"]["description"] = f"{unique_name}_MOD"
    payload["ontservice"]["data"]["wifi5ssid1"] = f"{unique_name[:24]}_MOD"
    return payload


def ge_service_payload(env: Any, unique_name: str, ge_template: str | None = None) -> dict[str, Any]:
    return {
        "geservice": {
            "geTemplate": str(ge_template or env.dut.ge_template),
            "Tel": env.dut.ge_telephone,
            "PortName": unique_name[:31],
        }
    }


def ge_service_modified_payload(env: Any, unique_name: str, ge_template: str | None = None) -> dict[str, Any]:
    return {
        "geservice": {
            "geTemplate": str(ge_template or env.dut.ge_template),
            "Tel": f"{env.dut.ge_telephone}0123",
            "PortName": f"{unique_name}_MOD"[:31],
        }
    }


def remote_console_payload(env: Any, unique_name: str) -> dict[str, Any]:
    return {"command": ["show version"]}
