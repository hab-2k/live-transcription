from app.services.coaching.nudge_service import NudgeService


def test_nudge_service_deduplicates_similar_advice() -> None:
    service = NudgeService()

    first = service.should_emit("Show empathy first")
    second = service.should_emit("Show empathy first")

    assert first is True
    assert second is False
