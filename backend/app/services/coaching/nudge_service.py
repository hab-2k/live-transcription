class NudgeService:
    def __init__(self) -> None:
        self._last_message: str | None = None

    def should_emit(self, message: str) -> bool:
        normalized = " ".join(message.lower().split())
        if not normalized or normalized == self._last_message:
            return False

        self._last_message = normalized
        return True
