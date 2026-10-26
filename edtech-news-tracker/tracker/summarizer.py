"""
Extractive summarizer: selects the most representative sentences from an
article's full text, in their original order, up to a target word count.

Deliberately extractive (verbatim sentences from the source) rather than
LLM-generated -- for a competitive-intelligence feed, grounding the summary
in actual article sentences avoids the risk of a generated summary
misstating or inventing a fact. No extra API/model is needed for this.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import List, Optional

_STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any",
    "are", "as", "at", "be", "because", "been", "before", "being", "below", "between",
    "both", "but", "by", "could", "did", "do", "does", "doing", "down", "during", "each",
    "few", "for", "from", "further", "had", "has", "have", "having", "he", "her", "here",
    "hers", "herself", "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "just", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our", "ours", "ourselves",
    "out", "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "we",
    "were", "what", "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "yours", "yourself", "yourselves", "also", "said",
}

_SENT_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z0-9"‘“])')
_WORD_RE = re.compile(r"[A-Za-z']+")


def _split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    sentences = _SENT_SPLIT_RE.split(text)
    return [s.strip() for s in sentences if len(s.strip()) >= 25]


def _words(sentence: str) -> List[str]:
    return _WORD_RE.findall(sentence.lower())


def summarize(
    text: str,
    focus_terms: Optional[List[str]] = None,
    target_words: int = 450,
    max_words: int = 500,
) -> str:
    """Returns a summary of `text`: the full text if it's already short, or
    the highest-scoring sentences (by word-frequency + lead-sentence bonus +
    mention of `focus_terms`, e.g. the company name) otherwise, capped at
    `max_words` and kept in original article order for readability."""
    sentences = _split_sentences(text)
    if not sentences:
        words = (text or "").split()
        return " ".join(words[:max_words]) + ("..." if len(words) > max_words else "")

    if sum(len(_words(s)) for s in sentences) <= max_words:
        return " ".join(sentences)

    freq = Counter()
    for s in sentences:
        for w in _words(s):
            if w not in _STOPWORDS and len(w) > 2:
                freq[w] += 1
    max_freq = max(freq.values()) if freq else 1
    for w in freq:
        freq[w] /= max_freq

    focus_lower = [t.lower() for t in (focus_terms or []) if t]

    scored = []  # (index, sentence, score, word_count)
    for idx, s in enumerate(sentences):
        ws = _words(s)
        if not ws:
            continue
        score = sum(freq.get(w, 0) for w in ws) / len(ws)
        if idx < 3:
            score += 0.15  # news leads usually carry the crux
        if any(t in s.lower() for t in focus_lower):
            score += 0.2
        scored.append((idx, s, score, len(ws)))

    selected = set()
    word_count = 0
    for idx, s, score, wc in sorted(scored, key=lambda x: x[2], reverse=True):
        if word_count >= target_words:
            break
        selected.add(idx)
        word_count += wc

    ordered = [s for idx, s, _, _ in scored if idx in selected]
    summary = " ".join(ordered)

    words = summary.split()
    if len(words) > max_words:
        summary = " ".join(words[:max_words]) + "..."
    return summary
