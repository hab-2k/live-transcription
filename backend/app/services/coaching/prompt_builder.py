from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class PromptBuilder:
    def __init__(self, persona: dict[str, Any]) -> None:
        self.persona = persona

    @classmethod
    def from_file(cls, path: Path) -> "PromptBuilder":
        data = yaml.safe_load(path.read_text()) or {}
        return cls(persona=data)

    def build(self, transcript: list[dict[str, Any]], flags: list[dict[str, Any]]) -> str:
        persona_name = self.persona.get("name", "coach")
        system_prompt = self.persona.get("system_prompt", "")
        transcript_lines = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('text', '')}" for turn in transcript
        )
        flag_lines = "\n".join(flag.get("message", "") for flag in flags) or "No active flags."

        return (
            f"{system_prompt}\n"
            f"Persona: {persona_name}\n"
            f"Recent transcript:\n{transcript_lines}\n"
            f"Rule flags:\n{flag_lines}\n"
            "Return one short live coaching nudge."
        )

    def build_after_call_summary(
        self,
        *,
        transcript: list[dict[str, Any]],
        flags: list[dict[str, Any]],
    ) -> str:
        persona_name = self.persona.get("name", "coach")
        system_prompt = self.persona.get("system_prompt", "")
        summary_prompt = self.persona.get(
            "after_call_summary_prompt",
            "Write an after-call coaching summary.",
        )
        transcript_lines = "\n".join(
            f"{turn.get('role', 'unknown')}: {turn.get('text', '')}" for turn in transcript
        ) or "No transcript provided."
        flag_lines = "\n".join(flag.get("message", "") for flag in flags) or "No flagged moments."

        return (
            f"{system_prompt}\n"
            f"Persona: {persona_name}\n"
            f"{summary_prompt}\n"
            "Return valid JSON with keys recap, strengths, weaknesses, flagged_moments.\n"
            f"Transcript:\n{transcript_lines}\n"
            f"Flags:\n{flag_lines}\n"
        )
