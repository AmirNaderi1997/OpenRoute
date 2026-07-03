import asyncio
import logging
from app.services.ssh.base import BaseSSHManager

logger = logging.getLogger(__name__)

class MockSSHManager(BaseSSHManager):
    """
    A mock implementation of BaseSSHManager for testing purposes.
    It simulates network latency and returns success without actually connecting to any servers.
    """

    async def create_system_user(self, server_ip: str, username: str, password: str, expire_days: int) -> bool:
        logger.info(f"[MOCK SSH] Connecting to {server_ip}...")
        await asyncio.sleep(1) # Simulate network delay
        logger.info(f"[MOCK SSH] Executing: useradd -M -s /bin/false {username}")
        logger.info(f"[MOCK SSH] Executing: echo '{username}:{password}' | chpasswd")
        logger.info(f"[MOCK SSH] Executing: chage -E $(date -d '+{expire_days} days' +%Y-%m-%d) {username}")
        await asyncio.sleep(0.5)
        logger.info(f"[MOCK SSH] Successfully created user {username} on {server_ip}")
        return True

    async def lock_user(self, server_ip: str, username: str) -> bool:
        logger.info(f"[MOCK SSH] Connecting to {server_ip}...")
        await asyncio.sleep(1) # Simulate network delay
        logger.info(f"[MOCK SSH] Executing: usermod -L {username}")
        logger.info(f"[MOCK SSH] Executing: pkill -u {username}")
        await asyncio.sleep(0.5)
        logger.info(f"[MOCK SSH] Successfully locked user {username} on {server_ip}")
        return True
