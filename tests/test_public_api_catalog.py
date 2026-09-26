"""
tests/test_public_api_catalog.py

Validates the curated Public API Catalog tool and database integrated into NeuroWeave.
Ensures only project-relevant APIs are included, zero-auth filtering works, and RBAC is enforced.
"""
import os
import unittest
import asyncio
from core.tool_registry import registry
from tools.public_api_catalog import (
    public_api_catalog,
    search_apis,
    list_categories,
    get_catalog_statistics,
    get_recommended_apis_for_intent,
    _load_database
)


class TestPublicAPICatalog(unittest.TestCase):
    """Tests for NeuroWeave Public API Catalog integration."""

    @classmethod
    def setUpClass(cls):
        # Force loading database
        cls.db = _load_database()

    def test_database_integrity_and_project_relevance(self):
        """Verify the database is loaded and contains strictly project-relevant categories."""
        meta = self.db.get("metadata", {})
        total_apis = meta.get("total_curated_apis", 0)
        self.assertGreater(total_apis, 700, f"Expected >700 curated APIs, found {total_apis}")

        zero_auth = meta.get("zero_auth_apis", 0)
        self.assertGreater(zero_auth, 300, f"Expected >300 Zero-Auth APIs, found {zero_auth}")

        categories = meta.get("categories", [])
        self.assertEqual(len(categories), 18)

        # Confirm essential research categories exist
        for req_cat in [
            "Development", "Finance", "Currency Exchange", "Science & Math",
            "Open Data", "Security", "Government", "Geocoding", "Data Validation"
        ]:
            self.assertIn(req_cat, categories, f"Required category '{req_cat}' missing from catalog")

        # Confirm non-relevant categories are strictly excluded
        for forbidden_cat in ["Animals", "Anime", "Games & Comics", "Food & Drink", "Personality"]:
            self.assertNotIn(forbidden_cat, categories, f"Irrelevant category '{forbidden_cat}' must not be in catalog")

    def test_entry_schema_and_security(self):
        """Verify every entry complies with schema, HTTPS security, and agent mappings."""
        apis = self.db.get("apis", [])
        self.assertTrue(len(apis) > 0)

        for entry in apis:
            self.assertIn("name", entry)
            self.assertIn("url", entry)
            self.assertIn("description", entry)
            self.assertIn("category", entry)
            self.assertIn("auth", entry)
            self.assertIn("zero_auth", entry)
            self.assertTrue(entry.get("https", False), f"API '{entry['name']}' must use HTTPS")
            self.assertIsInstance(entry.get("relevant_agents"), list)
            self.assertGreater(len(entry["relevant_agents"]), 0)

    def test_tool_registration(self):
        """Verify the tool is registered in ToolRegistry with proper allowed agents."""
        tool = registry.tools.get("public_api_catalog")
        self.assertIsNotNone(tool, "public_api_catalog tool must be registered in ToolRegistry")
        self.assertIn("researcher", tool.allowed_agents)
        self.assertIn("planner", tool.allowed_agents)
        self.assertIn("analyzer", tool.allowed_agents)
        self.assertIn("synthesizer", tool.allowed_agents)

    def test_keyword_search_accuracy(self):
        """Verify searching by keywords returns relevant results."""
        res_cur = search_apis("currency", limit=5)
        self.assertTrue(res_cur["success"])
        self.assertGreater(res_cur["total_matches"], 0)
        self.assertTrue(any("currency" in r["name"].lower() or "currency" in r["description"].lower() or "currency" in r["category"].lower() for r in res_cur["results"]))

        res_sec = search_apis("vulnerability", limit=5)
        self.assertTrue(res_sec["success"])
        self.assertGreater(res_sec["total_matches"], 0)

    def test_zero_auth_filtering(self):
        """Verify zero_auth_only filter returns strictly keyless APIs."""
        res = search_apis("", zero_auth_only=True, limit=20)
        self.assertTrue(res["success"])
        self.assertGreater(len(res["results"]), 0)
        for r in res["results"]:
            self.assertTrue(r["zero_auth"], f"API '{r['name']}' has auth '{r['auth']}', expected zero_auth")

    def test_category_filtering(self):
        """Verify category filter isolates results to specified domain."""
        res = search_apis("", category="Finance", limit=10)
        self.assertTrue(res["success"])
        self.assertGreater(len(res["results"]), 0)
        for r in res["results"]:
            self.assertEqual(r["category"], "Finance")

    def test_agent_role_filtering(self):
        """Verify filtering by for_agent isolates results mapped to that agent."""
        res = search_apis("data", for_agent="critic", limit=5)
        self.assertTrue(res["success"])
        for r in res["results"]:
            self.assertIn("critic", [a.lower() for a in r["relevant_agents"]])

    def test_intent_recommendation_helper(self):
        """Verify get_recommended_apis_for_intent returns relevant zero-auth suggestions."""
        rec_quant = get_recommended_apis_for_intent("quantitative", limit=3)
        self.assertGreater(len(rec_quant), 0)
        for r in rec_quant:
            self.assertIn(r["category"], ["Finance", "Currency Exchange"])
            self.assertEqual(r["auth"], "None")

        rec_sci = get_recommended_apis_for_intent("research", limit=3)
        self.assertGreater(len(rec_sci), 0)
        for r in rec_sci:
            self.assertIn(r["category"], ["Science & Math", "Open Data", "Government"])
            self.assertEqual(r["auth"], "None")

    def test_tool_registry_execution_and_rbac(self):
        """Verify execution through registry enforces RBAC checks."""
        async def run_rbac():
            # 1. Allowed agent: researcher
            allowed_res = await registry.execute(
                tool_name="public_api_catalog",
                agent_name="researcher",
                args={"query": "arxiv", "limit": 3},
                session_id="test_sess_catalog"
            )
            self.assertTrue(allowed_res.get("success", False))

            # 2. Blocked agent: unauthorized_dummy
            blocked_res = await registry.execute(
                tool_name="public_api_catalog",
                agent_name="unauthorized_dummy",
                args={"query": "arxiv"},
                session_id="test_sess_catalog"
            )
            self.assertFalse(blocked_res.get("success", True))
            self.assertIn("not authorized", blocked_res.get("error", "").lower())

        asyncio.run(run_rbac())

    def test_researcher_agent_collects_public_api_evidence(self):
        """Verify ResearcherAgent integrates public_api_catalog results into evidence ledger."""
        from agents.researcher import ResearcherAgent
        from core.model_router import ModelRouter
        from utils.citation_manager import CitationManager

        async def run_test():
            agent = ResearcherAgent(ModelRouter(), CitationManager())
            evidence = await agent._gather_multi_source_intelligence(
                search_query="free currency exchange API",
                topic="Free currency exchange rate APIs",
                domain="Finance"
            )
            self.assertIsInstance(evidence, list)
            self.assertGreater(len(evidence), 0)
            has_catalog_evidence = any(e.get("source_type") == "public_api_catalog" for e in evidence)
            self.assertTrue(has_catalog_evidence, "Researcher should include public_api_catalog evidence for API queries")

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
