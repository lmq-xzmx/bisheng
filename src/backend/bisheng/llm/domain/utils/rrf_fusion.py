"""Reciprocal Rank Fusion (RRF) algorithm for merging search results from multiple embedding models.

RRF is a rank-based fusion algorithm that combines results from multiple ranking systems
without requiring score normalization. It is the industry standard used by Elasticsearch,
Weaviate, and other vector search engines.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class HasDocId(Protocol):
    """Protocol for documents that have an ID field."""

    id: str | int


def _get_doc_id(doc: Any) -> str:
    """Extract unique document identifier from a document."""
    if hasattr(doc, "id"):
        return str(doc.id)
    if hasattr(doc, "chunk_id"):
        return str(doc.chunk_id)
    if hasattr(doc, "doc_id"):
        return str(doc.doc_id)
    # LangChain Document uses page_content as content
    if hasattr(doc, "page_content"):
        return str(hash(doc.page_content))
    if hasattr(doc, "content"):
        return str(hash(doc.content))
    return str(id(doc))


@dataclass
class RRFResult:
    """A document scored by RRF with source tracking."""

    doc: Any
    score: float
    sources: list[str] = field(default_factory=list)  # "new", "old", or both


def reciprocal_rank_fusion(
    results_new: list[Any],
    results_old: list[Any],
    k: int = 60,
) -> list[RRFResult]:
    """
    Combine two ranked result lists using Reciprocal Rank Fusion.

    RRF score = SUM(1 / (k + rank)) for each system that returned the doc
    where rank is 1-indexed position in that system's result list.

    Args:
        results_new: Results from the new embedding model, ordered by relevance (most relevant first).
        results_old: Results from the old embedding model, ordered by relevance (most relevant first).
        k: Fusion constant (default 60, standard value used by Elasticsearch).
           Higher values reduce the impact of rank differences.

    Returns:
        List of RRFResult sorted by RRF score descending.

    Example:
        new_results = [doc_a, doc_b, doc_c]  # doc_a is most relevant
        old_results = [doc_c, doc_d, doc_a]  # doc_c is most relevant
        fused = reciprocal_rank_fusion(new_results, old_results)
        # doc_a and doc_c will have equal scores (both appear in both lists)
    """
    if not results_new and not results_old:
        return []
    if not results_new:
        return [RRFResult(doc=d, score=0.0, sources=["old"]) for d in results_old]
    if not results_old:
        return [RRFResult(doc=d, score=0.0, sources=["new"]) for d in results_new]

    scores: dict[str, tuple[float, list[str], Any]] = {}

    # Score new model results
    for rank, doc in enumerate(results_new, start=1):
        doc_id = _get_doc_id(doc)
        if doc_id in scores:
            score, sources, _ = scores[doc_id]
            scores[doc_id] = (score + 1 / (k + rank), [*sources, "new"], doc)
        else:
            scores[doc_id] = (1 / (k + rank), ["new"], doc)

    # Score old model results
    for rank, doc in enumerate(results_old, start=1):
        doc_id = _get_doc_id(doc)
        if doc_id in scores:
            score, sources, first_doc = scores[doc_id]
            scores[doc_id] = (score + 1 / (k + rank), [*sources, "old"], first_doc)
        else:
            scores[doc_id] = (1 / (k + rank), ["old"], doc)

    # Sort by RRF score descending
    ranked = sorted(scores.items(), key=lambda x: x[1][0], reverse=True)

    return [RRFResult(doc=score_data[2], score=score_data[0], sources=score_data[1]) for doc_id, score_data in ranked]


def fuse_results(
    results_new: list[Any],
    results_old: list[Any],
    k: int = 60,
) -> list[Any]:
    """Fuse results and return just the documents, preserving order."""
    return [result.doc for result in reciprocal_rank_fusion(results_new, results_old, k)]
