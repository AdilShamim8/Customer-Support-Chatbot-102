"""
Comprehensive Prompt Engineering module.
Implements:
  - Zero-shot prompting
  - Few-shot prompting
  - Chain-of-thought (CoT) prompting
  - Role-specific prompting
  - User-context prompting
  - RAG-specific prompt construction
  - Context window management
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from string import Template
from typing import Any, Optional

import structlog
import tiktoken

from configs.settings import settings
from src.generation.llm_client import Message, MessageRole
from src.retrieval.retriever import RetrievalResult

logger = structlog.get_logger(__name__)


# ─── Prompt Strategy Enum ─────────────────────────────────────────────────────

class PromptStrategy(str, Enum):
    ZERO_SHOT = "zero_shot"
    FEW_SHOT = "few_shot"
    CHAIN_OF_THOUGHT = "chain_of_thought"
    ROLE_SPECIFIC = "role_specific"
    RAG_STANDARD = "rag_standard"
    RAG_WITH_COT = "rag_with_cot"


# ─── Few-Shot Example ─────────────────────────────────────────────────────────

@dataclass
class FewShotExample:
    """A single few-shot demonstration example."""
    user_input: str
    context: str
    assistant_output: str
    explanation: Optional[str] = None   # For CoT examples

    def to_messages(self, include_context: bool = True) -> list[Message]:
        if include_context and self.context:
            user_content = (
                f"Context:\n{self.context}\n\n"
                f"Question: {self.user_input}"
            )
        else:
            user_content = self.user_input

        messages = [
            Message(role=MessageRole.USER, content=user_content),
            Message(role=MessageRole.ASSISTANT, content=self.assistant_output),
        ]
        return messages


# ─── Customer Support Few-Shot Examples ───────────────────────────────────────

CUSTOMER_SUPPORT_EXAMPLES = [
    FewShotExample(
        user_input="How do I reset my password?",
        context=(
            "[Source 1: Account Management Guide]\n"
            "To reset your password, visit the login page and click 'Forgot Password'. "
            "Enter your registered email address. You will receive a reset link within "
            "5 minutes. The link expires after 24 hours."
        ),
        assistant_output=(
            "To reset your password, follow these steps:\n\n"
            "1. Go to the login page\n"
            "2. Click **'Forgot Password'**\n"
            "3. Enter your registered email address\n"
            "4. Check your inbox for the reset link (arrives within 5 minutes)\n"
            "5. Click the link and set your new password\n\n"
            "⚠️ Note: The reset link expires after 24 hours. "
            "If you don't receive the email, check your spam folder.\n\n"
            "Is there anything else I can help you with?"
        ),
    ),
    FewShotExample(
        user_input="I was charged twice for my subscription",
        context=(
            "[Source 1: Billing Policy]\n"
            "Duplicate charges are investigated within 3-5 business days. "
            "Refunds are processed to the original payment method within 7-10 business days. "
            "Customers should provide transaction IDs for faster resolution."
        ),
        assistant_output=(
            "I'm sorry to hear you were charged twice — that's definitely something "
            "we need to fix right away.\n\n"
            "Here's what will happen:\n\n"
            "1. **Investigation**: Our billing team will review the duplicate charge "
            "within **3-5 business days**\n"
            "2. **Refund**: Once confirmed, the refund will be returned to your "
            "original payment method within **7-10 business days**\n\n"
            "To speed things up, could you please provide:\n"
            "- Your **transaction IDs** for both charges\n"
            "- The **date** the charges occurred\n\n"
            "I'll escalate this to our billing team immediately. "
            "Is there anything else I can help you with?"
        ),
    ),
    FewShotExample(
        user_input="What is your return policy?",
        context=(
            "[Source 1: Return & Refund Policy]\n"
            "Items can be returned within 30 days of purchase. "
            "Items must be unused and in original packaging. "
            "Digital products are non-refundable. "
            "Return shipping is free for defective items."
        ),
        assistant_output=(
            "Here's a summary of our return policy:\n\n"
            "**✅ What you can return:**\n"
            "- Physical items within **30 days** of purchase\n"
            "- Items must be unused and in **original packaging**\n\n"
            "**❌ What cannot be returned:**\n"
            "- Digital products (non-refundable)\n\n"
            "**📦 Shipping:**\n"
            "- Return shipping is **free** for defective items\n"
            "- Standard returns may have shipping costs\n\n"
            "Would you like help starting a return? "
            "If so, please share your order number and I'll guide you through the process."
        ),
    ),
]

COT_EXAMPLES = [
    FewShotExample(
        user_input="My order says delivered but I haven't received it",
        context=(
            "[Source 1: Delivery Policy]\n"
            "If tracking shows delivered but item not received, wait 24 hours as "
            "carriers sometimes update tracking early. File a claim after 24 hours. "
            "Claims must be filed within 7 days of delivery date."
        ),
        assistant_output=(
            "Let me think through this step by step:\n\n"
            "**Step 1: Verify the situation**\n"
            "The tracking shows 'delivered' but the package hasn't arrived. "
            "This can happen for a few reasons:\n"
            "- Carrier updated tracking prematurely\n"
            "- Package delivered to wrong address or neighbor\n"
            "- Package left in an unexpected location (porch, mailroom)\n\n"
            "**Step 2: Immediate actions**\n"
            "Since it just showed delivered, I recommend:\n"
            "- Check all entry points to your home\n"
            "- Ask neighbors if they received it by mistake\n"
            "- Wait up to 24 hours (carriers sometimes update early)\n\n"
            "**Step 3: If still missing after 24 hours**\n"
            "You'll need to file a claim — and importantly, you have a **7-day window** "
            "from the delivery date to do so. I can help you start that process.\n\n"
            "What would you like to do next?"
        ),
        explanation=(
            "This example shows CoT: identifying root causes, "
            "providing ordered action steps, and setting expectations."
        ),
    ),
]


# ─── System Prompt Templates ──────────────────────────────────────────────────

SYSTEM_PROMPTS = {

    "base_support": """\
