import json
import base64
from app.core.config import settings

def generate_streisand_profile(username: str, password: str, server_ip: str | None = None, port: int | None = None) -> str:
    """
    Generates a Streisand-compatible JSON profile string.
    """
    server_ip = server_ip or settings.VPN_HOST
    port = port or settings.VPN_PUBLIC_PORT
    profile = {
        "name": f"VPN_{username}",
        "server": server_ip,
        "port": port,
        "type": "ssh",
        "username": username,
        "password": password,
        "ws_path": "",
        "tls": False,
        "sni": ""
    }
    return json.dumps(profile)

def generate_npv_tunnel_uri(username: str, password: str, server_ip: str | None = None, port: int | None = None) -> str:
    """
    Generates an NPV Tunnel compatible URI.
    Format: npv://<base64_encoded_json>
    """
    server_ip = server_ip or settings.VPN_HOST
    port = port or settings.VPN_PUBLIC_PORT
    profile = {
        "ps": f"VPN_{username}",
        "add": server_ip,
        "port": str(port),
        "id": username,
        "pw": password,
        "net": "tcp",
        "type": "none",
        "host": server_ip,
        "path": "",
        "tls": "",
        "sni": ""
    }
    
    json_str = json.dumps(profile)
    b64_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    return f"npv://{b64_str}"
