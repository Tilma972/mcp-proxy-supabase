"""
Middleware for request tracking and observability
"""

import uuid
from contextvars import ContextVar
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

# Context variable for request ID (thread-safe, async-safe)
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware to generate and bind a unique request ID to each request

    The request ID is:
    - Generated as a UUID for each incoming request
    - Bound to structlog context for automatic inclusion in all logs
    - Stored in ContextVar for access in handlers
    - Returned in X-Request-ID response header
    - Propagated to worker calls via X-Request-ID request header
    """

    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Store in ContextVar for handler access
        request_id_ctx.set(request_id)

        # Bind to structlog context
        structlog.contextvars.bind_contextvars(request_id=request_id)

        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Request-ID"] = request_id

        # Clear context after request
        structlog.contextvars.clear_contextvars()

        return response
