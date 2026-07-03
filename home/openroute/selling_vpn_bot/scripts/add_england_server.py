import asyncio
from sqlalchemy import select
from app.db.database import async_session_maker
from app.db.models import SshServer

async def main():
    async with async_session_maker() as session:
        # Check if already exists
        existing = await session.scalar(select(SshServer).where(SshServer.ip_address == "212.74.39.164"))
        if existing:
            print("Server 212.74.39.164 already exists.")
            return

        server = SshServer(
            name="England VPS",
            ip_address="212.74.39.164",
            ssh_port=22,
            root_password="1272510662",
            status="active"
        )
        session.add(server)
        await session.commit()
        print("Successfully added England VPS to database.")

if __name__ == "__main__":
    asyncio.run(main())
