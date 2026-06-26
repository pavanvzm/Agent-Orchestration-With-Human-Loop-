import { render, screen, fireEvent } from '@testing-library/react';
import { AgentStream } from '../AgentStream';

// Mock lucide-react icons
jest.mock('lucide-react', () => ({
  Brain: () => <span data-testid="brain-icon">Brain</span>,
  Zap: () => <span data-testid="zap-icon">Zap</span>,
  CheckCircle: () => <span data-testid="check-icon">Check</span>,
  AlertCircle: () => <span data-testid="alert-icon">Alert</span>,
  Hand: () => <span data-testid="hand-icon">Hand</span>,
  Loader2: () => <span data-testid="loader-icon">Loader</span>,
  Check: () => <span data-testid="check-icon-sm">Check</span>,
  X: () => <span data-testid="x-icon">X</span>,
}));

describe('AgentStream', () => {
  const mockEvents = [];
  const mockOnApprovalAction = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders connection status', () => {
    render(
      <AgentStream
        events={mockEvents}
        isProcessing={false}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('shows disconnected state', () => {
    render(
      <AgentStream
        events={mockEvents}
        isProcessing={false}
        isConnected={false}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });

  it('shows processing indicator when processing', () => {
    render(
      <AgentStream
        events={mockEvents}
        isProcessing={true}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText(/Processing/)).toBeInTheDocument();
  });

  it('shows empty state when no events', () => {
    render(
      <AgentStream
        events={[]}
        isProcessing={false}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText(/Submit a task/)).toBeInTheDocument();
  });

  it('renders agent thought events', () => {
    const events = [
      {
        type: 'agent_thought' as const,
        content: 'Analyzing the task...',
        timestamp: '2024-01-01T12:00:00Z',
      },
    ];

    render(
      <AgentStream
        events={events}
        isProcessing={false}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText('Analyzing the task...')).toBeInTheDocument();
  });

  it('renders multiple events in order', () => {
    const events = [
      {
        type: 'workflow_start' as const,
        content: 'Starting workflow',
        timestamp: '2024-01-01T12:00:00Z',
      },
      {
        type: 'agent_thought' as const,
        content: 'Processing...',
        timestamp: '2024-01-01T12:00:01Z',
      },
      {
        type: 'agent_result' as const,
        content: 'Done!',
        timestamp: '2024-01-01T12:00:02Z',
      },
    ];

    render(
      <AgentStream
        events={events}
        isProcessing={false}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText('Starting workflow')).toBeInTheDocument();
    expect(screen.getByText('Processing...')).toBeInTheDocument();
    expect(screen.getByText('Done!')).toBeInTheDocument();
  });
});

describe('Approval Actions', () => {
  const mockOnApprovalAction = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders approval required event with actions', () => {
    const events = [
      {
        type: 'approval_required' as const,
        content: 'Approval needed',
        timestamp: '2024-01-01T12:00:00Z',
        metadata: {
          id: 'approval-1',
          title: 'Test Approval',
          description: 'Please approve',
          suggestedActions: [
            { label: 'Approve', value: 'approve' },
            { label: 'Reject', value: 'reject' },
          ],
          expiresAt: '2024-01-02T12:00:00Z',
        },
      },
    ];

    render(
      <AgentStream
        events={events}
        isProcessing={false}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    expect(screen.getByText('Human Approval Required')).toBeInTheDocument();
  });

  it('calls onApprovalAction when approve is clicked', () => {
    const events = [
      {
        type: 'approval_required' as const,
        content: 'Approval needed',
        timestamp: '2024-01-01T12:00:00Z',
        metadata: {
          id: 'approval-1',
          title: 'Test Approval',
          description: 'Please approve',
          suggestedActions: [],
          expiresAt: '2024-01-02T12:00:00Z',
        },
      },
    ];

    render(
      <AgentStream
        events={events}
        isProcessing={false}
        isConnected={true}
        onApprovalAction={mockOnApprovalAction}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /Approve/i }));

    expect(mockOnApprovalAction).toHaveBeenCalledWith('approval-1', true, undefined);
  });
});
