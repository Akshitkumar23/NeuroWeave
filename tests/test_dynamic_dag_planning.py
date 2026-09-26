import os
import unittest
from core.deterministic_engine import detect_query_intent, is_unanswerable, QueryIntent
from agents.planner import PlannerAgent
from core.model_router import ModelRouter

class TestDynamicDAGPlanning(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Enforce Zero-API / clean router for planning tests
        os.environ["LLM_PROVIDER"] = "none"
        self.router = ModelRouter()
        self.planner = PlannerAgent(self.router)

    async def test_conceptual_query_mcp_vs_api_dag(self):
        """Conceptual queries like MCP vs API must produce conceptual DAG, never Mathematical Calculation."""
        query = "What is MCP and how is it different from an API?"
        intent = detect_query_intent(query)
        self.assertIn(intent, [QueryIntent.CONCEPTUAL, QueryIntent.CONCEPTUAL_COMPARISON, "conceptual", "conceptual_comparison"])
        self.assertNotEqual(intent, QueryIntent.QUANTITATIVE)

        plan = await self.planner.generate_plan(query, "")
        valid_agents = {"researcher", "analyzer", "critic", "synthesizer"}

        for task in plan.tasks:
            self.assertIn(task.assigned_agent, valid_agents)
            # Ensure task title is not falsely classified as math
            self.assertNotIn("Mathematical Calculation", task.title)
            self.assertNotIn("Mathematical Projection", task.title)

    async def test_quantitative_query_revenue_growth_dag(self):
        """Financial calculation queries must be classified as quantitative with analyzer tasks."""
        query = "If a startup has ₹50 lakh annual revenue and grows 25% annually for 5 years, calculate the projected revenue for every year and total cumulative growth."
        intent = detect_query_intent(query)
        self.assertEqual(intent, QueryIntent.QUANTITATIVE)

        plan = await self.planner.generate_plan(query, "")
        analyzer_tasks = [t for t in plan.tasks if t.assigned_agent == "analyzer"]
        self.assertGreater(len(analyzer_tasks), 0)

    async def test_forecasting_query_dag(self):
        """Uncertain long-term future predictions must be flagged as unanswerable."""
        query = "Predict exactly which AI startup will become India's market leader in 2035."
        intent = detect_query_intent(query)
        self.assertEqual(intent, QueryIntent.PREDICTION)
        self.assertTrue(is_unanswerable(query))

        plan = await self.planner.generate_plan(query, "")
        task_titles = [t.title.lower() for t in plan.tasks]
        self.assertTrue(any("landscape" in t or "scenario" in t or "analysis" in t or "research" in t for t in task_titles))

if __name__ == "__main__":
    unittest.main()
