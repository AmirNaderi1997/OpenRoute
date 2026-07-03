import asyncio
from sqlalchemy import delete, select
from app.db.database import async_session_maker
from app.db.models import SshServer, Payment, SshAccount

async def main():
    async with async_session_maker() as session:
        # First find the mock servers
        servers = (await session.scalars(select(SshServer).where(SshServer.name == "E2E Simulation Node"))).all()
        for server in servers:
            # Delete associated payments and accounts
            await session.execute(delete(Payment).where(Payment.server_id == server.id))
            await session.execute(delete(SshAccount).where(SshAccount.server_id == server.id))
            # Now delete the server
            await session.delete(server)
            
        await session.commit()
        print("Cleanup successful")

if __name__ == "__main__":
    asyncio.run(main())
