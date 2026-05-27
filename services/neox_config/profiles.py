from __future__ import annotations


NEOX_PROFILE_TYPES = [
    "IGMPGroupPrivilegeProfile",
    "ONTAclProfile",
    "ONTAlarmProfile",
    "ONTBandwidthProfile",
    "ONTMulticastProfile",
    "ONTONTProfile",
    "ONTSecurityProfile",
    "ONTServiceProfile",
    "ONTTemplateProfile",
    "ONTUNIProfile",
    "ONTVoipCommonProfile",
    "ONTVoipDialPlanProfile",
    "ONTVoipSipProfile",
    "RateLimitProfile",
    "ShapingProfile",
    "WeightProfile",
]


NEOX_PROFILE_READWRITE_TYPES = list(NEOX_PROFILE_TYPES)


NEOX_PROFILE_CONFIG_REFS = {
    "IGMPGroupPrivilegeProfile": "igmp_group_privilege_profile_data",
    "ONTAclProfile": "ont_acl_profile_data",
    "ONTAlarmProfile": "ont_alarm_profile_data",
    "ONTBandwidthProfile": "ont_bandwidth_profile_data",
    "ONTMulticastProfile": "ont_multicast_profile_data",
    "ONTONTProfile": "ont_ont_profile_data",
    "ONTSecurityProfile": "ont_security_profile_data",
    "ONTServiceProfile": "ont_service_profile_data",
    "ONTTemplateProfile": "ont_template_profile_data",
    "ONTUNIProfile": "ont_uni_profile_data",
    "ONTVoipCommonProfile": "ont_voip_common_profile_data",
    "ONTVoipDialPlanProfile": "ont_voip_dialplan_profile_data",
    "ONTVoipSipProfile": "ont_voip_sip_profile_data",
    "RateLimitProfile": "rate_limit_profile_data",
    "ShapingProfile": "shaping_profile_data",
    "WeightProfile": "weight_profile_data",
}


NEOX_PROFILE_NAMES = {
    "IGMPGroupPrivilegeProfile": "RestApi_NeoX_IGMPGroupPriv",
    "ONTAclProfile": "RestApi_NeoX_ONTAcl",
    "ONTAlarmProfile": "RestApi_NeoX_ONTAlarm",
    "ONTBandwidthProfile": "RestApi_NeoX_ONTBandwidth",
    "ONTMulticastProfile": "RestApi_NeoX_ONTMulticast",
    "ONTONTProfile": "RestApi_NeoX_ONT",
    "ONTSecurityProfile": "RestApi_NeoX_ONTSecurity",
    "ONTServiceProfile": "RestApi_NeoX_ONTService",
    "ONTTemplateProfile": "RestApi_NeoX_ONTTemplate",
    "ONTUNIProfile": "RestUNI",
    "ONTVoipCommonProfile": "RestVoipCom",
    "ONTVoipDialPlanProfile": "RestVoipDP",
    "ONTVoipSipProfile": "RestVoipSip",
    "RateLimitProfile": "RestApi_NeoX_RateLimit",
    "ShapingProfile": "RestApi_NeoX_Shaping",
    "WeightProfile": "RestApi_NeoX_Weight",
}


NEOX_PROFILE_DEPENDENCIES = {
    "ONTTemplateProfile": [
        "ONTAlarmProfile",
        "ONTBandwidthProfile",
        "ONTMulticastProfile",
        "ONTONTProfile",
        "ONTSecurityProfile",
        "ONTServiceProfile",
    ],
}


NEOX_PREFIXES = {
    "IGMPGroupPrivilegeProfile": "ontigmpprofile_",
    "ONTAclProfile": "ontaclprofile_",
    "ONTAlarmProfile": "ontalarmprofile_",
    "ONTBandwidthProfile": "bwprofile_",
    "ONTMulticastProfile": "multicastprofile_",
    "ONTSecurityProfile": "securityprofile_",
    "ONTServiceProfile": "serviceprofile_",
    "ONTTemplateProfile": "templateprofile_",
    "ONTUNIProfile": "uniprofile_",
    "ONTVoipCommonProfile": "ontvoipcommprofile_",
    "ONTVoipDialPlanProfile": "ontvoipdialplanprofile_",
    "ONTVoipSipProfile": "ontvoipsipprofile_",
    "RateLimitProfile": "ratelimitprofile_",
    "ShapingProfile": "shapingprofile_",
    "WeightProfile": "weightprofile_",
}


ONT_UNI_SMOKE_CONTENT = {
    "xlanethertype1": "ipoe",
    "xlanunivlan1": "1",
    "xlanuniport1": "1",
    "xlanvlan1": "1",
    "xlanactive1": "no",
    "xlanfdb1": "255",
    "xlandspir1": "128",
    "xlanbroadcast1": "32",
    "xlanmulticast1": "32",
    "xlandlf1": "32",
}


NEOX_CONTENT_OVERRIDES = {
    "IGMPGroupPrivilegeProfile": {},
    "ONTAclProfile": {},
    "ONTAlarmProfile": {
        "lowcurr": "0",
        "upcurr": "79",
        "lowrxpower": "-127",
        "uprxpower": "0",
        "lowtemp": "-40",
        "uptemp": "100",
        "lowtxpower": "-15.3",
        "uptxpower": "6.5",
        "lowvolt": "2.8",
        "upvol": "3.59",
    },
    "ONTBandwidthProfile": {"air": "0", "sir": "10240", "pir": "10240"},
    "ONTMulticastProfile": {},
    "ONTONTProfile": {},
    "ONTSecurityProfile": {"fdb": "1023"},
    "ONTServiceProfile": {"mode": "veip", "uniport": "lan", "lan": "1", "vlan": "1314", "pbit": "0"},
    "ONTTemplateProfile": {},
    "ONTUNIProfile": ONT_UNI_SMOKE_CONTENT,
    "ONTVoipCommonProfile": {
        "1codec": "G729",
        "1packet": "10",
        "1silence": "disable",
        "buf": "500",
        "dscp": "63",
        "dtmf": "enable",
        "echo": "enable",
        "maxport": "65535",
        "minport": "1",
    },
    "ONTVoipDialPlanProfile": {
        "critical": "8000",
        "format": "h248",
        "identifier": "+88603(X.)",
        "max": "256",
        "partial": "32000",
    },
    "ONTVoipSipProfile": {
        "hosturi": "10.0.0.1",
        "proxyaddr": "10.0.0.1",
        "registrar": "10.0.0.1",
        "regexptime": "3600",
        "pridns": "8.8.8.8",
        "secdns": "8.8.4.4",
    },
    "RateLimitProfile": {},
    "ShapingProfile": {
        "rate0": "0",
        "rate1": "1000000",
        "rate2": "2000000",
        "rate3": "3000000",
        "rate4": "4000000",
        "rate5": "5000000",
        "rate6": "6000000",
        "rate7": "7000000",
    },
    "WeightProfile": {
        "weight0": "0",
        "weight1": "1",
        "weight2": "2",
        "weight3": "3",
        "weight4": "4",
        "weight5": "5",
        "weight6": "6",
        "weight7": "7",
    },
}
