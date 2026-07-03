from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/servers/webhook/session")
async def ssh_session_webhook(payload: dict):
    # Expected payload: {"server_ip": "...", "username": "...", "remote_ip": "...", "event": "open_session|close_session"}
    server_ip = payload.get("server_ip")
    username = payload.get("username")
    event = payload.get("event")
    
    # TODO: Log this to the database, maybe update user's last_login or active_sessions count
    return {"status": "success"}
