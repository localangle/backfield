from backfield_entities.canonical.candidate_review import strip_ai_recommendations_from_review_reasons


def test_strip_ai_recommendations_keeps_review_context() -> None:
    raw = [
        {"code": "first_name_only", "message": "First name only"},
        {"code": "canonical_suggestion", "suggested_action": "defer"},
        {"code": "canonical_adjudication", "outcome": "no_high_confidence_link"},
    ]
    out = strip_ai_recommendations_from_review_reasons(raw)
    assert out == [{"code": "first_name_only", "message": "First name only"}]
