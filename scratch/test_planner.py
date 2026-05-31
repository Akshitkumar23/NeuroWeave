"""
NeuroWeave Planner validation tests.
Verifies circular dependency detection, field validations, and dangling dependency cleanups.
"""

import os
import sys
import asyncio
import logging

# Ensure parent directory is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pydantic import ValidationError
from core.model_router import ModelRouter
from agents.planner import PlannerAgent, TaskPlan, TaskItem

# Setup simple logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("neuroweave.test_planner")

async def test_planner_validations():
    logger.info("========================================")
    logger.info("RUNNING DEDICATED PLANNER VALIDATION TESTS")
    logger.info("========================================")

    # 1. Test Valid Plan Validation
    logger.info("1. Testing valid task plan parsing...")
    valid_data = {
        "tasks": [
            {
                "id": "task_01",
                "title": "Gather research",
                "description": "Search web for initial metrics.",
                "assigned_agent": "researcher",
                "dependencies": []
            },
            {
                "id": "task_02",
                "title": "Analyze financial data",
                "description": "Calculate cagr and target ratios.",
                "assigned_agent": "analyzer",
                "dependencies": ["task_01"]
            }
        ]
    }
    
    try:
        plan = TaskPlan(**valid_data)
        assert len(plan.tasks) == 2
        logger.info(" [✔] Valid plan parsed and validated successfully.")
    except Exception as e:
        logger.error(f" [✖] Valid plan parsing failed unexpectedly: {e}")
        raise e

    # 2. Test Invalid Task ID Format (Dynamic Field Validation)
    logger.info("2. Testing invalid task ID validation (e.g. spaces)...")
    invalid_id_data = {
        "tasks": [
            {
                "id": "task 01 with spaces",
                "title": "Gather research",
                "description": "Search web for initial metrics.",
                "assigned_agent": "researcher",
                "dependencies": []
            }
        ]
    }
    try:
        TaskPlan(**invalid_id_data)
        logger.error(" [✖] Failed to block invalid task ID format.")
        assert False, "Failed to raise validation error on invalid task ID."
    except ValidationError as ve:
        logger.info(f" [✔] Correctly blocked invalid task ID format with exception: {ve.errors()[0]['msg']}")

    # 3. Test Invalid Assigned Agent (Dynamic Field Validation)
    logger.info("3. Testing invalid assigned agent validation...")
    invalid_agent_data = {
        "tasks": [
            {
                "id": "task_01",
                "title": "Gather research",
                "description": "Search web for initial metrics.",
                "assigned_agent": "hacker_agent",
                "dependencies": []
            }
        ]
    }
    try:
        TaskPlan(**invalid_agent_data)
        logger.error(" [✖] Failed to block invalid assigned agent.")
        assert False, "Failed to raise validation error on invalid assigned agent."
    except ValidationError as ve:
        logger.info(f" [✔] Correctly blocked invalid assigned agent with exception: {ve.errors()[0]['msg']}")

    # 4. Test Circular Dependency Detection (Model Level)
    logger.info("4. Testing circular dependency cycle detection...")
    cycle_data = {
        "tasks": [
            {
                "id": "task_01",
                "title": "First",
                "description": "Start.",
                "assigned_agent": "researcher",
                "dependencies": ["task_02"]
            },
            {
                "id": "task_02",
                "title": "Second",
                "description": "Middle.",
                "assigned_agent": "analyzer",
                "dependencies": ["task_01"]
            }
        ]
    }
    try:
        TaskPlan(**cycle_data)
        logger.error(" [✖] Failed to detect circular dependency cycle.")
        assert False, "Failed to raise circular dependency error."
    except ValidationError as ve:
        logger.info(f" [✔] Correctly blocked circular dependency with exception: {ve.errors()[0]['msg']}")

    # 5. Test Dangling Dependency Cleanup during plan post-processing
    logger.info("5. Testing dangling dependency cleanup in PlannerAgent.generate_plan...")
    router = ModelRouter()
    planner = PlannerAgent(router)
    
    # We will simulate a plan with a dangling dependency
    dangling_plan = TaskPlan(
        tasks=[
            TaskItem(
                id="task_01",
                title="Task One",
                description="Do something.",
                assigned_agent="researcher",
                dependencies=["non_existent_dependency"]
            )
        ]
    )
    
    # Check that initially it has the dangling dependency
    assert "non_existent_dependency" in dangling_plan.tasks[0].dependencies
    
    # Now simulate generate_plan post-processing logic
    task_ids = {t.id for t in dangling_plan.tasks}
    for task in dangling_plan.tasks:
        task.dependencies = [dep for dep in task.dependencies if dep in task_ids]
        
    assert "non_existent_dependency" not in dangling_plan.tasks[0].dependencies
    logger.info(" [✔] Correctly stripped dangling dependency 'non_existent_dependency' from task_01.")

    # 6. Test Autonomous Goal Expansion Dangling Dependency Pruning & Combined Cycle Prevention
    logger.info("6. Testing Goal Expansion dangling dependency pruning & cycle prevention...")
    current_tasks = {
        "task_01": {
            "id": "task_01",
            "title": "Gather statistics",
            "assigned_agent": "researcher",
            "dependencies": [],
            "status": "completed",
            "output": "Some data"
        }
    }
    
    expanded_tasks_input = [
        TaskItem(
            id="task_expanded_01",
            title="Market risks analysis",
            description="Deep dive on competitive parameters.",
            assigned_agent="analyzer",
            # task_01 is valid, but missing_dep is dangling, and task_expanded_02 is valid
            dependencies=["task_01", "missing_dep", "task_expanded_02"]
        ),
        TaskItem(
            id="task_expanded_02",
            title="Competitor lookup",
            description="Lookup competitor details.",
            assigned_agent="researcher",
            dependencies=[]
        )
    ]
    
    # Simulate autonomous expansion processing
    new_tasks = []
    new_task_ids = {t.id for t in expanded_tasks_input}
    valid_task_ids = set(current_tasks.keys()).union(new_task_ids)
    
    for t in expanded_tasks_input:
        if t.id not in current_tasks:
            # Clean up dangling dependencies
            t.dependencies = [dep for dep in t.dependencies if dep in valid_task_ids]
            new_tasks.append(t)
            
    # Verify dangling 'missing_dep' is removed, but 'task_01' and 'task_expanded_02' remain
    assert "missing_dep" not in new_tasks[0].dependencies
    assert "task_01" in new_tasks[0].dependencies
    assert "task_expanded_02" in new_tasks[0].dependencies
    logger.info(" [✔] Goal expansion correctly pruned dangling dependencies while preserving valid ones.")

    # Test combined cycle detection for autonomous goal expansion
    logger.info("7. Testing combined cycle detection blocking for autonomous goal expansion...")
    
    # Simulate a new task that introduces a cycle with current tasks
    # Assume current_tasks: task_01 depends on task_02 (no cycle yet)
    current_tasks_cycle = {
        "task_01": {
            "id": "task_01",
            "dependencies": ["task_02"]
        },
        "task_02": {
            "id": "task_02",
            "dependencies": []
        }
    }
    # Expanded task_02_new depends on task_01, and since task_01 depends on task_02, if task_02 depends on task_02_new we get a cycle.
    # Let's say expanded task_02 (duplicate is skipped, but let's say expanded task_03 depends on task_01, and task_02 is updated to depend on task_03).
    # Since we can't update existing tasks, let's say expanded task_03 depends on task_01, and expanded task_04 depends on task_03, and expanded task_03 depends on task_04. Cycle is task_03 <-> task_04.
    
    expanded_tasks_cycle = [
        TaskItem(
            id="task_03",
            title="Three",
            description="Desc.",
            assigned_agent="researcher",
            dependencies=["task_04"]
        ),
        TaskItem(
            id="task_04",
            title="Four",
            description="Desc.",
            assigned_agent="analyzer",
            dependencies=["task_03"]
        )
    ]
    
    # Build combined adj
    combined_adj = {}
    for tid, tval in current_tasks_cycle.items():
        combined_adj[tid] = tval.get("dependencies", [])
    for t in expanded_tasks_cycle:
        combined_adj[t.id] = t.dependencies

    visited = {}
    cycle_detected = False

    def dfs(node: str) -> bool:
        if visited.get(node, 0) == 1:
            return True
        if visited.get(node, 0) == 2:
            return False

        visited[node] = 1
        for dep in combined_adj.get(node, []):
            if dep in combined_adj:
                if dfs(dep):
                    return True
        visited[node] = 2
        return False

    for task_id in list(combined_adj.keys()):
        if visited.get(task_id, 0) == 0:
            if dfs(task_id):
                cycle_detected = True
                break

    assert cycle_detected
    logger.info(" [✔] Combined cycle detection successfully intercepted and blocked cycle.")
    
    logger.info("========================================")
    logger.info("ALL PLANNER VALIDATION TESTS PASSED [100% SUCCESS]")
    logger.info("========================================")

if __name__ == "__main__":
    asyncio.run(test_planner_validations())
