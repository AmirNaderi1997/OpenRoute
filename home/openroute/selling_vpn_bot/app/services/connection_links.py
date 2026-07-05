from collections.abc import Mapping
from urllib.parse import quote, urlencode

from app.core.config import settings
from app.services.account_types import ACCOUNT_TYPE_SSH

REALITY_PUBLIC_KEY = "65xmnjL5GoQm8CEzy45NAdQsQBr8dQYE15Q0VD418yI"
REALITY_SHORT_ID = "0123456789abcdef"
REALITY_DEFAULT_SNI = "yahoo.com"


def normalize_reality_params(
    base_params: Mapping[str, str] | None = None,
    *,
    sni: str = REALITY_DEFAULT_SNI,
) -> dict[str, str]:
    """
    Keep only the Reality client fields that should survive into a final VLESS link.

    This deliberately strips transport-specific fields like `flow`, `host`, `path`, and
    any sniffing-related headers that can leak through from upstream subscriptions.
    """
    params = dict(base_params or {})
    return {
        "security": "reality",
        "allowInsecure": "0",
        "encryption": "none",
        "type": "tcp",
        "sni": sni,
        "sid": params.get("sid", REALITY_SHORT_ID),
        "fp": params.get("fp", "chrome"),
        "pbk": params.get("pbk", REALITY_PUBLIC_KEY),
        "headerType": "none",
    }


def build_vless_reality_link(
    uuid: str,
    host: str,
    port: int,
    *,
    remark: str = "VLESS Reality Tunnel",
    sni: str = REALITY_DEFAULT_SNI,
    base_params: Mapping[str, str] | None = None,
) -> str:
    query = urlencode(normalize_reality_params(base_params, sni=sni))
    return f"vless://{uuid}@{host}:{port}?{query}#{remark}"


def build_ws_path(token: str) -> str:
    if not settings.VPN_WS_PATH_NORMALIZED:
        return ""
    return f"{settings.VPN_WS_PATH_NORMALIZED}?token={token}"


def build_ssh_import_link(
    username: str,
    password: str,
    host: str | None = None,
    port: int | None = None,
) -> str:
    ssh_host = host or settings.REMOTE_VPN_DOMAIN
    ssh_port = port or settings.REMOTE_VPN_PUBLIC_PORT
    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")
    label = quote(f"SSH_{username}", safe="")
    return f"ssh://{encoded_username}:{encoded_password}@{ssh_host}:{ssh_port}#{label}"


def build_import_link(
    username: str,
    password: str,
    _token: str | None = None,
    *,
    service_type: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> str:
    if service_type == ACCOUNT_TYPE_SSH:
        return build_ssh_import_link(username, password, host=host, port=port)
    # For VLESS Reality, use the actual VPN host and the reality port 20443
    host = settings.VPN_PUBLIC_HOST or "p.ipping.ir"
    port = 20443
    return build_vless_reality_link(
        password,
        host,
        port,
        remark=f"OpenRoute - {username}",
    )


def get_connection_details(
    username: str,
    password: str,
    token: str | None = None,
    *,
    service_type: str | None = None,
    host: str | None = None,
    port: int | None = None,
) -> dict[str, str | int]:
    if service_type == ACCOUNT_TYPE_SSH:
        ssh_host = host or settings.REMOTE_VPN_DOMAIN
        ssh_port = port or settings.REMOTE_VPN_PUBLIC_PORT
        return {
            "host": ssh_host,
            "port": ssh_port,
            "path": "",
            "security": "password",
            "sni": "",
            "type": ACCOUNT_TYPE_SSH,
            "import_link": build_import_link(
                username,
                password,
                token,
                service_type=service_type,
                host=ssh_host,
                port=ssh_port,
            ),
        }
    host = settings.VPN_HOST
    return {
        "host": host,
        "port": settings.VPN_PUBLIC_PORT,
        "path": "",
        "security": "reality",
        "sni": "yahoo.com",
        "type": "direct",
        "import_link": build_import_link(username, password, token, service_type=service_type),
    }
