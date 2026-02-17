"""
Test script to verify FlowChat MCP Unified Proxy implementation

This script tests:
1. All modules import correctly (modular tools/ architecture)
2. Tool registry has all 21 tools
3. Schemas are defined correctly per domain
4. Configuration loads
5. Handler-schema mapping is consistent
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

        # New modular tools architecture
        import tools
        import tools.base
        import tools.entreprises
        import tools.qualifications
        import tools.factures
        import tools.paiements
        import tools.communications
        import tools.analytics

        print("[PASS] All modules import successfully")
        return True

    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_tool_registry():
    """Test that all 21 tools are registered"""
    print("\nTesting tool registry...")

    try:
        from tools_registry import TOOL_REGISTRY, ToolCategory

        # Count tools by category
        read_tools = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.READ]
        write_tools = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.WRITE]
        workflow_tools = [t for t in TOOL_REGISTRY.values() if t.category == ToolCategory.WORKFLOW]

        print(f"   READ tools: {len(read_tools)}/11")
        print(f"   WRITE tools: {len(write_tools)}/6")
        print(f"   WORKFLOW tools: {len(workflow_tools)}/4")
        print(f"   TOTAL: {len(TOOL_REGISTRY)}/21")

        # List all tools by domain
        print("\nRegistered tools by category:")
        for category in [ToolCategory.READ, ToolCategory.WRITE, ToolCategory.WORKFLOW]:
            tools = [t for t in TOOL_REGISTRY.values() if t.category == category]
            print(f"\n{category.value.upper()}:")
            for tool in tools:
                print(f"   - {tool.name}")

        if len(TOOL_REGISTRY) == 21:
            print("\n[PASS] All 21 tools registered successfully")
            return True
        else:
            print(f"\n[FAIL] Expected 21 tools, got {len(TOOL_REGISTRY)}")
            return False

    except Exception as e:
        print(f"[FAIL] Tool registry test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_schemas():
    """Test that all schemas are defined per domain"""
    print("\nTesting schemas (modular architecture)...")

    try:
        from tools.entreprises import ENTREPRISE_SCHEMAS
        from tools.qualifications import QUALIFICATION_SCHEMAS
        from tools.factures import FACTURE_SCHEMAS
        from tools.paiements import PAIEMENT_SCHEMAS
        from tools.communications import COMMUNICATION_SCHEMAS
        from tools import ALL_TOOL_SCHEMAS

        print(f"   Entreprises schemas: {len(ENTREPRISE_SCHEMAS)}/5")
        print(f"   Qualifications schemas: {len(QUALIFICATION_SCHEMAS)}/3")
        print(f"   Factures schemas: {len(FACTURE_SCHEMAS)}/7")
        print(f"   Paiements schemas: {len(PAIEMENT_SCHEMAS)}/3")
        print(f"   Communications schemas: {len(COMMUNICATION_SCHEMAS)}/3")
        print(f"   TOTAL (ALL_TOOL_SCHEMAS): {len(ALL_TOOL_SCHEMAS)}/21")

        if len(ALL_TOOL_SCHEMAS) == 21:
            print("[PASS] All 21 schemas defined successfully")
            return True
        else:
            print(f"[FAIL] Expected 21 schemas, got {len(ALL_TOOL_SCHEMAS)}")
            return False

    except Exception as e:
        print(f"[FAIL] Schema test failed: {e}")
        import traceback
        traceback.print_exc()
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
        from tools import ALL_TOOL_SCHEMAS

        # Check that every registered tool has a schema
        missing_schemas = []
        for tool_name in TOOL_REGISTRY.keys():
            if tool_name not in ALL_TOOL_SCHEMAS:
                missing_schemas.append(tool_name)

        # Check that every schema has a registered handler
        missing_handlers = []
        for schema_name in ALL_TOOL_SCHEMAS.keys():
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


def test_domain_distribution():
    """Test that tools are correctly distributed across domains"""
    print("\nTesting domain distribution...")

    try:
        from tools.entreprises import ENTREPRISE_SCHEMAS
        from tools.qualifications import QUALIFICATION_SCHEMAS
        from tools.factures import FACTURE_SCHEMAS
        from tools.paiements import PAIEMENT_SCHEMAS
        from tools.communications import COMMUNICATION_SCHEMAS

        expected = {
            "entreprises": {
                "schemas": ENTREPRISE_SCHEMAS,
                "expected_tools": [
                    "search_entreprise_with_stats",
                    "get_entreprise_by_id",
                    "list_entreprises",
                    "get_stats_entreprises",
                    "upsert_entreprise",
                ]
            },
            "qualifications": {
                "schemas": QUALIFICATION_SCHEMAS,
                "expected_tools": [
                    "get_entreprise_qualifications",
                    "search_qualifications",
                    "upsert_qualification",
                ]
            },
            "factures": {
                "schemas": FACTURE_SCHEMAS,
                "expected_tools": [
                    "search_factures",
                    "get_facture_by_id",
                    "create_facture",
                    "update_facture",
                    "delete_facture",
                    "generate_facture_pdf",
                    "create_and_send_facture",
                ]
            },
            "paiements": {
                "schemas": PAIEMENT_SCHEMAS,
                "expected_tools": [
                    "get_unpaid_factures",
                    "get_revenue_stats",
                    "mark_facture_paid",
                ]
            },
            "communications": {
                "schemas": COMMUNICATION_SCHEMAS,
                "expected_tools": [
                    "list_recent_interactions",
                    "send_facture_email",
                    "generate_monthly_report",
                ]
            },
        }

        all_ok = True
        for domain_name, domain_info in expected.items():
            schemas = domain_info["schemas"]
            expected_tools = domain_info["expected_tools"]

            actual_tools = sorted(schemas.keys())
            expected_sorted = sorted(expected_tools)

            if actual_tools == expected_sorted:
                print(f"   {domain_name}: OK ({len(schemas)} tools)")
            else:
                missing = set(expected_tools) - set(actual_tools)
                extra = set(actual_tools) - set(expected_tools)
                print(f"   {domain_name}: MISMATCH")
                if missing:
                    print(f"      Missing: {missing}")
                if extra:
                    print(f"      Extra: {extra}")
                all_ok = False

        if all_ok:
            print("[PASS] All tools correctly distributed across domains")
        else:
            print("[FAIL] Domain distribution mismatch")

        return all_ok

    except Exception as e:
        print(f"[FAIL] Domain distribution test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("=" * 60)
    print("FlowChat MCP Unified Proxy - Modular Architecture Test")
    print("=" * 60)

    tests = [
        test_imports,
        test_config,
        test_schemas,
        test_tool_registry,
        test_handler_registration,
        test_domain_distribution,
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
        print("\n[PASS] All tests passed! Modular architecture is ready.")
        print("\nArchitecture:")
        print("   tools/entreprises.py    - 5 tools (clients)")
        print("   tools/qualifications.py - 3 tools (commercial)")
        print("   tools/factures.py       - 7 tools (facturation)")
        print("   tools/paiements.py      - 3 tools (tresorerie)")
        print("   tools/communications.py - 3 tools (emails)")
        print("   tools/analytics.py      - placeholder (futur)")
        return 0
    else:
        print(f"\n[FAIL] {total - passed} test(s) failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
