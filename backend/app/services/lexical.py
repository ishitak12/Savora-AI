"""BM25 lexical retrieval — the offline fallback for semantic search.

Pure Python, zero dependencies, no model download. It exists so that a
missing AI provider key, an expired quota, or hotel wifi during the demo
degrades the product instead of breaking it: the customer still gets ranked
results, they are just lexically matched rather than semantically matched.

BM25 over ~40 short documents is microseconds of work, so the index is
rebuilt per request rather than cached and invalidated. If the catalogue
grew to thousands of items this would move to a persistent index.
"""
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Culinary synonym expansion. Lexical matching alone cannot connect "light"
# to "grilled" or "salad"; this table gives the fallback path a fighting
# chance on the kind of query the brief actually asks about.
_SYNONYMS: dict[str, list[str]] = {
    "light": ["light", "grilled", "salad", "soup", "steamed", "clear", "fresh"],
    "heavy": ["heavy", "rich", "creamy", "buttery", "indulgent"],
    "spicy": ["spicy", "chilli", "hot", "fiery", "pepper", "masala"],
    "mild": ["mild", "creamy", "sweet", "delicate"],
    "veg": ["vegetarian", "paneer", "vegetable", "dal", "mushroom"],
    "vegetarian": ["vegetarian", "paneer", "vegetable", "dal", "mushroom"],
    "healthy": ["grilled", "steamed", "salad", "roasted", "light", "tandoori"],
    "lunch": ["rice", "curry", "thali", "bowl", "main"],
    "dinner": ["curry", "biryani", "main", "bread"],
    "snack": ["starter", "small", "bite", "chaat"],
    "sweet": ["dessert", "sweet", "sugar", "kheer", "halwa"],
    "cheap": ["affordable", "budget"],
    "filling": ["hearty", "rich", "biryani", "thali"],
    "drink": ["beverage", "lassi", "juice", "tea", "coffee"],
}

_STOPWORDS = {
    "a", "an", "and", "the", "for", "with", "without", "some", "something",
    "that", "is", "not", "of", "to", "me", "i", "want", "would", "like",
    "under", "below", "over", "above", "rs", "rupees", "please", "give",
    "show", "find", "looking", "need", "can", "you", "my", "it", "in", "on",
}


def tokenize(text: str, expand: bool = False) -> list[str]:
    tokens = [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]
    if not expand:
        return tokens
    expanded: list[str] = []
    for token in tokens:
        expanded.append(token)
        expanded.extend(s for s in _SYNONYMS.get(token, []) if s != token)
    return expanded


class BM25:
    """Textbook Okapi BM25 (k1=1.5, b=0.75)."""

    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(d) for d in documents]
        self.doc_lengths = [len(t) for t in self.doc_tokens]
        self.avg_length = (
            sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        )
        self.term_freqs = [Counter(t) for t in self.doc_tokens]

        doc_freq: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            doc_freq.update(set(tokens))
        n = max(len(documents), 1)
        # Standard BM25+ style IDF floor keeps common terms from going negative.
        self.idf = {
            term: math.log(1 + (n - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_freq.items()
        }

    def score(self, query: str) -> list[float]:
        query_tokens = tokenize(query, expand=True)
        scores = [0.0] * len(self.doc_tokens)
        if not query_tokens or self.avg_length == 0:
            return scores
        for index, freqs in enumerate(self.term_freqs):
            length = self.doc_lengths[index]
            total = 0.0
            for token in query_tokens:
                tf = freqs.get(token, 0)
                if tf == 0:
                    continue
                idf = self.idf.get(token, 0.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * length / self.avg_length
                )
                total += idf * numerator / denominator
            scores[index] = total
        return scores


def normalise(scores: list[float]) -> list[float]:
    """Squash raw BM25 scores into 0-1 so they are comparable with cosine
    similarity and presentable as a percentage in the UI."""
    if not scores:
        return []
    top = max(scores)
    if top <= 0:
        return [0.0] * len(scores)
    return [round(s / top, 4) for s in scores]
