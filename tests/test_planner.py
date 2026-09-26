"""
Unit Test Suite for PlannerAgent and TaskPlan schema.
Covers task decomposition, input sanitization, alias mapping, DAG validation,
self-dependency and cycle detection, dangling dependency cleanup, and autonomous goal expansion.
"""

import unittest
from pydantic import ValidationError
from agents.planner import TaskItem, TaskPlan, PlannerAgent
from core.model_router import ModelRouter


class TestPlanner(unittest.TestCase):

    def test_task_item_sanitization_and_aliases(self):
        # 1. ID with spaces and special chars
        item = TaskItem(
            id="task 01: research #market",
            title="Market Research",
            description="Gather market data",
            assigned_agent="web_searcher",  # alias for researcher
            dependencies="task 00"  # single string dependency converted to list
        )
        self.assertEqual(item.id, "task_01_research_market")
        self.assertEqual(item.assigned_agent, "researcher")
        self.assertEqual(item.dependencies, ["task_00"])

        # 2. Test analysis alias
        item2 = TaskItem(
            id="task_calc",
            title="Calculations",
            description="Run math",
            assigned_agent="data_analyzer",
            dependencies=["task_01_research_market"]
        )
        self.assertEqual(item2.assigned_agent, "analyzer")

        # 3. Test critic alias
        item3 = TaskItem(
            id="task_audit",
            title="Audit",
            description="Audit findings",
            assigned_agent="auditor",
            dependencies=[]
        )
        self.assertEqual(item3.assigned_agent, "critic")

    def test_task_plan_valid_dag(self):
        plan = TaskPlan(tasks=[
            TaskItem(id="t1", title="T1", description="D1", assigned_agent="researcher", dependencies=[]),
            TaskItem(id="t2", title="T2", description="D2", assigned_agent="analyzer", dependencies=["t1"]),
            TaskItem(id="t3", title="T3", description="D3", assigned_agent="critic", dependencies=["t2"]),
        ])
        self.assertEqual(len(plan.tasks), 3)

    def test_task_plan_rejects_duplicate_ids(self):
        with self.assertRaises(ValidationError) as ctx:
            TaskPlan(tasks=[
                TaskItem(id="t1", title="T1", description="D1", assigned_agent="researcher", dependencies=[]),
                TaskItem(id="t1", title="T1 duplicate", description="D2", assigned_agent="analyzer", dependencies=[]),
            ])
        self.assertIn("Duplicate task ID", str(ctx.exception))

    def test_task_plan_rejects_self_dependency(self):
        with self.assertRaises(ValidationError) as ctx:
            TaskPlan(tasks=[
                TaskItem(id="t1", title="T1", description="D1", assigned_agent="researcher", dependencies=["t1"]),
            ])
        self.assertIn("Self-dependency detected", str(ctx.exception))

    def test_task_plan_rejects_cycle(self):
        with self.assertRaises(ValidationError) as ctx:
            TaskPlan(tasks=[
                TaskItem(id="t1", title="T1", description="D1", assigned_agent="researcher", dependencies=["t3"]),
                TaskItem(id="t2", title="T2", description="D2", assigned_agent="analyzer", dependencies=["t1"]),
                TaskItem(id="t3", title="T3", description="D3", assigned_agent="critic", dependencies=["t2"]),
            ])
        self.assertIn("Circular dependency detected", str(ctx.exception))


class TestPlannerAsync(unittest.IsolatedAsyncioTestCase):

    async def test_planner_agent_run(self):
        router = ModelRouter()
        planner = PlannerAgent(router)
        
        # Test agent execution interface with fallback/mock capabilities
        res = await planner.run(
            query="Analyze quantum computing algorithms",
            context_summary="Empirical context"
        )
        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["agent_name"], "planner")
        self.assertIn("tasks", res["data"])
        self.assertTrue(len(res["data"]["tasks"]) >= 1)

    async def test_autonomous_goal_expansion(self):
        router = ModelRouter()
        planner = PlannerAgent(router)
        
        current_tasks = {
            "task_01": {"title": "Task 1", "dependencies": []}
        }
        new_tasks = await planner.autonomously_expand_goals(
            query="Compare GPU architectures",
            current_tasks=current_tasks,
            critic_feedback="Missing H100 vs B200 memory bandwidth metrics and FP8 throughput."
        )
        # Should return a list of task items or empty if no expansion
        self.assertIsInstance(new_tasks, list)
        for t in new_tasks:
            self.assertNotEqual(t.id, "task_01")


if __name__ == "__main__":
    unittest.main()
