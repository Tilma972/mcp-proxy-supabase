"""
Retry utilities with exponential backoff
"""

from functools import wraps
import asyncio
import httpx
import structlog

logger = structlog.get_logger()


def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 10.0):
    """
    Decorator for retrying async functions with exponential backoff

    Retries on:
    - httpx.TimeoutException
    - httpx.NetworkError
    - httpx.HTTPStatusError (5xx only)

    Args:
        max_attempts: Maximum number of attempts (default: 3)
        base_delay: Base delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 10.0)

    Usage:
        @retry_with_backoff(max_attempts=3, base_delay=1.0)
        async def call_worker():
            return await client.post(...)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    last_exception = e
                    error_type = type(e).__name__

                    if attempt < max_attempts:
                        delay = min(base_delay * (2 ** (attempt - 1)), max_delay)

                        logger.warning(
                            "retry_network_error",
                            function=func.__name__,
                            attempt=attempt,
                            max_attempts=max_attempts,
                            error_type=error_type,
                            retry_delay=delay
                        )

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "retry_exhausted_network",
                            function=func.__name__,
                            attempts=max_attempts,
                            error_type=error_type
                        )
                        raise

                except httpx.HTTPStatusError as e:
                    # Retry only on 5xx errors
                    if 500 <= e.response.status_code < 600:
                        last_exception = e

                        if attempt < max_attempts:
                            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)

                            logger.warning(
                                "retry_http_error",
                                function=func.__name__,
                                attempt=attempt,
                                max_attempts=max_attempts,
                                status_code=e.response.status_code,
                                retry_delay=delay
                            )

                            await asyncio.sleep(delay)
                        else:
                            logger.error(
                                "retry_exhausted_http",
                                function=func.__name__,
                                attempts=max_attempts,
                                status_code=e.response.status_code
                            )
                            raise
                    else:
                        # Don't retry on 4xx errors
                        logger.error(
                            "http_error_no_retry",
                            function=func.__name__,
                            status_code=e.response.status_code
                        )
                        raise

                except Exception as e:
                    # Don't retry on unexpected errors
                    logger.error(
                        "unexpected_error_no_retry",
                        function=func.__name__,
                        error_type=type(e).__name__,
                        error=str(e)
                    )
                    raise

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator
