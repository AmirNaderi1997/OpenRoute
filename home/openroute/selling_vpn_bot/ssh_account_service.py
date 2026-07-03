import secrets
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import SshAccount, SshServer
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY
from app.services.connection_links import get_connection_details
from app.services.ssh.linux import LinuxSSHManager
from pasarguard import PasarguardAPI, Tools, UserCreate, UserModify, UserStatus, UserStatusToggle


async def _get_pg_token(api: PasarguardAPI) -> str:
    token = await api.get_token(
        username=settings.PASARGUARD_ADMIN_USERNAME,
        password=settings.PASARGUARD_ADMIN_PASSWORD,
    )
    return token.access_token


async def _get_active_group_ids(api: PasarguardAPI, token: str) -> list[int]:
    groups = await api.get_all_groups(token=token)
    group_rows = getattr(groups, "groups", None) or []
    group_ids: list[int] = []
    for group in group_rows:
        group_id = getattr(group, "id", None)
        if group_id is not None:
            group_ids.append(int(group_id))
    return group_ids


def _get_prefix(service_type: str) -> str:
    if service_type == ACCOUNT_TYPE_SSH:
        return settings.SSH_VPN_USERNAME_PREFIX
    return settings.REMOTE_VPN_USERNAME_PREFIX


def _extract_suffix(username: str, prefix: str) -> int | None:
    if not username.startswith(prefix):
        return None
    suffix = username[len(prefix):]
    if not suffix.isdigit():
        return None
    return int(suffix)


async def get_next_username(session: AsyncSession, service_type: str) -> str:
    prefix = _get_prefix(service_type)
    usernames = (await session.scalars(select(SshAccount.ssh_username))).all()
    next_number = 1001
    for username in usernames:
        value = _extract_suffix(username, prefix)
        if value is not None and value >= next_number:
            next_number = value + 1
    return f"{prefix}{next_number}"


def generate_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_v2ray_account(
    session: AsyncSession,
    user_id: int,
    server_id: int,
    duration_days: int,
    max_connections: int,
    payment_id: int | None = None,
    data_limit_gb: int | None = None,
) -> tuple[SshAccount, str]:
    username = await get_next_username(session, ACCOUNT_TYPE_V2RAY)

    async with PasarguardAPI(base_url=settings.PASARGUARD_API_BASE, verify=False, timeout=30.0) as api:
        token = await _get_pg_token(api)
        user_response = await api.create_user_in_all_groups(
            UserCreate(
                username=username,
                status=UserStatus.ACTIVE,
                expire=Tools.days(duration_days),
                data_limit=Tools.gb(data_limit_gb) if data_limit_gb else None,
                note=f"Created by bot for user {user_id}",
            ),
            token=token,
        )

        active_group_ids = await _get_active_group_ids(api, token)
        if active_group_ids:
            try:
                await api.modify_user(
                    username=username,
                    user=UserModify(group_ids=active_group_ids),
                    token=token,
                )
            except Exception:
                pass

        vless_id = ""
        if user_response.proxy_settings and user_response.proxy_settings.vless:
            vless_id = user_response.proxy_settings.vless.id or ""

        sub_url = user_response.subscription_url or ""
        if sub_url.startswith("http"):
            import_link = sub_url
        elif sub_url:
            import_link = f"{settings.PASARGUARD_API_BASE.rstrip('/')}{sub_url}"
        else:
            import_link = f"{settings.PASARGUARD_API_BASE.rstrip('/')}/sub/{username}"

        if isinstance(user_response.expire, (int, float)):
            expires_at = datetime.fromtimestamp(user_response.expire, tz=timezone.utc)
        else:
            expires_at = user_response.expire or (datetime.now(timezone.utc) + timedelta(days=duration_days))

    account = SshAccount(
        user_id=user_id,
        server_id=server_id,
        payment_id=payment_id,
        ssh_username=username,
        ssh_password=vless_id,
        import_link=import_link,
        duration_days=duration_days,
        traffic_limit_gb=data_limit_gb,
        traffic_used_gb=0.0,
        expires_at=expires_at,
        status="active",
        max_connections=max_connections,
        service_type=ACCOUNT_TYPE_V2RAY,
    )
    session.add(account)
    await session.flush()
    return account, import_link


