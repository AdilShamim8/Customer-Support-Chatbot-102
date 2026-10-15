"""
Complete RAG Pipeline orchestrating all components end-to-end.

Flow:
  User Query
    → Standalone Question Reformulation (if conversational)
    → Query Expansion (optional)
    → Hybrid Retrieval (Vector + BM25 + RRF)
    → Reranking
    → Prompt Construction (with strategy)
    → LLM Generation
    → Hallucination Check (optional)
    → Response
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator, Optional

import structlog

from configs.settings import settings
from src.generation.llm_client import (
    BaseLLMClient,
    LLMClientFactory,
    LLMRequest,
    LLMResponse,
    Message,
    MessageRole,
)
from src.generation.prompt_engine import (
    PromptConfig,
    PromptEngine,
    PromptStrategy,
)
from src.retrieval.retriever import (
    Retriever,
    RetrievalConfig,
    RetrievalResult,
)
from src.pipeline.conversation import ConversationManager, Conversation

logger = structlog.get_logger(__name__)


@dataclass
class RAGConfig:
    """Full RAG pipeline configuration."""
    # Retrieval
    retrieval_config: RetrievalConfig = field(
        default_factory=RetrievalConfig
    )
    # Prompt Engineering
    prompt_config: PromptConfig = field(
        default_factory=PromptConfig
    )
    # Generation
    temperature: float = 0.1
    max_tokens: int = settings.max_response_tokens
    stream: bool = False
    # Pipeline features
    reformulate_query: bool = True
    check_hallucination: bool = False
    enable_citations: bool = True
    fallback_to_general: bool = True


@dataclass
class RAGResponse:
    """Complete RAG pipeline response."""
    answer: str
    sources: list[dict]
    retrieval_result: RetrievalResult
    llm_response: LLMResponse
    query: str
    reformulated_query: Optional[str] = None
    hallucination_check: Optional[dict] = None
    pipeline_metadata: dict[str, Any] = field(default_factory=dict)
    total_latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "answer": self.answer,
            "sources": self.sources,
            "query": self.query,
            "reformulated_query": self.reformulated_query,
            "hallucination_check": self.hallucination_check,
            "pipeline_metadata": {
                **self.pipeline_metadata,
                "retrieval": self.retrieval_result.retrieval_metadata,
                "llm": self.llm_response.to_dict(),
                "total_latency_ms": self.total_latency_ms,
            },
        }

    @property
    def has_sources(self) -> bool:
        return len(self.sources) > 0

    @property
    def context_used(self) -> str:
        return self.retrieval_result.context


class RAGPipeline:
    """
    Production RAG Pipeline.

    Integrates all components into a unified interface
    for single-turn and multi-turn customer support.
    """

    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        llm_client: Optional[BaseLLMClient] = None,
        conversation_manager: Optional[ConversationManager] = None,
        config: Optional[RAGConfig] = None,
    ):
        self.retriever = retriever or Retriever()
        self.llm = llm_client or LLMClientFactory.create_default()
        self.conversation_manager = conversation_manager or ConversationManager()
        self.config = config or RAGConfig()

        # Initialize prompt engine with config
        self.prompt_engine = PromptEngine(config=self.config.prompt_config)

        logger.info(
            "RAG Pipeline initialized",
            strategy=self.config.prompt_config.strategy.value,
            stream=self.config.stream,
            check_hallucination=self.config.check_hallucination,
        )

    # ── Main Query Method ─────────────────────────────────────────────────────

    def query(
        self,
        user_query: str,
        conversation_id: Optional[str] = None,
        user_context: Optional[dict] = None,
        config_override: Optional[RAGConfig] = None,
    ) -> RAGResponse:
        """
        Process a user query through the full RAG pipeline.

        Args:
            user_query: The customer's question
            conversation_id: Session ID for multi-turn conversations
            user_context: User profile metadata
            config_override: Override pipeline config for this request

        Returns:
            RAGResponse with answer, sources, and metadata
        """
        pipeline_start = time.time()
        config = config_override or self.config

        logger.info(
            "RAG query started",
            query=user_query[:100],
            conversation_id=conversation_id,
        )

        # Step 1: Get conversation history
        conversation = None
        history = []
        if conversation_id:
            conversation = self.conversation_manager.get_or_create(
                conversation_id
            )
            history = conversation.get_messages()

        # Step 2: Query reformulation for conversational context
        retrieval_query = user_query
        reformulated_query = None

        if config.reformulate_query and history:
            reformulated_query = self._reformulate_query(
                query=user_query,
                history=history,
            )
            retrieval_query = reformulated_query or user_query
            logger.debug(
                "Query reformulated",
                original=user_query,
                reformulated=reformulated_query,
            )

        # Step 3: Hybrid retrieval
        retrieval_result = self.retriever.retrieve(
            query=retrieval_query,
            config=config.retrieval_config,
        )

        # Step 4: Build prompt
        messages = self.prompt_engine.build_rag_prompt(
            user_query=user_query,
            retrieval_result=retrieval_result,
            conversation_history=history,
            user_context=user_context,
        )

        # Step 5: LLM generation
        llm_request = LLMRequest(
            messages=messages,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            stream=config.stream,
        )

        llm_response = self.llm.complete(llm_request)

        # Step 6: Optional hallucination check
        hallucination_check = None
        if config.check_hallucination and retrieval_result.chunks:
            hallucination_check = self._check_hallucination(
                question=user_query,
                context=retrieval_result.context,
                answer=llm_response.content,
            )

            if hallucination_check and not hallucination_check.get("grounded", True):
                logger.warning(
                    "Hallucination detected",
                    confidence=hallucination_check.get("confidence"),
                    issues=hallucination_check.get("issues"),
                )

        # Step 7: Format response
        answer = llm_response.content
        if config.enable_citations:
            answer = self._add_citation_footer(
                answer=answer,
                sources=retrieval_result.sources,
            )

        # Step 8: Update conversation history
        if conversation:
            conversation.add_message(
                Message(role=MessageRole.USER, content=user_query)
            )
            conversation.add_message(
                Message(role=MessageRole.ASSISTANT, content=llm_response.content)
            )
            self.conversation_manager.save(conversation)

        total_latency = (time.time() - pipeline_start) * 1000

        response = RAGResponse(
            answer=answer,
            sources=retrieval_result.sources,
            retrieval_result=retrieval_result,
            llm_response=llm_response,
            query=user_query,
            reformulated_query=reformulated_query,
            hallucination_check=hallucination_check,
            total_latency_ms=total_latency,
            pipeline_metadata={
                "strategy": config.prompt_config.strategy.value,
                "reformulated": reformulated_query is not None,
            },
        )

        logger.info(
            "RAG query complete",
            latency_ms=round(total_latency, 1),
            sources=len(retrieval_result.sources),
            tokens=llm_response.total_tokens,
            cost=llm_response.total_cost_display,
        )

        return response

    async def aquery(
        self,
        user_query: str,
        conversation_id: Optional[str] = None,
        user_context: Optional[dict] = None,
    ) -> RAGResponse:
        """Async version of query for FastAPI integration."""
        pipeline_start = time.time()

        # Get history
        conversation = None
        history = []
        if conversation_id:
            conversation = self.conversation_manager.get_or_create(conversation_id)
            history = conversation.get_messages()

        # Reformulate
        retrieval_query = user_query
        reformulated_query = None
        if self.config.reformulate_query and history:
            reformulated_query = self._reformulate_query(user_query, history)
            retrieval_query = reformulated_query or user_query

        # Retrieve
        retrieval_result = self.retriever.retrieve(
            query=retrieval_query,
            config=self.config.retrieval_config,
        )

        # Build prompt
        messages = self.prompt_engine.build_rag_prompt(
            user_query=user_query,
            retrieval_result=retrieval_result,
            conversation_history=history,
            user_context=user_context,
        )

        # Generate
        llm_request = LLMRequest(
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        llm_response = await self.llm.acomplete(llm_request)

        # Format
        answer = llm_response.content
        if self.config.enable_citations:
            answer = self._add_citation_footer(answer, retrieval_result.sources)

        # Save conversation
        if conversation:
            conversation.add_message(Message(role=MessageRole.USER, content=user_query))
            conversation.add_message(
                Message(role=MessageRole.ASSISTANT, content=llm_response.content)
            )
            self.conversation_manager.save(conversation)

        total_latency = (time.time() - pipeline_start) * 1000

        return RAGResponse(
            answer=answer,
            sources=retrieval_result.sources,
            retrieval_result=retrieval_result,
            llm_response=llm_response,
            query=user_query,
            reformulated_query=reformulated_query,
            total_latency_ms=total_latency,
        )

    def stream_query(
        self,
        user_query: str,
        conversation_id: Optional[str] = None,
        user_context: Optional[dict] = None,
    ) -> Iterator[str]:
        """Stream response tokens as they are generated."""

        conversation = None
        history = []
        if conversation_id:
            conversation = self.conversation_manager.get_or_create(conversation_id)
            history = conversation.get_messages()

        retrieval_query = user_query
        if self.config.reformulate_query and history:
            reformulated = self._reformulate_query(user_query, history)
            retrieval_query = reformulated or user_query

        retrieval_result = self.retriever.retrieve(
            query=retrieval_query,
            config=self.config.retrieval_config,
        )

        messages = self.prompt_engine.build_rag_prompt(
            user_query=user_query,
            retrieval_result=retrieval_result,
            conversation_history=history,
            user_context=user_context,
        )

        llm_request = LLMRequest(
            messages=messages,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            stream=True,
        )

        full_response = ""
        for token in self.llm.stream(llm_request):
            full_response += token
            yield token

        # Save to conversation after streaming completes
        if conversation:
            conversation.add_message(Message(role=MessageRole.USER, content=user_query))
            conversation.add_message(
                Message(role=MessageRole.ASSISTANT, content=full_response)
            )
            self.conversation_manager.save(conversation)

    # ── Internal Helpers ──────────────────────────────────────────────────────

    def _reformulate_query(
        self,
        query: str,
        history: list[Message],
    ) -> Optional[str]:
        """Reformulate follow-up question as standalone for retrieval."""
        if not history:
            return None

        # Don't reformulate if clearly standalone
        if len(query.split()) > 8 and "?" in query:
            return query

        messages = self.prompt_engine.build_standalone_question_prompt(
            question=query,
            conversation_history=history,
        )

        try:
            request = LLMRequest(
                messages=messages,
                temperature=0.0,
                max_tokens=150,
            )
            response = self.llm.complete(request)
            reformulated = response.content.strip().strip('"\'')

            # Don't use if it's basically the same
            if reformulated.lower() == query.lower():
                return None

            return reformulated

        except Exception as e:
            logger.warning("Query reformulation failed", error=str(e))
            return None

    def _check_hallucination(
        self,
        question: str,
        context: str,
        answer: str,
    ) -> Optional[dict]:
        """Check if answer is grounded in retrieved context."""
        messages = self.prompt_engine.build_hallucination_check_prompt(
            question=question,
            context=context[:3000],   # Limit for token budget
            answer=answer,
        )

        try:
            request = LLMRequest(
                messages=messages,
                temperature=0.0,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            response = self.llm.complete(request)
            return json.loads(response.content)
        except Exception as e:
            logger.warning("Hallucination check failed", error=str(e))
            return None

    def _add_citation_footer(
        self,
        answer: str,
        sources: list[dict],
    ) -> str:
        """Append citation footer to the answer."""
        if not sources:
            return answer

        citation_parts = ["\n\n---\n**Sources:**"]
        for i, source in enumerate(sources, 1):
            title = source.get("title", "Unknown")
            doc_type = source.get("doc_type", "")
            citation_parts.append(f"{i}. {title}" + (f" ({doc_type})" if doc_type else ""))

        return answer + "\n".join(citation_parts)

    def get_pipeline_stats(self) -> dict:
        return {
            "retriever": self.retriever.get_stats(),
            "llm_usage": self.llm.get_usage_stats(),
            "config": {
                "strategy": self.config.prompt_config.strategy.value,
                "retrieval_top_k": self.config.retrieval_config.top_k_retrieval,
                "rerank_top_k": self.config.retrieval_config.top_k_rerank,
            },
        }