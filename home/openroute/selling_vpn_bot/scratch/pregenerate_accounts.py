import asyncio
import random
import string
import os
import sys
from datetime import datetime, timedelta, timezone

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import async_session_maker
from app.db.models import User, SshServer, SshAccount
from app.services.ssh.linux import LinuxSSHManager
from app.services.tunnel_db import sync_user_to_tunnel_db, generate_option1_link
from sqlalchemy import select

VPS_IP = "66.92.161.177"
ROOT_PASS = "1272510662"
SSH_PORT = 22

def generate_random_string(length=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

async def main():
    print("=== Pregenerating 5 Premium VPN Accounts ===")
    
    async with async_session_maker() as session:
        # 1. Ensure system user exists
        system_user = await session.get(User, 1)
        if not system_user:
            system_user = User(id=1, username="system_store", is_admin=False, balance=0.0)
            session.add(system_user)
            await session.commit()
            print("Created system_store user in Postgres (ID=1).")
        else:
            print("System user already exists.")

        # 2. Ensure SshServer exists
        server = await session.scalar(select(SshServer).where(SshServer.ip_address == VPS_IP))
        if not server:
            server = SshServer(
                name="England🏴",
                ip_address=VPS_IP,
                ssh_port=SSH_PORT,
                root_password=ROOT_PASS,
                status="active"
            )
            session.add(server)
            await session.commit()
            print(f"Registered server {VPS_IP} in Postgres.")
        else:
            # Make sure password is correct
            server.root_password = ROOT_PASS
            await session.commit()
            print(f"Server {VPS_IP} already registered.")

        # 3. Create SSH Manager
        ssh_manager = LinuxSSHManager(ssh_port=SSH_PORT, root_password=ROOT_PASS)
        
        links = []
        
        # 4. Generate 5 accounts
        for i in range(1, 6):
            rand_suffix = generate_random_string(5)
            username = f"premium_{rand_suffix}"
            password = f"key_{generate_random_string(6)}"
            
            print(f"\n[{i}/5] Provisioning account: {username}")
            
            # Create system user on VPS host
            success = await ssh_manager.create_system_user(VPS_IP, username, password, expire_days=30)
            if not success:
                print(f"❌ Failed to create system user {username} on VPS host.")
                continue
                
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)
            
            # Save SshAccount in PostgreSQL
            account = SshAccount(
                user_id=system_user.id,
                server_id=server.id,
                ssh_username=username,
                ssh_password=password,
                duration_days=30,
                traffic_limit_gb=100,  # 100GB limit
                expires_at=expires_at,
                status="active"
            )
            session.add(account)
            await session.commit()
            print("✅ Registered account in Postgres.")
            
            # Sync to SQLite tunnel.db
            token = await sync_user_to_tunnel_db(
                username=username,
                password=password,
                expires_at=expires_at,
                traffic_limit_gb=100.0
            )
            print("✅ Synced account to host tunnel.db.")
            
            # Generate SSH Link
            link = generate_option1_link(username, password, token)
            links.append((username, password, link))
            print(f"🔗 Link: {link}")

        print("\n=== Generation Completed! ===")
        print("Here are your generated VPN config URIs (Direct SSH):")
        print("==================================================")
        for idx, (u, p, l) in enumerate(links, 1):
            print(f"Account {idx}:")
            print(f"  Username: {u}")
            print(f"  Password: {p}")
            print(f"  URI: {l}")
            print("--------------------------------------------------")

if __name__ == "__main__":
    asyncio.run(main())
