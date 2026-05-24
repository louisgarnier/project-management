"""EPIC-18 S2.3 — Single source of truth for topic similarity scoring.

Used by:
  - v5 Stage 6 (reconcile) to suggest registry merges
  - Pass 1 lexical_precheck to qualify LLM evaluation candidates
  - Pass 1 confidence scoring

Replaces three previously-divergent implementations.
"""
from __future__ import annotations
import math as _math
import re as _re


_STOPWORDS = {
    "the", "a", "an", "to", "and", "or", "for", "with", "of", "in", "on", "at",
    "by", "from", "this", "that", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "can", "may", "might", "must", "shall", "their", "our", "us",
    "we", "they", "he", "she", "it", "you", "your", "my", "as", "if",
    "when", "where", "what", "who", "how", "why", "all", "any", "some", "no",
    "not", "more", "less", "very", "just", "also", "than", "then", "but",
    "into", "out", "off", "over", "under", "again", "further", "once",
}


def effective_token_set(topic_or_candidate: dict) -> set[str]:
    """Build the effective token bag for lexical matching.

    Aggregates per-task key_terms across all tasks of the topic, in addition
    to topic.key_terms and topic.name.
    """
    tokens: set[str] = set()
    sources: list[str] = []
    for kt in (topic_or_candidate.get("key_terms") or []):
        if kt:
            sources.append(str(kt))
    if topic_or_candidate.get("name"):
        sources.append(str(topic_or_candidate["name"]))
    for task in (topic_or_candidate.get("tasks") or []):
        if isinstance(task, dict):
            for kt in (task.get("key_terms") or []):
                if kt:
                    sources.append(str(kt))
    for src in sources:
        for word in _re.findall(r"\b[a-z][a-z0-9_-]+\b", src.lower()):
            if len(word) > 2 and word not in _STOPWORDS:
                tokens.add(word)
    return tokens


def compute_idf(project_topics: list[dict]) -> dict[str, float]:
    """IDF over effective token sets. Common tokens → low IDF; rare → high.
    Formula: IDF(t) = log((N + 1) / (df + 1)) + 1
    """
    N = max(len(project_topics), 1)
    df: dict[str, int] = {}
    for t in project_topics:
        for tok in effective_token_set(t):
            df[tok] = df.get(tok, 0) + 1
    return {tok: _math.log((N + 1) / (count + 1)) + 1.0 for tok, count in df.items()}


def weighted_jaccard_tokens(a_tokens: set[str], b_tokens: set[str], idf: dict[str, float]) -> float:
    """IDF-weighted Jaccard on pre-computed token sets."""
    inter = a_tokens & b_tokens
    union = a_tokens | b_tokens
    if not union:
        return 0.0
    inter_w = sum(idf.get(t, 1.0) for t in inter)
    union_w = sum(idf.get(t, 1.0) for t in union)
    return inter_w / union_w if union_w > 0 else 0.0


def weighted_jaccard(a_terms: list[str], b_terms: list[str], idf: dict[str, float]) -> float:
    """Convenience: takes raw term lists, builds effective token sets, then scores."""
    set_a = effective_token_set({"key_terms": a_terms})
    set_b = effective_token_set({"key_terms": b_terms})
    return weighted_jaccard_tokens(set_a, set_b, idf)
