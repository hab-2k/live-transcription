# After-Call Summary and Review Navigation Design

## Summary

Refresh the ended-call experience so it feels like a real coaching review rather than a placeholder list dump.

The updated flow should:

- land on a proper after-call summary when the session stops
- show an LLM-generated `Call recap` at the top
- keep three coaching sections:
  - `Strengths`
  - `Weaknesses`
  - `Flagged moments`
- make `Flagged moments` mean possible vulnerabilities, dissatisfaction signals, or important things the caller may have missed
- let the user move from the summary to a read-only transcript review screen
- let the user start a new call or return to setup without pretending the ended session is still live
- generate the recap and all three sections through the existing OpenAI-compatible LLM integration rather than placeholder heuristics

## Problem Statement

The current after-call experience is not good enough for the product goal.

Today:

- the backend summary generator is a placeholder with very shallow heuristics
- the app already has an OpenAI-compatible LLM integration for coaching, but the summary path does not use it
- the summary content is too generic and often reads like empty filler
- the second section is named `Missed opportunities`, which does not match the desired colleague-facing coaching language
- the third section can look blank or arbitrary rather than highlighting genuine call risks or vulnerabilities
- once a session ends, there is no intentional review flow between the summary, transcript, and setup screens

The result is that the app technically produces a summary, but not one that feels like a useful after-call review.

## Goals

- Produce a concise, human-readable `Call recap` for the ended session.
- Generate the recap and coaching sections through the configured LLM, using the same integration boundary the app already uses for live coaching.
- Make `Strengths` focus on politeness, calmness, empathy, clarity, and helpful tone.
- Make `Weaknesses` focus on practical improvements in how the call was handled.
- Make `Flagged moments` focus on dissatisfaction, vulnerabilities, missed concerns, unclear commitments, or other important moments the caller may have missed.
- Ensure every section renders useful explicit copy rather than looking empty or broken.
- Land on the summary screen by default after `Stop Session`.
- Allow the user to move from summary to transcript review and from transcript review back to summary or setup.
- Allow `Start new call` to reset cleanly back to setup.

## Non-Goals

- No long-form analytics dashboard or call scorecard.
- No persistence or historical call browsing.
- No change to in-call coaching behavior.
- No attempt to make the ended transcript editable.
- No silent downgrade back to shallow heuristic bullets when the LLM path is available.

## Confirmed Product Decisions

- The after-call screen keeps exactly three coaching subsections:
  - `Strengths`
  - `Weaknesses`
  - `Flagged moments`
- `Flagged moments` remains the heading text.
- `Flagged moments` content means:
  - points of vulnerability
  - dissatisfaction signals
  - important things the caller might have missed
- The summary includes a short `Call recap` above the coaching sections.
- The after-call summary is LLM-driven and persona-aware.
- After stopping a session, the app lands on the summary screen first.
- The summary screen includes:
  - `View transcript`
  - `Start new call`
- The ended transcript review screen includes:
  - `Back to summary`
  - `Back to setup`
- Returning to transcript after stop is read-only review, not a resumed live session.

## User Experience

### After-Call Summary

When a session stops, the app shows an after-call review with this structure:

1. session-complete eyebrow
2. `Call summary` heading
3. short `Call recap`
4. `Strengths`
5. `Weaknesses`
6. `Flagged moments`
7. actions for `View transcript` and `Start new call`

The recap should be short and direct. It should tell the user what generally happened in the call, not restate every turn.

### Strengths

This section should focus on whether the colleague came across well in the interaction.

Expected signals include:

- polite or courteous phrasing
- helpful wording
- empathy or reassurance
- calm, steady responses
- clear structure or easy-to-follow wording

If there is weak evidence, the section should still show a useful explicit sentence rather than rendering as an empty list.

### Weaknesses

This section should focus on how the call could have gone better.

Expected signals include:

- weak ownership
- unclear next steps
- vague explanations
- missed probing questions
- insufficient reassurance
- lack of confirmation or closure

The wording should feel like coaching, not criticism.

### Flagged Moments

This section should highlight moments that may need more attention because they point to risk or dissatisfaction.

Expected signals include:

- caller frustration or dissatisfaction
- unresolved or partially resolved concerns
- ambiguity around what happens next
- possible missed vulnerabilities in the caller's situation
- important details the caller may not have understood or acknowledged
- risky or sensitive moments that were not handled explicitly enough

