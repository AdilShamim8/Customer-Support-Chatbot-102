"""
Admin API routes - document management, evaluation, and statistics.
"""

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, File
from pathlib import Path
import tempfile

from src.api.schemas import (
    EvaluationRequest,
    EvaluationResponse,
    StatsResponse,
)
from src.evaluation.evaluator import RAGEvaluator, EvaluationSample
from src.parsing.document_parser import DocumentParserFactory, ParseStrategy
from src.parsing.chunking import ChunkingStrategy, ChunkerFactory
from src.pipeline.rag_pipeline import RAGPipeline

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


def get_pipeline(request: Request) -> RAGPipeline:
    return request.app.state.rag_pipeline


@router.post(
    "/documents/upload",
    summary="Upload and index a document",
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    chunk_strategy: str = "hierarchical",
    parse_strategy: str = "rule_based",
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> dict:
    """
    Upload a document file for indexing.
    Supports PDF, DOCX, HTML, and Markdown.
    """
    ALLOWED_EXTENSIONS = {".pdf", ".docx", ".html", ".htm", ".md", ".txt"}
    file_ext = Path(file.filename or "").suffix.lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file_ext}. "
                   f"Allowed: {ALLOWED_EXTENSIONS}",
        )

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(
        suffix=file_ext, delete=False
    ) as tmp_file:
        content = await file.read()
        tmp_file.write(content)
        tmp_path = Path(tmp_file.name)

    doc_id = None

    def _ingest():
        nonlocal doc_id
        try:
            # Parse document
            doc = DocumentParserFactory.parse(
                tmp_path,
                strategy=ParseStrategy(parse_strategy),
            )
            doc_id = doc.doc_id

            # Chunk document
            chunker = ChunkerFactory.get_chunker(
                strategy=ChunkingStrategy(chunk_strategy)
            )
            chunks = chunker.chunk(doc)

            # Index chunks
            pipeline.retriever.index_chunks(chunks)

            logger.info(
                "Document ingested",
                doc_id=doc_id,
                title=doc.title,
                chunks=len(chunks),
            )
        except Exception as e:
            logger.error("Document ingestion failed", error=str(e))
        finally:
            tmp_path.unlink(missing_ok=True)

    background_tasks.add_task(_ingest)

    return {
        "status": "processing",
        "filename": file.filename,
        "message": "Document is being indexed in the background",
    }


@router.delete(
    "/documents/{doc_id}",
    summary="Remove a document from the index",
)
async def delete_document(
    doc_id: str,
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> dict:
    """Delete all chunks for a document from all indices."""
    deleted = pipeline.retriever.hybrid_index.delete_document(doc_id)
    return {
        "status": "deleted",
        "doc_id": doc_id,
        "chunks_removed": deleted,
    }


@router.post(
    "/evaluate",
    response_model=EvaluationResponse,
    summary="Run evaluation on test samples",
)
async def run_evaluation(
    request_body: EvaluationRequest,
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> EvaluationResponse:
    """
    Run RAG evaluation on provided test samples.
    Samples should include question, answer, contexts, and optionally ground_truth.
    """
    evaluator = RAGEvaluator(
        rag_pipeline=pipeline,
        use_llm_metrics=request_body.use_llm_metrics,
        use_statistical_metrics=request_body.use_statistical_metrics,
    )

    samples = [
        EvaluationSample(
            question=s["question"],
            answer=s.get("answer", ""),
            contexts=s.get("contexts", []),
            ground_truth=s.get("ground_truth"),
        )
        for s in request_body.samples
    ]

    report = evaluator.evaluate_answers(
        samples=samples,
        dataset_name=request_body.dataset_name,
    )

    return EvaluationResponse(
        dataset_name=report.dataset_name,
        total_samples=report.total_samples,
        overall_pass_rate=report.overall_pass_rate,
        metric_averages=report.metric_averages,
        pass_rates=report.pass_rates,
        evaluation_time_seconds=report.evaluation_time_seconds,
    )


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Get pipeline statistics",
)
async def get_stats(
    pipeline: RAGPipeline = Depends(get_pipeline),
) -> StatsResponse:
    """Return current pipeline statistics."""
    stats = pipeline.get_pipeline_stats()
    hybrid_stats = stats.get("hybrid_index", {})
    llm_usage = stats.get("llm_usage", {})

    return StatsResponse(
        vector_store_count=hybrid_stats.get("vector_store_count", 0),
        keyword_index_count=hybrid_stats.get("keyword_index_count", 0),
        document_count=hybrid_stats.get("document_count", 0),
        llm_requests=llm_usage.get("request_count", 0),
        total_tokens_used=llm_usage.get("total_tokens", 0),
        total_cost_usd=llm_usage.get("total_cost_usd", 0.0),
    )