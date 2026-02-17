"""
Configuration settings for Supabase MCP Unified Proxy
"""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with validation"""

    # Supabase Configuration
    supabase_project_ref: str
    supabase_pat: str
    supabase_mcp_base_url: str = "https://mcp.supabase.com"
    supabase_url: Optional[str] = None
    supabase_api_key: Optional[str] = None

    # Auth - Existing proxy key
    x_proxy_key: str  # Secret key pour authentifier les clients du proxy Supabase

    # Auth - FlowChat MCP key
    flowchat_mcp_key: Optional[str] = None  # Key pour accéder aux FlowChat tools

    # Worker URLs (FlowChat backend)
    database_worker_url: Optional[str] = None
    document_worker_url: Optional[str] = None
    storage_worker_url: Optional[str] = None
    email_worker_url: Optional[str] = None

    # Worker Auth
    worker_auth_key: Optional[str] = None  # X-FlowChat-Worker-Auth header

    # Telegram Bot (HITL - Human In The Loop)
    telegram_token: Optional[str] = None  # Bot token from @BotFather
    telegram_webhook_secret: Optional[str] = None  # Secret for webhook verification
    telegram_admin_id: Optional[str] = None  # Admin user ID for notifications
    telegram_webhook_url: Optional[str] = None  # Full webhook URL (e.g., https://supabase.dsolution-ia.fr/webhook/telegram)

    # HITL Configuration
    hitl_enabled: bool = False  # Enable HITL validation system
    hitl_timeout_minutes: int = 30  # Request timeout in minutes
    hitl_facture_threshold: float = 1500.0  # Facture amount requiring validation (EUR)

    # App
    environment: str = "production"
    log_level: str = "INFO"

    # CORS
    allowed_origins: str = "*"

    # Rate limiting
    rate_limit: str = "200/minute"  # Plus haut pour SSE

    class Config:
        env_file = ".env"
        case_sensitive = False


# Initialize settings (lazy loading)
settings = None

def get_settings() -> Settings:
    """Get or create settings instance"""
    global settings
    if settings is None:
        try:
            settings = Settings()
        except Exception as e:
            print(f"Configuration error: {e}")
            print("Required: SUPABASE_PROJECT_REF, SUPABASE_PAT, X_PROXY_KEY")
            raise
    return settings

# Initialize on import (for backwards compatibility)
try:
    settings = Settings()
except Exception:
    # Allow import to succeed even if .env is missing (for testing)
    settings = None
