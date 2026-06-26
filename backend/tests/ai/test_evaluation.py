"""
AI Evaluation Framework Tests.
Tests agent behavior using LLM-as-a-Judge methodology.
"""
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class ScoreType(str, Enum):
    CONTINUOUS = "continuous"
    CATEGORICAL = "categorical"
    COMPARATIVE = "comparative"


@dataclass
class Criterion:
    name: str
    description: str
    weight: float = 1.0
    score_type: ScoreType = ScoreType.CONTINUOUS
    rubric: Optional[dict[str, float]] = None


@dataclass
class EvaluationResult:
    criterion_name: str
    score: float
    reasoning: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class AggregatedResult:
    individual_results: list[EvaluationResult]
    overall_score: float
    passed: bool
    feedback: str


class MockJudge:
    """
    Mock LLM Judge for testing without real API calls.
    In production, replace with actual AnthropicJudge or OpenAIJudge.
    """
    
    def __init__(self, mock_responses: Optional[dict[str, Any]] = None):
        self.mock_responses = mock_responses or {}
        self.call_history: list[dict[str, Any]] = []
    
    async def evaluate(
        self,
        prompt: str,
        response: str,
        context: Optional[str] = None,
        rubric: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Evaluate a response (mock implementation)."""
        
        self.call_history.append({
            "prompt": prompt,
            "response": response,
            "context": context,
            "rubric": rubric
        })
        
        # Check for predefined mock responses
        for key, mock_result in self.mock_responses.items():
            if key in response.lower():
                return mock_result
        
        # Generate a reasonable mock evaluation
        score = 0.8  # Default good score
        
        # Penalize for short responses
        if len(response) < 50:
            score = 0.5
        
        # Penalize for error indicators
        error_indicators = ["error", "failed", "exception", "sorry"]
        for indicator in error_indicators:
            if indicator in response.lower():
                score -= 0.2
                break
        
        # Cap score
        score = max(0.0, min(1.0, score))
        
        return {
            "scores": {
                "quality": {
                    "score": score,
                    "reasoning": f"Mock evaluation: response length {len(response)} chars",
                    "evidence": [response[:100] + "..."]
                }
            },
            "overall_score": score,
            "feedback": f"Mock feedback: Score {score:.2f}",
            "passed": score >= 0.7
        }


class BehaviorEvaluator:
    """Evaluates agent behavior using defined criteria."""
    
    def __init__(self, judge: MockJudge):
        self.judge = judge
        self.criteria: list[Criterion] = []
    
    def add_criterion(self, criterion: Criterion) -> None:
        self.criteria.append(criterion)
    
    async def evaluate_response(
        self,
        input_prompt: str,
        agent_response: str,
        reference_response: Optional[str] = None
    ) -> AggregatedResult:
        """Evaluate a single agent response."""
        
        rubric_dict = {
            "criteria": [
                {
                    "name": c.name,
                    "weight": c.weight,
                    "description": c.description
                }
                for c in self.criteria
            ]
        }
        
        result = await self.judge.evaluate(
            prompt=input_prompt,
            response=agent_response,
            context=reference_response,
            rubric=rubric_dict
        )
        
        results = []
        for criterion_name, score_data in result.get("scores", {}).items():
            results.append(EvaluationResult(
                criterion_name=criterion_name,
                score=score_data.get("score", 0.0),
                reasoning=score_data.get("reasoning", ""),
                evidence=score_data.get("evidence", [])
            ))
        
        return AggregatedResult(
            individual_results=results,
            overall_score=result.get("overall_score", 0.0),
            passed=result.get("passed", False),
            feedback=result.get("feedback", "")
        )
    
    async def evaluate_batch(
        self,
        test_cases: list[dict[str, Any]]
    ) -> list[AggregatedResult]:
        """Evaluate multiple test cases."""
        results = []
        
        for case in test_cases:
            result = await self.evaluate_response(
                input_prompt=case["input"],
                agent_response=case["output"],
                reference_response=case.get("expected")
            )
            results.append(result)
        
        return results


# ─────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────

class TestMockJudge:
    """Tests for the mock judge."""
    
    def test_judge_initialization(self):
        """Test judge can be initialized."""
        judge = MockJudge()
        assert judge is not None
        assert judge.call_history == []
    
    def test_judge_with_mock_responses(self):
        """Test judge with predefined responses."""
        judge = MockJudge(
            mock_responses={
                "hello": {
                    "scores": {"quality": {"score": 1.0, "reasoning": "Perfect", "evidence": []}},
                    "overall_score": 1.0,
                    "feedback": "Great!",
                    "passed": True
                }
            }
        )
        
        assert "hello" in judge.mock_responses
    
    @pytest.mark.asyncio
    async def test_judge_evaluates_good_response(self):
        """Test judge evaluates a good response."""
        judge = MockJudge()
        
        result = await judge.evaluate(
            prompt="What is Python?",
            response="Python is a high-level programming language known for its readability and versatility."
        )
        
        assert "overall_score" in result
        assert result["overall_score"] >= 0.5
        assert "feedback" in result
    
    @pytest.mark.asyncio
    async def test_judge_evaluates_poor_response(self):
        """Test judge evaluates a poor response."""
        judge = MockJudge()
        
        result = await judge.evaluate(
            prompt="What is Python?",
            response="Error"
        )
        
        assert result["overall_score"] < 0.8  # Should be penalized
    
    @pytest.mark.asyncio
    async def test_judge_records_call_history(self):
        """Test judge records call history."""
        judge = MockJudge()
        
        await judge.evaluate(
            prompt="Test prompt",
            response="Test response"
        )
        
        assert len(judge.call_history) == 1
        assert judge.call_history[0]["prompt"] == "Test prompt"


class TestBehaviorEvaluator:
    """Tests for the behavior evaluator."""
    
    @pytest.fixture
    def evaluator(self):
        """Create an evaluator with mock judge."""
        judge = MockJudge()
        evaluator = BehaviorEvaluator(judge)
        evaluator.add_criterion(Criterion(
            name="quality",
            description="Response quality",
            weight=1.0
        ))
        return evaluator
    
    @pytest.mark.asyncio
    async def test_evaluate_single_response(self, evaluator):
        """Test evaluating a single response."""
        result = await evaluator.evaluate_response(
            input_prompt="What is AI?",
            agent_response="AI stands for Artificial Intelligence, which is the simulation of human intelligence by machines."
        )
        
        assert isinstance(result, AggregatedResult)
        assert result.overall_score >= 0.0
        assert isinstance(result.passed, bool)
    
    @pytest.mark.asyncio
    async def test_evaluate_batch(self, evaluator):
        """Test evaluating a batch of responses."""
        test_cases = [
            {"input": "What is 1+1?", "output": "2"},
            {"input": "What is Python?", "output": "A programming language"},
            {"input": "What is the capital of France?", "output": "Paris"}
        ]
        
        results = await evaluator.evaluate_batch(test_cases)
        
        assert len(results) == 3
        for result in results:
            assert isinstance(result, AggregatedResult)


class TestCriteriaWeighting:
    """Tests for criterion weighting."""
    
    def test_criterion_default_weight(self):
        """Test default weight is 1.0."""
        criterion = Criterion(name="test", description="Test criterion")
        assert criterion.weight == 1.0
    
    def test_criterion_custom_weight(self):
        """Test custom weight."""
        criterion = Criterion(
            name="test",
            description="Test",
            weight=0.5
        )
        assert criterion.weight == 0.5
    
    def test_multiple_criteria_weights(self):
        """Test multiple criteria with different weights."""
        criteria = [
            Criterion(name="accuracy", description="Accurate", weight=0.4),
            Criterion(name="helpfulness", description="Helpful", weight=0.3),
            Criterion(name="safety", description="Safe", weight=0.3)
        ]
        
        total_weight = sum(c.weight for c in criteria)
        assert total_weight == 1.0


class TestEvaluationRubric:
    """Tests for evaluation rubric configuration."""
    
    def test_rubric_with_criteria(self):
        """Test rubric with multiple criteria."""
        criteria = [
            Criterion(name="quality", description="Quality check", weight=0.5),
            Criterion(name="safety", description="Safety check", weight=0.5)
        ]
        
        assert len(criteria) == 2
        
        for criterion in criteria:
            assert criterion.name in ["quality", "safety"]
    
    def test_categorical_criterion(self):
        """Test categorical scoring criterion."""
        criterion = Criterion(
            name="rating",
            description="Rate the response",
            score_type=ScoreType.CATEGORICAL,
            rubric={
                "excellent": 1.0,
                "good": 0.75,
                "acceptable": 0.5,
                "poor": 0.25
            }
        )
        
        assert criterion.score_type == ScoreType.CATEGORICAL
        assert criterion.rubric is not None
        assert "excellent" in criterion.rubric


# ─────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────

class TestAgentEvaluationIntegration:
    """Integration tests for agent evaluation."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_evaluation(self):
        """Test complete evaluation flow."""
        # Setup
        judge = MockJudge()
        evaluator = BehaviorEvaluator(judge)
        evaluator.add_criterion(Criterion(
            name="relevance",
            description="Response addresses the query",
            weight=1.0
        ))
        
        # Test case
        test_case = {
            "input": "What is machine learning?",
            "output": "Machine learning is a subset of artificial intelligence that enables systems to learn from data and improve their performance without being explicitly programmed."
        }
        
        # Evaluate
        result = await evaluator.evaluate_response(
            input_prompt=test_case["input"],
            agent_response=test_case["output"]
        )
        
        # Assert
        assert result.overall_score > 0.5
        assert len(result.individual_results) > 0
        
        # Check judge was called
        assert len(judge.call_history) == 1
        assert test_case["input"] in judge.call_history[0]["prompt"]
        assert test_case["output"] in judge.call_history[0]["response"]
    
    @pytest.mark.asyncio
    async def test_multiple_agents_comparison(self):
        """Test comparing multiple agent responses."""
        judge = MockJudge()
        evaluator = BehaviorEvaluator(judge)
        evaluator.add_criterion(Criterion(
            name="accuracy",
            description="Factual accuracy",
            weight=1.0
        ))
        
        test_prompt = "What is the capital of Japan?"
        
        agent_responses = [
            {"agent": "Agent A", "output": "Tokyo"},
            {"agent": "Agent B", "output": "The capital of Japan is Tokyo."},
            {"agent": "Agent C", "output": "Osaka"}
        ]
        
        results = []
        for agent_response in agent_responses:
            result = await evaluator.evaluate_response(
                input_prompt=test_prompt,
                agent_response=agent_response["output"]
            )
            results.append({
                "agent": agent_response["agent"],
                "score": result.overall_score
            })
        
        # Agent A and B should have higher scores (correct answer with more detail)
        # Agent C should have lower score (wrong answer)
        # Note: Mock judge gives lower scores to short responses
        assert results[0]["score"] >= 0.5  # "Tokyo" is short but correct
        assert results[1]["score"] >= 0.5  # "The capital..." is longer
