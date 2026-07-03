import json
import base64
import urllib.parse

users = [
    {"username": "premium_esjl3", "password": "key_gvgm9o", "token": "5a908897-a5d0-5cc3-a1f8-4c565f8c46d2"},
    {"username": "premium_egq3w", "password": "key_bfz3f9", "token": "1d7dc043-08d9-59e7-ac13-a4540d22b882"},
    {"username": "premium_9278e", "password": "key_4665x7", "token": "abcbf174-3710-5321-bdaf-84d108887668"},
    {"username": "premium_tx5jc", "password": "key_wlhdzo", "token": "1094ca39-c117-5570-b3ed-330bbdd82ff0"},
    {"username": "premium_6uqwj", "password": "key_3xp34e", "token": "ee50b942-d2e8-58c6-9d8b-4456a3707e46"}
]

domain = "panel.ipping.ir"

for idx, u in enumerate(users, 1):
    username = u["username"]
    password = u["password"]
    token = u["token"]
    
    path = f"/vpn?token={token}"
    
    # 1. Streisand JSON Profile
    streisand = {
        "name": f"VPN_{username}",
        "server": domain,
        "port": 443,
        "type": "ssh",
        "username": username,
        "password": password,
        "ws_path": path,
        "tls": True,
        "sni": domain
    }
    
    # 2. NPV Tunnel Base64 URI
    npv_profile = {
        "ps": f"VPN_{username}",
        "add": domain,
        "port": "443",
        "id": username,
        "pw": password,
        "net": "ws",
        "type": "none",
        "host": domain,
        "path": path,
        "tls": "tls",
        "sni": domain
    }
    npv_json = json.dumps(npv_profile)
    npv_b64 = base64.b64encode(npv_json.encode('utf-8')).decode('utf-8')
    npv_uri = f"npv://{npv_b64}"
    
    # 3. HTTP Custom (Payload details for manual input)
    payload = f"GET {path} HTTP/1.1[crlf]Host: {domain}[crlf]Upgrade: websocket[crlf]Connection: Upgrade[crlf][crlf]"
    
    print(f"==================================================")
    print(f"CONFIG FOR Account {idx} ({username})")
    print(f"==================================================")
    print(f"📶 NPV Tunnel / NapsternetV One-Click Link:")
    print(f"{npv_uri}")
    print()
    print(f"🎒 Streisand JSON Profile (Copy & paste directly):")
    print(json.dumps(streisand, indent=2))
    print()
    print(f"🛠️ HTTP Custom / NetMod Manual Settings:")
    print(f"  SSH Host: {domain}")
    print(f"  SSH Port: 443")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print(f"  Payload: {payload}")
    print("--------------------------------------------------\n")
