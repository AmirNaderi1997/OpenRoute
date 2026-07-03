import asyncio
import random
import string
import os
import sys
import secrets
from datetime import datetime, timedelta, timezone

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import async_session_maker
from app.db.models import User, SshServer, SshAccount
from app.services.ssh.linux import LinuxSSHManager
from app.services.tunnel_db import sync_user_to_tunnel_db
from sqlalchemy import select, delete

VPS_IP = "66.92.161.177"
ROOT_PASS = "1272510662"
SSH_PORT = 22

def generate_random_password(length=8):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

async def main():
    print("=== Recreating openroute1001 to openroute1010 Accounts ===")
    
    async with async_session_maker() as session:
        # 1. Ensure system user exists
        system_user = await session.get(User, 1)
        if not system_user:
            system_user = User(id=1, username="system_store", is_admin=False, balance=0.0)
            session.add(system_user)
            await session.commit()
            print("Created system_store user in Postgres (ID=1).")
        
        # 2. Ensure SshServer exists
        server = await session.scalar(select(SshServer).where(SshServer.ip_address == VPS_IP))
        if not server:
            server = SshServer(
                name="England",
                ip_address=VPS_IP,
                ssh_port=SSH_PORT,
                root_password=ROOT_PASS,
                status="active"
            )
            session.add(server)
            await session.commit()
            print(f"Registered server {VPS_IP} in Postgres.")
        else:
            server.name = "England"
            server.root_password = ROOT_PASS
            await session.commit()
            print(f"Server {VPS_IP} already registered. Updated name to England.")
            
        ssh_manager = LinuxSSHManager(ssh_port=SSH_PORT, root_password=ROOT_PASS)
        
        # 3. Fetch and clean up any existing accounts from VPS and tunnel.db
        existing_accounts = (await session.scalars(select(SshAccount))).all()
        print(f"Found {len(existing_accounts)} existing accounts to clean up.")
        
        import aiosqlite
        dir_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        tunnel_db_path = os.path.join(dir_path, "tunnel", "data", "tunnel.db")
        
        for acc in existing_accounts:
            print(f"Cleaning up {acc.ssh_username}...")
            # Delete system user from Linux host
            try:
                # We can run userdel via ssh manager
                await ssh_manager._run_command(VPS_IP, f"userdel -r {acc.ssh_username}")
                print(f"  Deleted Linux system user {acc.ssh_username}")
            except Exception as e:
                print(f"  Error deleting Linux user {acc.ssh_username}: {e}")
                
            # Delete from SQLite tunnel.db
            try:
                if os.path.exists(tunnel_db_path):
                    async with aiosqlite.connect(tunnel_db_path) as db:
                        await db.execute("DELETE FROM users WHERE username = ?", (acc.ssh_username,))
                        await db.commit()
                    print(f"  Deleted {acc.ssh_username} from tunnel.db")
            except Exception as e:
                print(f"  Error deleting {acc.ssh_username} from tunnel.db: {e}")
                
        # Clear SshAccounts table
        await session.execute(delete(SshAccount))
        await session.commit()
        print("Cleared ssh_accounts table in Postgres.")
        
        # 4. Pregenerate exactly openroute1001 to openroute1010
        expires_at = datetime.now(timezone.utc) + timedelta(days=365) # 1 year validity placeholder
        
        for i in range(1001, 1011):
            username = f"openroute{i}"
            password = generate_random_password(8)
            print(f"\nProvisioning {username}...")
            
            # Create system user on VPS host
            success = await ssh_manager.create_system_user(VPS_IP, username, password, expire_days=365)
            if not success:
                print(f"❌ Failed to create system user {username} on VPS host.")
                continue
                
            # Lock the system user immediately since they are inactive
            await ssh_manager._run_command(VPS_IP, f"usermod -L {username}")
            print(f"🔒 Locked system user {username} (inactive by default)")
            
            # Save SshAccount in PostgreSQL (assigned to system user ID 1, inactive status)
            account = SshAccount(
                user_id=system_user.id,
                server_id=server.id,
                ssh_username=username,
                ssh_password=password,
                duration_days=30,
                traffic_limit_gb=100,  # default 100GB limit
                expires_at=expires_at,
                status="inactive"
            )
            session.add(account)
            await session.commit()
            print(f"✅ Registered {username} in Postgres.")
            
            # Sync to SQLite tunnel.db as inactive (is_active = 0)
            await sync_user_to_tunnel_db(
                username=username,
                password=password,
                expires_at=expires_at,
                traffic_limit_gb=100.0,
                is_active=0,
                target_host=server.ip_address,
                target_port=server.ssh_port,
            )
            print(f"✅ Synced {username} to tunnel.db as inactive.")
            
    print("\n=== Recreation Completed Successfully! ===")

if __name__ == "__main__":
    asyncio.run(main())
