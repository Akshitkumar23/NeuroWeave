import asyncio
import logging
import sys
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("neuroweave.test_debate")

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.model_router import ModelRouter
from agents.debate_engine import DebateEngineAgent, DebateResult

async def run_tests():
    logger.info("Initializing ModelRouter and DebateEngineAgent...")
    router = ModelRouter()
    agent = DebateEngineAgent(router)

    # Test Case 1: Standard Multi-round Debate with Mock Provider
    logger.info("Test Case 1: Running standard debate under mock provider...")
    findings = "The research team shows a 24.5% market growth rate in automation sectors."
    issues = ["The TAM calculations may be inflated.", "VC reports suggest lower CAGR."]
    
    result = await agent.execute_debate(findings, issues)
    assert isinstance(result, DebateResult)
    assert result.rounds_played == 2
    assert "CAGR" in result.consensus
    assert len(result.contradictions_found) > 0
    assert result.consensus_score == 0.92
    logger.info(" [✔] Test Case 1 Passed Successfully!")

    # Test Case 2: Empty Inputs
    logger.info("Test Case 2: Running debate with empty inputs...")
    result_empty = await agent.execute_debate("", [])
    assert result_empty.rounds_played == 0
    assert result_empty.consensus_score == 1.0
    assert len(result_empty.contradictions_found) == 0
    logger.info(" [✔] Test Case 2 Passed Successfully!")

    # Test Case 3: Empty Findings, with Issues
    logger.info("Test Case 3: Running debate with empty findings but active issues...")
    result_gaps = await agent.execute_debate("", ["Missing market projections.", "Invalid revenue split."])
    assert result_gaps.rounds_played == 1
    assert result_gaps.consensus_score == 0.85
    assert "Missing market projections" in result_gaps.consensus
    logger.info(" [✔] Test Case 3 Passed Successfully!")

    logger.info("ALL DEBATE ENGINE TEST CASES PASSED INTEGRITY VERIFICATION [✔ 100% SUCCESS]")

if __name__ == "__main__":
    asyncio.run(run_tests())