If there are no major flagged moments, the section should say so explicitly in a useful sentence.

### Ended Transcript Review

When the user selects `View transcript` from the summary screen, the app shows the transcript view for the ended call.

This screen reuses the transcript-first layout but behaves differently from a live session:

- transcript remains visible
- nudges may remain visible as session history if already present
- no live session controls like `Pause Coaching` or `Stop Session`
- clear review navigation actions replace the live controls

The user can then:

- go back to the summary
- go back to setup

### Starting a New Call

When the user selects `Start new call` from the summary, the app should reset to setup and clear ended-session navigation state.

This should behave like intentionally beginning a fresh session, not like partially reviving the last one.

## Backend Design

### Summary Contract

The backend after-call summary payload should become:

- `recap`
- `strengths`
- `weaknesses`
- `flagged_moments`

The desktop client should normalize this into its renderer-facing summary view model.

### Summary Generation

The summary generator should stop relying on the current minimal phrase checks and instead use the existing OpenAI-compatible LLM integration as the primary summary engine.

The summary prompt should be persona-aware and based on:

- transcript history for the session
- relevant local rule outputs or risk flags
- the active persona pack or coaching posture
- a strict output contract for `recap`, `strengths`, `weaknesses`, and `flagged_moments`

Recommended approach:

- add a dedicated after-call summary prompt path rather than reusing the live nudge prompt as-is
- instruct the model to produce:
  - a short recap of what happened in the call
  - strengths centered on politeness, empathy, helpfulness, and tone
  - weaknesses centered on specific coaching improvements
  - flagged moments centered on dissatisfaction, vulnerability, or important missed points
- require concise structured output that the backend can parse into the stable summary schema
- keep the backend responsible for validation and normalization of the model response before returning it to the UI

### Fallback Behavior

The product requirement is that summary content comes from the LLM path.

That means the backend should not silently replace LLM output with generic heuristic bullets, because that recreates the current problem in a less obvious form.

Instead:

- if the transcript is thin, the prompt should explicitly tell the model to say evidence is limited while still returning useful coaching
- if the LLM response is malformed, the backend should validate, repair if possible, or return an explicit summary-unavailable result
- if the LLM call fails, the UI should show an honest unavailable state rather than pretending a real summary was produced

## Desktop Design

### State Model

The desktop app needs an ended-session view mode rather than treating all non-setup states as effectively live.

Recommended shape:

- keep session lifecycle status: `setup`, `live`, `ended`
- add an ended-session view selector:
  - `summary`
  - `transcript`

On `complete_session`, the reducer should:

- mark the session as `ended`
- store the summary payload
- default the ended view to `summary`

### Summary Screen

The summary screen should:

- render the `Call recap`
- render `Strengths`, `Weaknesses`, and `Flagged moments`
- show explicit section copy when arrays would otherwise feel empty
- expose `View transcript` and `Start new call`

### Transcript Review Screen

The transcript review screen should reuse the main transcript layout as much as possible.

However, once the session is ended:

- live controls must disappear
- review-navigation controls must appear instead

Recommended review actions:

- `Back to summary`
- `Back to setup`

## Testing

### Backend Tests

Add coverage that verifies:

- the summary service sends a structured after-call prompt through the LLM client
- parsed summaries include `recap`, `strengths`, `weaknesses`, and `flagged_moments`
- persona and rule-context are included in the summary request path
- malformed model output is rejected or normalized correctly
- LLM failure returns an explicit unavailable path rather than heuristic filler

### Desktop Tests

Add coverage that verifies:

- summary screen renders recap plus the three approved headings
- summary screen renders `View transcript` and `Start new call`
- stopping a session lands on summary by default
- `View transcript` transitions to transcript review mode
- transcript review mode hides live controls
- transcript review mode shows `Back to summary` and `Back to setup`
- `Start new call` and `Back to setup` both return to setup cleanly

## Risks and Tradeoffs

- LLM-generated summaries should be much more useful than heuristic bullets, but they introduce response-format and availability risks that must be handled explicitly.
- Reusing the live transcript screen for ended review keeps implementation small, but requires care so ended-state controls do not look like live-session controls.
- Summary quality will still depend on transcript quality, so the prompt and UI should prefer explicit, honest wording when evidence is weak.
