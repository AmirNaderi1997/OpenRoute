import json
import logging
import os
import shlex
from datetime import date, datetime

import asyncssh

from app.core.config import settings

logger = logging.getLogger(__name__)


class RemoteProvisionerClient:
    def __init__(self) -> None:
        self.host = settings.REMOTE_VPN_HOST
        self.port = settings.REMOTE_VPN_SSH_PORT
        self.username = settings.REMOTE_VPN_ROOT_USER
        self.password = settings.REMOTE_VPN_ROOT_PASSWORD
        self.private_key_path = settings.SSH_PRIVATE_KEY_PATH
        self.manager_path = settings.REMOTE_VPN_MANAGER_PATH
        self.public_domain = settings.REMOTE_VPN_DOMAIN
        self.public_port = settings.REMOTE_VPN_PUBLIC_PORT

    def _connection_options(self) -> dict:
        options = {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "known_hosts": None,
        }
        if self.private_key_path and os.path.exists(self.private_key_path):
            options["client_keys"] = [self.private_key_path]
        elif self.password:
            options["password"] = self.password
        return options

    async def _run_json(self, args: list[str]) -> dict:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        command = f"python3 {shlex.quote(self.manager_path)} {quoted}"
        try:
            async with asyncssh.connect(**self._connection_options()) as conn:
                result = await conn.run(command)
        except Exception as exc:
            logger.error("[RemoteProvisioner] SSH call failed: %s", exc)
            raise

        if result.exit_status != 0:
            stderr = (result.stderr or "").strip()
            logger.error("[RemoteProvisioner] command failed: %s", stderr)
            raise RuntimeError(stderr or "remote_provisioner_failed")

        try:
            return json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            logger.error("[RemoteProvisioner] invalid JSON response: %s", result.stdout)
            raise RuntimeError("invalid_remote_json") from exc

    async def create_account(
        self,
        username: str,
        password: str,
        expire_days: int,
        max_connections: int,
    ) -> dict:
        return await self._run_json(
            [
                "create",
                "--username",
                username,
                "--password",
                password,
                "--expire-days",
                str(expire_days),
                "--domain",
                self.public_domain,
                "--port",
                str(self.public_port),
                "--max-connections",
                str(max_connections),
            ]
        )

    async def renew_account(self, username: str, expire_at: datetime) -> dict:
        return await self._run_json(
            [
                "renew",
                "--username",
                username,
                "--expire-date",
                expire_at.date().isoformat(),
            ]
        )

    async def lock_account(self, username: str) -> dict:
        return await self._run_json(["lock", "--username", username])

    async def change_password(self, username: str, password: str) -> dict:
        return await self._run_json(
            [
                "passwd",
                "--username",
                username,
                "--password",
                password,
            ]
        )

    async def get_user_traffic(self, username: str) -> int:
        payload = await self._run_json(["traffic", "--username", username])
        return int(payload.get("bytes_used", 0))

    async def user_exists(self, username: str) -> bool:
        payload = await self._run_json(["exists", "--username", username])
        return bool(payload.get("exists"))
