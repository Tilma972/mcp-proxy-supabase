"""
Tool registry and dispatch system for FlowChat MCP tools
"""

from enum import Enum
from typing import Dict, Callable, Awaitable, Any, Optional
from dataclasses import dataclass
import structlog

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

    except Exception as e:
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
