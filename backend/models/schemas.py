"""
Domain models and schemas for the Multi-Agent Platform.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


# ─────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────
class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MemorySource(str, Enum):
    CONVERSATION = "conversation"
    DOCUMENT = "document"
    AGENT_GENERATED = "agent_generated"
    USER_INPUT = "user_input"


class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    CONTEXT = "context"
    HISTORY = "history"


class Importance(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    DELEGATED = "delegated"


class EventType(str, Enum):
    AGENT_THOUGHT = "agent_thought"
    AGENT_ACTION = "agent_action"
    AGENT_RESULT = "agent_result"
    AGENT_ERROR = "agent_error"
    WORKFLOW_START = "workflow_start"
    WORKFLOW_UPDATE = "workflow_update"
    WORKFLOW_COMPLETE = "workflow_complete"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RECEIVED = "approval_received"


# ─────────────────────────────────────────────────────────
# Agent Models
# ─────────────────────────────────────────────────────────
class AgentCapability(BaseModel):
    type: str = Field(..., description="Capability type: reasoning, tool_use, etc.")
    description: str = Field(..., description="Human-readable description")
    parameters: Optional[dict[str, Any]] = Field(default=None, description="JSON schema for parameters")


class Agent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    model: str = Field(default="gpt-4-turbo-preview")
    capabilities: list[AgentCapability] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────
# Memory Models
# ─────────────────────────────────────────────────────────
class MemoryMetadata(BaseModel):
    source: MemorySource = Field(..., description="Origin of the memory")
    type: MemoryType = Field(..., description="Type of memory content")
    tags: list[str] = Field(default_factory=list)
    importance: Importance = Field(default=Importance.MEDIUM)
    conversation_id: Optional[str] = Field(default=None)
    user_id: Optional[str] = Field(default=None)
    
    model_config = ConfigDict(from_attributes=True)


class MemoryEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: Optional[str] = Field(default=None)
    user_id: Optional[str] = Field(default=None)
    content: str = Field(..., description="Memory content")
    embedding: Optional[list[float]] = Field(default=None, description="Vector representation")
    metadata: MemoryMetadata = Field(default_factory=MemoryMetadata)
    relevance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    accessed_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(default=None)
    
    model_config = ConfigDict(from_attributes=True)
    
    def mark_accessed(self) -> None:
        self.accessed_at = datetime.utcnow()


class MemorySearchResult(BaseModel):
    entry: MemoryEntry
    relevance_score: float
    distance: Optional[float] = None
    rank: int = 0


# ─────────────────────────────────────────────────────────
# Workflow Models
# ─────────────────────────────────────────────────────────
class WorkflowStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    agent_id: Optional[str] = None
    tool: Optional[str] = None
    config: dict[str, Any] = Field(default_factory=dict)
    next_step: Optional[str] = None
    conditions: dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    version: str = Field(default="1.0.0")
    steps: list[WorkflowStep] = Field(default_factory=list)
    entry_point: str = Field(default="start")
    
    model_config = ConfigDict(from_attributes=True)


class Workflow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., description="Workflow name")
    definition: WorkflowDefinition = Field(..., description="Workflow definition")
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)
    current_step: str = Field(default="start")
    context: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(..., description="User ID who created the workflow")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(default=None)
    error: Optional[str] = Field(default=None)
    
    model_config = ConfigDict(from_attributes=True)


class WorkflowExecution(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)
    current_state: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = Field(default=None)
    result: Optional[dict[str, Any]] = Field(default=None)
    
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────
# HITL Models
# ─────────────────────────────────────────────────────────
class ApprovalAction(BaseModel):
    label: str = Field(..., description="Display label for the action")
    value: str = Field(..., description="Value to return if action is selected")
    description: Optional[str] = Field(default=None)


class HITLApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    checkpoint_id: str = Field(description="Checkpoint identifier")
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    context: dict[str, Any] = Field(default_factory=dict, description="Summary data for review")
    suggested_actions: list[ApprovalAction] = Field(default_factory=list)
    status: ApprovalStatus = Field(default=ApprovalStatus.PENDING)
    requested_by: str = Field(default="system", description="Agent/system ID that requested approval")
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    responded_by: Optional[str] = Field(default=None, description="User ID who responded")
    responded_at: Optional[datetime] = Field(default=None)
    response_data: Optional[dict[str, Any]] = Field(default=None)
    
    model_config = ConfigDict(from_attributes=True)
    
    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at
    
    @property
    def is_pending(self) -> bool:
        return self.status == ApprovalStatus.PENDING and not self.is_expired


# ─────────────────────────────────────────────────────────
# User Models
# ─────────────────────────────────────────────────────────
class UserPreferences(BaseModel):
    theme: str = Field(default="system", pattern="^(light|dark|system)$")
    language: str = Field(default="en")
    timezone: str = Field(default="UTC")
    accessibility_options: dict[str, bool] = Field(default_factory=dict)


class NotificationSettings(BaseModel):
    email: bool = Field(default=True)
    push: bool = Field(default=True)
    in_app: bool = Field(default=True)
    digest_frequency: str = Field(default="realtime", pattern="^(realtime|hourly|daily)$")
    quiet_hours_start: Optional[str] = Field(default=None)
    quiet_hours_end: Optional[str] = Field(default=None)


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str = Field(..., description="User email address")
    name: str = Field(..., min_length=1, max_length=100)
    hashed_password: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    notification_settings: NotificationSettings = Field(default_factory=NotificationSettings)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────
# Event Models
# ─────────────────────────────────────────────────────────
class AgentEvent(BaseModel):
    type: EventType = Field(..., description="Event type")
    workflow_id: str = Field(..., description="Associated workflow ID")
    agent_id: Optional[str] = Field(default=None)
    content: str = Field(..., description="Event content/message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    model_config = ConfigDict(from_attributes=True)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "workflow_id": self.workflow_id,
            "agent_id": self.agent_id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


# ─────────────────────────────────────────────────────────
# API Request/Response Models
# ─────────────────────────────────────────────────────────
class ExecuteTaskRequest(BaseModel):
    agent_id: str = Field(..., description="Agent to use for execution")
    task: str = Field(..., min_length=1, description="Task description")
    context: Optional[dict[str, Any]] = Field(default=None, description="Additional context")
    config: Optional[dict[str, Any]] = Field(default=None, description="Execution config")


class ExecuteTaskResponse(BaseModel):
    workflow_id: str
    status: WorkflowStatus
    message: str = ""


class ApprovalRequest(BaseModel):
    request_id: str = Field(..., description="Approval request ID")
    approved: bool = Field(..., description="Whether to approve")
    user_id: str = Field(..., description="User making the decision")
    response_data: Optional[dict[str, Any]] = Field(default=None)


class ApprovalResponse(BaseModel):
    success: bool
    message: str
    workflow_id: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    services: dict[str, bool]
