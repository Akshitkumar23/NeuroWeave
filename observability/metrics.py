import logging
from typing import Dict, Any, List

logger = logging.getLogger("neuroweave.metrics")

class MetricsAggregator:
    """
    Tracks and aggregates transaction counters for token volumes,
    financial parameters, tool triggers, and reliability indicators.
    """
    def __init__(self):
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost: float = 0.0
        
        self.tool_calls_count: Dict[str, int] = {}
        self.tool_failures: int = 0
        
        self.hallucinations_detected: int = 0
        self.replans_triggered: int = 0
        self.degraded_executions: int = 0
        
        self.agent_latencies: Dict[str, List[float]] = {}

    def record_llm_call(self, tokens_in: int, tokens_out: int, cost: float):
        self.total_input_tokens += tokens_in
        self.total_output_tokens += tokens_out
        self.total_cost += cost

    def record_tool_call(self, tool_name: str, success: bool):
        self.tool_calls_count[tool_name] = self.tool_calls_count.get(tool_name, 0) + 1
        if not success:
            self.tool_failures += 1

    def record_critic_audit(self, has_issues: bool, replan: bool):
        if has_issues:
            self.hallucinations_detected += 1
        if replan:
            self.replans_triggered += 1

    def record_agent_latency(self, agent_name: str, duration: float):
        if agent_name not in self.agent_latencies:
            self.agent_latencies[agent_name] = []
        self.agent_latencies[agent_name].append(duration)

    def record_degraded_trigger(self):
        self.degraded_executions += 1

    def get_summary(self) -> Dict[str, Any]:
        """
        Synthesizes aggregated telemetry into dashboard-ready parameters.
        """
        avg_latencies = {}
        for agent, list_times in self.agent_latencies.items():
            if list_times:
                avg_latencies[agent] = sum(list_times) / len(list_times)
            else:
                avg_latencies[agent] = 0.0
                
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens_consumed": self.total_input_tokens + self.total_output_tokens,
            "total_estimated_cost_usd": round(self.total_cost, 6),
            "tool_calls_summary": dict(self.tool_calls_count),
            "tool_failures_count": self.tool_failures,
            "critic_hallucination_indicators": self.hallucinations_detected,
            "replanning_cycle_count": self.replans_triggered,
            "degraded_operation_count": self.degraded_executions,
            "average_agent_latencies_sec": avg_latencies
        }
