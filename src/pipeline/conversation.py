"""
Conversation state management with Redis persistence.
Handles multi-turn conversation tracking, session management,
and conversation history trimming.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import structlog

from configs.settings import settings
from src.generation.llm_client import Message, MessageRole

logger = structlog.get_logger(__name__)


@dataclass
class Conversation:
    """Represents a customer support conversation session."""
    conversation_id: str
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat()
    )
    messages: list[dict] = field(default_factory=list)
    user_context: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        self.messages.append({
            "role": message.role.value,
            "content": message.content,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.updated_at = datetime.utcnow().isoformat()

    def get_messages(
        self,
        max_turns: int = settings.max_conversation_turns,
    ) -> list[Message]:
        """Get messages as Message objects, limited to recent turns."""
        # Each turn = 1 user + 1 assistant message
        # max_turns * 2 = total message limit
        recent = self.messages[-(max_turns * 2):]

        return [
            Message(
                role=MessageRole(m["role"]),
                content=m["content"],
            )
            for m in recent
            if m["role"] in ("user", "assistant")
        ]

    @property
    def turn_count(self) -> int:
        user_msgs = [m for m in self.messages if m["role"] == "user"]
        return len(user_msgs)

    def to_dict(self) -> dict:
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": self.messages,
            "user_context": self.user_context,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        conv = cls(conversation_id=data["conversation_id"])
        conv.created_at = data.get("created_at", conv.created_at)
        conv.updated_at = data.get("updated_at", conv.updated_at)
        conv.messages = data.get("messages", [])
        conv.user_context = data.get("user_context", {})
        conv.metadata = data.get("metadata", {})
        return conv

    @classmethod
    def new(cls, user_context: Optional[dict] = None) -> "Conversation":
        return cls(
            conversation_id=str(uuid.uuid4()),
            user_context=user_context or {},
        )


class ConversationManager:
    """
    Manages conversation persistence.
    Uses Redis for production, in-memory dict for development.
    """

    def __init__(self, use_redis: bool = True):
        self._memory_store: dict[str, Conversation] = {}
        self._redis = None
        self._use_redis = use_redis

        if use_redis:
            try:
                import redis
                self._redis = redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                )
                self._redis.ping()
                logger.info("ConversationManager using Redis")
            except Exception as e:
                logger.warning(
                    "Redis unavailable, using in-memory store",
                    error=str(e),
                )
                self._redis = None

    def get_or_create(
        self,
        conversation_id: str,
        user_context: Optional[dict] = None,
    ) -> Conversation:
        existing = self.get(conversation_id)
        if existing:
            return existing

        new_conv = Conversation(
            conversation_id=conversation_id,
            user_context=user_context or {},
        )
        self.save(new_conv)
        return new_conv

    def get(self, conversation_id: str) -> Optional[Conversation]:
        if self._redis:
            try:
                key = self._redis_key(conversation_id)
                data = self._redis.get(key)
                if data:
                    return Conversation.from_dict(json.loads(data))
            except Exception as e:
                logger.error("Redis get failed", error=str(e))

        return self._memory_store.get(conversation_id)

    def save(self, conversation: Conversation) -> None:
        data = json.dumps(conversation.to_dict(), ensure_ascii=False)

        if self._redis:
            try:
                key = self._redis_key(conversation.conversation_id)
                self._redis.setex(
                    key,
                    settings.conversation_ttl_seconds,
                    data,
                )
                return
            except Exception as e:
                logger.error("Redis save failed", error=str(e))

        self._memory_store[conversation.conversation_id] = conversation

    def delete(self, conversation_id: str) -> None:
        if self._redis:
            try:
                self._redis.delete(self._redis_key(conversation_id))
            except Exception as e:
                logger.error("Redis delete failed", error=str(e))

        self._memory_store.pop(conversation_id, None)

    def create_new(
        self, user_context: Optional[dict] = None
    ) -> Conversation:
        conv = Conversation.new(user_context=user_context)
        self.save(conv)
        return conv

    def _redis_key(self, conversation_id: str) -> str:
        return f"conversation:{conversation_id}"