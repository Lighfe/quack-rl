# Codex review: rule-fixes-and-brew-screen-spec

- Date: 2026-10-25
- Target: docs/specs/2026-10-25-rule-fixes-and-brew-screen.md
- Verdict: needs-attention

## Summary

The rule fixes are coherent, but the browser/API contract has gaps that could stall games or misapply actions. Review based on the spec and current engine; no tests run.

## Findings

### 1. [high] Specify automatic advancement until a human decision

- File: docs/specs/2026-10-25-rule-fixes-and-brew-screen.md:73-75
- Confidence: 0.98

The service only explicitly steps after actions arrive. However, new_game starts in CARD, and CARD and RESOLVE require step(..., actions=None); inactive seats require automatic wait actions. Without an explicit advancement loop, a new human game can stall before its first decision, and a stopped human can block the remaining bot. The bot-only acceptance test does not cover these mixed-seat transitions.

Recommendation: Require advancement on creation and after submissions through automatic phases, forced waits and bot decisions until human input is needed or the game ends. Test human/bot games where the human stops first.

Decision: taken - the service section now requires advancement at creation and after each step through card/resolve phases, wait-only seats and bot decisions; tests for human-vs-bot advancement added

### 2. [high] Include blue-hand choices in the brew screen

- File: docs/specs/2026-10-25-rule-fixes-and-brew-screen.md:110
- Confidence: 0.99

Blue chips create a hand during BREW, where legal actions include play:<index> instead of draw. The brew-screen decision list only specifies Draw, Stop, flask and card 17; the generic action buttons are specified only for other phases. An implementation following this division cannot play a chip from a blue hand, preventing full gameplay.

Recommendation: Specify selectable hand chips mapped to the service's legal play actions, with a generic legal-action fallback. Test a blue draw and a chained blue placement through the UI.

Decision: taken - the brew screen shows blue hand chips as selectable play actions with the put-back buttons, plus a plain-button fallback for any legal action without its own control

### 3. [medium] Bind action submissions to a decision revision

- File: docs/specs/2026-10-25-rule-fixes-and-brew-screen.md:75-80
- Confidence: 0.96

The request contains only seat and action, and validation checks current legality. A duplicated or delayed draw request can therefore execute another draw after the first request advances the game, because draw remains legal. Pending submissions also have no defined replacement or rejection behavior, leaving hot-seat handoff ambiguous.

Recommendation: Return a decision revision, require it on submissions, and process each game's submissions atomically. Define duplicate handling and exclude seats with accepted pending actions from the seats still awaiting input. Test repeated and stale requests.

Decision: taken - submissions carry the decision revision; stale or duplicate submissions give 409, one game processes submissions one at a time, accepted seats leave to_act; test added

### 4. [medium] Define look-ahead field numbers at the track boundary

- File: docs/specs/2026-10-25-rule-fixes-and-brew-screen.md:82
- Confidence: 1.0

The spec assigns fields scoring field + k while also requiring exact correspondence with ahead. The existing _ahead clamps every index to track_end, repeating field 53 near the boundary. Literal addition would produce nonexistent fields up to 63, which the frontend's 0–53 layout cannot render.

Recommendation: Specify field = min(scoring_field + k, track_end), explain how repeated cells render, and compare the money/points/ruby projection with ahead. Add a boundary case at field 53.

Decision: taken - window is min(scoring field + k, track_end), the frontend lights each field once, other seats have no window; boundary test added

## Next steps

- Clarify service advancement and action revision semantics.
- Add blue-hand interaction and track-boundary acceptance cases.
