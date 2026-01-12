from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import json
import numpy as np

@dataclass
class PipelineTrace:
    listing_id: str
    steps: Dict[str, Any] = field(default_factory=dict)
    
    def log(self, step: str, data: Any):
        # Handle non-serializable types safely
        if hasattr(data, "model_dump"):
            self.steps[step] = data.model_dump()
        elif hasattr(data, "tolist"): # numpy
            self.steps[step] = data.tolist()
        else:
            self.steps[step] = data

class QATracer:
    """
    Tracer for capturing intermediate pipeline states during Golden Set runs.
    """
    def __init__(self):
        self.traces: List[PipelineTrace] = []
        self._current_trace: Optional[PipelineTrace] = None
        
    def start_trace(self, listing_id: str):
        self._current_trace = PipelineTrace(listing_id)
        
    def end_trace(self):
        if self._current_trace:
            self.traces.append(self._current_trace)
            self._current_trace = None
            
    def log(self, step: str, data: Any):
        if self._current_trace:
            self._current_trace.log(step, data)
            
    def get_traces(self) -> List[PipelineTrace]:
        return self.traces