You are a helpful, professional, and empathetic customer support assistant for {company_name}.

Your responsibilities:
- Answer customer questions accurately using the provided context
- Be warm, professional, and solution-oriented
- Acknowledge customer frustrations with empathy
- Provide clear, actionable steps
- Escalate appropriately when you cannot resolve an issue

Guidelines:
- Only use information from the provided context to answer questions
- If the context doesn't contain the answer, say so clearly and offer to escalate
- Never make up information or policies
- Keep responses concise but complete
- Use bullet points and formatting for clarity
- Always end with a helpful follow-up offer

Current date: {current_date}
Company: {company_name}
Support tier: {support_tier}
""",

    "technical_support": """\
You are an expert technical support specialist for {company_name}.

Your expertise includes:
- Troubleshooting software and hardware issues
- Walking customers through technical processes step by step
- Identifying root causes systematically
- Providing workarounds when primary solutions fail

Technical Guidelines:
- Use precise technical language appropriate to the customer's expertise level
- Provide numbered steps for procedures
- Include expected outcomes for each step
- Mention prerequisites before starting troubleshooting
- Always ask for error messages and system information when relevant

Customer technical level: {user_technical_level}
Product: {product_name}
""",

    "billing_support": """\
You are a billing specialist for {company_name}.

Your role:
- Resolve billing inquiries, disputes, and refund requests
- Explain charges and subscription details clearly
- Process refunds and adjustments within policy
- Escalate complex billing disputes to finance team

Billing Guidelines:
- Always verify the customer's concern before proposing solutions
- Be clear about timelines for refunds and investigations
- Never promise refunds outside of policy
- Collect transaction IDs and dates for investigations
- Treat all financial matters with urgency and sensitivity

Refund policy window: {refund_window_days} days
Currency: {currency}
""",

    "zero_shot_rag": """\
You are a helpful customer support assistant. Answer the customer's question \
using ONLY the information provided in the context below. 

If the context does not contain enough information to answer the question, \
say "I don't have enough information to answer that" and offer to connect \
them with a human agent.

Do not make up any information.
""",

    "chain_of_thought_rag": """\
You are a helpful customer support assistant. When answering questions:

1. THINK: Analyze what the customer is asking
2. SEARCH: Identify the relevant information from context  
3. REASON: Consider what the best answer is
4. RESPOND: Give a clear, structured answer

