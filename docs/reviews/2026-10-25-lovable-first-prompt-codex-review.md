# Codex review: lovable-first-prompt

- Date: 2026-10-25
- Target: docs/specs/2026-10-25-lovable-first-prompt.md
- Verdict: needs-attention

## Summary

The prompt is usable for a first mock, but its sample contradicts two engine rules and leaves opponent-window rendering ambiguous.

## Findings

### 1. [medium] Use the effective explosion limit in the sample

- File: docs/specs/2026-10-25-lovable-first-prompt.md:25-26
- Confidence: 1

The sample activates card 4 (+2 explosion limit) but supplies explosion_limit = 7. The engine's effective limit is 9. A frontend faithfully rendering this state will show an incorrect explosion meter; calculating the adjustment in the app would violate the prohibition on frontend game rules.

Recommendation: Set explosion_limit to 9 and specify that this field already includes active card effects.

Decision: taken - sample explosion_limit is 9 with card 4, and the prompt says the value already includes card effects

### 2. [medium] Replace the impossible yellow-chip placement fixture

- File: docs/specs/2026-10-25-lovable-first-prompt.md:38-44
- Confidence: 1

The pot retains white_2 immediately before yellow_2. Under the implemented first-spellbook yellow effect, that white chip returns to the bag. Consequently, the displayed pot, bag count and white_total cannot all represent the stated draw sequence. This gives the visual implementation an incorrect reference for returned-chip handling.

Recommendation: Use a fixture generated from a valid engine state, including the resulting coverage, bag counts and white total after the yellow effect.

Decision: taken - yellow_2 after white_2 replaced by green_2, so pot, bag and white total are consistent

### 3. [medium] Specify that opponent panels have no look-ahead window

- File: docs/specs/2026-10-25-lovable-first-prompt.md:15
- Confidence: 0.96

The instruction to give opponents panels 'of the same kind' follows a pot definition that includes illuminated scoring values. However, the sample supplies only one top-level window, and the parent spec explicitly restricts it to the viewing seat. Reusing that window for p2 would illuminate incorrect fields; inventing a separate window would require data or game logic the prompt does not provide.

Recommendation: State that window belongs exclusively to you, and that opponent pots—including enlarged panels—render their supplied chips without look-ahead rewards.

Decision: taken - prompt says the window belongs to the viewing player only; other pots show only placed chips, also enlarged

## Next steps

- Correct the mock state and clarify opponent-window rendering before submitting the prompt to Lovable.
