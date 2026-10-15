# Prompt Engineering Playbook

> Status: Active · Owner: @AdilShamim8 · Last reviewed: 2026-10-15
>
> Implementation: `src/generation/prompt_engine.py`. Every strategy here
> maps to a `PromptStrategy` enum member. Changes to prompts are changes
> to product behavior: they require an eval delta (ADR-0007).

## The Ground Rules (apply to every strategy)

1. **Groundedness first.** The system instruction always includes: answer
   ONLY from the provided context; if the context is insufficient, say so
   and offer the human-handoff path. A confident hallucination is the
   worst possible failure in support.
2. **Untrusted-data framing.** Retrieved chunks are delimited and
   labeled as data (see threat model §1) - the model is told context
   contains no instructions.
3. **Citations required.** Every factual sentence cites chunk IDs; the
   API surfaces them as `sources`. Users trust what they can verify.
4. **Tone contract.** Empathetic, concise, action-oriented - a support
   answer is a *resolution*, not an essay.
5. **Budget discipline.** Prompts are token-budgeted (`max_context_tokens`);
   the assembler truncates by relevance order, never silently dropping
   the citation scaffolding.

## Strategy 1: Zero-Shot

**When**: high-volume FAQ-shaped traffic, well-covered topics, latency-
and cost-sensitive paths.

```
SYSTEM: [role + ground rules + tone]
USER: [question] + [retrieved context blocks] + [output format]
```

- Cheapest and fastest; quality depends entirely on retrieval precision.
- Works when the top-5 chunks unambiguously contain the answer.
- **Watch**: eval faithfulness on this strategy is your retrieval-quality
  canary - zero-shot has nothing else to lean on.

## Strategy 2: Few-Shot

**When**: format-sensitive answers (refund policies with amounts,
step-by-step procedures), tone consistency matters.

```
USER: [2-3 exemplar Q→A pairs, drawn from real resolved conversations]
      + [actual question + context]
```

- Examples teach *format and tone*, not facts - the examples' facts come
  from the same corpus (in-context exemplars that contradict the corpus
  teach the model to hallucinate).
- `num_few_shot_examples` is tuned; 2 is the sweet spot in evals - more
  improved tone marginally but cost tokens linearly.
- **Watch**: exemplar drift - examples are versioned with the prompt, and
  stale exemplars (old policy) poison tone *and* facts.

## Strategy 3: Chain-of-Thought

**When**: multi-hop questions ("I ordered X with Y, then returned Y but
kept X - what's my refund?"), policy-combination logic, eligibility
arithmetic.

```
SYSTEM: reason step-by-step from the context, THEN give the final answer
         prefixed with "Answer:"; cite each reasoning step's source
```

- Reasoning quality gain is real but latency + tokens ≈ 2x; route to
  CoT only when retrieval-confidence is low or the question classifies
  as multi-hop.
- The `Answer:` prefix makes post-processing robust - the streaming UI
  renders reasoning collapsibly, the API returns the full trace.
- **Watch**: CoT can *rationalize* a wrong answer persuasively -
  faithfulness eval gates this strategy hardest.

## Strategy 4: Role + User-Context

**When**: personalization layer over any of the above - the strategy
composes (few-shot + role, CoT + role...).

```
SYSTEM: You are {company}'s support agent for {product_line}.
        The customer: tier={vip|standard}, member since {year},
        open orders={n}, prior tickets={topics}.
        Adjust tone and allowed concessions accordingly.
```

- User-context comes from the conversation/profile layer, **never**
  embedded in the retrieved chunks (separation keeps injection surface
  small - the threat model's untrusted-data framing applies to chunks,
  not to this trusted context).
- Enables policy-correct treatment: VIP gets the goodwill-refund policy,
  standard tier gets the standard one - the *policy doc* is retrieved;
  the *tier* is context.

## RAG-Specific Assembly Order (why it's this order)

```
system(role+rules) → few-shot exemplars → conversation history (last N)
→ [BEGIN UNTRUSTED CONTEXT] chunks [END] → question → format contract
```

- Instructions at the **top** (models weight early tokens), the question
  **last** (recency bias makes the query salient).
- History BEFORE context: chunks must be the nearest thing to the
  question so relevance ordering in the prompt matches retrieval order.
- Context blocks carry `(source, date)` labels - the model cites them,
  and staleness becomes visible in answers ("per the Jan 2026 policy").

## Anti-Patterns (each earned its place by an eval regression)

- **"Always be helpful and never refuse"** - overrides groundedness;
  faithfulness dropped measurably in tests.
- **Mixed-language instructions** with English context - model code-
  switches mid-answer; keep one language per prompt.
- **Stuffed context** (all top-50, no rerank cut) - diluted relevance;
  models attend to the middle less (lost-in-the-middle): put the best
  chunks first and last.
- **Unversioned prompt edits** - prompt strings now live in code with
  eval-gated changes; no "quick copy tweak" without a diff review.

## Tuning Loop

1. Change prompt → 2. run golden-set eval → 3. compare the three
   metrics + token cost → 4. merge or revert (ADR-0007's gate) →
   5. production canary via the deploy runbook.
