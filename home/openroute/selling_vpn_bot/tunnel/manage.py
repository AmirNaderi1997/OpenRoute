import asyncio
import os
import sys
import uuid
import secrets
import string
import subprocess
import argparse
from datetime import datetime, timezone, timedelta
import aiosqlite
try:
    from tunnel.database import DB_PATH, init_db
except ModuleNotFoundError:
    from database import DB_PATH, init_db

VPN_PUBLIC_HOST = os.getenv("VPN_PUBLIC_HOST", "panel.ipping.ir")
VPN_PUBLIC_PORT = int(os.getenv("VPN_PUBLIC_PORT", "443"))
VPN_WS_PATH = os.getenv("VPN_WS_PATH", "/vpn")

# Helper to format timestamps
def parse_date(date_str: str) -> str:
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return date_str

def generate_random_password(length: int = 10) -> str:
    """
    Generates a secure random alphanumeric password.
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))

def generate_import_link(username: str, password: str, token: str) -> str:
    import urllib.parse

    path_with_token = f"{VPN_WS_PATH}?token={token}"
    encoded_path = urllib.parse.quote(path_with_token, safe="")
    encoded_host = urllib.parse.quote(VPN_PUBLIC_HOST, safe="")
    encoded_username = urllib.parse.quote(username, safe="")
    encoded_password = urllib.parse.quote(password, safe="")
    encoded_label = urllib.parse.quote(f"VPN_{username}", safe="")
    return (
        f"ssh://{encoded_username}:{encoded_password}@{VPN_PUBLIC_HOST}:{VPN_PUBLIC_PORT}"
        f"?type=ws&path={encoded_path}&host={encoded_host}&security=tls&sni={encoded_host}"
        f"#{encoded_label}"
    )

def create_system_user(username: str, password: str, expiry_date: datetime) -> bool:
    """
    Creates a restricted system user on Linux and sets their password and expiry.
    """
    # Only run on Linux hosts
    if sys.platform != "linux":
        print(f"[Local Dev] Simulated Linux user creation for: {username}")
        return True
        
    try:
        # 1. Create user with no login shell
        subprocess.run(
            ["useradd", "-m", "-s", "/usr/sbin/nologin", username],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # 2. Set user password
        chpasswd_proc = subprocess.Popen(
            ["chpasswd"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        chpasswd_proc.communicate(input=f"{username}:{password}")
        
        # 3. Set expiry date (YYYY-MM-DD format for chage)
        expiry_str = expiry_date.strftime("%Y-%m-%d")
        subprocess.run(
            ["chage", "-E", expiry_str, username],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        return True
    except subprocess.CalledProcessError as e:
        stderr_output = e.stderr.decode().strip() if e.stderr else str(e)
        print(f"Error creating system user '{username}': {stderr_output}")
        return False
    except Exception as e:
        print(f"Failed to create system user '{username}': {e}")
        return False

async def add_users(count: int, limit_gb: float, days: int) -> None:
    """
    Generates a batch of unique users, creates their Linux accounts, and saves credentials to SQLite.
    """
    expire_dt = datetime.now(timezone.utc) + timedelta(days=days)
    expire_str = expire_dt.isoformat()
    
    generated_users = []
    
    async with aiosqlite.connect(DB_PATH) as db:
        for _ in range(count):
            user_uuid = str(uuid.uuid4())
            short_id = user_uuid.split('-')[0]
            username = f"user_{short_id}"
            password = generate_random_password(10)
            
            # Create the actual Linux user
            success = create_system_user(username, password, expire_dt)
            if not success and sys.platform == "linux":
                print(f"Aborting creation for '{username}' due to system error.")
                continue
                
            await db.execute(
                """
                INSERT INTO users (username, uuid_token, ssh_password, is_active, expire_at, data_used_gb, data_limit_gb)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (username, user_uuid, password, 1, expire_str, 0.0, limit_gb)
            )
            generated_users.append((username, password, user_uuid))
        
        await db.commit()
    
    # Print Copy-Pastable configuration blocks
    print("=" * 70)
    print(f"🎉 SUCCESS: Generated {len(generated_users)} new VPN users (Linux + WebSocket Proxy)")
    print("=" * 70)
    for username, password, token in generated_users:
        import_link = generate_import_link(username, password, token)
        
        print(f"Username: {username}")
        print(f"Password: {password}")
        print(f"Token:    {token}")
        print(f"Copy-Pastable VPN Config Link:")
        print(import_link)
        print("-" * 70)

def urllib_encode(text: str) -> str:
    import urllib.parse
    return urllib.parse.quote(text, safe='')

