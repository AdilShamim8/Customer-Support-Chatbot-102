"""
Keyword-based indexing using BM25 and Elasticsearch.
Provides full-text search capabilities to complement vector search.
BM25 is especially good at exact term matching and rare keyword retrieval.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog
from rank_bm25 import BM25Okapi

from configs.settings import settings
from src.indexing.vector_store import SearchResult, SearchQuery
from src.parsing.chunking import DocumentChunk

logger = structlog.get_logger(__name__)


def simple_tokenize(text: str) -> list[str]:
    """
    Simple whitespace + punctuation tokenizer.
    In production, consider NLTK or spaCy for better tokenization.
    """
    import re
    # Lowercase and split on non-alphanumeric
    tokens = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    # Remove very short tokens
    return [t for t in tokens if len(t) > 1]


class BaseKeywordIndex(ABC):
    """Abstract keyword index interface."""
    
    @abstractmethod
    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        pass
    
    @abstractmethod
    def search(self, query: SearchQuery) -> list[SearchResult]:
        pass
    
    @abstractmethod
    def delete_document(self, doc_id: str) -> int:
        pass
    
    @abstractmethod
    def count(self) -> int:
        pass


class BM25Index(BaseKeywordIndex):
    """
    In-memory BM25 keyword index.
    Fast, no external dependencies.
    Best for datasets up to ~100K chunks.
    """
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self._chunks: list[DocumentChunk] = []
        self._bm25: Optional[BM25Okapi] = None
        self._tokenized_corpus: list[list[str]] = []
    
    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        """Add chunks and rebuild the BM25 index."""
        self._chunks.extend(chunks)
        
        # Tokenize new chunks
        new_tokenized = [
            simple_tokenize(chunk.content) for chunk in chunks
        ]
        self._tokenized_corpus.extend(new_tokenized)
        
        # Rebuild BM25 index (required on each addition)
        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(
                self._tokenized_corpus,
                k1=self.k1,
                b=self.b,
            )
        
        logger.info(
            "BM25 index updated",
            total_chunks=len(self._chunks),
        )
    
    def search(self, query: SearchQuery) -> list[SearchResult]:
        if not self._bm25 or not self._chunks:
            return []
        
        query_tokens = simple_tokenize(query.text)
        
        if not query_tokens:
            return []
        
        # Get BM25 scores for all documents
        scores = self._bm25.get_scores(query_tokens)
        
        # Get top-k indices
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:query.top_k]
        
        results = []
        max_score = max(scores) if max(scores) > 0 else 1.0
        
        for rank, idx in enumerate(top_indices):
            if scores[idx] <= 0:
                continue
            
            chunk = self._chunks[idx]
            # Normalize BM25 score to 0-1 range
            normalized_score = float(scores[idx]) / max_score
            
            results.append(SearchResult(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                content=chunk.content,
                score=normalized_score,
                metadata=chunk.metadata,
                rank=rank,
            ))
        
        return results
    
    def delete_document(self, doc_id: str) -> int:
        """Remove all chunks for a document and rebuild index."""
        original_count = len(self._chunks)
        
        remaining_chunks = []
        remaining_tokenized = []
        
        for chunk, tokenized in zip(self._chunks, self._tokenized_corpus):
            if chunk.doc_id != doc_id:
                remaining_chunks.append(chunk)
                remaining_tokenized.append(tokenized)
        
        self._chunks = remaining_chunks
        self._tokenized_corpus = remaining_tokenized
        
        # Rebuild index
        if self._tokenized_corpus:
            self._bm25 = BM25Okapi(self._tokenized_corpus, k1=self.k1, b=self.b)
        else:
            self._bm25 = None
        
        deleted = original_count - len(self._chunks)
        logger.info("Document deleted from BM25", doc_id=doc_id, deleted=deleted)
        return deleted
    
    def count(self) -> int:
        return len(self._chunks)


class ElasticsearchIndex(BaseKeywordIndex):
    """
    Elasticsearch-based keyword index.
    Production-ready for large-scale deployments.
    Supports full-text search, fuzzy matching, and complex filters.
    """
    
    def __init__(
        self,
        index_name: str = settings.elasticsearch_index,
        url: str = settings.elasticsearch_url,
    ):
        from elasticsearch import Elasticsearch
        
        self.index_name = index_name
        self.es = Elasticsearch(
            url,
            basic_auth=(
                settings.elasticsearch_user,
                settings.elasticsearch_password,
            ),
            verify_certs=False,
        )
        
        self._ensure_index_exists()
        logger.info("Elasticsearch index initialized", index=index_name)
    
    def _ensure_index_exists(self) -> None:
        """Create index with appropriate mappings if it doesn't exist."""
        if self.es.indices.exists(index=self.index_name):
            return
        
        mappings = {
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "doc_id": {"type": "keyword"},
                    "content": {
                        "type": "text",
                        "analyzer": "english",
                        "fields": {
                            "exact": {"type": "keyword"},
                            "suggest": {"type": "search_as_you_type"},
                        }
                    },
                    "section_title": {"type": "text"},
                    "source": {"type": "keyword"},
                    "doc_type": {"type": "keyword"},
                    "title": {"type": "text"},
                    "chunk_index": {"type": "integer"},
                    "token_count": {"type": "integer"},
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "english": {
                            "tokenizer": "standard",
                            "filter": ["lowercase", "english_stop", "english_stemmer"],
                        }
                    },
                    "filter": {
                        "english_stop": {
                            "type": "stop",
                            "stopwords": "_english_",
                        },
                        "english_stemmer": {
                            "type": "stemmer",
                            "language": "english",
                        }
                    }
                }
            }
        }
        
        self.es.indices.create(index=self.index_name, body=mappings)
        logger.info("Elasticsearch index created", index=self.index_name)
    
    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        from elasticsearch.helpers import bulk
        
        actions = []
        for chunk in chunks:
            actions.append({
                "_index": self.index_name,
                "_id": chunk.chunk_id,
                "_source": {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "content": chunk.content,
                    "section_title": chunk.section_title or "",
                    "chunk_index": chunk.chunk_index,
                    "token_count": chunk.token_count,
                    **{
                        k: v for k, v in chunk.metadata.items()
                        if isinstance(v, (str, int, float, bool))
                    },
                }
            })
        
        if actions:
            success, errors = bulk(self.es, actions)
            logger.info(
                "Chunks indexed to Elasticsearch",
                success=success,
                errors=len(errors) if errors else 0,
            )
    
    def search(self, query: SearchQuery) -> list[SearchResult]:
        """
        Multi-match search with BM25 scoring.
        Boosts title and section_title fields.
        """
        es_query = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": query.text,
                                "fields": [
                                    "content^1.0",
                                    "section_title^1.5",
                                    "title^2.0",
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO",
                                "operator": "or",
                            }
                        }
                    ],
                    "filter": self._build_filters(query.filters),
                }
            },
            "size": query.top_k,
            "highlight": {
                "fields": {"content": {"fragment_size": 200}},
            },
        }
        
        response = self.es.search(index=self.index_name, body=es_query)
        
        results = []
        hits = response["hits"]["hits"]
        max_score = response["hits"]["max_score"] or 1.0
        
        for rank, hit in enumerate(hits):
            source = hit["_source"]
            normalized_score = hit["_score"] / max_score
            
            results.append(SearchResult(
                chunk_id=source["chunk_id"],
                doc_id=source["doc_id"],
                content=source["content"],
                score=normalized_score,
                metadata={k: v for k, v in source.items() 
                          if k not in ["chunk_id", "doc_id", "content"]},
                rank=rank,
            ))
        
        return results
    
    def delete_document(self, doc_id: str) -> int:
        response = self.es.delete_by_query(
            index=self.index_name,
            body={"query": {"term": {"doc_id": doc_id}}},
        )
        deleted = response.get("deleted", 0)
        logger.info("Document deleted from ES", doc_id=doc_id, deleted=deleted)
        return deleted
    
    def count(self) -> int:
        response = self.es.count(index=self.index_name)
        return response["count"]
    
    def _build_filters(self, filters: dict) -> list:
        """Build Elasticsearch filter clauses."""
        if not filters:
            return []
        return [{"term": {k: v}} for k, v in filters.items()]