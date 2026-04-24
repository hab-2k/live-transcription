from pathlib import Path

from app.services.coaching.rule_engine import RuleEngine


def test_rule_engine_flags_missing_ownership_statement() -> None:
    engine = RuleEngine.from_file(Path("backend/config/rules/default.yaml"))

    result = engine.evaluate(
        transcript=[
            {"role": "customer", "text": "I'm worried about this payment"},
            {"role": "colleague", "text": "Let me check"},
        ]
    )

    assert any(flag.code == "missing_ownership" for flag in result.flags)
