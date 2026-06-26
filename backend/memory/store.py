"""
Hybrid Memory Store - Combines Vector DB for semantic search 
with relational DB for structured metadata.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

import chromadb
import numpy as np
from chromadb.config import Settings as ChromaSettings
from sqlalchemy import Column, String, DateTime, Text, Float, JSON, Index
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from models.schemas import MemoryEntry, MemoryMetadata, MemorySearchResult, MemorySource, MemoryType, Importance


Base = declarative_base()


# ─────────────────────────────────────────────────────────
# SQLAlchemy Models
# ─────────────────────────────────────────────────────────
class MemoryEntryModel(Base):
    __tablename__ = "memory_entries"
    
    id = Column(String(36), primary_key=True)
    agent_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    content = Column(Text, nullable=False)
    
    # Metadata stored as JSON
    source = Column(String(50), nullable=False)
    memory_type = Column(String(50), nullable=False)
    tags = Column(JSON, default=list)
    importance = Column(String(20), default="medium")
    conversation_id = Column(String(36), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    accessed_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True, index=True)
    
    __table_args__ = (
        Index("idx_memory_user_created", "user_id", "created_at"),
        Index("idx_memory_agent_created", "agent_id", "created_at"),
    )


# ─────────────────────────────────────────────────────────
# Vector Embedding Service
# ─────────────────────────────────────────────────────────
class EmbeddingService:
    """Service for generating text embeddings."""
    
    def __init__(self, model: str = "text-embedding-ada-002"):
        self.model = model
        self._client = None
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        # Lazy import to avoid hard dependency
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            # Fallback to simple hash-based pseudo-embeddings for development
            return self._pseudo_embed(texts)
        
        if self._client is None:
            self._client = OpenAIEmbeddings(model=self.model)
        
        embeddings = await asyncio.to_thread(self._client.embed_documents, texts)
        return embeddings
    
    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query."""
        embeddings = await self.embed([text])
        return embeddings[0]
    
    def _pseudo_embed(self, texts: list[str]) -> list[list[float]]:
        """Generate pseudo-embeddings using hash for development."""
        import hashlib
        result = []
        for text in texts:
            # Create a deterministic pseudo-embedding from text hash
            hash_val = int(hashlib.sha256(text.encode()).hexdigest(), 16)
            # Generate a 384-dimensional pseudo-embedding
            rng = np.random.RandomState(hash_val % (2**32))
            embedding = rng.randn(384).tolist()
            # Normalize
            norm = np.linalg.norm(embedding)
            embedding = [x / norm for x in embedding]
            result.append(embedding)
        return result


