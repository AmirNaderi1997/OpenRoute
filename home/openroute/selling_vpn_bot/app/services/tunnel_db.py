import os
import uuid
import aiosqlite
from datetime import datetime, timezone
import logging

from app.services.connection_links import build_import_link

logger = logging.getLogger(__name__)

def get_deterministic_uuid(username: str) -> str:
    """
    Generates a deterministic UUID based on the username.
    This eliminates the need to store the token in the PostgreSQL database,
    making database schema modifications unnecessary.
    """
    NAMESPACE_VPN = uuid.UUID("12345678-1234-5678-1234-567812345678")
    return str(uuid.uuid5(NAMESPACE_VPN, username))

def generate_option1_link(username: str, password: str, token: str = None) -> str:
    """
    Generates the public WebSocket/TLS ssh:// import URI for VPN clients.
    """
    if token is None:
        token = get_deterministic_uuid(username)
    return build_import_link(username, password, token)

async def sync_user_to_tunnel_db(
    username: str,
    password: str,
    expires_at: datetime,
    traffic_limit_gb: float = None,
    is_active: int = 1,
    max_connections: int = 1,
    target_host: str | None = None,
    target_port: int | None = None,
) -> str:
    """
    Ensures a VPN user is present and correct in the host's tunnel.db SQLite file.
    Returns the uuid_token for client configuration.
    """
    if traffic_limit_gb is None:
        traffic_limit_gb = 99999.0
    if target_host is None:
        target_host = "127.0.0.1"
    if target_port is None:
        target_port = 22

    token = get_deterministic_uuid(username)
    # Expiration string in ISO format
    # Ensure expires_at has timezone info
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    expire_str = expires_at.isoformat()
    
    # Resolve tunnel.db path relative to the project root
    dir_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    tunnel_db_path = os.path.join(dir_path, "tunnel", "data", "tunnel.db")
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(tunnel_db_path), exist_ok=True)
    
    try:
        async with aiosqlite.connect(tunnel_db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    uuid_token TEXT UNIQUE NOT NULL,
                    ssh_password TEXT,
                    is_active INTEGER DEFAULT 1,
                    expire_at TEXT NOT NULL,
                    data_used_gb REAL DEFAULT 0.0,
                    data_limit_gb REAL DEFAULT 100.0,
                    max_connections INTEGER DEFAULT 1,
                    target_host TEXT DEFAULT '127.0.0.1',
                    target_port INTEGER DEFAULT 22
                )
                """
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_token ON users (uuid_token)")
            for migration_sql in (
                "ALTER TABLE users ADD COLUMN max_connections INTEGER DEFAULT 1",
                "ALTER TABLE users ADD COLUMN target_host TEXT DEFAULT '127.0.0.1'",
                "ALTER TABLE users ADD COLUMN target_port INTEGER DEFAULT 22",
            ):
                try:
                    await db.execute(migration_sql)
                except Exception:
                    pass

            # Check if user already exists
            async with db.execute("SELECT uuid_token, is_active FROM users WHERE username = ?", (username,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    # Update credentials, status, expiry, limit, max_connections
                    await db.execute(
                        """
                        UPDATE users 
                        SET uuid_token = ?, ssh_password = ?, expire_at = ?, is_active = ?, data_limit_gb = ?, max_connections = ?, target_host = ?, target_port = ?
                        WHERE username = ?
                        """,
                        (
                            token,
                            password,
                            expire_str,
                            is_active,
                            traffic_limit_gb,
                            max_connections,
                            target_host,
                            target_port,
                            username,
                        )
                    )
                    logger.info(f"[TunnelDB Sync] Updated existing user '{username}' (is_active={is_active}, max_connections={max_connections}) in tunnel.db")
                else:
                    # Insert new user
                    await db.execute(
                        """
                        INSERT INTO users (
                            username,
                            uuid_token,
                            ssh_password,
                            is_active,
                            expire_at,
                            data_used_gb,
                            data_limit_gb,
                            max_connections,
                            target_host,
                            target_port
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username,
                            token,
                            password,
                            is_active,
                            expire_str,
                            0.0,
                            traffic_limit_gb,
                            max_connections,
                            target_host,
                            target_port,
                        )
                    )
                    logger.info(f"[TunnelDB Sync] Inserted new user '{username}' (is_active={is_active}, max_connections={max_connections}) in tunnel.db")
            await db.commit()
    except Exception as e:
        logger.error(f"[TunnelDB Sync] Error syncing user '{username}' to tunnel.db: {e}")
        
    return token