async def list_users() -> None:
    """
    Lists all users in the database with their usage status.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, ssh_password, uuid_token, is_active, expire_at, data_used_gb, data_limit_gb FROM users"
        ) as cursor:
            rows = await cursor.fetchall()
            
            if not rows:
                print("No users found in database.")
                return
                
            print(f"{'Username':<15} | {'Password':<11} | {'Status':<8} | {'Usage (GB)':<13} | {'Expiry Date':<22} | {'Token'}")
            print("-" * 125)
            for row in rows:
                username, password, token, active, expiry, used, limit = row
                status_str = "Active" if active == 1 else "Disabled"
                usage_str = f"{used:.2f}/{limit:.0f}"
                expiry_str = parse_date(expiry)
                print(f"{username:<15} | {password:<11} | {status_str:<8} | {usage_str:<13} | {expiry_str:<22} | {token}")

async def renew_user(username: str, days: int) -> None:
    """
    Extends user expiration date by a number of days.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Fetch current expiration
        async with db.execute("SELECT expire_at FROM users WHERE username = ?", (username,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                print(f"Error: User '{username}' not found.")
                return
            
            current_expiry = datetime.fromisoformat(row[0])
            # If already expired, start from current time, otherwise add to current expiry
            base_time = datetime.now(timezone.utc) if current_expiry < datetime.now(timezone.utc) else current_expiry
            new_expiry = base_time + timedelta(days=days)
            new_expiry_str = new_expiry.isoformat()
            
            # 1. Update SQLite
            await db.execute(
                "UPDATE users SET expire_at = ?, is_active = 1 WHERE username = ?",
                (new_expiry_str, username)
            )
            await db.commit()
            
            # 2. Update Linux system user expiry and unlock password
            if sys.platform == "linux":
                expiry_str = new_expiry.strftime("%Y-%m-%d")
                subprocess.run(["chage", "-E", expiry_str, username])
                subprocess.run(["usermod", "-U", username])
                
            print(f"User '{username}' renewed for {days} days. New expiry: {parse_date(new_expiry_str)}")

async def disable_user(username: str) -> None:
    """
    Disables a user in the database and locks their Linux account.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE users SET is_active = 0 WHERE username = ?", (username,))
        await db.commit()
        
        if cursor.rowcount > 0:
            # Lock the actual Linux system user password and set expiry to 0 (expired)
            if sys.platform == "linux":
                subprocess.run(["usermod", "-L", username])
                subprocess.run(["chage", "-E", "0", username])
            print(f"User '{username}' has been successfully disabled/locked.")
        else:
            print(f"Error: User '{username}' not found.")

async def get_info(username: str) -> None:
    """
    Prints detailed account stats for a specific user.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT username, ssh_password, uuid_token, is_active, expire_at, data_used_gb, data_limit_gb FROM users WHERE username = ?",
            (username,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                print(f"Error: User '{username}' not found.")
                return
            
            username, password, token, active, expiry, used, limit = row
            status_str = "Active" if active == 1 else "Disabled"
            percentage = (used / limit) * 100 if limit > 0 else 0
            
            print(f"=== ACCOUNT INFO: {username} ===")
            print(f"SSH Password:     {password}")
            print(f"Proxy Token:      {token}")
            print(f"Status:           {status_str}")
            print(f"Data Usage:       {used:.4f} GB / {limit:.1f} GB ({percentage:.2f}%)")
            print(f"Expiry:           {parse_date(expiry)}")
            
            # Format connection link
            import_link = generate_import_link(username, password, token)
            print(f"Connection Link:  {import_link}")

def main():
    parser = argparse.ArgumentParser(description="Tunnel VPN User Management CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Init DB command
    subparsers.add_parser("init", help="Initialize the database schema")
    
    # Add users command
    add_parser = subparsers.add_parser("add-users", help="Generate a batch of new users")
    add_parser.add_argument("--count", type=int, default=5, help="Number of users to generate (default: 5)")
    add_parser.add_argument("--limit", type=float, default=100.0, help="Data limit in GB (default: 100)")
    add_parser.add_argument("--days", type=int, default=30, help="Validity period in days (default: 30)")
    
    # List users command
    subparsers.add_parser("list-users", help="List all users in the database")
    
    # Renew user command
    renew_parser = subparsers.add_parser("renew-user", help="Renew/extend user access duration")
    renew_parser.add_argument("username", type=str, help="Username of the client to renew")
    renew_parser.add_argument("--days", type=int, default=30, help="Number of days to extend (default: 30)")
    
    # Disable user command
    disable_parser = subparsers.add_parser("disable-user", help="Disable a user immediately")
    disable_parser.add_argument("username", type=str, help="Username of the client to disable")
    
    # Get info command
    info_parser = subparsers.add_parser("get-info", help="Print detailed stats for a user")
    info_parser.add_argument("username", type=str, help="Username of the client to inspect")
    
    args = parser.parse_args()
    
    if args.command == "init":
        asyncio.run(init_db())
    elif args.command == "add-users":
        asyncio.run(add_users(args.count, args.limit, args.days))
    elif args.command == "list-users":
        asyncio.run(list_users())
    elif args.command == "renew-user":
        asyncio.run(renew_user(args.username, args.days))
    elif args.command == "disable-user":
        asyncio.run(disable_user(args.username))
    elif args.command == "get-info":
        asyncio.run(get_info(args.username))

if __name__ == "__main__":
    main()
