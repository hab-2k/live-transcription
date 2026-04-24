from pydantic import BaseModel


class CallSummary(BaseModel):
    strengths: list[str]
    missed_opportunities: list[str]
    flagged_moments: list[str]


class SummaryService:
    def build(self, transcript: list[dict[str, str]]) -> CallSummary:
        colleague_lines = " ".join(turn.get("text", "").lower() for turn in transcript if turn.get("role") == "colleague")
        strengths: list[str] = []
        missed: list[str] = []

        if "i will" in colleague_lines or "i can" in colleague_lines:
            strengths.append("Clear ownership statement")
        else:
            missed.append("Could show stronger ownership")

        if "next step" not in colleague_lines:
            missed.append("Could confirm the next step more clearly")

        return CallSummary(
            strengths=strengths or ["Maintained a clear call structure"],
            missed_opportunities=missed,
            flagged_moments=[],
        )
