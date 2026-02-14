"""
Test script to verify FlowChat MCP Unified Proxy implementation

This script tests:
1. All modules import correctly
2. Tool registry has all 19 tools
3. Schemas are defined correctly
4. Configuration loads
"""

import sys
from typing import Dict, Any


def test_imports():
    """Test that all modules import correctly"""
    print("Testing imports...")

    try:
        import config
        import auth
        import middleware
        import tools_registry
        import utils.http_client
        import utils.retry
        import handlers.supabase_read
        import handlers.database_write
        import handlers.workflows
        from schemas import read_tools, write_tools, workflow_tools

        print("[PASS] All modules import successfully")
        return True

    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return False


def test_tool_registry():
    """Test that all 19 tools are registered"""
    print("\nTesting tool registry...")

    try:
        from tools_registry import TOOL_REGISTRY, ToolCategory

        # Count tools by category
        read_tools = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.READ]
        write_tools = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.WRITE]
        workflow_tools = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.WORKFLOW]

        print(f"   READ tools: {len(read_tools)}/10")
        print(f"   WRITE tools: {len(write_tools)}/6")
        print(f"   WORKFLOW tools: {len(workflow_tools)}/3")
        print(f"   TOTAL: {len(TOOL_REGISTRY)}/19")

        # List all tools
        print("\nRegistered tools:")
        for category in [ToolCategory.READ, ToolCategory.WRITE, ToolCategory.WORKFLOW]:
            tools = [t for t in TOOL_REGISTRY.values() if t.category == category]
            print(f"\n{category.value.upper()}:")
            for tool in tools:
                print(f"   - {tool.name}")

        if len(TOOL_REGISTRY) == 19:
            print("\n[PASS] All 19 tools registered successfully")
            return True
        else:
            print(f"\n[FAIL] Expected 19 tools, got {len(TOOL_REGISTRY)}")
            return False

    except Exception as e:
        print(f"[FAIL] Tool registry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_schemas():
    """Test that all schemas are defined"""
    print("\nTesting schemas...")

    try:
        from schemas.read_tools import READ_TOOL_SCHEMAS
        from schemas.write_tools import WRITE_TOOL_SCHEMAS
        from schemas.workflow_tools import WORKFLOW_TOOL_SCHEMAS

        print(f"   READ schemas: {len(READ_TOOL_SCHEMAS)}/10")
        print(f"   WRITE schemas: {len(WRITE_TOOL_SCHEMAS)}/6")
        print(f"   WORKFLOW schemas: {len(WORKFLOW_TOOL_SCHEMAS)}/3")

        total_schemas = len(READ_TOOL_SCHEMAS) + len(WRITE_TOOL_SCHEMAS) + len(WORKFLOW_TOOL_SCHEMAS)

        if total_schemas == 19:
            print("[PASS] All 19 schemas defined successfully")
            return True
        else:
            print(f"[FAIL] Expected 19 schemas, got {total_schemas}")
            return False

    except Exception as e:
        print(f"[FAIL] Schema test failed: {e}")
        return False


def test_config():
    """Test configuration loading"""
    print("\nTesting configuration...")

    try:
        from config import settings

        if settings is None:
            print("   [WARN] No .env file found - using defaults for testing")
            print("   [INFO] Configuration will be loaded from .env when server starts")
            print("[PASS] Configuration module loads successfully (no .env)")
            return True

        print(f"   Environment: {settings.environment}")
        print(f"   Log level: {settings.log_level}")
        print(f"   Supabase URL configured: {bool(settings.supabase_url)}")
        print(f"   FlowChat MCP Key configured: {bool(settings.flowchat_mcp_key)}")
        print(f"   Database worker URL: {settings.database_worker_url or 'Not configured'}")
        print(f"   Document worker URL: {settings.document_worker_url or 'Not configured'}")
        print(f"   Storage worker URL: {settings.storage_worker_url or 'Not configured'}")
        print(f"   Email worker URL: {settings.email_worker_url or 'Not configured'}")

        print("[PASS] Configuration loaded successfully")

        # Warn about missing worker URLs
        if not settings.database_worker_url:
            print("[WARN]  DATABASE_WORKER_URL not configured (WRITE tools will fail)")
        if not settings.document_worker_url:
            print("[WARN]  DOCUMENT_WORKER_URL not configured (WORKFLOW tools will fail)")
        if not settings.storage_worker_url:
            print("[WARN]  STORAGE_WORKER_URL not configured (WORKFLOW tools will fail)")
        if not settings.email_worker_url:
            print("[WARN]  EMAIL_WORKER_URL not configured (WORKFLOW tools will fail)")

        return True

    except Exception as e:
        print(f"[FAIL] Config test failed: {e}")
        return False


def test_handler_registration():
    """Test that handlers are properly registered with schemas"""
    print("\nTesting handler-schema mapping...")

    try:
        from tools_registry import TOOL_REGISTRY
        from schemas.read_tools import READ_TOOL_SCHEMAS
        from schemas.write_tools import WRITE_TOOL_SCHEMAS
        from schemas.workflow_tools import WORKFLOW_TOOL_SCHEMAS

        all_schemas = {
            **READ_TOOL_SCHEMAS,
            **WRITE_TOOL_SCHEMAS,
            **WORKFLOW_TOOL_SCHEMAS
        }

        # Check that every registered tool has a schema
        missing_schemas = []
        for tool_name in TOOL_REGISTRY.keys():
            if tool_name not in all_schemas:
                missing_schemas.append(tool_name)

        # Check that every schema has a registered handler
        missing_handlers = []
        for schema_name in all_schemas.keys():
            if schema_name not in TOOL_REGISTRY:
                missing_handlers.append(schema_name)

        if missing_schemas:
            print(f"[FAIL] Tools missing schemas: {missing_schemas}")
            return False

        if missing_handlers:
            print(f"[FAIL] Schemas missing handlers: {missing_handlers}")
            return False

        print("[PASS] All tools have matching schemas and handlers")
        return True

    except Exception as e:
        print(f"[FAIL] Handler-schema mapping test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("FlowChat MCP Unified Proxy - Implementation Test")
    print("=" * 60)

    tests = [
        test_imports,
        test_config,
        test_schemas,
        test_tool_registry,
        test_handler_registration,
    ]

    results = []
    for test in tests:
        results.append(test())

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("\n[PASS] All tests passed! Implementation is ready for runtime testing.")
        print("\nNext steps:")
        print("1. Configure worker URLs in .env")
        print("2. Start the server: uvicorn main:app --reload")
        print("3. Test endpoints:")
        print("   - GET /health")
        print("   - GET /mcp/tools/list")
        print("   - POST /mcp/tools/call")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} test(s) failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
