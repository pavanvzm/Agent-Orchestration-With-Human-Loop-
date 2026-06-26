// Domain types for the Multi-Agent Platform
// These types should be auto-generated from the backend schema

export interface Agent {
  id: string;
  name: string;
  description: string;
  model: string;
  capabilities: AgentCapability[];
  metadata?: Record<string, unknown>;
  createdAt?: string;
  updatedAt?: string;
}

export interface AgentCapability {
  type: string;
  description: string;
  parameters?: Record<string, unknown>;
}

export interface WorkflowStatus {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'paused' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled';
  currentStep: string;
  createdAt: string;
  updatedAt?: string;
  completedAt?: string;
  error?: string;
}

export interface MemoryEntry {
  id: string;
  content: string;
  metadata: MemoryMetadata;
  relevanceScore?: number;
  createdAt: string;
  accessedAt?: string;
  expiresAt?: string;
}

export interface MemoryMetadata {
  source: 'conversation' | 'document' | 'agent_generated' | 'user_input';
  type: 'fact' | 'preference' | 'context' | 'history';
  tags: string[];
  importance: 'low' | 'medium' | 'high' | 'critical';
  conversationId?: string;
  userId?: string;
}

export interface ApprovalRequest {
  id: string;
  workflowId: string;
  checkpointId: string;
  title: string;
  description: string;
  context: Record<string, unknown>;
  suggestedActions?: ApprovalAction[];
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'delegated';
  requestedBy: string;
  requestedAt: string;
  expiresAt: string;
  respondedBy?: string;
  respondedAt?: string;
  responseData?: Record<string, unknown>;
}

export interface ApprovalAction {
  label: string;
  value: string;
  description?: string;
}

// Agent Events
export type AgentEventType =
  | 'agent_thought'
  | 'agent_action'
  | 'agent_result'
  | 'agent_error'
  | 'workflow_start'
  | 'workflow_update'
  | 'workflow_complete'
  | 'approval_required'
  | 'approval_received'
  | 'memory_retrieved'
  | 'done';

export interface AgentEvent {
  type: AgentEventType;
  workflow_id?: string;
  agent_id?: string;
  content?: string;
  timestamp?: string;
  metadata?: Record<string, unknown>;
  confidence?: number;
  data?: Record<string, unknown>;
}

export interface ExecutionResult {
  workflowId: string;
  status: string;
  result?: Record<string, unknown>;
  error?: string;
}

// API Responses
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
}