Show your reasoning process clearly before giving the final answer.
Use "Let me think through this..." to begin your reasoning.
""",
}


# ─── Prompt Builder ───────────────────────────────────────────────────────────

@dataclass
class PromptConfig:
    """Configuration for prompt building."""
    strategy: PromptStrategy = PromptStrategy.RAG_STANDARD
    company_name: str = "AcmeCorp Support"
    support_tier: str = "standard"
    user_technical_level: str = "beginner"
    product_name: str = "our product"
    refund_window_days: int = 30
    currency: str = "USD"
    include_few_shot: bool = True
    num_few_shot_examples: int = 2
    include_cot: bool = False
    max_context_tokens: int = settings.max_context_tokens
    user_metadata: dict[str, Any] = field(default_factory=dict)


class PromptEngine:
    """
    Comprehensive prompt engineering engine.

    Handles all prompt strategies:
    - Zero-shot: Direct answer from context
    - Few-shot: With demonstration examples
    - Chain-of-thought: Step-by-step reasoning
    - Role-specific: Persona-based prompting
    - RAG-specific: Context-grounded answering
    """

    def __init__(self, config: Optional[PromptConfig] = None):
        self.config = config or PromptConfig()
        self.token_counter = self._init_token_counter()

    def _init_token_counter(self):
        try:
            return tiktoken.encoding_for_model("gpt-4")
        except Exception:
            return tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.token_counter.encode(text))

    # ── Main Entry Point ─────────────────────────────────────────────────────

    def build_rag_prompt(
        self,
        user_query: str,
        retrieval_result: RetrievalResult,
        conversation_history: Optional[list[Message]] = None,
        user_context: Optional[dict] = None,
    ) -> list[Message]:
        """
        Build a complete RAG prompt with all configured strategies applied.

        Args:
            user_query: The user's question
            retrieval_result: Retrieved context from the RAG pipeline
            conversation_history: Prior conversation messages
            user_context: Optional user metadata (tier, history, etc.)

        Returns:
            List of messages ready to send to the LLM
        """
        messages = []

        # Step 1: Build system prompt
        system_prompt = self._build_system_prompt(user_context)
        messages.append(Message(role=MessageRole.SYSTEM, content=system_prompt))

        # Step 2: Add few-shot examples (if configured)
        if self.config.include_few_shot:
            few_shot_messages = self._build_few_shot_messages(
                user_query,
                use_cot=self.config.include_cot,
            )
            messages.extend(few_shot_messages)

        # Step 3: Add conversation history
        if conversation_history:
            # Trim history to fit token budget
            trimmed_history = self._trim_history(
                conversation_history,
                current_tokens=self._count_messages_tokens(messages),
            )
            messages.extend(trimmed_history)

        # Step 4: Build the final user message with context
        user_message = self._build_user_message(
            query=user_query,
            retrieval_result=retrieval_result,
            user_context=user_context,
        )
        messages.append(Message(role=MessageRole.USER, content=user_message))

        total_tokens = self._count_messages_tokens(messages)
        logger.debug(
            "Prompt built",
            strategy=self.config.strategy.value,
            message_count=len(messages),
            total_tokens=total_tokens,
        )

        return messages

    # ── System Prompt Builder ─────────────────────────────────────────────────

    def _build_system_prompt(
        self, user_context: Optional[dict] = None
    ) -> str:
        """Build a role-specific system prompt."""
        import datetime

        strategy = self.config.strategy
        ctx = user_context or {}

        # Select base template
        if strategy == PromptStrategy.ZERO_SHOT:
            template = SYSTEM_PROMPTS["zero_shot_rag"]

        elif strategy == PromptStrategy.CHAIN_OF_THOUGHT:
            template = SYSTEM_PROMPTS["chain_of_thought_rag"]

        elif strategy == PromptStrategy.ROLE_SPECIFIC:
            # Select role based on user context or config
            role = ctx.get("support_role", "base_support")
            template = SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["base_support"])

        else:
            # Default: base support agent
            template = SYSTEM_PROMPTS["base_support"]

        # Fill template variables
        variables = {
            "company_name": self.config.company_name,
            "current_date": datetime.date.today().isoformat(),
            "support_tier": ctx.get("support_tier", self.config.support_tier),
            "user_technical_level": ctx.get(
                "technical_level", self.config.user_technical_level
            ),
            "product_name": ctx.get("product_name", self.config.product_name),
            "refund_window_days": self.config.refund_window_days,
            "currency": self.config.currency,
        }

        # Safe substitution (won't raise on missing keys)
        try:
            prompt = template.format(**variables)
        except KeyError:
            prompt = template

        # Add user-specific context if available
        if ctx:
            user_context_section = self._build_user_context_section(ctx)
            if user_context_section:
                prompt += f"\n\n{user_context_section}"

        return prompt

    def _build_user_context_section(self, user_context: dict) -> str:
        """Build a user-specific context section for the system prompt."""
        parts = ["## Customer Context"]

        if user_context.get("customer_name"):
            parts.append(f"- Name: {user_context['customer_name']}")
        if user_context.get("account_tier"):
            parts.append(f"- Account Tier: {user_context['account_tier']}")
        if user_context.get("customer_since"):
            parts.append(f"- Customer Since: {user_context['customer_since']}")
        if user_context.get("open_tickets"):
            parts.append(f"- Open Tickets: {user_context['open_tickets']}")
        if user_context.get("recent_purchases"):
            parts.append(
                f"- Recent Purchases: {', '.join(user_context['recent_purchases'])}"
            )
        if user_context.get("preferred_language"):
            parts.append(
                f"- Preferred Language: {user_context['preferred_language']}"
            )
        if user_context.get("special_notes"):
            parts.append(f"- Notes: {user_context['special_notes']}")

        return "\n".join(parts) if len(parts) > 1 else ""

    # ── Few-Shot Builder ──────────────────────────────────────────────────────

    def _build_few_shot_messages(
        self,
        current_query: str,
        use_cot: bool = False,
    ) -> list[Message]:
        """
        Select and build few-shot demonstration messages.
        Selects the most relevant examples for the current query.
        """
        examples_pool = COT_EXAMPLES if use_cot else CUSTOMER_SUPPORT_EXAMPLES
        n = min(self.config.num_few_shot_examples, len(examples_pool))

        # Select most relevant examples (simple keyword matching)
        selected = self._select_relevant_examples(
            query=current_query,
            examples=examples_pool,
            n=n,
        )

        few_shot_messages = []
        for example in selected:
            few_shot_messages.extend(example.to_messages(include_context=True))

        return few_shot_messages

    def _select_relevant_examples(
        self,
        query: str,
        examples: list[FewShotExample],
        n: int,
    ) -> list[FewShotExample]:
        """
        Select the n most relevant examples for the query.
        Uses simple token overlap scoring.
        In production, use embedding-based selection.
        """
        if n >= len(examples):
            return examples[:n]

        query_tokens = set(query.lower().split())

        scored = []
        for example in examples:
            example_tokens = set(example.user_input.lower().split())
            overlap = len(query_tokens & example_tokens)
            scored.append((overlap, example))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:n]]

    # ── User Message Builder ──────────────────────────────────────────────────

    def _build_user_message(
        self,
        query: str,
        retrieval_result: RetrievalResult,
        user_context: Optional[dict] = None,
    ) -> str:
        """
        Build the final user message combining context and query.
        Manages token budget to fit within context window.
        """
        strategy = self.config.strategy

        # Build context section
        context_section = self._build_context_section(retrieval_result)

        # Build query section
        if strategy == PromptStrategy.CHAIN_OF_THOUGHT:
            query_section = self._build_cot_query(query)
        else:
            query_section = self._build_standard_query(query, user_context)

        # Combine
        if context_section:
            message = f"{context_section}\n\n{query_section}"
        else:
            message = query_section

        return message

    def _build_context_section(self, retrieval_result: RetrievalResult) -> str:
        """Build the context section with token budget management."""
        if not retrieval_result.chunks:
            return (
                "**Context:** No relevant documentation found. "
                "Please answer based on general knowledge or escalate."
            )

        # Calculate available tokens for context
        header_tokens = 50
        query_tokens = 200
        reserved = header_tokens + query_tokens + 200  # Buffer
        available_tokens = self.config.max_context_tokens - reserved

        context_parts = ["## Relevant Documentation\n"]
        used_tokens = self.count_tokens(context_parts[0])

        for i, chunk in enumerate(retrieval_result.chunks, 1):
            source = chunk.metadata.get("title", f"Document {chunk.doc_id[:8]}")
            section = chunk.metadata.get("section_title", "")
            score = chunk.score

            header = f"### Source {i}: {source}"
            if section:
                header += f" — {section}"
            header += f" (relevance: {score:.2f})"

            chunk_text = f"{header}\n{chunk.content}"
            chunk_tokens = self.count_tokens(chunk_text)

            if used_tokens + chunk_tokens > available_tokens:
                # Truncate this chunk to fit
                remaining = available_tokens - used_tokens
                if remaining < 100:
                    break
                truncated = self._truncate_to_tokens(chunk.content, remaining - 50)
                chunk_text = f"{header}\n{truncated}... [truncated]"

            context_parts.append(chunk_text)
            used_tokens += self.count_tokens(chunk_text)

            if used_tokens >= available_tokens:
                break

        return "\n\n".join(context_parts)

    def _build_standard_query(
        self,
        query: str,
        user_context: Optional[dict] = None,
    ) -> str:
        """Build a standard query section."""
        parts = ["## Customer Question"]

        if user_context and user_context.get("customer_name"):
            parts.append(
                f"Customer: {user_context['customer_name']} "
                f"({user_context.get('account_tier', 'standard')} tier)"
            )

        parts.append(f"\n{query}")
        parts.append(
            "\n## Your Response\n"
            "Answer based strictly on the provided documentation. "
            "Be helpful, empathetic, and actionable."
        )

        return "\n".join(parts)

    def _build_cot_query(self, query: str) -> str:
        """Build a chain-of-thought query section."""
        return (
            f"## Customer Question\n{query}\n\n"
            "## Instructions\n"
            "Think through this step by step:\n"
            "1. What is the customer's core problem?\n"
            "2. What does the context say about this?\n"
            "3. What are the possible solutions?\n"
            "4. What is the best response?\n\n"
            "Start with 'Let me think through this...'"
        )

    # ── Utility Methods ───────────────────────────────────────────────────────

    def _trim_history(
        self,
        history: list[Message],
        current_tokens: int,
        max_history_tokens: int = 1000,
    ) -> list[Message]:
        """
        Trim conversation history to fit within token budget.
        Keeps most recent messages, always preserves system context.
        """
        available = max_history_tokens
        trimmed = []

        # Work backwards through history
        for message in reversed(history):
            msg_tokens = self.count_tokens(message.content)
            if available - msg_tokens < 0:
                break
            trimmed.insert(0, message)
            available -= msg_tokens

        return trimmed

    def _count_messages_tokens(self, messages: list[Message]) -> int:
        total = 0
        for msg in messages:
            total += self.count_tokens(msg.content)
            total += 4  # Message overhead tokens
        return total

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        tokens = self.token_counter.encode(text)
        if len(tokens) <= max_tokens:
            return text
        return self.token_counter.decode(tokens[:max_tokens])

    # ── Specialized Prompt Builders ───────────────────────────────────────────

    def build_standalone_question_prompt(
        self,
        question: str,
        conversation_history: list[Message],
    ) -> list[Message]:
        """
        Build a prompt to rephrase a follow-up question as standalone.
        Used to make conversational questions self-contained for retrieval.
        """
        history_text = "\n".join(
            f"{m.role.value}: {m.content}"
            for m in conversation_history[-6:]  # Last 3 turns
        )

        system = (
            "Given a conversation history and a follow-up question, "
            "rephrase the follow-up question to be completely self-contained "
            "so it can be understood without the conversation history. "
            "Return ONLY the rephrased question, nothing else."
        )

        user_content = (
            f"Conversation History:\n{history_text}\n\n"
            f"Follow-up Question: {question}\n\n"
            "Standalone Question:"
        )

        return [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user_content),
        ]

    def build_query_expansion_prompt(self, query: str) -> list[Message]:
        """Build a prompt to generate multiple search queries from one question."""
        system = (
            "You are a search query optimizer. Generate 3 different search queries "
            "that capture different aspects of the user's question. "
            "These will be used to search a knowledge base. "
            "Return a JSON array of strings. Example: "
            '["query 1", "query 2", "query 3"]'
        )

        user_content = (
            f"Original question: {query}\n\n"
            "Generate 3 search queries (JSON array):"
        )

        return [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user_content),
        ]

    def build_hallucination_check_prompt(
        self,
        question: str,
        context: str,
        answer: str,
    ) -> list[Message]:
        """Build a prompt to check if an answer is grounded in context."""
        system = (
            "You are a factual accuracy checker. "
            "Determine if the given answer is fully supported by the provided context. "
            "Respond with JSON: "
            '{"grounded": true/false, "confidence": 0.0-1.0, "issues": ["..."]}'
        )

        user_content = (
            f"Context:\n{context}\n\n"
            f"Question: {question}\n\n"
            f"Answer: {answer}\n\n"
            "Is this answer fully grounded in the context?"
        )

        return [
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user_content),
        ]