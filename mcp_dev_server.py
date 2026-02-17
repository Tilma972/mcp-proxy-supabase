"""
MCP STDIO Server for Claude Desktop (Development)

Calls tool handlers directly - no HTTP proxy needed.
Uses the same schemas, handlers, and registry as the production proxy.

Usage:
    python mcp_dev_server.py

Requires:
    - pip install mcp
    - .env file with Supabase + Worker credentials (or env vars via Claude Desktop config)

Protocol: JSON-RPC over STDIO (MCP native)
"""

import asyncio
import json
import logging
import sys
import uuid

import structlog

# CRITICAL: Configure structlog to stderr BEFORE any other project imports.
# MCP protocol uses stdout for JSON-RPC, so any log output to stdout
# would corrupt the protocol and crash the connection.
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from config import settings
from tools import ALL_TOOL_SCHEMAS  # 🆕 Centralized schema registry
from tools_registry import dispatch_tool
from utils.http_client import init_shared_client, close_shared_client
from middleware import request_id_ctx

# Import tool domains to trigger @register_tool decorators
import tools.entreprises  # noqa: F401
import tools.qualifications  # noqa: F401
import tools.factures  # noqa: F401
import tools.paiements  # noqa: F401
import tools.communications  # noqa: F401
import tools.analytics  # noqa: F401

logger = structlog.get_logger()

# MCP server instance
server = Server("flowchat-dev-mcp")


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Expose all FlowChat tools via MCP protocol."""
    return [
        Tool(
            name=name,
            description=schema.description,
            inputSchema=schema.input_schema,
        )
        for name, schema in ALL_TOOL_SCHEMAS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool via the existing handler registry."""
    # Set request ID for tracing (normally done by RequestIDMiddleware)
    request_id_ctx.set(str(uuid.uuid4()))

    try:
        result = await dispatch_tool(name, arguments or {})
        return [TextContent(
            type="text",
            text=json.dumps(result, default=str, ensure_ascii=False),
        )]
    except Exception as e:
        logger.error("tool_call_error", tool=name, error=str(e))
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "tool": name}, ensure_ascii=False),
        )]


async def main():
    """Run the STDIO MCP server."""
    if not settings:
        print(
            "ERROR: Settings not loaded. Check .env file or environment variables.\n"
            "Required: SUPABASE_PROJECT_REF, SUPABASE_PAT, X_PROXY_KEY",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.info(
        "mcp_dev_server_starting",
        tools=len(ALL_TOOL_SCHEMAS),
        tool_names=list(ALL_TOOL_SCHEMAS.keys()),
    )

    # Initialize shared HTTP client (used by all handlers for Supabase + Worker calls)
    await init_shared_client()

    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        await close_shared_client()
        logger.info("mcp_dev_server_stopped")


if __name__ == "__main__":
    asyncio.run(main())
