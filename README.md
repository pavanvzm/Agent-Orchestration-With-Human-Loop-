# Multi-Agent Orchestration Platform

Enterprise-grade multi-agent system with Human-in-the-Loop (HITL) capabilities, persistent memory, and cross-platform support.

## Overview

This platform enables orchestration of multiple AI agents with:
- **Multi-Agent Coordination**: LangGraph-based workflow orchestration
- **Human-in-the-Loop**: Checkpoint approval system for sensitive operations
- **Persistent Memory**: Hybrid vector + relational storage for semantic search
- **Real-Time Communication**: WebSocket/SSE for live agent streaming
- **Cross-Platform**: Web (React/Next.js), iOS, Android support

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client Layer                                 │
├─────────────────────────────────────────────────────────────────────┤
│  Web (Next.js)        │     iOS (SwiftUI)      │   Android (Kotlin) │
└───────────────────────┴───────────────────────┴─────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API Gateway Layer                               │
│              (FastAPI + WebSocket + SSE)                             │
└─────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────────┐   ┌───────────────────┐   ┌───────────────────┐
│ Orchestrator      │   │ Memory System     │   │ HITL Service      │
│ (LangGraph)       │   │ (Chroma + PG)     │   │ (Checkpoint Mgr)  │
└───────────────────┘   └───────────────────┘   └───────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker & Docker Compose

### 1. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your API keys

# Run the server
uvicorn api.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

### 3. Docker Compose (Full Stack)

```bash
# From project root
docker-compose -f infrastructure/docker/docker-compose.yml up -d

# With custom API keys
OPENAI_API_KEY=your-key ANTHROPIC_API_KEY=your-key docker-compose up -d
```

## Project Structure

```
.
├── backend/                    # Python/FastAPI backend
│   ├── agents/                 # Agent implementations
│   │   ├── base.py            # Base agent class
│   │   └── orchestrator.py    # LangGraph orchestrator + HITL
│   ├── memory/                 # Memory subsystem
│   │   └── store.py           # Hybrid vector + SQL store
│   ├── models/                 # Pydantic schemas
│   │   └── schemas.py         # Domain models
│   ├── workflows/              # Workflow definitions
│   │   └── definitions.py    # Sample workflows
│   ├── api/                    # FastAPI routes
│   │   └── main.py            # Application entry point
│   └── tests/                  # Test suite
│       ├── unit/              # Unit tests
│       ├── integration/       # Integration tests
│       └── ai/                # AI evaluation tests
│
├── frontend/                   # Next.js frontend
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── hooks/            # Custom React hooks
│   │   ├── types/            # TypeScript types
│   │   └── lib/              # Utilities
│   └── tests/                 # Jest tests
│
└── infrastructure/             # Infrastructure as code
    ├── docker/               # Docker configurations
    └── ci/                   # CI/CD pipelines
```

## API Reference

### Execute Task

```bash
POST /api/execute
{
  "agent_id": "reasoning-agent",
  "task": "Explain quantum computing",
  "context": {}
}
```

### Stream Execution

```bash
POST /api/execute/stream
# Returns SSE stream of agent events
```

### Approvals

```bash
# List pending approvals
GET /api/approvals?user_id=xxx

# Submit approval
POST /api/approvals
{
  "request_id": "xxx",
  "approved": true,
  "user_id": "xxx",
  "response_data": {}
}
```

### Memory

```bash
# Search memory
GET /api/memory/search?query=python&top_k=5

# Add memory
POST /api/memory?content=...&user_id=xxx
```

## Key Features

### 1. Multi-Agent Orchestration

```python
from agents.orchestrator import AgentOrchestrator

orchestrator = AgentOrchestrator(
    memory_store=memory_store,
    hitl_bridge=hitl_bridge
)

# Register agents
orchestrator.register_agent(my_agent)

# Execute task
result = await orchestrator.execute(
    agent_id="reasoning-agent",
    user_id="user-123",
    task="Analyze this data",
    hitl_enabled=True
)
```

### 2. Human-in-the-Loop Checkpoints

```python
from agents.orchestrator import HITLCheckpointConfig, ApprovalAction

config = HITLCheckpointConfig(
    title="Confirm Action",
    description="Approve data modification",
    context_summary={"action": "delete", "count": 100},
    suggested_actions=[
        ApprovalAction(label="Proceed", value="approve"),
        ApprovalAction(label="Cancel", value="reject")
    ],
    timeout_hours=24
)

request = await hitl_bridge.create_checkpoint(
    workflow_id="wf-123",
    config=config,
    user_id="approver@example.com"
)
```

### 3. Memory-Enhanced Agents

```python
# Automatic context retrieval
results = await memory_store.semantic_search(
    query="customer preferences",
    user_id="user-123",
    top_k=5,
    filters={"importance": ["high", "critical"]}
)
```

## Testing

### Backend Tests

```bash
cd backend

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agents --cov=memory --cov-report=html

# Run AI evaluation tests
pytest tests/ai/ -v
```

### Frontend Tests

```bash
cd frontend

# Run tests
npm test

# Run with coverage
npm run test:ci
```

## CI/CD Pipeline

The project includes a GitHub Actions pipeline that:

1. **Quality Checks**: Linting, type checking
2. **Unit Tests**: Backend and frontend
3. **Integration Tests**: API and database
4. **AI Evaluation**: LLM-as-Judge testing
5. **Security Scanning**: Trivy vulnerability scan
6. **Container Build**: Docker images
7. **Deployment**: Staging and Production

See `.github/workflows/ci-cd.yml` for configuration.

## Environment Variables

### Backend (.env)

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0
VECTOR_DB_TYPE=chroma
CHROMA_DB_PATH=./data/chroma

# LLM Provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=gpt-4-turbo-preview

# Security
SECRET_KEY=your-secret-key
ALGORITHM=HS256

# HITL
HITL_DEFAULT_TIMEOUT_HOURS=24
```

## Roadmap

- [ ] Production-ready authentication (OAuth 2.0/OIDC)
- [ ] Advanced workflow designer UI
- [ ] Native mobile SDKs (iOS/Android)
- [ ] Enterprise SSO integration
- [ ] Advanced analytics dashboard
- [ ] Multi-tenancy support
- [ ] Custom agent marketplace

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Built with [LangGraph](https://github.com/langchain-ai/langgraph)
- Frontend powered by [Next.js](https://nextjs.org/)
- State management by [Zustand](https://github.com/pmndrs/zustand)
