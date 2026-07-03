import os
import aiosqlite
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

# Resolve database path
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "tunnel.db")

async def init_db() -> None:
    """
    Initializes the SQLite database and creates the users table with data tracking and password columns.
    """
    os.makedirs(DB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
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
            );
        """)
        # Run migration if database exists without column
        try:
            await db.execute("ALTER TABLE users ADD COLUMN max_connections INTEGER DEFAULT 1")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN target_host TEXT DEFAULT '127.0.0.1'")
        except Exception:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN target_port INTEGER DEFAULT 22")
        except Exception:
            pass
            
        # Create an index on uuid_token for fast lookups
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_token ON users (uuid_token);")
        
        await db.commit()
    print(f"Database initialized at: {DB_PATH}")

async def verify_token(token: str) -> Optional[Tuple[str, int, str, int]]:
    """
    Verifies if a uuid_token exists, is active, is not expired, and has not exceeded its data limit.
    Returns (username, max_connections, target_host, target_port) if valid, otherwise None.
    """
    current_utc_str = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT username, max_connections, COALESCE(target_host, '127.0.0.1'), COALESCE(target_port, 22) FROM users 
            WHERE uuid_token = ? 
              AND is_active = 1 
              AND expire_at > ? 
              AND data_used_gb < data_limit_gb
            """,
            (token, current_utc_str)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0], row[1], row[2], int(row[3])
    return None

async def increment_data_usage(username: str, bytes_count: int) -> None:
    """
    Increments the user's data_used_gb by converting bytes to Gigabytes (binary: 1024^3).
    """
    if bytes_count <= 0:
        return
        
    gb_value = bytes_count / (1024 ** 3)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET data_used_gb = data_used_gb + ? WHERE username = ?",
            (gb_value, username)
        )
        await db.commit()

async def seed_test_user() -> None:
    """
    Seeds a test user into the database for validation.
    """
    test_username = "test_vpn_user"
    test_token = "test-uuid-token-1234"
    test_pass = "TestPass123"
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO users (username, uuid_token, ssh_password, is_active, expire_at, data_used_gb, data_limit_gb)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (test_username, test_token, test_pass, 1, expiry, 0.0, 100.0)
        )
        await db.commit()
    print(f"Seeded test user: '{test_username}' with token: '{test_token}' expiring on: {expiry}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(init_db())
    asyncio.run(seed_test_user())
