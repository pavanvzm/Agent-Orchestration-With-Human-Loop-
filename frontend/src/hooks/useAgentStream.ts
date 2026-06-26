import { useEffect, useRef, useState, useCallback } from 'react';
import { AgentEvent, ApprovalRequest } from '@/types';

interface UseAgentStreamOptions {
  onApprovalRequired?: (request: ApprovalRequest) => void;
  onComplete?: (result: unknown) => void;
  onError?: (error: Error) => void;
  onEvent?: (event: AgentEvent) => void;
}

interface UseAgentStreamReturn {
  isConnected: boolean;
  isProcessing: boolean;
  events: AgentEvent[];
  error: string | null;
  connect: () => void;
  disconnect: () => void;
  submitApproval: (requestId: string, approved: boolean, data?: Record<string, unknown>) => Promise<void>;
  reset: () => void;
}

export function useAgentStream(options: UseAgentStreamOptions = {}): UseAgentStreamReturn {
  const { onApprovalRequired, onComplete, onError, onEvent } = options;
  
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    // Build WebSocket URL
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/stream`;
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as AgentEvent;
          
          setEvents(prev => [...prev, data]);
          onEvent?.(data);
          
          switch (data.type) {
            case 'workflow_start':
              setIsProcessing(true);
              break;
            
            case 'workflow_complete':
            case 'done':
              setIsProcessing(false);
              onComplete?.(data.data);
              break;
            
            case 'agent_error':
            case 'error':
              setIsProcessing(false);
              setError(data.content || 'Unknown error');
              onError?.(new Error(data.content || 'Unknown error'));
              break;
            
            case 'approval_required':
              const approvalData = data.metadata as unknown as ApprovalRequest;
              if (approvalData) {
                onApprovalRequired?.(approvalData);
              }
              break;
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };
      
      ws.onclose = () => {
        setIsConnected(false);
        
        // Exponential backoff reconnection
        if (reconnectAttemptsRef.current < 5) {
          const delay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 30000);
          reconnectAttemptsRef.current++;
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        }
      };
      
      ws.onerror = () => {
        setError('WebSocket connection error');
        setIsConnected(false);
      };
      
    } catch (e) {
      setError('Failed to connect');
    }
  }, [onApprovalRequired, onComplete, onError, onEvent]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    
    setIsConnected(false);
    setIsProcessing(false);
  }, []);

  const submitApproval = useCallback(async (
    requestId: string,
    approved: boolean,
    data?: Record<string, unknown>
  ) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      // Fallback to HTTP API
      const response = await fetch('/api/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          approved,
          user_id: 'current-user',
          response_data: data
        })
      });
      
      if (!response.ok) {
        throw new Error('Failed to submit approval');
      }
      return;
    }
    
    wsRef.current.send(JSON.stringify({
      type: 'approval_response',
      request_id: requestId,
      approved,
      user_id: 'current-user',
      response_data: data
    }));
  }, []);

  const reset = useCallback(() => {
    setEvents([]);
    setError(null);
    setIsProcessing(false);
  }, []);

  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    isProcessing,
    events,
    error,
    connect,
    disconnect,
    submitApproval,
    reset
  };
}

// Hook for SSE-based streaming
export function useAgentStreamSSE(
  agentId: string,
  task: string,
  userId: string = 'default-user'
) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);
  
  const eventSourceRef = useRef<EventSource | null>(null);

  const execute = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setEvents([]);
    
    try {
      const response = await fetch('/api/execute/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, task }),
      });
      
      if (!response.ok) {
        throw new Error('Failed to start execution');
      }
      
      // Handle SSE stream
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      if (reader) {
        let buffer = '';
        
        while (true) {
          const { done, value } = await reader.read();
          
          if (done) break;
          
          buffer += decoder.decode(value, { stream: true });
          
          // Process complete lines
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const event = JSON.parse(line.slice(6)) as AgentEvent;
                setEvents(prev => [...prev, event]);
                
                if (event.type === 'workflow_complete') {
                  setResult(event.data);
                }
                
                if (event.type === 'agent_error' || event.type === 'error') {
                  setError(event.content || 'Execution failed');
                }
              } catch (e) {
                console.error('Failed to parse SSE event:', e);
              }
            }
          }
        }
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Execution failed');
    } finally {
      setIsLoading(false);
    }
  }, [agentId, task, userId]);

  const reset = useCallback(() => {
    setEvents([]);
    setError(null);
    setResult(null);
  }, []);

  return {
    events,
    isLoading,
    error,
    result,
    execute,
    reset
  };
}

// Hook for managing approval state
export function useApprovals() {
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchApprovals = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/approvals');
      
      if (!response.ok) {
        throw new Error('Failed to fetch approvals');
      }
      
      const data = await response.json();
      setApprovals(data.approvals || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch approvals');
    } finally {
      setIsLoading(false);
    }
  }, []);

  const submitApproval = useCallback(async (
    requestId: string,
    approved: boolean,
    responseData?: Record<string, unknown>
  ) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await fetch('/api/approvals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          approved,
          user_id: 'current-user',
          response_data: responseData
        })
      });
      
      if (!response.ok) {
        throw new Error('Failed to submit approval');
      }
      
      // Refresh approvals list
      await fetchApprovals();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to submit approval');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [fetchApprovals]);

  useEffect(() => {
    fetchApprovals();
    
    // Poll for new approvals
    const interval = setInterval(fetchApprovals, 10000);
    return () => clearInterval(interval);
  }, [fetchApprovals]);

  return {
    approvals,
    isLoading,
    error,
    fetchApprovals,
    submitApproval
  };
}
