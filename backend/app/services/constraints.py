"""Deterministic constraint extraction from a natural-language query.

Why this exists at all, given we have an LLM: numeric and dietary
constraints are *hard* constraints. "under 200 rupees" returning a 240-rupee
dish is a correctness bug, not a ranking imperfection. Embeddings are bad at
numbers and LLMs are only probabilistically good at them, so price and
dietary filters are applied as SQL-level predicates by this module and the
AI layer is left to do what it is actually good at: judging semantic fit.

The LLM extractor in ai_search.py may *add* constraints on top of these; it
never overrides a rule that fired here.
"""
import re

from app.schemas import ParsedConstraints

_NUMBER = r"(\d{2,5})"

_MAX_PRICE_PATTERNS = [
    rf"under\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"below\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"less\s+than\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"cheaper\s+than\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"within\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"(?:rs\.?|₹|inr)\s*{_NUMBER}\s*(?:or\s+less|and\s+under|max)",
    rf"budget\s+of\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"upto\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"up\s+to\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
]

_MIN_PRICE_PATTERNS = [
    rf"over\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"above\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"more\s+than\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
    rf"at\s+least\s*(?:rs\.?|₹|inr)?\s*{_NUMBER}",
]

# Vegetarian intent. Order matters: the negations are checked first so
# "non veg" never trips the "veg" branch.
_NON_VEG_HINTS = [
    "non-veg", "non veg", "nonveg", "non-vegetarian", "meaty", "with meat",
    "chicken", "mutton", "lamb", "fish", "prawn", "egg", "seafood",
]
_VEG_HINTS = [
    "vegetarian", "veggie", "veg only", "no meat", "meatless", "pure veg",
]
_VEGAN_HINTS = ["vegan", "no dairy", "dairy free", "dairy-free"]

_SPICY_HINTS = ["spicy", "hot", "fiery", "chilli", "chili", "masaledar", "tangy hot"]
_MILD_HINTS = [
    "not spicy", "non spicy", "mild", "no spice", "less spicy", "without spice",
    "not too spicy", "not hot",
]

# "light", "not fried" and friends are soft preferences: they steer ranking
# but must not hard-filter the catalogue, or a small menu returns nothing.
_SOFT_EXCLUSIONS = {
    "not fried": ["fried", "deep-fried", "deep fried"],
    "no fried": ["fried", "deep-fried"],
    "without fried": ["fried"],
    "not deep fried": ["deep-fried", "deep fried", "fried"],
    "no onion": ["onion"],
    "no garlic": ["garlic"],
    "nut free": ["nut", "peanut", "cashew"],
    "nut-free": ["nut", "peanut", "cashew"],
    "no nuts": ["nut", "peanut", "cashew"],
    "without nuts": ["nut", "peanut", "cashew"],
    "no cream": ["cream", "creamy"],
    "not heavy": ["rich", "buttery", "creamy"],
}

# Phrases that map to a hard tag exclusion rather than a text exclusion.
# An allergy is not a preference: "without nuts" must never return an item
# tagged contains-nuts, even if the word "nut" is absent from its description.
_TAG_EXCLUSION_HINTS: dict[str, str] = {
    "nut free": "contains-nuts",
    "nut-free": "contains-nuts",
    "no nuts": "contains-nuts",
    "without nuts": "contains-nuts",
    "nut allergy": "contains-nuts",
    "allergic to nuts": "contains-nuts",
}

_CATEGORY_HINTS = {
    "starter": "Starters",
    "starters": "Starters",
    "appetizer": "Starters",
    "appetiser": "Starters",
    "main course": "Main Course",
    "mains": "Main Course",
    "main": "Main Course",
    "curry": "Main Course",
    "bread": "Breads",
    "breads": "Breads",
    "roti": "Breads",
    "naan": "Breads",
    "rice": "Rice & Biryani",
    "biryani": "Rice & Biryani",
    "dessert": "Desserts",
    "desserts": "Desserts",
    "sweet": "Desserts",
    "drink": "Beverages",
    "drinks": "Beverages",
    "beverage": "Beverages",
    "beverages": "Beverages",
}


def _first_number(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return float(match.group(1))
    return None


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(n in text for n in needles)


def parse_constraints(query: str) -> ParsedConstraints:
    """Extract hard filters from a free-text query. Never raises."""
    text = f" {query.lower().strip()} "
    text = text.replace("rupees", "rs").replace("rupee", "rs")

    constraints = ParsedConstraints(source="rules")

    constraints.max_price = _first_number(text, _MAX_PRICE_PATTERNS)
    constraints.min_price = _first_number(text, _MIN_PRICE_PATTERNS)

    # --- diet ------------------------------------------------------------
    if _contains_any(text, _NON_VEG_HINTS):
        # Only treat it as a hard non-veg filter when the user asked for meat
        # generally, not when they named a specific dish ("chicken biryani"),
        # which the semantic layer handles better.
        if _contains_any(text, ["non-veg", "non veg", "nonveg", "non-vegetarian", "meaty", "with meat"]):
            constraints.require_tags.append("non-vegetarian")
    elif _contains_any(text, _VEG_HINTS):
        constraints.require_tags.append("vegetarian")

    if _contains_any(text, _VEGAN_HINTS):
        constraints.require_tags.append("vegan")

    # --- heat ------------------------------------------------------------
    if _contains_any(text, _MILD_HINTS):
        constraints.exclude_tags.append("spicy")
    elif _contains_any(text, _SPICY_HINTS):
        constraints.require_tags.append("spicy")

    # --- soft exclusions --------------------------------------------------
    for phrase, terms in _SOFT_EXCLUSIONS.items():
        if phrase in text:
            constraints.exclude_terms.extend(terms)

    # --- allergen exclusions (hard) --------------------------------------
    for phrase, tag in _TAG_EXCLUSION_HINTS.items():
        if phrase in text:
            constraints.exclude_tags.append(tag)

    # --- category ---------------------------------------------------------
    for hint, category in _CATEGORY_HINTS.items():
        if re.search(rf"\b{re.escape(hint)}\b", text):
            if category not in constraints.categories:
                constraints.categories.append(category)

    # De-duplicate while preserving order.
    constraints.require_tags = list(dict.fromkeys(constraints.require_tags))
    constraints.exclude_tags = list(dict.fromkeys(constraints.exclude_tags))
    constraints.exclude_terms = list(dict.fromkeys(constraints.exclude_terms))
    return constraints


def merge_constraints(
    base: ParsedConstraints, extra: ParsedConstraints
) -> ParsedConstraints:
    """Fold LLM-extracted constraints into rule-extracted ones.

    Rules win on conflicts: a regex that matched "under 200" is more
    trustworthy than a model that decided the budget was 250.
    """
    merged = base.model_copy(deep=True)
    if merged.max_price is None:
        merged.max_price = extra.max_price
    if merged.min_price is None:
        merged.min_price = extra.min_price
    for field in ("require_tags", "exclude_tags", "exclude_terms", "categories"):
        combined = getattr(merged, field) + [
            v for v in getattr(extra, field) if v not in getattr(merged, field)
        ]
        setattr(merged, field, combined)
    # A tag cannot be both required and excluded; the required side wins.
    merged.exclude_tags = [t for t in merged.exclude_tags if t not in merged.require_tags]
    merged.source = "rules+llm"
    return merged
