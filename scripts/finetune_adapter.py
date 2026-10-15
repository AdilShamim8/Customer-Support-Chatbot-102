#!/usr/bin/env python3
"""
PEFT Fine-Tuning with LoRA for Customer Support.

Supports:
  - LoRA (Low-Rank Adaptation) - parameter-efficient fine-tuning
  - QLoRA - quantized LoRA for memory efficiency
  - Adapter layers
  - Fine-tuning on RAFT-generated datasets

Usage:
    python scripts/finetune_adapter.py \
        --base-model mistralai/Mistral-7B-Instruct-v0.2 \
        --dataset ./data/raft/train.jsonl \
        --output ./models/support-lora \
        --method lora \
        --epochs 3
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from configs.logging_config import setup_logging

logger = structlog.get_logger(__name__)


# ─── LoRA Configuration ───────────────────────────────────────────────────────

def get_lora_config(
    r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
    target_modules: Optional[list[str]] = None,
):
    """
    Create LoRA configuration.

    Args:
        r: Rank of the low-rank matrices. Lower = fewer params, faster.
           Typical: 8, 16, 32, 64
        lora_alpha: Scaling factor. Usually = 2*r
        lora_dropout: Dropout on LoRA layers
        target_modules: Which layers to apply LoRA to
    """
    from peft import LoraConfig, TaskType

    # Default targets for most transformer models
    default_targets = [
        "q_proj", "v_proj",    # Attention query and value projections
        "k_proj", "o_proj",    # Key and output projections
        "gate_proj",           # MLP gate (LLaMA/Mistral)
        "up_proj",             # MLP up projection
        "down_proj",           # MLP down projection
    ]

    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=target_modules or default_targets,
        bias="none",
        inference_mode=False,
    )


def get_qlora_config(r: int = 16):
    """
    QLoRA: Quantized LoRA for memory-efficient fine-tuning.
    Runs 7B models on a single GPU with 16GB VRAM.
    """
    from peft import LoraConfig, TaskType

    return LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=r,
        lora_alpha=r * 2,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        bias="none",
        inference_mode=False,
    )


# ─── Dataset Loading ──────────────────────────────────────────────────────────

def load_training_data(dataset_path: str) -> "datasets.Dataset":
    """Load RAFT-format JSONL training data."""
    from datasets import Dataset

    records = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            # Handle OpenAI messages format from RAFT
            if "messages" in record:
                records.append(record)

    logger.info("Training data loaded", records=len(records))
    return Dataset.from_list(records)


def format_prompt(messages: list[dict], tokenizer) -> str:
    """
    Format messages list into model-specific prompt string.
    Uses tokenizer's chat template if available.
    """
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )
    # Fallback: simple format
    parts = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        parts.append(f"<|{role}|>\n{content}")
    return "\n".join(parts) + "<|END|>"


# ─── Training ─────────────────────────────────────────────────────────────────

def train_lora(
    base_model_name: str,
    dataset_path: str,
    output_dir: str,
    method: str = "lora",
    epochs: int = 3,
    batch_size: int = 4,
    learning_rate: float = 2e-4,
    max_seq_length: int = 2048,
    lora_r: int = 16,
    use_4bit: bool = True,
    gradient_accumulation_steps: int = 4,
):
    """
    Fine-tune a model using LoRA/QLoRA with the TRL SFTTrainer.

    Args:
        base_model_name: HuggingFace model ID or local path
        dataset_path: Path to RAFT JSONL training data
        output_dir: Where to save the fine-tuned adapter
        method: "lora" or "qlora"
        epochs: Number of training epochs
        batch_size: Per-device batch size
        learning_rate: Initial learning rate
        max_seq_length: Maximum sequence length
        lora_r: LoRA rank
        use_4bit: Use 4-bit quantization (QLoRA)
        gradient_accumulation_steps: Steps before optimizer update
    """
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        TrainingArguments,
    )
    from peft import get_peft_model, prepare_model_for_kbit_training
    from trl import SFTTrainer, DataCollatorForCompletionOnlyLM
    from datasets import Dataset

    logger.info(
        "Starting LoRA fine-tuning",
        base_model=base_model_name,
        method=method,
        epochs=epochs,
        lora_r=lora_r,
    )

    # ── Load Tokenizer ─────────────────────────────────────────────────────────
    tokenizer = AutoTokenizer.from_pretrained(
        base_model_name,
        trust_remote_code=True,
        padding_side="right",
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id

    # ── Quantization Config (for QLoRA) ───────────────────────────────────────
    bnb_config = None
    if use_4bit and method == "qlora":
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        logger.info("Using 4-bit quantization (QLoRA)")

    # ── Load Base Model ────────────────────────────────────────────────────────
    logger.info("Loading base model...", model=base_model_name)
    model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if not use_4bit else None,
    )
    model.config.use_cache = False
    model.config.pretraining_tp = 1

    # ── Prepare for k-bit training (QLoRA requirement) ───────────────────────
    if use_4bit:
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=True,
        )

    # ── Apply LoRA ─────────────────────────────────────────────────────────────
    if method == "qlora":
        peft_config = get_qlora_config(r=lora_r)
    else:
        peft_config = get_lora_config(r=lora_r)

    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    logger.info(
        "PEFT model ready",
        trainable_params=sum(
            p.numel() for p in model.parameters() if p.requires_grad
        ),
        total_params=sum(p.numel() for p in model.parameters()),
    )

    # ── Load Dataset ───────────────────────────────────────────────────────────
    raw_dataset = load_training_data(dataset_path)

    def formatting_func(examples):
        """Format messages into training strings."""
        texts = []
        for messages in examples["messages"]:
            text = format_prompt(messages, tokenizer)
            texts.append(text)
        return texts

    # ── Training Arguments ─────────────────────────────────────────────────────
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        learning_rate=learning_rate,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        save_strategy="epoch",
        evaluation_strategy="no",
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        report_to="none",
        optim="paged_adamw_8bit" if use_4bit else "adamw_torch",
        dataloader_num_workers=2,
        remove_unused_columns=True,
    )

    # ── Initialize SFT Trainer ─────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        train_dataset=raw_dataset,
        peft_config=peft_config,
        formatting_func=formatting_func,
        max_seq_length=max_seq_length,
        tokenizer=tokenizer,
        args=training_args,
    )

    # ── Train ──────────────────────────────────────────────────────────────────
    logger.info("Starting training...")
    trainer.train()

    # ── Save Adapter ───────────────────────────────────────────────────────────
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    trainer.model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    logger.info(
        "LoRA adapter saved",
        output_dir=output_dir,
    )

    # Save training metadata
    metadata = {
        "base_model": base_model_name,
        "method": method,
        "lora_r": lora_r,
        "epochs": epochs,
        "learning_rate": learning_rate,
        "max_seq_length": max_seq_length,
        "training_samples": len(raw_dataset),
    }
    with open(output_path / "training_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    return output_dir


# ─── Inference with LoRA Adapter ─────────────────────────────────────────────

def load_lora_model(adapter_path: str, base_model_name: Optional[str] = None):
    """
    Load a fine-tuned LoRA adapter for inference.
    Can be merged with base model or kept as adapter.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    # Load training metadata if available
    metadata_path = Path(adapter_path) / "training_metadata.json"
    if metadata_path.exists() and base_model_name is None:
        with open(metadata_path) as f:
            metadata = json.load(f)
        base_model_name = metadata["base_model"]

    if not base_model_name:
        raise ValueError("base_model_name required if no training_metadata.json")

    logger.info(
        "Loading LoRA model",
        base_model=base_model_name,
        adapter=adapter_path,
    )

    tokenizer = AutoTokenizer.from_pretrained(adapter_path)

    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_name,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    # Load PEFT adapter on top of base model
    model = PeftModel.from_pretrained(base_model, adapter_path)

    return model, tokenizer


