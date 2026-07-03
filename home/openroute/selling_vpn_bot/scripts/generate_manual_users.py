import asyncio
import random
from app.services.ssh.linux import LinuxSSHManager
from app.services.config_generator import generate_streisand_profile, generate_npv_tunnel_uri

VPS_IP = "212.74.39.164"
ROOT_PASS = "1272510662"
SSH_PORT = 22 # We connect locally to 22
CONFIG_PORT = 443 # The user connects to 443 externally

async def generate_users():
    print(f"Connecting to VPS {VPS_IP} on port {SSH_PORT}...")
    manager = LinuxSSHManager(ssh_port=SSH_PORT, root_password=ROOT_PASS)
    
    for i in range(1, 3):
        rand_id = random.randint(1000, 9999)
        username = f"user_{rand_id}"
        password = f"pass{rand_id}"
        
        print(f"\n--- Generating {username} ---")
        # create user on the VPS. LinuxSSHManager connects via SSH to VPS_IP.
        success = await manager.create_system_user(VPS_IP, username, password, expire_days=30)
        
        if success:
            print("✅ User created successfully.")
            # Important: The configuration strings expect the app's DOMAIN logic.
            # We will generate them using the domain 'cdn.ipping.ir'
            
            streisand = generate_streisand_profile(username, password)
            npv = generate_npv_tunnel_uri(username, password)
            
            # Since generate_streisand_profile uses settings.VPN_DOMAIN, let's manually patch the host if needed
            # For demonstration, we just use the default generators which pull from settings
            
            print(f"👤 Username: {username}")
            print(f"🔑 Password: {password}")
            print(f"🔗 NPV Tunnel: \n{npv}\n")
            print(f"📄 Streisand: \n{streisand}")
        else:
            print("❌ Failed to create user via SSH.")

if __name__ == "__main__":
    asyncio.run(generate_users())
