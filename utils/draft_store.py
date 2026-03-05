import uuid
import time
from typing import Dict, Any

# Simple In-Memory dict pour les brouillons (efface d'emblee si le proxy redemarre)
# Structure: {
#   "draft_uuid": {
#       "payload": dict, 
#       "expires_at": float
#   }
# }
_DRAFTS: Dict[str, Dict[str, Any]] = {}

def store_draft(payload: dict, ttl_seconds: int = 3600) -> str:
    """Store un payload d'email pendant 1 heure par defaut. Retourne l'ID."""
    draft_id = str(uuid.uuid4())
    _DRAFTS[draft_id] = {
        "payload": payload,
        "expires_at": time.time() + ttl_seconds
    }
    _cleanup_expired()
    return draft_id

def get_draft(draft_id: str) -> dict:
    """Recupere le draft (ou leve KeyError) et le retire."""
    _cleanup_expired()
    item = _DRAFTS.pop(draft_id, None)
    if not item:
        raise ValueError("Ce brouillon a expiré ou a déjà été envoyé.")
    return item["payload"]

def _cleanup_expired():
    """Nettoyage paresseux des vieux drafts"""
    now = time.time()
    to_delete = [k for k, v in _DRAFTS.items() if v["expires_at"] < now]
    for k in to_delete:
        del _DRAFTS[k]
