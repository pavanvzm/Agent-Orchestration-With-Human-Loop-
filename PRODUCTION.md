# Multi-Agent Orchestration Platform - Production Deployment Guide

## Table of Contents
1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Environment Setup](#environment-setup)
4. [Deployment Options](#deployment-options)
5. [Configuration](#configuration)
6. [API Reference](#api-reference)
7. [Monitoring & Observability](#monitoring--observability)
8. [Security](#security)
9. [Troubleshooting](#troubleshooting)

---

## Overview

The Multi-Agent Orchestration Platform is an enterprise-grade system for orchestrating multiple AI agents with Human-in-the-Loop (HITL) capabilities. It provides:

- **Multi-Agent Coordination**: LangGraph-based workflow orchestration
- **Persistent Memory**: Hybrid vector + relational storage for semantic search
- **Real-Time Communication**: WebSocket/SSE for live agent streaming
- **HITL Checkpoints**: Human approval for sensitive operations

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 2 cores | 4+ cores |
| RAM | 4 GB | 8+ GB |
| Disk | 20 GB SSD | 50+ GB SSD |
| Python | 3.11+ | 3.12 |
| Node.js | 18+ | 20+ |

### Required Services

- **PostgreSQL 15+** (for structured data and metadata)
- **Redis 7+** (for caching and real-time features)
- **ChromaDB** or **Pinecone** (for vector embeddings)
- **OpenAI API Key** or **Anthropic API Key** (for LLM)

---

## Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/multi-agent-platform.git
cd multi-agent-platform
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -e ".[dev]"

# Install additional production dependencies
pip install gunicorn uvloop
```

### 3. Environment Variables

Create a `.env` file based on `.env.example`:

```bash
cp .env.example .env
```

Edit the `.env` file with your configuration:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/agent_platform
REDIS_URL=redis://localhost:6379/0

# Vector Database
VECTOR_DB_TYPE=chroma
CHROMA_DB_PATH=/var/lib/chroma

# LLM Provider (choose one)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-key
# ANTHROPIC_API_KEY=sk-ant-your-anthropic-key

# Security (generate a secure key)
SECRET_KEY=your-super-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# HITL Configuration
HITL_DEFAULT_TIMEOUT_HOURS=24
HITL_MAX_TIMEOUT_HOURS=168
```

### 4. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create environment file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

---

## Deployment Options

### Option 1: Docker Compose (Recommended for Development/Staging)

```bash
# From project root
docker-compose -f infrastructure/docker/docker-compose.yml up -d

# View logs
docker-compose -f infrastructure/docker/docker-compose.yml logs -f

# Stop services
docker-compose -f infrastructure/docker/docker-compose.yml down
```

### Option 2: Kubernetes (Production)

```bash
# Apply Kubernetes manifests
kubectl apply -f infrastructure/k8s/

# Check deployment status
kubectl get pods -n agent-platform

# View logs
kubectl logs -n agent-platform -l app=api
```

### Option 3: Manual Deployment (Bare Metal)

#### Backend (Production)

```bash
cd backend

# Set environment
export DATABASE_URL=postgresql://...
export REDIS_URL=redis://...
export SECRET_KEY=your-secret-key

# Run with gunicorn (production)
gunicorn api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile /var/log/agent-platform/access.log \
  --error-logfile /var/log/agent-platform/error.log \
  --log-level info
```

#### Frontend (Production)

```bash
cd frontend

# Build for production
npm run build

# Start production server
npm run start
```

---

## Configuration

### Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | - | PostgreSQL connection string |
| `REDIS_URL` | No | redis://localhost:6379/0 | Redis connection string |
| `VECTOR_DB_TYPE` | No | chroma | Vector DB type (chroma, pinecone, milvus) |
| `CHROMA_DB_PATH` | No | ./data/chroma | ChromaDB data path |
| `LLM_PROVIDER` | Yes | openai | LLM provider (openai, anthropic) |
| `OPENAI_API_KEY` | Conditional | - | OpenAI API key |
| `ANTHROPIC_API_KEY` | Conditional | - | Anthropic API key |
| `LLM_MODEL` | No | gpt-4-turbo-preview | Default LLM model |
| `SECRET_KEY` | Yes | - | JWT signing key |
| `HITL_DEFAULT_TIMEOUT_HOURS` | No | 24 | Default HITL approval timeout |
| `LOG_LEVEL` | No | INFO | Logging level |

### Database Setup

```bash
# Create database
psql -U postgres -c "CREATE DATABASE agent_platform;"

# Run migrations (if using Alembic)
alembic upgrade head

# Or create tables manually
# Tables are auto-created on first startup
```

---

## API Reference

### Base URL

```
http://localhost:8000
```

### Authentication

Currently uses simple user_id query parameter. For production, implement JWT authentication.

### Endpoints

#### Health Check

```bash
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "services": {
    "memory_store": true,
    "orchestrator": true,
    "hitl_bridge": true
  }
}
```

#### List Agents

```bash
GET /api/agents
```

#### Execute Task

```bash
POST /api/execute
Content-Type: application/json

{
  "agent_id": "reasoning-agent",
  "task": "Explain quantum computing",
  "context": {}
}
```

**Response:**
```json
{
  "workflow_id": "uuid",
  "status": "completed",
  "message": "Task submitted successfully"
}
```

#### Stream Execution

```bash
POST /api/execute/stream
Content-Type: application/json

{
  "agent_id": "reasoning-agent",
  "task": "Your task here"
}
```

Returns Server-Sent Events (SSE) stream.

#### List Pending Approvals

```bash
GET /api/approvals?user_id=your-user-id
```

#### Submit Approval

```bash
POST /api/approvals
Content-Type: application/json

{
  "request_id": "approval-uuid",
  "approved": true,
  "user_id": "your-user-id",
  "response_data": {}
}
```

#### Search Memory

```bash
GET /api/memory/search?query=your-query&top_k=5&user_id=your-user-id
```

#### Add Memory

```bash
POST /api/memory?content=your-content&user_id=your-user-id&source=user_input&memory_type=context
```

---

## Monitoring & Observability

### Prometheus Metrics

Metrics are exposed at `/metrics` endpoint when prometheus-client is installed.

**Key Metrics:**

| Metric | Type | Description |
|--------|------|-------------|
| `agent_execution_duration_seconds` | Histogram | Agent task execution time |
| `agent_token_usage_total` | Counter | Token usage by agent |
| `hitl_approval_duration_seconds` | Histogram | Time to approve/reject |
| `hitl_pending_count` | Gauge | Current pending approvals |
| `api_request_duration_seconds` | Histogram | HTTP request latency |

### Grafana Dashboards

Import dashboards from `infrastructure/grafana/dashboards/`.

### Logging

Logs are output in JSON format for production:

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "message": "Agent task completed",
  "workflow_id": "uuid",
  "agent_id": "reasoning-agent"
}
```

### Health Checks

```bash
# Liveness probe
GET /health

# Readiness probe
GET /health
# Returns 503 if dependencies unavailable
```

---

## Security

### Authentication

1. **JWT Tokens** (recommended for production):
   - Implement JWT token generation in `/api/auth`
   - Use `python-jose` for token handling
   - Set appropriate expiration times

2. **API Keys** (for service-to-service):
   - Generate secure API keys for backend services
   - Store in secure vault (AWS Secrets Manager, HashiCorp Vault)

### Data Protection

- **Encryption at Rest**: Enable PostgreSQL encryption
- **Encryption in Transit**: Use TLS 1.3 for all connections
- **PII Handling**: Implement data masking for sensitive fields
- **Memory Isolation**: User-specific memory namespaces

### HITL Security

- Approval requires authenticated user
- Multi-approval for critical operations
- Time-limited approval tokens (24hr default)
- Audit logging of all approval decisions

### Network Security

- Use private networking in cloud deployments
- Implement rate limiting at API Gateway
- Use WAF (Web Application Firewall) for public endpoints

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Failed

```
Error: Cannot connect to database
```

**Solution:**
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Verify connection string
psql $DATABASE_URL

# Check firewall rules
sudo ufw allow 5432/tcp
```

#### 2. Redis Connection Failed

```
Error: Cannot connect to Redis
```

**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Verify connection
redis-cli -u $REDIS_URL ping
```

#### 3. LLM API Key Invalid

```
Error: Invalid API key
```

**Solution:**
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

#### 4. Out of Memory

```
Error: Cannot allocate memory
```

**Solution:**
```bash
# Check available memory
free -h

# Increase swap
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
```

#### 5. Worker Crashes

```bash
# Check logs
tail -f /var/log/agent-platform/error.log

# Restart workers
pkill -HUP gunicorn

# Check system limits
ulimit -a
```

### Debug Mode

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
```

Or in `.env`:
```
LOG_LEVEL=DEBUG
```

### Performance Tuning

1. **Database Connection Pooling:**
   ```python
   # In database URL
   ?pool_size=20&max_overflow=40
   ```

2. **Redis Caching:**
   ```python
   # Increase maxmemory for production
   redis-cli config set maxmemory 2gb
   ```

3. **Gunicorn Workers:**
   ```bash
   # Formula: 2 * CPU cores + 1
   gunicorn --workers 9
   ```

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/multi-agent-platform/issues
- Documentation: https://docs.agent-platform.dev
- Email: support@agent-platform.dev

---

## License

MIT License - See [LICENSE](LICENSE) for details.
