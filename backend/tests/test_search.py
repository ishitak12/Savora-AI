"""AI search: constraint extraction and the offline fallback contract.

These tests run with no Gemini key set (see conftest), which is exactly the
degraded path. That is intentional: the fallback is the part that must never
break, and it is the part a CI runner can test deterministically without
network access or spend.
"""
from app.services.constraints import merge_constraints, parse_constraints
from app.schemas import ParsedConstraints


# --------------------------------------------------------------------------
# Constraint parser (pure function — no database, no network)
# --------------------------------------------------------------------------
def test_parses_the_brief_example_query():
    c = parse_constraints("something spicy and vegetarian under 200 rupees")
    assert c.max_price == 200
    assert "spicy" in c.require_tags
    assert "vegetarian" in c.require_tags


def test_parses_the_second_brief_example_query():
    c = parse_constraints("a light lunch that is not fried")
    assert c.max_price is None
    assert "fried" in c.exclude_terms


def test_not_spicy_excludes_rather_than_requires():
    c = parse_constraints("something not spicy please")
    assert "spicy" in c.exclude_tags
    assert "spicy" not in c.require_tags


def test_price_phrasings():
    assert parse_constraints("under rs 150").max_price == 150
    assert parse_constraints("below ₹300").max_price == 300
    assert parse_constraints("less than 250 rupees").max_price == 250
    assert parse_constraints("budget of 400").max_price == 400
    assert parse_constraints("above 500").min_price == 500


def test_nut_allergy_becomes_a_hard_tag_exclusion():
    c = parse_constraints("a dessert without nuts")
    assert "contains-nuts" in c.exclude_tags


def test_naming_a_dish_does_not_force_a_diet_filter():
    # "chicken biryani" should be handled semantically, not turned into a
    # hard non-vegetarian filter that could hide a relevant veg alternative.
    c = parse_constraints("chicken biryani")
    assert c.require_tags == []


def test_rules_win_over_llm_on_conflicting_price():
    rules = parse_constraints("under 200 rupees")
    llm = ParsedConstraints(max_price=500, require_tags=["vegan"], source="llm")
    merged = merge_constraints(rules, llm)
    assert merged.max_price == 200          # rule value preserved
    assert "vegan" in merged.require_tags   # llm addition folded in
    assert merged.source == "rules+llm"


def test_merge_drops_a_tag_that_is_both_required_and_excluded():
    rules = ParsedConstraints(require_tags=["spicy"])
    llm = ParsedConstraints(exclude_tags=["spicy"], source="llm")
    assert merge_constraints(rules, llm).exclude_tags == []


# --------------------------------------------------------------------------
# End-to-end search through the API, offline path
# --------------------------------------------------------------------------
def test_search_endpoint_is_public_and_reports_its_mode(client):
    response = client.get("/api/search", params={"q": "spicy vegetarian under 200"})
    assert response.status_code == 200
    body = response.json()
    assert body["search_mode"] == "lexical"   # no key configured in tests
    assert body["degraded"] is True
    assert body["constraints"]["max_price"] == 200


def test_hard_price_constraint_is_never_violated(client):
    body = client.get("/api/search", params={"q": "anything under 190 rupees"}).json()
    assert body["results"], "expected at least one match under 190"
    assert all(r["item"]["price"] <= 190 for r in body["results"])


def test_dietary_constraint_is_never_violated(client):
    body = client.get("/api/search", params={"q": "vegetarian food"}).json()
    assert body["results"]
    assert all("vegetarian" in r["item"]["tags"] for r in body["results"])


def test_unavailable_items_never_surface(client):
    body = client.get("/api/search", params={"q": "sold out special"}).json()
    assert all(r["item"]["name"] != "Sold Out Special" for r in body["results"])


def test_soft_exclusion_removes_fried_dishes(client):
    body = client.get("/api/search", params={"q": "a light lunch that is not fried"}).json()
    names = [r["item"]["name"] for r in body["results"]]
    assert "Crispy Corn" not in names  # its description says deep-fried


def test_impossible_constraints_return_empty_with_an_explanation(client):
    body = client.get("/api/search", params={"q": "non veg dish under 10 rupees"}).json()
    assert body["results"] == []
    assert any("constraint" in n.lower() for n in body["notes"])


def test_results_are_sorted_by_descending_score(client):
    body = client.get("/api/search", params={"q": "spicy chickpeas"}).json()
    scores = [r["score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)


def test_blank_query_is_rejected(client):
    assert client.get("/api/search", params={"q": ""}).status_code == 422


def test_ai_health_reports_unconfigured_without_crashing(client):
    body = client.get("/api/search/health").json()
    assert body["configured"] is False
