"""
Shared HTTP client for optimal connection pooling
"""

from typing import Optional
import httpx
import structlog

logger = structlog.get_logger()

# Shared client instance (initialized on startup)
_shared_client: Optional[httpx.AsyncClient] = None


async def init_shared_client():
    """
    Initialize the shared HTTP client

    Called during FastAPI startup event. Creates a single AsyncClient
    instance with optimized settings for connection pooling.

    Benefits:
    - Connection pooling: Reuses TCP connections across requests
    - Reduced latency: No handshake overhead for repeated calls
    - Optimized for 19 tools calling 4 workers (many HTTP requests)
    """
    global _shared_client

    if _shared_client is not None:
        logger.warning("shared_client_already_initialized")
        return

    _shared_client = httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20
        ),
        follow_redirects=True
    )

    logger.info(
        "shared_client_initialized",
        max_connections=100,
        max_keepalive=20,
        timeout=30.0
    )


async def close_shared_client():
    """
    Close the shared HTTP client

    Called during FastAPI shutdown event. Ensures all connections
    are properly closed and resources are released.
    """
    global _shared_client

    if _shared_client is None:
        logger.warning("shared_client_not_initialized")
        return

    await _shared_client.aclose()
    _shared_client = None

    logger.info("shared_client_closed")


async def get_shared_client() -> httpx.AsyncClient:
    """
    Get the shared HTTP client instance

    Returns:
        The shared AsyncClient instance

    Raises:
        RuntimeError: If client not initialized (missing startup hook)
    """
    if _shared_client is None:
        raise RuntimeError(
            "Shared HTTP client not initialized. "
            "Ensure init_shared_client() is called during app startup."
        )

    return _shared_client
