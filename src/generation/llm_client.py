"""
LLM Client abstraction layer.
Supports OpenAI, Anthropic, and local models.
Includes streaming, retry logic, token counting, and cost tracking.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Iterator, Optional

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from configs.settings import settings, LLMProvider

logger = structlog.get_logger(__name__)


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


@dataclass
class Message:
    """A single conversation message."""
    role: MessageRole
    content: str
    name: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {"role": self.role.value, "content": self.content}
        if self.name:
            d["name"] = self.name
        return d


@dataclass
class LLMResponse:
    """Standardized LLM response across all providers."""
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    finish_reason: str = "stop"
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_cost_display(self) -> str:
        return f"${self.cost_usd:.6f}"

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "model": self.model,
            "tokens": {
                "prompt": self.prompt_tokens,
                "completion": self.completion_tokens,
                "total": self.total_tokens,
            },
            "finish_reason": self.finish_reason,
            "latency_ms": self.latency_ms,
            "cost_usd": self.cost_usd,
        }


@dataclass
class LLMRequest:
    """Standardized LLM request."""
    messages: list[Message]
    model: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = settings.max_response_tokens
    top_p: float = 1.0
    stream: bool = False
    stop_sequences: list[str] = field(default_factory=list)
    response_format: Optional[dict] = None    # {"type": "json_object"}


# ─── Pricing Table (USD per 1K tokens) ──────────────────────────────────────

PRICING = {
    # OpenAI
    "gpt-4-turbo-preview":   {"prompt": 0.01,   "completion": 0.03},
    "gpt-4o":                {"prompt": 0.005,  "completion": 0.015},
    "gpt-4o-mini":           {"prompt": 0.00015,"completion": 0.0006},
    "gpt-3.5-turbo":         {"prompt": 0.0005, "completion": 0.0015},
    # Anthropic
    "claude-3-opus-20240229":  {"prompt": 0.015,  "completion": 0.075},
    "claude-3-sonnet-20240229":{"prompt": 0.003,  "completion": 0.015},
    "claude-3-haiku-20240307": {"prompt": 0.00025,"completion": 0.00125},
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate USD cost for a request."""
    pricing = PRICING.get(model, {"prompt": 0.01, "completion": 0.03})
    cost = (
        (prompt_tokens / 1000) * pricing["prompt"]
        + (completion_tokens / 1000) * pricing["completion"]
    )
    return round(cost, 8)


# ─── Base Client ─────────────────────────────────────────────────────────────

class BaseLLMClient(ABC):
    """Abstract LLM client interface."""

    def __init__(self, model: str):
        self.model = model
        self._total_tokens_used = 0
        self._total_cost_usd = 0.0
        self._request_count = 0

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        pass

    @abstractmethod
    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        pass

    @abstractmethod
    def stream(self, request: LLMRequest) -> Iterator[str]:
        pass

    @abstractmethod
    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        pass

    def chat(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        history: Optional[list[Message]] = None,
        **kwargs,
    ) -> LLMResponse:
        """Convenience method for single-turn chat."""
        messages = []

        if system_prompt:
            messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        if history:
            messages.extend(history)

        messages.append(Message(role=MessageRole.USER, content=user_message))

        request = LLMRequest(messages=messages, **kwargs)
        return self.complete(request)

    def _track_usage(self, response: LLMResponse) -> None:
        self._total_tokens_used += response.total_tokens
        self._total_cost_usd += response.cost_usd
        self._request_count += 1

    def get_usage_stats(self) -> dict:
        return {
            "total_tokens": self._total_tokens_used,
            "total_cost_usd": round(self._total_cost_usd, 6),
            "request_count": self._request_count,
            "avg_tokens_per_request": (
                self._total_tokens_used / self._request_count
                if self._request_count > 0 else 0
            ),
        }


# ─── OpenAI Client ────────────────────────────────────────────────────────────