# ─────────────────────────────────────────────────────────
# Hybrid Memory Store
# ─────────────────────────────────────────────────────────
class HybridMemoryStore:
    """
    Hybrid memory system combining:
    - ChromaDB for semantic vector search
    - PostgreSQL for structured metadata and full-text search
    - Redis for caching hot entries
    """
    
    def __init__(
        self,
        database_url: str,
        vector_db_path: str = "./data/chroma",
        redis_url: Optional[str] = None,
        embedding_service: Optional[EmbeddingService] = None
    ):
        self.database_url = database_url
        self.vector_db_path = vector_db_path
        self.redis_url = redis_url
        
        # Initialize embedding service
        self.embedding_service = embedding_service or EmbeddingService()
        
        # Initialize connections (created on first use)
        self._engine = None
        self._session_factory = None
        self._chroma_client = None
        self._redis_client = None
        self._vector_collection = None
    
    async def initialize(self) -> None:
        """Initialize all connections."""
        # Database
        self._engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_size=10,
            max_overflow=20
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        # Create tables
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Vector DB
        self._chroma_client = chromadb.Client(ChromaSettings(
            persist_directory=self.vector_db_path,
            anonymized_telemetry=False
        ))
        self._vector_collection = self._chroma_client.get_or_create_collection(
            name="memory_embeddings",
            metadata={"hnsw:space": "cosine"}
        )
        
        # Redis (optional)
        if self.redis_url:
            import redis.asyncio as redis
            self._redis_client = redis.from_url(self.redis_url, decode_responses=True)
    
    async def close(self) -> None:
        """Close all connections."""
        if self._engine:
            await self._engine.dispose()
        if self._redis_client:
            await self._redis_client.close()
    
    # ─────────────────────────────────────────────────────
    # Core Operations
    # ─────────────────────────────────────────────────────
    
    async def insert(
        self,
        content: str,
        metadata: MemoryMetadata,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        embedding: Optional[list[float]] = None,
        expires_at: Optional[datetime] = None
    ) -> MemoryEntry:
        """Insert a new memory entry."""
        entry_id = str(uuid4())
        
        # Generate embedding if not provided
        if embedding is None:
            embedding = await self.embedding_service.embed_query(content)
        
        # Store in PostgreSQL
        async with self._session_factory() as session:
            model = MemoryEntryModel(
                id=entry_id,
                user_id=user_id,
                agent_id=agent_id,
                content=content,
                source=metadata.source.value,
                memory_type=metadata.type.value,
                tags=metadata.tags,
                importance=metadata.importance.value,
                conversation_id=metadata.conversation_id,
                expires_at=expires_at
            )
            session.add(model)
            await session.commit()
        
        # Store embedding in ChromaDB
        self._vector_collection.add(
            ids=[entry_id],
            embeddings=[embedding],
            metadatas=[{
                "user_id": user_id,
                "agent_id": agent_id,
                "source": metadata.source.value,
                "memory_type": metadata.type.value,
                "importance": metadata.importance.value
            }]
        )
        
        # Cache in Redis
        await self._cache_entry(entry_id, content, metadata)
        
        return MemoryEntry(
            id=entry_id,
            user_id=user_id,
            agent_id=agent_id,
            content=content,
            embedding=embedding,
            metadata=metadata,
            created_at=datetime.utcnow(),
            accessed_at=datetime.utcnow(),
            expires_at=expires_at
        )
    
    async def insert_batch(self, entries: list[tuple[str, MemoryMetadata, dict[str, Any]]]) -> list[MemoryEntry]:
        """Insert multiple memory entries efficiently."""
        results = []
        
        # Batch generate embeddings
        contents = [e[0] for e in entries]
        embeddings = await self.embedding_service.embed(contents)
        
        for i, (content, metadata, extra) in enumerate(entries):
            entry = await self.insert(
                content=content,
                metadata=metadata,
                user_id=extra.get("user_id"),
                agent_id=extra.get("agent_id"),
                embedding=embeddings[i],
                expires_at=extra.get("expires_at")
            )
            results.append(entry)
        
        return results
    
    async def semantic_search(
        self,
        query: str,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
        min_importance: Optional[Importance] = None
    ) -> list[MemorySearchResult]:
        """
        Perform semantic search across memory entries.
        Combines vector similarity with metadata filtering.
        """
        # Generate query embedding
        query_embedding = await self.embedding_service.embed_query(query)
        
        # Build ChromaDB where clause
        where_filter = {}
        if user_id:
            where_filter["user_id"] = user_id
        if agent_id:
            where_filter["agent_id"] = agent_id
        if filters:
            where_filter.update(filters)
        
        # Search vector DB
        results = self._vector_collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k * 2,  # Get more for filtering
            where=where_filter if where_filter else None
        )
        
        if not results or not results["ids"]:
            return []
        
        # Filter and fetch from PostgreSQL
        entry_ids = results["ids"][0]
        distances = results["distances"][0] if results.get("distances") else [0.0] * len(entry_ids)
        
        # Calculate relevance scores (1 - cosine_distance)
        relevance_scores = [1.0 - d for d in distances]
        
        # Filter by minimum importance
        if min_importance:
            importance_order = {Importance.LOW: 0, Importance.MEDIUM: 1, Importance.HIGH: 2, Importance.CRITICAL: 3}
            min_level = importance_order.get(min_importance, 1)
            filtered_ids = []
            filtered_scores = []
            for entry_id, score in zip(entry_ids, relevance_scores):
                entry_importance = results["metadatas"][0].get(entry_ids.index(entry_id), {}).get("importance", "medium")
                if importance_order.get(Importance(entry_importance), 1) >= min_level:
                    filtered_ids.append(entry_id)
                    filtered_scores.append(score)
            entry_ids = filtered_ids
            relevance_scores = filtered_scores
        
        # Fetch full entries from PostgreSQL
        async with self._session_factory() as session:
            from sqlalchemy import select
            stmt = select(MemoryEntryModel).where(MemoryEntryModel.id.in_(entry_ids))
            result = await session.execute(stmt)
            models = result.scalars().all()
        
        # Create lookup map
        entry_map = {m.id: m for m in models}
        
        # Build results
        memory_results = []
        for rank, (entry_id, score) in enumerate(zip(entry_ids, relevance_scores)):
            if entry_id in entry_map:
                model = entry_map[entry_id]
                metadata = MemoryMetadata(
                    source=MemorySource(model.source),
                    type=MemoryType(model.memory_type),
                    tags=model.tags or [],
                    importance=Importance(model.importance),
                    conversation_id=model.conversation_id,
                    user_id=model.user_id
                )
                
                memory_results.append(MemorySearchResult(
                    entry=MemoryEntry(
                        id=model.id,
                        user_id=model.user_id,
                        agent_id=model.agent_id,
                        content=model.content,
                        metadata=metadata,
                        created_at=model.created_at,
                        accessed_at=model.accessed_at,
                        expires_at=model.expires_at
                    ),
                    relevance_score=score,
                    distance=distances[entry_ids.index(entry_id)] if entry_id in entry_ids else None,
                    rank=rank + 1
                ))
        
        # Update access times asynchronously
        asyncio.create_task(self._update_access_times([r.entry.id for r in memory_results]))
        
        return memory_results[:top_k]
    
    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get a specific memory entry by ID."""
        # Check cache first
        cached = await self._get_cached_entry(entry_id)
        if cached:
            return cached
        
        async with self._session_factory() as session:
            from sqlalchemy import select
            stmt = select(MemoryEntryModel).where(MemoryEntryModel.id == entry_id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
        
        if not model:
            return None
        
        metadata = MemoryMetadata(
            source=MemorySource(model.source),
            type=MemoryType(model.memory_type),
            tags=model.tags or [],
            importance=Importance(model.importance),
            conversation_id=model.conversation_id,
            user_id=model.user_id
        )
        
        return MemoryEntry(
            id=model.id,
            user_id=model.user_id,
            agent_id=model.agent_id,
            content=model.content,
            metadata=metadata,
            created_at=model.created_at,
            accessed_at=model.accessed_at,
            expires_at=model.expires_at
        )
    
    async def delete(self, entry_id: str) -> bool:
        """Delete a memory entry."""
        # Delete from PostgreSQL
        async with self._session_factory() as session:
            from sqlalchemy import delete
            stmt = delete(MemoryEntryModel).where(MemoryEntryModel.id == entry_id)
            await session.execute(stmt)
            await session.commit()
        
        # Delete from vector DB
        self._vector_collection.delete(ids=[entry_id])
        
        # Remove from cache
        if self._redis_client:
            await self._redis_client.delete(f"memory:{entry_id}")
        
        return True
    
    async def get_user_context(
        self,
        user_id: str,
        max_entries: int = 50,
        time_window: Optional[timedelta] = None
    ) -> list[MemoryEntry]:
        """Get recent memory context for a user."""
        async with self._session_factory() as session:
            from sqlalchemy import select, desc
            stmt = select(MemoryEntryModel).where(
                MemoryEntryModel.user_id == user_id
            ).order_by(desc(MemoryEntryModel.accessed_at)).limit(max_entries)
            
            if time_window:
                cutoff = datetime.utcnow() - time_window
                stmt = stmt.where(MemoryEntryModel.accessed_at >= cutoff)
            
            result = await session.execute(stmt)
            models = result.scalars().all()
        
        entries = []
        for model in models:
            metadata = MemoryMetadata(
                source=MemorySource(model.source),
                type=MemoryType(model.memory_type),
                tags=model.tags or [],
                importance=Importance(model.importance),
                conversation_id=model.conversation_id,
                user_id=model.user_id
            )
            entries.append(MemoryEntry(
                id=model.id,
                user_id=model.user_id,
                agent_id=model.agent_id,
                content=model.content,
                metadata=metadata,
                created_at=model.created_at,
                accessed_at=model.accessed_at,
                expires_at=model.expires_at
            ))
        
        return entries
    
    async def cleanup_expired(self) -> int:
        """Remove expired memory entries. Returns count of deleted entries."""
        async with self._session_factory() as session:
            from sqlalchemy import delete, select
            
            # Find expired entries
            stmt = select(MemoryEntryModel).where(
                MemoryEntryModel.expires_at < datetime.utcnow()
            )
            result = await session.execute(stmt)
            expired = result.scalars().all()
            
            if not expired:
                return 0
            
            # Delete from PostgreSQL
            delete_stmt = delete(MemoryEntryModel).where(
                MemoryEntryModel.expires_at < datetime.utcnow()
            )
            await session.execute(delete_stmt)
            await session.commit()
            
            # Delete from vector DB
            expired_ids = [e.id for e in expired]
            self._vector_collection.delete(ids=expired_ids)
            
            return len(expired_ids)
    
    # ─────────────────────────────────────────────────────
    # Cache Operations
    # ─────────────────────────────────────────────────────
    
    async def _cache_entry(self, entry_id: str, content: str, metadata: MemoryMetadata) -> None:
        """Cache entry in Redis."""
        if not self._redis_client:
            return
        
        cache_data = {
            "id": entry_id,
            "content": content,
            "metadata": {
                "source": metadata.source.value,
                "type": metadata.type.value,
                "tags": metadata.tags,
                "importance": metadata.importance.value
            }
        }
        
        await self._redis_client.setex(
            f"memory:{entry_id}",
            ttl=3600,  # 1 hour cache
            value=json.dumps(cache_data)
        )
    
    async def _get_cached_entry(self, entry_id: str) -> Optional[MemoryEntry]:
        """Get entry from Redis cache."""
        if not self._redis_client:
            return None
        
        cached = await self._redis_client.get(f"memory:{entry_id}")
        if not cached:
            return None
        
        data = json.loads(cached)
        metadata = MemoryMetadata(
            source=MemorySource(data["metadata"]["source"]),
            type=MemoryType(data["metadata"]["type"]),
            tags=data["metadata"]["tags"],
            importance=Importance(data["metadata"]["importance"])
        )
        
        return MemoryEntry(
            id=data["id"],
            content=data["content"],
            metadata=metadata
        )
    
    async def _update_access_times(self, entry_ids: list[str]) -> None:
        """Update accessed_at timestamps for entries."""
        async with self._session_factory() as session:
            from sqlalchemy import update
            now = datetime.utcnow()
            for entry_id in entry_ids:
                stmt = update(MemoryEntryModel).where(
                    MemoryEntryModel.id == entry_id
                ).values(accessed_at=now)
                await session.execute(stmt)
            await session.commit()


# ─────────────────────────────────────────────────────────
# Factory Function
# ─────────────────────────────────────────────────────────
async def create_memory_store(
    database_url: str,
    vector_db_path: str = "./data/chroma",
    redis_url: Optional[str] = None
) -> HybridMemoryStore:
    """Create and initialize a HybridMemoryStore."""
    store = HybridMemoryStore(
        database_url=database_url,
        vector_db_path=vector_db_path,
        redis_url=redis_url
    )
    await store.initialize()
    return store
