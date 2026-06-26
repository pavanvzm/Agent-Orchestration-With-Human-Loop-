'use client';

import { useState, useCallback } from 'react';
import { AgentEvent, ApprovalRequest } from '@/types';
import { cn } from '@/lib/utils';
import { 
  Brain, 
  Zap, 
  CheckCircle, 
  AlertCircle, 
  Hand, 
  Loader2,
  Check,
  X
} from 'lucide-react';

interface AgentStreamProps {
  events: AgentEvent[];
  isProcessing: boolean;
  isConnected: boolean;
  onApprovalAction?: (requestId: string, approved: boolean, data?: Record<string, unknown>) => void;
  className?: string;
}

export function AgentStream({
  events,
  isProcessing,
  isConnected,
  onApprovalAction,
  className
}: AgentStreamProps) {
  return (
    <div className={cn("space-y-4", className)}>
      {/* Connection Status */}
      <div className="flex items-center gap-2 text-sm">
        <span
          className={cn(
            "h-2 w-2 rounded-full",
            isConnected ? "bg-green-500" : "bg-red-500"
          )}
        />
        <span className="text-muted-foreground">
          {isConnected ? "Connected" : "Disconnected"}
          {isProcessing && " • Processing..."}
        </span>
      </div>

      {/* Event Stream */}
      <div className="space-y-3">
        {events.length === 0 && !isProcessing && (
          <div className="text-center text-muted-foreground py-8">
            <Brain className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p>Submit a task to see the agent's thoughts here</p>
          </div>
        )}
        
        {events.map((event, index) => (
          <EventBubble
            key={`${event.timestamp}-${index}`}
            event={event}
            onApprovalAction={onApprovalAction}
          />
        ))}
        
        {/* Loading indicator */}
        {isProcessing && (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Agent is thinking...</span>
          </div>
        )}
      </div>
    </div>
  );
}

// Event Bubble Component
interface EventBubbleProps {
  event: AgentEvent;
  onApprovalAction?: (requestId: string, approved: boolean, data?: Record<string, unknown>) => void;
}

function EventBubble({ event, onApprovalAction }: EventBubbleProps) {
  const icons = {
    agent_thought: <Brain className="h-4 w-4" />,
    agent_action: <Zap className="h-4 w-4" />,
    agent_result: <CheckCircle className="h-4 w-4" />,
    agent_error: <AlertCircle className="h-4 w-4 text-red-500" />,
    workflow_start: <Brain className="h-4 w-4" />,
    workflow_update: <Zap className="h-4 w-4" />,
    workflow_complete: <CheckCircle className="h-4 w-4 text-green-500" />,
    approval_required: <Hand className="h-4 w-4 text-orange-500" />,
    approval_received: <CheckCircle className="h-4 w-4 text-green-500" />,
    memory_retrieved: <Brain className="h-4 w-4" />,
    done: <CheckCircle className="h-4 w-4" />
  };

  const colors = {
    agent_thought: "border-l-blue-500 bg-blue-50 dark:bg-blue-950/20",
    agent_action: "border-l-yellow-500 bg-yellow-50 dark:bg-yellow-950/20",
    agent_result: "border-l-green-500 bg-green-50 dark:bg-green-950/20",
    agent_error: "border-l-red-500 bg-red-50 dark:bg-red-950/20",
    workflow_start: "border-l-purple-500 bg-purple-50 dark:bg-purple-950/20",
    workflow_update: "border-l-gray-500 bg-gray-50 dark:bg-gray-950/20",
    workflow_complete: "border-l-green-500 bg-green-50 dark:bg-green-950/20",
    approval_required: "border-l-orange-500 bg-orange-50 dark:bg-orange-950/20",
    approval_received: "border-l-green-500 bg-green-50 dark:bg-green-950/20",
    memory_retrieved: "border-l-cyan-500 bg-cyan-50 dark:bg-cyan-950/20",
    done: "border-l-green-500 bg-green-50 dark:bg-green-950/20"
  };

  const event = event;

  return (
    <div className={cn("rounded-lg p-4 border-l-4", colors[event.type] || colors.agent_thought)}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 text-muted-foreground">
          {icons[event.type] || icons.agent_thought}
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-medium text-muted-foreground uppercase">
              {event.type.replace('_', ' ')}
            </span>
            {event.confidence && (
              <span className="text-xs bg-muted px-2 py-0.5 rounded-full">
                {Math.round(event.confidence * 100)}% confidence
              </span>
            )}
          </div>
          
          <p className="text-sm whitespace-pre-wrap">{event.content}</p>
          
          {/* Memory results */}
          {event.type === 'memory_retrieved' && event.data && (
            <div className="mt-2 space-y-1">
              <span className="text-xs text-muted-foreground">
                Retrieved {event.data.count || 0} context entries
              </span>
            </div>
          )}
          
          {/* Approval Required Actions */}
          {event.type === 'approval_required' && event.metadata && onApprovalAction && (
            <ApprovalActions
              metadata={event.metadata as unknown as ApprovalRequest}
              onAction={(approved, data) => {
                if (event.metadata) {
                  onApprovalAction(
                    (event.metadata as ApprovalRequest).id || '',
                    approved,
                    data
                  );
                }
              }}
            />
          )}
        </div>
        
        {event.timestamp && (
          <span className="text-xs text-muted-foreground">
            {new Date(event.timestamp).toLocaleTimeString()}
          </span>
        )}
      </div>
    </div>
  );
}

// Approval Actions Component
interface ApprovalActionsProps {
  metadata: ApprovalRequest;
  onAction: (approved: boolean, data?: Record<string, unknown>) => void;
}

function ApprovalActions({ metadata, onAction }: ApprovalActionsProps) {
  return (
    <div className="mt-4 space-y-3 border-t pt-3">
      <p className="text-sm font-medium">Human Approval Required</p>
      
      <div className="flex gap-2">
        <button
          onClick={() => onAction(true)}
          className="flex items-center gap-1.5 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Check className="h-4 w-4" />
          Approve
        </button>
        <button
          onClick={() => onAction(false)}
          className="flex items-center gap-1.5 px-4 py-2 border border-red-300 hover:bg-red-50 text-red-600 text-sm font-medium rounded-lg transition-colors"
        >
          <X className="h-4 w-4" />
          Reject
        </button>
      </div>
      
      {metadata.suggestedActions && metadata.suggestedActions.length > 0 && (
        <div className="text-sm">
          <span className="text-muted-foreground">Suggested actions: </span>
          <div className="flex gap-2 mt-1">
            {metadata.suggestedActions.map((action) => (
              <button
                key={action.value}
                onClick={() => onAction(true, { action: action.value })}
                className="text-blue-600 hover:text-blue-700 hover:underline"
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      )}
      
      <div className="text-xs text-muted-foreground">
        Expires: {new Date(metadata.expiresAt).toLocaleString()}
      </div>
    </div>
  );
}

// Memory Context Display
interface MemoryContextProps {
  memories: Array<{ content: string; relevance: number }>;
}

export function MemoryContext({ memories }: MemoryContextProps) {
  if (memories.length === 0) return null;
  
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium text-muted-foreground uppercase">
        Retrieved Context
      </div>
      <div className="space-y-2">
        {memories.map((memory, index) => (
          <div
            key={index}
            className="text-sm p-2 bg-muted/50 rounded border"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-muted-foreground">
                Relevance: {Math.round(memory.relevance * 100)}%
              </span>
            </div>
            <p className="text-sm">{memory.content}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
