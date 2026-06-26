"""
Multi-Agent Orchestrator with LangGraph and Human-in-the-Loop Support.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, TypedDict, Optional
from uuid import uuid4

# Try to import LangGraph - make it optional for development/testing
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    StateGraph = None
    END = None

from pydantic import BaseModel, Field

from agents.base import BaseAgent, AgentResponse
from memory.store import HybridMemoryStore
from models.schemas import (
    AgentEvent, AgentCapability, EventType,
    HITLApprovalRequest, ApprovalAction, ApprovalStatus,
    MemoryEntry, MemoryMetadata, MemorySource, MemoryType, Importance
)


# ─────────────────────────────────────────────────────────
# State Definition
# ─────────────────────────────────────────────────────────
class OrchestratorState(TypedDict, total=False):
    """State managed throughout the agent workflow."""
    workflow_id: str
    agent_id: str
    user_id: str
    task: str
    context: dict[str, Any]
    memory_results: list[dict[str, Any]]
    current_step: str
    hitl_checkpoint: str | None
    hitl_request_id: str | None
    approved_data: dict[str, Any] | None
    result: dict[str, Any] | None
    error: str | None
    events: list[AgentEvent]


class HITLCheckpointConfig(BaseModel):
    """Configuration for a human approval checkpoint."""
    checkpoint_id: str = Field(default_factory=uuid4)
    title: str
    description: str
    context_summary: dict[str, Any]
    notification_channels: list[str] = ["push", "email"]
    timeout_hours: int = 24
    suggested_actions: list[ApprovalAction] = Field(default_factory=list)
    require_multi_approval: bool = False
    approvers: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────
# Notification Service (Protocol for dependency injection)
# ─────────────────────────────────────────────────────────
class NotificationServiceProtocol:
    """Protocol for notification services."""
    
    async def send(
        self,
        user_id: str,
        channels: list[str],
        title: str,
        body: str,
        data: dict[str, Any]
    ) -> bool:
        """Send a notification to a user."""
        ...


class ConsoleNotificationService:
    """Development notification service that prints to console."""
    
    async def send(
        self,
        user_id: str,
        channels: list[str],
        title: str,
        body: str,
        data: dict[str, Any]
    ) -> bool:
        # Convert UUID to string for JSON serialization
        serializable_data = {}
        for k, v in data.items():
            if hasattr(v, '__str__') and type(v).__name__ == 'UUID':
                serializable_data[k] = str(v)
            else:
                serializable_data[k] = v
        
        print(f"\n{'='*60}")
        print(f"NOTIFICATION to {user_id}")
        print(f"Channels: {channels}")
        print(f"Title: {title}")
        print(f"Body: {body}")
        print(f"Data: {json.dumps(serializable_data, indent=2)}")
        print(f"{'='*60}\n")
        return True


# ─────────────────────────────────────────────────────────
# HITL Bridge
# ─────────────────────────────────────────────────────────
class HITLBridge:
    """
    Manages Human-in-the-Loop checkpoints and approvals.
    Handles workflow pausing, notification, and resumption.
    """
    
    def __init__(
        self,
        notification_service: Optional[NotificationServiceProtocol] = None,
        redis_client: Optional[Any] = None,
        default_timeout_hours: int = 24
    ):
        self.notification_service = notification_service or ConsoleNotificationService()
        self.redis = redis_client
        self.default_timeout_hours = default_timeout_hours
        self._pending_approvals: dict[str, HITLApprovalRequest] = {}
        self._approval_futures: dict[str, asyncio.Future] = {}
    
    async def create_checkpoint(
        self,
        workflow_id: str,
        config: HITLCheckpointConfig,
        user_id: str
    ) -> HITLApprovalRequest:
        """Create a new HITL checkpoint and notify users."""
        
        request = HITLApprovalRequest(
            id=str(uuid4()),
            workflow_id=workflow_id,
            checkpoint_id=str(config.checkpoint_id),
            title=config.title,
            description=config.description,
            context=config.context_summary,
            suggested_actions=config.suggested_actions,
            status=ApprovalStatus.PENDING,
            requested_by="system",
            expires_at=datetime.utcnow() + timedelta(hours=config.timeout_hours)
        )
        
        # Store pending approval
        self._pending_approvals[request.id] = request
        
        # Store in Redis for distributed access
        if self.redis:
            await self.redis.setex(
                f"hitl:{request.id}",
                ttl=config.timeout_hours * 3600,
                value=json.dumps({
                    "workflow_id": workflow_id,
                    "checkpoint_id": config.checkpoint_id,
                    "status": "pending"
                })
            )
        
        # Create future for async waiting
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._approval_futures[request.id] = future
        
        # Send notifications
        await self.notification_service.send(
            user_id=user_id,
            channels=config.notification_channels,
            title=config.title,
            body=config.description,
            data={
                "approval_id": request.id,
                "workflow_id": workflow_id,
                "checkpoint_id": config.checkpoint_id,
                "expires_at": request.expires_at.isoformat()
            }
        )
        
        return request
    
    async def wait_for_approval(self, request_id: str) -> tuple[bool, dict[str, Any]]:
        """
        Wait for human approval.
        Returns (approved, response_data) tuple.
        """
        future = self._approval_futures.get(request_id)
        
        if not future:
            return False, {"error": "Approval request not found"}
        
        # Wait with timeout based on request expiry
        request = self._pending_approvals.get(request_id)
        if request:
            timeout = (request.expires_at - datetime.utcnow()).total_seconds()
            timeout = max(timeout, 0)
            
            try:
                result = await asyncio.wait_for(future, timeout=timeout)
                return result
            except asyncio.TimeoutError:
                await self._expire_request(request_id)
                return False, {"error": "Approval timed out"}
        else:
            # No request found, wait indefinitely
            return await future
    
    async def approve(
        self,
        request_id: str,
        user_id: str,
        approved: bool,
        response_data: Optional[dict[str, Any]] = None
    ) -> bool:
        """Process an approval decision."""
        request = self._pending_approvals.get(request_id)
        
        if not request:
            return False
        
        # Update request status
        request.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        request.responded_by = user_id
        request.responded_at = datetime.utcnow()
        request.response_data = response_data or {}
        
        # Remove from Redis
        if self.redis:
            await self.redis.delete(f"hitl:{request_id}")
        
        # Complete the future
        future = self._approval_futures.get(request_id)
        if future and not future.done():
            future.set_result((approved, response_data or {}))
        
        # Clean up
        self._pending_approvals.pop(request_id, None)
        self._approval_futures.pop(request_id, None)
        
        return True
    
    async def _expire_request(self, request_id: str) -> None:
        """Mark a request as expired."""
        request = self._pending_approvals.get(request_id)
        
        if request:
            request.status = ApprovalStatus.EXPIRED
            
            if self.redis:
                await self.redis.delete(f"hitl:{request_id}")
            
            # Complete future with rejection
            future = self._approval_futures.get(request_id)
            if future and not future.done():
                future.set_result((False, {"error": "Request expired"}))
            
            self._pending_approvals.pop(request_id, None)
            self._approval_futures.pop(request_id, None)
    
    async def get_pending_approvals(self, user_id: str) -> list[HITLApprovalRequest]:
        """Get all pending approvals for a user."""
        return [
            req for req in self._pending_approvals.values()
            if req.status == ApprovalStatus.PENDING and not req.is_expired
        ]
    
    async def get_request(self, request_id: str) -> Optional[HITLApprovalRequest]:
        """Get a specific approval request."""
        return self._pending_approvals.get(request_id)


# ─────────────────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────────────────
class AgentOrchestrator:
    """
    Main orchestrator service managing agent execution with LangGraph.
    Supports human-in-the-loop checkpoints and persistent memory.
    """
    
    def __init__(
        self,
        memory_store: HybridMemoryStore,
        hitl_bridge: Optional[HITLBridge] = None,
        event_handlers: Optional[list[callable]] = None
    ):
        self.memory_store = memory_store
        self.hitl_bridge = hitl_bridge or HITLBridge()
        self.event_handlers = event_handlers or []
        
        # Agent registry
        self._agents: dict[str, BaseAgent] = {}
        
        # Build workflow graph
        self.workflow_graph = self._build_workflow_graph()
    
    def register_agent(self, agent: BaseAgent) -> None:
        """Register an agent for use in workflows."""
        self._agents[agent.id] = agent
    
    def get_agent(self, agent_id: str) -> Optional[BaseAgent]:
        """Get a registered agent by ID."""
        return self._agents.get(agent_id)
    
    async def execute(
        self,
        agent_id: str,
        user_id: str,
        task: str,
        context: Optional[dict[str, Any]] = None,
        config: Optional[dict[str, Any]] = None,
        hitl_enabled: bool = True
    ) -> dict[str, Any]:
        """
        Execute an agent task with memory and HITL support.
        
        Args:
            agent_id: ID of the agent to use
            user_id: User executing the task
            task: Task description
            context: Additional context data
            config: Execution configuration
            hitl_enabled: Whether HITL checkpoints are enabled
            
        Returns:
            Execution result with status and output
        """
        agent = self.get_agent(agent_id)
        if not agent:
            return {"status": "failed", "error": f"Agent not found: {agent_id}"}
        
        workflow_id = str(uuid4())
        config = config or {}
        
        # Initial state
        initial_state: OrchestratorState = {
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "task": task,
            "context": context or {},
            "memory_results": [],
            "current_step": "retrieve_context",
            "hitl_checkpoint": None,
            "hitl_request_id": None,
            "approved_data": None,
            "result": None,
            "error": None,
            "events": []
        }
        
        # Emit start event
        await self._emit_event(
            workflow_id,
            EventType.WORKFLOW_START,
            content=f"Starting workflow with agent {agent.name}",
            agent_id=agent_id
        )
        
        # Run workflow
        try:
            # Check if workflow has astream method (LangGraph) or is a simple async generator
            if hasattr(self.workflow_graph, 'astream'):
                final_state = None
                async for state in self.workflow_graph.astream(initial_state):
                    final_state = state
                    # Emit state updates
                    current_step = state.get("current_step", "unknown")
                    
                    await self._emit_event(
                        workflow_id,
                        EventType.WORKFLOW_UPDATE,
                        content=f"Step: {current_step}",
                        agent_id=agent_id,
                        metadata=state
                    )
                    
                    # Handle HITL checkpoint
                    if hitl_enabled and state.get("hitl_checkpoint"):
                        await self._emit_event(
                            workflow_id,
                            EventType.APPROVAL_REQUIRED,
                            content=state.get("hitl_checkpoint", "Approval required"),
                            agent_id=agent_id,
                            metadata=state
                        )
                        
                        # Wait for approval
                        if state.get("hitl_request_id"):
                            approved, response_data = await self.hitl_bridge.wait_for_approval(
                                state["hitl_request_id"]
                            )
                            
                            await self._emit_event(
                                workflow_id,
                                EventType.APPROVAL_RECEIVED,
                                content=f"Approval received: {approved}",
                                agent_id=agent_id
                            )
                            
                            if not approved:
                                return {
                                    "status": "rejected",
                                    "workflow_id": workflow_id,
                                    "result": response_data
                                }
            else:
                # Simple workflow (no LangGraph) - async generator
                final_state = None
                async for step_result in self.workflow_graph(initial_state):
                    if isinstance(step_result, dict) and "state" in step_result:
                        final_state = step_result["state"]
                        step_name = step_result.get("step", "unknown")
                        
                        # Emit state updates for non-done steps
                        if step_name != "done":
                            await self._emit_event(
                                workflow_id,
                                EventType.WORKFLOW_UPDATE,
                                content=f"Step: {final_state.get('current_step', step_name)}",
                                agent_id=agent_id,
                                metadata=final_state
                            )
            
            if final_state is None:
                final_state = initial_state
            
            # Workflow completed
            await self._emit_event(
                workflow_id,
                EventType.WORKFLOW_COMPLETE,
                content="Workflow completed successfully",
                agent_id=agent_id,
                metadata=final_state
            )
            
            return {
                "status": "completed",
                "workflow_id": workflow_id,
                "result": final_state.get("result", {})
            }
            
        except Exception as e:
            await self._emit_event(
                workflow_id,
                EventType.AGENT_ERROR,
                content=f"Workflow error: {str(e)}",
                agent_id=agent_id
            )
            
            return {
                "status": "failed",
                "workflow_id": workflow_id,
                "error": str(e)
            }
    
    async def stream_execute(
        self,
        agent_id: str,
        user_id: str,
        task: str,
        context: Optional[dict[str, Any]] = None,
        hitl_enabled: bool = True
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream workflow execution events.
        Yields real-time updates as the workflow progresses.
        """
        agent = self.get_agent(agent_id)
        if not agent:
            yield {"type": "error", "content": f"Agent not found: {agent_id}"}
            return
        
        workflow_id = str(uuid4())
        
        yield {
            "type": "workflow_start",
            "workflow_id": workflow_id,
            "agent_id": agent_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        try:
            # Retrieve context from memory
            memory_results = []
            if self.memory_store:
                results = await self.memory_store.semantic_search(
                    query=task,
                    user_id=user_id,
                    top_k=5
                )
                memory_results = [
                    {"content": r.entry.content, "relevance": r.relevance_score}
                    for r in results
                ]
                
                yield {
                    "type": "memory_retrieved",
                    "count": len(memory_results),
                    "entries": memory_results
                }
            
            # Emit thought
            yield {
                "type": "agent_thought",
                "content": f"Analyzing task: {task[:100]}...",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Execute agent
            memory_entries = [
                MemoryEntry(
                    id=f"ctx-{i}",
                    content=r["content"],
                    metadata=MemoryMetadata(
                        source=MemorySource.AGENT_GENERATED,
                        type=MemoryType.CONTEXT
                    )
                )
                for i, r in enumerate(memory_results)
            ]
            
            response = await agent.execute(
                task=task,
                context=memory_entries,
                stream=False
            )
            
            yield {
                "type": "agent_result",
                "content": response.output,
                "confidence": response.confidence,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Store in memory
            if self.memory_store:
                await self.memory_store.insert(
                    content=f"Task: {task}\nResponse: {response.output}",
                    metadata=MemoryMetadata(
                        source=MemorySource.CONVERSATION,
                        type=MemoryType.HISTORY,
                        tags=["task", "response"]
                    ),
                    user_id=user_id,
                    agent_id=agent_id
                )
            
            yield {
                "type": "workflow_complete",
                "workflow_id": workflow_id,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            yield {
                "type": "error",
                "content": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
    
    # ─────────────────────────────────────────────────────
    # Workflow Graph Construction
    # ─────────────────────────────────────────────────────
    
    def _build_workflow_graph(self):
        """Build the LangGraph workflow with HITL support."""
        
        if not LANGGRAPH_AVAILABLE:
            # Return a simple async generator for development
            async def simple_workflow(initial_state):
                """Simple workflow for development without LangGraph."""
                state = initial_state.copy()
                
                # Execute nodes sequentially
                state = await self._node_retrieve_context(state)
                yield {"step": "retrieve_context", "state": state}
                
                state = await self._node_execute_task(state)
                yield {"step": "execute_task", "state": state}
                
                state = await self._node_pre_execution_check(state)
                yield {"step": "pre_execution_check", "state": state}
                
                # Handle approval if needed
                if state.get("hitl_checkpoint"):
                    state = await self._node_await_approval(state)
                    yield {"step": "await_approval", "state": state}
                    
                    if not state.get("error"):
                        state = await self._node_execute_task(state)
                        yield {"step": "retry_execute", "state": state}
                
                state = await self._node_store_result(state)
                yield {"step": "store_result", "state": state}
                
                # Return final state as last yielded value
                yield {"step": "done", "state": state}
            
            return simple_workflow
        
        workflow = StateGraph(OrchestratorState)
        
        # Define nodes
        workflow.add_node("retrieve_context", self._node_retrieve_context)
        workflow.add_node("execute_task", self._node_execute_task)
        workflow.add_node("check_pre_execution", self._node_pre_execution_check)
        workflow.add_node("await_approval", self._node_await_approval)
        workflow.add_node("store_result", self._node_store_result)
        workflow.add_node("handle_error", self._node_handle_error)
        
        # Define edges
        workflow.add_edge("retrieve_context", "execute_task")
        workflow.add_edge("execute_task", "check_pre_execution")
        
        # Conditional routing after pre-execution check
        workflow.add_conditional_edges(
            "check_pre_execution",
            self._should_wait_for_approval,
            {
                "await_approval": "await_approval",
                "continue": "store_result"
            }
        )
        
        workflow.add_edge("await_approval", "execute_task")
        workflow.add_edge("store_result", END)
        workflow.add_edge("handle_error", END)
        
        # Set entry point
        workflow.set_entry_point("retrieve_context")
        
        return workflow.compile()
    
    async def _node_retrieve_context(self, state: OrchestratorState) -> OrchestratorState:
        """Retrieve relevant context from memory."""
        if not self.memory_store:
            return state
        
        results = await self.memory_store.semantic_search(
            query=state["task"],
            user_id=state["user_id"],
            agent_id=state["agent_id"],
            top_k=5
        )
        
        memory_results = [
            {"id": r.entry.id, "content": r.entry.content, "relevance": r.relevance_score}
            for r in results
        ]
        
        state["memory_results"] = memory_results
        state["current_step"] = "retrieve_context"
        
        return state
    
    async def _node_execute_task(self, state: OrchestratorState) -> OrchestratorState:
        """Execute the main agent task."""
        agent = self.get_agent(state["agent_id"])
        
        if not agent:
            state["error"] = f"Agent not found: {state['agent_id']}"
            return state
        
        # Convert memory results to MemoryEntry objects
        memory_entries = [
            MemoryEntry(
                id=r["id"],
                content=r["content"],
                metadata=MemoryMetadata(
                    source=MemorySource.MEMORY,
                    type=MemoryType.CONTEXT
                )
            )
            for r in state.get("memory_results", [])
        ]
        
        # Execute agent
        response = await agent.execute(
            task=state["task"],
            context=memory_entries,
            stream=False
        )
        
        state["result"] = {
            "output": response.output,
            "confidence": response.confidence,
            "context_used": response.context_used
        }
        state["current_step"] = "execute_task"
        
        return state
    
    async def _node_pre_execution_check(self, state: OrchestratorState) -> OrchestratorState:
        """
        Pre-execution checkpoint for sensitive operations.
        Creates HITL checkpoint if confidence is low.
        """
        result = state.get("result", {})
        confidence = result.get("confidence", 1.0)
        
        # Low confidence threshold
        if confidence < 0.7:
            config = HITLCheckpointConfig(
                title="Low Confidence Result",
                description=f"The agent produced a result with {confidence:.0%} confidence. Please review.",
                context_summary={
                    "task": state["task"],
                    "confidence": confidence,
                    "result_preview": str(result.get("output", ""))[:500]
                },
                suggested_actions=[
                    ApprovalAction(label="Approve", value="approve"),
                    ApprovalAction(label="Retry", value="retry"),
                    ApprovalAction(label="Reject", value="reject")
                ]
            )
            
            request = await self.hitl_bridge.create_checkpoint(
                workflow_id=state["workflow_id"],
                config=config,
                user_id=state["user_id"]
            )
            
            state["hitl_checkpoint"] = config.checkpoint_id
            state["hitl_request_id"] = request.id
        
        state["current_step"] = "check_pre_execution"
        return state
    
    async def _node_await_approval(self, state: OrchestratorState) -> OrchestratorState:
        """Wait for human approval."""
        if not state.get("hitl_request_id"):
            return state
        
        approved, response_data = await self.hitl_bridge.wait_for_approval(
            state["hitl_request_id"]
        )
        
        state["approved_data"] = response_data
        state["hitl_checkpoint"] = None
        state["hitl_request_id"] = None
        
        if not approved:
            state["error"] = "Approval rejected by human"
        
        state["current_step"] = "await_approval"
        return state
    
    async def _node_store_result(self, state: OrchestratorState) -> OrchestratorState:
        """Store the final result in memory."""
        if self.memory_store and state.get("result"):
            await self.memory_store.insert(
                content=f"Task: {state['task']}\nResult: {state['result']}",
                metadata=MemoryMetadata(
                    source=MemorySource.AGENT_GENERATED,
                    type=MemoryType.HISTORY,
                    tags=["workflow", "result"]
                ),
                user_id=state["user_id"],
                agent_id=state["agent_id"]
            )
        
        state["current_step"] = "store_result"
        return state
    
    async def _node_handle_error(self, state: OrchestratorState) -> OrchestratorState:
        """Handle workflow errors."""
        state["current_step"] = "handle_error"
        return state
    
    def _should_wait_for_approval(self, state: OrchestratorState) -> str:
        """Determine if we should wait for approval."""
        if state.get("hitl_checkpoint"):
            return "await_approval"
        return "continue"
    
    # ─────────────────────────────────────────────────────
    # Event Handling
    # ─────────────────────────────────────────────────────
    
    async def _emit_event(
        self,
        workflow_id: str,
        event_type: EventType,
        content: str,
        agent_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> None:
        """Emit an event to all registered handlers."""
        event = AgentEvent(
            type=event_type,
            workflow_id=workflow_id,
            agent_id=agent_id,
            content=content,
            metadata=metadata or {}
        )
        
        for handler in self.event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                print(f"Error in event handler: {e}")
