"""
Pydantic schemas for API request/response validation.
All API contracts are defined here.
"""

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class SupportTier(str, Enum):
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"


class PromptStrategyEnum(str, Enum):
    ZERO_SHOT = "zero_shot"
    FEW_SHOT = "few_shot"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    ROLE_SPECIFIC = "role_specific"
    RAG_STANDARD = "rag_standard"
    RAG_WITH_COT = "rag_with_cot"


# ─── Request Schemas ──────────────────────────────────────────────────────────

class UserContext(BaseModel):
    """Optional user profile context passed with each request."""
    customer_name: Optional[str] = None
    account_tier: SupportTier = SupportTier.STANDARD
    customer_since: Optional[str] = None
    preferred_language: str = "en"
    technical_level: str = "beginner"
    open_tickets: int = 0
    recent_purchases: list[str] = Field(default_factory=list)
    special_notes: Optional[str] = None

    class Config:
        use_enum_values = True


class ChatRequest(BaseModel):
    """Request to the main chat endpoint."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The customer's message or question",
    )
    conversation_id: Optional[str] = Field(
        None,
        description="Session ID for multi-turn conversation. "
                    "If not provided, a new session is created.",
    )
    user_context: Optional[UserContext] = Field(
        None,
        description="Optional user profile for personalized responses",
    )
    stream: bool = Field(
        False,
        description="Whether to stream the response token by token",
    )
    prompt_strategy: PromptStrategyEnum = Field(
        PromptStrategyEnum.RAG_STANDARD,
        description="Prompting strategy to use",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata filters for retrieval",
    )

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be empty or whitespace")
        return v.strip()


class FeedbackRequest(BaseModel):
    """Customer feedback on a response."""
    conversation_id: str
    message_index: int = Field(..., ge=0)
    rating: int = Field(..., ge=1, le=5)
    feedback_text: Optional[str] = Field(None, max_length=1000)
    was_helpful: bool = True
    issue_category: Optional[str] = None


class DocumentIngestRequest(BaseModel):
    """Request to ingest a document from URL or base64."""
    url: Optional[str] = None
    content: Optional[str] = None   # Base64 encoded content
    filename: Optional[str] = None
    doc_type: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_strategy: str = "hierarchical"


class EvaluationRequest(BaseModel):
    """Request to run evaluation on test samples."""
    samples: list[dict] = Field(
        ...,
        description="List of {question, answer, contexts, ground_truth} dicts",
    )
    dataset_name: str = "api_evaluation"
    use_llm_metrics: bool = True
    use_statistical_metrics: bool = True


# ─── Response Schemas ─────────────────────────────────────────────────────────

class SourceReference(BaseModel):
    """A source document reference in the response."""
    doc_id: str
    title: str
    source: str = ""
    doc_type: str = ""


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    answer: str
    conversation_id: str
    sources: list[SourceReference] = Field(default_factory=list)
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score based on retrieval relevance",
    )
    reformulated_query: Optional[str] = Field(
        None,
        description="Reformulated query used for retrieval (if conversational)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Pipeline metadata: tokens, latency, cost",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "answer": "To reset your password, click 'Forgot Password'...",
                "conversation_id": "conv-abc123",
                "sources": [
                    {
                        "doc_id": "doc_001",
                        "title": "Account Management Guide",
                        "source": "docs/account.pdf",
                        "doc_type": "pdf",
                    }
                ],
                "confidence": 0.92,
                "metadata": {
                    "latency_ms": 1250.5,
                    "tokens_used": 1823,
                    "cost_usd": 0.000456,
                },
            }
        }


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "1.0.0"
    components: dict[str, str] = Field(default_factory=dict)
    uptime_seconds: float = 0.0


class EvaluationResponse(BaseModel):
    """Response from evaluation endpoint."""
    dataset_name: str
    total_samples: int
    overall_pass_rate: float
    metric_averages: dict[str, float]
    pass_rates: dict[str, float]
    evaluation_time_seconds: float


class StatsResponse(BaseModel):
    """Pipeline statistics response."""
    vector_store_count: int
    keyword_index_count: int
    document_count: int
    llm_requests: int
    total_tokens_used: int
    total_cost_usd: float