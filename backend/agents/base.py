"""
Base Agent class with LLM integration.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Optional
from uuid import uuid4

from pydantic import BaseModel

from models.schemas import AgentCapability, MemoryEntry


@dataclass
class AgentResponse:
    """Response from an agent execution."""
    output: str
    confidence: float = 1.0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    thoughts: list[str] = field(default_factory=list)
    context_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """Represents a tool call made by an agent."""
    name: str
    arguments: dict[str, Any]
    result: Any = None
    started_at: datetime = field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    error: Optional[str] = None


class BaseAgent(ABC):
    """
    Abstract base class for agents.
    Provides common functionality for LLM-based agents.
    """
    
    def __init__(
        self,
        id: str,
        name: str,
        description: str = "",
        model: str = "gpt-4-turbo-preview",
        capabilities: Optional[list[AgentCapability]] = None,
        tools: Optional[list[Any]] = None,
        system_prompt: Optional[str] = None
    ):
        self.id = id
        self.name = name
        self.description = description
        self.model = model
        self.capabilities = capabilities or []
        self.tools = tools or []
        self.system_prompt = system_prompt or self._get_default_system_prompt()
        
        self._llm_client = None
        self._tool_registry: dict[str, Any] = {}
        
        # Register tools
        for tool in self.tools:
            self._tool_registry[tool.name] = tool
    
    @abstractmethod
    def _get_default_system_prompt(self) -> str:
        """Return the default system prompt for this agent type."""
        pass
    
    @abstractmethod
    async def _call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        stream: bool = True
    ) -> AsyncGenerator[str, None]:
        """
        Call the LLM with a prompt.
        Yields chunks of the response.
        """
        pass
    
    @abstractmethod
    async def _create_embedding(self, text: str) -> list[float]:
        """Create an embedding for text."""
        pass
    
    async def execute(
        self,
        task: str,
        context: Optional[list[MemoryEntry]] = None,
        stream: bool = True
    ) -> AgentResponse:
        """
        Execute a task with the agent.
        
        Args:
            task: The task description
            context: Optional memory entries to use as context
            stream: Whether to stream the response
            
        Returns:
            AgentResponse with output and metadata
        """
        thoughts = []
        tool_calls: list[ToolCall] = []
        
        # Build context prompt
        context_prompt = ""
        if context:
            context_prompt = "\n\n## Relevant Context:\n"
            for i, entry in enumerate(context[:5]):  # Limit to top 5
                context_prompt += f"[{i+1}] {entry.content}\n"
        
        # Build full prompt
        full_prompt = f"""## Task
{task}
{context_prompt}

## Instructions
Think step by step about how to accomplish this task. 
Provide a clear, helpful response."""
        
        # Execute with streaming
        output_chunks = []
        async for chunk in self._call_llm(full_prompt, self.system_prompt, stream):
            if stream:
                output_chunks.append(chunk)
                # Could emit thought updates here
        
        output = "".join(output_chunks)
        
        return AgentResponse(
            output=output,
            confidence=0.85,  # Placeholder - could be calculated from response
            tool_calls=[tc.__dict__ for tc in tool_calls],
            thoughts=thoughts,
            context_used=[e.id for e in context] if context else []
        )
    
    async def think_aloud(self) -> AsyncGenerator[dict[str, Any], None]:
        """
        Generate a stream of thoughts as the agent processes.
        Used for real-time visualization of agent reasoning.
        """
        pass  # Implemented in subclasses
    
    def register_tool(self, tool: Any) -> None:
        """Register a new tool for this agent."""
        self._tool_registry[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Any]:
        """Get a registered tool by name."""
        return self._tool_registry.get(name)


class ReasoningAgent(BaseAgent):
    """Agent specialized for reasoning and analysis tasks."""
    
    def _get_default_system_prompt(self) -> str:
        return """You are a helpful AI assistant specialized in reasoning and analysis.
