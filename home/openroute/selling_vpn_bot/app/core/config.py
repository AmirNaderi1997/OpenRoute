from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str = "YOUR_BOT_TOKEN_HERE"
    BOT_USERNAME: str = "getopenroutebot"
    SUPERADMIN_USERNAME: str = "admin"
    SUPERADMIN_PASSWORD: str = "supersecretpassword"
    ENVIRONMENT: str = "development"
    MANAGER_GROUP_ID: str | None = None
    
    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # Security
    SSH_PRIVATE_KEY_PATH: str | None = None

    APP_BASE_URL: str = "https://openroute.ir"
    VPN_PUBLIC_HOST: str | None = "openroute.ir"
    VPN_PUBLIC_PORT: int = 443
    VPN_WS_PATH: str = ""
    VPN_SECURITY: str = "ssh"
    MINIAPP_VERSION: str = "7"
    REMOTE_VPN_HOST: str = "212.74.39.224"
    REMOTE_VPN_SSH_PORT: int = 443
    REMOTE_VPN_ROOT_USER: str = "root"
    REMOTE_VPN_ROOT_PASSWORD: str = ""
    REMOTE_VPN_DOMAIN: str = "openroute.ir"
    REMOTE_VPN_PUBLIC_PORT: int = 443
    REMOTE_VPN_USERNAME_PREFIX: str = "openroute_"
    SSH_VPN_USERNAME_PREFIX: str = "ssh_"
    REMOTE_VPN_MANAGER_PATH: str = "/opt/openroute/remote_ssh_vpn_manager.py"
    
    NOWPAYMENTS_API_KEY: str | None = None
    NOWPAYMENTS_IPN_SECRET: str | None = None

    # PasarGuard configuration settings
    PASARGUARD_API_BASE: str = "https://127.0.0.1:8080"
    PASARGUARD_ADMIN_USERNAME: str = "admin"
    PASARGUARD_ADMIN_PASSWORD: str = "YOUR_PASARGUARD_PASSWORD"
    PASARGUARD_GROUP_ID: str | None = None   # PasarGuard group to auto-assign new users
    VLESS_TUNNEL_HOST: str = "pi.ipping.ir"
    VLESS_TUNNEL_PORT: int = 20443
    
    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    @property
    def APP_BASE_URL_NORMALIZED(self) -> str:
        return self.APP_BASE_URL.rstrip("/")

    @property
    def VPN_HOST(self) -> str:
        if self.VPN_PUBLIC_HOST:
            return self.VPN_PUBLIC_HOST
        parsed = urlparse(self.APP_BASE_URL_NORMALIZED)
        return parsed.hostname or "openroute.ir"

    @property
    def VPN_WS_PATH_NORMALIZED(self) -> str:
        if not self.VPN_WS_PATH:
            return ""
        if self.VPN_WS_PATH.startswith("/"):
            return self.VPN_WS_PATH
        return f"/{self.VPN_WS_PATH}"

    @property
    def MINIAPP_URL(self) -> str:
        # Telegram menu/webapp URLs are sometimes fragile with querystrings.
        # Keep it stable; cache-busting is handled by the frontend hashed assets.
        return f"{self.APP_BASE_URL_NORMALIZED}/panel/"


    @property
    def NOWPAYMENTS_WEBHOOK_URL(self) -> str:
        return f"{self.APP_BASE_URL_NORMALIZED}/api/v1/payments/nowpayments/webhook"

    @property
    def NOWPAYMENTS_SUCCESS_URL(self) -> str:
        return f"{self.APP_BASE_URL_NORMALIZED}/?payment=success"

    @property
    def NOWPAYMENTS_CANCEL_URL(self) -> str:
        return f"{self.APP_BASE_URL_NORMALIZED}/?payment=cancelled"

    @property
    def NOWPAYMENTS_PARTIAL_URL(self) -> str:
        return f"{self.APP_BASE_URL_NORMALIZED}/?payment=partial"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
