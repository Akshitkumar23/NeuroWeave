import time
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("neuroweave.traces")

class TraceSpan:
    def __init__(self, name: str, agent: str, task_id: Optional[str] = None):
        self.name: str = name
        self.agent: str = agent
        self.task_id: Optional[str] = task_id
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None
        self.duration: float = 0.0
        self.success: bool = True
        self.meta: Dict[str, Any] = {}

    def complete(self, success: bool = True, meta: Optional[Dict[str, Any]] = None):
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        self.success = success
        if meta:
            self.meta.update(meta)
        logger.info(f"Trace complete: {self.name} ({self.agent}) completed in {self.duration:.2f}s (Success: {success})")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "agent": self.agent,
            "task_id": self.task_id,
            "start_time": self.start_time,
            "duration_sec": round(self.duration, 3),
            "success": self.success,
            "metadata": self.meta
        }

class ActiveTracer:
    """
    Manages active latency traces and compiles waterfall chart structures
    illustrating sequential and parallel execution speeds.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.spans: List[TraceSpan] = []
        self._active_spans: Dict[str, TraceSpan] = {}

    def start_span(self, name: str, agent: str, task_id: Optional[str] = None) -> str:
        """
        Begins a new duration measure span. Returns a tracking key.
        """
        span = TraceSpan(name, agent, task_id)
        key = f"{agent}_{task_id or name}_{len(self.spans)}"
        self._active_spans[key] = span
        self.spans.append(span)
        return key

    def stop_span(self, key: str, success: bool = True, meta: Optional[Dict[str, Any]] = None):
        """
        Completes duration measure.
        """
        span = self._active_spans.pop(key, None)
        if span:
            span.complete(success, meta)

    def get_waterfall_chart_data(self) -> List[Dict[str, Any]]:
        """
        Generates timeline records sorted by execution start times,
        ideal for plotting on a front-end Gantt chart.
        """
        return [span.to_dict() for span in self.spans]