async def create_ssh_account(
    session: AsyncSession,
    user_id: int,
    server_id: int,
    duration_days: int,
    max_connections: int,
    payment_id: int | None = None,
    data_limit_gb: int | None = None,
) -> tuple[SshAccount, str]:
    server = await session.get(SshServer, server_id)
    if not server:
        raise RuntimeError("SSH server not found")

    username = await get_next_username(session, ACCOUNT_TYPE_SSH)
    password = generate_password()
    ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
    success = await ssh_manager.create_system_user(server.ip_address, username, password, duration_days)
    if not success:
        raise RuntimeError(f"Failed to create Linux SSH account {username}")

    expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
    connection = get_connection_details(
        username,
        password,
        service_type=ACCOUNT_TYPE_SSH,
    )
    import_link = str(connection["import_link"])

    account = SshAccount(
        user_id=user_id,
        server_id=server_id,
        payment_id=payment_id,
        ssh_username=username,
        ssh_password=password,
        import_link=import_link,
        duration_days=duration_days,
        traffic_limit_gb=data_limit_gb,
        traffic_used_gb=0.0,
        expires_at=expires_at,
        status="active",
        max_connections=max_connections,
        service_type=ACCOUNT_TYPE_SSH,
    )
    session.add(account)
    await session.flush()
    return account, import_link


async def create_remote_account(
    session: AsyncSession,
    user_id: int,
    server_id: int,
    duration_days: int,
    max_connections: int,
    payment_id: int | None = None,
    data_limit_gb: int | None = None,
    service_type: str = ACCOUNT_TYPE_V2RAY,
) -> tuple[SshAccount, str]:
    if service_type == ACCOUNT_TYPE_SSH:
        return await create_ssh_account(
            session=session,
            user_id=user_id,
            server_id=server_id,
            duration_days=duration_days,
            max_connections=max_connections,
            payment_id=payment_id,
            data_limit_gb=data_limit_gb,
        )
    return await create_v2ray_account(
        session=session,
        user_id=user_id,
        server_id=server_id,
        duration_days=duration_days,
        max_connections=max_connections,
        payment_id=payment_id,
        data_limit_gb=data_limit_gb,
    )


async def renew_v2ray_account(account: SshAccount, duration_days: int = 30) -> tuple[datetime, str]:
    now = datetime.now(timezone.utc)
    current_expiry = account.expires_at
    if current_expiry.tzinfo is None:
        current_expiry = current_expiry.replace(tzinfo=timezone.utc)
    base = current_expiry if current_expiry > now else now
    new_expiry = base + timedelta(days=duration_days)

    async with PasarguardAPI(base_url=settings.PASARGUARD_API_BASE, verify=False, timeout=30.0) as api:
        token = await _get_pg_token(api)
        await api.modify_user(
            username=account.ssh_username,
            user=UserModify(expire=int(new_expiry.timestamp()), status=UserStatus.ACTIVE),
            token=token,
        )

    account.expires_at = new_expiry
    account.status = "active"
    return new_expiry, str(account.import_link or "")


async def renew_ssh_account(
    session: AsyncSession,
    account: SshAccount,
    duration_days: int = 30,
) -> tuple[datetime, str]:
    server = await session.get(SshServer, account.server_id)
    if not server:
        raise RuntimeError("SSH server not found")

    now = datetime.now(timezone.utc)
    current_expiry = account.expires_at
    if current_expiry.tzinfo is None:
        current_expiry = current_expiry.replace(tzinfo=timezone.utc)
    base = current_expiry if current_expiry > now else now
    new_expiry = base + timedelta(days=duration_days)

    ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
    expire_cmd = f"chage -E {new_expiry.date().isoformat()} {account.ssh_username}"
    await ssh_manager._run_command(server.ip_address, expire_cmd)

    account.expires_at = new_expiry
    account.status = "active"
    return new_expiry, str(account.import_link or "")


async def renew_remote_account(
    session: AsyncSession,
    account: SshAccount,
    duration_days: int = 30,
) -> tuple[datetime, str]:
    if account.service_type == ACCOUNT_TYPE_SSH:
        return await renew_ssh_account(session, account, duration_days=duration_days)
    return await renew_v2ray_account(account, duration_days=duration_days)


async def lock_v2ray_account(account: SshAccount) -> None:
    async with PasarguardAPI(base_url=settings.PASARGUARD_API_BASE, verify=False, timeout=30.0) as api:
        token = await _get_pg_token(api)
        await api.set_user_disabled(
            username=account.ssh_username,
            status=UserStatusToggle(disabled=True),
            token=token,
        )
    account.status = "disabled"


async def lock_ssh_account(session: AsyncSession, account: SshAccount) -> None:
    server = await session.get(SshServer, account.server_id)
    if not server:
        raise RuntimeError("SSH server not found")

    ssh_manager = LinuxSSHManager(ssh_port=server.ssh_port, root_password=server.root_password)
    await ssh_manager.lock_user(server.ip_address, account.ssh_username)
    account.status = "disabled"


async def lock_remote_account(session: AsyncSession, account: SshAccount) -> None:
    if account.service_type == ACCOUNT_TYPE_SSH:
        await lock_ssh_account(session, account)
        return
    await lock_v2ray_account(account)
