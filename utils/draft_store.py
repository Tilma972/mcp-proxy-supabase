import uuid
import time
import httpx
from typing import Dict, Any

from config import settings
from utils.http_client import get_shared_client
import structlog

logger = structlog.get_logger()

# Simple In-Memory dict pour les brouillons (HYBRID CACHE)
_DRAFTS: Dict[str, Dict[str, Any]] = {}

async def store_draft(payload: dict, ttl_seconds: int = 3600) -> str:
    """
    Store un payload d'email pendant 1 heure par defaut.
    Stocke d'abord en RAM (cache rapide), puis backup sur la table mcp_email_drafts de Supabase.
    """
    draft_id = str(uuid.uuid4())
    expires_at = time.time() + ttl_seconds
    
    # 1. Store in RAM (Fast fallback)
    _DRAFTS[draft_id] = {
        "payload": payload,
        "expires_at": expires_at
    }
    
    # 2. Store in Supabase DB (Persistence)
    if settings.supabase_url and settings.supabase_api_key:
        try:
            client = await get_shared_client()
            resp = await client.post(
                f"{settings.supabase_url}/rest/v1/mcp_email_drafts",
                headers={
                    "apikey": settings.supabase_api_key,
                    "Authorization": f"Bearer {settings.supabase_api_key}",
                    "Content-Type": "application/json",
                    "Prefer": "return=minimal"
                },
                json={
                    "id": draft_id,
                    "payload": payload,
                    "expires_at": int(expires_at)
                }
            )
            if resp.status_code not in (200, 201):
                logger.warning("draft_db_insert_failed", draft_id=draft_id, status=resp.status_code, error=resp.text)
        except Exception as e:
            logger.error("draft_db_connection_error", error=str(e))
    
    _cleanup_expired()
    return draft_id

async def get_draft(draft_id: str) -> dict:
    """Recupere le draft et le retire (une seule execution autorisee)."""
    _cleanup_expired()
    
    payload = None
    
    # 1. Try to get from RAM
    item = _DRAFTS.pop(draft_id, None)
    if item:
        payload = item["payload"]
        
    # 2. If not in RAM, try to get from Supabase DB
    if not payload and settings.supabase_url and settings.supabase_api_key:
        try:
            client = await get_shared_client()
            resp = await client.get(
                f"{settings.supabase_url}/rest/v1/mcp_email_drafts?id=eq.{draft_id}&select=*",
                headers={
                    "apikey": settings.supabase_api_key,
                    "Authorization": f"Bearer {settings.supabase_api_key}",
                }
            )
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    row = data[0]
                    # Check expiration
                    if row.get("expires_at", 0) > time.time():
                        payload = row["payload"]
        except Exception as e:
            logger.error("draft_db_fetch_error", error=str(e))

    # 3. Supprimer de la DB pour empecher une double execution
    if settings.supabase_url and settings.supabase_api_key:
        try:
            # We fire & forget deletion
            client = await get_shared_client()
            await client.delete(
                f"{settings.supabase_url}/rest/v1/mcp_email_drafts?id=eq.{draft_id}",
                headers={
                    "apikey": settings.supabase_api_key,
                    "Authorization": f"Bearer {settings.supabase_api_key}",
                }
            )
        except Exception as e:
            logger.error("draft_db_delete_error", error=str(e))
            
    if not payload:
        raise ValueError("Ce brouillon a expiré ou a déjà été envoyé.")
        
    return payload

def _cleanup_expired():
    """Nettoyage paresseux des vieux drafts en RAM"""
    now = time.time()
    to_delete = [k for k, v in _DRAFTS.items() if v["expires_at"] < now]        
    for k in to_delete:
        del _DRAFTS[k]
