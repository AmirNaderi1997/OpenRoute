ACCOUNT_TYPE_SSH = "ssh"
ACCOUNT_TYPE_V2RAY = "v2ray"
ACCOUNT_TYPE_WALLET = "wallet"


def is_v2ray_account(service_type: str | None) -> bool:
    return service_type == ACCOUNT_TYPE_V2RAY


def is_ssh_account(service_type: str | None) -> bool:
    return service_type == ACCOUNT_TYPE_SSH


def service_type_label(service_type: str | None) -> str:
    if service_type == ACCOUNT_TYPE_SSH:
        return "SSH VPN"
    if service_type == ACCOUNT_TYPE_V2RAY:
        return "V2Ray VPN"
    if service_type == ACCOUNT_TYPE_WALLET:
        return "Wallet"
    return "Unknown"
