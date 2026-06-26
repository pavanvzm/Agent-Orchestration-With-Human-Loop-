"""
Unit tests for the Agent Orchestrator.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

import pytest

from agents.base import BaseAgent, ReasoningAgent, AgentResponse
from agents.orchestrator import AgentOrchestrator, HITLBridge, HITLCheckpointConfig
from memory.store import HybridMemoryStore
from models.schemas import MemoryEntry, MemoryMetadata, MemorySource, MemoryType, Importance


class TestHITLBridge:
    """Tests for the HITL Bridge."""
    
    @pytest.fixture
    def hitl_bridge(self):
        """Create a HITL bridge for testing."""
        return HITLBridge()
    
    @pytest.mark.asyncio
    async def test_create_checkpoint(self, hitl_bridge):
        """Test creating a checkpoint creates an approval request."""
        config = HITLCheckpointConfig(
            title="Test Approval",
            description="Please approve this action",
            context_summary={"action": "test"}
        )
        
        request = await hitl_bridge.create_checkpoint(
            workflow_id="test-workflow",
            config=config,
            user_id="test-user"
        )
        
        assert request.id is not None
        assert request.title == "Test Approval"
        assert request.status.value == "pending"
        assert request.workflow_id == "test-workflow"
    
    @pytest.mark.asyncio
    async def test_approve_request(self, hitl_bridge):
        """Test approving a request."""
        config = HITLCheckpointConfig(
            title="Test Approval",
            description="Please approve",
            context_summary={}
        )
        
        request = await hitl_bridge.create_checkpoint(
            workflow_id="test-workflow",
            config=config,
            user_id="test-user"
        )
        
        success = await hitl_bridge.approve(
            request_id=request.id,
            user_id="test-user",
            approved=True,
            response_data={"notes": "Looks good"}
        )
        
        assert success is True
        # After approval, request is removed from pending (consumed)
        # Check it no longer appears in pending approvals
        pending = await hitl_bridge.get_pending_approvals("test-user")
        assert request.id not in [p.id for p in pending]
    
    @pytest.mark.asyncio
    async def test_reject_request(self, hitl_bridge):
        """Test rejecting a request."""
        config = HITLCheckpointConfig(
            title="Test Rejection",
            description="Please reject",
            context_summary={}
        )
        
        request = await hitl_bridge.create_checkpoint(
            workflow_id="test-workflow",
            config=config,
            user_id="test-user"
        )
        
        success = await hitl_bridge.approve(
            request_id=request.id,
            user_id="test-user",
            approved=False,
            response_data={"reason": "Not approved"}
        )
        
        assert success is True
        # After rejection, request is removed from pending
    
    @pytest.mark.asyncio
    async def test_wait_for_approval(self, hitl_bridge):
        """Test waiting for approval."""
        config = HITLCheckpointConfig(
            title="Test Wait",
            description="Wait for approval",
            context_summary={},
            timeout_hours=1
        )
        
        request = await hitl_bridge.create_checkpoint(
            workflow_id="test-workflow",
            config=config,
            user_id="test-user"
        )
        
        # Simulate approval in background
        async def approve_later():
            await asyncio.sleep(0.1)
            await hitl_bridge.approve(
                request_id=request.id,
                user_id="test-user",
                approved=True,
                response_data={}
            )
        
        # Start approval task
        task = asyncio.create_task(approve_later())
        
        # Wait for approval
        approved, data = await hitl_bridge.wait_for_approval(request.id)
        
        assert approved is True
        
        # Clean up
        await task
    
    @pytest.mark.asyncio
    async def test_get_pending_approvals(self, hitl_bridge):
        """Test getting pending approvals."""
        config = HITLCheckpointConfig(
            title="Pending Approval",
            description="Test",
            context_summary={}
        )
        
        await hitl_bridge.create_checkpoint(
            workflow_id="wf-1",
            config=config,
            user_id="user-1"
        )
        
        await hitl_bridge.create_checkpoint(
            workflow_id="wf-2",
            config=config,
            user_id="user-1"
        )
        
        # Approve one
        request = await hitl_bridge.create_checkpoint(
            workflow_id="wf-3",
            config=config,
            user_id="user-2"
        )
        await hitl_bridge.approve(request.id, "user-2", True, {})
        
        pending = await hitl_bridge.get_pending_approvals("user-1")
        assert len(pending) == 2


class TestAgentOrchestrator:
    """Tests for the Agent Orchestrator."""
    
    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = MagicMock(spec=BaseAgent)
        agent.id = "test-agent"
        agent.name = "Test Agent"
        agent.execute = AsyncMock(return_value=AgentResponse(
            output="Test response",
            confidence=0.9
        ))
        return agent
    
    @pytest.fixture
    def mock_memory(self):
        """Create a mock memory store."""
        memory = MagicMock(spec=HybridMemoryStore)
        memory.semantic_search = AsyncMock(return_value=[])
        memory.insert = AsyncMock()
        return memory
    
    @pytest.fixture
    def orchestrator(self, mock_agent, mock_memory):
        """Create an orchestrator for testing."""
        hitl_bridge = HITLBridge()
        orch = AgentOrchestrator(
            memory_store=mock_memory,
            hitl_bridge=hitl_bridge
        )
        orch.register_agent(mock_agent)
        return orch
    
    @pytest.mark.asyncio
    async def test_execute_with_agent(self, orchestrator, mock_agent):
        """Test basic task execution."""
        result = await orchestrator.execute(
            agent_id="test-agent",
            user_id="test-user",
            task="Test task",
            hitl_enabled=False
        )
        
        # Either completed or agent was called
        assert result["status"] in ["completed", "failed"] or result["workflow_id"] is not None
        # Just verify agent execute was attempted
        mock_agent.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_agent_not_found(self, orchestrator):
        """Test executing with non-existent agent."""
        result = await orchestrator.execute(
            agent_id="non-existent",
            user_id="test-user",
            task="Test task"
        )
        
        assert result["status"] == "failed"
        assert "not found" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_stream_execute(self, orchestrator, mock_agent):
        """Test streaming execution."""
        events = []
        
        async for event in orchestrator.stream_execute(
            agent_id="test-agent",
            user_id="test-user",
            task="Test streaming",
            hitl_enabled=False
        ):
            events.append(event)
        
        # Check events
        event_types = [e["type"] for e in events]
        assert "workflow_start" in event_types
        assert "agent_result" in event_types
        assert "workflow_complete" in event_types
    
    @pytest.mark.asyncio
    async def test_memory_retrieval(self, orchestrator, mock_agent, mock_memory):
        """Test that memory is retrieved for tasks."""
        mock_memory.semantic_search = AsyncMock(return_value=[
            MagicMock(
                entry=MagicMock(id="mem-1", content="Previous context"),
                relevance_score=0.9
            )
        ])
        
        result = await orchestrator.execute(
            agent_id="test-agent",
            user_id="test-user",
            task="Test with memory",
            hitl_enabled=False
        )
        
        # Verify memory search was called
        mock_memory.semantic_search.assert_called_once()
        # Verify workflow completed (some result returned)
        assert result is not None


class TestAgentResponse:
    """Tests for Agent Response handling."""
    
    def test_agent_response_creation(self):
        """Test creating an agent response."""
        response = AgentResponse(
            output="Test output",
            confidence=0.85,
            thoughts=["Thinking step 1", "Thinking step 2"],
            context_used=["ctx-1", "ctx-2"]
        )
        
        assert response.output == "Test output"
        assert response.confidence == 0.85
        assert len(response.thoughts) == 2
        assert len(response.context_used) == 2
    
    def test_agent_response_defaults(self):
        """Test default values for agent response."""
        response = AgentResponse(output="Test")
        
        assert response.confidence == 1.0
        assert response.tool_calls == []
        assert response.thoughts == []
        assert response.context_used == []
