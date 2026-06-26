"""
FastAPI Application for Multi-Agent Orchestration Platform.
"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agents.base import ReasoningAgent
from agents.orchestrator import AgentOrchestrator, HITLBridge
from memory.store import HybridMemoryStore, create_memory_store
from models.schemas import (
    ExecuteTaskRequest, ExecuteTaskResponse,
    ApprovalRequest, ApprovalResponse, HealthResponse,
    Agent, AgentCapability, AgentEvent, EventType
)


# ─────────────────────────────────────────────────────────
# Application State
# ─────────────────────────────────────────────────────────
class AppState:
    """Application state container."""
    
    def __init__(self):
        self.memory_store: Optional[HybridMemoryStore] = None
        self.hitl_bridge: Optional[HITLBridge] = None
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.agents: dict[str, ReasoningAgent] = {}
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.initialized = False


state = AppState()


# ─────────────────────────────────────────────────────────
# Lifespan Management
# ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Startup
    await initialize_app()
    yield
    # Shutdown
    await shutdown_app()


async def initialize_app():
    """Initialize application components."""
    if state.initialized:
        return
    
    print("Initializing Multi-Agent Platform...")
    
    # Configuration (from environment or defaults)
    database_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/agent_platform"
    redis_url = "redis://localhost:6379/0"
    vector_db_path = "./data/chroma"
    
    # Initialize memory store
    try:
        state.memory_store = await create_memory_store(
            database_url=database_url,
            vector_db_path=vector_db_path,
            redis_url=redis_url
        )
        print("✓ Memory store initialized")
    except Exception as e:
        print(f"⚠ Memory store initialization failed: {e}")
        # Create a mock memory store for development
        state.memory_store = None
    
    # Initialize HITL bridge
    state.hitl_bridge = HITLBridge()
    print("✓ HITL bridge initialized")
    
    # Initialize orchestrator
    state.orchestrator = AgentOrchestrator(
        memory_store=state.memory_store,
        hitl_bridge=state.hitl_bridge
    )
    print("✓ Orchestrator initialized")
    
    # Register default agents
    await register_default_agents()
    
    state.initialized = True
    print("✓ Application ready!")


async def shutdown_app():
    """Cleanup on shutdown."""
    if state.memory_store:
        await state.memory_store.close()
    print("Application shutdown complete.")


async def register_default_agents():
    """Register default system agents."""
    
    # Reasoning Agent
    reasoning_agent = ReasoningAgent(
        id="reasoning-agent",
        name="Reasoning Assistant",
        description="General-purpose reasoning and analysis agent",
        model="gpt-4-turbo-preview",
        capabilities=[
            AgentCapability(
                type="reasoning",
                description="Performs step-by-step reasoning on complex problems"
            ),
            AgentCapability(
                type="analysis",
                description="Analyzes and summarizes information"
            )
        ]
    )
    
    state.agents["reasoning-agent"] = reasoning_agent
    state.orchestrator.register_agent(reasoning_agent)
    
    print("✓ Default agents registered")


# ─────────────────────────────────────────────────────────
# FastAPI Application
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Multi-Agent Orchestration Platform",
    description="Enterprise-grade multi-agent system with human-in-the-loop capabilities",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────
# Health & Info Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="0.1.0",
        services={
            "memory_store": state.memory_store is not None,
            "orchestrator": state.orchestrator is not None,
            "hitl_bridge": state.hitl_bridge is not None
        }
    )


@app.get("/api/info")
async def get_info():
    """Get platform information."""
    return {
        "name": "Multi-Agent Orchestration Platform",
        "version": "0.1.0",
        "description": "Enterprise-grade multi-agent system with HITL",
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "capabilities": [c.model_dump() for c in agent.capabilities]
            }
            for agent in state.agents.values()
        ]
    }


# ─────────────────────────────────────────────────────────
# Agent Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/api/agents")
async def list_agents():
    """List all available agents."""
    return {
        "agents": [
            {
                "id": agent.id,
                "name": agent.name,
                "description": agent.description,
                "model": agent.model,
                "capabilities": [c.model_dump() for c in agent.capabilities]
            }
            for agent in state.agents.values()
        ]
    }


@app.get("/api/agents/{agent_id}")
async def get_agent(agent_id: str):
    """Get details for a specific agent."""
    agent = state.agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return {
        "id": agent.id,
        "name": agent.name,
        "description": agent.description,
        "model": agent.model,
        "capabilities": [c.model_dump() for c in agent.capabilities]
    }


# ─────────────────────────────────────────────────────────
# Task Execution Endpoints
# ─────────────────────────────────────────────────────────
@app.post("/api/execute", response_model=ExecuteTaskResponse)
async def execute_task(request: ExecuteTaskRequest, user_id: str = Query(default="default-user")):
    """
    Execute a task with the specified agent.
    Returns immediately with a workflow_id for tracking.
    """
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    
    if request.agent_id not in state.agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # Execute task
    result = await state.orchestrator.execute(
        agent_id=request.agent_id,
        user_id=user_id,
        task=request.task,
        context=request.context,
        config=request.config
    )
    
    return ExecuteTaskResponse(
        workflow_id=result.get("workflow_id", ""),
        status=result.get("status", "pending"),
        message=result.get("error", "") if result.get("status") == "failed" else "Task submitted successfully"
    )


@app.post("/api/execute/stream")
async def execute_task_stream(request: ExecuteTaskRequest, user_id: str = Query(default="default-user")):
    """
    Execute a task and stream results via Server-Sent Events.
    """
    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not available")
    
    if request.agent_id not in state.agents:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    return StreamingResponse(
        execution_stream(state.orchestrator, request.agent_id, user_id, request.task),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Transfer-Encoding": "chunked"
        }
    )


async def execution_stream(
    orchestrator: AgentOrchestrator,
    agent_id: str,
    user_id: str,
    task: str
):
    """Generate SSE stream for task execution."""
    
    async for event in orchestrator.stream_execute(
        agent_id=agent_id,
        user_id=user_id,
        task=task
    ):
        yield f"data: {json.dumps(event)}\n\n"
        
        # Small delay for streaming effect
        await asyncio.sleep(0.01)
    
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


class StreamingResponse:
    """Simple streaming response wrapper."""
    
    def __init__(self, generator, media_type: str, headers: dict):
        self.generator = generator
        self.media_type = media_type
        self.headers = headers
    
    async def __call__(self, scope, receive, send):
        await self._stream_response(scope, receive, send)
    
    async def _stream_response(self, scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [[k.encode(), v.encode()] for k, v in self.headers.items()]
        })
        
        async for chunk in self.generator:
            await send({
                "type": "http.response.body",
                "body": chunk.encode()
            })
        
        await send({"type": "http.response.body", "body": b""})


# ─────────────────────────────────────────────────────────
# Workflow Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/api/workflows/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """Get the status of a workflow execution."""
    # In production, this would query the database
    return {
        "workflow_id": workflow_id,
        "status": "completed",
        "message": "Workflow status lookup would be implemented here"
    }


# ─────────────────────────────────────────────────────────
# HITL Approval Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/api/approvals")
async def list_pending_approvals(user_id: str = Query(default="default-user")):
    """List pending approval requests for a user."""
    if not state.hitl_bridge:
        return {"approvals": []}
    
    approvals = await state.hitl_bridge.get_pending_approvals(user_id)
    
    return {
        "approvals": [
            {
                "id": req.id,
                "workflow_id": req.workflow_id,
                "title": req.title,
                "description": req.description,
                "context": req.context,
                "suggested_actions": [a.model_dump() for a in req.suggested_actions],
                "status": req.status.value,
                "expires_at": req.expires_at.isoformat(),
                "is_expired": req.is_expired
            }
            for req in approvals
        ]
    }


@app.get("/api/approvals/{request_id}")
async def get_approval_request(request_id: str):
    """Get details of a specific approval request."""
    if not state.hitl_bridge:
        raise HTTPException(status_code=503, detail="HITL service not available")
    
    request = await state.hitl_bridge.get_request(request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    return {
        "id": request.id,
        "workflow_id": request.workflow_id,
        "checkpoint_id": request.checkpoint_id,
        "title": request.title,
        "description": request.description,
        "context": request.context,
        "suggested_actions": [a.model_dump() for a in request.suggested_actions],
        "status": request.status.value,
        "requested_at": request.requested_at.isoformat(),
        "expires_at": request.expires_at.isoformat(),
        "responded_by": request.responded_by,
        "responded_at": request.responded_at.isoformat() if request.responded_at else None,
        "response_data": request.response_data,
        "is_expired": request.is_expired
    }


@app.post("/api/approvals", response_model=ApprovalResponse)
async def submit_approval(request: ApprovalRequest):
    """Submit an approval decision."""
    if not state.hitl_bridge:
        raise HTTPException(status_code=503, detail="HITL service not available")
    
    success = await state.hitl_bridge.approve(
        request_id=request.request_id,
        user_id=request.user_id,
        approved=request.approved,
        response_data=request.response_data
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Approval request not found or already processed")
    
    # Get the workflow_id for the response
    approval_req = await state.hitl_bridge.get_request(request.request_id)
    
    return ApprovalResponse(
        success=True,
        message="Approval submitted successfully",
        workflow_id=approval_req.workflow_id if approval_req else None
    )


# ─────────────────────────────────────────────────────────
# Memory Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/api/memory/search")
async def search_memory(
    query: str = Query(..., min_length=1),
    user_id: str = Query(default="default-user"),
    top_k: int = Query(default=5, ge=1, le=20)
):
    """Search memory for relevant context."""
    if not state.memory_store:
        return {"results": [], "message": "Memory store not available"}
    
    results = await state.memory_store.semantic_search(
        query=query,
        user_id=user_id,
        top_k=top_k
    )
    
    return {
        "results": [
            {
                "id": r.entry.id,
                "content": r.entry.content,
                "relevance_score": r.relevance_score,
                "metadata": r.entry.metadata.model_dump(),
                "created_at": r.entry.created_at.isoformat()
            }
            for r in results
        ]
    }


@app.post("/api/memory")
async def add_memory(
    content: str = Query(...),
    user_id: str = Query(default="default-user"),
    source: str = Query(default="user_input"),
    memory_type: str = Query(default="context"),
    importance: str = Query(default="medium")
):
    """Add a new memory entry."""
    if not state.memory_store:
        raise HTTPException(status_code=503, detail="Memory store not available")
    
    from models.schemas import MemoryMetadata, MemorySource, MemoryType, Importance
    
    entry = await state.memory_store.insert(
        content=content,
        metadata=MemoryMetadata(
            source=MemorySource(source),
            type=MemoryType(memory_type),
            importance=Importance(importance)
        ),
        user_id=user_id
    )
    
    return {
        "id": entry.id,
        "content": entry.content,
        "created_at": entry.created_at.isoformat()
    }


# ─────────────────────────────────────────────────────────
# WebSocket Endpoints
# ─────────────────────────────────────────────────────────
@app.websocket("/ws/{workflow_id}")
async def websocket_endpoint(websocket: WebSocket, workflow_id: str):
    """WebSocket endpoint for real-time workflow updates."""
    await websocket.accept()
    
    # Register connection
    if workflow_id not in state.active_connections:
        state.active_connections[workflow_id] = []
    state.active_connections[workflow_id].append(websocket)
    
    try:
        # Send initial connection message
        await websocket.send_json({
            "type": "connected",
            "workflow_id": workflow_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Keep connection alive and handle messages
        while True:
            try:
                # Wait for messages from client
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Handle ping/pong
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
                # Handle approval responses via WebSocket
                elif message.get("type") == "approval_response":
                    if state.hitl_bridge:
                        await state.hitl_bridge.approve(
                            request_id=message.get("request_id"),
                            user_id=message.get("user_id", "websocket-user"),
                            approved=message.get("approved", True),
                            response_data=message.get("response_data")
                        )
                
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON"
                })
    
    except WebSocketDisconnect:
        pass
    
    finally:
        # Clean up connection
        if workflow_id in state.active_connections:
            state.active_connections[workflow_id].remove(websocket)


async def broadcast_to_workflow(workflow_id: str, message: dict):
    """Broadcast a message to all WebSocket connections for a workflow."""
    if workflow_id in state.active_connections:
        dead_connections = []
        
        for websocket in state.active_connections[workflow_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.append(websocket)
        
        # Remove dead connections
        for ws in dead_connections:
            state.active_connections[workflow_id].remove(ws)


# ─────────────────────────────────────────────────────────
# Run Application
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
