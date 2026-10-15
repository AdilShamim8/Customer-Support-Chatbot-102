"""
RAFT: Retrieval Augmented Fine-Tuning
Implementation of the RAFT training data generation technique.

RAFT trains LLMs to:
1. Identify relevant documents from a mix of relevant + distractor documents
2. Generate answers citing specific sources using special tokens
3. Ignore misleading distractor documents

Paper: "RAFT: Adapting Language Model to Domain Specific RAG"
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog

from src.generation.llm_client import BaseLLMClient, LLMClientFactory, Message, MessageRole, LLMRequest
from src.indexing.vector_store import SearchResult
from src.retrieval.retriever import RetrievalResult

logger = structlog.get_logger(__name__)


# ─── RAFT Data Structures ─────────────────────────────────────────────────────

@dataclass
class RAFTExample:
    """
    A single RAFT training example.

    Structure:
    - question: The user question
    - context: Mix of oracle (relevant) + distractor documents
    - chain_of_thought: Step-by-step reasoning citing sources
    - answer: Final answer with citations using ##begin_quote## markers
    - oracle_doc_ids: IDs of the truly relevant documents
    - distractor_doc_ids: IDs of the misleading documents
    """
    question: str
    context: list[dict]          # List of {doc_id, content, is_oracle}
    chain_of_thought: str
    answer: str
    oracle_doc_ids: list[str]
    distractor_doc_ids: list[str]
    metadata: dict[str, str] = field(default_factory=dict)

    def to_training_format(self) -> dict:
        """Convert to the training data format for fine-tuning."""
        context_text = self._format_context()

        return {
            "instruction": self._build_instruction(context_text),
            "input": self.question,
            "output": f"{self.chain_of_thought}\n\nFinal Answer: {self.answer}",
            "metadata": {
                "oracle_docs": self.oracle_doc_ids,
                "distractor_docs": self.distractor_doc_ids,
                **self.metadata,
            }
        }

    def to_messages(self) -> list[dict]:
        """Convert to OpenAI fine-tuning messages format."""
        context_text = self._format_context()
        instruction = self._build_instruction(context_text)

        return {
            "messages": [
                {
                    "role": "system",
                    "content": instruction,
                },
                {
                    "role": "user",
                    "content": self.question,
                },
                {
                    "role": "assistant",
                    "content": (
                        f"{self.chain_of_thought}\n\n"
                        f"Final Answer: {self.answer}"
                    ),
                },
            ]
        }

    def _format_context(self) -> str:
        parts = []
        for i, doc in enumerate(self.context, 1):
            parts.append(
                f"Document [{i}] (ID: {doc['doc_id']}):\n{doc['content']}"
            )
        return "\n\n".join(parts)

    def _build_instruction(self, context_text: str) -> str:
        return (
            "You are a helpful customer support assistant. "
            "Answer the question using ONLY the provided documents. "
            "When quoting from a document, use ##begin_quote## and ##end_quote## markers. "
            "Explicitly state which document IDs support your answer.\n\n"
            f"Available Documents:\n{context_text}\n\n"
            "Think step by step, identify relevant documents, "
            "and provide a well-cited answer."
        )


@dataclass
class RAFTDataset:
    """Collection of RAFT training examples."""
    examples: list[RAFTExample] = field(default_factory=list)
    split_ratios: dict = field(default_factory=lambda: {
        "train": 0.8, "val": 0.1, "test": 0.1
    })

    def add(self, example: RAFTExample) -> None:
        self.examples.append(example)

    def __len__(self) -> int:
        return len(self.examples)

    def to_jsonl(self, format_type: str = "openai") -> list[str]:
        """Convert dataset to JSONL format."""
        lines = []
        for example in self.examples:
            if format_type == "openai":
                record = example.to_messages()
            else:
                record = example.to_training_format()
            lines.append(json.dumps(record, ensure_ascii=False))
        return lines

    def save(
        self,
        output_dir: str,
        format_type: str = "openai",
    ) -> dict[str, Path]:
        """Save dataset split into train/val/test JSONL files."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Shuffle and split
        examples = self.examples.copy()
        random.shuffle(examples)

        n = len(examples)
        n_train = int(n * self.split_ratios["train"])
        n_val = int(n * self.split_ratios["val"])

        splits = {
            "train": examples[:n_train],
            "val": examples[n_train:n_train + n_val],
            "test": examples[n_train + n_val:],
        }

        saved_paths = {}
        for split_name, split_examples in splits.items():
            file_path = output_path / f"{split_name}.jsonl"
            with open(file_path, "w", encoding="utf-8") as f:
                for example in split_examples:
                    if format_type == "openai":
                        record = example.to_messages()
                    else:
                        record = example.to_training_format()
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")

            saved_paths[split_name] = file_path
            logger.info(
                "RAFT split saved",
                split=split_name,
                examples=len(split_examples),
                path=str(file_path),
            )

        return saved_paths

    def get_stats(self) -> dict:
        return {
            "total_examples": len(self.examples),
            "avg_oracle_docs": (
                sum(len(e.oracle_doc_ids) for e in self.examples) / len(self.examples)
                if self.examples else 0
            ),
            "avg_distractor_docs": (
                sum(len(e.distractor_doc_ids) for e in self.examples) / len(self.examples)
                if self.examples else 0
            ),
        }


