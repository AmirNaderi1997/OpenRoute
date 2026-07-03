import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from app.db.database import async_session_maker
from app.db.models import SshServer, SshAccount
from app.services.account_types import ACCOUNT_TYPE_SSH
from app.services.ssh.linux import LinuxSSHManager
from app.services.ssh.remote_provisioner import RemoteProvisionerClient
from app.services.ssh_account_service import lock_remote_account
from app.worker.backups import run_database_backup
from app.worker.seo_bot import run_auto_seo_updater
from app.bot import bot

logger = logging.getLogger(__name__)

async def check_expired_accounts():
    """
    Checks the database for expired SSH accounts and traffic limits.
    Locks the user on the server via LinuxSSHManager, updates DB status to 'expired',
    and sends a notification to the user via Telegram.
    """
    logger.info("Running scheduled task: check_expired_accounts")
    async with async_session_maker() as session:
        # 1. Fetch active servers
        servers = (await session.scalars(select(SshServer).where(SshServer.status == "active"))).all()
        
        for server in servers:
            # 2. Fetch active accounts for this server
            accounts = (await session.scalars(
                select(SshAccount).where(SshAccount.server_id == server.id, SshAccount.status == "active")
            )).all()
            
            for account in accounts:
                # 3. Read Traffic
                if account.service_type == ACCOUNT_TYPE_SSH:
                    ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
                    bytes_used = await ssh_manager.get_user_traffic(server.ip_address, account.ssh_username)
                else:
                    provisioner = RemoteProvisionerClient()
                    bytes_used = await provisioner.get_user_traffic(account.ssh_username)
                gb_used = bytes_used / (1024 ** 3)
                account.traffic_used_gb = gb_used
                
                # 4. Check Limits
                expired_by_time = account.expires_at.timestamp() <= account.expires_at.now().timestamp() # Simplified time check
                expired_by_traffic = account.traffic_limit_gb is not None and gb_used >= account.traffic_limit_gb
                
                if expired_by_time or expired_by_traffic:
                    await lock_remote_account(session, account)
                    account.status = "expired"
                    # TODO: await bot.send_message(account.user_id, "Your SSH account has expired or reached traffic limit.")
                    logger.info(f"Account {account.ssh_username} locked (Traffic: {gb_used}GB)")
                    
        await session.commit()

def start_scheduler():
    scheduler = AsyncIOScheduler()
    # Run every hour at the top of the hour
    scheduler.add_job(check_expired_accounts, CronTrigger(minute="0"))
    # Run every day at 3:00 AM
    scheduler.add_job(
        run_database_backup, 
        trigger=CronTrigger(hour=3, minute=0),
        id="daily_pg_backup",
        replace_existing=True
    )
    # Run daily SEO Updater at 4:00 AM
    scheduler.add_job(
        run_auto_seo_updater,
        trigger=CronTrigger(hour=4, minute=0),
        id="daily_seo_updater",
        replace_existing=True
    )
    scheduler.start()
    logger.info("APScheduler started")
    return scheduler
