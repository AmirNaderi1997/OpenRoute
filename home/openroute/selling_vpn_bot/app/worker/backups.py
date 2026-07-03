import os
import asyncio
import logging
from datetime import datetime
from app.core.config import settings

logger = logging.getLogger(__name__)

async def run_database_backup():
    """
    Executes pg_dump via subprocess and compresses the output.
    """
    try:
        os.makedirs("backups", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"backup_{timestamp}.sql.gz"
        filepath = os.path.join("backups", filename)
        
        # We assume pg_dump is available in the environment (e.g. docker container)
        # We can construct the Postgres URI from settings
        db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
        
        logger.info(f"Starting database backup: {filename}")
        
        # pg_dump -d DB_URL | gzip > filepath
        cmd = f"pg_dump -d {db_url} | gzip > {filepath}"
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            logger.info(f"Database backup completed successfully: {filepath}")
            return filepath
        else:
            logger.error(f"Database backup failed. Error: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Error during database backup: {e}")
        return None
