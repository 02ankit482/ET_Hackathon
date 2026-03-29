# event_logger.py
# ─────────────────────────────────────────────────────────────
# CrewAI Event Logger: Captures and broadcasts crew events
# to connected SSE clients in real-time.
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
import asyncio
from typing import Any, Callable, Dict, List
from datetime import datetime
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)
class CrewEventLogger:
    """
    Captures CrewAI events and broadcasts them to connected SSE clients.
    
    Usage:
        event_logger = CrewEventLogger(session_id="user_123")
        crew = Crew(..., step_callback=event_logger.callback, task_callback=event_logger.callback)
        
        # In SSE endpoint:
        async for event in event_logger.event_stream():
            yield f"data: {json.dumps(event)}\n\n"
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.events: List[Dict[str, Any]] = []
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self._closed = False
        
    def callback(self, step_output) -> None:
        """
        Callback function passed to CrewAI step_callback and task_callback.
        
        CrewAI callbacks receive different types of data:
        - step_callback: Called after each agent step with step output
        - task_callback: Called after task completion with task output
        
        The step_output can be:
        - A dict with keys like 'action', 'output', 'thought', etc.
        - A TaskOutput object with attributes
        - A string output
        """
        try:
            # Handle different input types from CrewAI
            if step_output is None:
                return
                
            event_data = {}
            
            # If it's a dict (legacy or custom format)
            if isinstance(step_output, dict):
                event_type = step_output.get("event", "step")
                data = step_output.get("data", step_output)
                event_data = self._parse_event(event_type, data)
            
            # If it's a TaskOutput object (from task_callback) - has model_dump method
            elif hasattr(step_output, 'model_dump'):
                logger.debug(f"[{self.session_id}] Processing TaskOutput")
                event_data = self._parse_task_output(step_output)
            
            # If it's an AgentFinish object (from step_callback) - has output and thought
            elif hasattr(step_output, 'output') and hasattr(step_output, 'thought'):
                logger.debug(f"[{self.session_id}] Processing AgentFinish")
                event_data = self._parse_agent_step(step_output)
            
            # If it's a string
            elif isinstance(step_output, str):
                event_data = {
                    "type": "output",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "content": self._truncate_output(step_output),
                }
            
            # Unknown format - try to extract what we can
            else:
                event_data = {
                    "type": "generic_event",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "data": str(step_output)[:500],
                }
            
            if event_data:
                # Store event
                self.events.append(event_data)
                
                # Broadcast to SSE clients
                if not self._closed:
                    try:
                        self.event_queue.put_nowait(event_data)
                    except asyncio.QueueFull:
                        logger.warning(f"Event queue full for session {self.session_id}")
        except Exception as e:
            logger.error(f"Error in event callback: {e}", exc_info=True)
    
    def _parse_agent_step(self, step) -> Dict[str, Any] | None:
        """Parse an agent step/action from CrewAI."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Handle AgentFinish from CrewAI
        if hasattr(step, 'output') and hasattr(step, 'thought'):
            return {
                "type": "agent_action",
                "timestamp": timestamp,
                "thought": self._truncate_output(str(getattr(step, 'thought', ''))),
                "output": self._truncate_output(str(getattr(step, 'output', ''))),
            }
        
        # Extract action if present (tool usage)
        if hasattr(step, 'action'):
            action = getattr(step, 'action', '')
            tool = getattr(step, 'tool', 'unknown')
            tool_input = getattr(step, 'tool_input', '')
            
            return {
                "type": "tool_started",
                "timestamp": timestamp,
                "tool_name": tool,
                "tool_input": self._truncate_output(str(tool_input)),
            }
        
        return None
    
    def _parse_task_output(self, task_output) -> Dict[str, Any] | None:
        """Parse a TaskOutput object from CrewAI."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # TaskOutput is a Pydantic model - use model_dump()
        try:
            data = task_output.model_dump() if hasattr(task_output, 'model_dump') else {}
            
            task_desc = data.get('description', 'Unnamed task')
            output_text = data.get('raw', '') or data.get('output', '')
            agent_name = data.get('agent', 'Unknown agent')
            
            return {
                "type": "task_completed",
                "timestamp": timestamp,
                "task_name": str(task_desc)[:100] if task_desc else "Unnamed task",
                "agent_name": str(agent_name)[:100] if agent_name else "Unknown",
                "output": self._truncate_output(str(output_text)),
            }
        except Exception as e:
            logger.warning(f"Failed to parse TaskOutput: {e}")
            # Fallback to string representation
            return {
                "type": "task_completed",
                "timestamp": timestamp,
                "task_name": "Task",
                "output": self._truncate_output(str(task_output)),
            }
    
    def _parse_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any] | None:
        """Parse CrewAI event into frontend-friendly format."""
        timestamp = datetime.utcnow().isoformat() + "Z"
        
        # Crew lifecycle events
        if event_type == "crew_kickoff_started":
            return {
                "type": "crew_started",
                "timestamp": timestamp,
                "crew_name": data.get("name", "crew"),
                "crew_id": data.get("id"),
            }
        
        elif event_type == "crew_kickoff_completed":
            return {
                "type": "crew_completed",
                "timestamp": timestamp,
                "crew_name": data.get("name", "crew"),
                "crew_id": data.get("id"),
            }
        
        elif event_type == "crew_kickoff_failed":
            return {
                "type": "crew_failed",
                "timestamp": timestamp,
                "crew_name": data.get("name", "crew"),
                "crew_id": data.get("id"),
                "error": str(data.get("error", "Unknown error")),
            }
        
        # Task events
        elif event_type == "task_started":
            return {
                "type": "task_started",
                "timestamp": timestamp,
                "task_name": data.get("name", "Unnamed task"),
                "task_id": data.get("id"),
                "description": data.get("description", ""),
            }
        
        elif event_type == "task_completed":
            return {
                "type": "task_completed",
                "timestamp": timestamp,
                "task_name": data.get("name", "Unnamed task"),
                "task_id": data.get("id"),
                "output": self._truncate_output(data.get("output", "")),
            }
        
        elif event_type == "task_failed":
            return {
                "type": "task_failed",
                "timestamp": timestamp,
                "task_name": data.get("name", "Unnamed task"),
                "task_id": data.get("id"),
                "error": str(data.get("error", "Unknown error")),
            }
        
        # Agent events
        elif event_type == "agent_started":
            return {
                "type": "agent_started",
                "timestamp": timestamp,
                "agent_name": data.get("name", "Unnamed agent"),
                "agent_role": data.get("role", ""),
            }
        
        elif event_type == "agent_finished":
            return {
                "type": "agent_finished",
                "timestamp": timestamp,
                "agent_name": data.get("name", "Unnamed agent"),
                "final_answer": self._truncate_output(data.get("final_answer", "")),
            }
        
        # Tool usage events
        elif event_type == "tool_usage_started":
            return {
                "type": "tool_started",
                "timestamp": timestamp,
                "tool_name": data.get("name", "Unknown tool"),
                "tool_input": self._truncate_output(str(data.get("input", ""))),
            }
        
        elif event_type == "tool_usage_finished":
            return {
                "type": "tool_finished",
                "timestamp": timestamp,
                "tool_name": data.get("name", "Unknown tool"),
                "tool_output": self._truncate_output(str(data.get("output", ""))),
            }
        
        # Thought process (LLM calls)
        elif event_type == "llm_call_started":
            return {
                "type": "thought_started",
                "timestamp": timestamp,
                "prompt": self._truncate_output(data.get("prompt", "")),
            }
        
        elif event_type == "llm_call_finished":
            return {
                "type": "thought_finished",
                "timestamp": timestamp,
                "response": self._truncate_output(data.get("response", "")),
            }
        
        # Unknown event - log for debugging
        else:
            logger.debug(f"Unknown event type: {event_type}")
            return None
    
    def _truncate_output(self, text: str, max_length: int = 500) -> str:
        """Truncate long outputs for frontend display."""
        if not text:
            return ""
        text_str = str(text)
        if len(text_str) <= max_length:
            return text_str
        return text_str[:max_length] + "..."
    
    async def event_stream(self):
        """
        Async generator for SSE streaming.
        
        Yields events as they arrive in the queue.
        """
        try:
            while not self._closed:
                try:
                    # Wait for event with timeout to allow checking _closed
                    event = await asyncio.wait_for(
                        self.event_queue.get(),
                        timeout=1.0
                    )
                    yield event
                except asyncio.TimeoutError:
                    # Send keepalive ping
                    yield {"type": "ping", "timestamp": datetime.utcnow().isoformat() + "Z"}
                except Exception as e:
                    logger.error(f"Error in event stream: {e}")
                    break
        finally:
            self._closed = True
    
    def close(self):
        """Close the event logger and stop streaming."""
        self._closed = True
    
    def get_all_events(self) -> List[Dict[str, Any]]:
        """Get all captured events (for debugging or replay)."""
        return self.events.copy()


# Global registry for active event loggers (keyed by session_id)
_active_loggers: Dict[str, CrewEventLogger] = {}


def get_event_logger(session_id: str) -> CrewEventLogger:
    """Get or create an event logger for a session."""
    if session_id not in _active_loggers:
        _active_loggers[session_id] = CrewEventLogger(session_id)
    return _active_loggers[session_id]


def cleanup_event_logger(session_id: str):
    """Remove and close an event logger."""
    if session_id in _active_loggers:
        _active_loggers[session_id].close()
        del _active_loggers[session_id]