class OpenAIClient(BaseLLMClient):
    """
    OpenAI API client with streaming, retry, and cost tracking.
    Supports GPT-4o, GPT-4-turbo, GPT-3.5-turbo.
    """

    def __init__(
        self,
        model: str = settings.chat_model,
        api_key: Optional[str] = None,
        organization: Optional[str] = None,
    ):
        super().__init__(model)
        import openai

        self.client = openai.OpenAI(
            api_key=api_key or settings.openai_api_key,
            organization=organization,
        )
        self.async_client = openai.AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            organization=organization,
        )
        logger.info("OpenAI client initialized", model=model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=20),
        retry=retry_if_exception_type(Exception),
    )
    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()

        params = self._build_params(request)

        response = self.client.chat.completions.create(**params)

        latency_ms = (time.time() - start_time) * 1000
        content = response.choices[0].message.content or ""
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        llm_response = LLMResponse(
            content=content,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=response.usage.total_tokens,
            finish_reason=response.choices[0].finish_reason,
            latency_ms=latency_ms,
            cost_usd=calculate_cost(response.model, prompt_tokens, completion_tokens),
        )

        self._track_usage(llm_response)

        logger.debug(
            "OpenAI completion",
            model=response.model,
            tokens=response.usage.total_tokens,
            latency_ms=round(latency_ms, 1),
            cost=llm_response.total_cost_display,
        )

        return llm_response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=20),
    )
    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()

        params = self._build_params(request)
        response = await self.async_client.chat.completions.create(**params)

        latency_ms = (time.time() - start_time) * 1000
        content = response.choices[0].message.content or ""
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens

        llm_response = LLMResponse(
            content=content,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=response.usage.total_tokens,
            finish_reason=response.choices[0].finish_reason,
            latency_ms=latency_ms,
            cost_usd=calculate_cost(response.model, prompt_tokens, completion_tokens),
        )

        self._track_usage(llm_response)
        return llm_response

    def stream(self, request: LLMRequest) -> Iterator[str]:
        params = self._build_params(request)
        params["stream"] = True

        with self.client.chat.completions.create(**params) as stream:
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        params = self._build_params(request)
        params["stream"] = True

        async with await self.async_client.chat.completions.create(**params) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

    def _build_params(self, request: LLMRequest) -> dict:
        params = {
            "model": request.model or self.model,
            "messages": [m.to_dict() for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
        }
        if request.stop_sequences:
            params["stop"] = request.stop_sequences
        if request.response_format:
            params["response_format"] = request.response_format
        return params


# ─── Anthropic Client ─────────────────────────────────────────────────────────

class AnthropicClient(BaseLLMClient):
    """
    Anthropic Claude API client.
    Supports Claude 3 Opus, Sonnet, and Haiku.
    """

    def __init__(
        self,
        model: str = "claude-3-sonnet-20240229",
        api_key: Optional[str] = None,
    ):
        super().__init__(model)
        import anthropic

        self.client = anthropic.Anthropic(
            api_key=api_key or settings.anthropic_api_key
        )
        self.async_client = anthropic.AsyncAnthropic(
            api_key=api_key or settings.anthropic_api_key
        )
        logger.info("Anthropic client initialized", model=model)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=20),
    )
    def complete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()

        system_prompt, messages = self._split_messages(request.messages)

        response = self.client.messages.create(
            model=request.model or self.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=system_prompt,
            messages=messages,
        )

        latency_ms = (time.time() - start_time) * 1000
        content = response.content[0].text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens

        llm_response = LLMResponse(
            content=content,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=response.stop_reason or "stop",
            latency_ms=latency_ms,
            cost_usd=calculate_cost(response.model, prompt_tokens, completion_tokens),
        )

        self._track_usage(llm_response)
        return llm_response

    async def acomplete(self, request: LLMRequest) -> LLMResponse:
        start_time = time.time()
        system_prompt, messages = self._split_messages(request.messages)

        response = await self.async_client.messages.create(
            model=request.model or self.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=system_prompt,
            messages=messages,
        )

        latency_ms = (time.time() - start_time) * 1000
        content = response.content[0].text
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens

        llm_response = LLMResponse(
            content=content,
            model=response.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            finish_reason=response.stop_reason or "stop",
            latency_ms=latency_ms,
            cost_usd=calculate_cost(response.model, prompt_tokens, completion_tokens),
        )
        self._track_usage(llm_response)
        return llm_response

    def stream(self, request: LLMRequest) -> Iterator[str]:
        system_prompt, messages = self._split_messages(request.messages)

        with self.client.messages.stream(
            model=request.model or self.model,
            max_tokens=request.max_tokens,
            system=system_prompt,
            messages=messages,
        ) as stream:
            for text in stream.text_stream:
                yield text

    async def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        system_prompt, messages = self._split_messages(request.messages)

        async with self.async_client.messages.stream(
            model=request.model or self.model,
            max_tokens=request.max_tokens,
            system=system_prompt,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def _split_messages(
        self, messages: list[Message]
    ) -> tuple[str, list[dict]]:
        """
        Anthropic requires system prompt separate from messages.
        """
        system_parts = []
        conversation = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_parts.append(msg.content)
            else:
                conversation.append(msg.to_dict())

        return "\n\n".join(system_parts), conversation


# ─── LLM Client Factory ───────────────────────────────────────────────────────

class LLMClientFactory:
    """Factory for creating LLM clients."""

    @staticmethod
    def create(
        provider: LLMProvider = LLMProvider.OPENAI,
        model: Optional[str] = None,
        **kwargs,
    ) -> BaseLLMClient:

        if provider == LLMProvider.OPENAI:
            return OpenAIClient(
                model=model or settings.chat_model,
                **kwargs,
            )
        elif provider == LLMProvider.ANTHROPIC:
            return AnthropicClient(
                model=model or "claude-3-sonnet-20240229",
                **kwargs,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    @staticmethod
    def create_default() -> BaseLLMClient:
        return LLMClientFactory.create(provider=settings.llm_provider)