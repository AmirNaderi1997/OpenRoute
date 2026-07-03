import asyncio
import os
import sys
import asyncpg
import redis.asyncio as redis

# A script to check the health and configuration of the production environment
# Intended to be run on the server or locally pointing to the remote DB

async def check_db(url: str):
    print(f"[*] Checking PostgreSQL connection...")
    try:
        # replace postgresql+asyncpg with postgresql
        db_url = url.replace("postgresql+asyncpg", "postgresql")
        conn = await asyncpg.connect(db_url)
        print("    [OK] Connected to PostgreSQL successfully.")
        await conn.close()
        return True
    except Exception as e:
        print(f"    [FAIL] Database connection failed: {e}")
        return False

async def check_redis(host: str, port: int):
    print(f"[*] Checking Redis connection at {host}:{port}...")
    try:
        r = redis.Redis(host=host, port=port)
        await r.ping()
        print("    [OK] Connected to Redis successfully.")
        await r.close()
        return True
    except Exception as e:
        print(f"    [FAIL] Redis connection failed: {e}")
        return False

def check_env():
    print("[*] Checking critical environment variables...")
    keys = ["BOT_TOKEN", "SUPERADMIN_USERNAME", "SUPERADMIN_PASSWORD", "SSH_PRIVATE_KEY_PATH"]
    all_ok = True
    for key in keys:
        if not os.getenv(key):
            print(f"    [FAIL] Missing {key}")
            all_ok = False
        else:
            print(f"    [OK] {key} is present.")
    return all_ok

async def main():
    print("==========================================")
    print("   Production Health & Bug Check Script   ")
    print("==========================================")
    
    # Normally this would load from settings, but as a standalone script we check manually
    from app.core.config import settings
    
    env_ok = check_env()
    db_ok = await check_db(settings.DATABASE_URL)
    redis_ok = await check_redis(settings.REDIS_HOST, settings.REDIS_PORT)
    
    if env_ok and db_ok and redis_ok:
        print("\n✅ All systems nominal. No immediate bugs found.")
        sys.exit(0)
    else:
        print("\n❌ System health check failed. Review the logs above.")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
