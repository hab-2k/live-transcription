from dataclasses import dataclass


@dataclass(slots=True)
class DebugRecord:
    kind: str
    message: str


class DebugStore:
    def __init__(self) -> None:
        self._records: list[DebugRecord] = []

    def record(self, kind: str, message: str) -> None:
        self._records.append(DebugRecord(kind=kind, message=message))

    def list(self) -> list[DebugRecord]:
        return list(self._records)
