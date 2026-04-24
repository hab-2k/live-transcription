from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from app.contracts.events import RuleFlagEvent


@dataclass(slots=True)
class RuleEvaluation:
    flags: list[RuleFlagEvent]


class RuleEngine:
    def __init__(self, rules: dict[str, Any]) -> None:
        self.rules = rules

    @classmethod
    def from_file(cls, path: Path) -> "RuleEngine":
        data = yaml.safe_load(path.read_text()) or {}
        return cls(rules=data)

    def evaluate(self, transcript: list[dict[str, Any]]) -> RuleEvaluation:
        flags: list[RuleFlagEvent] = []
        rule = self.rules.get("missing_ownership", {})
        customer_keywords = [word.lower() for word in rule.get("customer_keywords", [])]
        ownership_keywords = [word.lower() for word in rule.get("ownership_keywords", [])]
        customer_text = " ".join(
            turn.get("text", "").lower() for turn in transcript if turn.get("role") == "customer"
        )
        colleague_text = " ".join(
            turn.get("text", "").lower() for turn in transcript if turn.get("role") == "colleague"
        )

        if any(keyword in customer_text for keyword in customer_keywords) and not any(
            keyword in colleague_text for keyword in ownership_keywords
        ):
            flags.append(
                RuleFlagEvent(
                    code="missing_ownership",
                    message=rule.get("message", "State ownership and confirm the next step."),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
            )

        return RuleEvaluation(flags=flags)
