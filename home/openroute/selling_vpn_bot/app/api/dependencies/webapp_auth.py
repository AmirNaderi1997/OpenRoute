import hashlib
import hmac
import json
import urllib.parse
from fastapi import Header, HTTPException, Depends, status
from app.core.config import settings

async def webapp_auth(telegram_web_app_data: str = Header(..., alias="Telegram-Web-App-Data")):
    """
    FastAPI dependency to cryptographically validate Telegram Web App initData.
    """
    if not telegram_web_app_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Telegram Web App Data"
        )
        
    try:
        # Parse the query string
        parsed_data = urllib.parse.parse_qsl(telegram_web_app_data, keep_blank_values=True)
        data_dict = dict(parsed_data)
        
        # Extract the hash and remove it from the dict
        received_hash = data_dict.pop('hash', None)
        if not received_hash:
            raise ValueError("No hash found in data")

        # Sort the remaining data alphabetically by key
        sorted_keys = sorted(data_dict.keys())
        data_check_array = [f"{k}={data_dict[k]}" for k in sorted_keys]
        data_check_string = "\n".join(data_check_array)

        # Compute the secret key: HMAC-SHA256 of the BOT_TOKEN with "WebAppData" as the key
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=settings.BOT_TOKEN.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()

        # Compute the final hash
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        if hmac.compare_digest(calculated_hash, received_hash):
            # Valid signature, return the parsed user JSON if available
            user_json_str = data_dict.get('user')
            if user_json_str:
                return json.loads(user_json_str)
            return {"valid": True}
        else:
            raise ValueError("Invalid hash signature")

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Telegram Data: {str(e)}"
        )

from app.db.database import async_session_maker
from app.db.models import User

async def admin_webapp_required(user_data: dict = Depends(webapp_auth)) -> dict:
    """
    Dependency that enforces the authenticated Telegram Web App user
    to have Admin privileges in the database.
    """
    user_id = user_data.get("id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User ID not found in data")
        
    async with async_session_maker() as session:
        user = await session.get(User, user_id)
        if not user or not user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Admin privileges required."
            )
            
    return user_data
