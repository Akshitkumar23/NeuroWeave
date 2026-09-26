"""
Verification script for NeuroWeave Critic Agent & CriticReport validation (ASCII version to prevent Windows UnicodeEncodeError).
"""
import asyncio
import sys
import os
from pydantic import ValidationError

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agents.critic import CriticAgent, CriticReport
from core.model_router import ModelRouter

async def test_critic_systems():
    print("====================================================")
    print("TESTING CRITIC SCHEMA VALIDATIONS & PROGRAMMATIC AUDITS")
    print("====================================================")
    
    # 1. Test schema constraints
    print("1. Testing Basic CriticReport constraints...")
    try:
        # Healthy proceed report
        report = CriticReport(
            summary="Coherent output with sufficient references.",
            confidence=0.85,
            issues=[],
            action="PROCEED"
        )
        print(" [OK] Healthy PROCEED report created successfully.")
    except Exception as e:
        print(f" [FAIL] Failed to create healthy report: {e}")
        return False

    # 2. Test invalid confidence ranges
    print("\n2. Testing invalid confidence ranges...")
    try:
        CriticReport(
            summary="Invalid confidence rating.",
            confidence=1.2,
            issues=[],
            action="PROCEED"
        )
        print(" [FAIL] Error: Accepted confidence > 1.0!")
        return False
    except ValidationError as e:
        print(" [OK] Successfully caught invalid confidence range (> 1.0).")

    try:
        CriticReport(
            summary="Invalid confidence rating.",
            confidence=-0.1,
            issues=[],
            action="REPLAN"
        )
        print(" [FAIL] Error: Accepted confidence < 0.0!")
        return False
    except ValidationError as e:
        print(" [OK] Successfully caught invalid confidence range (< 0.0).")

    # 3. Test reflection loop consistency
    print("\n3. Testing reflection loop indicator mismatches...")
    try:
        CriticReport(
            summary="Mismatched action.",
            confidence=0.5,
            issues=[],
            action="PROCEED"
        )
        print(" [FAIL] Error: Allowed PROCEED with confidence 0.5!")
        return False
    except ValidationError as e:
        print(" [OK] Successfully caught mismatch: confidence 0.5 + PROCEED.")

    try:
        CriticReport(
            summary="Mismatched action.",
            confidence=0.8,
            issues=[],
            action="REPLAN"
        )
        print(" [FAIL] Error: Allowed REPLAN with confidence 0.8!")
        return False
    except ValidationError as e:
        print(" [OK] Successfully caught mismatch: confidence 0.8 + REPLAN.")

    # 4. Test issue-based dynamic capping
    print("\n4. Testing issue count dynamic caps in validator...")
    try:
        CriticReport(
            summary="Too many issues for high confidence.",
            confidence=0.8,
            issues=["Issue 1", "Issue 2", "Issue 3"],
            action="PROCEED"
        )
        print(" [FAIL] Error: Allowed confidence 0.8 with >= 3 issues!")
        return False
    except ValidationError as e:
        print(" [OK] Successfully caught high issue count mismatch.")

    # 5. Test programmatic audits
    print("\n5. Testing CriticAgent programmatic post-audits...")
    router = ModelRouter()
    critic = CriticAgent(router)
    
    # Baseline normal report
    base_report = CriticReport(
        summary="LLM thinks everything is fine.",
        confidence=0.80,  # Set to 0.80 so deduction of 0.15 drops it to 0.65 (< 0.75 floor)
        issues=[],
        action="PROCEED"
    )

    # Test 5a: Output contains errors
    error_output = "Task executed but received traceback error: ZeroDivisionError inside code."
    audited = critic._run_programmatic_audits(error_output, "https://validcitation.com", base_report)
    print(f" [Audit Error Check] Issues found: {audited.issues}")
    print(f" [Audit Error Check] Confidence: {audited.confidence}, Action: {audited.action}")
    assert audited.confidence <= 0.6, "Failed to penalize for execution error keywords."
    assert audited.action == "REPLAN", "Failed to switch to REPLAN action on error."
    print(" [OK] Successfully detected and penalized execution error.")

    # Test 5b: Output lacks citations
    no_citation_output = "The total market size of agricultural technology is 15 billion USD."
    audited_cit = critic._run_programmatic_audits(no_citation_output, "", base_report)
    print(f" [Audit Citation Check] Issues found: {audited_cit.issues}")
    print(f" [Audit Citation Check] Confidence: {audited_cit.confidence}, Action: {audited_cit.action}")
    assert audited_cit.confidence <= 0.75, "Failed to penalize for missing citations."
    assert audited_cit.action == "REPLAN", "Failed to set REPLAN on missing citations."
    print(" [OK] Successfully detected and penalized missing citations.")

    # Test 5c: Multiple issues combined
    complex_output = "Traceback error. Total value is NaN. No citation provided."
    audited_comp = critic._run_programmatic_audits(complex_output, "", base_report)
    print(f" [Audit Multiple Issues Check] Issues found: {audited_comp.issues}")
    print(f" [Audit Multiple Issues Check] Confidence: {audited_comp.confidence}, Action: {audited_comp.action}")
    assert len(audited_comp.issues) >= 2, "Failed to capture all programmatic issues."
    assert audited_comp.confidence <= 0.5, "Failed to apply compounded penalties."
    assert audited_comp.action == "REPLAN", "Action should be REPLAN."
    print(" [OK] Successfully applied compounded issue adjustments and caps.")

    # 6. Test fallback mechanism
    print("\n6. Testing programmatic fallback audit...")
    # Mocking a parser failure by testing fallback logic directly
    fallback_report = await critic.evaluate_task_output("Fail Task", "", "")
    print(f" [Fallback Check] Summary: {fallback_report.summary}")
    print(f" [Fallback Check] Issues: {fallback_report.issues}")
    print(f" [Fallback Check] Confidence: {fallback_report.confidence}, Action: {fallback_report.action}")
    assert fallback_report.confidence == 0.0, "Empty task output fallback confidence should be 0.0"
    assert fallback_report.action == "REPLAN", "Empty task output fallback action should be REPLAN"
    print(" [OK] Successfully tested programmatic fallback recovery.")

    print("\n====================================================")
    print("ALL CRITIC AGENT TESTS AND SCHEMAS PASSED SUCCESSFULLY! [OK]")
    print("====================================================")
    return True

if __name__ == "__main__":
    asyncio.run(test_critic_systems())