You think carefully about complex problems and provide well-reasoned answers.
Break down complex tasks into steps. Verify your reasoning.
Always be accurate and acknowledge uncertainty when appropriate."""
    
    async def _call_llm(self, prompt: str, system_prompt: Optional[str] = None, stream: bool = True) -> AsyncGenerator[str, None]:
        """Call OpenAI API."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            # Fallback for development
            yield "This is a simulated response for development purposes."
            return
        
        if self._llm_client is None:
            self._llm_client = AsyncOpenAI()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        if stream:
            stream_response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                temperature=0.7
            )
            
            async for chunk in stream_response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        else:
            response = await self._llm_client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7
            )
            yield response.choices[0].message.content
    
    async def _create_embedding(self, text: str) -> list[float]:
        """Create embedding using OpenAI."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            import numpy as np
            # Fallback
            rng = np.random.RandomState(hash(text) % (2**32))
            return rng.randn(384).tolist()
        
        if self._llm_client is None:
            self._llm_client = AsyncOpenAI()
        
        response = await self._llm_client.embeddings.create(
            model="text-embedding-ada-002",
            input=text
        )
        return response.data[0].embedding


class ToolUseAgent(ReasoningAgent):
    """Agent that can use tools to accomplish tasks."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._execution_history: list[dict[str, Any]] = []
    
    async def execute_with_tools(
        self,
        task: str,
        context: Optional[list[MemoryEntry]] = None,
        max_tool_calls: int = 5
    ) -> AgentResponse:
        """
        Execute task with tool use capabilities.
        Implements a simple tool-calling loop.
        """
        current_prompt = task
        tool_calls_made = 0
        execution_trace = []
        
        while tool_calls_made < max_tool_calls:
            # Get LLM response
            response_text = ""
            async for chunk in self._call_llm(
                current_prompt,
                system_prompt=self.system_prompt + "\n\nYou have access to tools.",
                stream=False
            ):
                response_text += chunk
            
            # Parse tool calls from response (simplified)
            tool_calls = self._parse_tool_calls(response_text)
            
            if not tool_calls:
                # No more tool calls, return final response
                return AgentResponse(
                    output=response_text,
                    confidence=0.9,
                    tool_calls=[tc.__dict__ for tc in execution_trace],
                    context_used=[e.id for e in context] if context else []
                )
            
            # Execute tool calls
            for tool_call in tool_calls:
                result = await self._execute_tool(tool_call)
                execution_trace.append(tool_call.__dict__)
                
                # Add result to prompt for next iteration
                current_prompt += f"\n\n[Tool Result: {tool_call.name}]\n{result}"
                tool_calls_made += 1
        
        return AgentResponse(
            output="Maximum tool calls reached. Please refine your request.",
            confidence=0.5,
            tool_calls=[tc.__dict__ for tc in execution_trace]
        )
    
    def _parse_tool_calls(self, response_text: str) -> list[ToolCall]:
        """Parse tool calls from LLM response."""
        # Simplified parsing - in production, use structured outputs or function calling
        tool_calls = []
        
        # Look for patterns like: <tool_call>search: {"query": "..."}</tool_call>
        import re
        pattern = r'<tool_call>(\w+):\s*({.*?})</tool_call>'
        matches = re.findall(pattern, response_text, re.DOTALL)
        
        for name, args_str in matches:
            if name in self._tool_registry:
                import json
                try:
                    args = json.loads(args_str)
                    tool_calls.append(ToolCall(name=name, arguments=args))
                except json.JSONDecodeError:
                    pass
        
        return tool_calls
    
    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a tool and return its result."""
        tool = self.get_tool(tool_call.name)
        
        if not tool:
            tool_call.error = f"Tool not found: {tool_call.name}"
            return f"Error: {tool_call.error}"
        
        try:
            if asyncio.iscoroutinefunction(tool.execute):
                result = await tool.execute(**tool_call.arguments)
            else:
                result = tool.execute(**tool_call.arguments)
            
            tool_call.result = result
            tool_call.ended_at = datetime.utcnow()
            return str(result)
        except Exception as e:
            tool_call.error = str(e)
            tool_call.ended_at = datetime.utcnow()
            return f"Error executing {tool_call.name}: {str(e)}"
