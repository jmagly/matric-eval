"""
Base judge interface for universal LLM-as-Judge evaluation.

Defines the abstract Judge protocol and shared result types.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class JudgeResult:
    """Result from a judge evaluation."""

    score: float  # 0.0 - 1.0 normalized
    raw_score: float  # Original scale (e.g., 1-10)
    reasoning: str = ""
    confidence: float = 1.0
    metadata: dict = field(default_factory=dict)
    winner: Optional[Literal["A", "B", "tie"]] = None


class Judge(ABC):
    """
    Abstract base class for LLM-as-Judge evaluators.

    All judge implementations must provide evaluate() and compare() methods.
    """

    @abstractmethod
    async def evaluate(
        self,
        prompt: str,
        response: str,
        criteria: dict,
        reference: Optional[str] = None,
    ) -> JudgeResult:
        """
        Evaluate a single response against criteria.

        Args:
            prompt: The original prompt/question
            response: The model's response to evaluate
            criteria: Evaluation criteria with weights (e.g., {"accuracy": 0.5, "clarity": 0.5})
            reference: Optional reference answer

        Returns:
            JudgeResult with score, reasoning, and metadata
        """

    @abstractmethod
    async def compare(
        self,
        prompt: str,
        response_a: str,
        response_b: str,
        criteria: dict,
    ) -> JudgeResult:
        """
        Compare two responses (pairwise evaluation).

        Args:
            prompt: The original prompt/question
            response_a: First response
            response_b: Second response
            criteria: Evaluation criteria with weights

        Returns:
            JudgeResult with winner field set to "A", "B", or "tie"
        """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this judge."""
