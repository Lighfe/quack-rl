# Codex adversarial review: quack-rl-design-spec

- Date: 2026-10-08
- Target: branch diff against 6c4960e (spec and rules v1)
- Tool: Codex plugin, adversarial review
- Verdict: needs-attention

## Findings

### 1. [high] Version engine semantics, not only rules and components

Keeping old rulesets and components does not preserve phase order, legality, scoring or termination in the engine core; the header's engine version drives no replay dispatch, so "old records can always replay" is unsupported. Recommendation: an immutable replay compatibility identifier covering engine semantics, explicit rejection of unsupported versions, historical fixtures.

Decision: partly taken - the rules version now names the complete game behavior including the engine's transition logic; behavior changes, also engine bug fixes, supersede the version; the engine replays only explicitly supported versions and refuses others with a clear error; golden fixtures per supported version. No promise to keep every old version runnable.

### 2. [medium] Replay consistency does not establish chance validity

A corrupted record with an impossible draw can stay internally consistent. Recommendation: validate each chance outcome against the pre-event state, require exact consumption, separate seed verification, corrupted-record fixtures.

Decision: taken - spec 6.1 and 8.

### 3. [medium] Removing the last placed White 1 can change the tie-break

Final field is defined by the last placed chip; removing it in the round 9 shop could change the tie-break under one reading.

Decision: rejected - the final field is the round result, a one-time cash-out settled when brewing ends; later actions do not change it. The rules wording (4.2, 5) now says so explicitly to avoid the misreading.

### 4. [medium] Define one transition boundary for online play and dataset export

Actionless resolve steps and forced Wait steps can be cut differently by the env and the export. Recommendation: one decision-to-decision projection, masks on pre-action observations, terminal observations, equivalence test.

Decision: taken - spec 5.1 "RL step boundary" and 8.

### 5. [medium] Bag visibility does not guarantee a Markov single-seat environment

Against human or adaptive opponents, a single seat's view is not Markov. Recommendation: narrow the claim, keep opponent context in exports.

Decision: taken - spec 5.2 narrowed; 6.3 episode metadata names the opponent.
