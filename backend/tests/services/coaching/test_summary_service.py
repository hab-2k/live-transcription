from app.services.coaching.summary_service import SummaryService


def test_summary_service_returns_strengths_and_missed_opportunities() -> None:
    summary = SummaryService().build(
        [
            {"role": "colleague", "text": "I will take ownership of this for you."},
            {"role": "customer", "text": "Thank you."},
        ]
    )

    payload = summary.model_dump()

    assert "strengths" in payload
    assert "missed_opportunities" in payload
