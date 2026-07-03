import asyncio
import json
import time
from decimal import Decimal
from sqlalchemy import select
from app.db.database import async_session_maker
from app.db.models import User, Payment, SshServer, SshAccount
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY
from app.services.payment_pipeline import execute_payment_approval
from app.services.ssh.linux import LinuxSSHManager
from app.services.ssh_account_service import _get_pg_token
from pasarguard import PasarguardAPI
from app.core.config import settings

async def approve_and_verify(service_type: str, server: SshServer, user_id: int):
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user:
            user = User(id=user_id, username=f"test_{service_type}_{user_id}", balance=Decimal("0.00"))
            session.add(user)
            await session.commit()
        payment = Payment(
            user_id=user_id,
            server_id=server.id,
            amount=Decimal("98000.00"),
            currency="IRR",
            payment_method="card_to_card",
            gateway_tx_id=f"test_{service_type}_{int(time.time())}|payable_toman=98000",
            status="pending",
            service_type=service_type,
        )
        session.add(payment)
        await session.commit()
        payment_id = payment.id
        before_balance = float(user.balance or 0)

    success, result = await execute_payment_approval(payment_id)

    async with async_session_maker() as session:
        payment = await session.get(Payment, payment_id)
        user = await session.get(User, user_id)
        account = await session.scalar(select(SshAccount).where(SshAccount.payment_id == payment_id))
        summary = {
            "payment_id": payment_id,
            "service_type": service_type,
            "success": success,
            "result": result,
            "payment_status": payment.status if payment else None,
            "user_balance_before": before_balance,
            "user_balance_after": float(user.balance or 0) if user else None,
            "account_username": account.ssh_username if account else None,
            "account_service_type": account.service_type if account else None,
            "import_link": account.import_link if account else None,
        }
        if not account:
            return summary
        if service_type == ACCOUNT_TYPE_SSH:
            manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
            try:
                uid = await manager._run_command(server.ip_address, f"id -u {account.ssh_username}")
                expiry = await manager._run_command(server.ip_address, f"chage -l {account.ssh_username}")
                summary["remote_check"] = {"uid": uid, "expiry": expiry.splitlines()[:2]}
            except Exception as exc:
                summary["remote_check_error"] = str(exc)
        else:
            try:
                async with PasarguardAPI(base_url=settings.PASARGUARD_API_BASE, verify=False, timeout=30.0) as api:
                    token = await _get_pg_token(api)
                    pg_user = await api.get_user_by_username(account.ssh_username, token=token)
                    summary["remote_check"] = {
                        "username": getattr(pg_user, "username", None),
                        "subscription_url": getattr(pg_user, "subscription_url", None),
                    }
            except Exception as exc:
                summary["remote_check_error"] = str(exc)
        return summary

async def main():
    async with async_session_maker() as session:
        ssh_server = await session.scalar(select(SshServer).where(SshServer.service_type == ACCOUNT_TYPE_SSH, SshServer.status == "active").order_by(SshServer.id.asc()))
        v2ray_server = await session.scalar(select(SshServer).where(SshServer.service_type == ACCOUNT_TYPE_V2RAY, SshServer.status == "active").order_by(SshServer.id.asc()))
    if not ssh_server or not v2ray_server:
        raise RuntimeError("required servers not found")
    ssh_result = await approve_and_verify(ACCOUNT_TYPE_SSH, ssh_server, 990001001)
    v2ray_result = await approve_and_verify(ACCOUNT_TYPE_V2RAY, v2ray_server, 990001002)
    print(json.dumps({"ssh": ssh_result, "v2ray": v2ray_result}, ensure_ascii=False, indent=2, default=str))

asyncio.run(main())
