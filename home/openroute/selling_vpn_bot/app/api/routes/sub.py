import base64
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from app.db.database import async_session_maker
from app.db.models import SshAccount
from app.services.account_types import ACCOUNT_TYPE_V2RAY
from app.services.connection_links import build_import_link

router = APIRouter()

@router.get("/{username}", response_class=PlainTextResponse)
async def get_subscription(username: str):
    async with async_session_maker() as session:
        result = await session.execute(
            select(SshAccount).where(SshAccount.ssh_username == username)
        )
        account = result.scalar_one_or_none()
        
        if not account or account.status != "active" or account.service_type != ACCOUNT_TYPE_V2RAY:
            raise HTTPException(status_code=404, detail="Subscription not found or inactive")
        
        # We use ssh_password because it holds the VLESS UUID
        vless_link = build_import_link(username, account.ssh_password, service_type=ACCOUNT_TYPE_V2RAY)
        
        # Base64 encode for standard subscription format
        encoded = base64.b64encode(vless_link.encode("utf-8")).decode("utf-8")
        return encoded