def merge_and_export(
    adapter_path: str,
    output_path: str,
    base_model_name: Optional[str] = None,
):
    """
    Merge LoRA weights into the base model for faster inference.
    Merged model has no PEFT overhead.
    """
    import torch

    model, tokenizer = load_lora_model(adapter_path, base_model_name)

    logger.info("Merging LoRA weights into base model...")
    merged_model = model.merge_and_unload()

    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)

    merged_model.save_pretrained(output_path)
    tokenizer.save_pretrained(output_path)

    logger.info("Merged model saved", path=output_path)
    return output_path


# ─── Main CLI ─────────────────────────────────────────────────────────────────

def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Fine-tune LLM with LoRA/QLoRA for customer support"
    )
    parser.add_argument(
        "--base-model",
        type=str,
        default="mistralai/Mistral-7B-Instruct-v0.2",
        help="HuggingFace model ID or local path",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Path to RAFT JSONL training data",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./models/support-lora",
        help="Output directory for LoRA adapter",
    )
    parser.add_argument(
        "--method",
        choices=["lora", "qlora"],
        default="qlora",
        help="Fine-tuning method",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--max-seq-length", type=int, default=2048)
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Merge adapter into base model after training",
    )
    parser.add_argument(
        "--generate-raft-data",
        action="store_true",
        help="Generate RAFT training data before fine-tuning",
    )

    args = parser.parse_args()

    # Optionally generate RAFT training data first
    if args.generate_raft_data:
        logger.info("Generating RAFT training data...")
        from src.generation.raft import RAFTDataGenerator
        from src.generation.llm_client import LLMClientFactory

        generator = RAFTDataGenerator(
            llm_client=LLMClientFactory.create_default(),
            num_distractors=3,
            oracle_probability=0.8,
            questions_per_chunk=3,
        )

        # Load chunks from the index
        from src.indexing.hybrid_index import HybridIndex
        from src.indexing.vector_store import SearchQuery

        index = HybridIndex()
        search_results = index.vector_store.search(
            SearchQuery(text="customer support", top_k=100)
        )

        if search_results:
            dataset = generator.generate_dataset(
                chunks=search_results,
                max_examples=500,
            )
            raft_output = Path(args.dataset).parent
            dataset.save(str(raft_output), format_type="openai")
            logger.info(
                "RAFT dataset generated",
                examples=len(dataset),
                output=str(raft_output),
            )

    # Run fine-tuning
    output_dir = train_lora(
        base_model_name=args.base_model,
        dataset_path=args.dataset,
        output_dir=args.output,
        method=args.method,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        lora_r=args.lora_r,
        max_seq_length=args.max_seq_length,
        use_4bit=(args.method == "qlora"),
    )

    # Optionally merge adapter
    if args.merge:
        merged_path = args.output + "-merged"
        merge_and_export(output_dir, merged_path, args.base_model)

    print(f"\n✅ Fine-tuning complete. Adapter saved to: {output_dir}")


if __name__ == "__main__":
    main()