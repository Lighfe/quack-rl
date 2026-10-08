# Codex review: quack-rl-design-spec

- Date: 2026-10-08
- Target: 6c4960e..HEAD
- Verdict: needs-attention

## Summary

Reviewed git diff 6c4960e..HEAD. This documentation-only range has two concrete inconsistencies to resolve before implementation. No tests ran; diff whitespace checks passed.

## Findings

### 1. [medium] Add the promised ignore rule for game records

- File: /home/julian/tuberlin/projects/ai-dev-tools-zoomcamp/quack-rl/docs/specs/2026-10-08-quack-rl-design.md:175
- Confidence: 1

The spec states that data/ is gitignored, but the tracked .gitignore contains no such rule. Following the documented storage paths would leave human records and generated datasets eligible for accidental commits to this public repository.

Recommendation: Add /data/ to the repository's .gitignore and confirm representative record and dataset paths are ignored.

Decision: taken - added /data/ to .gitignore; checked that a record path is ignored

### 2. [medium] Account for legitimate chip creation and removal in the invariant

- File: /home/julian/tuberlin/projects/ai-dev-tools-zoomcamp/quack-rl/docs/specs/2026-10-08-quack-rl-design.md:227
- Confidence: 0.99

The proposed invariant that chips are never created or lost conflicts with legal actions: purchases and the orange bonus die add chips, while removing a White 1 deletes one. Applied literally to random games, this invariant would reject correct engine behavior.

Recommendation: Specify conservation per chip type across bag and placed chips, adjusted for purchases, die rewards, and removals.

Decision: taken - invariant reworded as per-type chip accounting; also fixed rules 4.4 so Remove White 1 counts placed chips, and made the reset back into the bag explicit

## Next steps

- Add the missing ignore rule and correct the chip-accounting invariant before deriving implementation tests.
