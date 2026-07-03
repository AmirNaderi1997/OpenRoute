import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.database import async_session_maker
from app.db.models import SshAccount
from app.services.connection_links import build_import_link
from app.services.ssh.remote_provisioner import RemoteProvisionerClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    provisioner = RemoteProvisionerClient()
    async with async_session_maker() as session:
        accounts = (await session.scalars(select(SshAccount).where(SshAccount.status == "active"))).all()
        migrated = 0
        for account in accounts:
            try:
                if await provisioner.user_exists(account.ssh_username):
                    await provisioner.renew_account(account.ssh_username, account.expires_at)
                else:
                    expires_at = account.expires_at
                    if expires_at.tzinfo is None:
                        expires_at = expires_at.replace(tzinfo=timezone.utc)
                    remaining_days = max(1, (expires_at - datetime.now(timezone.utc)).days or 1)
                    await provisioner.create_account(
                        username=account.ssh_username,
                        password=account.ssh_password,
                        expire_days=remaining_days,
                        max_connections=account.max_connections,
                    )
                account.import_link = build_import_link(account.ssh_username, account.ssh_password)
                migrated += 1
            except Exception as exc:
                logger.error("Failed to migrate %s: %s", account.ssh_username, exc)
        await session.commit()
    logger.info("Migrated %s active accounts", migrated)


if __name__ == "__main__":
    asyncio.run(main())
