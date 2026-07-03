import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.database import Base
from app.db.models import SshAccount, SshServer, User
from app.services.connection_links import build_import_link
from app.services.ssh_account_service import create_remote_account


class SshAccountServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.session_maker = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with self.session_maker() as session:
            session.add(User(id=10001, username="buyer"))
            session.add(SshServer(id=1, name="srv-1", ip_address="127.0.0.1", ssh_port=22, root_password="secret"))
            await session.commit()

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_create_remote_account_persists_link_from_account_credentials(self) -> None:
        remote_payload = {
            "expires_at": "2026-07-17T00:00:00+00:00",
            "import_link": "ssh://shared-user:shared-pass@shared-host:443#shared",
        }

        with patch(
            "app.services.ssh_account_service.RemoteProvisionerClient.create_account",
            new=AsyncMock(return_value=remote_payload),
        ), patch.object(settings, "VPN_PUBLIC_HOST", "panel.example.com"), patch.object(settings, "VPN_PUBLIC_PORT", 443):
            async with self.session_maker() as session:
                account, import_link = await create_remote_account(
                    session=session,
                    user_id=10001,
                    server_id=1,
                    duration_days=30,
                    max_connections=1,
                    payment_id=77,
                )
                await session.commit()

                stored_account = await session.get(SshAccount, account.id)

        expected_link = build_import_link(stored_account.ssh_username, stored_account.ssh_password)
        self.assertEqual(import_link, expected_link)
        self.assertEqual(stored_account.import_link, expected_link)
        self.assertEqual(stored_account.payment_id, 77)
        self.assertNotEqual(stored_account.import_link, remote_payload["import_link"])


if __name__ == "__main__":
    unittest.main()
