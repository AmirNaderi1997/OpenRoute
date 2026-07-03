import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import httpx

from app.bot import bot, dp
from app.api.routes.callbacks import router as callbacks_router
from app.api.routes.webapp import router as webapp_router
from app.api.routes.admin_webapp import router as admin_webapp_router
from app.api.routes.payments import router as payments_router
from app.worker.scheduler import start_scheduler
from app.db.database import engine
from app.core.config import settings
from app.services.connection_links import build_vless_reality_link, normalize_reality_params
from app.services.account_types import ACCOUNT_TYPE_SSH, ACCOUNT_TYPE_V2RAY
from aiogram.types import MenuButtonWebApp, WebAppInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("main")
MENU_BUTTON_TEXT = "Open"


async def safe_bot_polling():
    """
    Wraps the aiogram bot polling in a try-except block.
    This ensures that transient Telegram API errors do not crash the entire FastAPI application.
    """
    try:
        logger.info("Initializing aiogram long-polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types(), handle_signals=False)
    except Exception as e:
        logger.error(f"Telegram Bot Polling encountered a critical error: {e}", exc_info=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Unified Application Lifecycle Manager
    Orchestrates the startup and teardown of the database, scheduler, and telegram bot.
    """
    # --- STARTUP SEQUENCE ---
    logger.info("Starting up FastAPI application...")
    
    # 0. Migrate Database Schema (lightweight startup safety net for prod)
    from sqlalchemy import text
    from app.db.models import Base
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE ssh_accounts ADD COLUMN IF NOT EXISTS max_connections INTEGER DEFAULT 1"))
            await conn.execute(text("ALTER TABLE ssh_accounts ADD COLUMN IF NOT EXISTS import_link VARCHAR"))
            await conn.execute(text("ALTER TABLE ssh_accounts ADD COLUMN IF NOT EXISTS payment_id INTEGER NULL"))
            await conn.execute(text("ALTER TABLE ssh_accounts ADD COLUMN IF NOT EXISTS service_type VARCHAR NOT NULL DEFAULT 'ssh'"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ssh_accounts_payment_id ON ssh_accounts(payment_id)"))
            await conn.execute(text("ALTER TABLE ssh_accounts ALTER COLUMN traffic_used_gb TYPE NUMERIC(12,6)"))
            await conn.execute(text("UPDATE ssh_accounts SET traffic_limit_gb = NULL"))
            await conn.execute(text("ALTER TABLE ssh_servers ADD COLUMN IF NOT EXISTS service_type VARCHAR NOT NULL DEFAULT 'ssh'"))
            await conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS service_type VARCHAR NULL"))
            await conn.execute(text("UPDATE ssh_accounts SET service_type = 'ssh' WHERE service_type IS NULL"))
            await conn.execute(text("UPDATE ssh_servers SET service_type = 'ssh' WHERE service_type IS NULL"))
            await conn.execute(text("UPDATE payments SET service_type = 'wallet' WHERE service_type IS NULL AND server_id IS NULL"))
            await conn.execute(text("UPDATE payments SET service_type = 'v2ray' WHERE service_type IS NULL AND server_id IS NOT NULL"))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS discount_codes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR UNIQUE NOT NULL,
                    percent_off INTEGER NOT NULL,
                    payment_method_scope VARCHAR NOT NULL DEFAULT 'all',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    is_used BOOLEAN NOT NULL DEFAULT FALSE,
                    used_by_user_id BIGINT NULL,
                    used_payment_id INTEGER NULL,
                    used_at TIMESTAMPTZ NULL,
                    created_by BIGINT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            await conn.execute(text("ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS payment_method_scope VARCHAR NOT NULL DEFAULT 'all'"))
            await conn.execute(text("ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS is_used BOOLEAN NOT NULL DEFAULT FALSE"))
            await conn.execute(text("ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS used_by_user_id BIGINT NULL"))
            await conn.execute(text("ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS used_payment_id INTEGER NULL"))
            await conn.execute(text("ALTER TABLE discount_codes ADD COLUMN IF NOT EXISTS used_at TIMESTAMPTZ NULL"))
        logger.info("Database migration (max_connections/import_link & clearing traffic limits) completed successfully.")
    except Exception as e:
        logger.error(f"Database migration failed: {e}")
    
    # Ensure default server exists in DB (representing "self" VPS)
    from sqlalchemy import select
    from app.db.database import async_session_maker
    from app.db.models import SshServer
    try:
        async with async_session_maker() as session:
            ssh_server = await session.scalar(select(SshServer).where(SshServer.service_type == ACCOUNT_TYPE_SSH).limit(1))
            if not ssh_server:
                logger.info("No SSH sales server registered. Creating default SSH server...")
                ssh_server = SshServer(
                    name="OpenRoute SSH Server",
                    ip_address=settings.REMOTE_VPN_HOST,
                    ssh_port=settings.REMOTE_VPN_SSH_PORT,
                    root_password=settings.REMOTE_VPN_ROOT_PASSWORD,
                    status="active",
                    service_type=ACCOUNT_TYPE_SSH,
                )
                session.add(ssh_server)

            v2ray_server = await session.scalar(select(SshServer).where(SshServer.service_type == ACCOUNT_TYPE_V2RAY).limit(1))
            if not v2ray_server:
                logger.info("No V2Ray sales server registered. Creating PasarGuard virtual server entry...")
                v2ray_server = SshServer(
                    name="PasarGuard V2Ray",
                    ip_address=settings.VLESS_TUNNEL_HOST,
                    ssh_port=settings.VLESS_TUNNEL_PORT,
                    root_password="managed-by-pasarguard",
                    status="active",
                    service_type=ACCOUNT_TYPE_V2RAY,
                )
                session.add(v2ray_server)

            await session.commit()
            logger.info("Default service entries verified successfully.")
    except Exception as e:
        logger.error(f"Failed to check/create default server: {e}", exc_info=True)
    
    # 1. Start the Scheduler
    logger.info("Starting AsyncIOScheduler...")
    scheduler = start_scheduler()
    
    # 2. Set the Telegram Menu Button.
    logger.info(f"Setting Telegram menu button '{MENU_BUTTON_TEXT}' to WebApp URL: {settings.MINIAPP_URL}")
    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=MENU_BUTTON_TEXT,
                web_app=WebAppInfo(url=settings.MINIAPP_URL)
            )
        )
        await bot.set_my_name(name="v2rayBundlenesse")
        logger.info("Telegram menu button set successfully.")
    except Exception as e:
        logger.error(f"Failed to set Telegram menu button: {e}", exc_info=True)
    
    # 3. Launch Telegram Bot Polling as a Background Task
    logger.info("Launching bot polling background task...")
    bot_task = asyncio.create_task(safe_bot_polling())
    
    yield  # Web Server starts serving requests here
    
    # --- SHUTDOWN SEQUENCE ---
    logger.info("Initiating graceful shutdown sequence...")
    
    # 1. Stop Telegram Polling & Close Session
    logger.info("Stopping aiogram polling...")
    await dp.stop_polling()
    if not bot_task.done():
        bot_task.cancel()
    
    logger.info("Closing Telegram Bot HTTP session...")
    await bot.session.close()
    
    # 2. Shutdown Scheduler
    logger.info("Shutting down AsyncIOScheduler...")
    scheduler.shutdown()
    
    # 3. Dispose Database Engine Pool
    logger.info("Disposing SQLAlchemy Engine pool...")
    await engine.dispose()
    
    logger.info("Application shutdown complete.")

app = FastAPI(lifespan=lifespan, title="VPN Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, strict configuration is recommended
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os
from fastapi.staticfiles import StaticFiles

# Include API Routers
app.include_router(callbacks_router, prefix="/api/v1")
app.include_router(webapp_router, prefix="/api/v1/webapp")
app.include_router(admin_webapp_router, prefix="/api/v1/admin/webapp")
app.include_router(payments_router, prefix="/api/v1/payments")


@app.get("/sub/{token}")
@app.get("/sub/{token}/{client_type}")
async def proxy_subscription(token: str, client_type: str | None = None, request: Request = None):
    suffix = f"/{client_type}" if client_type else ""
    target_url = f"{settings.PASARGUARD_API_BASE.rstrip('/')}/sub/{token}{suffix}"
    headers = dict(request.headers)
    headers.pop("host", None)
    
    async with httpx.AsyncClient(verify=False) as client:
        try:
            resp = await client.get(target_url, headers=headers, timeout=20.0)
            if resp.status_code != 200:
                return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers))
                
            content = resp.text
            
            # Try to decode from base64 to extract VLESS configurations
            import base64
            import urllib.parse
            
            try:
                # Pad base64 if needed
                padded_content = content.strip()
                missing_padding = len(padded_content) % 4
                if missing_padding:
                    padded_content += '=' * (4 - missing_padding)
                    
                decoded = base64.b64decode(padded_content).decode("utf-8")
                
                # Look for vless:// links
                vless_links = [line.strip() for line in decoded.splitlines() if line.strip().startswith("vless://")]
                
                if vless_links:
                    first_link = vless_links[0]
                    # Parse the link
                    parts = first_link.split("#", 1)
                    url_part = parts[0]
                    
                    url_str = url_part[8:] # remove vless://
                    user_host = url_str.split("@", 1)
                    if len(user_host) == 2:
                        uuid = user_host[0]
                        host_params = user_host[1].split("?", 1)
                        host_port = host_params[0]
                        query_str = host_params[1] if len(host_params) > 1 else ""
                        
                        host_port_parts = host_port.split(":")
                        original_port = int(host_port_parts[1]) if len(host_port_parts) > 1 else 443
                        
                        params = urllib.parse.parse_qs(query_str)
                        original_params = {k: v[0] for k, v in params.items() if v}
                        
                        # Look up username from PostgreSQL DB
                        from app.db.database import async_session_maker
                        from app.db.models import SshAccount
                        from sqlalchemy import select
                        
                        username = "V2Ray"
                        async with async_session_maker() as session:
                            stmt = select(SshAccount).where(SshAccount.import_link.like(f"%{token}%"))
                            acc = (await session.execute(stmt)).scalar_one_or_none()
                            if acc:
                                username = acc.ssh_username
                                
                        # List of candidate configurations: (address, port, sni, remark_suffix)
                        candidates = [
                            (settings.VLESS_TUNNEL_HOST, settings.VLESS_TUNNEL_PORT, "yahoo.com", "Tunnel-Yahoo"),
                            (settings.VLESS_TUNNEL_HOST, settings.VLESS_TUNNEL_PORT, "microsoft.com", "Tunnel-Microsoft"),
                            (settings.VLESS_TUNNEL_HOST, settings.VLESS_TUNNEL_PORT, "speedtest.net", "Tunnel-Speedtest"),
                            (settings.VLESS_TUNNEL_HOST, settings.VLESS_TUNNEL_PORT, "play.google.com", "Tunnel-GooglePlay"),
                            (settings.VLESS_TUNNEL_HOST, settings.VLESS_TUNNEL_PORT, "zoom.us", "Tunnel-Zoom"),
                            ("p.ipping.ir", settings.VLESS_TUNNEL_PORT, "yahoo.com", "Direct-Yahoo"),
                            ("p.ipping.ir", settings.VLESS_TUNNEL_PORT, "microsoft.com", "Direct-Microsoft"),
                            ("p.ipping.ir", settings.VLESS_TUNNEL_PORT, "speedtest.net", "Direct-Speedtest"),
                            ("p.ipping.ir", settings.VLESS_TUNNEL_PORT, "play.google.com", "Direct-GooglePlay"),
                            ("p.ipping.ir", settings.VLESS_TUNNEL_PORT, "zoom.us", "Direct-Zoom"),
                        ]
                        
                        # Concurrent reachability tests
                        async def test_tcp_port(h: str, p: int, t: float = 1.5) -> bool:
                            try:
                                r, w = await asyncio.wait_for(asyncio.open_connection(h, p), timeout=t)
                                w.close()
                                try:
                                    await w.wait_closed()
                                except Exception:
                                    pass
                                return True
                            except Exception:
                                return False

                        async def test_candidate(addr: str, prt: int, sn: str) -> bool:
                            res = await asyncio.gather(
                                test_tcp_port(addr, prt, 1.5),
                                test_tcp_port(sn, 443, 1.5),
                                return_exceptions=True
                            )
                            return all(x is True for x in res)

                        tasks = [test_candidate(c[0], c[1], c[2]) for c in candidates]
                        reachability = await asyncio.gather(*tasks)
                        
                        logger.info(f"Reachability results: { {c[3]: ok for c, ok in zip(candidates, reachability)} }")
                        
                        working_candidates = [candidates[i] for i, ok in enumerate(reachability) if ok]
                        
                        # Guarantee at least 5 links
                        selected = list(working_candidates)
                        if len(selected) < 5:
                            for idx, ok in enumerate(reachability):
                                if not ok:
                                    selected.append(candidates[idx])
                                    if len(selected) >= 5:
                                        break
                                        
                        # Generate final VLESS links
                        generated_links = []
                        for addr, prt, sni, suffix in selected:
                            link_params = normalize_reality_params(original_params, sni=sni)
                            remark = f"{username} | {suffix}"
                            vless_link = build_vless_reality_link(
                                uuid,
                                addr,
                                prt,
                                remark=remark,
                                sni=sni,
                                base_params=link_params,
                            )
                            generated_links.append(vless_link)
                            
                        new_content = "\n".join(generated_links)
                        encoded_content = base64.b64encode(new_content.encode("utf-8")).decode("utf-8")
                        
                        response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")}
                        return Response(content=encoded_content, status_code=200, headers=response_headers)
            except Exception as parse_ex:
                logger.error(f"Error parsing/generating custom subscription links: {parse_ex}", exc_info=True)
                
            # Fallback replacement logic if base64 decoding/parsing fails
            content = content.replace("p.ipping.ir:20443", f"{settings.VLESS_TUNNEL_HOST}:{settings.VLESS_TUNNEL_PORT}")
            content = content.replace("212.74.39.79:20443", f"{settings.VLESS_TUNNEL_HOST}:{settings.VLESS_TUNNEL_PORT}")
            content = content.replace("p.ipping.ir", settings.VLESS_TUNNEL_HOST)
            content = content.replace("212.74.39.79", settings.VLESS_TUNNEL_HOST)
            
            response_headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-encoding", "transfer-encoding")}
            return Response(content=content, status_code=resp.status_code, headers=response_headers)
        except Exception as e:
            logger.error(f"Subscription proxy failed: {e}")
            return Response(content="Subscription temporarily unavailable", status_code=503)


# Serve React Mini App Frontend
if os.path.isdir("webapp/dist"):
    app.mount("/", StaticFiles(directory="webapp/dist", html=True), name="frontend")
    logger.info("Webapp frontend mounted from webapp/dist/ — Mini App will be served at /")
else:
    logger.warning("webapp/dist/ directory not found — Mini App frontend will NOT be served! Run 'npm run build' in webapp/ directory.")

if __name__ == "__main__":
    ssl_cert_path = os.getenv("SSL_CERT_PATH")
    ssl_key_path = os.getenv("SSL_KEY_PATH")
    
    uvicorn_kwargs = {
        "app": "app.main:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": settings.ENVIRONMENT != "production"
    }
    
    if ssl_cert_path and ssl_key_path and os.path.exists(ssl_cert_path) and os.path.exists(ssl_key_path):
        uvicorn_kwargs["ssl_certfile"] = ssl_cert_path
        uvicorn_kwargs["ssl_keyfile"] = ssl_key_path
        logger.info(f"Starting Uvicorn with SSL (HTTPS) enabled. Cert: {ssl_cert_path}")
    else:
        logger.info("Starting Uvicorn with HTTP (No SSL).")
        
    uvicorn.run(**uvicorn_kwargs)
