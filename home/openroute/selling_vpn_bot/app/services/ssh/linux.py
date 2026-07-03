import asyncssh
import logging
import json
import os
from app.services.ssh.base import BaseSSHManager

logger = logging.getLogger(__name__)

class LinuxSSHManager(BaseSSHManager):
    """
    Real implementation of BaseSSHManager using asyncssh.
    Connects to the remote Linux server to provision users, lock them, and read traffic.
    """

    def __init__(self, ssh_port: int = 22, root_password: str = None, private_key_path: str = None):
        self.ssh_port = ssh_port
        self.root_password = root_password
        self.private_key_path = private_key_path

    async def _run_command(self, server_ip: str, command: str) -> str:
        """Helper to run a command via asyncssh"""
        conn_options = {
            "host": server_ip,
            "port": self.ssh_port,
            "username": "root",
            "known_hosts": None # For production, configure known_hosts properly
        }
        if self.private_key_path and os.path.exists(self.private_key_path):
            conn_options["client_keys"] = [self.private_key_path]
        elif self.root_password:
            conn_options["password"] = self.root_password
            
        try:
            async with asyncssh.connect(**conn_options) as conn:
                result = await conn.run(command)
                if result.exit_status != 0:
                    logger.error(f"[SSH] Command failed on {server_ip}: {command} -> {result.stderr}")
                    raise Exception(f"Command failed on VPS: {result.stderr}")
                return result.stdout.strip()
        except Exception as e:
            logger.error(f"[SSH] Connection/Execution error to {server_ip}: {e}")
            raise e

    async def create_system_user(self, server_ip: str, username: str, password: str, expire_days: int) -> bool:
        try:
            # Create user without shell
            cmd_add = f"useradd -M -s /bin/false {username}"
            await self._run_command(server_ip, cmd_add)
            
            # Set password
            cmd_pass = f"echo '{username}:{password}' | chpasswd"
            await self._run_command(server_ip, cmd_pass)
            
            # Set expiry
            cmd_expire = f"chage -E $(date -d '+{expire_days} days' +%Y-%m-%d) {username}"
            await self._run_command(server_ip, cmd_expire)
            
            # Setup traffic tracking (requires setup_user_traffic.sh to be deployed in /usr/local/bin)
            cmd_uid = f"id -u {username}"
            uid = await self._run_command(server_ip, cmd_uid)
            if uid:
                cmd_traffic = f"/usr/local/bin/setup_user_traffic.sh {username} {uid}"
                await self._run_command(server_ip, cmd_traffic)
                
            logger.info(f"[SSH] Successfully created user {username} on {server_ip}")
            return True
        except Exception as e:
            logger.error(f"[SSH] create_system_user failed for {username}: {e}")
            return False

    async def lock_user(self, server_ip: str, username: str) -> bool:
        try:
            cmd_lock = f"usermod -L {username}"
            await self._run_command(server_ip, cmd_lock)
            
            cmd_kill = f"pkill -u {username} || true"
            await self._run_command(server_ip, cmd_kill)
            
            logger.info(f"[SSH] Successfully locked user {username} on {server_ip}")
            return True
        except Exception as e:
            logger.error(f"[SSH] lock_user failed for {username}: {e}")
            return False

    async def get_user_traffic(self, server_ip: str, username: str) -> int:
        try:
            cmd_read = f"/usr/local/bin/read_user_traffic.sh {username}"
            output = await self._run_command(server_ip, cmd_read)
            if output:
                try:
                    data = json.loads(output)
                    return int(data.get("bytes_used", 0))
                except json.JSONDecodeError:
                    logger.error(f"[SSH] Failed to parse traffic JSON for {username}")
        except Exception as e:
            logger.error(f"[SSH] get_user_traffic failed for {username}: {e}")
        return 0