# ─── RAFT Data Generator ──────────────────────────────────────────────────────

class RAFTDataGenerator:
    """
    Generates RAFT training data from a document corpus.

    Algorithm:
    1. For each document chunk (oracle), generate Q&A pairs
    2. Sample distractor documents from the corpus
    3. Shuffle oracle + distractors in context
    4. Generate chain-of-thought answer citing oracle docs
    5. In p% of cases, exclude oracle (trains model to say "I don't know")
    """

    QUESTION_GENERATION_PROMPT = """\
You are generating training data for a customer support AI.
Given the following documentation, generate {num_questions} distinct, \
realistic customer support questions that can be answered using this content.

Return a JSON array of strings.

Documentation:
{content}

Generate exactly {num_questions} questions as a JSON array:"""

    COT_ANSWER_PROMPT = """\
You are a helpful customer support assistant. 
Answer the customer's question using ONLY the provided documents.

Rules:
- Use ##begin_quote## text ##end_quote## to quote directly from documents
- Cite the Document ID (e.g., "According to Document [2]...")
- Think step by step
- If documents don't contain the answer, say "The provided documents do not \
contain enough information to answer this question."

Documents:
{context}

Question: {question}

Answer (with citations):"""

    def __init__(
        self,
        llm_client: Optional[BaseLLMClient] = None,
        num_distractors: int = 3,
        oracle_probability: float = 0.8,
        questions_per_chunk: int = 3,
    ):
        """
        Args:
            llm_client: LLM for generating Q&A pairs
            num_distractors: Number of distractor docs per example
            oracle_probability: P(oracle doc included) — 1-P = "abstain" training
            questions_per_chunk: Questions generated per document chunk
        """
        self.llm = llm_client or LLMClientFactory.create_default()
        self.num_distractors = num_distractors
        self.oracle_probability = oracle_probability
        self.questions_per_chunk = questions_per_chunk

    def generate_dataset(
        self,
        chunks: list[SearchResult],
        max_examples: Optional[int] = None,
    ) -> RAFTDataset:
        """
        Generate a full RAFT dataset from document chunks.

        Args:
            chunks: All document chunks from the corpus
            max_examples: Optional limit on examples generated

        Returns:
            RAFTDataset ready for fine-tuning
        """
        dataset = RAFTDataset()
        all_chunks = chunks.copy()

        logger.info(
            "Starting RAFT dataset generation",
            total_chunks=len(chunks),
            num_distractors=self.num_distractors,
            oracle_probability=self.oracle_probability,
        )

        for i, oracle_chunk in enumerate(all_chunks):
            if max_examples and len(dataset) >= max_examples:
                break

            try:
                # Generate questions for this oracle chunk
                questions = self._generate_questions(oracle_chunk)

                for question in questions:
                    if max_examples and len(dataset) >= max_examples:
                        break

                    # Decide whether to include oracle (RAFT trick)
                    include_oracle = random.random() < self.oracle_probability

                    # Sample distractors (chunks from other documents)
                    distractors = self._sample_distractors(
                        oracle_chunk=oracle_chunk,
                        all_chunks=all_chunks,
                        n=self.num_distractors,
                    )

                    # Build context (oracle + distractors)
                    context_docs, oracle_ids, distractor_ids = self._build_context(
                        oracle_chunk=oracle_chunk,
                        distractors=distractors,
                        include_oracle=include_oracle,
                    )

                    # Generate CoT answer
                    answer, cot = self._generate_answer(
                        question=question,
                        context_docs=context_docs,
                        include_oracle=include_oracle,
                    )

                    example = RAFTExample(
                        question=question,
                        context=context_docs,
                        chain_of_thought=cot,
                        answer=answer,
                        oracle_doc_ids=oracle_ids,
                        distractor_doc_ids=distractor_ids,
                        metadata={
                            "oracle_chunk_id": oracle_chunk.chunk_id,
                            "include_oracle": str(include_oracle),
                        },
                    )

                    dataset.add(example)

                logger.debug(
                    "RAFT examples generated for chunk",
                    chunk_id=oracle_chunk.chunk_id,
                    examples_so_far=len(dataset),
                )

            except Exception as e:
                logger.error(
                    "RAFT generation failed for chunk",
                    chunk_id=oracle_chunk.chunk_id,
                    error=str(e),
                )
                continue

        logger.info(
            "RAFT dataset generation complete",
            total_examples=len(dataset),
            stats=dataset.get_stats(),
        )

        return dataset

    def _generate_questions(self, chunk: SearchResult) -> list[str]:
        """Generate realistic customer questions from a document chunk."""
        prompt = self.QUESTION_GENERATION_PROMPT.format(
            num_questions=self.questions_per_chunk,
            content=chunk.content[:2000],   # Limit context for question gen
        )

        response = self.llm.chat(
            user_message=prompt,
            temperature=0.8,    # Higher temp for diverse questions
            max_tokens=500,
            response_format={"type": "json_object"},
        )

        try:
            # Parse JSON array of questions
            content = response.content.strip()
            # Handle both array and object responses
            if content.startswith("["):
                questions = json.loads(content)
            else:
                parsed = json.loads(content)
                questions = parsed.get(
                    "questions",
                    list(parsed.values())[0] if parsed else []
                )

            return [q for q in questions if isinstance(q, str) and q.strip()]

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(
                "Failed to parse questions JSON",
                error=str(e),
                content=response.content[:200],
            )
            # Fallback: extract from text
            return self._extract_questions_from_text(response.content)

    def _extract_questions_from_text(self, text: str) -> list[str]:
        """Fallback question extraction from unstructured text."""
        import re
        questions = re.findall(r'["\']([^"\']+\?)["\']', text)
        return questions[:self.questions_per_chunk]

    def _sample_distractors(
        self,
        oracle_chunk: SearchResult,
        all_chunks: list[SearchResult],
        n: int,
    ) -> list[SearchResult]:
        """Sample n distractor chunks from different documents."""
        candidates = [
            c for c in all_chunks
            if c.doc_id != oracle_chunk.doc_id
            and c.chunk_id != oracle_chunk.chunk_id
        ]

        if len(candidates) <= n:
            return candidates

        return random.sample(candidates, n)

    def _build_context(
        self,
        oracle_chunk: SearchResult,
        distractors: list[SearchResult],
        include_oracle: bool,
    ) -> tuple[list[dict], list[str], list[str]]:
        """Build the mixed context with oracle and distractors."""
        docs = []
        oracle_ids = []
        distractor_ids = []

        if include_oracle:
            docs.append({
                "doc_id": oracle_chunk.chunk_id,
                "content": oracle_chunk.content,
                "is_oracle": True,
            })
            oracle_ids.append(oracle_chunk.chunk_id)

        for dist in distractors:
            docs.append({
                "doc_id": dist.chunk_id,
                "content": dist.content,
                "is_oracle": False,
            })
            distractor_ids.append(dist.chunk_id)

        # Shuffle to prevent position bias
        random.shuffle(docs)

        return docs, oracle_ids, distractor_ids

    def _generate_answer(
        self,
        question: str,
        context_docs: list[dict],
        include_oracle: bool,
    ) -> tuple[str, str]:
        """
        Generate a CoT answer with citations.

        Returns:
            (final_answer, chain_of_thought)
        """
        # Format context for the prompt
        context_text = "\n\n".join([
            f"Document [{i+1}] (ID: {doc['doc_id']}):\n{doc['content']}"
            for i, doc in enumerate(context_docs)
        ])

        prompt = self.COT_ANSWER_PROMPT.format(
            context=context_text,
            question=question,
        )

        response = self.llm.chat(
            user_message=prompt,
            temperature=0.0,    # Deterministic for faithfulness
            max_tokens=800,
        )

        full_response = response.content

        # Split CoT from final answer
        if "Final Answer:" in full_response:
            parts = full_response.split("Final Answer:", 1)
            cot = parts[0].strip()
            answer = parts[1].strip()
        else:
            # Treat entire response as answer
            cot = "Based on the provided documents..."
            answer = full_response.strip()

        return answer, cot