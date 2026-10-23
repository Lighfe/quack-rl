# M1 playtest fixes (addendum to the design spec)

Source: the owner's first playtest of M1 (2026-10-09). Base: `docs/specs/2026-10-08-quack-rl-design.md`, rules `docs/rules/rules-v1.md`.

Rules version stays `v1`. Versioning starts when real data exists; the one test record is deleted and the golden records are regenerated.

## 1. Scoring field

A chip still lands on its own field (green 1 from field 0 lands on 1). The **scoring field** is the first free field after the last placed chip:

`scoring_field = min(landing_field + 1, track_end)`

Ruby and money come from the scoring field, after an explosion too (money halved as before). The bonus die test ("furthest") and the tie-break after the last round compare scoring fields. A chip on field 53 scores field 53 (money 35), so landings on 52 and 53 tie.

The landing field stays the state value (`final_field`) and the footer value. The scoring field is derived and not stored.

## 2. Last-round multiplier

In the last round, the money a player earns is multiplied by 1.5, rounded down. The order is: field money, halved if the potion exploded, plus 1 if the bonus die gave money, then the multiplier. Unspent money is still lost at the reset. The factor is a ruleset value (`last_round_money_percent = 150`), not engine code.

## 3. Number of rounds

`play` and `simulate` get `--rounds N` (default 9, at least 1). The last round is round N. The record header stores `rounds`; `verify` and `replay` use it. Normal games use 9; shorter games are for testing mechanics.

## 4. Display

- The board shows the scoring field and its money, and whether stopping now gives a ruby (replaces "next ruby").
- The bonus die result is a clear line of its own in the resolve output.

## Not in this stage

Bot logic (issue 16) and the RL environment (M2).
