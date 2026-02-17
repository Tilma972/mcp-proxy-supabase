"""
Tool registry and dispatch system for FlowChat MCP tools
"""

from enum import Enum
from typing import Dict, Callable, Awaitable, Any, Optional
from dataclasses import dataclass
import structlog
import httpx
from fastapi import HTTPException

logger = structlog.get_logger()


class ToolCategory(str, Enum):
    """Tool categories for organization"""
    READ = "read"
    WRITE = "write"
    WORKFLOW = "workflow"


@dataclass
class ToolMetadata:
    """Metadata for a registered tool"""
    name: str
    category: ToolCategory
    description_short: str
    handler: Callable[[Dict[str, Any]], Awaitable[Any]]


# Global tool registry
TOOL_REGISTRY: Dict[str, ToolMetadata] = {}


def register_tool(
    name: str,
    category: ToolCategory,
    description_short: str
):
    """
    Decorator to register a tool handler

    Usage:
        @register_tool(
            name="search_entreprise_with_stats",
            category=ToolCategory.READ,
            description_short="Recherche entreprise par nom avec stats"
        )
        async def search_entreprise_handler(params: Dict[str, Any]):
            return await call_supabase_rpc("search_entreprise_with_stats", params)

    Args:
        name: Unique tool name (used in MCP protocol)
        category: Tool category (READ, WRITE, WORKFLOW)
        description_short: Brief description for tool list

    Returns:
        Decorator function that registers the handler
    """
    def decorator(handler_func):
        if name in TOOL_REGISTRY:
            logger.warning("tool_already_registered", tool_name=name)
            return handler_func

        TOOL_REGISTRY[name] = ToolMetadata(
            name=name,
            category=category,
            description_short=description_short,
            handler=handler_func
        )

        logger.debug(
            "tool_registered",
            tool_name=name,
            category=category.value
        )

        return handler_func

    return decorator


async def dispatch_tool(tool_name: str, params: Dict[str, Any]) -> Any:
    """
    Dispatch a tool call to its registered handler

    Args:
        tool_name: Name of the tool to execute
        params: Tool parameters (validated against schema)

    Returns:
        Tool execution result

    Raises:
        ValueError: If tool not found in registry
        HTTPException: 503 if worker unavailable, 422 if validation fails
    """
    tool = TOOL_REGISTRY.get(tool_name)

    if not tool:
        logger.error("tool_not_found", tool_name=tool_name)
        raise ValueError(f"Unknown tool: {tool_name}")

    logger.info(
        "tool_dispatch",
        tool_name=tool_name,
        category=tool.category.value,
        params_keys=list(params.keys())
    )

    try:
        result = await tool.handler(params)

        logger.info(
            "tool_dispatch_success",
            tool_name=tool_name,
            category=tool.category.value
        )

        return result

    except HTTPException:
        # Re-raise HTTPException as-is (422 validation, 404 not found, etc.)
        raise

    except RuntimeError as e:
        error_msg = str(e)

        # Map worker configuration errors to user-friendly messages
        if "DATABASE_WORKER_URL not configured" in error_msg:
            logger.warning(
                "worker_not_configured",
                tool_name=tool_name,
                worker="database"
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Le service d'écriture en base de données est temporairement indisponible. Seules les opérations de lecture sont disponibles.",
                    "tool": tool_name,
                    "category": tool.category.value
                }
            )

        elif "DOCUMENT_WORKER_URL not configured" in error_msg:
            logger.warning(
                "worker_not_configured",
                tool_name=tool_name,
                worker="document"
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Le service de génération de documents PDF est temporairement indisponible. Les opérations de lecture et d'écriture en base restent disponibles.",
                    "tool": tool_name,
                    "category": tool.category.value
                }
            )

        elif "STORAGE_WORKER_URL not configured" in error_msg:
            logger.warning(
                "worker_not_configured",
                tool_name=tool_name,
                worker="storage"
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Le service de stockage de fichiers est temporairement indisponible. Les opérations de lecture et d'écriture en base restent disponibles.",
                    "tool": tool_name,
                    "category": tool.category.value
                }
            )

        elif "EMAIL_WORKER_URL not configured" in error_msg:
            logger.warning(
                "worker_not_configured",
                tool_name=tool_name,
                worker="email"
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "service_unavailable",
                    "message": "Le service d'envoi d'emails est temporairement indisponible. Les opérations de lecture et d'écriture en base restent disponibles.",
                    "tool": tool_name,
                    "category": tool.category.value
                }
            )

        else:
            # Other RuntimeError - re-raise as-is
            logger.error(
                "tool_dispatch_error",
                tool_name=tool_name,
                category=tool.category.value,
                error=error_msg,
                error_type="RuntimeError"
            )
            raise

    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        # Connection errors to workers
        logger.error(
            "worker_connection_error",
            tool_name=tool_name,
            category=tool.category.value,
            error=str(e),
            error_type=type(e).__name__
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "service_unavailable",
                "message": "Un service externe requis pour cette opération est temporairement inaccessible. Veuillez réessayer dans quelques instants.",
                "tool": tool_name,
                "category": tool.category.value
            }
        )

    except httpx.TimeoutException as e:
        # Timeout errors
        logger.error(
            "worker_timeout_error",
            tool_name=tool_name,
            category=tool.category.value,
            error=str(e)
        )
        raise HTTPException(
            status_code=504,
            detail={
                "error": "gateway_timeout",
                "message": "L'opération a pris trop de temps à s'exécuter. Le service est peut-être surchargé. Veuillez réessayer.",
                "tool": tool_name,
                "category": tool.category.value
            }
        )

    except httpx.HTTPStatusError as e:
        # HTTP errors from workers (4xx, 5xx)
        status_code = e.response.status_code
        logger.error(
            "worker_http_error",
            tool_name=tool_name,
            category=tool.category.value,
            status_code=status_code,
            error=str(e)
        )

        # Try to extract error detail from worker response
        try:
            error_detail = e.response.json()
        except Exception:
            error_detail = {"message": e.response.text or "Erreur serveur"}

        raise HTTPException(
            status_code=status_code,
            detail={
                "error": "worker_error",
                "message": f"Le service a retourné une erreur : {error_detail.get('message', 'Erreur inconnue')}",
                "tool": tool_name,
                "category": tool.category.value,
                "worker_detail": error_detail
            }
        )

    except Exception as e:
        # Catch-all for unexpected errors
        logger.error(
            "tool_dispatch_error",
            tool_name=tool_name,
            category=tool.category.value,
            error=str(e),
            error_type=type(e).__name__
        )
        raise


def list_tools(category: Optional[ToolCategory] = None) -> list[Dict[str, str]]:
    """
    List all registered tools

    Args:
        category: Optional filter by category

    Returns:
        List of tool metadata (name, category, description)
    """
    tools = TOOL_REGISTRY.values()

    if category:
        tools = [t for t in tools if t.category == category]

    return [
        {
            "name": tool.name,
            "category": tool.category.value,
            "description": tool.description_short
        }
        for tool in tools
    ]


def get_tool_info(tool_name: str) -> Optional[Dict[str, str]]:
    """
    Get metadata for a specific tool

    Args:
        tool_name: Name of the tool

    Returns:
        Tool metadata or None if not found
    """
    tool = TOOL_REGISTRY.get(tool_name)

    if not tool:
        return None

    return {
        "name": tool.name,
        "category": tool.category.value,
        "description": tool.description_short
    }
